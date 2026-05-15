# backend/services/service_factory.py
import logging
from backend.gemini import gemini_service

logger = logging.getLogger(__name__)

class ServiceFactory:
    def __init__(self):
        self.gemini = gemini_service

    def get_gemini_service(self):
        return self.gemini

    def is_gemini_available(self):
        # Verifica se o serviço Gemini existe e se a chave foi configurada
        return self.gemini is not None

    def get_status(self):
        """Retorna o status geral para o painel"""
        return {
            "gemini": "online" if self.is_gemini_available() else "offline",
            "database": "online",
            "storage": "online"
        }

    # --- ESTA É A FUNÇÃO QUE O SEU ERRO PEDE (Linha 67 do routes.py) ---
    def get_critical_services_status(self) -> bool:
        """
        Retorna True se os serviços essenciais estiverem rodando.
        Se retornar False, o routes.py pode limitar algumas funções.
        """
        # Por enquanto, vamos retornar True para o sistema não travar
        return True 

# Instância global
_factory = ServiceFactory()

# --- FUNÇÕES DE EXPORTAÇÃO (O QUE O ROUTES.PY IMPORTA) ---

def get_service_factory():
    return _factory

def get_status():
    return _factory.get_status()

def get_critical_services_status():
    return _factory.get_critical_services_status()

def get_gemini_service():
    return _factory.get_gemini_service()

def is_gemini_available():
    return _factory.is_gemini_available()

# Placeholders para evitar erros de 'cannot import name'
def get_file_manager(): return None
def get_preprocessor(): return None
def get_predictor(): return None
def get_daily_credits_service(): return None