# backend/security.py - VERSÃO DEFINITIVA E OTIMIZADA (SEM CIRCULAR)
"""
MÓDULO CENTRAL DE SEGURANÇA
Todo o sistema DEVE importar daqui: from backend.security import ...
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
import secrets
import hashlib
import hmac
import logging
import json

# Argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

# JWT
from jose import JWTError, jwt

# FastAPI
from fastapi import HTTPException, status, Request, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse

# Redis
import redis.asyncio as redis

# Configurações
from backend.config.settings import settings

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURAÇÕES GLOBAIS
# ==============================================

# Definir o esquema OAuth2
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="api/auth/login", 
    auto_error=False,
    scheme_name="JWT"
)

# ==============================================
# 1. ARGON2 - HASH DE SENHA (OTIMIZADO)
# ==============================================

class Argon2Hasher:
    """Hash de senha usando Argon2id - MAIS SEGURO QUE BCRYPT"""
    
    def __init__(self):
        self.ph = PasswordHasher(
            time_cost=settings.ARGON2_TIME_COST,
            memory_cost=settings.ARGON2_MEMORY_COST,
            parallelism=settings.ARGON2_PARALLELISM,
            hash_len=32,
            salt_len=16
        )
        logger.info(f"✅ Argon2 inicializado (time_cost={settings.ARGON2_TIME_COST})")
    
    def hash_password(self, password: str) -> str:
        """
        Gera hash Argon2 da senha
        Args:
            password: Senha em texto puro
        Returns:
            Hash Argon2 em formato string
        """
        if not password or len(password) < 6:
            raise ValueError("Senha deve ter no mínimo 6 caracteres")
        
        try:
            return self.ph.hash(password)
        except Exception as e:
            logger.error(f"Erro ao gerar hash: {e}")
            raise HTTPException(
                status_code=500,
                detail="Erro interno ao processar senha"
            )
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        Verifica se a senha corresponde ao hash
        Args:
            password: Senha em texto puro
            hashed: Hash Argon2 armazenado
        Returns:
            True se válida, False caso contrário
        """
        if not password or not hashed:
            return False
        
        try:
            return self.ph.verify(hashed, password)
        except VerifyMismatchError:
            return False
        except InvalidHashError:
            logger.warning("Hash inválido encontrado no banco")
            return False
        except VerificationError as e:
            logger.error(f"Erro de verificação Argon2: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado na verificação: {e}")
            return False
    
    def check_needs_rehash(self, hashed: str) -> bool:
        """
        Verifica se o hash precisa ser atualizado (para migração)
        Args:
            hashed: Hash atual
        Returns:
            True se precisa rehash
        """
        try:
            return self.ph.check_needs_rehash(hashed)
        except:
            return False

# ==============================================
# 2. JWT COMPLETO COM REFRESH TOKEN NO BANCO
# ==============================================

