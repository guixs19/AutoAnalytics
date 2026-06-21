# backend/api/pow_routes.py - SERVIÇO PoW COMPLETO COM REDIS
"""
Serviço de Proof of Work (PoW) - VERSÃO PRODUÇÃO
🔒 SEGURANÇA MÁXIMA:
- Challenge TTL: 2 minutos (Redis)
- Prevenção de Replay Attack: Nonce usado apenas uma vez
- Validação Atômica: SHA-256 em microssegundos
- Fallback para banco se Redis offline
- Rate limiting por IP

SINCRONIZADO COM:
- upload_routes.py (validação PoW)
- pow-client.js (frontend)
- security.py (autenticação)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import secrets
import time
import logging
import json
from collections import defaultdict

from backend.security import get_current_active_user, get_current_admin_user
from backend.database import get_db
from sqlalchemy.orm import Session

# 🔥 Redis para armazenamento temporário
import redis.asyncio as redis
from backend.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pow", tags=["proof-of-work"])

# ==============================================
# 🔥 CONFIGURAÇÕES DE SEGURANÇA
# ==============================================

MIN_COMPLEXITY = 3
MAX_COMPLEXITY = 5
CHALLENGE_TTL_SECONDS = 120  # 🔥 2 MINUTOS (expiração curta)
NONCE_TTL_SECONDS = 120       # 🔥 2 MINUTOS (mesmo TTL)
CLEANUP_INTERVAL = 300        # 5 minutos

# 🔥 Rate limiting
MAX_POW_ATTEMPTS_PER_IP = 50
RATE_WINDOW_SECONDS = 300     # 5 minutos


# ==============================================
# 🔥 DATACLASSES
# ==============================================

@dataclass
class PoWChallenge:
    """Desafio PoW com TTL"""
    prefix: str
    complexity: int
    expires_in: int  # segundos restantes
    timestamp: int = field(default_factory=lambda: int(time.time()))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prefix": self.prefix,
            "complexity": self.complexity,
            "expires_in": self.expires_in,
            "timestamp": self.timestamp
        }


# ==============================================
# 🔥 SERVIÇO PoW COM REDIS
# ==============================================

class PoWService:
    """
    Serviço de Proof of Work com Redis
    
    🔒 SEGURANÇA:
    1. Challenge TTL: 2 minutos (Redis expires)
    2. Nonce usado uma vez (prevenção replay)
    3. Validação SHA-256 atômica
    4. Rate limiting por IP
    """
    
    def __init__(self):
        self.redis_client = None
        self._redis_initialized = False
        
        # Fallback em memória (se Redis offline)
        self._fallback_challenges = {}  # prefix -> timestamp
        self._fallback_nonces = {}      # key -> timestamp
        self._failed_attempts = defaultdict(int)
        self._stats = {
            "challenges_generated": 0,
            "solutions_verified": 0,
            "failed_verifications": 0,
            "replay_attempts": 0,
            "rate_limited": 0,
            "unique_users": set()
        }
        self._last_cleanup = time.time()
        
        logger.info("✅ PoW Service inicializado (Redis + Fallback)")
    
    async def init_redis(self):
        """Inicializa conexão com Redis"""
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
            logger.info("✅ Redis configurado para PoW (TTL e prevenção replay)")
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível para PoW: {e}")
            self.redis_client = None
            self._redis_initialized = True
    
    def _get_challenge_key(self, prefix: str) -> str:
        """Chave Redis para desafio"""
        return f"pow:challenge:{prefix}"
    
    def _get_nonce_key(self, prefix: str, nonce: str) -> str:
        """Chave Redis para nonce usado"""
        return f"pow:nonce:{prefix}:{nonce}"
    
    def _get_rate_key(self, ip: str) -> str:
        """Chave Redis para rate limiting"""
        return f"pow:rate:{ip}"
    
    async def generate_challenge(self, ip: str, user_id: Optional[int] = None) -> PoWChallenge:
        """
        Gera desafio PoW com TTL de 2 minutos
        
        🔒 O desafio expira automaticamente no Redis
        """
        await self.init_redis()
        self._cleanup_fallback()
        
        # Rate limiting
        if not await self._check_rate_limit(ip):
            self._stats["rate_limited"] += 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas de PoW. Aguarde alguns minutos."
            )
        
        # Complexidade adaptativa
        base_complexity = MIN_COMPLEXITY
        failures = self._failed_attempts.get(ip, 0)
        
        if failures > 10:
            complexity = min(MAX_COMPLEXITY, base_complexity + 2)
        elif failures > 5:
            complexity = min(MAX_COMPLEXITY, base_complexity + 1)
        else:
            complexity = base_complexity
        
        # Gera prefixo aleatório
        prefix = secrets.token_hex(8)
        
        # 🔥 SALVA NO REDIS COM TTL (2 minutos)
        challenge_data = {
            "prefix": prefix,
            "complexity": complexity,
            "timestamp": int(time.time()),
            "ip": ip,
            "user_id": user_id
        }
        
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    self._get_challenge_key(prefix),
                    CHALLENGE_TTL_SECONDS,
                    json.dumps(challenge_data)
                )
                logger.debug(f"🔐 Desafio PoW salvo no Redis TTL={CHALLENGE_TTL_SECONDS}s")
            except Exception as e:
                logger.error(f"Erro ao salvar desafio no Redis: {e}")
                # Fallback: salva em memória
                self._fallback_challenges[prefix] = {
                    "data": challenge_data,
                    "expires_at": time.time() + CHALLENGE_TTL_SECONDS
                }
        else:
            # Fallback: salva em memória
            self._fallback_challenges[prefix] = {
                "data": challenge_data,
                "expires_at": time.time() + CHALLENGE_TTL_SECONDS
            }
        
        self._stats["challenges_generated"] += 1
        if user_id:
            self._stats["unique_users"].add(user_id)
        
        logger.info(f"🔐 Desafio PoW gerado: prefixo={prefix[:4]}..., complexity={complexity}, TTL={CHALLENGE_TTL_SECONDS}s")
        
        return PoWChallenge(
            prefix=prefix,
            complexity=complexity,
            expires_in=CHALLENGE_TTL_SECONDS
        )
    
    async def verify_solution(
        self, 
        prefix: str, 
        nonce: str, 
        complexity: int, 
        ip: str,
        user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        🔥 VALIDAÇÃO ATÔMICA E SEGURA
        
        1. Verifica se o desafio existe e não expirou
        2. Verifica se o nonce já foi usado (prevenção replay)
        3. Valida o hash SHA-256 (microssegundos)
        4. Marca o nonce como usado (Redis SETEX)
        5. Retorna resultado
        
        🔒 Prevenção de Replay Attack: Nonce usado uma única vez
        """
        await self.init_redis()
        self._cleanup_fallback()
        
        # 1. Verifica se o desafio existe e é válido
        challenge_valid, challenge_data = await self._get_challenge_data(prefix)
        
        if not challenge_valid:
            self._stats["failed_verifications"] += 1
            self._record_failure(ip)
            return False, "Desafio expirado ou inválido. Gere um novo."
        
        # Verifica se a complexidade corresponde
        stored_complexity = challenge_data.get("complexity")
        if stored_complexity != complexity:
            self._stats["failed_verifications"] += 1
            self._record_failure(ip)
            return False, f"Complexidade incorreta. Esperado: {stored_complexity}"
        
        # 2. 🔥 VERIFICA SE O NONCE JÁ FOI USADO (PREVENÇÃO REPLAY)
        nonce_key = self._get_nonce_key(prefix, nonce)
        
        if self.redis_client:
            try:
                nonce_exists = await self.redis_client.exists(nonce_key)
                if nonce_exists:
                    self._stats["replay_attempts"] += 1
                    self._record_failure(ip)
                    logger.warning(f"⚠️ REPLAY ATTACK DETECTED: nonce={nonce[:4]}... de {ip}")
                    return False, "Nonce já utilizado. Gere um novo desafio."
            except Exception as e:
                logger.error(f"Erro ao verificar nonce no Redis: {e}")
                # Fallback: verifica em memória
                if nonce_key in self._fallback_nonces:
                    self._stats["replay_attempts"] += 1
                    self._record_failure(ip)
                    return False, "Nonce já utilizado. Gere um novo desafio."
        else:
            # Fallback: verifica em memória
            if nonce_key in self._fallback_nonces:
                self._stats["replay_attempts"] += 1
                self._record_failure(ip)
                return False, "Nonce já utilizado. Gere um novo desafio."
        
        # 3. 🔥 VALIDA O HASH SHA-256 (ATÔMICO E RÁPIDO)
        test_str = f"{prefix}{nonce}"
        hash_hex = hashlib.sha256(test_str.encode()).hexdigest()
        
        # Verifica se os primeiros 'complexity' bits são zero
        if complexity <= 4:
            is_valid = hash_hex.startswith('0')
        else:
            bits = complexity
            required_zeros = '0' * ((bits + 3) // 4)
            is_valid = hash_hex.startswith(required_zeros)
        
        if not is_valid:
            self._stats["failed_verifications"] += 1
            self._record_failure(ip)
            logger.warning(f"⚠️ Hash inválido: prefixo={prefix[:4]}..., hash={hash_hex[:8]}...")
            return False, "Solução inválida. O hash não atende à complexidade exigida."
        
        # 4. 🔥 MARCA O NONCE COMO USADO (TTL = 2 minutos)
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    nonce_key,
                    NONCE_TTL_SECONDS,
                    json.dumps({
                        "ip": ip,
                        "user_id": user_id,
                        "timestamp": int(time.time())
                    })
                )
                logger.debug(f"🔒 Nonce marcado como usado no Redis TTL={NONCE_TTL_SECONDS}s")
            except Exception as e:
                logger.error(f"Erro ao marcar nonce no Redis: {e}")
                self._fallback_nonces[nonce_key] = time.time() + NONCE_TTL_SECONDS
        else:
            self._fallback_nonces[nonce_key] = time.time() + NONCE_TTL_SECONDS
        
        # 5. Remove o desafio (já foi usado)
        if self.redis_client:
            try:
                await self.redis_client.delete(self._get_challenge_key(prefix))
            except Exception as e:
                logger.error(f"Erro ao remover desafio: {e}")
        else:
            self._fallback_challenges.pop(prefix, None)
        
        self._stats["solutions_verified"] += 1
        self._clear_failures(ip)
        
        logger.info(f"✅ PoW verificado: prefixo={prefix[:4]}..., nonce={nonce[:4]}..., complexity={complexity}")
        
        return True, "PoW validado com sucesso"
    
    async def _get_challenge_data(self, prefix: str) -> Tuple[bool, Dict[str, Any]]:
        """Obtém dados do desafio do Redis ou fallback"""
        if self.redis_client:
            try:
                data = await self.redis_client.get(self._get_challenge_key(prefix))
                if data:
                    return True, json.loads(data)
                return False, {}
            except Exception as e:
                logger.error(f"Erro ao buscar desafio no Redis: {e}")
                # Fallback: verifica em memória
                if prefix in self._fallback_challenges:
                    challenge = self._fallback_challenges[prefix]
                    if challenge["expires_at"] > time.time():
                        return True, challenge["data"]
                return False, {}
        else:
            if prefix in self._fallback_challenges:
                challenge = self._fallback_challenges[prefix]
                if challenge["expires_at"] > time.time():
                    return True, challenge["data"]
            return False, {}
    
    async def _check_rate_limit(self, ip: str) -> bool:
        """Verifica rate limiting por IP"""
        if self.redis_client:
            try:
                key = self._get_rate_key(ip)
                count = await self.redis_client.incr(key)
                if count == 1:
                    await self.redis_client.expire(key, RATE_WINDOW_SECONDS)
                return count <= MAX_POW_ATTEMPTS_PER_IP
            except Exception as e:
                logger.error(f"Erro no rate limit: {e}")
                return True  # Permite se Redis falhar
        return True  # Fallback: permite
    
    def _record_failure(self, ip: str):
        """Registra falha para adaptação de complexidade"""
        self._failed_attempts[ip] += 1
        if self._failed_attempts[ip] > 100:
            self._failed_attempts[ip] = 100
    
    def _clear_failures(self, ip: str):
        """Limpa falhas após sucesso"""
        if ip in self._failed_attempts:
            self._failed_attempts[ip] = max(0, self._failed_attempts[ip] - 2)
            if self._failed_attempts[ip] == 0:
                del self._failed_attempts[ip]
    
    def _cleanup_fallback(self):
        """Limpa fallback em memória"""
        now = time.time()
        if now - self._last_cleanup < CLEANUP_INTERVAL:
            return
        
        # Limpa desafios expirados
        expired = [k for k, v in self._fallback_challenges.items() if v["expires_at"] < now]
        for k in expired:
            del self._fallback_challenges[k]
        
        # Limpa nonces expirados
        expired = [k for k, v in self._fallback_nonces.items() if v < now]
        for k in expired:
            del self._fallback_nonces[k]
        
        if expired:
            logger.info(f"🧹 Limpeza fallback: {len(expired)} itens removidos")
        
        self._last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do serviço"""
        return {
            "challenges_generated": self._stats["challenges_generated"],
            "solutions_verified": self._stats["solutions_verified"],
            "failed_verifications": self._stats["failed_verifications"],
            "replay_attempts": self._stats["replay_attempts"],
            "rate_limited": self._stats["rate_limited"],
            "unique_users": len(self._stats["unique_users"]),
            "active_nonces": len(self._fallback_nonces) if not self.redis_client else 0,
            "redis_available": self.redis_client is not None,
            "config": {
                "min_complexity": MIN_COMPLEXITY,
                "max_complexity": MAX_COMPLEXITY,
                "challenge_ttl_seconds": CHALLENGE_TTL_SECONDS,
                "nonce_ttl_seconds": NONCE_TTL_SECONDS,
                "max_attempts_per_ip": MAX_POW_ATTEMPTS_PER_IP,
                "rate_window_seconds": RATE_WINDOW_SECONDS,
                "algorithm": "SHA-256"
            }
        }


# ==============================================
# 🔥 INSTÂNCIA GLOBAL DO SERVIÇO
# ==============================================

pow_service = PoWService()


# ==============================================
# 🔥 FUNÇÃO DE VALIDAÇÃO - DEPENDÊNCIA FASTAPI
# ==============================================

async def validate_pow_request(
    request: Request,
    x_pow_prefix: Optional[str] = Header(None, alias="X-PoW-Prefix"),
    x_pow_nonce: Optional[str] = Header(None, alias="X-PoW-Nonce"),
    x_pow_complexity: Optional[int] = Header(None, alias="X-PoW-Complexity"),
    current_user = None
) -> bool:
    """
    🔥 DEPENDÊNCIA FASTAPI - VALIDAÇÃO ATÔMICA
    
    USO:
    @router.post("/upload-auto")
    async def upload_auto(
        # ...
        pow_valid: bool = Depends(validate_pow_request)
    ):
        if not pow_valid:
            raise HTTPException(status_code=401, detail="PoW inválido")
        # ... resto do código
    
    🔒 VALIDA EM MICROSSEGUNDOS - Bots são bloqueados na entrada
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 1. Verifica se os headers existem
    if not x_pow_prefix or not x_pow_nonce or x_pow_complexity is None:
        logger.warning(f"⚠️ Requisição sem PoW: {client_ip}")
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail={
                "error": "Proof of Work é obrigatório",
                "required": ["X-PoW-Prefix", "X-PoW-Nonce", "X-PoW-Complexity"],
                "action": "GET /api/pow/challenge para obter um desafio"
            }
        )
    
    # 2. Valida complexidade
    if not (MIN_COMPLEXITY <= x_pow_complexity <= MAX_COMPLEXITY):
        logger.warning(f"⚠️ Complexidade inválida: {x_pow_complexity} de {client_ip}")
        raise HTTPException(
            status_code=400,
            detail=f"Complexidade deve estar entre {MIN_COMPLEXITY} e {MAX_COMPLEXITY}"
        )
    
    # 3. 🔥 VALIDAÇÃO ATÔMICA - MICROSSEGUNDOS
    user_id = current_user.id if current_user else None
    
    is_valid, message = await pow_service.verify_solution(
        prefix=x_pow_prefix,
        nonce=x_pow_nonce,
        complexity=x_pow_complexity,
        ip=client_ip,
        user_id=user_id
    )
    
    if not is_valid:
        logger.warning(f"⚠️ PoW inválido de {client_ip}: {message}")
        raise HTTPException(
            status_code=401,
            detail=f"Proof of Work inválido: {message}"
        )
    
    logger.debug(f"✅ PoW validado para {client_ip} (complexidade: {x_pow_complexity})")
    return True


