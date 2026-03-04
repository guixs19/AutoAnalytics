# backend/security.py - VERSÃO DEFINITIVA E CORRIGIDA
"""
MÓDULO CENTRAL DE SEGURANÇA
Todo o sistema DEVE importar daqui: from backend.security import ...
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import secrets
import hashlib
import hmac

# Argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

# JWT
from jose import JWTError, jwt

# FastAPI
from fastapi import HTTPException, status, Request, Depends
from fastapi.security import OAuth2PasswordBearer

# SQLAlchemy (importações postergadas para evitar circular)
# from sqlalchemy.orm import Session - VAI SER IMPORTADO DENTRO DAS FUNÇÕES

# Redis
import redis.asyncio as redis

# Configurações
from backend.config.settings import settings

# ==============================================
# CONFIGURAÇÕES GLOBAIS
# ==============================================

# Definir o esquema OAuth2 (será usado nas dependências)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

# ==============================================
# 1. ARGON2 - HASH DE SENHA
# ==============================================

class Argon2Hasher:
    """Hash de senha usando Argon2 - MAIS SEGURO QUE BCRYPT"""
    
    def __init__(self):
        self.ph = PasswordHasher(
            time_cost=settings.ARGON2_TIME_COST,
            memory_cost=settings.ARGON2_MEMORY_COST,
            parallelism=settings.ARGON2_PARALLELISM,
            hash_len=32,
            salt_len=16
        )
        print(f"✅ Argon2 inicializado (time_cost={settings.ARGON2_TIME_COST})")
    
    def hash_password(self, password: str) -> str:
        """Gera hash Argon2 da senha"""
        try:
            return self.ph.hash(password)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao gerar hash: {str(e)}"
            )
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verifica se a senha corresponde ao hash"""
        try:
            return self.ph.verify(hashed, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception:
            return False
    
    def check_needs_rehash(self, hashed: str) -> bool:
        """Verifica se o hash precisa ser atualizado"""
        try:
            return self.ph.check_needs_rehash(hashed)
        except:
            return False

# ==============================================
# 2. JWT COMPLETO
# ==============================================

class JWTManager:
    """Gerenciador de JWT - Tokens de acesso e refresh"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        # Tentar conectar Redis para blacklist
        self.redis_client = None
        self.memory_blacklist = set()  # Fallback em memória
        
        # 🔥 CORRIGIDO: Removida a tentativa de ping que causava warning
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2
            )
            # Não tentar fazer ping aqui - apenas configurar o cliente
            print("✅ Redis configurado para blacklist JWT (modo assíncrono)")
        except Exception as e:
            print(f"⚠️ Redis não disponível: {e}")
            self.redis_client = None
    
    def _generate_jti(self) -> str:
        """Gera ID único para o token"""
        return secrets.token_urlsafe(16)
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Cria token de acesso (curta duração)"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_expire_minutes)
        
        to_encode.update({
            "exp": expire,
            "type": "access",
            "iat": datetime.utcnow(),
            "jti": self._generate_jti()
        })
        
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Cria token de refresh (longa duração)"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_expire_days)
        
        to_encode.update({
            "exp": expire,
            "type": "refresh",
            "iat": datetime.utcnow(),
            "jti": self._generate_jti()
        })
        
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
    
    def create_token_pair(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Cria par de tokens (access + refresh)"""
        # Garantir que tem os campos obrigatórios
        payload = {
            "sub": user_data.get("sub") or user_data.get("email"),
            "email": user_data.get("email"),
            "name": user_data.get("name", ""),
            "role": user_data.get("role", "user")
        }
        
        return {
            "access_token": self.create_access_token(payload),
            "refresh_token": self.create_refresh_token(payload),
            "token_type": "bearer"
        }
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """Verifica token e retorna payload se válido"""
        if not token:
            return None
        
        try:
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm]
            )
            
            # Verificar tipo
            if payload.get("type") != token_type:
                return None
            
            # Verificar se está na blacklist (síncrono para uso em funções síncronas)
            jti = payload.get("jti")
            if jti:
                # Para uso síncrono, não podemos verificar Redis aqui
                # A verificação assíncrona será feita nas funções que usam await
                pass
            
            return payload
            
        except jwt.ExpiredSignatureError:
            return None
        except JWTError:
            return None
    
    async def verify_token_async(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """Versão assíncrona com verificação de blacklist"""
        payload = self.verify_token(token, token_type)
        
        if not payload:
            return None
        
        # Verificar blacklist
        jti = payload.get("jti")
        if jti and await self.is_token_blacklisted(jti):
            return None
        
        return payload
    
    async def blacklist_token(self, jti: str, expire_in: int):
        """Adiciona token à blacklist"""
        if not jti:
            return
        
        if self.redis_client:
            try:
                await self.redis_client.setex(f"blacklist:{jti}", expire_in, "1")
            except:
                self.memory_blacklist.add(jti)
        else:
            self.memory_blacklist.add(jti)
    
    async def is_token_blacklisted(self, jti: str) -> bool:
        """Verifica se token está na blacklist"""
        if not jti:
            return False
        
        if self.redis_client:
            try:
                return await self.redis_client.exists(f"blacklist:{jti}") > 0
            except:
                return jti in self.memory_blacklist
        else:
            return jti in self.memory_blacklist
    
    async def logout(self, token: str):
        """Faz logout invalidando o token"""
        payload = await self.verify_token_async(token)
        if payload and payload.get("jti"):
            exp = payload.get("exp", 0)
            now = datetime.utcnow().timestamp()
            remaining = max(int(exp - now), 3600)  # Mínimo 1 hora
            await self.blacklist_token(payload["jti"], remaining)
            return True
        return False
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Gera novo access token a partir de refresh token"""
        payload = await self.verify_token_async(refresh_token, "refresh")
        
        if not payload:
            return None
        
        # Extrair dados do usuário
        user_data = {
            "sub": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name", ""),
            "role": payload.get("role", "user")
        }
        
        # Invalidar refresh token antigo (token rotation)
        jti = payload.get("jti")
        if jti:
            exp = payload.get("exp", 0)
            now = datetime.utcnow().timestamp()
            remaining = max(int(exp - now), 3600)
            await self.blacklist_token(jti, remaining)
        
        # Criar novos tokens
        return self.create_token_pair(user_data)
    
    def extract_token_from_header(self, auth_header: str) -> Optional[str]:
        """Extrai token do header Authorization"""
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        return auth_header.replace("Bearer ", "")

# ==============================================
# 3. CAPTCHA MANAGER
# ==============================================

class CaptchaManager:
    """Gerenciador de CAPTCHA - Suporte a múltiplos tipos"""
    
    def __init__(self):
        self.captcha_type = settings.CAPTCHA_TYPE
        self.site_key = settings.CAPTCHA_SITE_KEY
        self.secret_key = settings.CAPTCHA_SECRET_KEY
        
        # Cache simples para desenvolvimento
        self._dev_mode = settings.DEBUG and not self.site_key
        
        if self._dev_mode:
            print("⚠️ CAPTCHA em modo desenvolvimento (sempre válido)")
        else:
            print(f"✅ CAPTCHA configurado: {self.captcha_type}")
    
    async def verify_recaptcha(self, token: str, remote_ip: str = None) -> bool:
        """Verifica reCAPTCHA v2/v3"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://www.google.com/recaptcha/api/siteverify",
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": remote_ip
                    },
                    timeout=5
                )
                
                result = response.json()
                
                # Para reCAPTCHA v3, verificar score
                if self.captcha_type == "recaptcha_v3":
                    score = result.get("score", 0)
                    return result.get("success", False) and score >= 0.5
                
                return result.get("success", False)
                
            except Exception as e:
                print(f"❌ Erro ao verificar reCAPTCHA: {e}")
                return False
    
    async def verify_hcaptcha(self, token: str, remote_ip: str = None) -> bool:
        """Verifica hCaptcha"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://hcaptcha.com/siteverify",
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": remote_ip
                    },
                    timeout=5
                )
                
                result = response.json()
                return result.get("success", False)
                
            except Exception:
                return False
    
    def generate_custom_captcha(self) -> Dict[str, Any]:
        """Gera CAPTCHA customizado (para desenvolvimento)"""
        import random
        from PIL import Image, ImageDraw, ImageFont
        import io
        import base64
        
        # Gerar número aleatório
        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        operation = random.choice(['+', '-', '*'])
        
        if operation == '+':
            result = num1 + num2
        elif operation == '-':
            result = num1 - num2
        else:
            result = num1 * num2
        
        # Criar imagem simples
        img = Image.new('RGB', (200, 80), color=(240, 240, 240))
        d = ImageDraw.Draw(img)
        
        # Texto
        text = f"{num1} {operation} {num2} = ?"
        d.text((50, 30), text, fill=(0, 0, 0))
        
        # Adicionar ruído
        for _ in range(100):
            x = random.randint(0, 200)
            y = random.randint(0, 80)
            d.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        
        # Converter para base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        # Gerar ID único
        captcha_id = secrets.token_urlsafe(8)
        
        # Armazenar resultado (em produção, usar Redis)
        self._dev_cache = getattr(self, '_dev_cache', {})
        self._dev_cache[captcha_id] = {
            "result": result,
            "expires": datetime.now().timestamp() + 300  # 5 minutos
        }
        
        return {
            "captcha_id": captcha_id,
            "image": f"data:image/png;base64,{img_str}",
            "type": "custom"
        }
    
    def verify_custom_captcha(self, captcha_id: str, answer: str) -> bool:
        """Verifica CAPTCHA customizado"""
        cache = getattr(self, '_dev_cache', {})
        data = cache.get(captcha_id)
        
        if not data:
            return False
        
        # Verificar expiração
        if data["expires"] < datetime.now().timestamp():
            del cache[captcha_id]
            return False
        
        # Verificar resposta
        try:
            return int(answer) == data["result"]
        except:
            return False
    
    async def verify_token(self, token: str, remote_ip: str = None) -> bool:
        """Verifica CAPTCHA baseado no tipo configurado"""
        # Modo desenvolvimento
        if self._dev_mode:
            return True
        
        if not token:
            return False
        
        # Custom CAPTCHA (formato "id:resposta")
        if self.captcha_type == "custom" and ":" in token:
            captcha_id, answer = token.split(":", 1)
            return self.verify_custom_captcha(captcha_id, answer)
        
        # reCAPTCHA
        if self.captcha_type.startswith("recaptcha"):
            return await self.verify_recaptcha(token, remote_ip)
        
        # hCaptcha
        if self.captcha_type == "hcaptcha":
            return await self.verify_hcaptcha(token, remote_ip)
        
        return False

# ==============================================
# 4. RATE LIMITER
# ==============================================

class RateLimiter:
    """Rate limiting - Previne abuso da API"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}  # Fallback em memória
        self._last_cleanup = datetime.now().timestamp()
        
        try:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
                socket_connect_timeout=2
            )
            print("✅ Redis configurado para rate limiting")
        except Exception as e:
            print(f"⚠️ Redis não disponível para rate limiting: {e}")
    
    async def check_rate_limit(self, key: str, max_requests: int, window: int) -> bool:
        """Verifica rate limit para uma chave"""
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
                return current <= max_requests
                
            except Exception as e:
                print(f"⚠️ Erro no Redis rate limit: {e}")
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

