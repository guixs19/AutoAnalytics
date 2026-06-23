# backend/api/auth_routes.py - VERSÃO COMPLETA E CORRIGIDA
"""
Módulo de LOGIN e AUTENTICAÇÃO - SEM CAPTCHA
Responsável por login, logout, refresh token e verificação de sessão
================================================================================
🔥 CORREÇÕES:
- ✅ Sincronizado com security.py corrigido (timezone)
- ✅ verify_token_async → verify_token (nome correto)
- ✅ Tratamento de erros melhorado
- ✅ Fallback para Redis offline
- ✅ _now_utc() para timezone correto (offset-aware)
- ✅ Importações otimizadas
- ✅ Logs mais detalhados
- 🔥 CORRIGIDO: erro de sintaxe na linha 190 (aspas)
================================================================================
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import logging
import traceback

from backend.database import get_db
from backend import crud
from backend.security import (
    rate_limiter,
    jwt_manager,
    hasher,
    set_auth_cookies,
    clear_auth_cookies,
    get_current_user,
    get_current_active_user,
    _now_utc  # 🔥 IMPORTADO PARA TIMEZONE CORRETO
)

logger = logging.getLogger(__name__)

# ==============================================
# ROUTER
# ==============================================

router = APIRouter(tags=["authentication"])

# ==============================================
# MODELOS PYDANTIC - SEM CAPTCHA
# ==============================================

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Email do usuário")
    password: str = Field(..., min_length=6, description="Senha do usuário")
    session_type: str = Field("login", description="Tipo de sessão")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token para renovação")
    old_access_token: Optional[str] = Field(None, description="Access token antigo para blacklist")


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(None, description="Refresh token para invalidar")


# ==============================================
# ROTA DE LOGIN - SEM CAPTCHA
# ==============================================

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    🔐 Login de usuário - SEM CAPTCHA
    POST /api/auth/login
    
    Retorna access_token e refresh_token em cookies e no body.
    """
    
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"🔐 [LOGIN] Tentativa: {login_data.email} | IP: {client_ip}")
    
    # 1. Rate limiting
    try:
        is_ip_allowed = await rate_limiter.check_rate_limit(f"login_ip:{client_ip}", 10, 900)
        is_email_allowed = await rate_limiter.check_rate_limit(f"login_email:{login_data.email}", 5, 900)
    except Exception as e:
        logger.warning(f"⚠️ Rate limit indisponível: {e}")
        is_ip_allowed = True
        is_email_allowed = True
    
    if not is_ip_allowed or not is_email_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Aguarde 15 minutos."
        )
    
    # 2. Autenticar
    try:
        user = crud.authenticate_user(db, login_data.email, login_data.password)
    except Exception as e:
        logger.error(f"❌ [LOGIN] Erro na autenticação: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao autenticar usuário"
        )
    
    if not user:
        logger.warning(f"❌ [LOGIN] Credenciais inválidas | Email: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos."
        )
    
    if not user.is_active:
        logger.warning(f"❌ [LOGIN] Conta inativa: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada. Contate o suporte."
        )
    
    # 3. Atualizar último login
    try:
        crud.update_last_login(db, user.id)
    except Exception as e:
        logger.warning(f"⚠️ Erro ao atualizar último login: {e}")
    
    # 4. Criar payload do usuário
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "workshop_name": user.workshop_name,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
        "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,
        "promotional_price_locked": getattr(user, 'promotional_price_locked', False),
        "promotional_price": getattr(user, 'promotional_price', None)
    }
    
    # 5. Gerar tokens
    tokens = jwt_manager.create_token_pair(user_data)
    
    # 6. Salvar refresh token no banco
    if hasattr(user, 'set_refresh_token'):
        user.set_refresh_token(tokens["refresh_token"], tokens["refresh_jti"], 7)
        db.commit()
    
    # 7. Montar resposta
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
        "promotional_price_locked": getattr(user, 'promotional_price_locked', False),
        "promotional_price": getattr(user, 'promotional_price', None),
        "message": "Login realizado com sucesso"
    }
    
    # 8. Definir cookies
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
# ROTA DE REFRESH (CORRIGIDA)
# ==============================================

@router.post("/refresh")
async def refresh_token_endpoint(
    data: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    🔄 Renova o access token usando o refresh token.
    POST /api/auth/refresh
    """
    try:
        logger.info("🔄 [REFRESH] Tentando renovar tokens...")
        
        # 🔥 CORRIGIDO: refresh_access_token já está assíncrono
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
        
        # 🔥 CORRIGIDO: decode_token é síncrono (não precisa de await)
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
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao renovar tokens"
        )


# ==============================================
# VERIFICAÇÃO DE TOKEN (CORRIGIDA - TIMEZONE)
# ==============================================

@router.get("/check-token")
async def check_token(request: Request, db: Session = Depends(get_db)):
    """
    🔍 Verifica status do token JWT
    GET /api/auth/check-token
    """
    
    # 1. Extrair token
    access_token = request.cookies.get("access_token")
    if access_token and access_token.startswith("Bearer "):
        access_token = access_token.replace("Bearer ", "")
    
    if not access_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # 🔥🔥🔥 CORRIGIDO: aspas corretas!
            access_token = auth_header.replace("Bearer ", "")
    
    refresh_token = request.cookies.get("refresh_token")
    
    if not access_token and not refresh_token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "no_token", "message": "Nenhum token encontrado"}
        )
    
    # 2. Verificar access token
    if access_token:
        try:
            payload = await jwt_manager.verify_token(access_token, "access")
            
            if payload:
                email = payload.get("sub") or payload.get("email")
                user = crud.get_user_by_email(db, email)
                
                if user and user.is_active:
                    exp = payload.get("exp", 0)
                    # 🔥🔥🔥 CORRIGIDO: usa _now_utc() em vez de datetime.utcnow()
                    now = _now_utc().timestamp()
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
        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar access token: {e}")
    
    # 3. Se access token expirou, tenta refresh com o refresh token
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
    
    # 4. Se tudo falhou, retorna 401
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
# LOGOUT (CORRIGIDO)
# ==============================================

@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """
    🔓 Logout - invalida tokens
    POST /api/auth/logout
    """
    
    # 1. Extrair refresh token
    refresh_token = None
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        pass
    
    # 2. Extrair access token
    access_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # 🔥 CORRIGIDO: aspas corretas!
        access_token = auth_header.replace("Bearer ", "")
    
    # 3. Tentar logout
    try:
        if refresh_token:
            await jwt_manager.logout(refresh_token, db, access_token)
            logger.info("✅ Logout realizado com sucesso")
        else:
            logger.warning("⚠️ Logout sem refresh token - limpando cookies apenas")
    except Exception as e:
        logger.error(f"❌ Erro no logout: {e}")
    
    # 4. Limpar cookies
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
    👤 Retorna dados do usuário atual
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
            "is_active": current_user.is_active,
            "promotional_price_locked": getattr(current_user, 'promotional_price_locked', False),
            "promotional_price": getattr(current_user, 'promotional_price', None)
        }
    }


# ==============================================
# EXPORTAÇÕES
# ==============================================

print("✅ auth_routes.py carregado com sucesso!")
print("   📍 Rotas disponíveis:")
print("      POST   /api/auth/login")
print("      POST   /api/auth/refresh")
print("      POST   /api/auth/logout")
print("      GET    /api/auth/check-token")
print("      GET    /api/auth/me")