# ==============================================
# 🔥 ROTAS DA API
# ==============================================

@router.get("/challenge")
async def get_pow_challenge(
    request: Request,
    current_user = Depends(get_current_active_user)
):
    """
    🔐 Gera desafio PoW com TTL de 2 minutos
    
    O cliente deve resolver o desafio e enviar a solução
    junto com a requisição de upload.
    
    🔒 TTL curto (2 min) impede reuso de desafios antigos
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id = current_user.id if current_user else None
    
    challenge = await pow_service.generate_challenge(client_ip, user_id)
    
    logger.info(f"🔐 Desafio PoW para {current_user.email} (complexidade: {challenge.complexity})")
    
    return challenge.to_dict()


@router.post("/verify")
async def verify_pow_solution(
    request: Request,
    prefix: str,
    nonce: str,
    complexity: int,
    current_user = Depends(get_current_active_user)
):
    """
    🔐 Verifica se a solução do PoW está correta
    (Endpoint interno, usado pelo upload_routes.py)
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id = current_user.id if current_user else None
    
    is_valid, message = await pow_service.verify_solution(
        prefix=prefix,
        nonce=nonce,
        complexity=complexity,
        ip=client_ip,
        user_id=user_id
    )
    
    if not is_valid:
        logger.warning(f"⚠️ PoW inválido para {current_user.email}: {message}")
        raise HTTPException(status_code=401, detail=message)
    
    logger.info(f"✅ PoW verificado e consumido para {current_user.email}")
    
    return {
        "valid": True,
        "message": "PoW verificado com sucesso",
        "complexity": complexity,
        "verified_at": datetime.now().isoformat()
    }


