# backend/services/pow_service.py
"""
Proof of Work Service - Proteção silenciosa para API de IA/ML
Complexidade adaptativa baseada em comportamento
"""

import hashlib
import secrets
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PowChallenge:
    """Desafio PoW para o cliente resolver"""
    prefix: str
    complexity: int
    timestamp: int
    expires_in: int = 60
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prefix": self.prefix,
            "complexity": self.complexity,
            "timestamp": self.timestamp,
            "expires_in": self.expires_in,
            "target": "0" * self.complexity
        }


class PoWService:
    """
    Serviço de Proof of Work silencioso
    - Geração de desafios com complexidade adaptativa
    - Validação de soluções
    - Prevenção de replay attacks
    - Rate limiting por IP/usuário
    """
    
    def __init__(self):
        # Cache de nonces usados (prevenir replay)
        self._used_nonces = set()
        # Complexidade adaptativa por IP
        self._ip_complexity = defaultdict(lambda: 3)  # Começa com 3
        # Contagem de falhas por IP
        self._fail_count = defaultdict(int)
        # Limpeza periódica
        self._last_cleanup = time.time()
        
        # Configurações
        self.default_complexity = 3
        self.max_complexity = 5
        self.challenge_ttl = 60  # segundos
        self.max_failures = 10    # antes de aumentar complexidade
        
        logger.info("🧮 PoW Service inicializado")
        logger.info(f"   Complexidade padrão: {self.default_complexity}")
        logger.info(f"   Máxima complexidade: {self.max_complexity}")
    
    def generate_challenge(self, ip: str, user_id: Optional[int] = None) -> PowChallenge:
        """
        Gera um desafio PoW para o cliente resolver
        
        Args:
            ip: Endereço IP do cliente
            user_id: ID do usuário (opcional, para ajuste fino)
        
        Returns:
            PowChallenge: Desafio a ser resolvido
        """
        # Ajusta complexidade baseada no histórico do IP
        complexity = self._get_complexity_for_ip(ip, user_id)
        
        # Gera prefixo aleatório
        prefix = secrets.token_hex(16)
        timestamp = int(time.time())
        
        challenge = PowChallenge(
            prefix=prefix,
            complexity=complexity,
            timestamp=timestamp,
            expires_in=self.challenge_ttl
        )
        
        logger.debug(f"🔐 Desafio PoW gerado para IP {ip}: complexity={complexity}")
        
        return challenge
    
    def verify_solution(self, prefix: str, nonce: str, complexity: int, ip: str) -> Tuple[bool, str]:
        """
        Verifica se a solução do PoW está correta
        
        Args:
            prefix: Prefixo do desafio
            nonce: Solução encontrada pelo cliente
            complexity: Complexidade esperada
            ip: IP do cliente (para tracking)
        
        Returns:
            Tuple[bool, str]: (válido, mensagem)
        """
        # Limpeza periódica
        self._cleanup()
        
        # Verifica se nonce já foi usado (replay attack)
        nonce_key = f"{prefix}:{nonce}"
        if nonce_key in self._used_nonces:
            logger.warning(f"🔄 Replay attack detectado - IP: {ip}, nonce: {nonce[:20]}...")
            self._fail_count[ip] += 1
            return False, "Nonce já utilizado (replay attack)"
        
        # Verifica timestamp (não expirado)
        try:
            timestamp = int(nonce.split(':')[0])
            if time.time() - timestamp > self.challenge_ttl:
                logger.warning(f"⏰ PoW expirado - IP: {ip}")
                self._fail_count[ip] += 1
                return False, f"Desafio expirado (limite: {self.challenge_ttl}s)"
        except (ValueError, IndexError):
            self._fail_count[ip] += 1
            return False, "Nonce inválido (formato incorreto)"
        
        # Verifica a solução criptográfica
        data = f"{prefix}:{nonce}"
        hash_result = hashlib.sha256(data.encode()).hexdigest()
        target = "0" * complexity
        
        if not hash_result.startswith(target):
            logger.warning(f"❌ PoW inválido - IP: {ip}, hash: {hash_result[:8]}... (esperava {target}...)")
            self._fail_count[ip] += 1
            return False, f"Solução incorreta (hash não começa com {complexity} zeros)"
        
        # Sucesso! Registra nonce e reseta contagem de falhas
        self._used_nonces.add(nonce_key)
        self._fail_count[ip] = max(0, self._fail_count[ip] - 1)
        
        # Reduz complexidade se estava alta e agora está se comportando bem
        if self._ip_complexity[ip] > self.default_complexity and self._fail_count[ip] == 0:
            self._ip_complexity[ip] = max(self.default_complexity, self._ip_complexity[ip] - 1)
            logger.info(f"📉 Complexidade reduzida para IP {ip}: {self._ip_complexity[ip]}")
        
        logger.info(f"✅ PoW validado - IP: {ip} (complexidade {complexity})")
        
        return True, "PoW válido"
    
    def _get_complexity_for_ip(self, ip: str, user_id: Optional[int] = None) -> int:
        """
        Calcula complexidade adaptativa baseada no histórico
        
        Usuários premium podem ter complexidade menor
        IPs com muitas falhas têm complexidade maior
        """
        base_complexity = self.default_complexity
        
        # Aumenta complexidade para IPs com muitas falhas
        fail_count = self._fail_count[ip]
        if fail_count > self.max_failures:
            extra = min(fail_count // self.max_failures, self.max_complexity - base_complexity)
            return base_complexity + extra
        
        return base_complexity
    
    def _cleanup(self):
        """Limpa cache de nonces usados (evita crescimento infinito)"""
        now = time.time()
        if now - self._last_cleanup > 300:  # A cada 5 minutos
            # Nonces expiram após 2x o TTL do desafio
            expiry = now - (self.challenge_ttl * 2)
            # Como nonces não têm timestamp próprio, vamos limitar o tamanho
            if len(self._used_nonces) > 10000:
                # Mantém apenas os últimos 5000
                self._used_nonces = set(list(self._used_nonces)[-5000:])
                logger.info(f"🧹 Limpeza de nonces: {len(self._used_nonces)} restantes")
            self._last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do serviço PoW"""
        return {
            "active_nonces": len(self._used_nonces),
            "tracked_ips": len(self._ip_complexity),
            "default_complexity": self.default_complexity,
            "max_complexity": self.max_complexity,
            "challenge_ttl": self.challenge_ttl,
            "complexities": dict(self._ip_complexity)
        }


# Instância global
pow_service = PoWService()