class JWTManager:
    """Gerenciador de JWT - Tokens de acesso e refresh com banco de dados"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        # Redis para blacklist
        self.redis_client = None
        self.memory_blacklist = set()
        self._init_redis()
    
    def _init_redis(self):
        """Inicializa conexão Redis"""
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2,
                retry_on_timeout=True
            )
            logger.info("✅ Redis configurado para blacklist JWT")
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível: {e}")
            self.redis_client = None
    
    def _generate_jti(self) -> str:
        """Gera ID único para o token"""
        return secrets.token_urlsafe(16)
    
    def _create_token_payload(self, data: Dict[str, Any], token_type: str, expires_delta: timedelta) -> Dict[str, Any]:
        """
        Cria payload padrão para tokens
        Args:
            data: Dados do usuário
            token_type: "access" ou "refresh"
            expires_delta: Tempo de expiração
        Returns:
            Payload do token
        """
        now = datetime.utcnow()
        
        payload = {
            "sub": data.get("sub") or data.get("email"),
            "email": data.get("email"),
            "name": data.get("name", ""),
            "role": data.get("role", "user"),
            "plan": data.get("plan", "basico"),
            "credits": data.get("credits", 0),
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
            "jti": self._generate_jti(),
            "iss": "autoanalytics",
            "aud": "autoanalytics-api"
        }
        
        # Remover campos None
        return {k: v for k, v in payload.items() if v is not None}
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Cria token de acesso (curta duração)"""
        expires = timedelta(minutes=self.access_expire_minutes)
        payload = self._create_token_payload(data, "access", expires)
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, data: Dict[str, Any]) -> tuple:
        """
        Cria token de refresh (longa duração)
        Returns:
            (token, jti)
        """
        expires = timedelta(days=self.refresh_expire_days)
        payload = self._create_token_payload(data, "refresh", expires)
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, payload["jti"]
    
    def create_token_pair(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Cria par de tokens (access + refresh)"""
        # Payload base
        payload = {
            "sub": user_data.get("sub") or user_data.get("email"),
            "email": user_data.get("email"),
            "name": user_data.get("name", ""),
            "role": user_data.get("role", "user"),
            "plan": user_data.get("plan", "basico"),
            "credits": user_data.get("credits", 0)
        }
        
        # Criar tokens
        access_token = self.create_access_token(payload)
        refresh_token, refresh_jti = self.create_refresh_token(payload)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "refresh_jti": refresh_jti,
            "token_type": "bearer",
            "expires_in": self.access_expire_minutes * 60,
            "refresh_expires_in": self.refresh_expire_days * 24 * 60 * 60
        }
    
    def decode_token(self, token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
        """
        Decodifica token sem verificar tipo
        Args:
            token: JWT token
            verify_exp: Se deve verificar expiração
        Returns:
            Payload ou None se inválido
        """
        try:
            options = {"verify_exp": verify_exp}
            return jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options=options,
                audience="autoanalytics-api",
                issuer="autoanalytics"
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.JWTClaimsError as e:
            logger.warning(f"Claims inválidos: {e}")
            return None
        except JWTError as e:
            logger.warning(f"Erro JWT: {e}")
            return None
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Verifica token e retorna payload se válido
        Args:
            token: JWT token
            token_type: Tipo esperado ("access" ou "refresh")
        Returns:
            Payload ou None
        """
        payload = self.decode_token(token)
        
        if not payload:
            return None
        
        # Verificar tipo
        if payload.get("type") != token_type:
            logger.warning(f"Tipo de token inválido: esperado {token_type}, recebido {payload.get('type')}")
            return None
        
        return payload
    
    async def verify_token_async(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """Versão assíncrona com verificação de blacklist"""
        payload = self.verify_token(token, token_type)
        
        if not payload:
            return None
        
        # Verificar blacklist
        jti = payload.get("jti")
        if jti and await self.is_token_blacklisted(jti):
            logger.warning(f"Token {jti} está na blacklist")
            return None
        
        return payload
    
    async def refresh_access_token(self, refresh_token: str, db) -> Optional[Dict[str, str]]:
        """
        Gera novo access token a partir de refresh token
        🔥 VERIFICA NO BANCO DE DADOS!
        """
        from backend import crud
        
        # Verificar se refresh token é válido (JWT)
        payload = await self.verify_token_async(refresh_token, "refresh")
        
        if not payload:
            logger.warning("Refresh token inválido ou expirado")
            return None
        
        email = payload.get("sub") or payload.get("email")
        if not email:
            logger.warning("Refresh token sem email")
            return None
        
        # Buscar usuário
        user = crud.get_user_by_email(db, email)
        
        if not user:
            logger.warning(f"Usuário {email} não encontrado")
            return None
        
        # Validar refresh token no banco
        if not user.validate_refresh_token(refresh_token):
            logger.warning(f"Refresh token não corresponde ao banco para {email}")
            return None
        
        # Extrair dados do usuário
        user_data = {
            "sub": user.email,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
            "credits": user.credits
        }
        
        # TOKEN ROTATION: Invalidar token antigo
        user.revoke_refresh_token()
        
        # Criar novos tokens
        new_tokens = self.create_token_pair(user_data)
        
        # SALVAR NOVO REFRESH TOKEN NO BANCO
        user.set_refresh_token(
            new_tokens["refresh_token"], 
            new_tokens["refresh_jti"],
            self.refresh_expire_days
        )
        
        db.commit()
        
        logger.info(f"✅ Tokens renovados para {email}")
        
        return {
            "access_token": new_tokens["access_token"],
            "refresh_token": new_tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": new_tokens["expires_in"]
        }
    
    async def logout(self, refresh_token: str, db) -> bool:
        """Faz logout invalidando o refresh token no banco"""
        from backend import crud
        
        payload = await self.verify_token_async(refresh_token, "refresh")
        if not payload:
            return False
        
        email = payload.get("sub") or payload.get("email")
        if not email:
            return False
        
        user = crud.get_user_by_email(db, email)
        
        if user and user.validate_refresh_token(refresh_token):
            # Revogar refresh token no banco
            user.revoke_refresh_token()
            
            # Adicionar JTI à blacklist
            jti = payload.get("jti")
            if jti:
                exp = payload.get("exp", 0)
                now = datetime.utcnow().timestamp()
                remaining = max(int(exp - now), 3600)
                await self.blacklist_token(jti, remaining)
            
            db.commit()
            logger.info(f"✅ Logout realizado para {email}")
            return True
        
        return False
    
    async def blacklist_token(self, jti: str, expire_in: int):
        """Adiciona token à blacklist"""
        if not jti:
            return
        
        if self.redis_client:
            try:
                await self.redis_client.setex(f"blacklist:{jti}", expire_in, "1")
                logger.info(f"🔴 Token {jti} adicionado à blacklist Redis")
            except Exception as e:
                logger.error(f"Erro ao adicionar à blacklist Redis: {e}")
                self.memory_blacklist.add(jti)
        else:
            self.memory_blacklist.add(jti)
            logger.info(f"🔴 Token {jti} adicionado à blacklist em memória")
    
    async def is_token_blacklisted(self, jti: str) -> bool:
        """Verifica se token está na blacklist"""
        if not jti:
            return False
        
        if self.redis_client:
            try:
                exists = await self.redis_client.exists(f"blacklist:{jti}") > 0
                if exists:
                    logger.info(f"🔴 Token {jti} encontrado na blacklist Redis")
                return exists
            except Exception as e:
                logger.error(f"Erro ao verificar blacklist Redis: {e}")
                return jti in self.memory_blacklist
        else:
            return jti in self.memory_blacklist
    
    def extract_token_from_header(self, auth_header: str) -> Optional[str]:
        """Extrai token do header Authorization"""
        if not auth_header:
            return None
        
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "").strip()
        
        if auth_header.startswith("JWT "):
            return auth_header.replace("JWT ", "").strip()
        
        return auth_header.strip()

# ==============================================
# 3. CAPTCHA MANAGER (OTIMIZADO)
# ==============================================

class CaptchaManager:
    """Gerenciador de CAPTCHA - Suporte a múltiplos tipos"""
    
    def __init__(self):
        self.captcha_type = settings.CAPTCHA_TYPE
        self.site_key = settings.CAPTCHA_SITE_KEY
        self.secret_key = settings.CAPTCHA_SECRET_KEY
        self._dev_mode = settings.DEBUG and not self.site_key
        self._cache = {}  # Cache para desenvolvimento
        
        if self._dev_mode:
            logger.warning("⚠️ CAPTCHA em modo desenvolvimento (sempre válido)")
        else:
            logger.info(f"✅ CAPTCHA configurado: {self.captcha_type}")
    
    async def verify_recaptcha(self, token: str, remote_ip: str = None) -> bool:
        """Verifica reCAPTCHA v2/v3"""
        import httpx
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    "https://www.google.com/recaptcha/api/siteverify",
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": remote_ip
                    }
                )
                
                result = response.json()
                
                if self.captcha_type == "recaptcha_v3":
                    score = result.get("score", 0)
                    action = result.get("action", "")
                    logger.info(f"reCAPTCHA v3 - Score: {score}, Action: {action}")
                    return result.get("success", False) and score >= 0.5
                
                logger.info(f"reCAPTCHA v2 - Sucesso: {result.get('success')}")
                return result.get("success", False)
                
            except httpx.TimeoutException:
                logger.error("Timeout ao verificar reCAPTCHA")
                return False
            except Exception as e:
                logger.error(f"Erro ao verificar reCAPTCHA: {e}")
                return False
    
    async def verify_hcaptcha(self, token: str, remote_ip: str = None) -> bool:
        """Verifica hCaptcha"""
        import httpx
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    "https://hcaptcha.com/siteverify",
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": remote_ip
                    }
                )
                
                result = response.json()
                logger.info(f"hCaptcha - Sucesso: {result.get('success')}")
                return result.get("success", False)
                
            except Exception as e:
                logger.error(f"Erro ao verificar hCaptcha: {e}")
                return False
    
    async def verify_token(self, token: str, remote_ip: str = None) -> bool:
        """Verifica CAPTCHA baseado no tipo configurado"""
        # Modo desenvolvimento
        if self._dev_mode:
            return True
        
        if not token:
            logger.warning("Token CAPTCHA não fornecido")
            return False
        
        # reCAPTCHA
        if self.captcha_type.startswith("recaptcha"):
            return await self.verify_recaptcha(token, remote_ip)
        
        # hCaptcha
        if self.captcha_type == "hcaptcha":
            return await self.verify_hcaptcha(token, remote_ip)
        
        logger.warning(f"Tipo de CAPTCHA não suportado: {self.captcha_type}")
        return False

