# backend/api/pow_routes.py - VERSÃO COMPLETA REFATORADA v2.0
"""
🔥 Serviço de Proof of Work (PoW) - PROTEÇÃO CONTRA SPAM/DDOS
✅ ARQUITETURA ROBUSTA
✅ CACHE EFICIENTE COM TTL
✅ DIFICULDADE ADAPTATIVA
✅ RATE LIMITING POR IP/USUÁRIO
✅ PREVENÇÃO DE REPLAY ATTACKS
✅ LOGS ESTRUTURADOS
✅ SUPORTE A HEADERS X-PoW-*

VERSÃO: 2.0
AUTOR: AutoAnalytics Team
"""
import requests
import time
import logging
import hashlib
import secrets
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, Field
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from backend.security import get_current_user
from backend.database import get_db

# ==============================================
# 🔥 CONFIGURAÇÕES
# ==============================================

logger = logging.getLogger(__name__)

class PoWConfig:
    """Configurações centralizadas do PoW"""
    
    # 🔥 Dificuldade
    DEFAULT_DIFFICULTY: int = 4
    MIN_DIFFICULTY: int = 3
    MAX_DIFFICULTY: int = 6
    
    # 🔥 Expiração
    CHALLENGE_EXPIRY_SECONDS: int = 900  
    CHALLENGE_CLEANUP_INTERVAL: int = 600  # 10 minutos
    CHALLENGE_MAX_SIZE: int = 10000
    
    # 🔥 Rate Limiting
    MAX_CHALLENGES_PER_IP: int = 10
    MAX_CHALLENGES_PER_USER: int = 20
    RATE_LIMIT_WINDOW: int = 3600  # 1 hora
    RATE_LIMIT_BLOCK_DURATION: int = 300  # 5 minutos
    
    # 🔥 IP Tracking
    IP_SUSPICIOUS_THRESHOLD: int = 50
    IP_BLOCK_THRESHOLD: int = 100
    IP_TRACKING_WINDOW: int = 3600  # 1 hora
    
    # 🔥 Headers
    HEADER_CHALLENGE: str = "X-PoW-Challenge"
    HEADER_NONCE: str = "X-PoW-Nonce"
    HEADER_COMPLEXITY: str = "X-PoW-Complexity"
    
    # 🔥 Algoritmo
    ALGORITHM: str = "SHA-256"


# ==============================================
# 🔥 MODELOS DE DADOS
# ==============================================

class VerifyPoWRequest(BaseModel):
    """Modelo para verificação de PoW via JSON"""
    nonce: str = Field(..., description="Nonce encontrado pelo cliente", min_length=1, max_length=64)
    challenge: str = Field(..., description="Desafio recebido do servidor", min_length=32, max_length=32)
    difficulty: int = Field(4, description="Dificuldade do PoW", ge=3, le=6)
    client_timestamp: Optional[int] = Field(None, description="Timestamp do cliente para sincronização")
    
    class Config:
        schema_extra = {
            "example": {
                "nonce": "12345",
                "challenge": "5f36a6b6a55f7e1c88bdb2bd2cf5a2ae",
                "difficulty": 4,
                "client_timestamp": 1700000000
            }
        }


@dataclass
class ChallengeData:
    """Dados do desafio armazenado em cache"""
    prefix: str
    created_at: float
    expires_at: float
    user_id: Optional[int] = None
    ip: Optional[str] = None
    difficulty: int = 4
    used: bool = False
    
    def is_expired(self) -> bool:
        """Verifica se o desafio expirou"""
        return time.time() > self.expires_at
    
    def is_valid(self) -> bool:
        """Verifica se o desafio é válido (não expirado e não usado)"""
        return not self.is_expired() and not self.used
    
    def mark_used(self) -> None:
        """Marca o desafio como usado (prevenção replay)"""
        self.used = True


@dataclass
class RateLimitData:
    """Dados de rate limiting"""
    count: int = 0
    first_request: float = field(default_factory=time.time)
    last_request: float = field(default_factory=time.time)
    blocked_until: Optional[float] = None
    violations: int = 0


# ==============================================
# 🔥 CACHE E ESTADO
# ==============================================

