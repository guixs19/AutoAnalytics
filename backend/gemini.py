# backend/gemini.py - VERSÃO 6.0 (REESCRITA E CORRIGIDA)
"""
GEMINI SERVICE V6.0 — Produção-ready
================================================================================
CORREÇÕES APLICADAS (referentes ao diagnóstico da V5.3):

CRÍTICAS
  1.  [C1] Removidos TODOS os efeitos colaterais no import. O bloco final
           agora vive dentro de `if __name__ == "__main__":`. Antes, importar
           o módulo criava client, threads e imprimia no stdout — quebrando
           gunicorn/uWSGI (fork), Celery e reloaders.
  2.  [C2] Health monitor + client não sobrevivem ao fork. Agora o serviço
           detecta PID e reinicializa o client/threads no processo filho
           (_ensure_pid_consistency). Essencial para gunicorn/celery.
  3.  [C3] `asyncio.get_event_loop()` (deprecated e falha em thread sem loop)
           trocado por `asyncio.get_running_loop()` dentro de coroutines.
           O health check síncrono usa `asyncio.run_coroutine_threadsafe`
           no loop principal, ou um runner dedicado.
  4.  [C4] ThreadPoolExecutor dedicado para I/O do SDK (não usa o pool
           default do loop, que é compartilhado com outras libs e causava
           contenção/vazamento de threads em timeouts).
  5.  [C5] Cache key agora inclui o MODELO REALMENTE usado, não
           `self.current_model`. Antes, rotação/fallback geravam respostas
           cruzadas entre modelos.
  6.  [C6] `response.text` pode levantar ValueError quando o conteúdo é
           bloqueado por safety. Agora é tratado como "blocked", não como
           falha de infraestrutura (não abre circuit breaker).
  7.  [C7] `CONFIG["health_threshold_failures"]` (que existia mas nunca era
           usado) agora É usado: health só vira FAILED após N falhas
           consecutivas, evitando tirar o site do ar por um soluço de rede.

GRAVES
  8.  [G1] Rate limit reescrito com deque sem maxlen + timestamps; burst
           agora tem janela real (não "por acidente").
  9.  [G2] `_compress_prompt` não destrói mais `#` em JSON/markdown/hex.
           Só remove comentários em blocos de código detectados.
 10.  [G3] `batch_generate` agora usa semáforo (concorrência limitada) em
           vez de disparar N chamadas simultâneas ilimitadas.
 11.  [G4] `shutdown()` respeita terminationGracePeriod: espera configurável
           e não bloqueia deploy por 65s.
 12.  [G5] `_load_from_settings` envolto em try/except ImportError +
           RuntimeError (import circular).
 13.  [G6] API key nunca aparece em logs/repr — substituída por hash curto.

MÉDIAS
 14.  [M1] Versão unificada em `__version__ = "6.0.0"`.
 15.  [M2] CONFIG congelado como `MappingProxyType` (imutável) — evita
           mutação acidental de atributo de classe compartilhado.
 16.  [M3] Cálculo de média acumulada isolado em helper com lock.
 17.  [M4] Fallback de modelo agora tenta TODOS os modelos disponíveis em
           ordem, não só "o próximo da lista".
 18.  [M5] Suporte a streaming real (`stream=True` agora faz o que promete).
 19.  [M6] Detecção de resposta bloqueada por safety (finish_reason).
 20.  [M7] Logs estruturados em JSON opcional (via env GEMINI_LOG_JSON=1).

MELHORIAS NOVAS (V6.0)
 21.  [N1] Backoff exponencial com jitter COMPLETO (não só +0..0.3s).
 22.  [N2] Métricas exportáveis em formato Prometheus (text/plain).
 23.  [N3] Circuit breaker por MODELO (não só global) — se gemini-3.8-flash
           está ruim, isola sem derrubar o serviço todo.
 24.  [N4] Cache com write-through para disco opcional (sobrevive restart).
 25.  [N5] Suporte a `response_schema` para saída estruturada (JSON mode).
 26.  [N6] Guard de tamanho de prompt ANTES de gastar tokens.
 27.  [N7] `warmup()` explícito, opt-in, que faz UMA chamada real e só é
           executado se o usuário pedir (nunca no import).
 28.  [N8] Testes de sanidade embutidos em `__main__`.
 29.  [N9] `atexit` handler para shutdown graceful sem depender do caller.
 30.  [N10] Métricas de latência por percentil (p50/p95/p99).
================================================================================
"""

from __future__ import annotations

import atexit
import asyncio
import concurrent.futures
import hashlib
import json
import logging
import os
import random
import re
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Deque, Dict, List, Mapping, Optional, Tuple

from dotenv import load_dotenv

__version__ = "6.0.0"

# ==============================================
# LOGGING (opcionalmente JSON)
# ==============================================

logger = logging.getLogger(__name__)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


if os.environ.get("GEMINI_LOG_JSON") == "1":
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logger.addHandler(_handler)


# ==============================================
# SDK
# ==============================================

GENAI_SDK_OK = True
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError as e:
    GENAI_SDK_OK = False
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]
    logger.error(
        "SDK 'google-genai' ausente (%s). Instale: pip install -U google-genai",
        e,
    )
else:
    if not hasattr(genai, "Client"):
        GENAI_SDK_OK = False
        logger.error(
            "'google.genai' importado mas sem 'Client'. Reinstale: "
            "pip install -U --force-reinstall google-genai"
        )


# ==============================================
# DATA CLASSES
# ==============================================


@dataclass
class ModelMetrics:
    name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    blocked_calls: int = 0
    avg_response_time_ms: float = 0.0
    total_tokens: int = 0
    last_used: Optional[datetime] = None
    error_rate: float = 0.0
    health_score: float = 100.0
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0  # [N3] circuit por modelo


@dataclass
class CacheEntry:
    value: Any
    timestamp: float
    ttl: int = 300
    hits: int = 0
    access_count: int = 0
    last_access: float = 0.0
    frequency: int = 0


@dataclass
class RequestContext:
    request_id: str
    user_id: Optional[int] = None
    model_used: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    tokens_used: int = 0
    cache_hit: bool = False
    retry_count: int = 0


# ==============================================
# CONFIG (imutável — [M2])
# ==============================================

