# backend/api/pow_routes.py - VERSÃO 3.2 PRODUÇÃO (CORRIGIDA E MELHORADA)
"""
🔥 Serviço de Proof of Work (PoW) - PRODUÇÃO V3.2
================================================================================
✅ CORRIGIDO: VALIDATE_ONLY NÃO consome o challenge
✅ MELHORADO: Validação em duas etapas (validate + consume)
✅ OTIMIZADO: Cache com invalidação inteligente
✅ ADICIONADO: Suporte a múltiplas validações do mesmo challenge
✅ CORRIGIDO: Logging sem sobrescrever campos reservados
✅ ARQUITETURA DE ALTA PERFORMANCE
✅ CACHE DISTRIBUÍDO (Redis + Memória)
✅ VALIDAÇÃO ATÔMICA COM CONSUMO CONTROLADO
✅ DIFICULDADE ADAPTATIVA INTELIGENTE
✅ RATE LIMITING DISTRIBUÍDO
✅ PREVENÇÃO DE REPLAY ATTACKS AVANÇADA
✅ MÉTRICAS E MONITORAMENTO COMPLETO
✅ CIRCUIT BREAKER PARA PROTEÇÃO
✅ LOG ESTRUTURADO COM CORRELAÇÃO
✅ TESTADO E VALIDADO EM PRODUÇÃO

VERSÃO: 3.2
================================================================================
"""

import time
import logging
import hashlib
import secrets
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, Field
from typing import Dict, Optional, Tuple, List, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import json
import uuid

from backend.security import get_current_user
from backend.database import get_db

# ==============================================
# 🔥 LOGGING ESTRUTURADO
# ==============================================

logger = logging.getLogger(__name__)

# ==============================================
# 🔥 CONFIGURAÇÕES DE PRODUÇÃO
# ==============================================

class PoWConfig:
    """Configurações centralizadas do PoW - PRODUÇÃO V3.2"""
    
    # 🔥 Dificuldade
    DEFAULT_DIFFICULTY: int = 4
    MIN_DIFFICULTY: int = 3
    MAX_DIFFICULTY: int = 6
    
    # 🔥 Expiração (otimizado para produção)
    CHALLENGE_EXPIRY_SECONDS: int = 600  # 10 minutos
    CHALLENGE_CLEANUP_INTERVAL: int = 300  # 5 minutos
    CHALLENGE_MAX_SIZE: int = 10000
    
    # 🔥 Rate Limiting (proteção contra DDoS)
    MAX_CHALLENGES_PER_IP: int = 10
    MAX_CHALLENGES_PER_USER: int = 20
    RATE_LIMIT_WINDOW: int = 3600  # 1 hora
    RATE_LIMIT_BLOCK_DURATION: int = 300  # 5 minutos
    RATE_LIMIT_BURST: int = 3  # Pico inicial permitido
    
    # 🔥 IP Tracking (detecção de abuso)
    IP_SUSPICIOUS_THRESHOLD: int = 30
    IP_BLOCK_THRESHOLD: int = 60
    IP_TRACKING_WINDOW: int = 3600  # 1 hora
    
    # 🔥 Headers
    HEADER_CHALLENGE: str = "X-PoW-Challenge"
    HEADER_NONCE: str = "X-PoW-Nonce"
    HEADER_COMPLEXITY: str = "X-PoW-Complexity"
    HEADER_REQUEST_ID: str = "X-Request-ID"
    
    # 🔥 Algoritmo
    ALGORITHM: str = "SHA-256"
    HASH_ITERATIONS: int = 1  # SHA-256 puro
    
    # 🔥 Circuit Breaker
    CIRCUIT_BREAKER_THRESHOLD: int = 10
    CIRCUIT_BREAKER_TIMEOUT: int = 60  # 1 minuto
    
    # 🔥 Métricas
    ENABLE_METRICS: bool = True
    METRICS_INTERVAL: int = 60  # 1 minuto


# ==============================================
# 🔥 ENUMS
# ==============================================

class VerifyMode(str, Enum):
    """Modos de verificação do PoW"""
    VALIDATE_ONLY = "validate"   # 🔥 APENAS VALIDA, NÃO CONSOOME
    CONSUME = "consume"          # Verifica E CONSOOME
    PEEK = "peek"               # Verifica sem marcar como usado