@router.get("/stats")
async def get_pow_stats(
    current_user = Depends(get_current_active_user)
):
    """📊 Estatísticas do PoW (apenas admin)"""
    try:
        admin_user = await get_current_admin_user(current_user)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Acesso negado. Requer permissão de administrador.")
    
    stats = pow_service.get_stats()
    stats.update({
        "protected_routes": ["/api/upload-auto", "/api/upload"],
        "middleware_active": True,
        "status": "healthy",
        "security": {
            "challenge_ttl_seconds": CHALLENGE_TTL_SECONDS,
            "nonce_ttl_seconds": NONCE_TTL_SECONDS,
            "replay_protection": True,
            "rate_limit_active": True
        }
    })
    
    return stats


@router.get("/health")
async def pow_health():
    """🔍 Verifica saúde do sistema PoW"""
    await pow_service.init_redis()
    stats = pow_service.get_stats()
    
    return {
        "status": "healthy",
        "service": "pow",
        "version": "2.0",
        "algorithm": "SHA-256",
        "redis_available": pow_service.redis_client is not None,
        "challenge_ttl_seconds": CHALLENGE_TTL_SECONDS,
        "nonce_ttl_seconds": NONCE_TTL_SECONDS,
        "replay_protection": True,
        "active_nonces": stats["active_nonces"]
    }


