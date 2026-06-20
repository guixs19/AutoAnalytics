# backend/security.py - VERSÃO OTIMIZADA (CAPTCHA LEGÍVEL + RATE LIMIT)
"""
MÓDULO CENTRAL DE SEGURANÇA - VERSÃO ATUALIZADA
- CAPTCHA com números GIGANTES e espaçamento otimizado
- Rate Limit específico para validação de CAPTCHA
- PoW (Proof of Work) com Redis (apenas para upload)
- JWT com blacklist e refresh token
- Argon2 para hash de senhas
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union, Tuple
import secrets
import hashlib
import hmac
import logging
import io
import random
import string
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
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, Response

# Redis
import redis.asyncio as redis

# PIL para geração de imagem com distorção
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("⚠️ PIL não disponível. Instale: pip install Pillow")

# Configurações
from backend.config.settings import settings

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURAÇÕES GLOBAIS
# ==============================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="api/auth/login", 
    auto_error=False,
    scheme_name="JWT"
)

# 🔥 RATE LIMIT PARA CAPTCHA (anti-brute force)
CAPTCHA_RATE_LIMIT = 5  # Máximo de tentativas
CAPTCHA_RATE_WINDOW = 60  # Em 60 segundos


# ==============================================
# 1. ARGON2 - HASH DE SENHA
# ==============================================

class Argon2Hasher:
    """Hash de senha usando Argon2id - VERSÃO SEGURA"""
    
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
            raise HTTPException(
                status_code=500,
                detail="Erro interno ao processar senha"
            )
    
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
# 2. JWT COMPLETO COM REDIS E BLACKLIST
# ==============================================

class JWTManager:
    """Gerenciador de JWT com Redis e blacklist completa"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        self.redis_client = None
        self.memory_blacklist = set()
        self._redis_initialized = False
        
        self._pending_blacklist = {}
        self._blacklist_lock = asyncio.Lock()
        
        self._token_cache = {}
        self._token_cache_ttl = 60
        self._last_cache_cleanup = time.time()
        self._cache_cleanup_interval = 300
        
        logger.info("✅ JWT Manager inicializado")
    
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
            logger.warning(f"⚠️ Redis não disponível: {e} - usando fallback em memória")
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
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        payload = self.decode_token(token)
        
        if not payload:
            return None
        
        if payload.get("type") != token_type:
            logger.warning(f"Tipo de token inválido: esperado {token_type}, recebido {payload.get('type')}")
            return None
        
        return payload
    
    def _cleanup_token_cache(self):
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
    
    async def verify_token_async(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        self._cleanup_token_cache()
        
        token_hash = hashlib.md5(token.encode()).hexdigest()
        if token_hash in self._token_cache:
            cached = self._token_cache[token_hash]
            if time.time() - cached["timestamp"] < self._token_cache_ttl:
                return cached["payload"]
        
        payload = self.verify_token(token, token_type)
        
        if not payload:
            return None
        
        jti = payload.get("jti")
        if jti and await self.is_token_blacklisted(jti):
            logger.warning(f"🔴 Token {jti[:8]}... está na blacklist")
            return None
        
        if len(self._token_cache) < 2000:
            self._token_cache[token_hash] = {
                "payload": payload,
                "timestamp": time.time()
            }
        
        return payload
    
    async def refresh_access_token(self, refresh_token: str, db, old_access_token: str = None) -> Optional[Dict[str, str]]:
        from backend import crud
        
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
        
        old_jti = old_payload.get("jti")
        if old_jti:
            exp = old_payload.get("exp", 0)
            remaining = max(int(exp - datetime.utcnow().timestamp()), 3600)
            await self.blacklist_token(old_jti, remaining)
            logger.info(f"🔴 Refresh token antigo {old_jti[:8]}... blacklistado")
        
        if old_access_token:
            old_access_payload = self.verify_token(old_access_token, "access")
            if old_access_payload:
                old_access_jti = old_access_payload.get("jti")
                if old_access_jti:
                    remaining = max(int(old_access_payload.get("exp", 0) - datetime.utcnow().timestamp()), 300)
                    await self.blacklist_token(old_access_jti, remaining)
                    logger.info(f"🔴 Access token antigo {old_access_jti[:8]}... blacklistado")
        
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
    
    async def blacklist_token(self, jti: str, expire_in: int):
        if not jti:
            return
        
        async with self._blacklist_lock:
            if jti in self._pending_blacklist:
                return
            self._pending_blacklist[jti] = time.time()
        
        try:
            if self.redis_client:
                try:
                    await self.redis_client.setex(f"blacklist:{jti}", expire_in, "1")
                    logger.info(f"🔴 Token {jti[:8]}... adicionado à blacklist Redis")
                except Exception as e:
                    logger.error(f"Erro ao adicionar à blacklist Redis: {e}")
                    self.memory_blacklist.add(jti)
            else:
                self.memory_blacklist.add(jti)
                logger.info(f"🔴 Token {jti[:8]}... adicionado à blacklist em memória")
        finally:
            async with self._blacklist_lock:
                self._pending_blacklist.pop(jti, None)
    
    async def is_token_blacklisted(self, jti: str) -> bool:
        if not jti:
            return False
        
        if jti in self._pending_blacklist:
            return True
        
        if self.redis_client:
            try:
                exists = await self.redis_client.exists(f"blacklist:{jti}") > 0
                return exists
            except Exception as e:
                logger.error(f"Erro ao verificar blacklist Redis: {e}")
                return jti in self.memory_blacklist
        else:
            return jti in self.memory_blacklist
    
    def extract_token_from_header(self, auth_header: str) -> Optional[str]:
        if not auth_header:
            return None
        
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "").strip()
        
        if auth_header.startswith("JWT "):
            return auth_header.replace("JWT ", "").strip()
        
        return auth_header.strip()