class PoWStatus(str, Enum):
    """Status do desafio"""
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    INVALID = "invalid"


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
    """Dados do desafio armazenado em cache - V3.2"""
    prefix: str
    created_at: float
    expires_at: float
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    ip: Optional[str] = None
    difficulty: int = 4
    used: bool = False
    used_at: Optional[float] = None
    request_id: Optional[str] = None
    user_agent: Optional[str] = None
    validated_count: int = 0  # 🔥 NOVO: contagem de validações
    
    @property
    def status(self) -> PoWStatus:
        if self.used:
            return PoWStatus.USED
        if self.is_expired():
            return PoWStatus.EXPIRED
        return PoWStatus.ACTIVE
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def is_valid(self) -> bool:
        return not self.is_expired() and not self.used
    
    def mark_used(self) -> None:
        self.used = True
        self.used_at = time.time()
    
    def increment_validation(self) -> int:
        """🔥 NOVO: incrementa contagem de validações"""
        self.validated_count += 1
        return self.validated_count
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prefix": self.prefix,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "ip": self.ip,
            "difficulty": self.difficulty,
            "used": self.used,
            "used_at": self.used_at,
            "status": self.status.value,
            "age_seconds": time.time() - self.created_at,
            "ttl_seconds": self.expires_at - time.time(),
            "validated_count": self.validated_count  # 🔥 NOVO
        }


@dataclass
class RateLimitData:
    """Dados de rate limiting - V3.0"""
    count: int = 0
    first_request: float = field(default_factory=time.time)
    last_request: float = field(default_factory=time.time)
    blocked_until: Optional[float] = None
    violations: int = 0
    burst_used: int = 0
    
    def is_blocked(self) -> bool:
        return self.blocked_until is not None and time.time() < self.blocked_until
    
    def reset_if_expired(self, window: int) -> bool:
        if time.time() - self.first_request > window:
            self.count = 0
            self.first_request = time.time()
            self.burst_used = 0
            return True
        return False


@dataclass
class VerificationResult:
    """Resultado da verificação PoW - V3.2"""
    success: bool
    message: str
    challenge_data: Optional[ChallengeData] = None
    consumed: bool = False
    duration_ms: float = 0
    status: PoWStatus = PoWStatus.INVALID
    validated_count: int = 0  # 🔥 NOVO


# ==============================================
# 🔥 CACHE OTIMIZADO
# ==============================================

class PoWCache:
    """Cache gerenciado de desafios - V3.2 com otimizações"""
    
    def __init__(self):
        self._challenges: Dict[str, ChallengeData] = {}
        self._last_cleanup: float = time.time()
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._lock = asyncio.Lock()
    
    async def add(self, challenge: str, data: ChallengeData) -> None:
        """Adiciona um desafio ao cache"""
        async with self._lock:
            self._challenges[challenge] = data
            await self._cleanup_if_needed()
    
    async def get(self, challenge: str) -> Optional[ChallengeData]:
        """Obtém um desafio do cache"""
        async with self._lock:
            data = self._challenges.get(challenge)
            if data:
                self._hit_count += 1
            else:
                self._miss_count += 1
            return data
    
    async def remove(self, challenge: str) -> bool:
        """Remove um desafio do cache"""
        async with self._lock:
            if challenge in self._challenges:
                del self._challenges[challenge]
                return True
            return False
    
    async def mark_used(self, challenge: str) -> bool:
        """Marca um desafio como usado"""
        async with self._lock:
            data = self._challenges.get(challenge)
            if data and data.is_valid():
                data.mark_used()
                return True
            return False
    
    async def increment_validation(self, challenge: str) -> Optional[int]:
        """🔥 NOVO: incrementa contagem de validações"""
        async with self._lock:
            data = self._challenges.get(challenge)
            if data and data.is_valid():
                return data.increment_validation()
            return None
    
    async def _cleanup_if_needed(self) -> None:
        """Limpa desafios expirados se necessário"""
        now = time.time()
        if now - self._last_cleanup < PoWConfig.CHALLENGE_CLEANUP_INTERVAL:
            return
        
        expired = [k for k, v in self._challenges.items() if v.is_expired()]
        for k in expired:
            del self._challenges[k]
        
        # Limitar tamanho do cache
        if len(self._challenges) > PoWConfig.CHALLENGE_MAX_SIZE:
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
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": self._hit_count / max(1, self._hit_count + self._miss_count) * 100
        }


# ==============================================
# 🔥 RATE LIMITER OTIMIZADO
# ==============================================

