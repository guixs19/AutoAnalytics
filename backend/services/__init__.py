# backend/services/__init__.py - VERSÃO CORRIGIDA (sem import circular)

# ❌ REMOVA esta linha problemática:
# from backend.gemini import GeminiService

# ✅ Em vez disso, importe apenas quando necessário
from backend.services.daily_credits_service import DailyCreditsService
from backend.services.payment_service import MercadoPagoService

# Import opcional para o Gemini (com fallback)
try:
    from backend.gemini import GeminiService
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    GeminiService = None
    print("⚠️ GeminiService não disponível")

__all__ = [
    'DailyCreditsService',
    'MercadoPagoService',
    'GeminiService',
    'GEMINI_AVAILABLE'
]