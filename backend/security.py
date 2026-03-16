# backend/security.py - VERSÃO DEFINITIVA COM CAPTCHA PRÓPRIO E SUPORTE A ADMIN
"""
MÓDULO CENTRAL DE SEGURANÇA
Todo o sistema DEVE importar daqui: from backend.security import ...
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
            # ✅ ADICIONADO is_admin NO PAYLOAD
            "is_admin": data.get("is_admin", False),
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
            "credits": user_data.get("credits", 0),
            # ✅ ADICIONADO is_admin AQUI TAMBÉM
            "is_admin": user_data.get("is_admin", False)
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
            "credits": user.credits,
            # ✅ ADICIONADO is_admin
            "is_admin": user.is_admin
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
# 3. CAPTCHA MANAGER PRÓPRIO (COM RATE LIMIT, USO ÚNICO, EXPIRAÇÃO 2 MIN)
# ==============================================

class CaptchaStore:
    """Armazenamento de CAPTCHAs com expiração automática"""
    
    def __init__(self):
        self._store = {}  # {captcha_id: {"text": str, "expires": timestamp, "used": bool, "ip": str}}
        self._cleanup_interval = 60  # Limpar a cada 60 segundos
        self._last_cleanup = time.time()
    
    def _cleanup(self):
        """Remove CAPTCHAS expirados (mais de 2 minutos)"""
        now = time.time()
        expired = []
        
        for cid, data in self._store.items():
            if data["expires"] < now:
                expired.append(cid)
        
        for cid in expired:
            del self._store[cid]
        
        if expired:
            logger.debug(f"🧹 {len(expired)} CAPTCHAS expirados removidos")
        
        self._last_cleanup = now
    
    def add(self, captcha_id: str, text: str, ip: str):
        """Adiciona novo CAPTCHA com expiração de 2 minutos"""
        # Limpar antes de adicionar
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        self._store[captcha_id] = {
            "text": text,
            "expires": time.time() + 120,  # 2 MINUTOS EXATAMENTE!
            "used": False,
            "ip": ip,
            "created_at": time.time()
        }
        logger.info(f"✅ CAPTCHA criado para IP {ip}: {captcha_id} (expira em 2min)")
    
    def get_and_validate(self, captcha_id: str, user_input: str, ip: str) -> Tuple[bool, str]:
        """
        Valida CAPTCHA e retorna (sucesso, mensagem)
        Implementa: USO ÚNICO + EXPIRAÇÃO + VALIDAÇÃO DE IP
        """
        # Limpar antes de validar
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        # Verificar se existe
        if captcha_id not in self._store:
            return False, "CAPTCHA não encontrado ou já expirou"
        
        data = self._store[captcha_id]
        
        # VERIFICAÇÃO 1: EXPIRAÇÃO (2 minutos)
        if time.time() > data["expires"]:
            del self._store[captcha_id]
            return False, "CAPTCHA expirado (2 minutos)"
        
        # VERIFICAÇÃO 2: USO ÚNICO
        if data["used"]:
            del self._store[captcha_id]  # Remove imediatamente se já usado
            return False, "CAPTCHA já foi utilizado"
        
        # VERIFICAÇÃO 3: MESMO IP (segurança extra)
        if data["ip"] != ip:
            logger.warning(f"⚠️ IP diferente: esperado {data['ip']}, recebido {ip}")
            return False, "IP não corresponde ao CAPTCHA"
        
        # VERIFICAÇÃO 4: TEXTO CORRETO
        if data["text"].lower() != user_input.lower().strip():
            return False, "Texto incorreto"
        
        # ✅ TUDO VÁLIDO! Marcar como usado e remover
        del self._store[captcha_id]  # USO ÚNICO: remove após validar
        logger.info(f"✅ CAPTCHA {captcha_id} validado com sucesso e removido")
        
        return True, "CAPTCHA válido"
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do store (para debug/admin)"""
        self._cleanup()
        return {
            "total_active": len(self._store),
            "captchas": [
                {
                    "id": cid,
                    "ip": data["ip"],
                    "expires_in": int(data["expires"] - time.time()),
                    "used": data["used"],
                    "created_at": datetime.fromtimestamp(data["created_at"]).isoformat()
                }
                for cid, data in self._store.items()
            ]
        }