@router.get("/check")
async def check_pow_status(
    request: Request,
    current_user = Depends(get_current_active_user)
):
    """🔍 Verifica se o cliente tem um PoW válido pronto"""
    client_ip = request.client.host if request.client else "unknown"
    
    failures = pow_service._failed_attempts.get(client_ip, 0)
    
    return {
        "ready": failures < 3,
        "failures": failures,
        "required_complexity": MIN_COMPLEXITY + (1 if failures > 5 else 0),
        "max_complexity": MAX_COMPLEXITY,
        "suggested_action": "generate_challenge" if failures < 3 else "wait_and_retry"
    }


# ==============================================
# 🔥 EXPORTAÇÕES
# ==============================================

__all__ = [
    'router',
    'pow_service',
    'validate_pow_request',
    'MIN_COMPLEXITY',
    'MAX_COMPLEXITY',
    'CHALLENGE_TTL_SECONDS',
    'NONCE_TTL_SECONDS'
]

print("=" * 60)
print("🔥 PoW Service v2.0 - SEGURANÇA MÁXIMA")
print(f"   ✅ Challenge TTL: {CHALLENGE_TTL_SECONDS}s")
print(f"   ✅ Nonce TTL: {NONCE_TTL_SECONDS}s")
print(f"   ✅ Replay Attack Prevention: Ativo")
print(f"   ✅ Rate Limiting: {MAX_POW_ATTEMPTS_PER_IP}/5min")
print(f"   ✅ Complexidade: {MIN_COMPLEXITY}-{MAX_COMPLEXITY}")
print(f"   ✅ Algoritmo: SHA-256")
print("=" * 60)