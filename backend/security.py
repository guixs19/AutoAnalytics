# backend/security.py - SEM CAPTCHA (VERSÃO ATUALIZADA COM BLACKLIST CORRIGIDA)
"""
MÓDULO CENTRAL DE SEGURANÇA - VERSÃO SEM CAPTCHA
- JWT com Redis e blacklist (CORRIGIDO)
- Rate Limit com Redis
- Argon2 para hash de senhas
- 🔥 REMOVIDO: CAPTCHA completamente
- 🔥 CORRIGIDO: Blacklist funcionando em todas as verificações
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union, Tuple
import secrets
import hashlib
import hmac
import logging
import time
import os
import asyncio

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

# Configurações
from backend.config.settings import settings

logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURAÇÕES GLOBAIS
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
# 2. JWT COMPLETO COM REDIS E BLACKLIST (CORRIGIDO)
# ==============================================

class JWTManager:
    """Gerenciador de JWT com Redis e blacklist completa"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        self.redis_client = None
        self._redis_initialized = False
        
        self._pending_blacklist = {}
        self._blacklist_lock = asyncio.Lock()
        
        # 🔥 CACHE SEPARADO: token_cache para tokens válidos
        self._token_cache = {}
        self._token_cache_ttl = 60
        self._last_cache_cleanup = time.time()
        self._cache_cleanup_interval = 300
        
        # 🔥 NOVO: Cache específico para verificações de blacklist
        self._blacklist_check_cache = {}
        self._blacklist_cache_ttl = 30  # Menor TTL para blacklist
        
        self._blacklist_stats = {
            "total_revoked": 0,
            "redis_failures": 0,
            "offline_skips": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info("✅ JWT Manager inicializado com blacklist corrigida")
    
    async def init_redis(self):
        if self._redis_initialized:
            return
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2,
                retry_on_timeout=True
            )
            await self.redis_client.ping()
            self._redis_initialized = True
            logger.info("✅ Redis configurado para blacklist JWT")
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível: {e}")
            self.redis_client = None
            self._redis_initialized = True
    
    def _generate_jti(self) -> str:
        return secrets.token_urlsafe(16)
    
    def _create_token_payload(self, data: Dict[str, Any], token_type: str, expires_delta: timedelta) -> Dict[str, Any]:
        now = datetime.utcnow()
        payload = {
            "sub": data.get("sub") or data.get("email"),
            "email": data.get("email"),
            "name": data.get("name", ""),
            "role": data.get("role", "user"),
            "plan": data.get("plan", "basico"),
            "credits": data.get("credits", 0),
            "is_admin": data.get("is_admin", False),
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
            "jti": self._generate_jti(),
            "iss": "autoanalytics",
            "aud": "autoanalytics-api"
        }
        return {k: v for k, v in payload.items() if v is not None}
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        expires = timedelta(minutes=self.access_expire_minutes)
        payload = self._create_token_payload(data, "access", expires)
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, data: Dict[str, Any]) -> tuple:
        expires = timedelta(days=self.refresh_expire_days)
        payload = self._create_token_payload(data, "refresh", expires)
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, payload["jti"]
    
    def create_token_pair(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
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
    
    def decode_token(self, token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
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
    # 🔥 VERIFICAÇÃO DE TOKEN COM BLACKLIST (CORRIGIDO)
    # ==============================================
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        🔥 VERIFICAÇÃO SÍNCRONA COM BLACKLIST
        """
        payload = self.decode_token(token)
        if not payload:
            return None
        
        if payload.get("type") != token_type:
            logger.warning(f"Tipo de token inválido: esperado {token_type}, recebido {payload.get('type')}")
            return None
        
        # 🔥 VERIFICA BLACKLIST (síncrono)
        jti = payload.get("jti")
        if jti:
            # Verifica pending blacklist (memória)
            if jti in self._pending_blacklist:
                logger.warning(f"🔴 Token {jti[:8]}... está na pending blacklist")
                return None
            
            # Verifica cache de blacklist
            if self._check_blacklist_cache_sync(jti):
                logger.warning(f"🔴 Token {jti[:8]}... está na blacklist (cache)")
                return None
        
        return payload
    
    def _check_blacklist_cache_sync(self, jti: str) -> bool:
        """
        🔥 Verifica cache de blacklist (síncrono)
        """
        cache_key = f"bl_check:{jti}"
        if cache_key in self._blacklist_check_cache:
            cached = self._blacklist_check_cache[cache_key]
            # Cache expira em 30 segundos
            if time.time() - cached["timestamp"] < self._blacklist_cache_ttl:
                self._blacklist_stats["cache_hits"] += 1
                return cached.get("blacklisted", False)
        
        self._blacklist_stats["cache_misses"] += 1
        
        # Se não estiver no cache, verifica Redis (se disponível)
        if self.redis_client:
            try:
                # Tenta conexão síncrona
                exists = self.redis_client.exists(f"blacklist:{jti}")
                if exists:
                    ttl = self.redis_client.ttl(f"blacklist:{jti}")
                    if ttl <= 0:
                        self.redis_client.delete(f"blacklist:{jti}")
                        # Cache: não está blacklistado
                        self._blacklist_check_cache[cache_key] = {
                            "blacklisted": False,
                            "timestamp": time.time()
                        }
                        return False
                    # Cache: está blacklistado
                    self._blacklist_check_cache[cache_key] = {
                        "blacklisted": True,
                        "timestamp": time.time()
                    }
                    return True
                # Cache: não está blacklistado
                self._blacklist_check_cache[cache_key] = {
                    "blacklisted": False,
                    "timestamp": time.time()
                }
                return False
            except Exception as e:
                logger.error(f"Erro sync na blacklist Redis: {e}")
                return False
        
        return False
    
    async def verify_token_async(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        🔥 VERIFICAÇÃO ASSÍNCRONA COM BLACKLIST E CACHE CORRIGIDO
        """
        # 1. Limpeza de cache
        self._cleanup_token_cache()
        self._cleanup_blacklist_cache()
        
        # 2. Verifica token primeiro
        payload = self.verify_token(token, token_type)
        if not payload:
            return None
        
        # 3. Verifica blacklist (assíncrono)
        jti = payload.get("jti")
        if jti:
            # Verifica pending blacklist
            if jti in self._pending_blacklist:
                logger.warning(f"🔴 Token {jti[:8]}... está na pending blacklist")
                return None
            
            # Verifica blacklist no Redis (com cache)
            is_blacklisted = await self.is_token_blacklisted(jti)
            if is_blacklisted:
                logger.warning(f"🔴 Token {jti[:8]}... está na blacklist (Redis)")
                # Invalida cache do token
                token_hash = hashlib.md5(token.encode()).hexdigest()
                if token_hash in self._token_cache:
                    del self._token_cache[token_hash]
                return None
        
        # 4. Cache do token (apenas se válido)
        token_hash = hashlib.md5(token.encode()).hexdigest()
        if len(self._token_cache) < 2000:
            self._token_cache[token_hash] = {
                "payload": payload,
                "timestamp": time.time()
            }
        
        return payload
    
    def _cleanup_token_cache(self):
        """Limpeza do cache de tokens"""
        now = time.time()
        if now - self._last_cache_cleanup < self._cache_cleanup_interval:
            return
        
        expired = [k for k, v in self._token_cache.items() if now - v["timestamp"] > self._token_cache_ttl]
        for k in expired:
            del self._token_cache[k]
        
        if len(self._token_cache) > 1000:
            sorted_items = sorted(self._token_cache.items(), key=lambda x: x[1]["timestamp"])
            to_remove = int(len(sorted_items) * 0.2)
            for k, _ in sorted_items[:to_remove]:
                del self._token_cache[k]
            logger.info(f"🧹 Limpeza emergencial cache tokens: {to_remove} removidos")
        
        self._last_cache_cleanup = now
    
    def _cleanup_blacklist_cache(self):
        """Limpeza do cache de blacklist"""
        now = time.time()
        expired = [k for k, v in self._blacklist_check_cache.items() 
                   if now - v["timestamp"] > self._blacklist_cache_ttl]
        for k in expired:
            del self._blacklist_check_cache[k]
        
        if len(self._blacklist_check_cache) > 500:
            to_remove = int(len(self._blacklist_check_cache) * 0.3)
            for k in list(self._blacklist_check_cache.keys())[:to_remove]:
                del self._blacklist_check_cache[k]
    
    # ==============================================
    # 🔥 BLACKLIST - REVOGAÇÃO DE TOKENS (CORRIGIDO)
    # ==============================================
    
    async def blacklist_token(self, jti: str, expire_in: int):
        """
        🔥 ADICIONA TOKEN À BLACKLIST
        """
        if not jti:
            return
        
        if expire_in <= 0:
            logger.debug(f"Token {jti[:8]}... já expirado, não precisa blacklistar")
            return
        
        # 1. Adiciona à pending blacklist (memória)
        async with self._blacklist_lock:
            if jti in self._pending_blacklist:
                return
            self._pending_blacklist[jti] = time.time()
        
        # 2. Adiciona ao Redis
        try:
            if self.redis_client:
                try:
                    await self.redis_client.setex(f"blacklist:{jti}", expire_in, "1")
                    self._blacklist_stats["total_revoked"] += 1
                    logger.info(f"🔴 Token {jti[:8]}... adicionado à blacklist Redis (TTL: {expire_in}s)")
                    
                    # 🔥 Invalida cache de blacklist
                    cache_key = f"bl_check:{jti}"
                    if cache_key in self._blacklist_check_cache:
                        del self._blacklist_check_cache[cache_key]
                    
                except Exception as e:
                    self._blacklist_stats["redis_failures"] += 1
                    logger.error(f"Erro ao adicionar à blacklist Redis: {e}")
            else:
                self._blacklist_stats["offline_skips"] += 1
                logger.warning(f"⚠️ Redis indisponível - token {jti[:8]}... não foi blacklistado")
        finally:
            async with self._blacklist_lock:
                self._pending_blacklist.pop(jti, None)
    
    async def is_token_blacklisted(self, jti: str) -> bool:
        """
        🔥 VERIFICA SE TOKEN ESTÁ NA BLACKLIST (COM CACHE)
        """
        if not jti:
            return False
        
        # 1. Verifica pending blacklist
        if jti in self._pending_blacklist:
            return True
        
        # 2. Verifica cache de blacklist
        cache_key = f"bl_check:{jti}"
        if cache_key in self._blacklist_check_cache:
            cached = self._blacklist_check_cache[cache_key]
            if time.time() - cached["timestamp"] < self._blacklist_cache_ttl:
                self._blacklist_stats["cache_hits"] += 1
                return cached.get("blacklisted", False)
        
        self._blacklist_stats["cache_misses"] += 1
        
        # 3. Verifica Redis
        if not self.redis_client:
            logger.warning("⚠️ Redis indisponível - ignorando verificação de blacklist")
            return False
        
        try:
            exists = await self.redis_client.exists(f"blacklist:{jti}")
            if exists:
                ttl = await self.redis_client.ttl(f"blacklist:{jti}")
                if ttl <= 0:
                    await self.redis_client.delete(f"blacklist:{jti}")
                    # Cache: não está blacklistado
                    self._blacklist_check_cache[cache_key] = {
                        "blacklisted": False,
                        "timestamp": time.time()
                    }
                    return False
                
                # Cache: está blacklistado
                self._blacklist_check_cache[cache_key] = {
                    "blacklisted": True,
                    "timestamp": time.time()
                }
                return True
            
            # Cache: não está blacklistado
            self._blacklist_check_cache[cache_key] = {
                "blacklisted": False,
                "timestamp": time.time()
            }
            return False
            
        except Exception as e:
            logger.error(f"Erro ao verificar blacklist Redis: {e}")
            return False
    
    # ==============================================
    # 🔥 REFRESH E LOGOUT (CORRIGIDO)
    # ==============================================
    
    async def refresh_access_token(self, refresh_token: str, db, old_access_token: str = None) -> Optional[Dict[str, str]]:
        from backend import crud
        
        # Verifica refresh token (com blacklist)
        old_payload = await self.verify_token_async(refresh_token, "refresh")
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
            exp = old_payload.get("exp", 0)
            remaining = max(int(exp - datetime.utcnow().timestamp()), 3600)
            await self.blacklist_token(old_jti, remaining)
            logger.info(f"🔴 Refresh token antigo {old_jti[:8]}... blacklistado")
        
        # 🔥 Blacklist do access token antigo (se fornecido)
        if old_access_token:
            old_access_payload = self.verify_token(old_access_token, "access")
            if old_access_payload:
                old_access_jti = old_access_payload.get("jti")
                if old_access_jti:
                    remaining = max(int(old_access_payload.get("exp", 0) - datetime.utcnow().timestamp()), 300)
                    await self.blacklist_token(old_access_jti, remaining)
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
    
    async def logout(self, refresh_token: str, db, access_token: str = None) -> bool:
        from backend import crud
        
        # 🔥 Blacklist do refresh token
        refresh_payload = await self.verify_token_async(refresh_token, "refresh")
        if refresh_payload:
            email = refresh_payload.get("sub") or refresh_payload.get("email")
            if email:
                user = crud.get_user_by_email(db, email)
                if user and user.validate_refresh_token(refresh_token):
                    user.revoke_refresh_token()
            
            jti = refresh_payload.get("jti")
            if jti:
                exp = refresh_payload.get("exp", 0)
                remaining = max(int(exp - datetime.utcnow().timestamp()), 3600)
                await self.blacklist_token(jti, remaining)
                logger.info(f"🔴 Refresh token {jti[:8]}... blacklistado no logout")
        
        # 🔥 Blacklist do access token
        if access_token:
            access_payload = self.verify_token(access_token, "access")
            if access_payload:
                access_jti = access_payload.get("jti")
                if access_jti:
                    exp = access_payload.get("exp", 0)
                    remaining = max(int(exp - datetime.utcnow().timestamp()), 300)
                    await self.blacklist_token(access_jti, remaining)
                    logger.info(f"🔴 Access token {access_jti[:8]}... blacklistado no logout")
        
        if db:
            db.commit()
        
        return True
    
    def extract_token_from_header(self, auth_header: str) -> Optional[str]:
        if not auth_header:
            return None
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "").strip()
        if auth_header.startswith("JWT "):
            return auth_header.replace("JWT ", "").strip()
        return auth_header.strip()
    
    def get_blacklist_stats(self) -> Dict[str, Any]:
        return {
            **self._blacklist_stats,
            "redis_available": self.redis_client is not None,
            "pending_count": len(self._pending_blacklist),
            "cache_size": len(self._blacklist_check_cache),
            "token_cache_size": len(self._token_cache)
        }


# ==============================================
# 3. RATE LIMITER
# ==============================================

class RateLimiter:
    """Rate limiting - Previne abuso da API"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self._last_cleanup = datetime.now().timestamp()
        self._redis_initialized = False
        self._max_memory_keys = 5000
        logger.info("✅ Rate Limiter inicializado")
    
    async def init_redis(self):
        if self._redis_initialized:
            return
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2
            )
            await self.redis_client.ping()
            self._redis_initialized = True
            logger.info("✅ Redis configurado para rate limiting")
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível: {e}")
            self.redis_client = None
            self._redis_initialized = True
    
    async def check_rate_limit(self, key: str, max_requests: int, window: int) -> bool:
        now = datetime.now().timestamp()
        if self.redis_client:
            try:
                pipe = self.redis_client.pipeline()
                await pipe.incr(f"rate:{key}")
                await pipe.expire(f"rate:{key}", window)
                result = await pipe.execute()
                if result[0] <= max_requests:
                    return True
                else:
                    logger.warning(f"Rate limit excedido - {key}: {result[0]}/{max_requests}")
                    return False
            except Exception as e:
                logger.error(f"Erro no Redis: {e}")
                return True
        
        # Fallback em memória
        if now - self._last_cleanup > 300:
            self._cleanup_memory_cache()
            self._last_cleanup = now
        
        if key not in self.memory_cache:
            self.memory_cache[key] = []
        
        self.memory_cache[key] = [t for t in self.memory_cache[key] if t > now - window]
        
        if len(self.memory_cache[key]) >= max_requests:
            logger.warning(f"Rate limit excedido (memória) - {key}")
            return False
        
        self.memory_cache[key].append(now)
        
        if len(self.memory_cache) > self._max_memory_keys:
            to_remove = int(len(self.memory_cache) * 0.2)
            for k in list(self.memory_cache.keys())[:to_remove]:
                del self.memory_cache[k]
            logger.info(f"🧹 Limpeza rate limit cache: {to_remove} chaves")
        
        return True
    
    def _cleanup_memory_cache(self):
        now = datetime.now().timestamp()
        for key, timestamps in list(self.memory_cache.items()):
            self.memory_cache[key] = [t for t in timestamps if t > now - 3600]
            if not self.memory_cache[key]:
                del self.memory_cache[key]


# ==============================================
# 4. INSTÂNCIAS GLOBAIS
# ==============================================

hasher = Argon2Hasher()
jwt_manager = JWTManager()
rate_limiter = RateLimiter()


# ==============================================
# 5. DEPENDÊNCIAS FASTAPI (CORRIGIDAS)
# ==============================================

async def get_current_user(token: str = Depends(oauth2_scheme), db = None):
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
    
    # 🔥 Usa verify_token_async com blacklist
    payload = await jwt_manager.verify_token_async(token)
    if not payload:
        logger.warning("Token inválido, expirado ou revogado")
        raise credentials_exception
    
    email = payload.get("sub") or payload.get("email")
    if not email:
        logger.warning("Token sem email")
        raise credentials_exception
    
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


async def get_current_active_user(current_user = Depends(get_current_user)):
    if not current_user.is_active:
        logger.warning(f"Usuário {current_user.email} está inativo")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return current_user


async def get_current_admin_user(current_user = Depends(get_current_active_user)):
    if not current_user.is_admin:
        logger.warning(f"Usuário {current_user.email} tentou acesso admin")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de administrador."
        )
    return current_user


async def get_current_manager_user(current_user = Depends(get_current_active_user)):
    if current_user.is_admin:
        return current_user
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role_value not in ["admin", "ADMIN", "manager", "MANAGER"]:
        logger.warning(f"Usuário {current_user.email} tentou acesso manager")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de gestor ou admin."
        )
    return current_user


# ==============================================
# 6. FUNÇÕES DE UTILIDADE
# ==============================================

def generate_api_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token_hash(token: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_token(token), hashed)


def create_password_reset_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "sub": email,
        "type": "password_reset",
        "exp": expire,
        "jti": secrets.token_urlsafe(16)
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
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
# 7. FUNÇÕES PARA COOKIES
# ==============================================

def set_auth_cookies(response: Response, access_token: str, refresh_token: str = None, expires_in: int = 3600):
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=False,
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


def clear_auth_cookies(response: Response):
    response.set_cookie(key="access_token", value="", httponly=True, max_age=0, path="/")
    response.set_cookie(key="refresh_token", value="", httponly=True, max_age=0, path="/")
    return response


# ==============================================
# 8. EXPORTAÇÕES
# ==============================================

__all__ = [
    'hasher',
    'jwt_manager',
    'rate_limiter',
    'oauth2_scheme',
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user',
    'get_current_manager_user',
    'generate_api_key',
    'generate_reset_token',
    'hash_token',
    'verify_token_hash',
    'create_password_reset_token',
    'verify_password_reset_token',
    'set_auth_cookies',
    'clear_auth_cookies'
]

print("=" * 50)
print("🔥 SECURITY.PY - SEM CAPTCHA (VERSÃO ATUALIZADA)")
print("   ✅ JWT com blacklist (CORRIGIDO)")
print("   ✅ Rate Limit com Redis")
print("   ✅ Argon2 para hash de senhas")
print("   ✅ Cache separado para blacklist")
print("   ❌ CAPTCHA REMOVIDO")
print("=" * 50)