# ==============================================
# 3. PROOF OF WORK MANAGER 
# ==============================================

class PoWManager:
    """Proof of Work Manager - Apenas para upload de arquivos"""
    
    def __init__(self):
        self.default_complexity = 4
        self.mobile_complexity = 3
        
        self.redis_client = None
        self._redis_initialized = False
        
        self._memory_cache = {}
        self._max_memory_cache = 1000
        self._last_memory_cleanup = time.time()
        
        self._challenge_requests = {}
        self._max_challenges_per_minute = 10
        self._cache_lock = asyncio.Lock()
        
        logger.info("⚡ PoW Manager inicializado (apenas para upload)")
    
    async def init_redis(self):
        if self._redis_initialized:
            return
        
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True
            )
            await self.redis_client.ping()
            self._redis_initialized = True
            logger.info("✅ Redis configurado para PoW Manager")
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível para PoW: {e}")
            self.redis_client = None
            self._redis_initialized = True
    
    def _get_redis_key(self, prefix: str) -> str:
        return f"pow:challenge:{prefix}"
    
    async def _check_rate_limit(self, client_ip: str) -> bool:
        now = time.time()
        
        if client_ip in self._challenge_requests:
            self._challenge_requests[client_ip] = [
                t for t in self._challenge_requests[client_ip] if now - t < 60
            ]
        
        current_count = len(self._challenge_requests.get(client_ip, []))
        if current_count >= self._max_challenges_per_minute:
            return False
        
        if client_ip not in self._challenge_requests:
            self._challenge_requests[client_ip] = []
        self._challenge_requests[client_ip].append(now)
        
        if len(self._challenge_requests) > 1000:
            self._challenge_requests = {
                ip: timestamps for ip, timestamps in self._challenge_requests.items()
                if any(now - t < 300 for t in timestamps)
            }
        
        return True
    
    async def get_challenge(self, client_ip: str, complexity: int = None) -> dict:
        if complexity is None:
            complexity = self.default_complexity
        
        if not await self._check_rate_limit(client_ip):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=429,
                detail="Muitos desafios PoW solicitados. Aguarde um momento."
            )
        
        prefix = secrets.token_hex(8)
        expires_in = 120
        created_at = time.time()
        
        if self.redis_client:
            try:
                redis_key = self._get_redis_key(prefix)
                redis_value = f"{complexity}:{created_at + expires_in}:0:{created_at}"
                await self.redis_client.setex(redis_key, expires_in, redis_value)
                
                return {
                    "prefix": prefix,
                    "complexity": complexity,
                    "timestamp": int(created_at),
                    "expires_in": expires_in
                }
            except Exception as e:
                logger.error(f"Erro ao salvar PoW no Redis: {e}")
        
        async with self._cache_lock:
            self._cleanup_memory_cache()
            
            if len(self._memory_cache) >= self._max_memory_cache:
                logger.warning("⚠️ PoW cache em memória cheio")
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Servidor sobrecarregado. Tente novamente."
                )
            
            self._memory_cache[prefix] = {
                "complexity": complexity,
                "expires_at": created_at + expires_in,
                "created_at": created_at,
                "used": False,
                "ip": client_ip
            }
            
            return {
                "prefix": prefix,
                "complexity": complexity,
                "timestamp": int(created_at),
                "expires_in": expires_in
            }
    
    async def verify_solution(self, prefix: str, nonce: str, complexity: int, client_ip: str) -> bool:
        challenge_data = None
        used_redis = False
        
        if self.redis_client:
            try:
                redis_key = self._get_redis_key(prefix)
                value = await self.redis_client.get(redis_key)
                
                if value:
                    used_redis = True
                    parts = value.split(":")
                    if len(parts) >= 4:
                        stored_complexity = int(parts[0])
                        expires_at = float(parts[1])
                        used = parts[2] == "1"
                        
                        if used:
                            return False
                        
                        if time.time() > expires_at:
                            await self.redis_client.delete(redis_key)
                            return False
                        
                        if stored_complexity != complexity:
                            return False
                        
                        challenge_data = {"complexity": stored_complexity}
            except Exception as e:
                logger.error(f"Erro ao verificar PoW no Redis: {e}")
        
        if not challenge_data:
            async with self._cache_lock:
                if prefix not in self._memory_cache:
                    return False
                
                cached = self._memory_cache[prefix]
                
                if cached.get("used"):
                    return False
                
                if time.time() > cached.get("expires_at", 0):
                    del self._memory_cache[prefix]
                    return False
                
                if cached.get("complexity") != complexity:
                    return False
                
                challenge_data = cached
        
        is_valid = self._validate_pow(prefix, nonce, complexity)
        
        if is_valid:
            if used_redis and self.redis_client:
                try:
                    redis_key = self._get_redis_key(prefix)
                    current = await self.redis_client.get(redis_key)
                    if current:
                        parts = current.split(":")
                        parts[2] = "1"
                        ttl = await self.redis_client.ttl(redis_key)
                        if ttl > 0:
                            await self.redis_client.setex(redis_key, ttl, ":".join(parts))
                except Exception as e:
                    logger.error(f"Erro ao marcar PoW como usado: {e}")
            else:
                async with self._cache_lock:
                    if prefix in self._memory_cache:
                        self._memory_cache[prefix]["used"] = True
            
            logger.info(f"✅ PoW válido para {prefix[:8]}...")
        else:
            logger.warning(f"❌ PoW inválido para {prefix[:8]}...")
        
        return is_valid
    
    def _validate_pow(self, prefix: str, nonce: str, complexity: int) -> bool:
        import hashlib
        
        data = f"{prefix}{nonce}".encode()
        hash_result = hashlib.sha256(data).hexdigest()
        
        return hash_result.startswith('0')
    
    def _cleanup_memory_cache(self):
        now = time.time()
        
        if now - self._last_memory_cleanup < 60:
            return
        
        expired = [k for k, v in self._memory_cache.items() if now > v.get("expires_at", 0)]
        for k in expired:
            del self._memory_cache[k]
        
        if len(self._memory_cache) > self._max_memory_cache:
            sorted_items = sorted(
                self._memory_cache.items(),
                key=lambda x: x[1].get("created_at", 0)
            )
            to_remove = len(self._memory_cache) - self._max_memory_cache
            for k, _ in sorted_items[:to_remove]:
                del self._memory_cache[k]
            logger.warning(f"⚠️ PoW cache limpo: {to_remove} removidos")
        
        self._last_memory_cleanup = now
    
    async def cleanup_expired(self):
        while True:
            await asyncio.sleep(300)
            now = time.time()
            expired_ips = [
                ip for ip, timestamps in self._challenge_requests.items()
                if not any(now - t < 300 for t in timestamps)
            ]
            for ip in expired_ips:
                del self._challenge_requests[ip]


