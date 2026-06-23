# backend/api/pow_routes.py - VERSÃO CORRIGIDA (SEM Optional[Request])
"""
Serviço de Proof of Work (PoW) - PROTEÇÃO CONTRA SPAM/DDOS
✅ CORRIGIDO: Sem Optional[Request] na dependência
✅ CORRIGIDO: response_model=None em todas as rotas
✅ INTEGRADO: Com o sistema de autenticação
✅ SUPORTE: Headers X-PoW-Nonce e X-PoW-Challenge
"""

import time
import logging
import hashlib
import secrets
from fastapi import APIRouter, HTTPException, Depends, Request, Header, status
from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime

from backend.security import get_current_user
from backend.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pow", tags=["proof-of-work"])

# ==============================================
# MODELOS PYDANTIC
# ==============================================

class VerifyPoWRequest(BaseModel):
    nonce: str = Field(..., description="Nonce encontrado pelo cliente")
    challenge: str = Field(..., description="Desafio recebido do servidor")
    difficulty: int = Field(4, description="Dificuldade do PoW (número de zeros no prefixo)")
    client_timestamp: Optional[int] = Field(None, description="Timestamp do cliente para sincronização")


# ==============================================
# CONFIGURAÇÕES
# ==============================================

DEFAULT_DIFFICULTY = 4  # Número de zeros no prefixo do hash
CHALLENGE_EXPIRY_SECONDS = 300  # 5 minutos
MAX_CHALLENGES_PER_IP = 10  # Limite de desafios por IP para evitar abuse

# Cache em memória para os desafios gerados
_challenges_db: Dict[str, float] = {}
_ip_request_count: Dict[str, int] = {}


# ==============================================
# SERVIÇO PoW (NÚCLEO)
# ==============================================

class PoWService:
    """
    Serviço de Proof of Work baseado em SHA-256
    Implementa desafio-resposta com dificuldade configurável
    """
    
    @staticmethod
    def generate_challenge() -> str:
        """
        Gera um desafio criptográfico aleatório
        Retorna uma string hex de 32 caracteres
        """
        return secrets.token_hex(16)  # 32 caracteres hex
    
    @staticmethod
    def verify_proof(challenge: str, nonce: str, difficulty: int = DEFAULT_DIFFICULTY) -> bool:
        """
        Verifica se o nonce resolve o desafio com a dificuldade especificada
        """
        if not challenge or not nonce:
            return False
        
        if difficulty < 1:
            difficulty = 1
        if difficulty > 6:
            difficulty = 6  # Limite máximo para não sobrecarregar o servidor
        
        try:
            # Concatenar challenge + nonce
            data = f"{challenge}{nonce}".encode('utf-8')
            # Calcular hash SHA-256
            hash_hex = hashlib.sha256(data).hexdigest()
            # Verificar se o prefixo tem a quantidade correta de zeros
            prefix = '0' * difficulty
            return hash_hex.startswith(prefix)
        except Exception as e:
            logger.error(f"❌ Erro ao verificar PoW: {e}")
            return False
    
    @staticmethod
    def get_difficulty_from_request(request: Request) -> int:
        """
        Determina a dificuldade baseada no cliente (IP, headers, etc.)
        Aumenta a dificuldade para clientes suspeitos
        """
        client_ip = request.client.host if request.client else "unknown"
        
        # Aumentar dificuldade para IPs que fazem muitas requisições
        requests_count = _ip_request_count.get(client_ip, 0)
        if requests_count > 50:
            return 5
        elif requests_count > 20:
            return 4
        else:
            return DEFAULT_DIFFICULTY


# ==============================================
# 🔥 INSTÂNCIA GLOBAL DO SERVIÇO
# ==============================================

pow_service = PoWService()


# ==============================================
# 🔥 FUNÇÃO DE VALIDAÇÃO - DEPENDÊNCIA FASTAPI (CORRIGIDA)
# ==============================================

