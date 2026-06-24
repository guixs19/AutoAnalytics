# backend/security.py - VERSÃO FINAL COMPLETA CORRIGIDA
"""
MÓDULO DE SEGURANÇA - VERSÃO FINAL
================================================================================
🔥 CORREÇÕES E MELHORIAS:
- ✅ SEM asyncio.run() no escopo global
- ✅ Timezone offset-aware (UTC) com timestamps UNIX para JWT
- ✅ Redis com health check automático
- ✅ Blacklist centralizada (Redis → DB → Memória Cache)
- ✅ Cache com TTL automático (5 minutos)
- ✅ Rate limiting com janela deslizante
- ✅ Funções globais para blacklist (consistente entre workers)
- ✅ _get_remaining_seconds() para evitar erro de timezone
- ✅ pending_blacklist NÃO é mais exposta diretamente
- ✅ Memory cache limitado a 1000 entradas (apenas cache)
- ✅ Fallback seguro: permite em caso de erro
================================================================================
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Union, Tuple
import secrets
import hashlib
import hmac
import logging
import time
import os
import asyncio
from functools import lru_cache

# Argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

# JWT
from jose import JWTError, jwt

# FastAPI
from fastapi import HTTPException, status, Request, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse, Response

# Redis
import redis.asyncio as redis

# SQLAlchemy
from sqlalchemy.orm import Session

# Configurações
from backend.config.settings import settings

logger = logging.getLogger(__name__)

# ==============================================
# 🔥 TIMEZONE - CORREÇÃO CRÍTICA
# ==============================================

UTC = timezone.utc

def _now_utc() -> datetime:
    """
    Retorna datetime atual com timezone UTC (offset-aware)
    Usado APENAS para operações com banco de dados.
    """
    return datetime.now(UTC)

def _utc_timestamp() -> float:
    """Retorna timestamp atual em UTC"""
    return _now_utc().timestamp()

def _get_exp_timestamp(payload: Dict[str, Any]) -> int:
    """
    🔥 CORRIGIDO: Extrai o timestamp de expiração do payload JWT.
    Lida com timestamp UNIX (int) ou datetime.
    """
    exp = payload.get("exp", 0)
    if isinstance(exp, datetime):
        return int(exp.timestamp())
    return int(exp)

def _get_remaining_seconds(payload: Dict[str, Any]) -> int:
    """
    🔥 CORRIGIDO: Calcula segundos restantes até expiração do token.
    NUNCA compara datetime com datetime - usa timestamps UNIX.
    """
    exp_ts = _get_exp_timestamp(payload)
    now_ts = _now_utc().timestamp()
    return max(0, int(exp_ts - now_ts))


# ==============================================
# OAUTH2 SCHEME
# ==============================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="api/auth/login",
    auto_error=False,
    scheme_name="JWT"
)


# ==============================================
# 1. ARGON2 - HASH DE SENHA
# ==============================================

class Argon2Hasher:
    """Hash de senha usando Argon2id"""
    
    def __init__(self):
        self.ph = PasswordHasher(
            time_cost=settings.ARGON2_TIME_COST,
            memory_cost=settings.ARGON2_MEMORY_COST,
            parallelism=settings.ARGON2_PARALLELISM,
            hash_len=32,
            salt_len=16
        )
        logger.info(f"✅ Argon2 inicializado - time_cost={settings.ARGON2_TIME_COST}")
    
    def hash_password(self, password: str) -> str:
        if not password or len(password) < 6:
            raise ValueError("Senha deve ter no mínimo 6 caracteres")
        try:
            return self.ph.hash(password)
        except Exception as e:
            logger.error(f"Erro ao gerar hash: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao processar senha")
    
    def verify_password(self, password: str, hashed: str) -> bool:
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
        try:
            return self.ph.check_needs_rehash(hashed)
        except:
            return False


# ==============================================
# 2. REDIS CLIENT - CONFIGURAÇÃO SEGURA
# ==============================================

# 🔥 SEM asyncio.run() no escopo global!
# 🔥 Timeouts configurados para evitar travamentos
redis_client = redis.from_url(
    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
    decode_responses=True,
    socket_connect_timeout=3.0,
    socket_timeout=3.0,
    retry_on_timeout=True,
    health_check_interval=30,
    max_connections=10
)

# Estado do Redis (atualizado pelas funções de health check)
REDIS_AVAILABLE = False
_redis_initialized = False
_redis_health_check_lock = asyncio.Lock()


# ==============================================
# 3. BLACKLIST EM MEMÓRIA - APENAS CACHE
# ==============================================

# 🔥 APENAS CACHE LOCAL - NÃO para persistência entre workers!
# 🔥 Tamanho limitado para evitar memory leak
_memory_blacklist_cache: Dict[str, float] = {}  # jti -> expiration_timestamp
_MEMORY_BLACKLIST_MAX_SIZE = 1000
_MEMORY_BLACKLIST_TTL = 300  # 5 minutos (cache de curta duração)

# Cache de verificação (evita chamadas repetidas ao Redis/DB)
_verification_cache: Dict[str, float] = {}  # jti -> timestamp
_VERIFICATION_CACHE_TTL = 60  # 1 minuto

# Controle de limpeza
_last_cleanup_time = time.time()
_CLEANUP_INTERVAL = 60  # 1 minuto


# ==============================================
# 4. FUNÇÕES DE INICIALIZAÇÃO E HEALTH CHECK
# ==============================================

async def init_redis():
    """
    Inicializa conexão com Redis sob demanda.
    🔥 CORRIGIDO: SEM asyncio.run() no escopo global.
    """
    global REDIS_AVAILABLE, _redis_initialized
    
    if _redis_initialized:
        return
    
    try:
        await redis_client.ping()
        REDIS_AVAILABLE = True
        _redis_initialized = True
        logger.info("✅ Redis conectado com sucesso")
    except Exception as e:
        REDIS_AVAILABLE = False
        _redis_initialized = True
        logger.warning(f"⚠️ Redis não disponível: {e}")


async def check_redis_health() -> bool:
    """
    Verifica saúde do Redis sem gerar exceções.
    Usa lock para evitar múltiplas verificações simultâneas.
    """
    global REDIS_AVAILABLE
    
    if not _redis_initialized:
        await init_redis()
        return REDIS_AVAILABLE
    
    if not REDIS_AVAILABLE:
        return False
    
    async with _redis_health_check_lock:
        try:
            await redis_client.ping()
            REDIS_AVAILABLE = True
            return True
        except Exception as e:
            REDIS_AVAILABLE = False
            logger.warning(f"⚠️ Redis health check falhou: {e}")
            return False


# ==============================================
# 5. LIMPEZA DE CACHES
# ==============================================

async def _cleanup_caches():
    """
    Limpeza automática de caches.
    🔥 Executada periodicamente para evitar memory leak.
    """
    global _last_cleanup_time, _memory_blacklist_cache, _verification_cache
    
    now = time.time()
    if now - _last_cleanup_time < _CLEANUP_INTERVAL:
        return
    
    # Limpa memory blacklist cache (entradas expiradas)
    expired = [jti for jti, ts in _memory_blacklist_cache.items() if now > ts]
    for jti in expired:
        _memory_blacklist_cache.pop(jti, None)
    if expired:
        logger.debug(f"🧹 {len(expired)} entradas removidas do memory cache")
    
    # Limpa verification cache (entradas expiradas)
    expired = [jti for jti, ts in _verification_cache.items() if now - ts > _VERIFICATION_CACHE_TTL]
    for jti in expired:
        _verification_cache.pop(jti, None)
    if expired:
        logger.debug(f"🧹 {len(expired)} entradas removidas do verification cache")
    
    _last_cleanup_time = now


# ==============================================
# 6. BLACKLIST - FUNÇÕES CENTRALIZADAS
# ==============================================

def _add_to_memory_cache(jti: str, expire_in: int):
    """
    🔥 APENAS CACHE LOCAL - não substitui Redis/DB.
    Usado como último recurso quando Redis e DB falham.
    """
    global _memory_blacklist_cache
    
    if not jti or expire_in <= 0:
        return
    
    now = time.time()
    
    # Limpa entradas expiradas
    _memory_blacklist_cache = {
        k: v for k, v in _memory_blacklist_cache.items() 
        if v > now
    }
    
    # Limita tamanho (evita memory leak)
    if len(_memory_blacklist_cache) > _MEMORY_BLACKLIST_MAX_SIZE:
        sorted_items = sorted(_memory_blacklist_cache.items(), key=lambda x: x[1])
        for old_jti, _ in sorted_items[:len(sorted_items) // 2]:
            _memory_blacklist_cache.pop(old_jti, None)
    
    # Expira em no máximo _MEMORY_BLACKLIST_TTL segundos
    cache_expire = min(expire_in, _MEMORY_BLACKLIST_TTL)
    _memory_blacklist_cache[jti] = now + cache_expire


async def blacklist_token(jti: str, expire_in: int):
    """
    🔥 FUNÇÃO CENTRALIZADA DE BLACKLIST
    Persiste em: Redis → Banco de Dados → Memória (cache)
    
    Args:
        jti: JWT ID do token
        expire_in: Segundos até expiração
    """
    if not jti or expire_in <= 0:
        return
    
    logger.info(f"🔴 Blacklistando token {jti[:8]}... (TTL: {expire_in}s)")
    
    # 1. Adiciona ao Redis (prioridade - compartilhado entre workers)
    if REDIS_AVAILABLE and await check_redis_health():
        try:
            await redis_client.setex(f"blacklist:{jti}", expire_in, "1")
            logger.info(f"✅ Token {jti[:8]}... blacklistado no Redis")
            return
        except Exception as e:
            logger.error(f"❌ Erro ao blacklistar no Redis: {e}")
    
    # 2. FALLBACK: Banco de dados (persistente entre workers)
    try:
        from backend.database import SessionLocal
        from backend.models import BlacklistedToken
        
        db = SessionLocal()
        try:
            blacklisted = BlacklistedToken(
                jti=jti,
                expires_at=_now_utc() + timedelta(seconds=expire_in),
                created_at=_now_utc()
            )
            db.add(blacklisted)
            db.commit()
            logger.info(f"✅ Token {jti[:8]}... salvo no banco (fallback)")
            return
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ Erro no fallback DB: {e}")
    
    # 3. ÚLTIMO RECURSO: Memória local (apenas este worker)
    _add_to_memory_cache(jti, expire_in)
    logger.warning(f"⚠️ Token {jti[:8]}... apenas em memória local (não compartilhado)")


async def is_token_blacklisted(jti: str) -> bool:
    """
    🔥 VERIFICA BLACKLIST
    Ordem: Memória Cache → Redis → Banco de Dados
    
    🔥 CORRIGIDO: NUNCA retorna erro - sempre retorna bool.
    Em caso de falha, retorna False (permite) para não bloquear usuários.
    """
    if not jti:
        return False
    
    await _cleanup_caches()
    now = time.time()
    
    # 1. Verifica cache em memória (rápido, mas apenas este worker)
    if jti in _memory_blacklist_cache:
        if _memory_blacklist_cache[jti] > now:
            return True
        else:
            _memory_blacklist_cache.pop(jti, None)
    
    # 2. Verifica cache de verificação (evita chamadas repetidas)
    if jti in _verification_cache:
        if now - _verification_cache[jti] < _VERIFICATION_CACHE_TTL:
            return True
        else:
            _verification_cache.pop(jti, None)
    
    # 3. Verifica Redis (compartilhado entre workers)
    if REDIS_AVAILABLE and await check_redis_health():
        try:
            exists = await redis_client.exists(f"blacklist:{jti}")
            if exists:
                ttl = await redis_client.ttl(f"blacklist:{jti}")
                if ttl <= 0:
                    await redis_client.delete(f"blacklist:{jti}")
                    return False
                _verification_cache[jti] = now
                return True
            return False
        except Exception as e:
            logger.error(f"Erro ao verificar blacklist no Redis: {e}")
            # Continua para fallback
    
    # 4. FALLBACK: Banco de dados (persistente entre workers)
    try:
        from backend.database import SessionLocal
        from backend.models import BlacklistedToken
        
        db = SessionLocal()
        try:
            exists = db.query(BlacklistedToken).filter(
                BlacklistedToken.jti == jti,
                BlacklistedToken.expires_at > _now_utc()
            ).first()
            if exists:
                _verification_cache[jti] = now
                return True
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Erro no fallback DB: {e}")
        # 🔥 FALLBACK SEGURO: permite em caso de erro
        return False


# ==============================================
# 7. RATE LIMITER - JANELA DESLIZANTE
# ==============================================

class RateLimiter:
    """
    Rate limiting com janela deslizante usando Redis Sorted Sets.
    🔥 CORRIGIDO: Fallback seguro - permite em caso de erro.
    """
    
    def __init__(self):
        self._redis_initialized = False
        self._last_health_check = 0
        logger.info("✅ Rate Limiter inicializado")
    
    async def init_redis(self):
        """Inicializa Redis para rate limiting"""
        if self._redis_initialized:
            return
        await init_redis()
        self._redis_initialized = True
    
    async def check_redis_health(self) -> bool:
        """Verifica saúde do Redis"""
        return await check_redis_health()
    
    async def check_rate_limit(self, key: str, max_requests: int, window: int) -> bool:
        """
        🔥 Rate limiting com janela deslizante.
        Retorna True se permitido, False se bloqueado.
        Em caso de erro, retorna True (fallback seguro).
        """
        if not self._redis_initialized:
            await self.init_redis()
        
        if not REDIS_AVAILABLE or not await self.check_redis_health():
            logger.warning(f"⚠️ Redis indisponível - rate limit disabled para {key}")
            return True  # 🔥 FALLBACK SEGURO: permite
        
        try:
            now = time.time()
            window_start = now - window
            redis_key = f"rate:{key}"
            
            # Remove requisições fora da janela
            await redis_client.zremrangebyscore(redis_key, 0, window_start)
            
            # Conta requisições na janela
            count = await redis_client.zcard(redis_key)
            
            if count >= max_requests:
                logger.warning(f"Rate limit excedido - {key}: {count}/{max_requests}")
                return False
            
            # Adiciona nova requisição com ID único (evita colisões)
            unique_member = f"{now}:{secrets.token_hex(4)}"
            await redis_client.zadd(redis_key, {unique_member: now})
            await redis_client.expire(redis_key, window)
            
            return True
            
        except Exception as e:
            logger.error(f"Erro no rate limiting: {e}")
            return True  # 🔥 FALLBACK SEGURO: permite


# ==============================================
# 8. JWT MANAGER
# ==============================================

class JWTManager:
    """
    Gerenciador de JWT com Redis e blacklist.
    🔥 CORRIGIDO: Usa timestamps UNIX em vez de datetime para JWT.
    """
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        self._stats = {
            "total_revoked": 0,
            "redis_failures": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info("✅ JWT Manager inicializado (timestamps UNIX)")
    
    def _generate_jti(self) -> str:
        """Gera JWT ID único"""
        return secrets.token_urlsafe(16)
    
    # ==============================================
    # CRIAÇÃO DE TOKENS (COM TIMESTAMPS UNIX)
    # ==============================================
    
    def _create_token_payload(self, data: Dict[str, Any], token_type: str, expires_delta: timedelta) -> Dict[str, Any]:
        """
        🔥 CORRIGIDO: Usa timestamps UNIX em vez de datetime.
        Isso evita problemas de comparação offset-naive vs offset-aware.
        """
        now_ts = int(_now_utc().timestamp())
        exp_ts = now_ts + int(expires_delta.total_seconds())
        
        payload = {
            "sub": data.get("sub") or data.get("email"),
            "email": data.get("email"),
            "name": data.get("name", ""),
            "role": data.get("role", "user"),
            "plan": data.get("plan", "basico"),
            "credits": data.get("credits", 0),
            "is_admin": data.get("is_admin", False),
            "type": token_type,
            "iat": now_ts,  # 🔥 timestamp UNIX
            "exp": exp_ts,  # 🔥 timestamp UNIX
            "jti": self._generate_jti(),
            "iss": "autoanalytics",
            "aud": "autoanalytics-api"
        }
        return {k: v for k, v in payload.items() if v is not None}
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Cria access token"""
        expires = timedelta(minutes=self.access_expire_minutes)
        payload = self._create_token_payload(data, "access", expires)
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, data: Dict[str, Any]) -> tuple:
        """Cria refresh token e retorna (token, jti)"""
        expires = timedelta(days=self.refresh_expire_days)
        payload = self._create_token_payload(data, "refresh", expires)
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, payload["jti"]
    
    def create_token_pair(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Cria par de tokens (access + refresh)"""
        payload = {
            "sub": user_data.get("sub") or user_data.get("email"),
            "email": user_data.get("email"),
            "name": user_data.get("name", ""),
            "role": user_data.get("role", "user"),
            "plan": user_data.get("plan", "basico"),
            "credits": user_data.get("credits", 0),
            "is_admin": user_data.get("is_admin", False)
        }
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
    
    # ==============================================
    # DECODIFICAÇÃO DE TOKENS
    # ==============================================
    
    def decode_token(self, token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
        """
        Decodifica token JWT.
        🔥 CORRIGIDO: Lida com timestamps UNIX internamente.
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
    
    # ==============================================
    # VERIFICAÇÃO DE TOKEN
    # ==============================================
    
    async def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Verifica token com blacklist.
        🔥 CORRIGIDO: Usa is_token_blacklisted() centralizada.
        """
        # 1. Decodifica JWT
        payload = self.decode_token(token)
        if not payload:
            return None
        
        # 2. Verifica tipo
        if payload.get("type") != token_type:
            logger.warning(f"Tipo de token inválido: esperado {token_type}")
            return None
        
        # 3. Verifica blacklist
        jti = payload.get("jti")
        if jti:
            is_blacklisted = await is_token_blacklisted(jti)
            if is_blacklisted:
                logger.warning(f"🔴 Token {jti[:8]}... está na blacklist")
                return None
        
        return payload
    
    # ==============================================
    # REFRESH TOKEN
    # ==============================================
    
    async def refresh_access_token(
        self, 
        refresh_token: str, 
        db: Session, 
        old_access_token: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Renova access token usando refresh token.
        🔥 CORRIGIDO: Usa _get_remaining_seconds() para timezone.
        """
        from backend import crud
        
        # Verifica refresh token
        old_payload = await self.verify_token(refresh_token, "refresh")
        if not old_payload:
            logger.warning("Refresh token inválido ou expirado")
            return None
        
        email = old_payload.get("sub") or old_payload.get("email")
        if not email:
            logger.warning("Refresh token sem email")
            return None
        
        user = crud.get_user_by_email(db, email)
        if not user:
            logger.warning(f"Usuário {email} não encontrado")
            return None
        
        if not user.validate_refresh_token(refresh_token):
            logger.warning(f"Refresh token não corresponde ao banco para {email}")
            return None
        
        # 🔥 Blacklist do refresh token antigo
        old_jti = old_payload.get("jti")
        if old_jti:
            remaining = _get_remaining_seconds(old_payload)
            remaining = max(remaining, 3600)
            await blacklist_token(old_jti, remaining)
            logger.info(f"🔴 Refresh token antigo {old_jti[:8]}... blacklistado")
        
        # 🔥 Blacklist do access token antigo
        if old_access_token:
            old_access_payload = self.decode_token(old_access_token)
            if old_access_payload:
                old_access_jti = old_access_payload.get("jti")
                if old_access_jti:
                    remaining = _get_remaining_seconds(old_access_payload)
                    remaining = max(remaining, 300)
                    await blacklist_token(old_access_jti, remaining)
                    logger.info(f"🔴 Access token antigo {old_access_jti[:8]}... blacklistado")
        
        # Cria novos tokens
        user_data = {
            "sub": user.email,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
            "credits": user.credits,
            "is_admin": user.is_admin
        }
        
        new_tokens = self.create_token_pair(user_data)
        
        # Atualiza refresh token no banco
        user.revoke_refresh_token()
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
    
    # ==============================================
    # LOGOUT
    # ==============================================
    
    async def logout(self, refresh_token: str, db: Session, access_token: Optional[str] = None) -> bool:
        """
        Logout - invalida tokens.
        🔥 CORRIGIDO: Usa _get_remaining_seconds() para timezone.
        """
        from backend import crud
        
        # 🔥 Blacklist do refresh token
        refresh_payload = await self.verify_token(refresh_token, "refresh")
        if refresh_payload:
            email = refresh_payload.get("sub") or refresh_payload.get("email")
            if email:
                user = crud.get_user_by_email(db, email)
                if user and user.validate_refresh_token(refresh_token):
                    user.revoke_refresh_token()
            
            jti = refresh_payload.get("jti")
            if jti:
                remaining = _get_remaining_seconds(refresh_payload)
                remaining = max(remaining, 3600)
                await blacklist_token(jti, remaining)
                logger.info(f"🔴 Refresh token {jti[:8]}... blacklistado no logout")
        
        # 🔥 Blacklist do access token
        if access_token:
            access_payload = self.decode_token(access_token)
            if access_payload:
                access_jti = access_payload.get("jti")
                if access_jti:
                    remaining = _get_remaining_seconds(access_payload)
                    remaining = max(remaining, 300)
                    await blacklist_token(access_jti, remaining)
                    logger.info(f"🔴 Access token {access_jti[:8]}... blacklistado no logout")
        
        if db:
            db.commit()
        
        return True
    
    # ==============================================
    # UTILIDADES
    # ==============================================
    
    def extract_token_from_header(self, auth_header: str) -> Optional[str]:
        """Extrai token do header Authorization"""
        if not auth_header:
            return None
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "").strip()
        if auth_header.startswith("JWT "):
            return auth_header.replace("JWT ", "").strip()
        return auth_header.strip()
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do JWT Manager"""
        return {
            **self._stats,
            "redis_available": REDIS_AVAILABLE,
            "memory_cache_size": len(_memory_blacklist_cache),
            "verification_cache_size": len(_verification_cache)
        }


# ==============================================
# 9. INSTÂNCIAS GLOBAIS
# ==============================================

hasher = Argon2Hasher()
jwt_manager = JWTManager()
rate_limiter = RateLimiter()


# ==============================================
# 10. DEPENDÊNCIAS FASTAPI
# ==============================================

def get_db():
    """Dependency para obter sessão do banco de dados."""
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    🔥 OBTÉM O USUÁRIO ATUAL A PARTIR DO TOKEN JWT
    - Suporte a token no header (Authorization: Bearer)
    - Suporte a token no cookie (access_token)
    - Verifica se usuário está ativo
    - Fecha sessão do banco automaticamente
    """
    from backend import crud
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Extrai token de várias fontes
    extracted_token = token
    
    if not extracted_token:
        cookie_token = request.cookies.get("access_token")
        if cookie_token and cookie_token.startswith("Bearer "):
            extracted_token = cookie_token.replace("Bearer ", "")
    
    if not extracted_token:
        logger.warning("🔴 Token não fornecido")
        raise credentials_exception
    
    # 2. Verifica o token (com blacklist)
    try:
        payload = await jwt_manager.verify_token(extracted_token)
    except Exception as e:
        logger.error(f"❌ Erro ao verificar token: {e}")
        raise credentials_exception
    
    if not payload:
        logger.warning("🔴 Token inválido, expirado ou revogado")
        raise credentials_exception
    
    # 3. Extrai email do payload
    email = payload.get("sub") or payload.get("email")
    if not email:
        logger.warning("🔴 Token sem email")
        raise credentials_exception
    
    # 4. Busca usuário
    try:
        user = crud.get_user_by_email(db, email=email)
        if not user:
            logger.warning(f"🔴 Usuário {email} não encontrado")
            raise credentials_exception
        
        if not user.is_active:
            logger.warning(f"🔴 Usuário {email} está inativo")
            raise credentials_exception
        
        logger.debug(f"✅ Usuário autenticado: {user.email}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar usuário {email}: {e}")
        raise credentials_exception


