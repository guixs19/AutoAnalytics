# backend/security.py - VERSÃO COM CAPTCHA MATEMÁTICO (SOMA SIMPLES)
"""
MÓDULO CENTRAL DE SEGURANÇA
Ciclo de vida do CAPTCHA: 2 minutos, uso único
Refresh Token: Sistema completo de blacklist e invalidação
CAPTCHA: Desafio matemático de soma simples (ex: 5 + 3 = ?)
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
from threading import Timer

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
        logger.info(f"✅ Argon2 inicializado (time_cost={settings.ARGON2_TIME_COST})")
    
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
# 2. JWT COMPLETO COM REFRESH TOKEN
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
        
        # Cache de tokens recentemente blacklistados
        self._pending_blacklist = {}
        self._blacklist_lock = asyncio.Lock()
    
    async def init_redis(self):
        """Inicializa Redis de forma assíncrona (chamar no startup)"""
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
    
    async def verify_token_async(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        payload = self.verify_token(token, token_type)
        
        if not payload:
            return None
        
        jti = payload.get("jti")
        if jti and await self.is_token_blacklisted(jti):
            logger.warning(f"🔴 Token {jti[:8]}... está na blacklist")
            return None
        
        return payload
    
    async def refresh_access_token(self, refresh_token: str, db, old_access_token: str = None) -> Optional[Dict[str, str]]:
        """Refresh token com blacklist do token antigo"""
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
        
        # Blacklist do refresh token antigo
        old_jti = old_payload.get("jti")
        if old_jti:
            exp = old_payload.get("exp", 0)
            remaining = max(int(exp - datetime.utcnow().timestamp()), 3600)
            await self.blacklist_token(old_jti, remaining)
            logger.info(f"🔴 Refresh token antigo {old_jti[:8]}... blacklistado")
        
        # Blacklist do access token antigo
        if old_access_token:
            old_access_payload = self.verify_token(old_access_token, "access")
            if old_access_payload:
                old_access_jti = old_access_payload.get("jti")
                if old_access_jti:
                    remaining = max(int(old_access_payload.get("exp", 0) - datetime.utcnow().timestamp()), 300)
                    await self.blacklist_token(old_access_jti, remaining)
                    logger.info(f"🔴 Access token antigo {old_access_jti[:8]}... blacklistado")
        
        # Gerar novos tokens
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
        
        # Revogar token antigo no banco
        user.revoke_refresh_token()
        
        # Salvar novo refresh token
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
        """Logout com blacklist de ambos tokens"""
        from backend import crud
        
        # Blacklist do refresh token
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
        
        # Blacklist do access token
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
        """Adiciona token à blacklist"""
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
        """Verifica se token está na blacklist"""
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
# 3. CAPTCHA MANAGER - VERSÃO MATEMÁTICA (SOMA SIMPLES)
# ==============================================

class CaptchaSession:
    """Representa uma sessão de CAPTCHA para um usuário/IP"""
    
    def __init__(self, captcha_id: str, correct_answer: str, challenge_text: str, ip: str, expires_at: float):
        self.captcha_id = captcha_id
        self.correct_answer = correct_answer  # Armazena o resultado correto (ex: "8")
        self.challenge_text = challenge_text  # Armazena o desafio (ex: "5 + 3 = ?")
        self.ip = ip
        self.expires_at = expires_at
        self.used = False
        self.created_at = time.time()
        self.timer = None
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def time_remaining(self) -> int:
        return max(0, int(self.expires_at - time.time()))
    
    def cancel_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None


class CaptchaStore:
    """Armazenamento de CAPTCHAs matemáticos com ciclo de vida completo"""
    
    def __init__(self):
        self._store = {}
        self._user_sessions = {}
        self._cleanup_interval = 60
        self._last_cleanup = time.time()
        self._cleanup_task = None
    
    async def start_cleanup_loop(self):
        if self._cleanup_task is not None:
            return
        
        async def cleanup_loop():
            logger.info("🧹 Loop de limpeza do CAPTCHA matemático iniciado")
            while True:
                await asyncio.sleep(self._cleanup_interval)
                self._cleanup()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("✅ Cleanup loop do CAPTCHA agendado")
    
    async def stop_cleanup_loop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("🛑 Cleanup loop do CAPTCHA parado")
    
    def _get_user_key(self, ip: str, session_type: str = "login") -> str:
        return f"{session_type}:{ip}"
    
    def _cleanup(self):
        now = time.time()
        expired = []
        
        for cid, session in self._store.items():
            if session.is_expired():
                expired.append(cid)
                session.cancel_timer()
        
        for cid in expired:
            for user_key, session_cid in list(self._user_sessions.items()):
                if session_cid == cid:
                    del self._user_sessions[user_key]
            del self._store[cid]
        
        if expired:
            logger.info(f"🧹 {len(expired)} CAPTCHAS matemáticos expirados removidos")
        
        self._last_cleanup = now
    
    def _schedule_expiration(self, captcha_id: str, seconds: int):
        def expire_captcha():
            if captcha_id in self._store:
                session = self._store[captcha_id]
                if not session.used:
                    logger.info(f"⏰ CAPTCHA matemático {captcha_id[:8]}... expirou automaticamente após {seconds}s")
                    for user_key, session_cid in list(self._user_sessions.items()):
                        if session_cid == captcha_id:
                            del self._user_sessions[user_key]
                    del self._store[captcha_id]
        
        timer = Timer(seconds, expire_captcha)
        timer.daemon = True
        timer.start()
        
        if captcha_id in self._store:
            self._store[captcha_id].timer = timer
    
    def add(self, captcha_id: str, challenge_text: str, correct_answer: str, ip: str, session_type: str = "login") -> str:
        """Adiciona um novo desafio matemático"""
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        user_key = self._get_user_key(ip, session_type)
        
        # Remove CAPTCHA anterior do mesmo usuário
        if user_key in self._user_sessions:
            old_captcha_id = self._user_sessions[user_key]
            if old_captcha_id in self._store:
                old_session = self._store[old_captcha_id]
                old_session.cancel_timer()
                del self._store[old_captcha_id]
                logger.info(f"🔄 CAPTCHA anterior {old_captcha_id[:8]}... substituído")
        
        expires_at = time.time() + 120  # 2 minutos
        session = CaptchaSession(captcha_id, correct_answer, challenge_text, ip, expires_at)
        
        self._store[captcha_id] = session
        self._user_sessions[user_key] = captcha_id
        
        self._schedule_expiration(captcha_id, 120)
        
        logger.info(f"🧮 CAPTCHA matemático criado para IP {ip}: {challenge_text} = {correct_answer} (expira em 2min)")
        
        return captcha_id
    
    def get_and_validate(self, captcha_id: str, user_answer: str, ip: str, session_type: str = "login") -> Tuple[bool, str]:
        """Valida a resposta do desafio matemático"""
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        if captcha_id not in self._store:
            return False, "CAPTCHA não encontrado ou já expirou"
        
        session = self._store[captcha_id]
        user_key = self._get_user_key(ip, session_type)
        
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
        
        if user_key in self._user_sessions and self._user_sessions[user_key] != captcha_id:
            logger.warning(f"⚠️ Usuário {user_key} tentou usar CAPTCHA de outra sessão")
            return False, "Desafio não pertence à sua sessão atual"
        
        # Validação da resposta matemática
        user_answer_clean = user_answer.strip()
        
        if user_answer_clean != session.correct_answer:
            return False, f"Resposta incorreta! {session.challenge_text} não é {user_answer_clean}"
        
        # Sucesso - marcar como usado e remover
        session.used = True
        session.cancel_timer()
        
        if user_key in self._user_sessions:
            del self._user_sessions[user_key]
        
        del self._store[captcha_id]
        
        logger.info(f"✅ CAPTCHA matemático {captcha_id[:8]}... validado com sucesso! Resposta: {user_answer_clean}")
        
        return True, "Desafio resolvido corretamente"
    
    def get_active_captcha_for_user(self, ip: str, session_type: str = "login") -> Optional[str]:
        user_key = self._get_user_key(ip, session_type)
        captcha_id = self._user_sessions.get(user_key)
        
        if captcha_id and captcha_id in self._store:
            session = self._store[captcha_id]
            if not session.is_expired() and not session.used:
                return captcha_id
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        self._cleanup()
        return {
            "total_active": len(self._store),
            "total_sessions": len(self._user_sessions),
            "captcha_type": "mathematical_sum",
            "captchas": [
                {
                    "id": cid[:8] + "...",
                    "challenge": session.challenge_text,
                    "ip": session.ip,
                    "expires_in": session.time_remaining(),
                    "used": session.used,
                    "created_at": datetime.fromtimestamp(session.created_at).isoformat()
                }
                for cid, session in self._store.items()
            ]
        }


class CaptchaManager:
    """Gerenciador de CAPTCHA MATEMÁTICO - Desafio de soma simples (ex: 5 + 3 = ?)"""
    
    def __init__(self):
        self.store = CaptchaStore()
        self._dev_mode = settings.DEBUG
        logger.info("🧮 CAPTCHA Manager MATEMÁTICO inicializado (soma simples de 1+1 até 9+9)")
        if self._dev_mode:
            logger.info("   🔧 Modo DEV: resposta '9' aceita automaticamente (para testes)")
    
    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            return ip
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        if client_ip in ["localhost", "::1", "::ffff:127.0.0.1"]:
            client_ip = "127.0.0.1"
        
        return client_ip
    
    def generate_math_challenge(self) -> Tuple[str, str]:
        """
        Gera um desafio matemático de soma simples.
        
        Returns:
            Tuple[str, str]: (pergunta, resposta_correta)
            Exemplo: ("5 + 3 = ?", "8")
        """
        n1 = random.randint(1, 9)
        n2 = random.randint(1, 9)
        resultado = n1 + n2
        pergunta = f"{n1} + {n2} = ?"
        return pergunta, str(resultado)
    
    def _generate_svg_captcha(self, challenge_text: str) -> str:
        """
        Gera SVG com o desafio matemático em destaque.
        Design otimizado para mobile e fácil leitura.
        """
        # Configurações visuais
        width = 260
        height = 85
        
        # Cores aleatórias mas legíveis
        gradients = [
            ("#667eea", "#764ba2"),  # Roxo
            ("#48bb78", "#38a169"),  # Verde
            ("#4299e1", "#3182ce"),  # Azul
            ("#ed8936", "#dd6b20"),  # Laranja
            ("#e53e3e", "#c53030"),  # Vermelho
        ]
        grad1, grad2 = random.choice(gradients)
        
        # Efeitos de distorção (leves)
        rotation = random.randint(-2, 2)
        noise_density = random.randint(20, 40)
        
        # Escapar caracteres especiais
        challenge_escaped = challenge_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # Gerar ruído de fundo (pontos)
        noise = []
        for _ in range(noise_density):
            nx = random.randint(10, width - 10)
            ny = random.randint(10, height - 10)
            noise.append(f'<circle cx="{nx}" cy="{ny}" r="1.5" fill="rgba(255,255,255,0.25)"/>')
        
        # Linhas de distorção
        lines = []
        for _ in range(random.randint(2, 3)):
            x1 = random.randint(5, width // 2)
            y1 = random.randint(10, height - 10)
            x2 = random.randint(width // 2, width - 5)
            y2 = random.randint(10, height - 10)
            lines.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="rgba(255,255,255,0.2)" stroke-width="{random.randint(1, 2)}"/>'
            )
        
        # SVG completo com o desafio matemático
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{grad1};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{grad2};stop-opacity:1" />
    </linearGradient>
    <linearGradient id="shine" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:rgba(255,255,255,0.15)" />
      <stop offset="100%" style="stop-color:rgba(255,255,255,0)" />
    </linearGradient>
  </defs>
  
  <!-- Fundo gradiente -->
  <rect width="{width}" height="{height}" fill="url(#bgGrad)" rx="14" ry="14"/>
  
  <!-- Efeito de brilho -->
  <rect width="{width}" height="{height}" fill="url(#shine)" rx="14" ry="14"/>
  
  <!-- Ruído visual -->
  {''.join(noise)}
  
  <!-- Linhas de distorção -->
  {''.join(lines)}
  
  <!-- Círculos decorativos -->
  <circle cx="{width - 20}" cy="20" r="15" fill="rgba(255,255,255,0.08)"/>
  <circle cx="20" cy="{height - 20}" r="10" fill="rgba(255,255,255,0.08)"/>
  <circle cx="{width // 2}" cy="15" r="8" fill="rgba(255,255,255,0.06)"/>
  
  <!-- Texto do desafio matemático -->
  <text x="{width // 2}" y="{height // 2 + 8}" 
        font-family="'Courier New', 'Consolas', monospace" 
        font-size="34" 
        font-weight="bold" 
        fill="white" 
        text-anchor="middle"
        letter-spacing="3"
        dominant-baseline="middle"
        transform="rotate({rotation}, {width // 2}, {height // 2})">
    {challenge_escaped}
  </text>
  
  <!-- Borda sutil -->
  <rect width="{width - 2}" height="{height - 2}" x="1" y="1" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" rx="13" ry="13"/>
</svg>'''
        
        return svg
    
    def generate_captcha_image(self, request: Request, session_type: str = "login") -> Tuple[bytes, str]:
        """
        Gera CAPTCHA MATEMÁTICO ultrarrápido usando SVG.
        - Desafio: soma simples (ex: "5 + 3 = ?")
        - Resposta: resultado numérico (ex: "8")
        - Geração em menos de 5ms
        """
        client_ip = self._get_client_ip(request)
        
        try:
            # Gerar desafio matemático
            challenge_text, correct_answer = self.generate_math_challenge()
            
            # Criar SVG com o desafio
            svg = self._generate_svg_captcha(challenge_text)
            
            # Converter para bytes
            img_bytes = svg.encode('utf-8')
            
            # Gerar ID único
            captcha_id = f"math_{secrets.token_urlsafe(12)}_{int(time.time())}"
            
            # Armazenar no store (com a pergunta e resposta)
            self.store.add(captcha_id, challenge_text, correct_answer, client_ip, session_type)
            
            logger.info(f"🧮 CAPTCHA matemático gerado para IP {client_ip}: {challenge_text} = {correct_answer}")
            
            return img_bytes, captcha_id
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar CAPTCHA matemático: {e}")
            # Fallback em caso de erro
            return self._generate_fallback_captcha(client_ip, session_type)
    
    def _generate_fallback_captcha(self, ip: str, session_type: str) -> Tuple[bytes, str]:
        """Fallback simples em caso de erro (nunca deve acontecer)"""
        # Gerar desafio simples
        n1 = random.randint(1, 5)
        n2 = random.randint(1, 5)
        resultado = n1 + n2
        challenge = f"{n1} + {n2} = ?"
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="240" height="70">
            <rect width="240" height="70" fill="#667eea" rx="12" ry="12"/>
            <text x="120" y="45" font-family="monospace" font-size="32" fill="white" text-anchor="middle" font-weight="bold">{challenge}</text>
            <rect x="2" y="2" width="236" height="66" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="1.5" rx="10" ry="10"/>
        </svg>'''
        
        captcha_id = f"math_fallback_{secrets.token_urlsafe(8)}_{int(time.time())}"
        self.store.add(captcha_id, challenge, str(resultado), ip, session_type)
        
        logger.info(f"📸 CAPTCHA matemático fallback gerado para IP {ip}: {challenge} = {resultado}")
        
        return svg.encode('utf-8'), captcha_id
    
    def validate_captcha(self, captcha_id: str, captcha_text: str, request: Request, session_type: str = "login") -> bool:
        """
        Valida a resposta do CAPTCHA matemático.
        - Verifica se a resposta do usuário é o resultado correto da soma
        - Consumo único (remove após uso)
        - Expiração automática após 2 minutos
        """
        client_ip = self._get_client_ip(request)
        
        logger.info(f"🔍 Validando CAPTCHA matemático - ID: {captcha_id[:12] if captcha_id else 'None'}..., IP: {client_ip}")
        
        # Modo DEV: aceitar '9' como resposta mágica
        if self._dev_mode and captcha_text == "9":
            logger.warning("🔧 Modo DEV: resposta '9' aceita automaticamente no CAPTCHA")
            return True
        
        # Limpar resposta (remover espaços)
        user_answer_clean = captcha_text.strip()
        
        valid, message = self.store.get_and_validate(captcha_id, user_answer_clean, client_ip, session_type)
        
        if valid:
            logger.info(f"✅ CAPTCHA matemático válido para IP {client_ip} - Resposta: {user_answer_clean}")
        else:
            logger.warning(f"❌ CAPTCHA matemático inválido para IP {client_ip}: {message}")
        
        return valid
    
    def validate_captcha_only(self, captcha_id: str, captcha_text: str, request: Request, session_type: str = "login") -> bool:
        """
        Valida CAPTCHA sem consumir (apenas verifica se é válido).
        Útil para pré-validação antes de operações custosas.
        """
        client_ip = self._get_client_ip(request)
        
        if self._dev_mode and captcha_text == "9":
            return True
        
        if captcha_id not in self.store._store:
            return False
        
        session = self.store._store[captcha_id]
        
        if session.is_expired():
            return False
        
        if session.used:
            return False
        
        user_answer_clean = captcha_text.strip()
        
        if user_answer_clean != session.correct_answer:
            return False
        
        return True
    
    def get_active_captcha(self, request: Request, session_type: str = "login") -> Optional[str]:
        client_ip = self._get_client_ip(request)
        return self.store.get_active_captcha_for_user(client_ip, session_type)
    
    def get_stats(self) -> Dict[str, Any]:
        return self.store.get_stats()


# ==============================================
# 4. RATE LIMITER
# ==============================================

class RateLimiter:
    """Rate limiting - Previne abuso da API"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self._last_cleanup = datetime.now().timestamp()
        self._redis_initialized = False
    
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
            logger.warning(f"⚠️ Redis não disponível para rate limiting: {e}")
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
                
                current = result[0]
                
                if current <= max_requests:
                    return True
                else:
                    logger.warning(f"Rate limit excedido - {key}: {current}/{max_requests}")
                    return False
                
            except Exception as e:
                logger.error(f"Erro no Redis rate limit: {e}")
        
        if now - self._last_cleanup > 60:
            self._cleanup_memory_cache()
            self._last_cleanup = now
        
        if key not in self.memory_cache:
            self.memory_cache[key] = []
        
        self.memory_cache[key] = [t for t in self.memory_cache[key] if t > now - window]
        
        if len(self.memory_cache[key]) >= max_requests:
            logger.warning(f"Rate limit excedido (memória) - {key}")
            return False
        
        self.memory_cache[key].append(now)
        return True
    
    def _cleanup_memory_cache(self):
        now = datetime.now().timestamp()
        to_delete = []
        
        for key, timestamps in self.memory_cache.items():
            self.memory_cache[key] = [t for t in timestamps if t > now - 3600]
            if not self.memory_cache[key]:
                to_delete.append(key)
        
        for key in to_delete:
            del self.memory_cache[key]