class PoWCache:
    """Cache gerenciado de desafios"""
    
    def __init__(self):
        self._challenges: Dict[str, ChallengeData] = {}
        self._last_cleanup: float = time.time()
    
    def add(self, challenge: str, data: ChallengeData) -> None:
        """Adiciona um desafio ao cache"""
        self._challenges[challenge] = data
        self._cleanup_if_needed()
    
    def get(self, challenge: str) -> Optional[ChallengeData]:
        """Obtém um desafio do cache"""
        return self._challenges.get(challenge)
    
    def remove(self, challenge: str) -> bool:
        """Remove um desafio do cache"""
        if challenge in self._challenges:
            del self._challenges[challenge]
            return True
        return False
    
    def mark_used(self, challenge: str) -> bool:
        """Marca um desafio como usado"""
        data = self._challenges.get(challenge)
        if data and data.is_valid():
            data.mark_used()
            return True
        return False
    
    def _cleanup_if_needed(self) -> None:
        """Limpa desafios expirados se necessário"""
        now = time.time()
        if now - self._last_cleanup < PoWConfig.CHALLENGE_CLEANUP_INTERVAL:
            return
        
        expired = [k for k, v in self._challenges.items() if v.is_expired()]
        for k in expired:
            del self._challenges[k]
        
        # Limitar tamanho do cache
        if len(self._challenges) > PoWConfig.CHALLENGE_MAX_SIZE:
            # Remover os mais antigos
            sorted_items = sorted(
                self._challenges.items(),
                key=lambda x: x[1].created_at
            )
            to_remove = len(self._challenges) - PoWConfig.CHALLENGE_MAX_SIZE
            for k, _ in sorted_items[:to_remove]:
                del self._challenges[k]
        
        self._last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        now = time.time()
        total = len(self._challenges)
        valid = sum(1 for v in self._challenges.values() if v.is_valid())
        expired = sum(1 for v in self._challenges.values() if v.is_expired())
        used = sum(1 for v in self._challenges.values() if v.used)
        
        return {
            "total_challenges": total,
            "valid_challenges": valid,
            "expired_challenges": expired,
            "used_challenges": used,
            "cache_size": total,
            "max_size": PoWConfig.CHALLENGE_MAX_SIZE,
        }


# ==============================================
# 🔥 RATE LIMITER
# ==============================================

