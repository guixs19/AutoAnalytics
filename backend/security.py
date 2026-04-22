# backend/security.py - VERSÃO CORRIGIDA (SEM LOOP INFINITO NO INIT)
"""
MÓDULO CENTRAL DE SEGURANÇA
Ciclo de vida do CAPTCHA:
1. Geração → 2 minutos de validade
2. Se usuário gerar novo → anterior é desativado automaticamente
3. Expiração automática após 2 minutos
4. Uso único (valida e remove)
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
# 2. JWT COMPLETO COM REFRESH TOKEN (VERSÃO CORRIGIDA)
# ==============================================

class JWTManager:
    """Gerenciador de JWT com Redis opcional"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        self.redis_client = None
        self.memory_blacklist = set()
        self._redis_initialized = False  # ✅ Flag para evitar múltiplas tentativas
    
    async def init_redis(self):
        """✅ Inicializa Redis de forma assíncrona (chamar no startup)"""
        if self._redis_initialized:
            return
        
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2,
                retry_on_timeout=True
            )
            # Testar conexão
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
            logger.warning(f"Token {jti} está na blacklist")
            return None
        
        return payload
    
    async def refresh_access_token(self, refresh_token: str, db) -> Optional[Dict[str, str]]:
        from backend import crud
        
        payload = await self.verify_token_async(refresh_token, "refresh")
        
        if not payload:
            logger.warning("Refresh token inválido ou expirado")
            return None
        
        email = payload.get("sub") or payload.get("email")
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
        
        user_data = {
            "sub": user.email,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
            "credits": user.credits,
            "is_admin": user.is_admin
        }
        
        user.revoke_refresh_token()
        
        new_tokens = self.create_token_pair(user_data)
        
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
        from backend import crud
        
        payload = await self.verify_token_async(refresh_token, "refresh")
        if not payload:
            return False
        
        email = payload.get("sub") or payload.get("email")
        if not email:
            return False
        
        user = crud.get_user_by_email(db, email)
        
        if user and user.validate_refresh_token(refresh_token):
            user.revoke_refresh_token()
            
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
        if not auth_header:
            return None
        
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "").strip()
        
        if auth_header.startswith("JWT "):
            return auth_header.replace("JWT ", "").strip()
        
        return auth_header.strip()

# ==============================================
# 3. CAPTCHA MANAGER - CICLO DE VIDA COMPLETO (VERSÃO CORRIGIDA)
# ==============================================