# ==============================================
# 4. CAPTCHA OTIMIZADO - NÚMEROS GIGANTES + LEGÍVEL
# ==============================================

class CaptchaSession:
    """Sessão de CAPTCHA"""
    
    __slots__ = ['captcha_id', 'correct_code', 'ip', 'expires_at', 'used', 'created_at']
    
    def __init__(self, captcha_id: str, correct_code: str, ip: str, expires_at: float):
        self.captcha_id = captcha_id
        self.correct_code = correct_code
        self.ip = ip
        self.expires_at = expires_at
        self.used = False
        self.created_at = time.time()
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def time_remaining(self) -> int:
        return max(0, int(self.expires_at - time.time()))


class CaptchaStore:
    """
    Armazenamento de CAPTCHAs - VERSÃO CORRIGIDA
    Agora isola completamente sessões por tipo (login/register)
    """
    
    def __init__(self):
        self._store: Dict[str, CaptchaSession] = {}
        self._user_sessions: Dict[str, str] = {}
        self._cleanup_interval = 60
        self._last_cleanup = time.time()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._max_store_size = 5000
        self._store_lock = asyncio.Lock()
        
        logger.info("✅ CaptchaStore inicializado")
    
    async def start_cleanup_loop(self):
        if self._cleanup_task is not None:
            return
        
        async def cleanup_loop():
            logger.info("🧹 Loop de limpeza do CAPTCHA iniciado")
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_async()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("✅ Cleanup loop do CAPTCHA agendado")
    
    async def stop_cleanup_loop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("🛑 Cleanup loop do CAPTCHA parado")
    
    def _get_user_key(self, ip: str, session_type: str = "login") -> str:
        return f"{session_type}:{ip}"
    
    async def _cleanup_async(self):
        async with self._store_lock:
            now = time.time()
            expired = [cid for cid, s in self._store.items() if s.is_expired()]
            
            for cid in expired:
                for user_key, session_cid in list(self._user_sessions.items()):
                    if session_cid == cid:
                        del self._user_sessions[user_key]
                del self._store[cid]
            
            if expired:
                logger.info(f"🧹 {len(expired)} CAPTCHAs expirados removidos")
            
            self._last_cleanup = now
    
    async def add(self, captcha_id: str, correct_code: str, ip: str, session_type: str = "login") -> str:
        async with self._store_lock:
            now = time.time()
            
            if now - self._last_cleanup > self._cleanup_interval:
                await self._cleanup_async()
            
            if len(self._store) >= self._max_store_size:
                logger.warning(f"⚠️ CaptchaStore cheio ({len(self._store)} itens)")
                sorted_items = sorted(self._store.items(), key=lambda x: x[1].created_at)
                to_remove = int(len(sorted_items) * 0.1)
                for cid, _ in sorted_items[:to_remove]:
                    for user_key, session_cid in list(self._user_sessions.items()):
                        if session_cid == cid:
                            del self._user_sessions[user_key]
                    del self._store[cid]
                logger.info(f"🧹 Limpeza emergencial: {to_remove} CAPTCHAs removidos")
            
            user_key = self._get_user_key(ip, session_type)
            
            if user_key in self._user_sessions:
                old_id = self._user_sessions[user_key]
                if old_id in self._store:
                    del self._store[old_id]
                    logger.info(f"🔄 CAPTCHA anterior para {user_key} substituído")
                del self._user_sessions[user_key]
            
            expires_at = time.time() + 120
            session = CaptchaSession(captcha_id, correct_code, ip, expires_at)
            
            self._store[captcha_id] = session
            self._user_sessions[user_key] = captcha_id
            
            logger.info(f"🔢 CAPTCHA criado para {user_key}: código = {correct_code}")
            
            return captcha_id
    
    async def get_and_validate(self, captcha_id: str, user_answer: str, ip: str, session_type: str = "login") -> Tuple[bool, str]:
        async with self._store_lock:
            if time.time() - self._last_cleanup > self._cleanup_interval:
                await self._cleanup_async()
            
            if captcha_id not in self._store:
                return False, "CAPTCHA não encontrado ou já expirou"
            
            session = self._store[captcha_id]
            user_key = self._get_user_key(ip, session_type)
            
            if user_key in self._user_sessions and self._user_sessions[user_key] != captcha_id:
                logger.warning(f"⚠️ Usuário {user_key} tentou usar CAPTCHA de outra sessão")
                return False, "Desafio não pertence à sua sessão atual"
            
            if session.is_expired():
                if user_key in self._user_sessions and self._user_sessions[user_key] == captcha_id:
                    del self._user_sessions[user_key]
                del self._store[captcha_id]
                return False, "Desafio expirado (2 minutos)"
            
            if session.used:
                if user_key in self._user_sessions and self._user_sessions[user_key] == captcha_id:
                    del self._user_sessions[user_key]
                del self._store[captcha_id]
                return False, "Desafio já foi utilizado"
            
            user_answer_clean = user_answer.strip().replace(" ", "")
            
            if user_answer_clean != session.correct_code:
                return False, f"Resposta incorreta! O código correto é {session.correct_code}"
            
            session.used = True
            
            if user_key in self._user_sessions:
                del self._user_sessions[user_key]
            
            del self._store[captcha_id]
            
            logger.info(f"✅ CAPTCHA {captcha_id[:8]}... validado com sucesso para {user_key}!")
            
            return True, "Código correto!"
    
    def get_active_captcha_for_user(self, ip: str, session_type: str = "login") -> Optional[str]:
        user_key = self._get_user_key(ip, session_type)
        captcha_id = self._user_sessions.get(user_key)
        
        if captcha_id and captcha_id in self._store:
            session = self._store[captcha_id]
            if not session.is_expired() and not session.used:
                return captcha_id
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_active": len(self._store),
            "total_sessions": len(self._user_sessions),
            "max_size": self._max_store_size,
            "captcha_type": "simple_numbers_optimized"
        }


