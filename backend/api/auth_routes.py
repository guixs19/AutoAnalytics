# backend/api/auth_routes.py
"""
Módulo de LOGIN e AUTENTICAÇÃO - CORRIGIDO
Responsável por login, logout, refresh token e verificação de sessão
🔥 CORREÇÕES:
- Blacklist não bloqueia quando Redis está offline
- Tokens expirados NÃO vão para blacklist
- Logout mais robusto
- Refresh token com fallback seguro
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import logging
import os
import io

from backend.database import get_db
from backend import crud
from backend.security import (
    captcha_manager,
    rate_limiter,
    jwt_manager,
    hasher,
    set_auth_cookies,
    clear_auth_cookies,
    get_current_user,
    get_current_active_user
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])

# Flag para modo de desenvolvimento (permitir CAPTCHA fixo "1234")
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


# ==============================================
# MODELOS PYDANTIC
# ==============================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_id: Optional[str] = None
    captcha_code: Optional[str] = None
    session_type: str = "login"
    
    @validator('captcha_code')
    def validate_captcha_code(cls, v):
        if v and not v.isdigit():
            raise ValueError('CAPTCHA deve conter apenas números')
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str
    old_access_token: Optional[str] = None


# ==============================================
# ROTA DE CAPTCHA - NOVA
# ==============================================

@router.get("/captcha/generate")
async def get_captcha(
    request: Request,
    session_type: str = "login",
    db: Session = Depends(get_db)
):
    """
    Gera uma nova imagem CAPTCHA com números distorcidos.
    Retorna a imagem PNG e o ID do captcha no header X-Captcha-ID.
    GET /api/auth/captcha/generate?session_type=login
    """
    try:
        img_bytes, captcha_id = await captcha_manager.generate_captcha_image_async(
            request, 
            session_type=session_type
        )
        
        logger.info(f"🔢 CAPTCHA gerado: {captcha_id[:12]}... para {session_type}")
        
        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type="image/png",
            headers={
                "X-Captcha-ID": captcha_id,
                "Access-Control-Expose-Headers": "X-Captcha-ID",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error(f"❌ Erro ao gerar CAPTCHA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar CAPTCHA"
        )


# ==============================================
# ROTA DE LOGIN - CORRIGIDA
# ==============================================

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Login de usuário com CAPTCHA
    POST /api/auth/login
    🔥 CORRIGIDO: Tratamento de erro mais robusto
    """
    
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"🔐 [LOGIN] Tentativa: {login_data.email} | IP: {client_ip}")
    
    # Extrair CAPTCHA
    captcha_id = request.headers.get("X-Captcha-ID") or login_data.captcha_id
    captcha_text = login_data.captcha_code
    
    if not captcha_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA não carregado. Recarregue a página."
        )
    
    if not captcha_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Digite os números que aparecem na imagem."
        )
    
    # VALIDAÇÃO DO CAPTCHA
    is_valid = False
    
    if DEV_MODE and captcha_text == "1234":
        logger.warning(f"⚠️ [LOGIN] Modo DEV: CAPTCHA 1234 aceito para {login_data.email}")
        is_valid = True
    else:
        is_valid = await captcha_manager.validate_captcha_async(
            captcha_id=captcha_id,
            captcha_text=captcha_text,
            request=request,
            session_type=login_data.session_type
        )
    
    if not is_valid:
        logger.warning(f"❌ [LOGIN] CAPTCHA inválido | IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="❌ Código incorreto! Digite os números que aparecem na imagem."
        )
    
    # Rate limiting
    is_ip_allowed = await rate_limiter.check_rate_limit(f"login_ip:{client_ip}", 10, 900)
    is_email_allowed = await rate_limiter.check_rate_limit(f"login_email:{login_data.email}", 5, 900)
    
    if not is_ip_allowed or not is_email_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Aguarde 15 minutos."
        )
    
    # Credenciais
    user = crud.authenticate_user(db, login_data.email, login_data.password)
    
    if not user:
        logger.warning(f"❌ [LOGIN] Credenciais inválidas | Email: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos."
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada. Contate o suporte."
        )
    
    crud.update_last_login(db, user.id)
    
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "workshop_name": user.workshop_name,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
        "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,
        "admin_level": user.admin_level if hasattr(user, 'admin_level') else None
    }
    
    tokens = jwt_manager.create_token_pair(user_data)
    
    if hasattr(user, 'set_refresh_token'):
        user.set_refresh_token(tokens["refresh_token"], tokens["refresh_jti"], 7)
    db.commit()
    
    response_data = {
        "success": True,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],
        "user_email": user.email,
        "user_name": user.name,
        "workshop_name": user.workshop_name,
        "role": str(user.role),
        "plan": str(user.plan),
        "credits": user.credits,
        "credits_display": "∞" if user.is_admin else str(user.credits),
        "is_admin": user.is_admin,
        "message": "Login realizado com sucesso"
    }
    
    api_response = JSONResponse(content=response_data)
    api_response = set_auth_cookies(
        api_response,
        tokens["access_token"],
        tokens["refresh_token"],
        tokens["expires_in"]
    )
    
    logger.info(f"✅ [LOGIN] Sucesso: {user.email}")
    
    return api_response