async def get_current_active_user(current_user = Depends(get_current_user)):
    """Verifica se usuário está ativo"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return current_user


async def get_current_admin_user(current_user = Depends(get_current_active_user)):
    """Verifica se usuário é admin"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de administrador."
        )
    return current_user


async def get_current_manager_user(current_user = Depends(get_current_active_user)):
    """Verifica se usuário é manager ou admin"""
    if current_user.is_admin:
        return current_user
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role_value not in ["admin", "ADMIN", "manager", "MANAGER"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de gestor ou admin."
        )
    return current_user


# ==============================================
# 11. FUNÇÕES DE UTILIDADE
# ==============================================

def generate_api_key() -> str:
    """Gera API key"""
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
    """
    Cria token para reset de senha.
    🔥 CORRIGIDO: Usa timestamp UNIX para expiração.
    """
    now_ts = int(_now_utc().timestamp())
    exp_ts = now_ts + (24 * 60 * 60)  # 24 horas
    
    payload = {
        "sub": email,
        "type": "password_reset",
        "exp": exp_ts,  # 🔥 timestamp UNIX
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
# 12. FUNÇÕES PARA COOKIES
# ==============================================

def set_auth_cookies(
    response: Response, 
    access_token: str, 
    refresh_token: Optional[str] = None, 
    expires_in: int = 3600
) -> Response:
    """Define cookies de autenticação"""
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=False,  # 🔥 Em produção, mude para True
        samesite="lax",
        max_age=expires_in,
        path="/"
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
            path="/"
        )
    return response


