# backend/api/auth.py
"""
Módulo de REGISTRO de usuários
Responsável apenas por cadastro de novos usuários
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import logging
import re

from backend.database import get_db
from backend import crud
from backend.security import (
    captcha_manager,
    rate_limiter,
    hasher
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["registration"])


# ==============================================
# MODELOS PYDANTIC
# ==============================================

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    workshop_name: str = Field(..., min_length=2, max_length=100)
    captcha_id: str
    captcha_text: str
    session_type: str = "register"
    
    @validator('captcha_text')
    def validate_captcha_text(cls, v):
        if not v.isdigit():
            raise ValueError('CAPTCHA deve conter apenas números')
        return v


# ==============================================
# ROTA DE REGISTRO
# ==============================================

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    register_data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Registro de novo usuário
    POST /api/auth/register
    """
    
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"📝 [REGISTER] Tentativa: {register_data.email} | IP: {client_ip}")
    
    # VALIDAÇÃO 1: CAPTCHA
    is_valid = await captcha_manager.validate_captcha_async(
        captcha_id=register_data.captcha_id,
        captcha_text=register_data.captcha_text,
        request=request,
        session_type=register_data.session_type
    )
    
    if not is_valid:
        logger.warning(f"❌ [REGISTER] CAPTCHA inválido | IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="❌ Código CAPTCHA incorreto! Digite os números que aparecem na imagem."
        )
    
    # VALIDAÇÃO 2: Rate limiting
    is_rate_ok = await rate_limiter.check_rate_limit(f"register_ip:{client_ip}", 5, 3600)
    
    if not is_rate_ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de registro. Aguarde 1 hora."
        )
    
    # VALIDAÇÃO 3: Email único
    existing_user = crud.get_user_by_email(db, register_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este email já está cadastrado. Faça login."
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
        logger.error(f"❌ [REGISTER] Erro: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar usuário: {str(e)}"
        )