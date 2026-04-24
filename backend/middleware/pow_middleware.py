# backend/middleware/pow_middleware.py
"""
Middleware que exige Proof of Work para endpoints protegidos
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Optional
import logging

from backend.services.pow_service import pow_service

logger = logging.getLogger(__name__)


class PoWMiddleware(BaseHTTPMiddleware):
    """
    Middleware que exige PoW para endpoints críticos de IA/ML
    
    Endpoints protegidos:
    - /api/upload (upload de arquivos para IA)
    - /api/process (processamento de dados)
    - /api/predict (previsões)
    - /api/generate-report (relatórios automáticos)
    """
    
    # Endpoints que exigem PoW (protegidos)
    PROTECTED_ENDPOINTS = [
        "/api/upload",
        "/api/process", 
        "/api/predict",
        "/api/generate-report",
        "/api/ml/train",
        "/api/ml/inference"
    ]
    
    # Endpoints que NÃO exigem PoW (públicos/login)
    EXCLUDED_ENDPOINTS = [
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/pow/challenge",  # Desafio PoW é livre
        "/api/health",
        "/api/docs",
        "/openapi.json"
    ]
    
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        logger.info(f"🛡️ PoW Middleware inicializado - Proteção: {'ATIVA' if enabled else 'INATIVA'}")
        logger.info(f"   Endpoints protegidos: {len(self.PROTECTED_ENDPOINTS)}")
    
    async def dispatch(self, request: Request, call_next):
        # Pular se middleware está desabilitado
        if not self.enabled:
            return await call_next(request)
        
        path = request.url.path
        
        # Pular endpoints excluídos
        for excluded in self.EXCLUDED_ENDPOINTS:
            if path.startswith(excluded):
                return await call_next(request)
        
        # Verificar se endpoint precisa de proteção
        needs_protection = False
        for protected in self.PROTECTED_ENDPOINTS:
            if path.startswith(protected):
                needs_protection = True
                break
        
        if not needs_protection:
            return await call_next(request)
        
        # 🔐 VALIDAÇÃO DO PoW
        client_ip = request.client.host if request.client else "unknown"
        
        # Extrair headers do PoW
        pow_prefix = request.headers.get("X-PoW-Prefix")
        pow_nonce = request.headers.get("X-PoW-Nonce")
        pow_complexity = request.headers.get("X-PoW-Complexity")
        
        # Verificar se headers existem
        if not pow_prefix or not pow_nonce:
            logger.warning(f"🔐 PoW missing - IP: {client_ip}, Path: {path}")
            raise HTTPException(
                status_code=428,  # Precondition Required
                detail="Proof of Work required. Call /api/pow/challenge first."
            )
        
        # Converter complexity para int
        try:
            complexity = int(pow_complexity) if pow_complexity else 3
        except ValueError:
            complexity = 3
        
        # Validar solução
        is_valid, message = pow_service.verify_solution(
            prefix=pow_prefix,
            nonce=pow_nonce,
            complexity=complexity,
            ip=client_ip
        )
        
        if not is_valid:
            logger.warning(f"🔐 PoW invalid - IP: {client_ip}, Path: {path}, Reason: {message}")
            raise HTTPException(
                status_code=401,
                detail=f"PoW validation failed: {message}"
            )
        
        # PoW válido! Prosseguir
        logger.debug(f"✅ PoW validado para IP {client_ip} em {path}")
        
        return await call_next(request)