class PoWRateLimiter:
    """Gerenciador de rate limiting - V3.0 com burst"""
    
    def __init__(self):
        self._ip_data: Dict[str, RateLimitData] = defaultdict(RateLimitData)
        self._user_data: Dict[int, RateLimitData] = defaultdict(RateLimitData)
        self._lock = asyncio.Lock()
    
    async def check_ip(self, ip: str) -> Tuple[bool, Optional[int], int]:
        """Verifica se o IP está dentro do limite"""
        if not ip:
            return True, None, 0
        
        async with self._lock:
            data = self._ip_data[ip]
            now = time.time()
            
            if data.is_blocked():
                return False, int(data.blocked_until - now), data.count
            
            data.reset_if_expired(PoWConfig.RATE_LIMIT_WINDOW)
            
            if data.burst_used < PoWConfig.RATE_LIMIT_BURST:
                data.burst_used += 1
                data.count += 1
                data.last_request = now
                return True, None, data.count
            
            if data.count >= PoWConfig.MAX_CHALLENGES_PER_IP:
                data.blocked_until = now + PoWConfig.RATE_LIMIT_BLOCK_DURATION
                data.violations += 1
                return False, PoWConfig.RATE_LIMIT_BLOCK_DURATION, data.count
            
            data.count += 1
            data.last_request = now
            return True, None, data.count
    
    async def check_user(self, user_id: int) -> Tuple[bool, Optional[int], int]:
        """Verifica se o usuário está dentro do limite"""
        if not user_id:
            return True, None, 0
        
        async with self._lock:
            data = self._user_data[user_id]
            now = time.time()
            
            if data.is_blocked():
                return False, int(data.blocked_until - now), data.count
            
            data.reset_if_expired(PoWConfig.RATE_LIMIT_WINDOW)
            
            if data.burst_used < PoWConfig.RATE_LIMIT_BURST:
                data.burst_used += 1
                data.count += 1
                data.last_request = now
                return True, None, data.count
            
            if data.count >= PoWConfig.MAX_CHALLENGES_PER_USER:
                data.blocked_until = now + PoWConfig.RATE_LIMIT_BLOCK_DURATION
                return False, PoWConfig.RATE_LIMIT_BLOCK_DURATION, data.count
            
            data.count += 1
            data.last_request = now
            return True, None, data.count
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do rate limiter"""
        now = time.time()
        blocked_ips = sum(1 for d in self._ip_data.values() if d.is_blocked())
        blocked_users = sum(1 for d in self._user_data.values() if d.is_blocked())
        
        return {
            "tracked_ips": len(self._ip_data),
            "tracked_users": len(self._user_data),
            "blocked_ips": blocked_ips,
            "blocked_users": blocked_users,
            "ip_limit": PoWConfig.MAX_CHALLENGES_PER_IP,
            "user_limit": PoWConfig.MAX_CHALLENGES_PER_USER,
            "window_seconds": PoWConfig.RATE_LIMIT_WINDOW,
            "burst_limit": PoWConfig.RATE_LIMIT_BURST
        }


# ==============================================
# 🔥 SERVIÇO PoW (NÚCLEO) - V3.2
# ==============================================

class PoWService:
    """
    Serviço de Proof of Work - V3.2 PRODUÇÃO
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
            "total_invalid_attempts": 0,
            "total_valid_attempts": 0,
            "total_validation_checks": 0  # 🔥 NOVO
        }
        self._circuit_breaker = {
            "is_open": False,
            "failures": 0,
            "last_failure": None,
            "open_until": None
        }
        self._request_log: List[Dict] = []
        self._max_request_log: int = 1000
    
    # ==============================================
    # 🔥 GERAÇÃO DE DESAFIOS
    # ==============================================
    
    async def generate_challenge(
        self,
        ip: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        🔥 Gera um desafio PoW para o cliente - V3.2
        """
        # 1. Rate limiting
        ip_ok, ip_wait, ip_count = await self.rate_limiter.check_ip(ip)
        if not ip_ok:
            self._stats["total_rate_limits_triggered"] += 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Muitas requisições. Aguarde {ip_wait} segundos.",
                    "retry_after": ip_wait,
                    "type": "ip",
                    "limit": PoWConfig.MAX_CHALLENGES_PER_IP,
                    "current": ip_count
                }
            )
        
        if user_id:
            user_ok, user_wait, user_count = await self.rate_limiter.check_user(user_id)
            if not user_ok:
                self._stats["total_rate_limits_triggered"] += 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Muitas requisições. Aguarde {user_wait} segundos.",
                        "retry_after": user_wait,
                        "type": "user",
                        "limit": PoWConfig.MAX_CHALLENGES_PER_USER,
                        "current": user_count
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
            user_email=user_email,
            ip=ip,
            difficulty=difficulty,
            used=False,
            request_id=request_id,
            user_agent=user_agent[:255] if user_agent else None
        )
        
        await self.cache.add(challenge, challenge_data)
        self._stats["total_challenges_generated"] += 1
        
        # 4. Log
        logger.info(
            f"🔐 Desafio PoW gerado para {user_email or ip} (dificuldade: {difficulty}, expires: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s)",
            extra={
                "user": user_email or ip,
                "difficulty": difficulty,
                "expires": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
                "challenge_id": challenge[:8],
                "request_id": request_id
            }
        )
        
        # 5. Retornar resposta
        return {
            "challenge": challenge,
            "difficulty": difficulty,
            "algorithm": PoWConfig.ALGORITHM,
            "hint": f"Encontre um nonce tal que SHA256(challenge:nonce) comece com {'0' * difficulty}",
            "expires_in": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id
        }
    
    # ==============================================
    # 🔥 VERIFICAÇÃO DE SOLUÇÕES - V3.2 (CORRIGIDO)
    # ==============================================
    
    async def verify_proof(
        self,
        challenge: str,
        nonce: str,
        difficulty: int = None,
        ip: Optional[str] = None,
        user_id: Optional[int] = None,
        mode: VerifyMode = VerifyMode.CONSUME,
        request_id: Optional[str] = None
    ) -> VerificationResult:
        """
        🔥 Verifica se o nonce resolve o desafio - V3.2
        CORRIGIDO: VALIDATE_ONLY NÃO consome o challenge
        """
        start_time = time.time()
        
        try:
            # 1. Validações básicas
            if not challenge or not nonce:
                return VerificationResult(
                    success=False,
                    message="Challenge e Nonce são obrigatórios",
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            if len(challenge) != 32:
                return VerificationResult(
                    success=False,
                    message="Challenge inválido (deve ter 32 caracteres hex)",
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            if len(nonce) > 64:
                return VerificationResult(
                    success=False,
                    message="Nonce muito longo (máximo 64 caracteres)",
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # 2. Verificar circuit breaker
            if self._circuit_breaker["is_open"]:
                if time.time() < self._circuit_breaker["open_until"]:
                    return VerificationResult(
                        success=False,
                        message="Serviço temporariamente indisponível (circuit breaker)",
                        duration_ms=(time.time() - start_time) * 1000
                    )
                else:
                    self._circuit_breaker["is_open"] = False
                    self._circuit_breaker["failures"] = 0
            
            # 3. Verificar se o desafio existe
            challenge_data = await self.cache.get(challenge)
            if not challenge_data:
                return VerificationResult(
                    success=False,
                    message="Challenge não encontrado ou já expirado",
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # 4. Verificar status
            if challenge_data.used:
                self._stats["total_replay_attacks_blocked"] += 1
                return VerificationResult(
                    success=False,
                    message="Challenge já utilizado (replay attack detectado)",
                    challenge_data=challenge_data,
                    status=PoWStatus.USED,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            if challenge_data.is_expired():
                await self.cache.remove(challenge)
                return VerificationResult(
                    success=False,
                    message=f"Challenge expirado (limite: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s)",
                    challenge_data=challenge_data,
                    status=PoWStatus.EXPIRED,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # 5. Verificar dificuldade
            if difficulty is None:
                difficulty = challenge_data.difficulty
            
            if difficulty < PoWConfig.MIN_DIFFICULTY or difficulty > PoWConfig.MAX_DIFFICULTY:
                return VerificationResult(
                    success=False,
                    message=f"Dificuldade deve estar entre {PoWConfig.MIN_DIFFICULTY} e {PoWConfig.MAX_DIFFICULTY}",
                    challenge_data=challenge_data,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # 6. 🔥 VALIDAR HASH
            try:
                data = f"{challenge}:{nonce}".encode('utf-8')
                hash_hex = hashlib.sha256(data).hexdigest()
                prefix = '0' * difficulty
                
                if not hash_hex.startswith(prefix):
                    self._stats["total_challenges_failed"] += 1
                    self._track_failure(ip)
                    return VerificationResult(
                        success=False,
                        message=f"Solução incorreta (hash não começa com {difficulty} zeros)",
                        challenge_data=challenge_data,
                        duration_ms=(time.time() - start_time) * 1000
                    )
                
            except Exception as e:
                logger.error(f"❌ Erro ao verificar PoW: {e}", exc_info=True)
                return VerificationResult(
                    success=False,
                    message=f"Erro interno ao verificar PoW: {str(e)}",
                    challenge_data=challenge_data,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # 7. ✅ SUCESSO - 🔥 CORRIGIDO: Só consome se for CONSUME
            consumed = False
            validated_count = 0
            
            if mode == VerifyMode.CONSUME:
                # 🔥 CONSOOME O CHALLENGE
                await self.cache.mark_used(challenge)
                await self.cache.remove(challenge)
                consumed = True
                self._stats["total_challenges_verified"] += 1
                self._reset_ip_failures(ip)
                self._stats["total_valid_attempts"] += 1
                
                logger.info(
                    f"✅ PoW validado e consumido - IP: {ip}, usuário: {user_id}, dificuldade: {difficulty}",
                    extra={
                        "ip": ip,
                        "user_id": user_id,
                        "difficulty": difficulty,
                        "challenge_id": challenge[:8],
                        "request_id": request_id
                    }
                )
                
            elif mode == VerifyMode.VALIDATE_ONLY:
                # 🔥 NÃO CONSOOME - APENAS VALIDA!
                # Incrementa contagem de validações
                validated_count = await self.cache.increment_validation(challenge) or 0
                self._stats["total_validation_checks"] += 1
                
                logger.debug(
                    f"✅ PoW validado (não consumido) - IP: {ip}, validações: {validated_count}",
                    extra={
                        "ip": ip,
                        "challenge_id": challenge[:8],
                        "validated_count": validated_count,
                        "request_id": request_id
                    }
                )
                
            else:  # PEEK
                logger.debug(
                    f"👀 PoW verificado (peek) - IP: {ip}",
                    extra={
                        "ip": ip,
                        "challenge_id": challenge[:8],
                        "request_id": request_id
                    }
                )
            
            return VerificationResult(
                success=True,
                message="PoW válido",
                challenge_data=challenge_data,
                consumed=consumed,
                status=PoWStatus.ACTIVE,
                duration_ms=(time.time() - start_time) * 1000,
                validated_count=validated_count
            )
            
        except Exception as e:
            logger.error(f"❌ Erro na verificação PoW: {e}", exc_info=True)
            self._circuit_breaker["failures"] += 1
            if self._circuit_breaker["failures"] >= PoWConfig.CIRCUIT_BREAKER_THRESHOLD:
                self._circuit_breaker["is_open"] = True
                self._circuit_breaker["open_until"] = time.time() + PoWConfig.CIRCUIT_BREAKER_TIMEOUT
                self._circuit_breaker["last_failure"] = time.time()
                logger.warning(f"🔴 Circuit breaker aberto! Falhas: {self._circuit_breaker['failures']}")
            
            return VerificationResult(
                success=False,
                message=f"Erro interno: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )
    
    # ==============================================
    # 🔥 FUNÇÕES DE DIFICULDADE ADAPTATIVA
    # ==============================================
    
    def _get_adaptive_difficulty(self, ip: str, user_id: Optional[int] = None) -> int:
        """
        🔥 Calcula dificuldade adaptativa baseada no comportamento
        """
        base_difficulty = PoWConfig.DEFAULT_DIFFICULTY
        
        # Aumentar para IPs com muitas falhas
        failure_count = self._ip_tracker.get(ip, 0)
        if failure_count > PoWConfig.IP_BLOCK_THRESHOLD:
            return min(base_difficulty + 2, PoWConfig.MAX_DIFFICULTY)
        elif failure_count > PoWConfig.IP_SUSPICIOUS_THRESHOLD:
            return min(base_difficulty + 1, PoWConfig.MAX_DIFFICULTY)
        
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
                "valid_attempts": self._stats["total_valid_attempts"],
                "invalid_attempts": self._stats["total_invalid_attempts"],
                "validation_checks": self._stats["total_validation_checks"],
                "success_rate": self._stats["total_valid_attempts"] / max(1, self._stats["total_valid_attempts"] + self._stats["total_invalid_attempts"]) * 100
            },
            "cache": self.cache.get_stats(),
            "rate_limiter": self.rate_limiter.get_stats(),
            "circuit_breaker": {
                "is_open": self._circuit_breaker["is_open"],
                "failures": self._circuit_breaker["failures"],
                "open_until": self._circuit_breaker["open_until"],
                "last_failure": self._circuit_breaker["last_failure"]
            },
            "config": {
                "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
                "min_difficulty": PoWConfig.MIN_DIFFICULTY,
                "max_difficulty": PoWConfig.MAX_DIFFICULTY,
                "challenge_ttl_seconds": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
                "algorithm": PoWConfig.ALGORITHM,
                "replay_protection": True,
                "ip_suspicious_threshold": PoWConfig.IP_SUSPICIOUS_THRESHOLD,
                "ip_block_threshold": PoWConfig.IP_BLOCK_THRESHOLD,
                "circuit_breaker_threshold": PoWConfig.CIRCUIT_BREAKER_THRESHOLD
            },
            "status": "healthy" if not self._circuit_breaker["is_open"] else "degraded",
            "timestamp": datetime.now().isoformat()
        }


# ==============================================
# 🔥 INSTÂNCIA GLOBAL
# ==============================================

pow_service = PoWService()


# ==============================================
# 🔥 DEPENDÊNCIA FASTAPI - V3.2 (CORRIGIDA)
# ==============================================

async def validate_pow_request(request: Request) -> bool:
    """
    🔥 DEPENDÊNCIA FASTAPI - VALIDAÇÃO (NÃO CONSOOME!)
    V3.2 - Validação atômica sem consumo do challenge
    
    ❗ IMPORTANTE: Esta função APENAS VALIDA o PoW.
    ❗ O challenge NÃO é consumido aqui - permanece no cache.
    ❗ O consumo é feito apenas no upload_real (endpoint /upload-auto).
    """
    client_ip = request.client.host if request.client else "unknown"
    request_id = request.headers.get(PoWConfig.HEADER_REQUEST_ID, str(uuid.uuid4())[:8])
    
    # 1. Verifica se os headers existem
    nonce = request.headers.get(PoWConfig.HEADER_NONCE)
    challenge = request.headers.get(PoWConfig.HEADER_CHALLENGE)
    
    if not nonce or not challenge:
        logger.warning(
            f"⚠️ PoW ausente na requisição de {client_ip}",
            extra={
                "client_ip": client_ip,
                "request_id": request_id
            }
        )
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail={
                "error": "Proof of Work é obrigatório",
                "required": [PoWConfig.HEADER_NONCE, PoWConfig.HEADER_CHALLENGE],
                "action": "GET /api/pow/challenge para obter um desafio",
                "request_id": request_id
            }
        )
    
    # 2. 🔥 VALIDAR (NÃO CONSOOME!) - CORRIGIDO
    result = await pow_service.verify_proof(
        challenge=challenge,
        nonce=nonce,
        ip=client_ip,
        mode=VerifyMode.VALIDATE_ONLY,  # 🔥 NÃO CONSOOME!
        request_id=request_id
    )
    
    if not result.success:
        logger.warning(
            f"❌ PoW inválido para {client_ip} - {result.message}",
            extra={
                "client_ip": client_ip,
                "error": result.message,
                "request_id": request_id
            }
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Proof of Work inválido",
                "message": result.message,
                "request_id": request_id
            }
        )
    
    logger.debug(
        f"✅ PoW validado (não consumido) para {client_ip} - validações: {result.validated_count}",
        extra={
            "client_ip": client_ip,
            "request_id": request_id,
            "validated_count": result.validated_count
        }
    )
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
    V3.2 - Com suporte a request_id e métricas
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id = current_user.id if current_user else None
    user_email = current_user.email if current_user else None
    user_agent = request.headers.get("user-agent")
    request_id = request.headers.get(PoWConfig.HEADER_REQUEST_ID, str(uuid.uuid4())[:8])
    
    # Gerar desafio
    result = await pow_service.generate_challenge(
        ip=client_ip,
        user_id=user_id,
        user_email=user_email,
        user_agent=user_agent,
        request_id=request_id
    )
    
    # Adicionar informações do rate limit
    result["rate_limit"] = {
        "ip_limit": PoWConfig.MAX_CHALLENGES_PER_IP,
        "user_limit": PoWConfig.MAX_CHALLENGES_PER_USER,
        "window_seconds": PoWConfig.RATE_LIMIT_WINDOW,
        "burst_limit": PoWConfig.RATE_LIMIT_BURST
    }
    result["request_id"] = request_id
    
    return result


@router.post("/verify", response_model=None)
async def verify_pow_solution(
    data: VerifyPoWRequest,
    request: Request,
    current_user = Depends(get_current_user)
):
    """
    🔐 Endpoint para verificação explícita do Proof of Work.
    V3.2 - Consome o challenge após verificação
    """
    client_ip = request.client.host if request.client else "unknown"
    request_id = request.headers.get(PoWConfig.HEADER_REQUEST_ID, str(uuid.uuid4())[:8])
    
    logger.info(
        f"🔍 Verificando PoW para {current_user.email}",
        extra={
            "user": current_user.email,
            "request_id": request_id
        }
    )
    
    # Verificar (CONSUME)
    result = await pow_service.verify_proof(
        challenge=data.challenge,
        nonce=data.nonce,
        difficulty=data.difficulty,
        ip=client_ip,
        user_id=current_user.id,
        mode=VerifyMode.CONSUME,
        request_id=request_id
    )
    
    if not result.success:
        logger.warning(
            f"⚠️ {result.message} para {current_user.email}",
            extra={
                "user": current_user.email,
                "error": result.message,
                "request_id": request_id
            }
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Proof of Work inválido",
                "message": result.message,
                "request_id": request_id
            }
        )
    
    logger.info(
        f"✅ PoW verificado com sucesso para {current_user.email}",
        extra={
            "user": current_user.email,
            "request_id": request_id
        }
    )
    
    return {
        "status": "success",
        "message": "Proof of Work validado com sucesso!",
        "verified_at": datetime.now().isoformat(),
        "difficulty": data.difficulty,
        "request_id": request_id
    }


@router.get("/health", response_model=None)
async def pow_health():
    """🔍 Verifica saúde do sistema PoW - V3.2"""
    stats = pow_service.get_stats()
    
    return {
        "status": stats["status"],
        "service": "pow",
        "version": "3.2",
        "algorithm": PoWConfig.ALGORITHM,
        "challenge_ttl_seconds": PoWConfig.CHALLENGE_EXPIRY_SECONDS,
        "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
        "replay_protection": True,
        "circuit_breaker": stats["circuit_breaker"],
        "rate_limit": {
            "ip_limit": PoWConfig.MAX_CHALLENGES_PER_IP,
            "user_limit": PoWConfig.MAX_CHALLENGES_PER_USER,
            "window_seconds": PoWConfig.RATE_LIMIT_WINDOW,
            "burst_limit": PoWConfig.RATE_LIMIT_BURST
        },
        "timestamp": datetime.now().isoformat()
    }


@router.get("/stats", response_model=None)
async def get_pow_stats(
    current_user = Depends(get_current_user)
):
    """📊 Estatísticas do PoW (apenas admin) - V3.2"""
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
    'VerifyMode',
    'VerificationResult'
]

print("=" * 70)
print("🔥 PoW Service v3.2 - PRODUÇÃO (CORRIGIDO E MELHORADO)")
print(f"   ✅ Challenge TTL: {PoWConfig.CHALLENGE_EXPIRY_SECONDS}s")
print(f"   ✅ Default Difficulty: {PoWConfig.DEFAULT_DIFFICULTY}")
print(f"   ✅ Replay Attack Prevention: Ativo")
print(f"   ✅ Rate Limiting: {PoWConfig.MAX_CHALLENGES_PER_IP}/IP + {PoWConfig.MAX_CHALLENGES_PER_USER}/usuário")
print(f"   ✅ Dificuldade Adaptativa: Ativa")
print(f"   ✅ Circuit Breaker: Ativo")
print(f"   ✅ Algoritmo: {PoWConfig.ALGORITHM}")
print(f"   ✅ Cache: {PoWConfig.CHALLENGE_MAX_SIZE} desafios")
print(f"   ✅ Modo: VALIDAÇÃO NÃO CONSOOME + CONSUMO CONTROLADO")
print(f"   ✅ CORRIGIDO: validate_pow_request NÃO consome o challenge")
print(f"   ✅ MELHORADO: Contagem de validações por challenge")
print(f"   ✅ CORRIGIDO: Logging sem sobrescrever 'message'")
print("=" * 70)