class CaptchaSession:
    """Representa uma sessão de CAPTCHA para um usuário/IP"""
    
    def __init__(self, captcha_id: str, text: str, ip: str, expires_at: float):
        self.captcha_id = captcha_id
        self.text = text
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
    """
    Armazenamento de CAPTCHAs com ciclo de vida completo:
    ✅ Geração com expiração de 2 minutos
    ✅ Se usuário gerar novo, o anterior é desativado automaticamente
    ✅ Timer automático para expiração
    ✅ Uso único (valida e remove)
    
    🔥 CORRIGIDO: NÃO inicia loop infinito no __init__
    """
    
    def __init__(self):
        self._store = {}  # {captcha_id: CaptchaSession}
        self._user_sessions = {}  # {user_key: captcha_id} - Para rastrear sessão ativa do usuário
        self._cleanup_interval = 60
        self._last_cleanup = time.time()
        self._cleanup_task = None  # ✅ Referência para a task de cleanup
        # ❌ NÃO inicia loop aqui - será iniciado no startup do FastAPI
    
    async def start_cleanup_loop(self):
        """✅ Inicia loop de limpeza - DEVE SER CHAMADO NO STARTUP DO FASTAPI"""
        if self._cleanup_task is not None:
            logger.warning("Cleanup loop já está rodando")
            return
        
        async def cleanup_loop():
            logger.info("🧹 Loop de limpeza do CAPTCHA iniciado")
            while True:
                await asyncio.sleep(self._cleanup_interval)
                self._cleanup()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("✅ Cleanup loop do CAPTCHA agendado")
    
    async def stop_cleanup_loop(self):
        """Para o loop de limpeza (para shutdown graceful)"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("🛑 Cleanup loop do CAPTCHA parado")
    
    def _get_user_key(self, ip: str, session_type: str = "login") -> str:
        """Gera chave única para o usuário"""
        return f"{session_type}:{ip}"
    
    def _cleanup(self):
        """Remove CAPTCHAS expirados"""
        now = time.time()
        expired = []
        
        for cid, session in self._store.items():
            if session.is_expired():
                expired.append(cid)
                session.cancel_timer()
        
        for cid in expired:
            # Remover referência da sessão do usuário
            for user_key, session_cid in list(self._user_sessions.items()):
                if session_cid == cid:
                    del self._user_sessions[user_key]
            del self._store[cid]
        
        if expired:
            logger.info(f"🧹 {len(expired)} CAPTCHAS expirados removidos")
        
        self._last_cleanup = now
    
    def _schedule_expiration(self, captcha_id: str, seconds: int):
        """Agenda expiração automática do CAPTCHA"""
        def expire_captcha():
            if captcha_id in self._store:
                session = self._store[captcha_id]
                if not session.used:
                    logger.info(f"⏰ CAPTCHA {captcha_id[:8]}... expirou automaticamente após {seconds}s")
                    # Remover referência da sessão do usuário
                    for user_key, session_cid in list(self._user_sessions.items()):
                        if session_cid == captcha_id:
                            del self._user_sessions[user_key]
                    del self._store[captcha_id]
        
        timer = Timer(seconds, expire_captcha)
        timer.daemon = True
        timer.start()
        
        if captcha_id in self._store:
            self._store[captcha_id].timer = timer
    
    def add(self, captcha_id: str, text: str, ip: str, session_type: str = "login") -> str:
        """
        Adiciona novo CAPTCHA
        Se já existir um CAPTCHA ativo para este usuário, ele é DESATIVADO automaticamente
        Retorna o ID do novo CAPTCHA
        """
        # Limpar antes de adicionar
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        user_key = self._get_user_key(ip, session_type)
        
        # 🔥 SE JÁ EXISTE UM CAPTCHA ATIVO PARA ESTE USUÁRIO, DESATIVAR
        if user_key in self._user_sessions:
            old_captcha_id = self._user_sessions[user_key]
            if old_captcha_id in self._store:
                old_session = self._store[old_captcha_id]
                old_session.cancel_timer()
                del self._store[old_captcha_id]
                logger.info(f"🔄 CAPTCHA anterior {old_captcha_id[:8]}... desativado (novo CAPTCHA gerado para IP {ip})")
        
        # Criar nova sessão
        expires_at = time.time() + 120  # 2 MINUTOS EXATOS
        session = CaptchaSession(captcha_id, text, ip, expires_at)
        
        self._store[captcha_id] = session
        self._user_sessions[user_key] = captcha_id
        
        # Agendar expiração automática
        self._schedule_expiration(captcha_id, 120)
        
        logger.info(f"✅ CAPTCHA criado para IP {ip}: {captcha_id[:8]}... (expira em 2min)")
        logger.info(f"   Sessão ativa do usuário: {user_key} -> {captcha_id[:8]}...")
        
        return captcha_id
    
    def get_and_validate(self, captcha_id: str, user_input: str, ip: str, session_type: str = "login") -> Tuple[bool, str]:
        """
        Valida CAPTCHA com todas as regras:
        ✅ Expiração de 2 minutos
        ✅ Uso único
        ✅ Mesmo IP (opcional, mais flexível)
        """
        # Limpar antes de validar
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        # Verificar se existe
        if captcha_id not in self._store:
            return False, "CAPTCHA não encontrado ou já expirou"
        
        session = self._store[captcha_id]
        user_key = self._get_user_key(ip, session_type)
        
        # VERIFICAÇÃO 1: EXPIRAÇÃO (2 minutos)
        if session.is_expired():
            # Remover da sessão do usuário
            if user_key in self._user_sessions and self._user_sessions[user_key] == captcha_id:
                del self._user_sessions[user_key]
            del self._store[captcha_id]
            return False, "CAPTCHA expirado (2 minutos)"
        
        # VERIFICAÇÃO 2: USO ÚNICO
        if session.used:
            if user_key in self._user_sessions and self._user_sessions[user_key] == captcha_id:
                del self._user_sessions[user_key]
            del self._store[captcha_id]
            return False, "CAPTCHA já foi utilizado"
        
        # VERIFICAÇÃO 3: MESMA SESSÃO (o CAPTCHA pertence a este usuário/IP)
        if user_key in self._user_sessions and self._user_sessions[user_key] != captcha_id:
            logger.warning(f"⚠️ Usuário {user_key} tentou usar CAPTCHA de outra sessão")
            return False, "CAPTCHA não pertence à sua sessão atual"
        
        # VERIFICAÇÃO 4: TEXTO CORRETO (case insensitive)
        if session.text.lower() != user_input.lower().strip():
            return False, "Texto incorreto"
        
        # ✅ TUDO VÁLIDO! Marcar como usado e remover
        session.used = True
        session.cancel_timer()
        
        # Remover da sessão do usuário
        if user_key in self._user_sessions:
            del self._user_sessions[user_key]
        
        # Remover do store
        del self._store[captcha_id]
        
        logger.info(f"✅ CAPTCHA {captcha_id[:8]}... validado com sucesso e removido")
        
        return True, "CAPTCHA válido"
    
    def get_active_captcha_for_user(self, ip: str, session_type: str = "login") -> Optional[str]:
        """Retorna o CAPTCHA ativo para um usuário, se existir"""
        user_key = self._get_user_key(ip, session_type)
        captcha_id = self._user_sessions.get(user_key)
        
        if captcha_id and captcha_id in self._store:
            session = self._store[captcha_id]
            if not session.is_expired() and not session.used:
                return captcha_id
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do store (para debug/admin)"""
        self._cleanup()
        return {
            "total_active": len(self._store),
            "total_sessions": len(self._user_sessions),
            "captchas": [
                {
                    "id": cid[:8] + "...",
                    "ip": session.ip,
                    "expires_in": session.time_remaining(),
                    "used": session.used,
                    "created_at": datetime.fromtimestamp(session.created_at).isoformat()
                }
                for cid, session in self._store.items()
            ]
        }


