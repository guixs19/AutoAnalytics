# backend/api/pow_routes.py
"""
Rotas para Proof of Work
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional
import logging

from backend.services.pow_service import pow_service
from backend.security import get_current_active_user
from backend.database import get_db
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pow", tags=["proof-of-work"])


@router.get("/challenge")
async def get_pow_challenge(
    request: Request,
    current_user = Depends(get_current_active_user)
):
    """
    🔐 Gera desafio PoW para o cliente resolver (silencioso)
    
    O cliente deve resolver o desafio e enviar a solução
    junto com a requisição protegida.
    
    Complexidade adaptativa:
    - Usuários normais: complexity 3
    - IPs com falhas: complexity aumenta
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id = current_user.id if current_user else None
    
    challenge = pow_service.generate_challenge(client_ip, user_id)
    
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
    (Endpoint interno, normalmente não chamado diretamente)
    """
    client_ip = request.client.host if request.client else "unknown"
    
    is_valid, message = pow_service.verify_solution(
        prefix=prefix,
        nonce=nonce,
        complexity=complexity,
        ip=client_ip
    )
    
    if not is_valid:
        raise HTTPException(status_code=401, detail=message)
    
    return {"valid": True, "message": message}


@router.get("/stats")
async def get_pow_stats(
    current_user = Depends(get_current_active_user)
):
    """📊 Estatísticas do PoW (apenas admin)"""
    from backend.security import get_current_admin_user
    
    # Verifica se é admin (re-valida)
    admin_user = await get_current_admin_user(current_user)
    
    return pow_service.get_stats()