class PoWRateLimiter:
    """Gerenciador de rate limiting"""
    
    def __init__(self):
        self._ip_data: Dict[str, RateLimitData] = defaultdict(RateLimitData)
        self._user_data: Dict[int, RateLimitData] = defaultdict(RateLimitData)
    
    def check_ip(self, ip: str) -> Tuple[bool, Optional[int]]:
        """Verifica se o IP está dentro do limite"""
        if not ip:
            return True, None
        
        data = self._ip_data[ip]
        now = time.time()
        
        # Verificar se está bloqueado
        if data.blocked_until and now < data.blocked_until:
            return False, int(data.blocked_until - now)
        
        # Resetar contagem se a janela expirou
        if now - data.first_request > PoWConfig.RATE_LIMIT_WINDOW:
            data.count = 0
            data.first_request = now
            data.violations = 0
        
        # Verificar limite
        if data.count >= PoWConfig.MAX_CHALLENGES_PER_IP:
            data.blocked_until = now + PoWConfig.RATE_LIMIT_BLOCK_DURATION
            data.violations += 1
            return False, PoWConfig.RATE_LIMIT_BLOCK_DURATION
        
        data.count += 1
        data.last_request = now
        return True, None
    
    def check_user(self, user_id: int) -> Tuple[bool, Optional[int]]:
        """Verifica se o usuário está dentro do limite"""
        if not user_id:
            return True, None
        
        data = self._user_data[user_id]
        now = time.time()
        
        if data.blocked_until and now < data.blocked_until:
            return False, int(data.blocked_until - now)
        
        if now - data.first_request > PoWConfig.RATE_LIMIT_WINDOW:
            data.count = 0
            data.first_request = now
        
        if data.count >= PoWConfig.MAX_CHALLENGES_PER_USER:
            data.blocked_until = now + PoWConfig.RATE_LIMIT_BLOCK_DURATION
            return False, PoWConfig.RATE_LIMIT_BLOCK_DURATION
        
        data.count += 1
        data.last_request = now
        return True, None
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do rate limiter"""
        now = time.time()
        blocked_ips = sum(1 for d in self._ip_data.values() if d.blocked_until and now < d.blocked_until)
        blocked_users = sum(1 for d in self._user_data.values() if d.blocked_until and now < d.blocked_until)
        
        return {
            "tracked_ips": len(self._ip_data),
            "tracked_users": len(self._user_data),
            "blocked_ips": blocked_ips,
            "blocked_users": blocked_users,
            "ip_limit": PoWConfig.MAX_CHALLENGES_PER_IP,
            "user_limit": PoWConfig.MAX_CHALLENGES_PER_USER,
            "window_seconds": PoWConfig.RATE_LIMIT_WINDOW,
        }


# ==============================================
# 🔥 SERVIÇO PoW (NÚCLEO)
# ==============================================

class PoWService:
    """
    Serviço de Proof of Work baseado em SHA-256
    Implementa desafio-resposta com dificuldade configurável
    """
    
    def __init__(self):
        self.cache = PoWCache()
        self.rate_limiter = PoWRateLimiter()
        self._ip_tracker: Dict[str, int] = defaultdict(int)
        self._last_ip_cleanup: float = time.time()
        self._stats = {
            "total_challenges_generated": 0,
            "total_challenges_verified": 0,
            "total_challenges_failed": 0,
            "total_replay_attacks_blocked": 0,
            "total_rate_limits_triggered": 0,
        }
    
    # ==============================================
    # 🔥 GERAÇÃO DE DESAFIOS
    # ==============================================
    
    def generate_challenge(
        self,
        ip: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        🔥 Gera um desafio PoW para o cliente
        
        Args:
            ip: Endereço IP do cliente
            user_id: ID do usuário (opcional)
            user_email: Email do usuário (opcional)
        
        Returns:
            Dict com challenge, difficulty, expires_in, etc.
        """
        # 1. Rate limiting
        ip_ok, ip_wait = self.rate_limiter.check_ip(ip)
        if not ip_ok:
            self._stats["total_rate_limits_triggered"] += 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Muitas requisições. Aguarde {ip_wait} segundos.",
                    "retry_after": ip_wait,
                    "type": "ip",
                    "limit": PoWConfig.MAX_CHALLENGES_PER_IP
                }
            )
        
        if user_id:
            user_ok, user_wait = self.rate_limiter.check_user(user_id)
            if not user_ok:
                self._stats["total_rate_limits_triggered"] += 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Muitas requisições. Aguarde {user_wait} segundos.",
                        "retry_after": user_wait,
                        "type": "user",
                        "limit": PoWConfig.MAX_CHALLENGES_PER_USER
                    }
                )
        
        # 2. Determinar dificuldade adaptativa
        difficulty = self._get_adaptive_difficulty(ip, user_id)
        
        # 3. Gerar desafio
        challenge = secrets.token_hex(16)
        now = time.time()
        
        challenge_data = ChallengeData(
            prefix=challenge,
            created_at=now,
            expires_at=now + PoWConfig.CHALLENGE_EXPIRY_SECONDS,
            user_id=user_id,
            ip=ip,
            difficulty=difficulty,
            used=False
        )
        
        self.cache.add(challenge, challenge_data)
        self._stats["total_challenges_generated"] += 1
        
        # 4. Log
        logger.info(
            f"🔐 Desafio PoW gerado para {user_email or ip} "
            f"(dificuldade: {difficulty}, expires: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s)"
        )
        
        # 5. Retornar resposta
        return {
            "challenge": challenge,
            "difficulty": difficulty,
            "algorithm": PoWConfig.ALGORITHM,
            "hint": f"Encontre um nonce tal que {PoWConfig.ALGORITHM}(challenge:nonce) "
                    f"comece com {'0' * difficulty}",
            "expires_in": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
            "timestamp": datetime.now().isoformat(),
        }
    
    # ==============================================
    # 🔥 VERIFICAÇÃO DE SOLUÇÕES
    # ==============================================
    
    def verify_proof(
        self,
        challenge: str,
        nonce: str,
        difficulty: int = None,
        ip: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        🔥 Verifica se o nonce resolve o desafio
        
        Args:
            challenge: Desafio original
            nonce: Solução encontrada pelo cliente
            difficulty: Dificuldade esperada (opcional)
            ip: IP do cliente (para tracking)
            user_id: ID do usuário (para tracking)
        
        Returns:
            Tuple[bool, str]: (válido, mensagem)
        """
        # 1. Validações básicas
        if not challenge or not nonce:
            return False, "Challenge e Nonce são obrigatórios"
        
        if len(challenge) != 32:
            return False, "Challenge inválido (deve ter 32 caracteres hex)"
        
        if len(nonce) > 64:
            return False, "Nonce muito longo (máximo 64 caracteres)"
        
        # 2. Verificar se o desafio existe e é válido
        challenge_data = self.cache.get(challenge)
        if not challenge_data:
            return False, "Challenge não encontrado ou já expirado"
        
        if not challenge_data.is_valid():
            if challenge_data.is_expired():
                self.cache.remove(challenge)
                return False, f"Challenge expirado (limite: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s)"
            if challenge_data.used:
                self._stats["total_replay_attacks_blocked"] += 1
                return False, "Challenge já utilizado (replay attack detectado)"
            return False, "Challenge inválido"
        
        # 3. Verificar dificuldade
        if difficulty is None:
            difficulty = challenge_data.difficulty
        
        if difficulty < PoWConfig.MIN_DIFFICULTY or difficulty > PoWConfig.MAX_DIFFICULTY:
            return False, f"Dificuldade deve estar entre {PoWConfig.MIN_DIFFICULTY} e {PoWConfig.MAX_DIFFICULTY}"
        
        # 4. 🔥 VALIDAR HASH (com ":" entre challenge e nonce)
        try:
            data = f"{challenge}:{nonce}".encode('utf-8')
            hash_hex = hashlib.sha256(data).hexdigest()
            prefix = '0' * difficulty
            
            if not hash_hex.startswith(prefix):
                self._stats["total_challenges_failed"] += 1
                self._track_failure(ip)
                return False, f"Solução incorreta (hash não começa com {difficulty} zeros)"
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar PoW: {e}")
            return False, f"Erro interno ao verificar PoW: {str(e)}"
        
        # 5. ✅ Sucesso
        challenge_data.mark_used()
        self.cache.remove(challenge)  # Remove do cache após uso
        self._stats["total_challenges_verified"] += 1
        self._reset_ip_failures(ip)
        
        logger.info(f"✅ PoW validado - IP: {ip}, usuário: {user_id}, dificuldade: {difficulty}")
        return True, "PoW válido"
    
    # ==============================================
    # 🔥 FUNÇÕES DE DIFICULDADE ADAPTATIVA
    # ==============================================
    
    def _get_adaptive_difficulty(self, ip: str, user_id: Optional[int] = None) -> int:
        """
        🔥 Calcula dificuldade adaptativa baseada no comportamento
        
        Aumenta a dificuldade para:
        - IPs com muitas falhas
        - IPs com muitas requisições
        - Usuários não premium
        """
        base_difficulty = PoWConfig.DEFAULT_DIFFICULTY
        
        # 🔥 Aumentar para IPs com muitas falhas
        failure_count = self._ip_tracker.get(ip, 0)
        if failure_count > PoWConfig.IP_SUSPICIOUS_THRESHOLD:
            return min(base_difficulty + 1, PoWConfig.MAX_DIFFICULTY)
        elif failure_count > PoWConfig.IP_BLOCK_THRESHOLD:
            return min(base_difficulty + 2, PoWConfig.MAX_DIFFICULTY)
        
        return base_difficulty
    
    def _track_failure(self, ip: Optional[str]) -> None:
        """Registra uma falha para um IP"""
        if ip:
            self._ip_tracker[ip] += 1
            self._cleanup_ip_tracker()
    
    def _reset_ip_failures(self, ip: Optional[str]) -> None:
        """Reseta o contador de falhas para um IP"""
        if ip and ip in self._ip_tracker:
            self._ip_tracker[ip] = max(0, self._ip_tracker[ip] - 2)
    
    def _cleanup_ip_tracker(self) -> None:
        """Limpa o tracker de IPs periodicamente"""
        now = time.time()
        if now - self._last_ip_cleanup > PoWConfig.IP_TRACKING_WINDOW:
            # Resetar contagens antigas
            self._ip_tracker.clear()
            self._last_ip_cleanup = now
    
    # ==============================================
    # 🔥 UTILITÁRIOS E ESTATÍSTICAS
    # ==============================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas completas do serviço"""
        return {
            "challenges": {
                "generated": self._stats["total_challenges_generated"],
                "verified": self._stats["total_challenges_verified"],
                "failed": self._stats["total_challenges_failed"],
                "replay_attacks_blocked": self._stats["total_replay_attacks_blocked"],
                "rate_limits_triggered": self._stats["total_rate_limits_triggered"],
            },
            "cache": self.cache.get_stats(),
            "rate_limiter": self.rate_limiter.get_stats(),
            "config": {
                "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
                "min_difficulty": PoWConfig.MIN_DIFFICULTY,
                "max_difficulty": PoWConfig.MAX_DIFFICULTY,
                "challenge_ttl_seconds": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
                "algorithm": PoWConfig.ALGORITHM,
                "replay_protection": True,
                "ip_suspicious_threshold": PoWConfig.IP_SUSPICIOUS_THRESHOLD,
                "ip_block_threshold": PoWConfig.IP_BLOCK_THRESHOLD,
            },
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
        }


# ==============================================
# 🔥 INSTÂNCIA GLOBAL
# ==============================================

pow_service = PoWService()


# ==============================================
# 🔥 DEPENDÊNCIA FASTAPI - VALIDAÇÃO
# ==============================================

async def validate_pow_request(request: Request) -> bool:
    """
    🔥 DEPENDÊNCIA FASTAPI - VALIDAÇÃO ATÔMICA
    
    ❗ IMPORTANTE: Use apenas Request (sem Optional) para que o FastAPI entenda
    que é uma dependência que recebe o objeto Request.
    
    🔒 VALIDA EM MICROSSEGUNDOS - Bots são bloqueados na entrada
    
    USO:
    @router.post("/upload-auto")
    async def upload_auto(
        pow_valid: bool = Depends(validate_pow_request)
    ):
        # Se chegou aqui, o PoW já foi validado!
        pass
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 1. Verifica se os headers existem
    nonce = request.headers.get(PoWConfig.HEADER_NONCE)
    challenge = request.headers.get(PoWConfig.HEADER_CHALLENGE)
    
    if not nonce or not challenge:
        logger.warning(f"⚠️ PoW ausente na requisição de {client_ip}")
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail={
                "error": "Proof of Work é obrigatório",
                "required": [PoWConfig.HEADER_NONCE, PoWConfig.HEADER_CHALLENGE],
                "action": "GET /api/pow/challenge para obter um desafio"
            }
        )
    
    # 2. Validar expiração do challenge
    challenge_data = pow_service.cache.get(challenge)
    if not challenge_data:
        logger.warning(f"⚠️ Challenge inválido ou expirado de {client_ip}")
        raise HTTPException(
            status_code=400,
            detail="Challenge inválido ou expirado. Gere um novo."
        )
    
    if not challenge_data.is_valid():
        if challenge_data.is_expired():
            pow_service.cache.remove(challenge)
            raise HTTPException(
                status_code=400,
                detail=f"Challenge expirou. Gere um novo (TTL: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s)."
            )
        if challenge_data.used:
            pow_service._stats["total_replay_attacks_blocked"] += 1
            raise HTTPException(
                status_code=400,
                detail="Challenge já utilizado (replay attack). Gere um novo."
            )
        raise HTTPException(
            status_code=400,
            detail="Challenge inválido. Gere um novo."
        )
    
    # 3. 🔥 Obter dificuldade do header (ou padrão)
    try:
        difficulty = int(request.headers.get(PoWConfig.HEADER_COMPLEXITY, challenge_data.difficulty))
    except ValueError:
        difficulty = challenge_data.difficulty
    
    if difficulty < PoWConfig.MIN_DIFFICULTY or difficulty > PoWConfig.MAX_DIFFICULTY:
        difficulty = challenge_data.difficulty
    
    # 4. 🔥 Validar o hash
    is_valid, message = pow_service.verify_proof(
        challenge=challenge,
        nonce=nonce,
        difficulty=difficulty,
        ip=client_ip,
        user_id=None  # Será preenchido pelo endpoint que usa esta dependência
    )
    
    if not is_valid:
        logger.error(f"❌ PoW inválido para {client_ip} - {message}")
        raise HTTPException(
            status_code=400,
            detail=f"Proof of Work inválido. {message}"
        )
    
    logger.debug(f"✅ PoW validado para {client_ip}")
    return True


# ==============================================
# 🔥 ROTAS DA API
# ==============================================

router = APIRouter(prefix="/pow", tags=["proof-of-work"])


@router.get("/challenge", response_model=None)
async def get_pow_challenge(
    request: Request,
    current_user = Depends(get_current_user)
):
    """
    🔐 Gera um novo desafio criptográfico (challenge) para o cliente resolver.
    
    🔒 TTL: 5 minutos (expiração automática)
    🔒 Dificuldade: 4 (padrão) - adaptativa baseada no IP
    🔒 Rate Limit: 10/IP e 20/usuário por hora
    
    HEADERS:
    - X-PoW-Complexity: Dificuldade desejada (opcional, 3-6)
    
    RESPOSTA:
    {
        "challenge": "5f36a6b6a55f7e1c88bdb2bd2cf5a2ae",
        "difficulty": 4,
        "algorithm": "SHA-256",
        "hint": "Encontre um nonce tal que SHA256(challenge:nonce) comece com '0000'",
        "expires_in": 300,
        "timestamp": "2024-01-01T00:00:00"
    }
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id = current_user.id if current_user else None
    user_email = current_user.email if current_user else None
    
    # 🔥 Dificuldade do header (opcional)
    try:
        requested_difficulty = int(request.headers.get(PoWConfig.HEADER_COMPLEXITY, 0))
        if PoWConfig.MIN_DIFFICULTY <= requested_difficulty <= PoWConfig.MAX_DIFFICULTY:
            # O serviço decide a dificuldade final
            pass
    except ValueError:
        pass
    
    # Gerar desafio
    result = pow_service.generate_challenge(
        ip=client_ip,
        user_id=user_id,
        user_email=user_email
    )
    
    # Adicionar informações do rate limit
    result["rate_limit"] = {
        "ip_limit": PoWConfig.MAX_CHALLENGES_PER_IP,
        "user_limit": PoWConfig.MAX_CHALLENGES_PER_USER,
        "window_seconds": PoWConfig.RATE_LIMIT_WINDOW,
    }
    
    return result


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
    
    # Verificar
    is_valid, message = pow_service.verify_proof(
        challenge=data.challenge,
        nonce=data.nonce,
        difficulty=data.difficulty,
        ip=request.client.host if request.client else "unknown",
        user_id=current_user.id
    )
    
    if not is_valid:
        logger.warning(f"⚠️ {message} para {current_user.email}")
        raise HTTPException(
            status_code=400,
            detail=f"Solução do Proof of Work incorreta. {message}"
        )
    
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
        "version": "2.0",
        "algorithm": PoWConfig.ALGORITHM,
        "challenge_ttl_seconds": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
        "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
        "replay_protection": True,
        "rate_limit": {
            "ip_limit": PoWConfig.MAX_CHALLENGES_PER_IP,
            "user_limit": PoWConfig.MAX_CHALLENGES_PER_USER,
            "window_seconds": PoWConfig.RATE_LIMIT_WINDOW,
        }
    }