# ==============================================
# 🔥 CAPTCHA OTIMIZADO - VERSÃO LEGÍVEL NO MOBILE
# ==============================================

class CaptchaManager:
    """
    Gerenciador de CAPTCHA OTIMIZADO
    - Números GIGANTES (fonte 180px)
    - Espaçamento fixo entre caracteres (evita letras coladas)
    - Ruído substituído por pontos (splatters) - mais legível
    - Rotação individual de cada número (mantém segurança)
    """
    
    def __init__(self):
        self.store = CaptchaStore()
        self._dev_mode = getattr(settings, 'DEBUG', False)
        
        # ============================================================
        # 🔥 CONFIGURAÇÃO DO CAPTCHA
        # ============================================================
        self.image_width = 600
        self.image_height = 220
        self.font_size = 180
        
        # 🔥 ESPAÇAMENTO FIXO ENTRE CARACTERES (evita colagem)
        self.char_spacing = 35  # Espaço extra entre números
        
        # 🔥 ROTAÇÃO MÍNIMA (segurança sem prejudicar legibilidade)
        self.rotation_range = (-8, 8)  # Graus de rotação aleatória
        
        # 🔥 PONTOS DE RUÍDO (splatters) em vez de linhas
        self.noise_points = 120  # Quantidade de pontos de ruído
        self.noise_color_range = (100, 200)  # Tons de cinza
        # ============================================================
        
        # Cache de imagens
        self._image_cache: Dict[str, Tuple[float, bytes]] = {}
        self._cache_ttl = 60
        self._max_cache = 100
        
        logger.info(f"🔢 CAPTCHA OTIMIZADO - NÚMEROS GIGANTES (fonte: {self.font_size}px)")
        logger.info(f"   📐 Dimensões: {self.image_width}x{self.image_height}")
        logger.info(f"   📏 Espaçamento: {self.char_spacing}px entre caracteres")
        logger.info(f"   🔄 Rotação: {self.rotation_range}")
        logger.info(f"   🎯 Ruído: {self.noise_points} pontos (sem linhas cortantes)")
        
        if self._dev_mode:
            logger.info("   🔧 Modo DEV: resposta '1234' aceita automaticamente")
    
    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        if client_ip in ["localhost", "::1", "::ffff:127.0.0.1"]:
            client_ip = "127.0.0.1"
        
        return client_ip
    
    def generate_number_code(self, length: int = 4) -> str:
        return ''.join(str(random.randint(0, 9)) for _ in range(length))
    
    def _draw_optimized_captcha(self, code: str) -> bytes:
        """
        🔥 VERSÃO OTIMIZADA:
        - Números GIGANTES ocupando todo o espaço
        - Espaçamento fixo entre caracteres
        - Pontos de ruído (sem linhas cortantes)
        - Rotação individual de cada número
        """
        if not PIL_AVAILABLE:
            return self._generate_svg_fallback(code)
        
        width = self.image_width
        height = self.image_height
        font_size = self.font_size
        
        # Cria imagem com fundo gradiente
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Fundo com gradiente mais escuro para contraste
        for i in range(height):
            r = int(80 + (i / height) * 80)
            g = int(100 + (i / height) * 50)
            b = int(200 - (i / height) * 80)
            draw.line([(0, i), (width, i)], fill=(r, g, b))
        
        # 🔥 1. PONTOS DE RUÍDO (em vez de linhas cortantes)
        for _ in range(self.noise_points):
            x = random.randint(0, width)
            y = random.randint(0, height)
            gray = random.randint(*self.noise_color_range)
            draw.point((x, y), fill=(gray, gray, gray))
        
        # 🔥 2. CARREGAR FONTE GIGANTE
        try:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # 🔥 3. CALCULAR ESPAÇAMENTO FIXO
        # Total de caracteres, largura disponível, margens
        total_chars = len(code)
        margin = 30  # Margem esquerda/direita
        
        # Calcula largura de cada caractere (aproximadamente)
        try:
            # Mede o caractere '0' como referência
            bbox = draw.textbbox((0, 0), '0', font=font)
            char_width = bbox[2] - bbox[0]
        except:
            char_width = font_size * 0.7
        
        # Largura total ocupada pelos caracteres + espaçamento
        total_width = (char_width * total_chars) + (self.char_spacing * (total_chars - 1))
        
        # Se não couber, reduz o espaçamento
        if total_width > width - (margin * 2):
            spacing = (width - (margin * 2) - (char_width * total_chars)) / (total_chars - 1)
            spacing = max(10, spacing)  # Espaçamento mínimo
        else:
            spacing = self.char_spacing
        
        # 🔥 4. DESENHAR CADA NÚMERO COM ROTAÇÃO INDIVIDUAL
        start_x = margin
        
        for i, char in enumerate(code):
            # Posição X com espaçamento fixo
            x = start_x + (i * (char_width + spacing))
            
            # Posição Y centralizada com pequena variação
            y = (height // 2) - (font_size // 2) + random.randint(-5, 5)
            
            # 🔥 ROTAÇÃO INDIVIDUAL (segurança sem prejudicar legibilidade)
            angle = random.randint(*self.rotation_range)
            
            # Criar imagem temporária para o caractere rotacionado
            try:
                # Tamanho do caractere
                bbox = draw.textbbox((0, 0), char, font=font)
                char_w = bbox[2] - bbox[0] + 10
                char_h = bbox[3] - bbox[1] + 10
            except:
                char_w = char_width + 10
                char_h = font_size + 10
            
            # Criar imagem temporária com fundo transparente
            char_img = Image.new('RGBA', (char_w, char_h), (0, 0, 0, 0))
            char_draw = ImageDraw.Draw(char_img)
            
            # Desenhar caractere na imagem temporária
            char_draw.text((5, 5), char, fill=(255, 255, 255, 255), font=font)
            
            # 🔥 CONTORNO PRETO (destaque)
            char_draw.text((3, 3), char, fill=(0, 0, 0, 255), font=font)
            char_draw.text((7, 3), char, fill=(0, 0, 0, 255), font=font)
            char_draw.text((3, 7), char, fill=(0, 0, 0, 255), font=font)
            char_draw.text((7, 7), char, fill=(0, 0, 0, 255), font=font)
            
            # Desenhar caractere principal (branco) por cima
            char_draw.text((5, 5), char, fill=(255, 255, 255, 255), font=font)
            
            # Rotacionar a imagem do caractere
            rotated = char_img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
            
            # Calcular posição para colar na imagem principal (centralizado)
            rot_w, rot_h = rotated.size
            paste_x = x - (rot_w // 2) + (char_w // 2)
            paste_y = y - (rot_h // 2) + (char_h // 2)
            
            # 🔥 PEGA O CANAL ALPHA (transparência) para colagem suave
            img.paste(rotated, (paste_x, paste_y), rotated)
            
            # 🔥 PEQUENO BRILHO/REFLEXO (efeito 3D) - texto branco translúcido
            try:
                glow_img = Image.new('RGBA', (char_w, char_h), (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow_img)
                glow_draw.text((3, 3), char, fill=(255, 255, 255, 80), font=font)
                glow_rotated = glow_img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
                img.paste(glow_rotated, (paste_x, paste_y), glow_rotated)
            except:
                pass
        
        # 🔥 5. DESFOQUE MÍNIMO (suaviza bordas)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.3))
        
        # Converte para bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG', optimize=True)
        img_bytes.seek(0)
        
        return img_bytes.getvalue()
    
    def _generate_svg_fallback(self, code: str) -> bytes:
        """SVG com números GIGANTES e espaçamento otimizado"""
        
        width = self.image_width
        height = self.image_height
        spacing = self.char_spacing
        
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4a6cf7" />
      <stop offset="100%" stop-color="#6c3cb0" />
    </linearGradient>
    <filter id="shadow">
      <feDropShadow dx="3" dy="3" stdDeviation="2" flood-color="black" flood-opacity="0.5"/>
    </filter>
  </defs>
  
  <rect width="{width}" height="{height}" fill="url(#bgGrad)" rx="16" ry="16"/>
  
  <!-- Pontos de ruído (em vez de linhas) -->
  <g fill="rgba(255,255,255,0.15)">
    {''.join(f'<circle cx="{random.randint(0, width)}" cy="{random.randint(0, height)}" r="{random.randint(1, 3)}" />' for _ in range(80))}
  </g>
  
  <!-- Números com espaçamento fixo -->
  <text x="{width // 2}" y="{height // 2 + 20}" 
        font-family="'Courier New', monospace" font-size="{self.font_size + 10}" font-weight="bold" 
        fill="white" text-anchor="middle" dominant-baseline="middle"
        letter-spacing="{spacing + 20}"
        filter="url(#shadow)">
    {code}
  </text>
</svg>'''
        
        return svg.encode('utf-8')
    
    async def generate_captcha_image_async(self, request: Request, session_type: str = "login") -> Tuple[bytes, str]:
        """Gera imagem CAPTCHA OTIMIZADA com números GIGANTES"""
        client_ip = self._get_client_ip(request)
        
        try:
            code = self.generate_number_code(4)
            img_bytes = self._draw_optimized_captcha(code)
            
            captcha_id = f"captcha_{secrets.token_urlsafe(12)}_{int(time.time())}"
            
            await self.store.add(captcha_id, code, client_ip, session_type)
            
            logger.debug(f"🔢 CAPTCHA otimizado gerado: {code} para {session_type}:{client_ip}")
            
            return img_bytes, captcha_id
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar CAPTCHA: {e}")
            code = "1234"
            svg = self._generate_svg_fallback(code)
            captcha_id = f"captcha_fallback_{secrets.token_urlsafe(8)}_{int(time.time())}"
            await self.store.add(captcha_id, code, client_ip, session_type)
            return svg, captcha_id
    
    async def validate_captcha_async(self, captcha_id: str, captcha_text: str,
                                      request: Request, session_type: str = "login") -> bool:
        """
        Valida resposta do CAPTCHA com RATE LIMIT
        🔥 Anti-brute force: máximo de 5 tentativas por IP/minuto
        """
        client_ip = self._get_client_ip(request)
        
        if self._dev_mode and captcha_text == "1234":
            logger.info("🔧 Modo DEV: resposta '1234' aceita")
            return True
        
        # 🔥 RATE LIMIT para validação de CAPTCHA (anti-brute force)
        rate_key = f"captcha_rate:{client_ip}:{session_type}"
        current_count = await rate_limiter.check_rate_limit(
            rate_key, 
            CAPTCHA_RATE_LIMIT, 
            CAPTCHA_RATE_WINDOW
        )
        
        if not current_count:
            logger.warning(f"🚨 Rate limit excedido para CAPTCHA - IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Muitas tentativas de CAPTCHA. Aguarde {CAPTCHA_RATE_WINDOW} segundos."
            )
        
        valid, message = await self.store.get_and_validate(
            captcha_id, captcha_text.strip(), client_ip, session_type
        )
        
        if valid:
            logger.info(f"✅ CAPTCHA válido para {session_type}:{client_ip}")
        else:
            logger.warning(f"❌ CAPTCHA inválido para {session_type}:{client_ip}: {message}")
        
        return valid
    
    def get_active_captcha(self, request: Request, session_type: str = "login") -> Optional[str]:
        client_ip = self._get_client_ip(request)
        return self.store.get_active_captcha_for_user(client_ip, session_type)
    
    def get_stats(self) -> Dict[str, Any]:
        return self.store.get_stats()


# ==============================================
# 5. RATE LIMITER
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
# 6. INSTÂNCIAS GLOBAIS
# ==============================================

hasher = Argon2Hasher()
jwt_manager = JWTManager()
captcha_manager = CaptchaManager()
rate_limiter = RateLimiter()
pow_manager = PoWManager()


# ==============================================
# 7. DEPENDÊNCIAS FASTAPI
# ==============================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = None
):
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
    
    payload = await jwt_manager.verify_token_async(token)
    if not payload:
        logger.warning("Token inválido ou expirado")
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


async def get_current_active_user(
    current_user = Depends(get_current_user)
):
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
    if not current_user.is_admin:
        logger.warning(f"Usuário {current_user.email} tentou acesso admin")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de administrador."
        )
    return current_user


async def get_current_manager_user(
    current_user = Depends(get_current_active_user)
):
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


async def check_captcha(request: Request, session_type: str = "login") -> bool:
    if captcha_manager._dev_mode:
        return True
    
    captcha_id = request.headers.get("X-Captcha-ID")
    captcha_text = request.headers.get("X-Captcha-Text")
    
    if not captcha_id or not captcha_text:
        try:
            body = await request.json()
            captcha_id = body.get("captcha_id") or body.get("captchaId")
            captcha_text = body.get("captcha_text") or body.get("captchaText")
        except:
            pass
    
    if not captcha_id or not captcha_text:
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA ID e resposta são obrigatórios"
        )
    
    valid = await captcha_manager.validate_captcha_async(captcha_id, captcha_text, request, session_type)
    
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Código incorreto! Digite os números que aparecem na imagem."
        )
    
    return True


# ==============================================
# 8. FUNÇÕES DE UTILIDADE
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
# 9. FUNÇÕES PARA COOKIES
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
# 10. FUNÇÃO DE LIMPEZA GLOBAL
# ==============================================

async def start_cleanup_tasks():
    """Inicia todas as tarefas de limpeza em background"""
    await captcha_manager.store.start_cleanup_loop()
    asyncio.create_task(pow_manager.cleanup_expired())
    logger.info("✅ Tarefas de limpeza em background iniciadas")


# ==============================================
# 11. EXPORTAÇÕES
# ==============================================

__all__ = [
    'hasher',
    'jwt_manager',
    'captcha_manager',
    'rate_limiter',
    'pow_manager',
    'oauth2_scheme',
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user',
    'get_current_manager_user',
    'check_captcha',
    'generate_api_key',
    'generate_reset_token',
    'hash_token',
    'verify_token_hash',
    'create_password_reset_token',
    'verify_password_reset_token',
    'set_auth_cookies',
    'clear_auth_cookies',
    'start_cleanup_tasks'
]

print("=" * 60)
print("✅ security.py carregado - CAPTCHA OTIMIZADO!")
print("   📐 Dimensões: 600x220")
print("   📝 Tamanho fonte: 180px (ocupando todo o espaço)")
print("   📏 Espaçamento fixo: 35px entre caracteres (evita colagem)")
print("   🔄 Rotação individual: -8° a +8°")
print("   🎯 Ruído: 120 pontos (sem linhas cortantes)")
print("   🛡️ Rate limit: 5 tentativas/minuto por IP")
print("🔢 PoW mantido apenas para upload de arquivos")
print("🔒 CAPTCHA Store isola sessões por tipo (login/register)")
print("=" * 60)