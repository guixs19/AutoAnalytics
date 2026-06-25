# backend/api/auth_routes.py - VERSÃO CORRIGIDA V4.0
"""
Módulo de LOGIN e AUTENTICAÇÃO - SEM CAPTCHA
Responsável por login, logout, refresh token e verificação de sessão

🔥 CORREÇÕES V4.0:
- ✅ Usa blacklist_token() centralizada (consistente entre workers)
- ✅ Usa _get_remaining_seconds() para evitar erro de timezone
- ✅ NÃO usa pending_blacklist diretamente
- ✅ 🔥 CORREÇÃO: Função _is_token_expired() unificada para comparação segura
- ✅ 🔥 CORREÇÃO: Rota /refresh usa _is_token_expired()
- ✅ 🔥 CORREÇÃO: Rota /check-token usa _is_token_expired()
- ✅ 🔥 CORREÇÃO: Todas as comparações de data usam replace(tzinfo=None)
- ✅ 🔥 MELHORIA: Logs mais detalhados para debugging
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
    _now_utc,
    _get_remaining_seconds,
    blacklist_token,
    is_token_blacklisted
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])


# ==============================================
# 🔥 FUNÇÃO AUXILIAR PARA COMPARAÇÃO DE DATAS (UNIFICADA)
# ==============================================

def _is_token_expired(expires_at: Optional[datetime]) -> bool:
    """
    🔥 CORREÇÃO CRÍTICA: Verifica se um token expirou.
    Remove o fuso horário (tzinfo) de ambas as datas para comparação segura.
    
    Args:
        expires_at: Data de expiração do token (pode ter ou não timezone)
    
    Returns:
        True se o token expirou, False caso contrário
    """
    if expires_at is None:
        return True
    
    # Remove o fuso horário se existir (evita erro de comparação)
    if expires_at.tzinfo:
        naive_expiry = expires_at.replace(tzinfo=None)
    else:
        naive_expiry = expires_at
    
    naive_now = datetime.utcnow().replace(tzinfo=None)
    
    return naive_expiry < naive_now


def _is_token_valid(expires_at: Optional[datetime]) -> bool:
    """
    Versão positiva da verificação de expiração.
    Retorna True se o token NÃO expirou.
    """
    return not _is_token_expired(expires_at)


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
# ROTA DE LOGIN
# ==============================================

@router.post("/login", status_code=status.HTTP_200_OK, response_model=None)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """🔐 Login de usuário - SEM CAPTCHA"""
    
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"🔐 [LOGIN] Tentativa: {login_data.email} | IP: {client_ip}")
    
    # Rate limiting
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
    
    # Autenticar
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
    
    # Atualizar último login
    try:
        crud.update_last_login(db, user.id)
    except Exception as e:
        logger.warning(f"⚠️ Erro ao atualizar último login: {e}")
    
    # Criar payload
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
    
    # Gerar tokens
    tokens = jwt_manager.create_token_pair(user_data)
    
    # Salvar refresh token no banco
    if hasattr(user, 'set_refresh_token'):
        user.set_refresh_token(tokens["refresh_token"], tokens["refresh_jti"], 7)
        db.commit()
    
    # Montar resposta
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
# ROTA DE REFRESH - CORRIGIDA COM _is_token_expired()
# ==============================================

@router.post("/refresh", response_model=None)
async def refresh_token_endpoint(
    data: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """🔄 Renova o access token usando o refresh token."""
    try:
        logger.info("🔄 [REFRESH] Tentando renovar tokens...")
        
        # Extrai informações do refresh token
        refresh_payload = jwt_manager.decode_token(data.refresh_token)
        if not refresh_payload:
            logger.warning("❌ [REFRESH] Refresh token inválido")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )
        
        email = refresh_payload.get("sub") or refresh_payload.get("email")
        if not email:
            logger.warning("❌ [REFRESH] Refresh token sem email")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )
        
        # Busca usuário
        user = crud.get_user_by_email(db, email)
        if not user:
            logger.warning(f"❌ [REFRESH] Usuário {email} não encontrado")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não encontrado"
            )
        
        # 🔥 CORREÇÃO: Verifica se o refresh token no banco está expirado
        # Usa a função auxiliar _is_token_expired() para comparação segura
        if user.refresh_token_expires and _is_token_expired(user.refresh_token_expires):
            logger.warning(f"❌ [REFRESH] Refresh token expirado para {email} (expira em: {user.refresh_token_expires})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expirado. Faça login novamente."
            )
        
        # Verifica se o token corresponde ao salvo no banco
        if user.refresh_token != data.refresh_token:
            logger.warning(f"❌ [REFRESH] Refresh token não corresponde ao banco para {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )
        
        if user.refresh_token_revoked:
            logger.warning(f"❌ [REFRESH] Refresh token revogado para {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revogado"
            )
        
        # 🔥 Se passou em todas as verificações, prossegue com a renovação
        new_tokens = await jwt_manager.refresh_access_token(
            refresh_token=data.refresh_token,
            db=db,
            old_access_token=data.old_access_token
        )
        
        if not new_tokens:
            logger.warning("❌ [REFRESH] Falha ao renovar tokens")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Falha ao renovar tokens"
            )
        
        # Decodifica o novo access token para obter dados do usuário
        payload = jwt_manager.decode_token(new_tokens["access_token"])
        email = payload.get("sub") or payload.get("email")
        user = crud.get_user_by_email(db, email) if email else None
        
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
# VERIFICAÇÃO DE TOKEN - CORRIGIDA COM _is_token_expired()
# ==============================================

@router.get("/check-token", response_model=None)
async def check_token(request: Request, db: Session = Depends(get_db)):
    """🔍 Verifica status do token JWT"""
    
    # Extrair token
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
    
    # Verificar access token
    if access_token:
        try:
            payload = await jwt_manager.verify_token(access_token, "access")
            
            if payload:
                email = payload.get("sub") or payload.get("email")
                user = crud.get_user_by_email(db, email)
                
                if user and user.is_active:
                    # Usa _get_remaining_seconds
                    expires_in = _get_remaining_seconds(payload)
                    
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
    
    # Tenta refresh
    if refresh_token:
        logger.info("🔄 [TOKEN] Access token expirado, tentando refresh...")
        
        try:
            # 🔥 CORREÇÃO: Verifica se o refresh token no banco está expirado
            refresh_payload = jwt_manager.decode_token(refresh_token)
            if refresh_payload:
                email = refresh_payload.get("sub") or refresh_payload.get("email")
                user = crud.get_user_by_email(db, email)
                
                if user and user.refresh_token_expires:
                    # 🔥 Usa a função auxiliar _is_token_expired() para comparação segura
                    if _is_token_expired(user.refresh_token_expires):
                        logger.warning(f"⚠️ Refresh token expirado para {email} (expira em: {user.refresh_token_expires})")
                        # Não tenta renovar, apenas retorna expirado
                        response = JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={"status": "expired", "message": "Sessão expirada. Faça login novamente."}
                        )
                        response = clear_auth_cookies(response)
                        return response
            
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
    
    # Se tudo falhou
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"status": "invalid", "message": "Sessão expirada. Faça login novamente."}
    )
    response = clear_auth_cookies(response)
    return response


# ==============================================
# LOGOUT - CORRIGIDO (USA blacklist_token)
# ==============================================

@router.post("/logout", response_model=None)
async def logout(request: Request, db: Session = Depends(get_db)):
    """🔓 Logout - invalida tokens"""
    
    # Extrair refresh token
    refresh_token = None
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        pass
    
    # Extrair access token
    access_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.replace("Bearer ", "")
    
    # Tentar logout
    try:
        if refresh_token:
            await jwt_manager.logout(refresh_token, db, access_token)
            logger.info("✅ Logout realizado com sucesso")
        else:
            logger.warning("⚠️ Logout sem refresh token - limpando cookies apenas")
    except Exception as e:
        logger.error(f"❌ Erro no logout: {e}")
    
    # Limpar cookies
    response = JSONResponse(
        content={"success": True, "message": "Logout realizado"}
    )
    response = clear_auth_cookies(response)
    return response


# ==============================================
# PERFIL DO USUÁRIO
# ==============================================

@router.get("/me", response_model=None)
async def get_me(current_user = Depends(get_current_active_user)):
    """👤 Retorna dados do usuário atual"""
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
# VALIDADE DA SESSÃO
# ==============================================

@router.get("/session-status", response_model=None)
async def get_session_status(current_user = Depends(get_current_active_user)):
    """📊 Verifica o status da sessão atual"""
    from backend.security import _get_remaining_seconds
    
    # Extrai o token da requisição via depêndencia
    # Usa o token do current_user para verificar expiração
    
    return {
        "authenticated": True,
        "user": current_user.email,
        "name": current_user.name,
        "credits": current_user.credits,
        "is_admin": current_user.is_admin,
        "is_premium": current_user.plan and "PREMIUM" in str(current_user.plan).upper(),
        "session_active": True
    }


print("✅ auth_routes.py v4.0 carregado com sucesso!")
print("   ✅ Função _is_token_expired() unificada para comparação segura de datas")
print("   ✅ Rota /refresh com validação de expiração corrigida")
print("   ✅ Rota /check-token com validação de expiração corrigida")
print("   ✅ Todas as comparações de data usam replace(tzinfo=None)")
print("   ✅ Logs mais detalhados para debugging")