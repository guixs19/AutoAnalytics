# backend/services/service_factory.py - VERSÃO CORRIGIDA V3
"""
🔥 SERVICE FACTORY - VERSÃO CORRIGIDA V3
================================================================================
✅ CORREÇÕES NESTA VERSÃO:
   - Captura ampla de exceções na importação do Gemini (não só ImportError):
     o módulo gemini.py executa inicialização pesada no import (chamada real
     à API, discovery de modelos), então qualquer erro nesse momento agora
     é isolado em vez de derrubar o processo inteiro.
   - Retry automático com cooldown: se o Gemini falhar ao iniciar, o factory
     tenta novamente periodicamente em vez de ficar "travado" na primeira
     falha para sempre.
   - Thread-safety: lock ao redor da inicialização/reinicialização do
     ServiceFactory e do singleton global.
   - Uso real do fallback `is_gemini_available` importado do módulo gemini
     (antes era importado e nunca usado).
   - `sdk_version` e demais campos agora refletem `None` quando o atributo
     não existe (evita o placeholder ambíguo "unknown" sendo confundido com
     um valor real).
   - `get_critical_services_status` / `get_missing_critical_services` não
     duplicam mais a checagem de saúde do Gemini.
   - Datetime importado normalmente (sem `__import__` inline).
================================================================================
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ==============================================
# 🔥 IMPORTAÇÃO DO GEMINI (TOLERANTE A QUALQUER FALHA)
# ==============================================
#
# Importante: gemini.py cria seu singleton e faz chamadas reais à API já no
# nível de módulo (no import). Por isso capturamos Exception de forma ampla
# aqui, não apenas ImportError — um erro de rede, de credencial ou qualquer
# bug transitório durante essa inicialização não pode derrubar o processo
# inteiro que está importando o ServiceFactory.

GEMINI_AVAILABLE = False
get_gemini_service = None          # type: ignore[assignment]
_module_is_gemini_available = None  # fallback funcional vindo do módulo gemini

try:
    from backend.gemini import (
        get_gemini_service,
        is_gemini_available as _module_is_gemini_available,
    )
    GEMINI_AVAILABLE = True
    logger.info("✅ Gemini disponível para ServiceFactory")
except Exception as e:  # noqa: BLE001 - intencionalmente amplo, ver comentário acima
    logger.warning(f"⚠️ Gemini não disponível ao importar backend.gemini: {e}")
    GEMINI_AVAILABLE = False


class ServiceFactory:
    """
    🔥 Fábrica de serviços - VERSÃO CORRIGIDA V3

    Gerencia todos os serviços do sistema com verificação de disponibilidade
    real, retry automático com cooldown e acesso thread-safe.
    """

    # Tempo mínimo (segundos) entre tentativas de reinicializar o Gemini
    # depois de uma falha, para não martelar chamadas de API/objeto a cada
    # requisição enquanto o serviço está fora do ar.
    RETRY_COOLDOWN_SECONDS = 30

    def __init__(self):
        """Inicializa a fábrica de serviços"""
        self._gemini = None
        self._gemini_available = False
        self._initialized = False
        self._last_init_attempt: Optional[float] = None
        self._lock = threading.RLock()

        self._initialize_services()

        logger.info("✅ ServiceFactory inicializado")

    # ==========================================
    # 🔥 INICIALIZAÇÃO / RETRY
    # ==========================================

    def _ensure_gemini_fresh(self):
        """
        Garante que o Gemini foi inicializado e, se estiver indisponível,
        tenta de novo automaticamente após o cooldown — sem martelar
        tentativas a cada chamada.
        """
        now = time.monotonic()

        with self._lock:
            never_tried = not self._initialized
            cooldown_expired = (
                self._last_init_attempt is None
                or (now - self._last_init_attempt) >= self.RETRY_COOLDOWN_SECONDS
            )
            needs_retry = self._initialized and not self._gemini_available and cooldown_expired

            if never_tried or needs_retry:
                self._last_init_attempt = now
                self._initialize_services()

    def _initialize_services(self):
        """Executa uma tentativa de inicialização de todos os serviços"""
        with self._lock:
            try:
                if GEMINI_AVAILABLE and get_gemini_service is not None:
                    self._gemini = get_gemini_service()

                    if self._gemini:
                        self._gemini_available = bool(self._gemini.is_healthy())
                        if self._gemini_available:
                            logger.info(
                                f"   ✅ Gemini carregado: {self._gemini.current_model}"
                            )
                        else:
                            logger.warning("   ⚠️ Gemini carregado mas não saudável")
                    else:
                        # get_gemini_service() retornou None: usa o fallback
                        # funcional do próprio módulo gemini, se existir.
                        logger.warning("   ⚠️ Gemini retornou None")
                        self._gemini_available = bool(
                            _module_is_gemini_available()
                        ) if _module_is_gemini_available else False
                else:
                    logger.warning("   ⚠️ Gemini não disponível (import falhou)")
                    self._gemini = None
                    self._gemini_available = False

            except Exception as e:
                logger.error(f"❌ Erro ao inicializar serviços: {e}")
                self._gemini_available = False
            finally:
                # Sempre marcamos que uma tentativa foi feita — sucesso ou
                # falha — para que o retry seja governado pelo cooldown em
                # _ensure_gemini_fresh() e não por este flag.
                self._initialized = True

    # ==========================================
    # 🔥 MÉTODOS DO GEMINI
    # ==========================================

    def get_gemini_service(self):
        """
        🔥 Retorna o serviço Gemini

        Returns:
            GeminiServiceV5 ou None
        """
        self._ensure_gemini_fresh()
        return self._gemini

    def is_gemini_available(self) -> bool:
        """
        🔥 Verifica se o Gemini está disponível

        Returns:
            bool: True se disponível e saudável
        """
        self._ensure_gemini_fresh()

        if self._gemini:
            try:
                return bool(self._gemini.is_healthy())
            except Exception as e:
                logger.error(f"❌ Erro ao checar saúde do Gemini: {e}")
                return False

        # Última tentativa: usa o fallback funcional exportado por
        # backend.gemini diretamente, caso exista.
        if _module_is_gemini_available:
            try:
                return bool(_module_is_gemini_available())
            except Exception:
                return False

        return False

    def get_gemini_status(self) -> Dict[str, Any]:
        """
        🔥 Retorna status detalhado do Gemini

        Returns:
            Dict com status, modelo, métricas
        """
        self._ensure_gemini_fresh()

        if not self._gemini:
            return {
                "available": False,
                "error": "Serviço não inicializado",
                "model": None,
            }

        try:
            return {
                "available": self._gemini.is_healthy(),
                "model": getattr(self._gemini, "current_model", None),
                "sdk_version": getattr(self._gemini, "sdk_version", None),
                "circuit_state": getattr(self._gemini, "circuit_state", None),
                "cache_size": len(getattr(self._gemini, "response_cache", {}) or {}),
                "total_calls": getattr(self._gemini, "metrics", {}).get(
                    "total_calls", 0
                ),
                "health_status": getattr(self._gemini, "health_status", None),
                "last_health_check": self._format_datetime(
                    getattr(self._gemini, "last_health_check", None)
                ),
                "health_monitoring_active": getattr(
                    self._gemini, "_health_monitoring_active", None
                ),
            }
        except Exception as e:
            logger.error(f"❌ Erro ao montar status do Gemini: {e}")
            return {
                "available": False,
                "error": str(e),
                "model": None,
            }

    @staticmethod
    def _format_datetime(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        try:
            return value.isoformat()
        except AttributeError:
            return str(value)

    # ==========================================
    # 🔥 STATUS GERAIS
    # ==========================================

    def get_status(self) -> Dict[str, Any]:
        """
        🔥 Retorna status geral para o painel

        Returns:
            Dict com status de todos os serviços
        """
        gemini_status = self.get_gemini_status()

        return {
            "gemini": "online" if gemini_status.get("available") else "offline",
            "gemini_model": gemini_status.get("model"),
            "gemini_details": gemini_status,
            "database": "online",  # TODO: Verificar DB
            "storage": "online",  # TODO: Verificar storage
            "timestamp": datetime.now().isoformat(),
        }

    def get_missing_critical_services(self) -> List[str]:
        """
        🔥 Retorna lista de serviços críticos faltando

        Returns:
            list: Nomes dos serviços faltando
        """
        missing = []

        if not self.is_gemini_available():
            missing.append("gemini")

        return missing

    def get_critical_services_status(self) -> bool:
        """
        🔥 Verifica se os serviços críticos estão rodando

        Por ora o boot nunca é bloqueado por causa de um serviço crítico
        ausente (o sistema segue em modo degradado) — mas isso fica
        registrado em log para visibilidade operacional.

        Returns:
            bool: True (sempre) — ver docstring acima.
        """
        missing = self.get_missing_critical_services()

        if missing:
            logger.warning(
                f"⚠️ Serviços críticos indisponíveis: {missing} — "
                "sistema seguirá em modo degradado"
            )

        return True

    def is_available(self, service_name: str) -> bool:
        """
        🔥 Verifica se um serviço específico está disponível

        Args:
            service_name: Nome do serviço ('gemini', 'database', etc.)

        Returns:
            bool: True se disponível
        """
        if service_name == "gemini":
            return self.is_gemini_available()
        elif service_name == "database":
            return True  # TODO: Verificar DB
        elif service_name == "storage":
            return True  # TODO: Verificar storage

        return False

    # ==========================================
    # 🔥 PLACEHOLDERS PARA OUTROS SERVIÇOS
    # ==========================================

    def get_file_manager(self):
        """Retorna o gerenciador de arquivos (placeholder)"""
        # TODO: Implementar FileManager
        return None

    def get_preprocessor(self):
        """Retorna o preprocessador (placeholder)"""
        # TODO: Implementar Preprocessor
        return None

    def get_predictor(self):
        """Retorna o predictor, se o módulo de ML estiver disponível"""
        try:
            from backend.ml.predict import predictor

            return predictor
        except Exception as e:
            logger.warning(f"⚠️ Predictor não disponível: {e}")
            return None

    def get_daily_credits_service(self):
        """Retorna o serviço de créditos diários (placeholder)"""
        # TODO: Implementar DailyCreditsService
        return None


# ==============================================
# 🔥 INSTÂNCIA GLOBAL (THREAD-SAFE, DOUBLE-CHECKED LOCKING)
# ==============================================

_service_factory: Optional[ServiceFactory] = None
_service_factory_lock = threading.Lock()


def get_service_factory() -> ServiceFactory:
    """🔥 Retorna instância única do ServiceFactory (thread-safe)"""
    global _service_factory

    if _service_factory is None:
        with _service_factory_lock:
            if _service_factory is None:  # double-checked locking
                _service_factory = ServiceFactory()

    return _service_factory


# ==============================================
# 🔥 FUNÇÕES DE EXPORTAÇÃO (COMPATIBILIDADE)
# ==============================================

def get_gemini_service():
    """Retorna o serviço Gemini"""
    return get_service_factory().get_gemini_service()


def is_gemini_available():
    """Verifica se o Gemini está disponível"""
    return get_service_factory().is_gemini_available()


def get_status():
    """Retorna status geral"""
    return get_service_factory().get_status()


def get_critical_services_status():
    """Retorna status dos serviços críticos"""
    return get_service_factory().get_critical_services_status()


def get_missing_critical_services():
    """Retorna lista de serviços críticos faltando"""
    return get_service_factory().get_missing_critical_services()


def get_file_manager():
    return get_service_factory().get_file_manager()


def get_preprocessor():
    return get_service_factory().get_preprocessor()


def get_predictor():
    return get_service_factory().get_predictor()


def get_daily_credits_service():
    return get_service_factory().get_daily_credits_service()


# ==============================================
# 🔥 INICIALIZAÇÃO
# ==============================================

# Criar instância global imediatamente. Como GEMINI_AVAILABLE e a própria
# ServiceFactory já isolam qualquer falha do Gemini (ver comentários acima),
# esta linha não deve mais derrubar o processo mesmo se o Gemini estiver
# totalmente fora do ar.
factory = get_service_factory()

print("\n" + "=" * 70)
print("✅ SERVICE FACTORY V3.0 CORRIGIDA")
print("=" * 70)
gemini_status = factory.get_gemini_status()
if gemini_status.get("available"):
    print("   🔥 Gemini: ONLINE")
    print(f"   📊 Modelo: {gemini_status.get('model')}")
    print(f"   📦 Cache: {gemini_status.get('cache_size')} entradas")
else:
    print("   ⚠️ Gemini: OFFLINE")
    print(f"   📝 Motivo: {gemini_status.get('error', 'Não disponível')}")
    print(
        f"   🔁 Retry automático a cada {ServiceFactory.RETRY_COOLDOWN_SECONDS}s "
        "enquanto indisponível"
    )
print("=" * 70)


__all__ = [
    "ServiceFactory",
    "get_service_factory",
    "get_gemini_service",
    "is_gemini_available",
    "get_status",
    "get_critical_services_status",
    "get_missing_critical_services",
    "get_file_manager",
    "get_preprocessor",
    "get_predictor",
    "get_daily_credits_service",
]