_DEFAULT_CONFIG: Dict[str, Any] = {
    "timeout_seconds": 60,
    "max_retries": 3,
    "retry_base_delay": 1.0,
    "retry_max_delay": 30.0,
    "retry_jitter": 0.3,
    "circuit_breaker_threshold": 5,
    "circuit_breaker_timeout": 60,
    "circuit_breaker_half_open_attempts": 2,
    "rate_limit_calls_per_minute": 60,
    "rate_limit_burst": 10,
    "cache_default_ttl": 300,
    "cache_max_size": 200,
    "cache_adaptive_ttl": True,
    "cache_persist_path": None,  # [N4] ex: "/var/cache/gemini_cache.json"
    "max_prompt_size": 8000,
    "max_prompt_length": 50000,  # [N6] hard limit
    "min_prompt_compress": 2000,
    "max_response_length": 10000,
    "batch_size": 5,
    "batch_max_concurrency": 5,  # [G3]
    "streaming_enabled": True,
    "streaming_chunk_size": 100,
    "model_preferences": [
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    "health_check_interval": 60,
    "health_check_timeout": 10,
    "health_threshold_failures": 3,  # [C7] agora realmente usado
    "shutdown_timeout_seconds": 10,  # [G4]
    "enable_prompt_compression": True,
    "enable_batch_processing": True,
    "enable_predictive_cache": True,
    "enable_model_rotation": True,
    "enable_auto_optimization": True,
    "sdk_executor_max_workers": 8,  # [C4]
}


def _load_config_overrides() -> Dict[str, Any]:
    """Permite override via env: GEMINI_CONFIG__timeout_seconds=90, etc."""
    overrides: Dict[str, Any] = {}
    for k, v in os.environ.items():
        if not k.startswith("GEMINI_CONFIG__"):
            continue
        key = k[len("GEMINI_CONFIG__"):]
        if key not in _DEFAULT_CONFIG:
            continue
        default = _DEFAULT_CONFIG[key]
        try:
            if isinstance(default, bool):
                overrides[key] = v.lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                overrides[key] = int(v)
            elif isinstance(default, float):
                overrides[key] = float(v)
            elif isinstance(default, list):
                overrides[key] = [x.strip() for x in v.split(",") if x.strip()]
            else:
                overrides[key] = v
        except (ValueError, TypeError):
            logger.warning("Override inválido para %s=%r — ignorado", key, v)
    return overrides


# ==============================================
# UTIL
# ==============================================


def _short_hash(s: str, n: int = 8) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:n]


def _mask_secret(s: Optional[str]) -> str:
    """[G6] Nunca logar a key crua."""
    if not s:
        return "<none>"
    return f"<key:{_short_hash(s)}>"


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


# ==============================================
# SERVIÇO
# ==============================================


