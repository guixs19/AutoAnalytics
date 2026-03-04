# backend/config/settings.py - VERSÃO COMPLETA COM SEGURANÇA
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Diretório base
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Ajustado para raiz do projeto

class Settings:
    # ==============================================
    # APP CONFIGURAÇÕES BÁSICAS
    # ==============================================
    APP_NAME: str = "AutoAnalytics"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # ==============================================
    # DATABASE
    # ==============================================
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./autoanalytics.db")
    
    # ==============================================
    # FLOWISE / IA
    # ==============================================
    FLOWISE_API_KEY: str = os.getenv("FLOWISE_API_KEY", "")
    FLOWISE_URL: str = os.getenv(
        "FLOWISE_URL", 
        "https://cloud.flowiseai.com/api/v1/prediction/07284d0d-4185-425a-b1e3-3ee3f187ab32"
    )
    
    # ==============================================
    # PATHS
    # ==============================================
    TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "outputs")
    MODELS_DIR: str = os.path.join(BASE_DIR, "models")
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    
    # ==============================================
    # FILE UPLOAD
    # ==============================================
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: list = [".csv", ".xlsx", ".xls"]
    
    # ==============================================
    # 🔐 SEGURANÇA - JWT
    # ==============================================
    SECRET_KEY: str = os.getenv("SECRET_KEY", "mude-esta-chave-em-producao-urgente")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # ==============================================
    # 🔐 SEGURANÇA - ARGON2 (Hash de senha)
    # ==============================================
    ARGON2_TIME_COST: int = 3  # Iterações
    ARGON2_MEMORY_COST: int = 65536  # 64 MB
    ARGON2_PARALLELISM: int = 4  # Threads
    ARGON2_HASH_LEN: int = 32
    ARGON2_SALT_LEN: int = 16
    
    # ==============================================
    # 🔐 SEGURANÇA - CAPTCHA
    # ==============================================
    # Opções: 'recaptcha_v2', 'recaptcha_v3', 'hcaptcha', 'custom'
    CAPTCHA_TYPE: str = os.getenv("CAPTCHA_TYPE", "recaptcha_v2")
    
    # Google reCAPTCHA
    CAPTCHA_SITE_KEY: str = os.getenv("CAPTCHA_SITE_KEY", "")
    CAPTCHA_SECRET_KEY: str = os.getenv("CAPTCHA_SECRET_KEY", "")
    
    # ==============================================
    # 🔐 SEGURANÇA - RATE LIMITING (Redis)
    # ==============================================
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    
    # Limites de rate limiting
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 5  # Tentativas de login
    RATE_LIMIT_LOGIN_WINDOW: int = 900  # 15 minutos
    RATE_LIMIT_REGISTER_ATTEMPTS: int = 3  # Tentativas de registro
    RATE_LIMIT_REGISTER_WINDOW: int = 3600  # 1 hora
    RATE_LIMIT_API_ATTEMPTS: int = 60  # Requisições à API
    RATE_LIMIT_API_WINDOW: int = 60  # 1 minuto
    
    # ==============================================
    # 🔐 SEGURANÇA - CORS E HEADERS
    # ==============================================
    CORS_ORIGINS: list = [
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["*"]
    CORS_ALLOW_HEADERS: list = ["*"]
    
    # Headers de segurança
    SECURITY_HEADERS: dict = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self' https:; script-src 'self' 'unsafe-inline' https://www.google.com https://www.gstatic.com; style-src 'self' 'unsafe-inline';",
    }
    
    # ==============================================
    # SESSÃO E COOKIES
    # ==============================================
    SESSION_COOKIE_SECURE: bool = not DEBUG  # True em produção
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    
    def __init__(self):
        """Inicializa diretórios e validações"""
        self._create_directories()
        self._validate_security_settings()
    
    def _create_directories(self):
        """Cria todos os diretórios necessários"""
        directories = [
            self.TEMP_DIR,
            self.OUTPUT_DIR,
            self.MODELS_DIR,
            self.DATA_DIR
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            print(f"📁 Diretório verificado: {directory}")
    
    def _validate_security_settings(self):
        """Valida configurações de segurança"""
        if self.DEBUG:
            print("⚠️  MODO DEBUG ATIVO - NÃO USE EM PRODUÇÃO!")
        
        # Validar SECRET_KEY
        if self.SECRET_KEY == "mude-esta-chave-em-producao-urgente":
            print("⚠️  AVISO: Use uma SECRET_KEY forte em produção!")
        
        # Validar tamanho da SECRET_KEY
        if len(self.SECRET_KEY) < 32:
            print("⚠️  AVISO: SECRET_KEY muito curta (< 32 caracteres)")
        
        # Validar CAPTCHA
        if self.CAPTCHA_TYPE in ["recaptcha_v2", "recaptcha_v3", "hcaptcha"]:
            if not self.CAPTCHA_SITE_KEY or not self.CAPTCHA_SECRET_KEY:
                print(f"⚠️  AVISO: CAPTCHA configurado como {self.CAPTCHA_TYPE} mas chaves não fornecidas!")
        
        print("✅ Configurações de segurança validadas")
    
    # ==============================================
    # PROPRIEDADES ÚTEIS
    # ==============================================
    
    @property
    def is_production(self) -> bool:
        """Retorna True se estiver em produção"""
        return not self.DEBUG
    
    @property
    def redis_url(self) -> str:
        """Retorna URL do Redis para conexão"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    @property
    def captcha_config(self) -> dict:
        """Retorna configuração do CAPTCHA para o frontend"""
        return {
            "type": self.CAPTCHA_TYPE,
            "site_key": self.CAPTCHA_SITE_KEY,
            "version": "v3" if self.CAPTCHA_TYPE == "recaptcha_v3" else "v2"
        }

# Instância global
settings = Settings()

# Exportar para uso em outros módulos
__all__ = ['settings']