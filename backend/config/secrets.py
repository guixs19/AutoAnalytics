# backend/config/secrets.py - VERSÃO COMPLETA
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# ==============================================
# CONFIGURAÇÕES JWT
# ==============================================

# Chave secreta para JWT
# Em produção: use SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "autoanalytics-jwt-seguro-oficinas-2025")

# Algoritmo de encriptação
ALGORITHM = "HS256"

# Tempos de expiração dos tokens
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24))  # 24 horas
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))  # 7 dias - LINHA QUE FALTA!

# ==============================================
# CONFIGURAÇÕES DA API FLOWISE
# ==============================================

FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY", "")
FLOWISE_URL = os.getenv(
    "FLOWISE_URL", 
    "https://cloud.flowiseai.com/api/v1/prediction/07284d0d-4185-425a-b1e3-3ee3f187ab32"
)

# ==============================================
# CONFIGURAÇÕES DO BANCO DE DADOS
# ==============================================

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./autoanalytics.db")

# ==============================================
# MODO DEBUG
# ==============================================

DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# ==============================================
# VALIDAÇÃO
# ==============================================

if __name__ != "__main__":
    # Aviso se estiver usando chave padrão
    if SECRET_KEY == "your-secret-key-change-in-production":
        print("⚠️  AVISO: Altere SECRET_KEY no arquivo .env para produção!")