# ==============================================
# 5. INSTÂNCIAS GLOBAIS (SINGLETONS)
# ==============================================

# Criar instâncias únicas
hasher = Argon2Hasher()
jwt_manager = JWTManager()
captcha_manager = CaptchaManager()
rate_limiter = RateLimiter()

# ==============================================
# 6. DEPENDÊNCIAS FASTAPI (COM IMPORTAÇÕES POSTERGADAS)
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
    from backend.database import get_db
    from backend import crud
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
    
    # Verificar token (versão assíncrona)
    payload = await jwt_manager.verify_token_async(token)
    if not payload:
        raise credentials_exception
    
    email = payload.get("sub") or payload.get("email")
    if not email:
        raise credentials_exception
    
    # Se db não foi fornecido, criar sessão
    if db is None:
        from backend.database import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        user = crud.get_user_by_email(db, email=email)
        if not user:
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return current_user

async def get_current_admin_user(
    current_user = Depends(get_current_active_user)
):
    """Verifica se é administrador"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer permissão de administrador."
        )
    return current_user

async def get_current_manager_user(
    current_user = Depends(get_current_active_user)
):
    """Verifica se é gestor ou admin"""
    if current_user.role not in ["admin", "manager"]:
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
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA token é obrigatório"
        )
    
    # Verificar
    client_ip = request.client.host if request.client else None
    valid = await captcha_manager.verify_token(captcha_token, client_ip)
    
    if not valid:
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
]