# ==============================================
# 5. INSTÂNCIAS GLOBAIS
# ==============================================

hasher = Argon2Hasher()
jwt_manager = JWTManager()
captcha_manager = CaptchaManager()
rate_limiter = RateLimiter()

# ==============================================
# 6. DEPENDÊNCIAS FASTAPI
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
        
        if user.is_admin:
            logger.info(f"👑 Admin logado: {user.email}")
        
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
        logger.debug("🔧 Modo DEV: CAPTCHA ignorado")
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
        logger.warning("CAPTCHA ID ou texto não fornecido")
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA ID e resposta são obrigatórios"
        )
    
    valid = captcha_manager.validate_captcha(captcha_id, captcha_text, request, session_type)
    
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Resposta do desafio matemático incorreta ou expirada"
        )
    
    return True


# ==============================================
# 7. FUNÇÕES DE UTILIDADE
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
# 8. FUNÇÕES PARA COOKIES
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
    
    logger.info("🍪 Cookies de autenticação definidos")
    return response

def clear_auth_cookies(response: Response):
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=0,
        path="/"
    )
    
    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=0,
        path="/"
    )
    
    logger.info("🍪 Cookies de autenticação removidos")
    return response


# ==============================================
# 9. EXPORTAÇÕES
# ==============================================

__all__ = [
    'hasher',
    'jwt_manager',
    'captcha_manager',
    'rate_limiter',
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
    'clear_auth_cookies'
]