def clear_auth_cookies(response: Response) -> Response:
    """Remove cookies de autenticação"""
    response.set_cookie(key="access_token", value="", httponly=True, max_age=0, path="/")
    response.set_cookie(key="refresh_token", value="", httponly=True, max_age=0, path="/")
    return response


# ==============================================
# 13. EXPORTAÇÕES
# ==============================================

__all__ = [
    # Classes e instâncias
    'hasher',
    'jwt_manager',
    'rate_limiter',
    'oauth2_scheme',
    
    # Dependências FastAPI
    'get_db',
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user',
    'get_current_manager_user',
    
    # Funções de blacklist
    'blacklist_token',
    'is_token_blacklisted',
    
    # Funções de timezone
    '_now_utc',
    '_get_remaining_seconds',
    '_get_exp_timestamp',
    
    # Funções de utilidade
    'generate_api_key',
    'generate_reset_token',
    'hash_token',
    'verify_token_hash',
    'create_password_reset_token',
    'verify_password_reset_token',
    
    # Funções de cookies
    'set_auth_cookies',
    'clear_auth_cookies',
    
    # Inicialização
    'init_redis',
    'check_redis_health'
]

print("=" * 70)
print("🔥 SECURITY.PY - VERSÃO FINAL COMPLETA CORRIGIDA")
print("=" * 70)
print("   ✅ SEM asyncio.run() no escopo global")
print("   ✅ Redis com health check automático")
print("   ✅ Timezone: timestamps UNIX no JWT")
print("   ✅ _get_remaining_seconds() - sem erro de timezone")
print("   ✅ Blacklist centralizada: Redis → DB → Memória Cache")
print("   ✅ Memory cache limitado (1000 entradas, 5min TTL)")
print("   ✅ Fallback seguro: permite em caso de erro")
print("   ✅ Rate limiting com janela deslizante")
print("   ✅ pending_blacklist NÃO é exposta diretamente")
print("=" * 70)