class CaptchaManager:
    """
    Gerenciador de CAPTCHA próprio - CICLO DE VIDA COMPLETO
    
    Ciclo de vida:
    1. Usuário solicita CAPTCHA → Gera imagem e texto, armazena por 2 minutos
    2. Se usuário solicitar NOVO CAPTCHA → Anterior é DESATIVADO automaticamente
    3. Após 2 minutos → CAPTCHA expira e é removido automaticamente
    4. Usuário envia formulário → CAPTCHA é validado e removido (uso único)
    """
    
    def __init__(self):
        self.store = CaptchaStore()
        self._dev_mode = settings.DEBUG
        logger.info("✅ CAPTCHA Manager inicializado - Ciclo de vida: 2 minutos, uso único")
        logger.info("   🔄 Novo CAPTCHA desativa automaticamente o anterior")
        if self._dev_mode:
            logger.info("   🔧 Modo DEV: Verificação de IP desabilitada")
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Obtém IP do cliente de forma robusta
        Suporta proxies, localhost, IPv4, IPv6
        """
        # Tentar headers de proxy primeiro
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            logger.debug(f"IP via X-Forwarded-For: {ip}")
            return ip
        
        # Tentar header Real-IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            logger.debug(f"IP via X-Real-IP: {real_ip}")
            return real_ip
        
        # Fallback para client.host
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        # Normalizar localhost
        if client_ip in ["localhost", "::1", "::ffff:127.0.0.1"]:
            client_ip = "127.0.0.1"
        
        logger.debug(f"IP via client.host: {client_ip}")
        return client_ip
    
    def generate_captcha_image(self, request: Request, session_type: str = "login") -> Tuple[bytes, str]:
        """
        Gera imagem CAPTCHA e retorna (bytes_imagem, captcha_id)
        
        🔥 CICLO DE VIDA:
        - Gera novo CAPTCHA
        - Se já existia um CAPTCHA ativo para este usuário, ele é DESATIVADO
        - O novo CAPTCHA será válido por 2 minutos
        """
        # Extrair IP do cliente
        client_ip = self._get_client_ip(request)
        
        try:
            # Tentar importar PIL (Pillow)
            try:
                from PIL import Image, ImageDraw, ImageFont, ImageFilter
                PIL_AVAILABLE = True
            except ImportError:
                logger.warning("⚠️ Pillow não instalado. Usando gerador simples.")
                PIL_AVAILABLE = False
            
            if PIL_AVAILABLE:
                return self._generate_image_with_pillow(client_ip, session_type)
            else:
                return self._generate_simple_image(client_ip, session_type)
                
        except Exception as e:
            logger.error(f"❌ Erro ao gerar imagem CAPTCHA: {e}")
            return self._generate_simple_image(client_ip, session_type)
    
    def _generate_image_with_pillow(self, ip: str, session_type: str) -> Tuple[bytes, str]:
        """Gera imagem CAPTCHA usando Pillow"""
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        
        # Gerar texto aleatório (6 dígitos)
        captcha_text = ''.join(random.choices(string.digits, k=6))
        
        width, height = 200, 70
        
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        
        # Ruído de fundo
        for _ in range(200):
            x = random.randint(0, width)
            y = random.randint(0, height)
            color = (random.randint(200, 255), random.randint(200, 255), random.randint(200, 255))
            draw.point((x, y), fill=color)
        
        # Linhas onduladas
        for i in range(3):
            x1 = random.randint(0, width // 3)
            y1 = random.randint(0, height)
            x2 = random.randint(width // 2, width)
            y2 = random.randint(0, height)
            draw.line([(x1, y1), (x2, y2)], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=1)
        
        # Desenhar texto
        try:
            font = ImageFont.load_default()
        except:
            font = None
        
        for i, char in enumerate(captcha_text):
            x = 25 + i * 25
            y = 20 + random.randint(-5, 5)
            color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
            
            if font:
                draw.text((x, y), char, fill=color, font=font)
            else:
                draw.text((x, y), char, fill=color)
        
        # Aplicar blur
        image = image.filter(ImageFilter.GaussianBlur(radius=0.5))
        
        # Converter para bytes
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Gerar ID único e armazenar (isso DESATIVA o CAPTCHA anterior)
        captcha_id = secrets.token_urlsafe(16)
        self.store.add(captcha_id, captcha_text, ip, session_type)
        
        logger.info(f"📸 CAPTCHA gerado com Pillow para IP {ip}: {captcha_text}")
        
        return img_bytes, captcha_id
    
    def _generate_simple_image(self, ip: str, session_type: str) -> Tuple[bytes, str]:
        """Gera imagem CAPTCHA simples sem Pillow (fallback)"""
        captcha_text = ''.join(random.choices(string.digits, k=6))
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="70">
            <rect width="200" height="70" fill="#f0f0f0" rx="10" ry="10"/>
            <text x="30" y="45" font-family="Arial" font-size="30" fill="#333">{captcha_text}</text>
            <line x1="10" y1="20" x2="190" y2="50" stroke="#999" stroke-width="1"/>
            <line x1="20" y1="60" x2="180" y2="30" stroke="#999" stroke-width="1"/>
        </svg>'''
        
        img_bytes = svg.encode('utf-8')
        
        captcha_id = secrets.token_urlsafe(16)
        self.store.add(captcha_id, captcha_text, ip, session_type)
        
        logger.info(f"📸 CAPTCHA gerado (simples) para IP {ip}: {captcha_text}")
        
        return img_bytes, captcha_id
    
    def validate_captcha(self, captcha_id: str, captcha_text: str, request: Request, session_type: str = "login") -> bool:
        """
        Valida CAPTCHA com todas as regras do ciclo de vida:
        ✅ Expiração de 2 minutos
        ✅ Uso único
        ✅ Sessão ativa do usuário
        """
        # Extrair IP do cliente
        client_ip = self._get_client_ip(request)
        
        # 🔍 DEBUG: Log detalhado
        logger.info(f"🔍 Validando CAPTCHA - ID: {captcha_id[:8] if captcha_id else 'None'}..., IP: {client_ip}, Texto: {captcha_text}")
        
        # Se estiver em modo desenvolvimento e captcha for 123456, aceitar automaticamente
        if self._dev_mode and captcha_text == "123456":
            logger.warning("🔧 Modo DEV: CAPTCHA 123456 aceito automaticamente")
            return True
        
        valid, message = self.store.get_and_validate(captcha_id, captcha_text, client_ip, session_type)
        
        if valid:
            logger.info(f"✅ CAPTCHA válido para IP {client_ip}")
        else:
            logger.warning(f"❌ CAPTCHA inválido para IP {client_ip}: {message}")
        
        return valid
    
    def get_active_captcha(self, request: Request, session_type: str = "login") -> Optional[str]:
        """Retorna o CAPTCHA ativo para o usuário, se existir"""
        client_ip = self._get_client_ip(request)
        return self.store.get_active_captcha_for_user(client_ip, session_type)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas (para admin)"""
        return self.store.get_stats()

# ==============================================
# 4. RATE LIMITER (VERSÃO CORRIGIDA)
# ==============================================

class RateLimiter:
    """Rate limiting - Previne abuso da API"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self._last_cleanup = datetime.now().timestamp()
        self._redis_initialized = False
    
    async def init_redis(self):
        """✅ Inicializa Redis de forma assíncrona"""
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
        
        # Fallback em memória
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
    """
    Dependência para verificar CAPTCHA
    Uso: captcha_valid: bool = Depends(check_captcha)
    """
    # Modo desenvolvimento
    if captcha_manager._dev_mode:
        logger.debug("🔧 Modo DEV: CAPTCHA ignorado")
        return True
    
    # Pegar ID e texto do header/body
    captcha_id = request.headers.get("X-Captcha-ID")
    captcha_text = request.headers.get("X-Captcha-Text")
    
    # Tentar pegar do body
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
            detail="CAPTCHA ID e texto são obrigatórios"
        )
    
    # Validar CAPTCHA
    valid = captcha_manager.validate_captcha(captcha_id, captcha_text, request, session_type)
    
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA inválido ou expirado"
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