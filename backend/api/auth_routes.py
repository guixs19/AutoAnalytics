# backend/api/auth_routes.py - VERSÃO COMPLETA CORRIGIDA
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from backend.database import get_db
from backend import crud, schemas
from backend.security import (
    hasher,
    captcha_manager,
    jwt_manager,
    rate_limiter,
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
    set_auth_cookies,
    clear_auth_cookies,
    oauth2_scheme
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])

# ==============================================
# ROTAS PÚBLICAS COM CAPTCHA
# ==============================================

@router.get("/captcha/generate")
async def generate_captcha(request: Request):
    """Gera CAPTCHA próprio - Retorna imagem e ID no header"""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        img_bytes, captcha_id = captcha_manager.generate_captcha_image(client_ip)
    except Exception as e:
        logger.error(f"❌ Erro ao gerar CAPTCHA: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar CAPTCHA")
    
    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={
            "X-Captcha-ID": captcha_id,
            "X-Captcha-Expires": "120",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )


# ==============================================
# LOGIN - USANDO SCHEMA.UserLogin
# ==============================================

@router.post("/login")
async def login(
    login_data: schemas.UserLogin,  # ✅ USA O SCHEMA EXISTENTE
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    🔐 LOGIN - Aceita JSON com email, password, captcha_text
    ✅ Usa schema UserLogin do schemas.py
    ✅ CAPTCHA ID vem do HEADER (X-Captcha-ID)
    ✅ CAPTCHA TEXT vem do BODY (captcha_text)
    ✅ Rate limiting
    """
    
    client_ip = request.client.host
    
    # Rate limiting
    ip_allowed = await rate_limiter.check_rate_limit(f"login_ip:{client_ip}", 10, 900)
    email_allowed = await rate_limiter.check_rate_limit(f"login_email:{login_data.email}", 5, 900)
    
    if not ip_allowed or not email_allowed:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")
    
    # ✅ VALIDAR CAPTCHA - ID vem do HEADER, TEXT vem do BODY
    captcha_id = request.headers.get("X-Captcha-ID")
    
    if not captcha_id:
        raise HTTPException(status_code=400, detail="CAPTCHA ID não fornecido. Recarregue o CAPTCHA.")
    
    if not login_data.captcha_text:
        raise HTTPException(status_code=400, detail="CAPTCHA é obrigatório")
    
    if not captcha_manager.validate_captcha(captcha_id, login_data.captcha_text, client_ip):
        raise HTTPException(status_code=400, detail="CAPTCHA inválido ou expirado")
    
    # Buscar usuário
    user = crud.get_user_by_email(db, login_data.email)
    if not user or not user.verify_password(login_data.password):
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada")
    
    # Atualizar último login
    crud.update_last_login(db, user.id)
    
    # Dados para o token
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
        "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin
    }
    
    # Criar par de tokens
    tokens = jwt_manager.create_token_pair(user_data)
    
    # Salvar refresh token no banco
    user.set_refresh_token(
        tokens["refresh_token"],
        tokens["refresh_jti"],
        7
    )
    db.commit()
    
    # Dados para o frontend
    response_data = {
        "success": True,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],
        "user_name": user.name,
        "user_email": user.email,
        "workshop_name": user.workshop_name,
        "role": str(user.role),
        "plan": str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,
        "credits_display": "∞" if user.is_admin else str(user.credits),
        "message": "Login realizado com sucesso"
    }
    
    api_response = JSONResponse(content=response_data)
    
    # Setar cookies
    api_response = set_auth_cookies(
        response=api_response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"]
    )
    
    admin_tag = "👑 " if user.is_admin else ""
    logger.info(f"✅ {admin_tag}Login: {user.email}")
    
    return api_response


# ==============================================
# REGISTER - CORRIGIDO
# ==============================================

@router.post("/register")
async def register(
    request: Request,
    db: Session = Depends(get_db)
):
    """Registro com CAPTCHA - Aceita JSON"""
    
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Corpo da requisição inválido")
    
    name = body.get("name", "")
    email = body.get("email", "")
    password = body.get("password", "")
    workshop_name = body.get("workshop_name", "")
    captcha_text = body.get("captcha_text", "")
    
    # Validações
    if not all([name, email, password, workshop_name, captcha_text]):
        raise HTTPException(status_code=400, detail="Todos os campos são obrigatórios")
    
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter no mínimo 6 caracteres")
    
    # Rate limiting
    client_ip = request.client.host
    allowed = await rate_limiter.check_rate_limit(
        f"register:{client_ip}", 
        max_requests=3,
        window=3600
    )
    
    if not allowed:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 1 hora.")
    
    # Validar CAPTCHA
    captcha_id = request.headers.get("X-Captcha-ID")
    
    if not captcha_id:
        raise HTTPException(status_code=400, detail="CAPTCHA ID não fornecido. Recarregue o CAPTCHA.")
    
    if not captcha_text:
        raise HTTPException(status_code=400, detail="CAPTCHA é obrigatório")
    
    if not captcha_manager.validate_captcha(captcha_id, captcha_text, client_ip):
        raise HTTPException(status_code=400, detail="CAPTCHA inválido ou expirado")
    
    # Verificar email
    if crud.get_user_by_email(db, email):
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    # Criar usuário usando o schema UserCreate
    user_data = schemas.UserCreate(
        name=name,
        email=email,
        password=password,
        workshop_name=workshop_name
    )
    
    user = crud.create_user(db=db, user=user_data)
    logger.info(f"✅ Usuário registrado: {user.email}")
    
    return {
        "success": True,
        "message": "Conta criada com sucesso",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "workshop_name": user.workshop_name
        }
    }


# ==============================================
# VERIFICAÇÃO DE TOKEN
# ==============================================

@router.get("/check-token")
async def check_token(request: Request, db: Session = Depends(get_db)):
    """
    🔍 VERIFICAÇÃO DE TOKEN
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
            status_code=401,
            content={
                "status": "no_token",
                "message": "Nenhum token encontrado",
                "action": "redirect_to_login"
            }
        )
    
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
                    "message": "Token válido",
                    "user": user.email,
                    "name": user.name,
                    "is_admin": user.is_admin,
                    "credits": user.credits,
                    "credits_display": "∞" if user.is_admin else str(user.credits),
                    "expires_in": expires_in,
                    "action": "continue"
                }
    
    if refresh_token:
        logger.info("🔄 Token expirado - tentando refresh...")
        
        try:
            new_tokens = await jwt_manager.refresh_access_token(refresh_token, db)
            
            if new_tokens:
                payload = jwt_manager.decode_token(new_tokens["access_token"])
                email = payload.get("sub") or payload.get("email")
                user = crud.get_user_by_email(db, email)
                
                response_data = {
                    "status": "refreshed",
                    "message": "Token renovado",
                    "access_token": new_tokens["access_token"],
                    "refresh_token": new_tokens["refresh_token"],
                    "expires_in": new_tokens["expires_in"],
                    "user": user.email,
                    "name": user.name,
                    "is_admin": user.is_admin,
                    "credits": user.credits,
                    "credits_display": "∞" if user.is_admin else str(user.credits),
                    "action": "update_tokens"
                }
                
                response = JSONResponse(content=response_data)
                
                response = set_auth_cookies(
                    response=response,
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens["refresh_token"],
                    expires_in=new_tokens["expires_in"]
                )
                
                return response
                
        except Exception as e:
            logger.error(f"❌ Erro no refresh: {e}")
    
    logger.warning("❌ Refresh inválido - limpando tokens...")
    
    if refresh_token:
        try:
            await jwt_manager.logout(refresh_token, db)
        except:
            pass
    
    response = JSONResponse(
        status_code=401,
        content={
            "status": "invalid",
            "message": "Sessão expirada. Faça login novamente.",
            "action": "clear_storage_and_redirect"
        }
    )
    
    response = clear_auth_cookies(response)
    
    return response