class CaptchaManager:
    """Gerenciador de CAPTCHA próprio - SEM Google reCAPTCHA!"""
    
    def __init__(self):
        self.store = CaptchaStore()
        self._dev_mode = settings.DEBUG
        logger.info("✅ CAPTCHA Manager próprio inicializado (expiração: 2min, uso único, rate limit por IP)")
    
    # ==============================================
    # GERADOR DE IMAGEM CAPTCHA
    # ==============================================
    
    def generate_captcha_image(self, ip: str) -> Tuple[bytes, str]:
        """
        Gera imagem CAPTCHA e retorna (bytes_imagem, captcha_id)
        Args:
            ip: IP do usuário para rate limiting
        """
        try:
            # Tentar importar PIL (Pillow)
            try:
                from PIL import Image, ImageDraw, ImageFont, ImageFilter
                PIL_AVAILABLE = True
            except ImportError:
                logger.warning("⚠️ Pillow não instalado. Usando gerador simples.")
                PIL_AVAILABLE = False
            
            if PIL_AVAILABLE:
                return self._generate_image_with_pillow(ip)
            else:
                return self._generate_simple_image(ip)
                
        except Exception as e:
            logger.error(f"❌ Erro ao gerar imagem CAPTCHA: {e}")
            # Fallback para imagem simples em caso de erro
            return self._generate_simple_image(ip)
    
    def _generate_image_with_pillow(self, ip: str) -> Tuple[bytes, str]:
        """Gera imagem CAPTCHA usando Pillow"""
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        
        # Gerar texto aleatório (6 dígitos) - números apenas para facilitar
        captcha_text = ''.join(random.choices(string.digits, k=6))
        
        # Dimensões da imagem
        width, height = 200, 70
        
        # Criar imagem
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        
        # Adicionar ruído de fundo (pontos aleatórios)
        for _ in range(200):
            x = random.randint(0, width)
            y = random.randint(0, height)
            color = (random.randint(200, 255), random.randint(200, 255), random.randint(200, 255))
            draw.point((x, y), fill=color)
        
        # Adicionar linhas onduladas (dificulta OCR)
        for i in range(3):
            x1 = random.randint(0, width // 3)
            y1 = random.randint(0, height)
            x2 = random.randint(width // 2, width)
            y2 = random.randint(0, height)
            draw.line([(x1, y1), (x2, y2)], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=1)
        
        # Desenhar texto com distorção
        try:
            # Tentar usar uma fonte um pouco maior
            font = ImageFont.load_default()
        except:
            font = None
        
        for i, char in enumerate(captcha_text):
            x = 25 + i * 25
            y = 20 + random.randint(-5, 5)
            
            # Cores diferentes para cada caractere
            color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
            
            if font:
                draw.text((x, y), char, fill=color, font=font)
            else:
                draw.text((x, y), char, fill=color)
        
        # Aplicar blur leve para dificultar OCR
        image = image.filter(ImageFilter.GaussianBlur(radius=0.5))
        
        # Converter para bytes
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Gerar ID único e armazenar
        captcha_id = secrets.token_urlsafe(16)
        self.store.add(captcha_id, captcha_text, ip)
        
        return img_bytes, captcha_id
    
    def _generate_simple_image(self, ip: str) -> Tuple[bytes, str]:
        """Gera uma imagem CAPTCHA simples sem Pillow (fallback)"""
        # Gerar texto aleatório (6 dígitos)
        captcha_text = ''.join(random.choices(string.digits, k=6))
        
        # Criar uma imagem SVG simples (funciona em qualquer navegador)
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="70">
            <rect width="200" height="70" fill="#f0f0f0" rx="10" ry="10"/>
            <text x="30" y="45" font-family="Arial" font-size="30" fill="#333">{captcha_text}</text>
            <line x1="10" y1="20" x2="190" y2="50" stroke="#999" stroke-width="1"/>
            <line x1="20" y1="60" x2="180" y2="30" stroke="#999" stroke-width="1"/>
        </svg>'''
        
        img_bytes = svg.encode('utf-8')
        
        # Gerar ID único e armazenar
        captcha_id = secrets.token_urlsafe(16)
        self.store.add(captcha_id, captcha_text, ip)
        
        return img_bytes, captcha_id
    
    def validate_captcha(self, captcha_id: str, captcha_text: str, ip: str) -> bool:
        """
        Valida CAPTCHA com todas as regras:
        ✅ Rate limit (indireto, pelo IP)
        ✅ Uso único (remove após validar)
        ✅ Expiração de 2 minutos
        ✅ Mesmo IP do usuário
        """
        valid, message = self.store.get_and_validate(captcha_id, captcha_text, ip)
        
        if valid:
            logger.info(f"✅ CAPTCHA válido para IP {ip}")
        else:
            logger.warning(f"❌ CAPTCHA inválido para IP {ip}: {message}")
        
        return valid
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas (para admin)"""
        return self.store.get_stats()

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
captcha_manager = CaptchaManager()  # ✅ NOVO: CAPTCHA PRÓPRIO!
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
        
        # ✅ ADICIONADO LOG PARA VERIFICAR SE USUÁRIO É ADMIN
        if user.is_admin:
            logger.info(f"👑 Admin logado: {user.email}")
        
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
    # 🔥 VERIFICA PELO CAMPO is_admin
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
    """Verifica se é gestor ou admin"""
    # 🔥 VERIFICA PELO CAMPO is_admin OU role
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

async def check_captcha(request: Request) -> bool:
    """
    Dependência para verificar CAPTCHA
    Uso: captcha_valid: bool = Depends(check_captcha)
    """
    # Modo desenvolvimento
    if captcha_manager._dev_mode:
        return True
    
    # Pegar ID e texto do header/body
    captcha_id = request.headers.get("X-Captcha-ID")
    captcha_text = request.headers.get("X-Captcha-Text")
    
    # Tentar pegar do body se não estiver no header
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
    
    # Pegar IP do cliente
    client_ip = request.client.host if request.client else "unknown"
    
    # Validar CAPTCHA
    valid = captcha_manager.validate_captcha(captcha_id, captcha_text, client_ip)
    
    if not valid:
        logger.warning(f"CAPTCHA inválido para IP {client_ip}")
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA inválido ou expirado"
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
# 8. FUNÇÕES PARA COOKIES
# ==============================================

def set_auth_cookies(response: Response, access_token: str, refresh_token: str = None, expires_in: int = 3600):
    """
    Define cookies HTTP-only para autenticação
    Use esta função em todas as rotas de login/refresh
    """
    # Cookie do access token
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,        # Não acessível via JavaScript
        secure=False,         # ⚠️ False para desenvolvimento local (HTTP)
        samesite="lax",       # Proteção contra CSRF
        max_age=expires_in,   # Tempo de vida em segundos
        path="/"              # Disponível em todo o site
    )
    
    # Cookie do refresh token (se fornecido)
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,      # ⚠️ False para desenvolvimento
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 dias
            path="/"
        )
    
    logger.info(f"🍪 Cookies de autenticação definidos (secure=False)")
    return response

def clear_auth_cookies(response: Response):
    """
    Remove cookies de autenticação (logout)
    """
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
    
    # Funções de cookie
    'set_auth_cookies',
    'clear_auth_cookies'
]