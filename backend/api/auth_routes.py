# backend/api/auth_routes.py - VERSÃO 4.2 (CORRIGIDA + MELHORADA)
"""
Módulo de LOGIN e AUTENTICAÇÃO - SEM CAPTCHA
Responsável por login, logout, refresh token e verificação de sessão

🔥 MUDANÇAS v4.2:
   - ✅ FIX: _enum_value() garante role/plan como string minúscula
     (antes retornava "UserRole.USER" em vez de "user")
   - ✅ FIX: imports não usados removidos (hasher, _now_utc,
     blacklist_token, is_token_blacklisted)
   - ✅ FIX: import de get_full_user_context movido pro topo
   - ✅ CLEAN: logs padronizados com prefixo [auth]
   - ✅ CLEAN: LogoutRequest removido (não usado)

🔥 MANTIDO v4.0 / v4.1:
   - _is_token_expired() unificada para comparação segura
   - /session-status com segmentação e mensagens
   - /refresh e /check-token com validação de expiração corrigida
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Any
import logging
import traceback

from backend.database import get_db
from backend import crud
from backend.crud import (
    get_full_user_context,
    get_credits_display,
    MAX_CREDITS_PREMIUM,
)
from backend.security import (
    rate_limiter,
    jwt_manager,
    set_auth_cookies,
    clear_auth_cookies,
    get_current_user,
    get_current_active_user,
    _get_remaining_seconds,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])


# ==============================================
# 🔥 HELPERS
# ==============================================

def _enum_value(v: Any, default: Optional[str] = None) -> Optional[str]:
    """
    🔥 Normaliza Enum → .value → str.
    Evita que str(UserRole.USER) retorne "UserRole.USER".
    """
    if v is None:
        return default
    if hasattr(v, "value"):
        return v.value
    return str(v)


def _is_token_expired(expires_at: Optional[datetime]) -> bool:
    """
    🔥 Verifica se um token expirou.
    Compara datas naive (remove tzinfo) para evitar TypeError.
    """
    if expires_at is None:
        return True

    naive_expiry = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
    naive_now = datetime.utcnow().replace(tzinfo=None)

    return naive_expiry < naive_now


def _is_token_valid(expires_at: Optional[datetime]) -> bool:
    """Versão positiva: True se NÃO expirou."""
    return not _is_token_expired(expires_at)


# ==============================================
# MODELOS PYDANTIC
# ==============================================

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Email do usuário")
    password: str = Field(..., min_length=6, description="Senha do usuário")
    session_type: str = Field("login", description="Tipo de sessão")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token para renovação")
    old_access_token: Optional[str] = Field(None, description="Access token antigo para blacklist")


# ==============================================
# LOGIN
# ==============================================

@router.post("/login", status_code=status.HTTP_200_OK, response_model=None)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """🔐 Login de usuário - SEM CAPTCHA"""
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"[auth] 🔐 LOGIN: {login_data.email} | IP: {client_ip}")

    # Rate limiting
    try:
        is_ip_allowed = await rate_limiter.check_rate_limit(f"login_ip:{client_ip}", 10, 900)
        is_email_allowed = await rate_limiter.check_rate_limit(f"login_email:{login_data.email}", 5, 900)
    except Exception as e:
        logger.warning(f"[auth] ⚠️ Rate limit indisponível: {e}")
        is_ip_allowed = True
        is_email_allowed = True

    if not is_ip_allowed or not is_email_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Aguarde 15 minutos.",
        )

    # Autenticar
    try:
        user = crud.authenticate_user(db, login_data.email, login_data.password)
    except Exception as e:
        logger.error(f"[auth] ❌ Erro na autenticação: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao autenticar usuário",
        )

    if not user:
        logger.warning(f"[auth] ❌ Credenciais inválidas: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos.",
        )

    if not user.is_active:
        logger.warning(f"[auth] ❌ Conta inativa: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada. Contate o suporte.",
        )

    # Atualizar último login
    try:
        crud.update_last_login(db, user.id)
    except Exception as e:
        logger.warning(f"[auth] ⚠️ Erro ao atualizar last_login: {e}")

    # Payload do JWT
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "workshop_name": user.workshop_name,
        "role": _enum_value(user.role),
        "plan": _enum_value(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,
        "promotional_price_locked": getattr(user, "promotional_price_locked", False),
        "promotional_price": getattr(user, "promotional_price", None),
    }

    # Gerar tokens
    tokens = jwt_manager.create_token_pair(user_data)

    # Salvar refresh token no banco
    if hasattr(user, "set_refresh_token"):
        user.set_refresh_token(tokens["refresh_token"], tokens["refresh_jti"], 7)
        db.commit()

    # Resposta
    response_data = {
        "success": True,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],
        "user_email": user.email,
        "user_name": user.name,
        "workshop_name": user.workshop_name,
        "role": _enum_value(user.role),
        "plan": _enum_value(user.plan),
        "credits": user.credits,
        "credits_display": "∞" if user.is_admin else str(user.credits),
        "is_admin": user.is_admin,
        "promotional_price_locked": getattr(user, "promotional_price_locked", False),
        "promotional_price": getattr(user, "promotional_price", None),
        "message": "Login realizado com sucesso",
    }

    api_response = JSONResponse(content=response_data)
    api_response = set_auth_cookies(
        api_response,
        tokens["access_token"],
        tokens["refresh_token"],
        tokens["expires_in"],
    )

    logger.info(f"[auth] ✅ LOGIN OK: {user.email}")
    return api_response


# ==============================================
# REFRESH
# ==============================================

@router.post("/refresh", response_model=None)
async def refresh_token_endpoint(
    data: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """🔄 Renova o access token usando o refresh token."""
    try:
        logger.info("[auth] 🔄 REFRESH: tentando renovar")

        refresh_payload = jwt_manager.decode_token(data.refresh_token)
        if not refresh_payload:
            logger.warning("[auth] ❌ Refresh token inválido")
            raise HTTPException(status_code=401, detail="Refresh token inválido")

        email = refresh_payload.get("sub") or refresh_payload.get("email")
        if not email:
            logger.warning("[auth] ❌ Refresh token sem email")
            raise HTTPException(status_code=401, detail="Refresh token inválido")

        user = crud.get_user_by_email(db, email)
        if not user:
            logger.warning(f"[auth] ❌ Usuário {email} não encontrado")
            raise HTTPException(status_code=401, detail="Usuário não encontrado")

        # Verifica expiração do refresh token no banco
        if user.refresh_token_expires and _is_token_expired(user.refresh_token_expires):
            logger.warning(f"[auth] ❌ Refresh expirado: {email}")
            raise HTTPException(
                status_code=401,
                detail="Refresh token expirado. Faça login novamente.",
            )

        # Bate com o banco?
        if user.refresh_token != data.refresh_token:
            logger.warning(f"[auth] ❌ Refresh token não bate com o banco: {email}")
            raise HTTPException(status_code=401, detail="Refresh token inválido")

        if user.refresh_token_revoked:
            logger.warning(f"[auth] ❌ Refresh token revogado: {email}")
            raise HTTPException(status_code=401, detail="Refresh token revogado")

        new_tokens = await jwt_manager.refresh_access_token(
            refresh_token=data.refresh_token,
            db=db,
            old_access_token=data.old_access_token,
        )

        if not new_tokens:
            logger.warning("[auth] ❌ Falha ao renovar tokens")
            raise HTTPException(status_code=401, detail="Falha ao renovar tokens")

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
            "role": _enum_value(user.role) if user else "",
            "plan": _enum_value(user.plan) if user else "",
            "credits": user.credits if user else 0,
            "credits_display": "∞" if (user and user.is_admin) else str(user.credits if user else 0),
            "is_admin": user.is_admin if user else False,
            "message": "Tokens renovados com sucesso",
        }

        api_response = JSONResponse(content=response_data)
        api_response = set_auth_cookies(
            api_response,
            new_tokens["access_token"],
            new_tokens["refresh_token"],
            new_tokens.get("expires_in", 3600),
        )

        logger.info(f"[auth] ✅ REFRESH OK: {email}")
        return api_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[auth] ❌ Erro no refresh: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Erro interno ao renovar tokens")


# ==============================================
# CHECK TOKEN
# ==============================================

@router.get("/check-token", response_model=None)
async def check_token(request: Request, db: Session = Depends(get_db)):
    """🔍 Verifica status do token JWT"""

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
            status_code=401,
            content={"status": "no_token", "message": "Nenhum token encontrado"},
        )

    # Verificar access token
    if access_token:
        try:
            payload = await jwt_manager.verify_token(access_token, "access")
            if payload:
                email = payload.get("sub") or payload.get("email")
                user = crud.get_user_by_email(db, email)
                if user and user.is_active:
                    expires_in = _get_remaining_seconds(payload)
                    return {
                        "status": "valid",
                        "user": user.email,
                        "name": user.name,
                        "is_admin": user.is_admin,
                        "credits": user.credits,
                        "credits_display": "∞" if user.is_admin else str(user.credits),
                        "expires_in": expires_in,
                    }
        except Exception as e:
            logger.warning(f"[auth] ⚠️ Erro ao verificar access token: {e}")

    # Tentar refresh
    if refresh_token:
        logger.info("[auth] 🔄 Access expirado, tentando refresh")
        try:
            refresh_payload = jwt_manager.decode_token(refresh_token)
            if refresh_payload:
                email = refresh_payload.get("sub") or refresh_payload.get("email")
                user = crud.get_user_by_email(db, email)

                if user and user.refresh_token_expires:
                    if _is_token_expired(user.refresh_token_expires):
                        logger.warning(f"[auth] ⚠️ Refresh expirado: {email}")
                        resp = JSONResponse(
                            status_code=401,
                            content={"status": "expired", "message": "Sessão expirada. Faça login novamente."},
                        )
                        return clear_auth_cookies(resp)

            new_tokens = await jwt_manager.refresh_access_token(refresh_token, db, access_token)

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
                        "credits_display": "∞" if user.is_admin else str(user.credits),
                    }
                    resp = JSONResponse(content=response_data)
                    resp = set_auth_cookies(
                        resp,
                        new_tokens["access_token"],
                        new_tokens["refresh_token"],
                        new_tokens["expires_in"],
                    )
                    return resp
        except Exception as e:
            logger.error(f"[auth] ❌ Erro no refresh: {e}")

    resp = JSONResponse(
        status_code=401,
        content={"status": "invalid", "message": "Sessão expirada. Faça login novamente."},
    )
    return clear_auth_cookies(resp)


# ==============================================
# LOGOUT
# ==============================================

@router.post("/logout", response_model=None)
async def logout(request: Request, db: Session = Depends(get_db)):
    """🔓 Logout - invalida tokens"""
    refresh_token = None
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except Exception:
        pass

    access_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.replace("Bearer ", "")

    try:
        if refresh_token:
            await jwt_manager.logout(refresh_token, db, access_token)
            logger.info("[auth] ✅ Logout OK")
        else:
            logger.warning("[auth] ⚠️ Logout sem refresh token")
    except Exception as e:
        logger.error(f"[auth] ❌ Erro no logout: {e}")

    response = JSONResponse(content={"success": True, "message": "Logout realizado"})
    return clear_auth_cookies(response)


# ==============================================
# /me
# ==============================================

@router.get("/me", response_model=None)
async def get_me(current_user=Depends(get_current_active_user)):
    """👤 Retorna dados do usuário atual"""
    return {
        "success": True,
        "data": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "workshop_name": current_user.workshop_name,
            "role": _enum_value(current_user.role),
            "plan": _enum_value(current_user.plan),
            "credits": current_user.credits,
            "credits_display": "∞" if current_user.is_admin else str(current_user.credits),
            "is_admin": current_user.is_admin,
            "is_active": current_user.is_active,
            "promotional_price_locked": getattr(current_user, "promotional_price_locked", False),
            "promotional_price": getattr(current_user, "promotional_price", None),
        },
    }


# ==============================================
# SESSION STATUS
# ==============================================

@router.get("/session-status", response_model=None)
async def get_session_status(
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    📊 Status da sessão com segmentação e mensagens.
    """
    user_context = get_full_user_context(db, current_user)
    segment = user_context["segment"]
    ui_context = user_context["ui_context"]
    message_config = user_context["message_config"]

    is_premium = current_user.is_premium() if hasattr(current_user, "is_premium") else False
    days_left = (
        current_user.get_premium_days_left()
        if is_premium and hasattr(current_user, "get_premium_days_left")
        else 0
    )

    response_data = {
        "authenticated": True,
        "user": current_user.email,
        "name": current_user.name,
        "credits": current_user.credits or 0,
        "is_admin": current_user.is_admin,
        "is_premium": is_premium,
        "session_active": True,
        "credits_display": get_credits_display(current_user),
        "max_credits": MAX_CREDITS_PREMIUM,
        "segment": segment,
        "ui_context": ui_context,
        "message_config": message_config,
        "premium": {
            "is_premium": is_premium,
            "days_left": max(0, days_left),
            "plan": _enum_value(current_user.plan, "basico"),
        },
        "promotional": {
            "has_locked_price": getattr(current_user, "promotional_price_locked", False),
            "locked_price": getattr(current_user, "promotional_price", None),
            "is_vitalicio": getattr(current_user, "promotional_price_locked", False),
        },
    }

    logger.info(
        f"[auth] 📊 SESSION: {current_user.email} | "
        f"segment={segment} | credits={current_user.credits or 0} | "
        f"premium={is_premium} | "
        f"msg={message_config.get('message_id', 'none') if message_config else 'none'}"
    )

    return response_data


# ==============================================
# PRINTS
# ==============================================

print("=" * 70)
print("✅ auth_routes.py v4.2 carregado - ENUM FIX!")
print("   ✅ _enum_value() normaliza role/plan para string minúscula")
print("   ✅ Imports não usados removidos")
print("   ✅ get_full_user_context importado no topo")
print("   ✅ Logs padronizados com [auth]")
print("=" * 70)