# ==============================================
# 4. RATE LIMITER (OTIMIZADO)
# ==============================================

class RateLimiter:
    """Rate limiting - Previne abuso da API"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self._last_cleanup = datetime.now().timestamp()
        self._init_redis()
    
    def _init_redis(self):
        """Inicializa conexão Redis"""
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2
            )
            logger.info("✅ Redis configurado para rate limiting")
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível para rate limiting: {e}")
            self.redis_client = None
    
    async def check_rate_limit(self, key: str, max_requests: int, window: int) -> bool:
        """
        Verifica rate limit para uma chave
        Args:
            key: Chave única (ex: "login:email@teste.com")
            max_requests: Máximo de requisições permitidas
            window: Janela de tempo em segundos
        Returns:
            True se pode prosseguir, False se excedeu limite
        """
        now = datetime.now().timestamp()
        
        # Usar Redis se disponível
        if self.redis_client:
            try:
                # Pipeline para operação atômica
                pipe = self.redis_client.pipeline()
                await pipe.incr(f"rate:{key}")
                await pipe.expire(f"rate:{key}", window)
                result = await pipe.execute()
                
                current = result[0]
                remaining = max_requests - current
                
                if current <= max_requests:
                    logger.debug(f"Rate limit - {key}: {current}/{max_requests} (restam {remaining})")
                    return True
                else:
                    logger.warning(f"Rate limit excedido - {key}: {current}/{max_requests}")
                    return False
                
            except Exception as e:
                logger.error(f"Erro no Redis rate limit: {e}")
                # Fallback para memória
        
        # Fallback em memória
        # Limpar cache antigo a cada minuto
        if now - self._last_cleanup > 60:
            self._cleanup_memory_cache()
            self._last_cleanup = now
        
        # Criar ou atualizar entrada
        if key not in self.memory_cache:
            self.memory_cache[key] = []
        
        # Remover entradas antigas
        self.memory_cache[key] = [t for t in self.memory_cache[key] if t > now - window]
        
        # Verificar limite
        if len(self.memory_cache[key]) >= max_requests:
            logger.warning(f"Rate limit excedido (memória) - {key}: {len(self.memory_cache[key])}/{max_requests}")
            return False
        
        # Adicionar nova requisição
        self.memory_cache[key].append(now)
        return True
    
    def _cleanup_memory_cache(self):
        """Limpa cache em memória"""
        now = datetime.now().timestamp()
        to_delete = []
        
        for key, timestamps in self.memory_cache.items():
            # Remover entradas mais antigas que 1 hora
            self.memory_cache[key] = [t for t in timestamps if t > now - 3600]
            
            # Se ficou vazio, marcar para remoção
            if not self.memory_cache[key]:
                to_delete.append(key)
        
        for key in to_delete:
            del self.memory_cache[key]
        
        logger.debug(f"Cache de rate limit limpo: {len(to_delete)} entradas removidas")

# ==============================================
# 5. INSTÂNCIAS GLOBAIS (SINGLETONS)
# ==============================================

# Criar instâncias únicas
hasher = Argon2Hasher()
jwt_manager = JWTManager()
captcha_manager = CaptchaManager()
rate_limiter = RateLimiter()

# ==============================================
# 6. DEPENDÊNCIAS FASTAPI (COM SESSÃO CORRETA)
# ==============================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = None  # Não usar Depends aqui para evitar circular
):
    """
    Obtém usuário atual do token
    NOTA: Esta função deve ser chamada com db explicitamente ou via Depends
    """
    from sqlalchemy.orm import Session
    from backend.database import SessionLocal
    from backend import crud
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        logger.warning("Token não fornecido")
        raise credentials_exception
    
    # Verificar token (versão assíncrona)
    payload = await jwt_manager.verify_token_async(token)
    if not payload:
        logger.warning("Token inválido ou expirado")
        raise credentials_exception
    
    email = payload.get("sub") or payload.get("email")
    if not email:
        logger.warning("Token sem email")
        raise credentials_exception
    
    # Se db não foi fornecido, criar sessão
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        user = crud.get_user_by_email(db, email=email)
        if not user:
            logger.warning(f"Usuário {email} não encontrado")
            raise credentials_exception
        
        return user
    finally:
        if should_close:
            db.close()

async def get_current_active_user(
    current_user = Depends(get_current_user)
):
    """Verifica se usuário está ativo"""
    if not current_user.is_active:
        logger.warning(f"Usuário {current_user.email} está inativo")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return current_user

async def get_current_admin_user(
    current_user = Depends(get_current_active_user)
):
    """Verifica se é administrador"""
    # 🔥 CORRIGIDO: Comparação com strings em vez de enum
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    
    if role_value not in ["admin", "ADMIN"]:
        logger.warning(f"Usuário {current_user.email} tentou acesso admin")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de administrador."
        )
    return current_user

async def get_current_manager_user(
    current_user = Depends(get_current_active_user)
):
    """Verifica se é gestor ou admin"""
    # 🔥 CORRIGIDO: Comparação com strings em vez de enum
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    
    if role_value not in ["admin", "ADMIN", "manager", "MANAGER"]:
        logger.warning(f"Usuário {current_user.email} tentou acesso manager")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de gestor ou admin."
        )
    return current_user

async def check_captcha(request: Request) -> bool:
    """
    Dependência para verificar CAPTCHA
    Uso: captcha_valid: bool = Depends(check_captcha)
    """
    # Modo desenvolvimento
    if captcha_manager._dev_mode:
        return True
    
    # Pegar token do header
    captcha_token = request.headers.get("X-Captcha-Token")
    if not captcha_token:
        captcha_token = request.headers.get("Captcha-Token")
    
    if not captcha_token:
        logger.warning("CAPTCHA token não fornecido")
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA token é obrigatório"
        )
    
    # Verificar
    client_ip = request.client.host if request.client else None
    valid = await captcha_manager.verify_token(captcha_token, client_ip)
    
    if not valid:
        logger.warning("CAPTCHA inválido")
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA inválido"
        )
    
    return True

# ==============================================
# 7. FUNÇÕES DE UTILIDADE
# ==============================================

def generate_api_key() -> str:
    """Gera chave de API aleatória"""
    return f"sk_{secrets.token_urlsafe(32)}"

def generate_reset_token() -> str:
    """Gera token para reset de senha"""
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """Hash de token para armazenamento seguro"""
    return hashlib.sha256(token.encode()).hexdigest()

def verify_token_hash(token: str, hashed: str) -> bool:
    """Verifica token contra hash"""
    return hmac.compare_digest(hash_token(token), hashed)

def create_password_reset_token(email: str) -> str:
    """Cria token JWT para reset de senha"""
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "sub": email,
        "type": "password_reset",
        "exp": expire,
        "jti": secrets.token_urlsafe(16)
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def verify_password_reset_token(token: str) -> Optional[str]:
    """Verifica token de reset de senha"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        if payload.get("type") != "password_reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None

# ==============================================
# 8. EXPORTAÇÕES
# ==============================================

__all__ = [
    # Instâncias
    'hasher',
    'jwt_manager',
    'captcha_manager',
    'rate_limiter',
    'oauth2_scheme',
    
    # Dependências
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user',
    'get_current_manager_user',
    'check_captcha',
    
    # Utilitários
    'generate_api_key',
    'generate_reset_token',
    'hash_token',
    'verify_token_hash',
    'create_password_reset_token',
    'verify_password_reset_token',
]