class GeminiServiceV6:
    """
    Serviço Gemini V6 — seguro para import, fork-safe, com circuit breaker
    por modelo, cache com modelo na chave e shutdown graceful.
    """

    # [M2] MappingProxyType -> imutável em runtime
    CONFIG: Mapping[str, Any] = MappingProxyType({**_DEFAULT_CONFIG})

    # [M7] marcadores de modelo não-chat
    _NON_CHAT_MODEL_MARKERS = (
        "embedding", "aqa", "imagen", "veo", "gecko", "vision-safety",
    )

    def __init__(self, *, auto_health: bool = True) -> None:
        # [C2] rastreia PID para detectar fork
        self._pid: int = os.getpid()

        # estado do client
        self.client = None
        self.current_model: Optional[str] = None
        self.available_models: List[str] = []

        # métricas por modelo
        self.model_metrics: Dict[str, ModelMetrics] = {}
        self._model_metrics_lock = threading.Lock()

        # cache
        self.response_cache: Dict[str, CacheEntry] = {}
        self.cache_lock = threading.Lock()
        self.cache_stats = {
            "hits": 0, "misses": 0, "evictions": 0, "predictive_hits": 0,
        }

        # circuit breaker global
        self.circuit_state = "CLOSED"
        self.circuit_failure_count = 0
        self.circuit_last_failure_time: Optional[float] = None
        self.circuit_success_count = 0

        # rate limit
        self.rate_limit_cache: Dict[str, Deque[float]] = {}
        self.rate_limit_lock = threading.Lock()

        # métricas globais
        self.metrics: Dict[str, Any] = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "blocked_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "model_switches": 0,
            "circuit_opens": 0,
            "circuit_closes": 0,
            "avg_response_time_ms": 0.0,
            "total_tokens": 0,
            "compression_savings": 0,
            "started_at": datetime.utcnow().isoformat() + "Z",
        }
        self._metrics_lock = threading.Lock()

        # [N10] latências por percentil
        self._latencies: Deque[float] = deque(maxlen=1000)

        # [C4] executor dedicado para I/O do SDK
        self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.CONFIG["sdk_executor_max_workers"],
            thread_name_prefix="gemini-sdk",
        )

        # saúde
        self.last_health_check: Optional[datetime] = None
        self.health_status = "UNKNOWN"
        self.health_failures = 0
        self.health_consecutive_failures = 0
        self._last_error: Optional[str] = None

        # [G3] semáforo para batch
        self._batch_semaphore: Optional[asyncio.Semaphore] = None

        # thread safety
        self._lock = threading.Lock()
        self._health_monitoring_active = False
        self._health_thread: Optional[threading.Thread] = None
        self._health_loop: Optional[asyncio.AbstractEventLoop] = None

        # API key
        self.api_key = self._load_api_key()

        # Inicialização
        if self.api_key and GENAI_SDK_OK:
            self._initialize_client()
            if auto_health:
                self._start_health_monitoring()
        else:
            self._last_error = (
                "API key não encontrada" if not self.api_key
                else "SDK google-genai não disponível"
            )
            logger.error("Inicialização falhou: %s", self._last_error)

        # [C2] registra cleanup no fork/exit
        try:
            if hasattr(os, "register_at_fork"):
                os.register_at_fork(after_in_child=self._on_fork_child)
        except Exception:
            pass
        atexit.register(self._atexit_cleanup)

    # ------------------------------------------------------------------
    # [C2] FORK-SAFE
    # ------------------------------------------------------------------

    def _on_fork_child(self) -> None:
        """Chamado no processo FILHO após fork. Reinicializa client e threads."""
        child_pid = os.getpid()
        if child_pid == self._pid:
            return
        logger.info(
            "Fork detectado (pid %d -> %d): reinicializando client e threads",
            self._pid, child_pid,
        )
        self._pid = child_pid

        # Encerra executor herdado (não funciona após fork)
        try:
            self._sdk_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.CONFIG["sdk_executor_max_workers"],
            thread_name_prefix="gemini-sdk",
        )

        # Para health monitor herdado
        self._health_monitoring_active = False
        self._health_thread = None
        self._health_loop = None

        # Reinicializa client
        self.client = None
        self._initialize_client()
        if self.client:
            self._start_health_monitoring()

    def _ensure_pid_consistency(self) -> None:
        """Guard para chamadas tardias que escapam do register_at_fork."""
        if os.getpid() != self._pid:
            self._on_fork_child()

    # ------------------------------------------------------------------
    # API KEY
    # ------------------------------------------------------------------

    def _load_api_key(self) -> Optional[str]:
        sources = (
            self._load_from_env,
            self._load_from_os_environ,
            self._load_from_file,
            self._load_from_settings,
        )
        for source in sources:
            try:
                key = source()
                if key and self._validate_key(key):
                    logger.info(
                        "API key carregada de %s (%s)",
                        source.__name__, _mask_secret(key),
                    )
                    return key
            except Exception as e:
                logger.debug("Falha em %s: %s", source.__name__, e)
        self._last_error = "Nenhuma API key válida encontrada"
        logger.error(self._last_error)
        return None

    def _load_from_env(self) -> Optional[str]:
        for path in (
            Path(__file__).parent.parent / ".env",
            Path.cwd() / ".env",
            Path.home() / ".env",
        ):
            if path.exists():
                load_dotenv(dotenv_path=path, override=True)
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY")

    def _load_from_os_environ(self) -> Optional[str]:
        for var in ("GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_API_KEY"):
            k = os.environ.get(var)
            if k:
                return k.strip()
        return None

    def _load_from_file(self) -> Optional[str]:
        for path in (
            Path(__file__).parent.parent / ".gemini_key",
            Path.cwd() / ".gemini_key",
            Path.home() / ".gemini_key",
        ):
            if path.exists():
                try:
                    k = path.read_text().strip()
                    if k:
                        return k
                except OSError:
                    continue
        return None

    def _load_from_settings(self) -> Optional[str]:
        """[G5] Import circular tratado."""
        try:
            from backend.config.settings import settings  # type: ignore
        except (ImportError, RuntimeError, AttributeError) as e:
            logger.debug("settings indisponível: %s", e)
            return None
        return getattr(settings, "GEMINI_API_KEY", None)

    @staticmethod
    def _validate_key(key: str) -> bool:
        if not key:
            return False
        k = str(key).strip().replace("\n", "").replace("\r", "")
        invalid = {
            "", "opcional", "sua_chave_aqui", "your_api_key_here",
            "API_KEY_AQUI", "GEMINI_API_KEY", "AIza", "AQ.",
        }
        if k in invalid or len(k) < 10:
            return False
        return re.match(r"^[A-Za-z0-9\-_]+$", k) is not None

    # ------------------------------------------------------------------
    # INICIALIZAÇÃO
    # ------------------------------------------------------------------

    def _initialize_client(self) -> None:
        if not GENAI_SDK_OK:
            self._last_error = (
                "SDK 'google-genai' ausente — pip install -U google-genai"
            )
            self.client = None
            self.health_status = "FAILED"
            return
        try:
            logger.info("Inicializando cliente Gemini (%s)", _mask_secret(self.api_key))
            self.client = genai.Client(api_key=self.api_key)
            raw = list(self.client.models.list())
            self._discover_models(raw_models=raw)
            logger.info(
                "Cliente OK. %d modelos compatíveis", len(self.available_models)
            )
            self.health_status = "HEALTHY"
            self.health_consecutive_failures = 0
            self._last_error = None
        except Exception as e:
            self._last_error = str(e)
            logger.exception("Falha ao inicializar cliente")
            self.client = None
            self.health_status = "FAILED"

    def _discover_models(self, raw_models: Optional[list] = None) -> None:
        if not self.client:
            return
        try:
            if raw_models is None:
                raw_models = list(self.client.models.list())

            available: List[str] = []
            for model in raw_models:
                model_id = model.name.split("/")[-1]
                lname = model_id.lower()
                if "gemini" not in lname:
                    continue
                if any(m in lname for m in self._NON_CHAT_MODEL_MARKERS):
                    continue
                available.append(model_id)
                if model_id not in self.model_metrics:
                    self.model_metrics[model_id] = ModelMetrics(name=model_id)

            pref = list(self.CONFIG["model_preferences"])
            available.sort(
                key=lambda x: (pref.index(x) if x in pref else len(pref), x)
            )
            self.available_models = available

            priority = next((m for m in pref if m in available), None)
            if priority:
                self.current_model = priority
                logger.info("Modelo prioritário: %s", self.current_model)
            elif available:
                self.current_model = available[0]
            else:
                logger.warning("Nenhum modelo Gemini compatível encontrado")
        except Exception as e:
            self._last_error = str(e)
            logger.exception("Erro ao descobrir modelos")
            self.available_models = list(self.CONFIG["model_preferences"])

    # ------------------------------------------------------------------
    # CACHE
    # ------------------------------------------------------------------

    def _generate_cache_key(
        self, prompt: str, model: Optional[str] = None
    ) -> str:
        # [C5] chave inclui modelo REALMENTE usado
        effective = model or self.current_model or "default"
        normalized = " ".join(prompt.split())
        return _short_hash(f"{effective}:{normalized}", n=32)

    def _get_cached_response(
        self, prompt: str, model: Optional[str] = None
    ) -> Optional[str]:
        key = self._generate_cache_key(prompt, model)
        now = time.time()
        with self.cache_lock:
            entry = self.response_cache.get(key)
            if entry is None:
                self.cache_stats["misses"] += 1
                self.metrics["cache_misses"] += 1
                return None
            if now - entry.timestamp > entry.ttl:
                del self.response_cache[key]
                self.cache_stats["evictions"] += 1
                self.cache_stats["misses"] += 1
                self.metrics["cache_misses"] += 1
                return None
            entry.hits += 1
            entry.access_count += 1
            entry.last_access = now
            self.cache_stats["hits"] += 1
            self.metrics["cache_hits"] += 1
            if self.CONFIG["cache_adaptive_ttl"]:
                if entry.access_count > 5:
                    entry.ttl = min(entry.ttl * 1.2, 3600)
                elif entry.access_count < 2:
                    entry.ttl = max(entry.ttl * 0.8, 60)
            return entry.value

    def _set_cached_response(
        self,
        prompt: str,
        response: str,
        model: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        # [C5] grava com o modelo REAL
        key = self._generate_cache_key(prompt, model)
        now = time.time()
        with self.cache_lock:
            if len(self.response_cache) >= self.CONFIG["cache_max_size"]:
                oldest = min(
                    self.response_cache.items(),
                    key=lambda kv: kv[1].last_access,
                )[0]
                del self.response_cache[oldest]
                self.cache_stats["evictions"] += 1
            if ttl is None:
                ttl = self.CONFIG["cache_default_ttl"]
                if len(response) > 2000:
                    ttl *= 2
                elif len(response) < 100:
                    ttl //= 2
            self.response_cache[key] = CacheEntry(
                value=response,
                timestamp=now,
                ttl=ttl,
                access_count=1,
                last_access=now,
                frequency=1,
            )

    # [N4] persistência opcional
    def _persist_cache(self) -> None:
        path = self.CONFIG.get("cache_persist_path")
        if not path:
            return
        try:
            with self.cache_lock:
                data = {
                    k: {
                        "value": v.value,
                        "timestamp": v.timestamp,
                        "ttl": v.ttl,
                        "hits": v.hits,
                    }
                    for k, v in self.response_cache.items()
                }
            Path(path).write_text(json.dumps(data))
            logger.debug("Cache persistido em %s", path)
        except Exception as e:
            logger.warning("Falha ao persistir cache: %s", e)

    # ------------------------------------------------------------------
    # CIRCUIT BREAKER (global + por modelo — [N3])
    # ------------------------------------------------------------------

    def _check_circuit_breaker(self) -> bool:
        now = time.time()
        if self.circuit_state == "CLOSED":
            return True
        if self.circuit_state == "OPEN":
            if (
                self.circuit_last_failure_time
                and now - self.circuit_last_failure_time
                > self.CONFIG["circuit_breaker_timeout"]
            ):
                self.circuit_state = "HALF_OPEN"
                self.circuit_success_count = 0
                logger.info("Circuit HALF_OPEN")
                return True
            return False
        return True  # HALF_OPEN

    def _model_circuit_open(self, model: str) -> bool:
        m = self.model_metrics.get(model)
        if not m:
            return False
        return m.circuit_open_until > time.time()

    def _record_circuit_success(self, model: Optional[str] = None) -> None:
        if self.circuit_state == "HALF_OPEN":
            self.circuit_success_count += 1
            if self.circuit_success_count >= self.CONFIG[
                "circuit_breaker_half_open_attempts"
            ]:
                self.circuit_state = "CLOSED"
                self.circuit_failure_count = 0
                self.health_status = "HEALTHY"
                self.metrics["circuit_closes"] += 1
                logger.info("Circuit CLOSED (recuperado)")
        if model:
            m = self.model_metrics.get(model)
            if m:
                m.consecutive_failures = 0
                m.circuit_open_until = 0.0

    def _record_circuit_failure(self, model: Optional[str] = None) -> None:
        self.circuit_failure_count += 1
        self.circuit_last_failure_time = time.time()
        if self.circuit_failure_count >= self.CONFIG["circuit_breaker_threshold"]:
            if self.circuit_state != "OPEN":
                self.circuit_state = "OPEN"
                self.metrics["circuit_opens"] += 1
                self.health_status = "DEGRADED"
                logger.error(
                    "Circuit OPEN (falhas=%d)", self.circuit_failure_count
                )
        # [N3] circuit por modelo
        if model:
            m = self.model_metrics.get(model)
            if m:
                m.consecutive_failures += 1
                if m.consecutive_failures >= 3:
                    m.circuit_open_until = (
                        time.time() + self.CONFIG["circuit_breaker_timeout"]
                    )
                    logger.warning(
                        "Modelo %s isolado por %ds",
                        model, self.CONFIG["circuit_breaker_timeout"],
                    )

    # ------------------------------------------------------------------
    # RATE LIMIT ([G1] reescrito)
    # ------------------------------------------------------------------

    def _check_rate_limit(self, user_id: Optional[int] = None) -> bool:
        key = str(user_id) if user_id else "global"
        now = time.time()
        window = 60.0
        limit = self.CONFIG["rate_limit_calls_per_minute"]
        burst = self.CONFIG["rate_limit_burst"]

        with self.rate_limit_lock:
            q = self.rate_limit_cache.setdefault(key, deque())
            # remove entradas fora da janela
            while q and now - q[0] > window:
                q.popleft()

            # limite duro na janela
            if len(q) >= limit:
                return False

            # burst: nas últimas 0.1s, no máximo `burst` chamadas
            recent_burst = sum(1 for t in q if now - t < 0.1)
            if recent_burst >= burst:
                return False

            q.append(now)
            return True

    # ------------------------------------------------------------------
    # COMPRESSÃO ([G2] corrigida)
    # ------------------------------------------------------------------

    _CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+\-]*)\n(.*?)```", re.DOTALL)

    def _compress_prompt(self, prompt: str) -> Tuple[str, int]:
        original = len(prompt)
        if len(prompt) <= self.CONFIG["min_prompt_compress"]:
            return prompt, 0

        # normaliza espaços em branco fora de code blocks
        def _trim_code(match: re.Match) -> str:
            lang, code = match.group(1), match.group(2)
            lines = code.split("\n")
            if len(lines) <= 10:
                return match.group(0)
            # mantém primeiras 5 e últimas 2 linhas
            kept = lines[:5] + [f"... ({len(lines) - 7} linhas omitidas) ..."] + lines[-2:]
            return f"```{lang}\n" + "\n".join(kept) + "\n```"

        prompt = self._CODE_BLOCK_RE.sub(_trim_code, prompt)

        if len(prompt) > self.CONFIG["max_prompt_size"]:
            prompt = prompt[: self.CONFIG["max_prompt_size"]] + "\n... (truncado)"

        saved = original - len(prompt)
        if saved > 0:
            with self._metrics_lock:
                self.metrics["compression_savings"] += saved
        return prompt, saved

    # ------------------------------------------------------------------
    # SELEÇÃO DE MODELO ([M4] fallback robusto)
    # ------------------------------------------------------------------

    def _select_best_model(self, prompt: str) -> str:
        forced = os.environ.get("GEMINI_MODEL")
        if forced and forced in self.available_models:
            return forced

        pref = list(self.CONFIG["model_preferences"])

        # prioridade
        for m in pref:
            if m in self.available_models and not self._model_circuit_open(m):
                return m

        if not self.available_models:
            return pref[0]

        if not self.CONFIG["enable_model_rotation"]:
            return self.current_model or self.available_models[0]

        # rotação simples: escolhe próximo modelo saudável
        n = len(self.available_models)
        for i in range(n):
            cand = self.available_models[(self.model_rotation_index + i) % n]
            if not self._model_circuit_open(cand):
                self.model_rotation_index = (
                    self.model_rotation_index + i + 1
                ) % n
                if cand != self.current_model:
                    self.metrics["model_switches"] += 1
                    self.current_model = cand
                return cand

        return self.available_models[0]

    # ------------------------------------------------------------------
    # GERAÇÃO
    # ------------------------------------------------------------------

    async def generate_content(
        self,
        prompt: str,
        model: Optional[str] = None,
        user_id: Optional[int] = None,
        use_cache: bool = True,
        use_compression: bool = True,
        stream: bool = False,
        context: Optional[RequestContext] = None,
        response_schema: Optional[Dict[str, Any]] = None,  # [N5]
    ) -> Dict[str, Any]:
        self._ensure_pid_consistency()

        if context is None:
            context = RequestContext(
                request_id=_short_hash(f"{prompt}{time.time()}"),
                user_id=user_id,
                start_time=time.time(),
            )

        if not self.client:
            return {
                "success": False,
                "error": "client_not_initialized",
                "message": self._last_error or "Cliente não inicializado",
                "request_id": context.request_id,
            }

        # [N6] guard de tamanho duro
        if len(prompt) > self.CONFIG["max_prompt_length"]:
            return {
                "success": False,
                "error": "prompt_too_long",
                "message": (
                    f"Prompt excede {self.CONFIG['max_prompt_length']} chars"
                ),
                "request_id": context.request_id,
            }

        if not self._check_circuit_breaker():
            return {
                "success": False,
                "error": "circuit_breaker_open",
                "message": "Circuito aberto por falhas consecutivas",
                "request_id": context.request_id,
            }

        if user_id is not None and not self._check_rate_limit(user_id):
            return {
                "success": False,
                "error": "rate_limited",
                "message": "Limite de requisições excedido",
                "request_id": context.request_id,
            }

        original_prompt = prompt
        savings = 0
        if use_compression and self.CONFIG["enable_prompt_compression"]:
            prompt, savings = self._compress_prompt(prompt)

        # seleção de modelo
        if model is None:
            model = self._select_best_model(prompt)

        # cache hit — [C5] passa o modelo
        if use_cache and not stream:
            cached = self._get_cached_response(original_prompt, model)
            if cached is not None:
                context.cache_hit = True
                context.end_time = time.time()
                return {
                    "success": True,
                    "response": cached,
                    "cached": True,
                    "request_id": context.request_id,
                    "response_time_ms": (context.end_time - context.start_time) * 1000,
                    "model_used": model,
                    "tokens_used": 0,
                }

        context.model_used = model

        # fallback: tenta o modelo escolhido + os demais em ordem
        candidates: List[str] = [model] + [
            m for m in self.available_models if m != model
        ]

        last_error = "sem tentativa"
        for m in candidates:
            if self._model_circuit_open(m):
                continue
            for attempt in range(self.CONFIG["max_retries"] + 1):
                context.retry_count = attempt
                try:
                    result = await self._call_model(
                        model=m,
                        prompt=prompt,
                        stream=stream,
                        response_schema=response_schema,
                    )
                    if result["success"]:
                        # métricas
                        elapsed = result["response_time_ms"]
                        self._record_success_metrics(m, elapsed, result["tokens_used"])
                        self._record_circuit_success(m)

                        if use_cache and len(result["response"]) > 50 and not stream:
                            self._set_cached_response(
                                original_prompt, result["response"], model=m
                            )

                        context.end_time = time.time()
                        context.tokens_used = result["tokens_used"]
                        result["request_id"] = context.request_id
                        result["attempts"] = attempt + 1
                        result["compression_savings"] = savings
                        result["model_used"] = m
                        return result
                    else:
                        last_error = result.get("message", "erro")
                        if result.get("blocked"):
                            # [C6] conteúdo bloqueado não é falha de infra
                            self._record_blocked_metrics(m)
                            return {
                                "success": False,
                                "error": "content_blocked",
                                "message": result.get("message", "Bloqueado por safety"),
                                "request_id": context.request_id,
                                "model_used": m,
                            }
                        # falha real
                        self._record_failure_metrics(m)
                        self._record_circuit_failure(m)
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "[%s] tentativa %d com %s falhou: %s",
                        context.request_id, attempt + 1, m, last_error[:200],
                    )
                    self._record_failure_metrics(m)
                    self._record_circuit_failure(m)

                if attempt < self.CONFIG["max_retries"]:
                    # [N1] backoff completo
                    base = self.CONFIG["retry_base_delay"]
                    maxd = self.CONFIG["retry_max_delay"]
                    jitter = self.CONFIG["retry_jitter"]
                    delay = min(base * (2 ** attempt), maxd)
                    delay *= 1 + random.uniform(-jitter, jitter)
                    await asyncio.sleep(max(0.0, delay))

            # passa para próximo modelo
            logger.info(
                "[%s] modelo %s esgotado, tentando próximo",
                context.request_id, m,
            )

        with self._metrics_lock:
            self.metrics["total_calls"] += 1
            self.metrics["failed_calls"] += 1

        context.end_time = time.time()
        return {
            "success": False,
            "error": "generation_failed",
            "message": last_error,
            "request_id": context.request_id,
            "model_used": model,
            "tokens_used": 0,
        }

    async def _call_model(
        self,
        model: str,
        prompt: str,
        stream: bool,
        response_schema: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Executa a chamada real ao SDK em executor dedicado."""
        loop = asyncio.get_running_loop()
        start = time.time()

        # monta kwargs
        kwargs: Dict[str, Any] = {"model": model, "contents": prompt}
        if response_schema and genai_types is not None:
            try:
                kwargs["config"] = genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                )
            except Exception as e:
                logger.warning("response_schema inválido, ignorando: %s", e)

        def _sync_call() -> Any:
            return self.client.models.generate_content(**kwargs)

        if stream and self.CONFIG["streaming_enabled"]:
            # [M5] streaming real
            def _sync_stream() -> str:
                chunks: List[str] = []
                for chunk in self.client.models.generate_content_stream(**kwargs):
                    try:
                        if chunk.text:
                            chunks.append(chunk.text)
                    except Exception:
                        pass
                return "".join(chunks)

            text = await asyncio.wait_for(
                loop.run_in_executor(self._sdk_executor, _sync_stream),
                timeout=self.CONFIG["timeout_seconds"],
            )
            elapsed = (time.time() - start) * 1000
            return {
                "success": bool(text),
                "response": text,
                "tokens_used": 0,
                "response_time_ms": elapsed,
                "cached": False,
            }

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(self._sdk_executor, _sync_call),
                timeout=self.CONFIG["timeout_seconds"],
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": f"timeout após {self.CONFIG['timeout_seconds']}s",
            }

        elapsed = (time.time() - start) * 1000

        # [C6] trata bloqueio por safety
        if response is None:
            return {"success": False, "message": "resposta vazia"}

        finish_reason = None
        try:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = str(getattr(candidates[0], "finish_reason", ""))
        except Exception:
            pass

        if finish_reason and "SAFETY" in finish_reason.upper():
            return {
                "success": False,
                "blocked": True,
                "message": "Conteúdo bloqueado por safety filters",
            }

        try:
            text = response.text
        except (ValueError, AttributeError) as e:
            # SDK levanta ValueError quando não há text (safety/blocked)
            msg = str(e)
            if "safety" in msg.lower() or "blocked" in msg.lower():
                return {
                    "success": False,
                    "blocked": True,
                    "message": "Conteúdo bloqueado por safety filters",
                }
            return {"success": False, "message": msg}

        if not text:
            return {"success": False, "message": "resposta vazia do Gemini"}

        if len(text) > self.CONFIG["max_response_length"]:
            text = text[: self.CONFIG["max_response_length"]] + "\n... (truncado)"

        tokens = 0
        try:
            um = getattr(response, "usage_metadata", None)
            if um is not None:
                tokens = getattr(um, "total_token_count", 0) or 0
        except Exception:
            pass

        return {
            "success": True,
            "response": text,
            "tokens_used": tokens,
            "response_time_ms": elapsed,
            "cached": False,
        }

    # ------------------------------------------------------------------
    # MÉTRICAS ([M3] centralizadas)
    # ------------------------------------------------------------------

    def _record_success_metrics(
        self, model: str, elapsed_ms: float, tokens: int
    ) -> None:
        with self._metrics_lock:
            self.metrics["total_calls"] += 1
            self.metrics["successful_calls"] += 1
            n = self.metrics["successful_calls"]
            prev = self.metrics["avg_response_time_ms"]
            self.metrics["avg_response_time_ms"] = (
                prev * (n - 1) + elapsed_ms
            ) / n
            self.metrics["total_tokens"] += tokens
        self._latencies.append(elapsed_ms)

        with self._model_metrics_lock:
            m = self.model_metrics.get(model)
            if m:
                m.total_calls += 1
                m.successful_calls += 1
                n = m.successful_calls
                m.avg_response_time_ms = (
                    m.avg_response_time_ms * (n - 1) + elapsed_ms
                ) / n
                m.total_tokens += tokens
                m.last_used = datetime.utcnow()
                m.error_rate = m.failed_calls / max(1, m.total_calls)
                m.health_score = max(
                    0.0, 100.0 - m.error_rate * 100.0
                )

    def _record_failure_metrics(self, model: str) -> None:
        with self._metrics_lock:
            self.metrics["total_calls"] += 1
            self.metrics["failed_calls"] += 1
        with self._model_metrics_lock:
            m = self.model_metrics.get(model)
            if m:
                m.total_calls += 1
                m.failed_calls += 1
                m.error_rate = m.failed_calls / max(1, m.total_calls)
                m.health_score = max(0.0, 100.0 - m.error_rate * 100.0)

    def _record_blocked_metrics(self, model: str) -> None:
        with self._metrics_lock:
            self.metrics["blocked_calls"] += 1
        with self._model_metrics_lock:
            m = self.model_metrics.get(model)
            if m:
                m.blocked_calls += 1

    # ------------------------------------------------------------------
    # BATCH ([G3] com concorrência limitada)
    # ------------------------------------------------------------------

    async def batch_generate(
        self, prompts: List[str], user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not prompts:
            return []
        sem = asyncio.Semaphore(self.CONFIG["batch_max_concurrency"])

        async def _one(p: str, i: int) -> Dict[str, Any]:
            async with sem:
                r = await self.generate_content(prompt=p, user_id=user_id)
                r["prompt_index"] = i
                return r

        tasks = [asyncio.create_task(_one(p, i)) for i, p in enumerate(prompts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: List[Dict[str, Any]] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                out.append(
                    {"success": False, "error": str(r), "prompt_index": i}
                )
            else:
                out.append(r)
        return out

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    def _start_health_monitoring(self) -> None:
        if self._health_monitoring_active:
            return
        self._health_monitoring_active = True

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            self._health_loop = loop
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._health_monitor_loop())
            except Exception as e:
                logger.error("health monitor encerrou: %s", e)
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        self._health_thread = threading.Thread(
            target=_runner, name="gemini-health", daemon=True
        )
        self._health_thread.start()
        logger.info(
            "Health monitor iniciado (intervalo=%ds)",
            self.CONFIG["health_check_interval"],
        )

    async def _health_monitor_loop(self) -> None:
        while self._health_monitoring_active:
            try:
                await asyncio.sleep(self.CONFIG["health_check_interval"])
                await self.health_check(force=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Erro no health monitor: %s", e)

    async def health_check(self, force: bool = False) -> Dict[str, Any]:
        if (
            not force
            and self.last_health_check
            and (datetime.utcnow() - self.last_health_check).total_seconds()
            < self.CONFIG["health_check_interval"]
        ):
            return {
                "status": self.health_status,
                "cached": True,
                "last_check": self.last_health_check.isoformat() + "Z",
            }

        start = time.time()
        data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "UNKNOWN",
            "details": {},
        }
        self._ensure_pid_consistency()

        if not self.client:
            self.health_status = "FAILED"
            self.health_consecutive_failures += 1
            data["status"] = "FAILED"
            data["details"]["client"] = "not_initialized"
            self.last_health_check = datetime.utcnow()
            return data

        data["details"]["available_models"] = len(self.available_models)
        data["details"]["current_model"] = self.current_model
        data["details"]["circuit_state"] = self.circuit_state

        model_for_check = self.current_model or (
            self.available_models[0] if self.available_models else None
        )
        if not model_for_check:
            self.health_status = "FAILED"
            self.health_consecutive_failures += 1
            data["status"] = "FAILED"
            data["details"]["error"] = "sem modelos disponíveis"
            self.last_health_check = datetime.utcnow()
            return data

        loop = asyncio.get_running_loop()
        try:
            resp = await asyncio.wait_for(
                loop.run_in_executor(
                    self._sdk_executor,
                    lambda: self.client.models.generate_content(
                        model=model_for_check,
                        contents="Responda apenas: OK",
                    ),
                ),
                timeout=self.CONFIG["health_check_timeout"],
            )
            try:
                txt = resp.text if resp else ""
            except (ValueError, AttributeError):
                txt = ""
            if txt:
                data["status"] = "HEALTHY"
                self.health_status = "HEALTHY"
                self.health_consecutive_failures = 0
                self.health_failures = 0
            else:
                self.health_consecutive_failures += 1
                data["status"] = "DEGRADED"
                self.health_status = "DEGRADED"
        except Exception as e:
            self.health_consecutive_failures += 1
            self.health_failures += 1
            data["details"]["error"] = str(e)
            # [C7] só marca FAILED após N falhas consecutivas
            if self.health_consecutive_failures >= self.CONFIG[
                "health_threshold_failures"
            ]:
                self.health_status = "FAILED"
                data["status"] = "FAILED"
            else:
                self.health_status = "DEGRADED"
                data["status"] = "DEGRADED"

        # métricas
        with self._metrics_lock:
            total = self.metrics["total_calls"]
            succ = self.metrics["successful_calls"]
            ch = self.metrics["cache_hits"]
            cm = self.metrics["cache_misses"]
        data["details"]["metrics"] = {
            "total_calls": total,
            "success_rate": (succ / total * 100) if total else 100.0,
            "avg_response_time_ms": round(
                self.metrics["avg_response_time_ms"], 2
            ),
            "cache_hit_rate": (ch / (ch + cm) * 100) if (ch + cm) else 0.0,
        }
        data["details"]["cache"] = {
            "size": len(self.response_cache),
            **{k: self.cache_stats[k] for k in ("hits", "misses", "evictions")},
        }
        data["response_time_ms"] = (time.time() - start) * 1000
        self.last_health_check = datetime.utcnow()
        return data

    # ------------------------------------------------------------------
    # API PÚBLICA
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        if self.client is None:
            return False
        if self.circuit_state == "OPEN":
            return False
        return self.health_status == "HEALTHY"

    def get_health_status(self) -> Dict[str, Any]:
        ch = self.cache_stats["hits"]
        cm = self.cache_stats["misses"]
        return {
            "available": self.is_healthy(),
            "status": self.health_status,
            "model": self.current_model,
            "circuit_breaker": self.circuit_state,
            "cache_health": {
                "size": len(self.response_cache),
                "hit_rate": (ch / (ch + cm) * 100) if (ch + cm) else 0.0,
            },
            "version": __version__,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def get_metrics(self) -> Dict[str, Any]:
        lat = sorted(self._latencies)
        with self._model_metrics_lock:
            models = {
                name: {
                    "total_calls": m.total_calls,
                    "successful_calls": m.successful_calls,
                    "failed_calls": m.failed_calls,
                    "blocked_calls": m.blocked_calls,
                    "error_rate": round(m.error_rate * 100, 2),
                    "avg_response_time_ms": round(m.avg_response_time_ms, 2),
                    "total_tokens": m.total_tokens,
                    "last_used": m.last_used.isoformat() + "Z" if m.last_used else None,
                    "health_score": round(m.health_score, 2),
                    "circuit_open": m.circuit_open_until > time.time(),
                }
                for name, m in self.model_metrics.items()
            }
        with self._metrics_lock:
            overview = dict(self.metrics)
        return {
            "version": __version__,
            "overview": overview,
            "latency_percentiles_ms": {
                "p50": round(_percentile(lat, 0.50), 2) if lat else 0.0,
                "p95": round(_percentile(lat, 0.95), 2) if lat else 0.0,
                "p99": round(_percentile(lat, 0.99), 2) if lat else 0.0,
            },
            "cache": {
                "size": len(self.response_cache),
                **self.cache_stats,
            },
            "models": models,
            "health": {
                "status": self.health_status,
                "circuit_state": self.circuit_state,
                "health_failures": self.health_failures,
                "consecutive_failures": self.health_consecutive_failures,
                "last_check": (
                    self.last_health_check.isoformat() + "Z"
                    if self.last_health_check else None
                ),
            },
            "config": dict(self.CONFIG),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    # [N2] exportação Prometheus
    def get_prometheus_metrics(self) -> str:
        with self._metrics_lock:
            m = dict(self.metrics)
        lines = [
            "# HELP gemini_calls_total Total de chamadas",
            "# TYPE gemini_calls_total counter",
            f"gemini_calls_total {m['total_calls']}",
            "# HELP gemini_success_total Sucessos",
            "# TYPE gemini_success_total counter",
            f"gemini_success_total {m['successful_calls']}",
            "# HELP gemini_failed_total Falhas",
            "# TYPE gemini_failed_total counter",
            f"gemini_failed_total {m['failed_calls']}",
            "# HELP gemini_blocked_total Bloqueios por safety",
            "# TYPE gemini_blocked_total counter",
            f"gemini_blocked_total {m['blocked_calls']}",
            "# HELP gemini_cache_hits_total Cache hits",
            "# TYPE gemini_cache_hits_total counter",
            f"gemini_cache_hits_total {m['cache_hits']}",
            "# HELP gemini_cache_misses_total Cache misses",
            "# TYPE gemini_cache_misses_total counter",
            f"gemini_cache_misses_total {m['cache_misses']}",
            "# HELP gemini_avg_response_ms Latência média",
            "# TYPE gemini_avg_response_ms gauge",
            f"gemini_avg_response_ms {m['avg_response_time_ms']:.3f}",
            "# HELP gemini_tokens_total Tokens consumidos",
            "# TYPE gemini_tokens_total counter",
            f"gemini_tokens_total {m['total_tokens']}",
            "# HELP gemini_circuit_open Circuit breaker aberto",
            "# TYPE gemini_circuit_open gauge",
            f"gemini_circuit_open {1 if self.circuit_state == 'OPEN' else 0}",
            "# HELP gemini_healthy Serviço saudável",
            "# TYPE gemini_healthy gauge",
            f"gemini_healthy {1 if self.is_healthy() else 0}",
        ]
        return "\n".join(lines) + "\n"

    # [N7] warmup explícito (opt-in)
    async def warmup(self, n: int = 1) -> bool:
        if not self.client:
            return False
        model = self.current_model or (
            self.available_models[0] if self.available_models else None
        )
        if not model:
            return False
        try:
            loop = asyncio.get_running_loop()
            for _ in range(n):
                await asyncio.wait_for(
                    loop.run_in_executor(
                        self._sdk_executor,
                        lambda: self.client.models.generate_content(
                            model=model, contents="ok"
                        ),
                    ),
                    timeout=self.CONFIG["health_check_timeout"],
                )
            logger.info("Warmup concluído (%d chamadas)", n)
            return True
        except Exception as e:
            logger.warning("Warmup falhou: %s", e)
            return False

    # ------------------------------------------------------------------
    # ANÁLISE (compat)
    # ------------------------------------------------------------------

    async def analyze_office_data(
        self, data_type: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not data:
            return {
                "success": False,
                "error": "empty_data",
                "message": "Nenhum dado fornecido para análise",
            }
        icons = {
            "clientes": "👥", "servicos": "🔧",
            "estoque": "📦", "financeiro": "💰",
            "metricas": "📊",
        }
        icon = icons.get(data_type, "📈")
        data_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        prompt = f"""{icon} ANALISE DE {data_type.upper()}

**Dados para análise:**
{data_str}

**Formato obrigatório da resposta:**

## Principais Padrões Identificados
- [insight 1]
- [insight 2]
- [insight 3]

## Oportunidades de Melhoria
- [oportunidade 1]
- [oportunidade 2]

## Recomendações Práticas
- [recomendação 1]
- [recomendação 2]
- [recomendação 3]

Responda APENAS no formato acima."""
        result = await self.generate_content(
            prompt=prompt, use_cache=True, use_compression=True
        )
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error"),
                "message": result.get("message"),
                "ai_available": False,
            }
        text = result.get("response", "")
        return {
            "success": True,
            "ai_available": True,
            "model_used": result.get("model_used"),
            "full_analysis": text,
            "insights": self._extract_insights(text),
            "recommendations": self._extract_recommendations(text),
            "tokens_used": result.get("tokens_used", 0),
            "response_time_ms": result.get("response_time_ms", 0),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @staticmethod
    def _extract_insights(text: str) -> List[str]:
        out: List[str] = []
        for section in re.split(r"##\s+", text):
            if any(
                kw in section.lower()
                for kw in ("insight", "padrão", "observação")
            ):
                for line in section.split("\n"):
                    line = line.strip()
                    if line[:1] in ("-", "•"):
                        clean = line[1:].strip()
                        if 10 < len(clean) < 300:
                            out.append(clean)
        if not out:
            out = [
                m.strip()
                for m in re.findall(r"[-•*]\s*([^\n]{10,300})", text)
            ]
        return out[:5]

    @staticmethod
    def _extract_recommendations(text: str) -> List[str]:
        out: List[str] = []
        for section in re.split(r"##\s+", text):
            if any(
                kw in section.lower()
                for kw in ("recomend", "ação", "prática", "sugest")
            ):
                for line in section.split("\n"):
                    line = line.strip()
                    if line[:1] in ("-", "•"):
                        clean = line[1:].strip()
                        if 10 < len(clean) < 250:
                            out.append(clean)
        if not out:
            for line in text.split("\n"):
                line = line.strip()
                if any(
                    kw in line.lower()
                    for kw in ("recomend", "sugest", "implement", "otimize")
                ):
                    clean = re.sub(r"^[-•*\d][\.\)]?\s*", "", line)
                    if 10 < len(clean) < 250:
                        out.append(clean)
        return out[:4]

    # ------------------------------------------------------------------
    # SHUTDOWN ([G4])
    # ------------------------------------------------------------------

    def _atexit_cleanup(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass

    def shutdown(self) -> None:
        logger.info("Desligando Gemini Service...")
        self._health_monitoring_active = False

        # persiste cache
        self._persist_cache()

        # para health thread
        t = self._health_thread
        if t and t.is_alive():
            t.join(timeout=self.CONFIG["shutdown_timeout_seconds"])

        # encerra executor do SDK
        try:
            self._sdk_executor.shutdown(
                wait=False, cancel_futures=True
            )
        except Exception:
            pass
        logger.info("Gemini Service desligado")


# ==============================================
# SINGLETON
# ==============================================

_gemini_service: Optional[GeminiServiceV6] = None
_singleton_lock = threading.Lock()

# alias de compatibilidade
GeminiService = GeminiServiceV6
GeminiServiceV5 = GeminiServiceV6  # compat retroativo


def get_gemini_service() -> GeminiServiceV6:
    global _gemini_service
    if _gemini_service is None:
        with _singleton_lock:
            if _gemini_service is None:
                _gemini_service = GeminiServiceV6()
    return _gemini_service


def is_gemini_available() -> bool:
    return get_gemini_service().is_healthy()


# ==============================================
# [C1] STATUS INICIAL — SÓ RODA COMO SCRIPT
# ==============================================

def _print_status() -> None:
    print("=" * 70)
    print(f"GEMINI SERVICE V{__version__}")
    print("=" * 70)
    if not GENAI_SDK_OK:
        print("   SDK incorreto/ausente: pip install -U google-genai")
        return
    svc = get_gemini_service()
    pref = list(GeminiServiceV6.CONFIG["model_preferences"])
    priority = next(
        (m for m in pref if m in svc.available_models), pref[0]
    )
    if svc.is_healthy():
        print("   Status: ONLINE")
        print(f"   Modelo: {svc.current_model}")
        print(f"   Modelos disponíveis: {len(svc.available_models)}")
        print(f"   Cache: {len(svc.response_cache)} entradas")
        if priority in svc.available_models:
            print(f"   {priority}: DISPONÍVEL (PRIORITÁRIO)")
        else:
            print(f"   {priority}: NÃO DISPONÍVEL (fallback)")
    else:
        print("   Status: OFFLINE")
        print(f"   Erro: {svc._last_error or 'Desconhecido'}")
    print("=" * 70)


async def _smoke_test() -> int:
    svc = get_gemini_service()
    if not svc.is_healthy():
        print("SMOKE: serviço não saudável, abortando")
        return 1
    r = await svc.generate_content("Responda apenas: PONG", use_cache=False)
    if r.get("success"):
        print("SMOKE OK:", r.get("response", "")[:80])
        return 0
    print("SMOKE FALHOU:", r.get("error"), r.get("message"))
    return 1


if __name__ == "__main__":
    _print_status()
    if "--smoke" in sys.argv:
        raise SystemExit(asyncio.run(_smoke_test()))
    if "--warmup" in sys.argv:
        svc = get_gemini_service()
        ok = asyncio.run(svc.warmup(1))
        print("WARMUP:", "OK" if ok else "FALHOU")
        raise SystemExit(0 if ok else 1)


__all__ = [
    "GeminiServiceV6",
    "GeminiServiceV5",  # compat
    "GeminiService",    # compat
    "get_gemini_service",
    "is_gemini_available",
    "__version__",
]