# ==============================================
# ROTA DE REFRESH - CORRIGIDA
# ==============================================

@router.post("/refresh")
async def refresh_token_endpoint(
    data: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Renova o access token usando o refresh token.
    POST /api/auth/refresh
    🔥 CORRIGIDO: Fallback quando Redis está offline
    """
    try:
        logger.info("🔄 [REFRESH] Tentando renovar tokens...")
        
        new_tokens = await jwt_manager.refresh_access_token(
            refresh_token=data.refresh_token,
            db=db,
            old_access_token=data.old_access_token
        )
        
        if not new_tokens:
            logger.warning("❌ [REFRESH] Refresh token inválido ou expirado")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido ou expirado"
            )
        
        payload = jwt_manager.decode_token(new_tokens["access_token"])
        email = payload.get("sub") or payload.get("email")
        user = crud.get_user_by_email(db, email)
        
        response_data = {
            "access_token": new_tokens["access_token"],
            "refresh_token": new_tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": new_tokens.get("expires_in", 3600),
            "user_email": user.email if user else email,
            "user_name": user.name if user else "",
            "workshop_name": user.workshop_name if user else "",
            "role": str(user.role) if user else "",
            "plan": str(user.plan) if user else "",
            "credits": user.credits if user else 0,
            "credits_display": "∞" if (user and user.is_admin) else str(user.credits if user else 0),
            "is_admin": user.is_admin if user else False,
            "message": "Tokens renovados com sucesso"
        }
        
        api_response = JSONResponse(content=response_data)
        api_response = set_auth_cookies(
            api_response,
            new_tokens["access_token"],
            new_tokens["refresh_token"],
            new_tokens.get("expires_in", 3600)
        )
        
        logger.info(f"✅ [REFRESH] Tokens renovados para {email}")
        return api_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [REFRESH] Erro ao renovar tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao renovar tokens"
        )


# ==============================================
# VERIFICAÇÃO DE TOKEN - CORRIGIDA
# ==============================================

@router.get("/check-token")
async def check_token(request: Request, db: Session = Depends(get_db)):
    """
    Verifica status do token JWT
    GET /api/auth/check-token
    🔥 CORRIGIDO: Tratamento mais robusto de tokens expirados
    """
    
    access_token = request.cookies.get("access_token")
    if access_token and access_token.startswith("Bearer "):
        access_token = access_token.replace("Bearer ", "")
    
    if not access_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            access_token = auth_header.replace("Bearer ", "")
    
    refresh_token = request.cookies.get("refresh_token")
    
    if not access_token and not refresh_token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "no_token", "message": "Nenhum token encontrado"}
        )
    
    # 🔥 Tenta verificar o access token primeiro
    if access_token:
        payload = await jwt_manager.verify_token_async(access_token, "access")
        
        if payload:
            email = payload.get("sub") or payload.get("email")
            user = crud.get_user_by_email(db, email)
            
            if user and user.is_active:
                exp = payload.get("exp", 0)
                now = datetime.utcnow().timestamp()
                expires_in = max(0, int(exp - now))
                
                return {
                    "status": "valid",
                    "user": user.email,
                    "name": user.name,
                    "is_admin": user.is_admin,
                    "credits": user.credits,
                    "credits_display": "∞" if user.is_admin else str(user.credits),
                    "expires_in": expires_in
                }
    
    # 🔥 Se access token expirou, tenta refresh com o refresh token
    if refresh_token:
        logger.info("🔄 [TOKEN] Access token expirado, tentando refresh...")
        
        try:
            new_tokens = await jwt_manager.refresh_access_token(
                refresh_token, 
                db, 
                access_token
            )
            
            if new_tokens:
                payload = jwt_manager.decode_token(new_tokens["access_token"])
                email = payload.get("sub") or payload.get("email")
                user = crud.get_user_by_email(db, email)
                
                if user:
                    response_data = {
                        "status": "refreshed",
                        "access_token": new_tokens["access_token"],
                        "refresh_token": new_tokens["refresh_token"],
                        "expires_in": new_tokens["expires_in"],
                        "user": user.email,
                        "name": user.name,
                        "is_admin": user.is_admin,
                        "credits": user.credits,
                        "credits_display": "∞" if user.is_admin else str(user.credits)
                    }
                    
                    response = JSONResponse(content=response_data)
                    response = set_auth_cookies(
                        response,
                        new_tokens["access_token"],
                        new_tokens["refresh_token"],
                        new_tokens["expires_in"]
                    )
                    
                    return response
                    
        except Exception as e:
            logger.error(f"❌ [TOKEN] Erro no refresh: {e}")
            # 🔥 Se o refresh falhar, retorna 401 para forçar login
            pass
    
    # 🔥 Se tudo falhou, retorna 401
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "status": "invalid", 
            "message": "Sessão expirada. Faça login novamente."
        }
    )
    response = clear_auth_cookies(response)
    
    return response


# ==============================================
# LOGOUT - CORRIGIDO
# ==============================================

@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """
    Logout - invalida tokens
    POST /api/auth/logout
    🔥 CORRIGIDO: Mais robusto, não falha se Redis offline
    """
    
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        refresh_token = None
    
    access_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.replace("Bearer ", "")
    
    # 🔥 Tenta fazer logout mesmo se Redis estiver offline
    try:
        if refresh_token:
            await jwt_manager.logout(refresh_token, db, access_token)
            logger.info("✅ Logout realizado com sucesso")
        else:
            logger.warning("⚠️ Logout sem refresh token - limpando cookies apenas")
    except Exception as e:
        logger.error(f"❌ Erro no logout: {e}")
        # 🔥 Mesmo com erro, continuamos para limpar cookies
    
    response = JSONResponse(
        content={
            "success": True, 
            "message": "Logout realizado"
        }
    )
    response = clear_auth_cookies(response)
    
    return response


# ==============================================
# PERFIL DO USUÁRIO
# ==============================================

@router.get("/me")
async def get_me(current_user = Depends(get_current_active_user)):
    """
    Retorna dados do usuário atual
    GET /api/auth/me
    """
    return {
        "success": True,
        "data": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "workshop_name": current_user.workshop_name,
            "role": str(current_user.role),
            "plan": str(current_user.plan),
            "credits": current_user.credits,
            "credits_display": "∞" if current_user.is_admin else str(current_user.credits),
            "is_admin": current_user.is_admin,
            "is_active": current_user.is_active
        }
    }


# ==============================================
# EXPORTAÇÕES
# ==============================================

from backend.security import (
    get_current_user,
    get_current_active_user,
    get_current_admin_user
)