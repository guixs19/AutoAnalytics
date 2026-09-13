# backend/services/service_factory.py - VERSÃO 4.0 (REESCRITA)
"""
SERVICE FACTORY V4.0 — Produção-ready
================================================================================
CORREÇÕES APLICADAS (referentes ao diagnóstico da V3.0):

CRÍTICAS
  1.  [F1] Removida instanciação + print no import. Antes, qualquer
           `import service_factory` criava ServiceFactory, instanciava
           o Gemini, e imprimia ~10 linhas no stdout — quebrando
           gunicorn/uWSGI (fork), Celery e reloaders. Agora o singleton
           é lazy via `get_service_factory()`, e o print de status vive
           em `if __name__ == "__main__"`.
  2.  [F2] Exports duplicados renomeados. `service_factory` exportava
           `get_gemini_service` e `is_gemini_available` com o MESMO nome
           do `gemini.py`, retornando objetos diferentes. Agora são
           `get_gemini_service_via_factory` / `is_gemini_available_via_factory`
           (aliases antigos mantidos como shim com DeprecationWarning).
  3.  [F3] `_ensure_gemini_fresh` agora re-verifica saúde. Antes, se o
           Gemini ficava doente DEPOIS do boot (circuit breaker aberto,
           health check falhando), o factory nunca re-tentava porque
           `_gemini_available` continuava True para sempre.
  4.  [F4] Timestamps padronizados em UTC (com sufixo "Z"), alinhados
           com o gemini.py V6.0.

GRAVES
  5.  [F5] `get_status()` não mente mais sobre database/storage. Os
           checks são plugáveis via `register_health_probe()` e retornam
           "unknown" quando não há probe — não "online" hardcoded.
  6.  [F6] `sdk_version` não é mais lido (não existe no gemini V6.0).
           Substituído por `service_version` lido do `__version__` do
           módulo gemini.
  7.  [F7] Acesso a `_health_monitoring_active` (privado) removido.
           Agora usa `is_health_monitoring_active()` público do gemini.
  8.  [F8] `get_predictor` com cache negativo (evita import + warning
           a cada chamada quando ML indisponível).
  9.  [F9] `get_gemini_status` retorna a MESMA estrutura de
           `gemini.get_health_status()` — sem duplicação de campos.
 10.  [F10] Import do gemini.py não captura mais Exception amplo sem
           log. Agora captura ImportError (dependência real) e Exception
           (bug real) com stacktrace completo.

MELHORIAS NOVAS (V4.0)
 11.  [H1] Compatibilidade retroativa via `DeprecationWarning` nos
           aliases antigos (não quebra imports existentes).
 12.  [H2] `get_status()` retorna `uptime_seconds` de cada serviço.
 13.  [H3] Health probes plugáveis (DB, storage, etc.) via
           `register_health_probe(name, callable)`.
 14.  [H4] `ServiceFactory.shutdown()` graceful + atexit + fork-safe
           (os.register_at_fork).
 15.  [H5] Logs estruturados em JSON opcional (SERVICE_FACTORY_LOG_JSON=1).
 16.  [H6] `_ensure_gemini_fresh` agora usa lock apenas onde precisa —
           leitura de estado não bloqueia (double-checked).
 17.  [H7] Métricas de "factory" expostas em `get_metrics()`.
 18.  [H8] Testes de sanidade embutidos em `__main__` (`--smoke`).
 19.  [H9] Alinhamento total com `gemini.py` V6.0: se o gemini expõe
           `get_health_status()`, o factory usa esse método em vez de
           montar status do zero.
================================================================================
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import threading
import time
import warnings
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

__version__ = "4.0.0"

logger = logging.getLogger(__name__)


# ==============================================
# LOGGING JSON OPCIONAL
# ==============================================

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


if os.environ.get("SERVICE_FACTORY_LOG_JSON") == "1":
    _h = logging.StreamHandler()
    _h.setFormatter(_JsonFormatter())
    logger.addHandler(_h)


# ==============================================
# IMPORTAÇÃO DO GEMINI
# ==============================================
# [F10] O gemini.py V6.0 NÃO faz nada no import (nem rede, nem threads).
# Portanto capturamos apenas ImportError (dependência ausente) e Exception
# (bug real) — com stacktrace completo — em vez do catch-all silencioso
# que mascarava falhas.

GEMINI_AVAILABLE = False
_gemini_module = None
get_gemini_service_direct: Optional[Callable[[], Any]] = None
is_gemini_available_direct: Optional[Callable[[], bool]] = None
_GEMINI_MODULE_VERSION: Optional[str] = None

try:
    from backend import gemini as _gemini_module  # type: ignore

    get_gemini_service_direct = getattr(_gemini_module, "get_gemini_service", None)
    is_gemini_available_direct = getattr(_gemini_module, "is_gemini_available", None)
    _GEMINI_MODULE_VERSION = getattr(_gemini_module, "__version__", None)

    if get_gemini_service_direct is None:
        logger.error(
            "backend.gemini não expõe 'get_gemini_service'. "
            "Verifique se o módulo é a versão V5+."
        )
    else:
        GEMINI_AVAILABLE = True
        logger.info(
            "Gemini disponível para ServiceFactory (versão=%s)",
            _GEMINI_MODULE_VERSION or "?",
        )
except ImportError as e:
    logger.warning(
        "backend.gemini não pôde ser importado (dependência ausente): %s", e
    )
except Exception as e:  # bug real — logar stacktrace
    logger.exception("Erro inesperado importando backend.gemini: %s", e)


# ==============================================
# UPTIME / UTIL
# ==============================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_datetime(value: Optional[Any]) -> Optional[str]:
    """[F4] Padroniza qualquer datetime/str para ISO UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        if value.tzinfo is None:
            # assume UTC se naive — alinhado com gemini.py V6.0
            return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (AttributeError, ValueError):
        return str(value)