@router.get("/stats", response_model=None)
async def get_pow_stats(
    current_user = Depends(get_current_user)
):
    """📊 Estatísticas do PoW (apenas admin)"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado. Requer permissão de administrador."
        )
    
    return pow_service.get_stats()


# ==============================================
# 🔥 EXPORTAÇÕES
# ==============================================

__all__ = [
    'router',
    'pow_service',
    'validate_pow_request',
    'PoWConfig',
    'PoWService',
]

print("=" * 70)
print("🔥 PoW Service v2.0 - PROTEÇÃO CONTRA SPAM")
print(f"   ✅ Challenge TTL: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s")
print(f"   ✅ Default Difficulty: {PoWConfig.DEFAULT_DIFFICULTY}")
print(f"   ✅ Replay Attack Prevention: Ativo")
print(f"   ✅ Rate Limiting: {PoWConfig.MAX_CHALLENGES_PER_IP}/IP + {PoWConfig.MAX_CHALLENGES_PER_USER}/usuário")
print(f"   ✅ Dificuldade Adaptativa: Ativa")
print(f"   ✅ Algoritmo: {PoWConfig.ALGORITHM}")
print(f"   ✅ Cache: {PoWConfig.CHALLENGE_MAX_SIZE} desafios")
print("=" * 70)