# ==============================================
# REFRESH MANUAL
# ==============================================

@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: Session = Depends(get_db)
):
    """Renova access token manualmente - Aceita JSON"""
    
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        raise HTTPException(status_code=400, detail="Corpo inválido")
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token obrigatório")
    
    new_tokens = await jwt_manager.refresh_access_token(refresh_token, db)
    
    if not new_tokens:
        raise HTTPException(status_code=401, detail="Refresh token inválido")
    
    response_data = {
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": new_tokens["expires_in"],
        "message": "Token renovado"
    }
    
    response = JSONResponse(content=response_data)
    
    response = set_auth_cookies(
        response=response,
        access_token=new_tokens["access_token"],
        refresh_token=new_tokens["refresh_token"],
        expires_in=new_tokens["expires_in"]
    )
    
    return response


# ==============================================
# LOGOUT
# ==============================================

@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """Logout - invalida tokens e limpa cookies"""
    
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        refresh_token = None
    
    if refresh_token:
        await jwt_manager.logout(refresh_token, db)
    
    response = JSONResponse(content={
        "status": "logged_out",
        "message": "Logout realizado",
        "action": "clear_storage"
    })
    
    response = clear_auth_cookies(response)
    
    return response


# ==============================================
# ROTAS PROTEGIDAS
# ==============================================

@router.get("/me")
async def get_me(
    current_user = Depends(get_current_active_user)
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "workshop_name": current_user.workshop_name,
        "role": str(current_user.role),
        "plan": str(current_user.plan),
        "credits": current_user.credits,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active
    }


@router.post("/change-password")
async def change_password(
    request: Request,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Troca de senha - Aceita JSON"""
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Corpo inválido")
    
    current_password = body.get("current_password")
    new_password = body.get("new_password")
    
    if not current_password or not new_password:
        raise HTTPException(400, "Senha atual e nova senha são obrigatórias")
    
    if not hasher.verify_password(current_password, current_user.hashed_password):
        raise HTTPException(400, "Senha atual incorreta")
    
    if len(new_password) < 6:
        raise HTTPException(400, "Nova senha deve ter no mínimo 6 caracteres")
    
    new_hashed = hasher.hash_password(new_password)
    crud.update_user(db, current_user.id, {"hashed_password": new_hashed})
    
    current_user.revoke_refresh_token()
    db.commit()
    
    return {"message": "Senha alterada com sucesso"}


# ==============================================
# ROTAS DE ADMIN
# ==============================================

@router.get("/admin/users")
async def get_all_users(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    users = crud.get_all_users(db, skip=skip, limit=limit)
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "workshop_name": u.workshop_name,
            "role": str(u.role),
            "plan": str(u.plan),
            "credits": u.credits,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]


@router.get("/admin/stats")
async def get_stats(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    return crud.get_user_stats(db)


@router.post("/admin/make-admin")
async def make_admin(
    request: Request,
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    try:
        body = await request.json()
        email = body.get("email")
    except:
        raise HTTPException(400, "Corpo inválido")
    
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    
    user.is_admin = True
    db.commit()
    
    return {"message": f"{email} agora é admin"}


@router.post("/admin/remove-admin")
async def remove_admin(
    request: Request,
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    try:
        body = await request.json()
        email = body.get("email")
    except:
        raise HTTPException(400, "Corpo inválido")
    
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    
    user.is_admin = False
    db.commit()
    
    return {"message": f"Admin removido de {email}"}


@router.get("/admin/captcha-stats")
async def get_captcha_stats(
    current_user = Depends(get_current_admin_user)
):
    return captcha_manager.get_stats()