async def validate_pow_request(request: Request) -> bool:
    """
    🔥 DEPENDÊNCIA FASTAPI - VALIDAÇÃO ATÔMICA
    
    ❗ IMPORTANTE: NÃO use Optional[Request] aqui!
    O FastAPI usa o tipo do parâmetro para inferir o modelo de resposta.
    Use apenas Request (sem Optional) para que o FastAPI entenda
    que é uma dependência que recebe o objeto Request.
    
    USO:
    @router.post("/upload-auto")
    async def upload_auto(
        # ...
        pow_valid: bool = Depends(validate_pow_request)
    ):
        # Se chegou aqui, o PoW já foi validado!
        # ...
    
    🔒 VALIDA EM MICROSSEGUNDOS - Bots são bloqueados na entrada
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 1. Verifica se os headers existem
    nonce = request.headers.get("X-PoW-Nonce")
    challenge = request.headers.get("X-PoW-Challenge")
    
    if not nonce or not challenge:
        logger.warning(f"⚠️ PoW ausente na requisição de {client_ip}")
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail={
                "error": "Proof of Work é obrigatório",
                "required": ["X-PoW-Nonce", "X-PoW-Challenge"],
                "action": "GET /api/pow/challenge para obter um desafio"
            }
        )
    
    # 2. Validar expiração do challenge
    created_at = _challenges_db.get(challenge)
    if not created_at:
        logger.warning(f"⚠️ Challenge inválido ou expirado de {client_ip}")
        raise HTTPException(
            status_code=400, 
            detail="Challenge inválido ou expirado. Gere um novo."
        )
    
    if time.time() - created_at > CHALLENGE_EXPIRY_SECONDS:
        _challenges_db.pop(challenge, None)
        logger.warning(f"⚠️ Challenge expirou para {client_ip}")
        raise HTTPException(
            status_code=400, 
            detail="Challenge expirou. Gere um novo."
        )
    
    # 3. 🔥 VALIDA O HASH SHA-256 (ATÔMICO E RÁPIDO)
    is_valid = PoWService.verify_proof(challenge, nonce, difficulty=DEFAULT_DIFFICULTY)
    
    if not is_valid:
        logger.error(f"❌ PoW inválido para {client_ip} - challenge: {challenge[:8]}...")
        raise HTTPException(
            status_code=400, 
            detail="Proof of Work inválido. Solução incorreta."
        )
    
    # 4. Consumir o challenge para evitar replay attacks
    _challenges_db.pop(challenge, None)
    
    logger.debug(f"✅ PoW validado para {client_ip}")
    return True


# ==============================================
# 🔥 ROTAS DA API (TODAS COM response_model=None)
# ==============================================

@router.get("/challenge", response_model=None)
async def get_pow_challenge(
    request: Request,
    current_user = Depends(get_current_user)
):
    """
    🔐 Gera um novo desafio criptográfico (challenge) para o cliente resolver.
    Dificuldade padrão: 4 (prefixo com 4 zeros no hash '0000...')
    
    🔒 TTL: 5 minutos (expiração automática)
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limiting simples
    _ip_request_count[client_ip] = _ip_request_count.get(client_ip, 0) + 1
    if _ip_request_count[client_ip] > MAX_CHALLENGES_PER_IP:
        # Reset após 1 hora
        if time.time() % 3600 < 60:
            _ip_request_count[client_ip] = 0
        else:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas requisições de desafio. Aguarde alguns minutos."
            )
    
    # Determinar dificuldade adaptativa
    difficulty = PoWService.get_difficulty_from_request(request)
    
    # Gerar desafio
    challenge = PoWService.generate_challenge()
    _challenges_db[challenge] = time.time()
    
    logger.info(f"🔐 Desafio PoW gerado para {current_user.email} (dificuldade: {difficulty})")
    
    return {
        "challenge": challenge,
        "difficulty": difficulty,
        "algorithm": "SHA-256",
        "hint": f"Encontre um nonce tal que SHA256(challenge + nonce) comece com '{'0' * difficulty}'",
        "expires_in": CHALLENGE_EXPIRY_SECONDS,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/verify", response_model=None)
async def verify_pow_solution(
    data: VerifyPoWRequest,
    current_user = Depends(get_current_user)
):
    """
    🔐 Endpoint alternativo para verificação explícita do Proof of Work via JSON payload.
    
    🔒 Prevenção de replay: challenge é consumido após uso.
    """
    logger.info(f"🔍 Verificando PoW para {current_user.email}")
    
    # 1. Verificar se o challenge existe
    created_at = _challenges_db.get(data.challenge)
    if not created_at:
        logger.warning(f"⚠️ Challenge inválido para {current_user.email}")
        raise HTTPException(
            status_code=400, 
            detail="Challenge inválido ou já utilizado. Gere um novo."
        )
    
    # 2. Verificar expiração
    if time.time() - created_at > CHALLENGE_EXPIRY_SECONDS:
        _challenges_db.pop(data.challenge, None)
        logger.warning(f"⚠️ Challenge expirou para {current_user.email}")
        raise HTTPException(
            status_code=400, 
            detail="Challenge expirou. Gere um novo."
        )
    
    # 3. 🔥 Validar a solução
    is_valid = PoWService.verify_proof(
        data.challenge, 
        data.nonce, 
        difficulty=data.difficulty
    )
    
    if not is_valid:
        logger.warning(f"⚠️ Solução incorreta para {current_user.email}")
        raise HTTPException(
            status_code=400, 
            detail="Solução do Proof of Work incorreta."
        )
    
    # 4. Consumir o challenge (prevenção replay)
    _challenges_db.pop(data.challenge, None)
    
    logger.info(f"✅ PoW verificado com sucesso para {current_user.email}")
    
    return {
        "status": "success",
        "message": "Proof of Work validado com sucesso!",
        "verified_at": datetime.now().isoformat(),
        "difficulty": data.difficulty
    }


@router.get("/health", response_model=None)
async def pow_health():
    """🔍 Verifica saúde do sistema PoW"""
    return {
        "status": "healthy",
        "service": "pow",
        "version": "1.0",
        "algorithm": "SHA-256",
        "challenge_ttl_seconds": CHALLENGE_EXPIRY_SECONDS,
        "default_difficulty": DEFAULT_DIFFICULTY,
        "active_challenges": len(_challenges_db),
        "replay_protection": True
    }


@router.get("/stats", response_model=None)
async def get_pow_stats(
    current_user = Depends(get_current_user)
):
    """📊 Estatísticas do PoW (apenas admin)"""
    # Verifica se é admin
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, 
            detail="Acesso negado. Requer permissão de administrador."
        )
    
    return {
        "active_challenges": len(_challenges_db),
        "default_difficulty": DEFAULT_DIFFICULTY,
        "challenge_ttl_seconds": CHALLENGE_EXPIRY_SECONDS,
        "algorithm": "SHA-256",
        "replay_protection": True,
        "rate_limiting": {
            "max_challenges_per_ip": MAX_CHALLENGES_PER_IP,
            "active_ips": len(_ip_request_count)
        },
        "status": "healthy"
    }


# ==============================================
# 🔥 EXPORTAÇÕES
# ==============================================

__all__ = [
    'router',
    'pow_service',
    'validate_pow_request',
    'DEFAULT_DIFFICULTY',
    'CHALLENGE_EXPIRY_SECONDS'
]

print("=" * 60)
print("🔥 PoW Service v1.0 - PROTEÇÃO CONTRA SPAM")
print(f"   ✅ Challenge TTL: {CHALLENGE_EXPIRY_SECONDS}s")
print(f"   ✅ Default Difficulty: {DEFAULT_DIFFICULTY}")
print(f"   ✅ Replay Attack Prevention: Ativo")
print(f"   ✅ Rate Limiting: {MAX_CHALLENGES_PER_IP}/IP")
print(f"   ✅ Algoritmo: SHA-256")
print("=" * 60)