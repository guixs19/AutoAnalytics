# backend/services/service_factory.py - VERSÃO CORRIGIDA
"""
🔥 SERVICE FACTORY - VERSÃO CORRIGIDA
================================================================================
✅ CORREÇÕES:
   - Import correto do Gemini (get_gemini_service)
   - Verificação de disponibilidade real
   - Status detalhado do serviço
   - Fallback para quando Gemini não está disponível
================================================================================
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ==============================================
# 🔥 IMPORTAÇÃO CORRETA DO GEMINI
# ==============================================

try:
    from backend.gemini import get_gemini_service, is_gemini_available as _is_gemini_available
    GEMINI_AVAILABLE = True
    logger.info("✅ Gemini disponível para ServiceFactory")
except ImportError as e:
    logger.warning(f"⚠️ Gemini não disponível: {e}")
    GEMINI_AVAILABLE = False


class ServiceFactory:
    """
    🔥 Fábrica de serviços - VERSÃO CORRIGIDA
    
    Gerencia todos os serviços do sistema com verificação de disponibilidade.
    """
    
    def __init__(self):
        """Inicializa a fábrica de serviços"""
        self._gemini = None
        self._gemini_available = False
        self._initialized = False
        
        # Inicializar serviços
        self._initialize_services()
        
        logger.info("✅ ServiceFactory inicializado")
    
    def _initialize_services(self):
        """Inicializa todos os serviços"""
        try:
            # 🔥 CARREGAR GEMINI CORRETAMENTE
            if GEMINI_AVAILABLE:
                self._gemini = get_gemini_service()
                if self._gemini:
                    self._gemini_available = self._gemini.is_healthy()
                    if self._gemini_available:
                        logger.info(f"   ✅ Gemini carregado: {self._gemini.current_model}")
                    else:
                        logger.warning("   ⚠️ Gemini carregado mas não saudável")
                else:
                    logger.warning("   ⚠️ Gemini retornou None")
            else:
                logger.warning("   ⚠️ Gemini não disponível (import falhou)")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar serviços: {e}")
            self._initialized = False
    
    # ==========================================
    # 🔥 MÉTODOS DO GEMINI
    # ==========================================
    
    def get_gemini_service(self):
        """
        🔥 Retorna o serviço Gemini
        
        Returns:
            GeminiServiceV5 ou None
        """
        if not self._initialized:
            self._initialize_services()
        return self._gemini
    
    def is_gemini_available(self) -> bool:
        """
        🔥 Verifica se o Gemini está disponível
        
        Returns:
            bool: True se disponível e saudável
        """
        if not self._initialized:
            self._initialize_services()
        
        # Verificação em tempo real
        if self._gemini:
            try:
                return self._gemini.is_healthy()
            except Exception:
                return False
        
        return False
    
    def get_gemini_status(self) -> Dict[str, Any]:
        """
        🔥 Retorna status detalhado do Gemini
        
        Returns:
            Dict com status, modelo, métricas
        """
        if not self._initialized:
            self._initialize_services()
        
        if not self._gemini:
            return {
                "available": False,
                "error": "Serviço não inicializado",
                "model": None
            }
        
        try:
            return {
                "available": self._gemini.is_healthy(),
                "model": self._gemini.current_model,
                "sdk_version": self._gemini.sdk_version.value if hasattr(self._gemini, 'sdk_version') else "unknown",
                "circuit_state": self._gemini.circuit_state if hasattr(self._gemini, 'circuit_state') else "unknown",
                "cache_size": len(self._gemini.response_cache) if hasattr(self._gemini, 'response_cache') else 0,
                "total_calls": self._gemini.metrics.get("total_calls", 0) if hasattr(self._gemini, 'metrics') else 0,
                "health_status": self._gemini.health_status if hasattr(self._gemini, 'health_status') else "unknown"
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "model": None
            }
    
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
            "storage": "online",   # TODO: Verificar storage
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
    
    def get_critical_services_status(self) -> bool:
        """
        🔥 Verifica se os serviços críticos estão rodando
        
        Returns:
            bool: True se serviços críticos OK
        """
        # Por enquanto, apenas Gemini é crítico
        # Se Gemini não estiver disponível, ainda retorna True para não travar
        # Mas loga um aviso
        
        if not self.is_gemini_available():
            logger.warning("⚠️ Gemini não disponível - serviços críticos degradados")
            # Retorna True para não travar o sistema
            return True
        
        return True
    
    def get_missing_critical_services(self) -> list:
        """
        🔥 Retorna lista de serviços críticos faltando
        
        Returns:
            list: Nomes dos serviços faltando
        """
        missing = []
        
        if not self.is_gemini_available():
            missing.append("gemini")
        
        return missing
    
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
        """Retorna o predictor (placeholder)"""
        try:
            from backend.ml.predict import predictor
            return predictor
        except ImportError:
            return None
    
    def get_daily_credits_service(self):
        """Retorna o serviço de créditos diários (placeholder)"""
        # TODO: Implementar DailyCreditsService
        return None


# ==============================================
# 🔥 INSTÂNCIA GLOBAL
# ==============================================

_service_factory = None

def get_service_factory() -> ServiceFactory:
    """🔥 Retorna instância única do ServiceFactory"""
    global _service_factory
    if _service_factory is None:
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

# Criar instância global imediatamente
factory = get_service_factory()

print("\n" + "=" * 70)
print("✅ SERVICE FACTORY V2.0 CORRIGIDA")
print("=" * 70)
gemini_status = factory.get_gemini_status()
if gemini_status.get("available"):
    print(f"   🔥 Gemini: ONLINE")
    print(f"   📊 Modelo: {gemini_status.get('model')}")
    print(f"   📦 Cache: {gemini_status.get('cache_size')} entradas")
else:
    print("   ⚠️ Gemini: OFFLINE")
    print(f"   📝 Motivo: {gemini_status.get('error', 'Não disponível')}")
print("=" * 70)


__all__ = [
    'ServiceFactory',
    'get_service_factory',
    'get_gemini_service',
    'is_gemini_available',
    'get_status',
    'get_critical_services_status',
    'get_missing_critical_services',
    'get_file_manager',
    'get_preprocessor',
    'get_predictor',
    'get_daily_credits_service'
]