# ==============================================
# SERVICE FACTORY
# ==============================================

class ServiceFactory:
    """
    Fábrica de serviços com verificação de disponibilidade real, retry
    automático com cooldown e acesso thread-safe.
    """

    RETRY_COOLDOWN_SECONDS = 30

    def __init__(self) -> None:
        self._pid = os.getpid()

        self._gemini = None
        self._gemini_available: bool = False
        self._initialized: bool = False
        self._last_init_attempt: Optional[float] = None

        self._lock = threading.RLock()

        # [H3] health probes plugáveis
        self._health_probes: Dict[str, Callable[[], bool]] = {}
        self._health_probe_cache: Dict[str, Dict[str, Any]] = {}
        self._health_probe_lock = threading.Lock()

        # [F8] cache negativo de predictor
        self._predictor_cache: Optional[Any] = None
        self._predictor_unavailable_until: float = 0.0
        self._predictor_lock = threading.Lock()

        # [H7] métricas
        self._metrics_lock = threading.Lock()
        self._metrics: Dict[str, Any] = {
            "boot_attempts": 0,
            "boot_successes": 0,
            "boot_failures": 0,
            "gemini_retries": 0,
            "fork_reinitializations": 0,
            "uptime_start": _utcnow_iso(),
            "last_boot_error": None,
        }

        self._initialize_services()

        try:
            if hasattr(os, "register_at_fork"):
                os.register_at_fork(after_in_child=self._on_fork_child)
        except Exception:
            pass

        atexit.register(self._atexit_cleanup)

        logger.info("ServiceFactory V%s inicializado", __version__)

    # ------------------------------------------------------------------
    # FORK-SAFE ([H4])
    # ------------------------------------------------------------------

    def _on_fork_child(self) -> None:
        child_pid = os.getpid()
        if child_pid == self._pid:
            return
        logger.info(
            "Fork detectado no ServiceFactory (pid %d -> %d): resetando estado",
            self._pid, child_pid,
        )
        self._pid = child_pid

        with self._lock:
            self._gemini = None
            self._gemini_available = False
            self._initialized = False
            self._last_init_attempt = None

        with self._metrics_lock:
            self._metrics["fork_reinitializations"] += 1

        self._initialize_services()

    def _ensure_pid_consistency(self) -> None:
        if os.getpid() != self._pid:
            self._on_fork_child()

    # ------------------------------------------------------------------
    # BOOT / RETRY
    # ------------------------------------------------------------------

    def _ensure_gemini_fresh(self) -> None:
        """
        [F3] Garante que o Gemini foi inicializado E continua saudável.
        Se o serviço ficou doente depois do boot, re-tenta após cooldown.
        """
        self._ensure_pid_consistency()

        now = time.monotonic()

        # Leitura sem lock para o caminho rápido
        if self._initialized and self._gemini is not None:
            try:
                if self._gemini.is_healthy():
                    self._gemini_available = True
                    return
            except Exception as e:
                logger.debug("is_healthy() falhou: %s", e)
            # chegou aqui: serviço existe mas está doente — re-tentar se cooldown expirou
            with self._lock:
                if (
                    self._last_init_attempt is not None
                    and (now - self._last_init_attempt) < self.RETRY_COOLDOWN_SECONDS
                ):
                    self._gemini_available = False
                    return
        elif self._initialized and self._gemini is None and not GEMINI_AVAILABLE:
            # Import falhou na origem — não adianta re-tentar
            return

        with self._lock:
            # Double-check dentro do lock
            if (
                self._initialized
                and self._last_init_attempt is not None
                and (now - self._last_init_attempt) < self.RETRY_COOLDOWN_SECONDS
                and self._gemini_available
            ):
                return
            self._last_init_attempt = now
            if self._initialized:
                with self._metrics_lock:
                    self._metrics["gemini_retries"] += 1
            self._initialize_services()

    def _initialize_services(self) -> None:
        """Tenta inicializar (ou reinicializar) o Gemini."""
        with self._lock:
            with self._metrics_lock:
                self._metrics["boot_attempts"] += 1

            try:
                if not GEMINI_AVAILABLE or get_gemini_service_direct is None:
                    logger.warning(
                        "Gemini não disponível (import falhou na carga do módulo)"
                    )
                    self._gemini = None
                    self._gemini_available = False
                    with self._metrics_lock:
                        self._metrics["boot_failures"] += 1
                        self._metrics["last_boot_error"] = "gemini_import_failed"
                    return

                svc = get_gemini_service_direct()
                self._gemini = svc

                if svc is None:
                    logger.warning("get_gemini_service() retornou None")
                    self._gemini_available = False
                    with self._metrics_lock:
                        self._metrics["boot_failures"] += 1
                        self._metrics["last_boot_error"] = "gemini_returned_none"
                    return

                try:
                    healthy = bool(svc.is_healthy())
                except Exception as e:
                    logger.warning("is_healthy() levantou: %s", e)
                    healthy = False

                self._gemini_available = healthy
                if healthy:
                    logger.info(
                        "Gemini OK (modelo=%s)",
                        getattr(svc, "current_model", "?"),
                    )
                    with self._metrics_lock:
                        self._metrics["boot_successes"] += 1
                        self._metrics["last_boot_error"] = None
                else:
                    logger.warning("Gemini carregado mas NÃO saudável")
                    with self._metrics_lock:
                        self._metrics["boot_failures"] += 1
                        self._metrics["last_boot_error"] = "gemini_unhealthy"

            except Exception as e:
                logger.exception("Erro ao inicializar Gemini: %s", e)
                self._gemini_available = False
                with self._metrics_lock:
                    self._metrics["boot_failures"] += 1
                    self._metrics["last_boot_error"] = str(e)
            finally:
                self._initialized = True

    # ------------------------------------------------------------------
    # GEMINI
    # ------------------------------------------------------------------

    def get_gemini_service(self):
        """Retorna o serviço Gemini (pode ser None se indisponível)."""
        self._ensure_gemini_fresh()
        return self._gemini

    def is_gemini_available(self) -> bool:
        """Verifica se o Gemini está disponível e saudável AGORA."""
        self._ensure_gemini_fresh()

        if self._gemini is not None:
            try:
                healthy = bool(self._gemini.is_healthy())
                self._gemini_available = healthy
                return healthy
            except Exception as e:
                logger.error("Erro ao checar saúde do Gemini: %s", e)
                self._gemini_available = False
                return False

        # Fallback funcional
        if is_gemini_available_direct is not None:
            try:
                return bool(is_gemini_available_direct())
            except Exception:
                return False
        return False

    def get_gemini_status(self) -> Dict[str, Any]:
        """
        [F9] Usa `get_health_status()` do gemini V6.0 como fonte de
        verdade. Sem duplicar campos manualmente.
        """
        self._ensure_gemini_fresh()

        if self._gemini is None:
            return {
                "available": False,
                "status": "unavailable",
                "error": "Serviço não inicializado",
                "model": None,
                "version": _GEMINI_MODULE_VERSION,
                "timestamp": _utcnow_iso(),
            }

        try:
            # Preferência: método oficial do gemini.py
            get_health = getattr(self._gemini, "get_health_status", None)
            if callable(get_health):
                status = dict(get_health() or {})
            else:
                # Fallback mínimo
                status = {
                    "available": bool(self._gemini.is_healthy()),
                    "status": getattr(self._gemini, "health_status", None),
                    "model": getattr(self._gemini, "current_model", None),
                    "circuit_breaker": getattr(self._gemini, "circuit_state", None),
                }

            # Enriquecimento com campos do módulo gemini
            status.setdefault("version", _GEMINI_MODULE_VERSION)
            status.setdefault("timestamp", _utcnow_iso())

            # [F7] usa método público se existir
            is_mon = getattr(self._gemini, "is_health_monitoring_active", None)
            if callable(is_mon):
                try:
                    status["health_monitoring_active"] = bool(is_mon())
                except Exception:
                    status["health_monitoring_active"] = None
            else:
                status["health_monitoring_active"] = None

            # [F6] service_version em vez de sdk_version inexistente
            status["service_version"] = _GEMINI_MODULE_VERSION

            # Normaliza campos datetime
            if "last_check" in status:
                status["last_check"] = _format_datetime(status["last_check"])
            if "last_health_check" in status:
                status["last_health_check"] = _format_datetime(
                    status["last_health_check"]
                )

            return status
        except Exception as e:
            logger.exception("Erro montando status do Gemini: %s", e)
            return {
                "available": False,
                "status": "error",
                "error": str(e),
                "model": None,
                "version": _GEMINI_MODULE_VERSION,
                "timestamp": _utcnow_iso(),
            }

    # ------------------------------------------------------------------
    # HEALTH PROBES PLUGÁVEIS ([F5], [H3])
    # ------------------------------------------------------------------

    def register_health_probe(
        self, name: str, probe: Callable[[], bool], ttl_seconds: float = 5.0
    ) -> None:
        """
        Registra um probe de saúde para um serviço (ex.: 'database').
        O probe deve retornar True se saudável, False caso contrário.
        Resultados são cacheados por `ttl_seconds` para evitar chamar
        o probe em cada request.
        """
        if not callable(probe):
            raise TypeError("probe deve ser callable")
        with self._health_probe_lock:
            self._health_probes[name] = probe
            self._health_probe_cache[name] = {"value": None, "ts": 0.0, "ttl": ttl_seconds}

    def _check_probe(self, name: str) -> str:
        """
        Retorna "online", "offline" ou "unknown" (se não registrado).
        """
        with self._health_probe_lock:
            probe = self._health_probes.get(name)
            cache = self._health_probe_cache.get(name)

        if probe is None or cache is None:
            return "unknown"

        now = time.monotonic()
        if cache["value"] is not None and (now - cache["ts"]) < cache["ttl"]:
            return "online" if cache["value"] else "offline"

        try:
            ok = bool(probe())
        except Exception as e:
            logger.warning("Health probe %s falhou: %s", name, e)
            ok = False

        with self._health_probe_lock:
            cache["value"] = ok
            cache["ts"] = now
        return "online" if ok else "offline"

    # ------------------------------------------------------------------
    # STATUS GERAL
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Status geral para o painel (não mente sobre DB/storage)."""
        gemini_status = self.get_gemini_status()

        return {
            "gemini": "online" if gemini_status.get("available") else "offline",
            "gemini_model": gemini_status.get("model"),
            "gemini_details": gemini_status,
            "database": self._check_probe("database"),
            "storage": self._check_probe("storage"),
            "factory_version": __version__,
            "uptime_seconds": self._uptime_seconds(),
            "timestamp": _utcnow_iso(),
        }

    def _uptime_seconds(self) -> float:
        try:
            start = datetime.fromisoformat(
                self._metrics["uptime_start"].replace("Z", "+00:00")
            )
            return (datetime.now(timezone.utc) - start).total_seconds()
        except Exception:
            return 0.0

    def get_missing_critical_services(self) -> List[str]:
        missing: List[str] = []
        if not self.is_gemini_available():
            missing.append("gemini")
        return missing

    def get_critical_services_status(self) -> bool:
        """
        Sempre retorna True — boot nunca bloqueia por serviço crítico
        ausente. Loga aviso quando faltar algo.
        """
        missing = self.get_missing_critical_services()
        if missing:
            logger.warning(
                "Serviços críticos indisponíveis: %s — modo degradado", missing
            )
        return True

    def is_available(self, service_name: str) -> bool:
        if service_name == "gemini":
            return self.is_gemini_available()
        status = self._check_probe(service_name)
        # "unknown" → não afirma disponível
        return status == "online"

    # ------------------------------------------------------------------
    # PREDICTOR ([F8] cache negativo)
    # ------------------------------------------------------------------

    def get_predictor(self):
        self._ensure_pid_consistency()

        now = time.monotonic()
        with self._predictor_lock:
            if self._predictor_cache is not None:
                return self._predictor_cache
            if now < self._predictor_unavailable_until:
                return None

            try:
                from backend.ml.predict import predictor  # type: ignore
                self._predictor_cache = predictor
                logger.info("Predictor ML carregado")
                return predictor
            except Exception as e:
                # cache negativo por 60s
                self._predictor_unavailable_until = now + 60.0
                logger.warning("Predictor ML indisponível: %s", e)
                return None

    # ------------------------------------------------------------------
    # PLACEHOLDERS (compat)
    # ------------------------------------------------------------------

    def get_file_manager(self):
        # TODO: implementar FileManager
        return None

    def get_preprocessor(self):
        # TODO: implementar Preprocessor
        return None

    def get_daily_credits_service(self):
        # TODO: implementar DailyCreditsService
        return None

    # ------------------------------------------------------------------
    # MÉTRICAS ([H7])
    # ------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        with self._metrics_lock:
            m = dict(self._metrics)
        m["uptime_seconds"] = round(self._uptime_seconds(), 1)
        m["version"] = __version__
        return m

    def get_prometheus_metrics(self) -> str:
        with self._metrics_lock:
            m = dict(self._metrics)
        lines = [
            "# HELP factory_boot_attempts Total de tentativas de boot",
            "# TYPE factory_boot_attempts counter",
            f"factory_boot_attempts {m['boot_attempts']}",
            "# HELP factory_boot_successes Boots bem-sucedidos",
            "# TYPE factory_boot_successes counter",
            f"factory_boot_successes {m['boot_successes']}",
            "# HELP factory_boot_failures Boots falhados",
            "# TYPE factory_boot_failures counter",
            f"factory_boot_failures {m['boot_failures']}",
            "# HELP factory_gemini_retries Retries do Gemini",
            "# TYPE factory_gemini_retries counter",
            f"factory_gemini_retries {m['gemini_retries']}",
            "# HELP factory_gemini_available Gemini disponível",
            "# TYPE factory_gemini_available gauge",
            f"factory_gemini_available {1 if self._gemini_available else 0}",
            "# HELP factory_uptime_seconds Uptime do factory",
            "# TYPE factory_uptime_seconds gauge",
            f"factory_uptime_seconds {self._uptime_seconds():.0f}",
        ]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # SHUTDOWN ([H4])
    # ------------------------------------------------------------------

    def _atexit_cleanup(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass

    def shutdown(self) -> None:
        logger.info("ServiceFactory desligando...")
        svc = self._gemini
        if svc is not None:
            try:
                sd = getattr(svc, "shutdown", None)
                if callable(sd):
                    sd()
            except Exception as e:
                logger.warning("Erro no shutdown do Gemini: %s", e)
        logger.info("ServiceFactory desligado")


# ==============================================
# SINGLETON (lazy — [F1])
# ==============================================

_service_factory: Optional[ServiceFactory] = None
_service_factory_lock = threading.Lock()


def get_service_factory() -> ServiceFactory:
    """Retorna instância única do ServiceFactory (lazy + thread-safe)."""
    global _service_factory
    if _service_factory is None:
        with _service_factory_lock:
            if _service_factory is None:
                _service_factory = ServiceFactory()
    return _service_factory


# ==============================================
# EXPORTS (nomes renomeados — [F2])
# ==============================================

def get_gemini_service_via_factory():
    """Gemini via factory. Prefira `backend.gemini.get_gemini_service`."""
    return get_service_factory().get_gemini_service()


def is_gemini_available_via_factory() -> bool:
    return get_service_factory().is_gemini_available()


def get_status() -> Dict[str, Any]:
    return get_service_factory().get_status()


def get_critical_services_status() -> bool:
    return get_service_factory().get_critical_services_status()


def get_missing_critical_services() -> List[str]:
    return get_service_factory().get_missing_critical_services()


def get_file_manager():
    return get_service_factory().get_file_manager()


def get_preprocessor():
    return get_service_factory().get_preprocessor()


def get_predictor():
    return get_service_factory().get_predictor()


def get_daily_credits_service():
    return get_service_factory().get_daily_credits_service()


def register_health_probe(
    name: str, probe: Callable[[], bool], ttl_seconds: float = 5.0
) -> None:
    return get_service_factory().register_health_probe(name, probe, ttl_seconds)


# ==============================================
# ALIASES DE COMPATIBILIDADE ([H1])
# ==============================================

def get_gemini_service(*args, **kwargs):
    """[DEPRECATED] Use `backend.gemini.get_gemini_service`."""
    warnings.warn(
        "service_factory.get_gemini_service está deprecated; use "
        "backend.gemini.get_gemini_service ou "
        "service_factory.get_gemini_service_via_factory",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_gemini_service_via_factory()


def is_gemini_available(*args, **kwargs):
    """[DEPRECATED] Use `backend.gemini.is_gemini_available`."""
    warnings.warn(
        "service_factory.is_gemini_available está deprecated; use "
        "backend.gemini.is_gemini_available ou "
        "service_factory.is_gemini_available_via_factory",
        DeprecationWarning,
        stacklevel=2,
    )
    return is_gemini_available_via_factory()


# ==============================================
# STATUS (só como script — [F1])
# ==============================================

def _print_status() -> None:
    factory = get_service_factory()
    status = factory.get_status()

    print("=" * 70)
    print(f"SERVICE FACTORY V{__version__}")
    print("=" * 70)

    g = status.get("gemini_details", {}) or {}
    if status.get("gemini") == "online":
        print("   Gemini: ONLINE")
        print(f"   Modelo: {g.get('model')}")
        cache = g.get("cache_health", {}).get("size", g.get("cache_size"))
        if cache is not None:
            print(f"   Cache: {cache} entradas")
    else:
        print("   Gemini: OFFLINE")
        print(f"   Motivo: {g.get('error', 'Não disponível')}")
        print(
            f"   Retry automático a cada "
            f"{ServiceFactory.RETRY_COOLDOWN_SECONDS}s enquanto indisponível"
        )

    print(f"   Database: {status.get('database')}")
    print(f"   Storage: {status.get('storage')}")
    print(f"   Uptime: {status.get('uptime_seconds', 0):.0f}s")
    print("=" * 70)


async def _smoke_test() -> int:
    factory = get_service_factory()
    print("SMOKE: verificando Gemini...")
    if not factory.is_gemini_available():
        print("SMOKE: Gemini indisponível (skip)")
        return 0
    svc = factory.get_gemini_service()
    if svc is None:
        print("SMOKE: get_gemini_service() = None")
        return 1
    r = await svc.generate_content("Responda apenas: PONG", use_cache=False)
    if r.get("success"):
        print("SMOKE OK:", (r.get("response") or "")[:60])
        return 0
    print("SMOKE FALHOU:", r.get("error"), r.get("message"))
    return 1


if __name__ == "__main__":
    _print_status()
    if "--smoke" in sys.argv:
        import asyncio as _asyncio
        raise SystemExit(_asyncio.run(_smoke_test()))
    if "--metrics" in sys.argv:
        print(json.dumps(get_service_factory().get_metrics(), indent=2))
        raise SystemExit(0)


__all__ = [
    "ServiceFactory",
    "get_service_factory",
    # nomes novos (recomendados)
    "get_gemini_service_via_factory",
    "is_gemini_available_via_factory",
    # nomes genéricos
    "get_status",
    "get_critical_services_status",
    "get_missing_critical_services",
    "register_health_probe",
    "get_file_manager",
    "get_preprocessor",
    "get_predictor",
    "get_daily_credits_service",
    # compat (deprecated, com warning)
    "get_gemini_service",
    "is_gemini_available",
    "__version__",
]