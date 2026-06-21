# backend/api/auth.py - SEM CAPTCHA
"""
Módulo de REGISTRO de usuários - SEM CAPTCHA
Responsável apenas por cadastro de novos usuários
🔥 CORREÇÕES:
- Fallback quando Redis offline
- Tratamento de erro melhorado
- Validação de telefone mais rigorosa
- ✅ CAPTCHA REMOVIDO COMPLETAMENTE
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import logging
import os

from backend.database import get_db
from backend import crud
from backend.security import (
    rate_limiter,
    hasher
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["registration"])


# ==============================================
# MODELOS PYDANTIC - SEM CAPTCHA
# ==============================================

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    workshop_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    session_type: str = "register"
    
    @validator('phone')
    def validate_phone(cls, v):
        if v:
            cleaned = ''.join(filter(str.isdigit, v))
            if len(cleaned) < 10:
                raise ValueError('Telefone deve ter pelo menos 10 dígitos')
            if len(cleaned) > 11:
                raise ValueError('Telefone deve ter no máximo 11 dígitos')
        return v


# ==============================================
# ROTA DE REGISTRO - SEM CAPTCHA
# ==============================================

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    register_data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Registro de novo usuário - SEM CAPTCHA
    POST /api/auth/register
    """
    
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"📝 [REGISTER] Tentativa: {register_data.email} | IP: {client_ip}")
    
    # Rate limiting
    try:
        is_rate_ok = await rate_limiter.check_rate_limit(f"register_ip:{client_ip}", 5, 3600)
    except Exception as e:
        logger.error(f"❌ [REGISTER] Erro no rate limit: {e}")
        is_rate_ok = True
    
    if not is_rate_ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de registro. Aguarde 1 hora."
        )
    
    # Email único
    existing_user = crud.get_user_by_email(db, register_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este email já está cadastrado. Faça login."
        )
    
    # Telefone único (se fornecido)
    if register_data.phone:
        existing_phone = crud.get_user_by_phone(db, register_data.phone)
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este telefone já está cadastrado."
            )
    
    # Criar usuário
    try:
        new_user = crud.create_user(db, register_data)
        
        logger.info(f"✅ [REGISTER] Usuário criado: {new_user.email} | ID: {new_user.id}")
        
        return {
            "success": True,
            "message": "Cadastro realizado com sucesso! Faça login.",
            "user_id": new_user.id,
            "user_email": new_user.email,
            "user_name": new_user.name,
            "credits": new_user.credits,
            "redirect_to": "/login"
        }
        
    except Exception as e:
        logger.error(f"❌ [REGISTER] Erro ao criar usuário: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar usuário: {str(e)}"
        )