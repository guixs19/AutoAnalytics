# backend/api/auth_routes.py - VERSÃO FINAL COM CICLO DE VIDA COMPLETO
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

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])

# ==============================================
# ROTAS PÚBLICAS COM CAPTCHA
# ==============================================

@router.get("/captcha/generate")
async def generate_captcha(request: Request):
    """Gera CAPTCHA próprio"""
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
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )

@router.post("/register", response_model=schemas.UserResponse)
async def register(
    request: Request,
    user_data: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Registro com CAPTCHA"""
    
    # Rate limiting
    client_ip = request.client.host
    allowed = await rate_limiter.check_rate_limit(
        f"register:{client_ip}", 
        max_requests=3,
        window=3600
    )
    
    if not allowed:
        raise HTTPException(status_code=429, detail="Muitas tentativas")
    
    # Validar CAPTCHA
    captcha_id = request.headers.get("X-Captcha-ID")
    if not captcha_id or not user_data.captcha_text:
        raise HTTPException(status_code=400, detail="CAPTCHA obrigatório")
    
    if not captcha_manager.validate_captcha(captcha_id, user_data.captcha_text, client_ip):
        raise HTTPException(status_code=400, detail="CAPTCHA inválido")
    
    # Verificar email
    if crud.get_user_by_email(db, user_data.email):
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    # Criar usuário
    user = crud.create_user(db=db, user=user_data)
    logger.info(f"✅ Usuário registrado: {user.email}")
    
    return user

# ==============================================
# LOGIN - GERAÇÃO DO TOKEN
# ==============================================

@router.post("/login")
async def login(
    request: Request,
    login_data: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    """
    🔐 LOGIN - Gera token com vida de 15 minutos
    ✅ CAPTCHA validado
    ✅ Rate limiting por IP/email
    ✅ Cookies HTTP-only
    ✅ is_admin no payload
    """
    
    # Rate limiting
    client_ip = request.client.host
    ip_allowed = await rate_limiter.check_rate_limit(f"login_ip:{client_ip}", 10, 900)
    email_allowed = await rate_limiter.check_rate_limit(f"login_email:{login_data.email}", 5, 900)
    
    if not ip_allowed or not email_allowed:
        raise HTTPException(status_code=429, detail="Muitas tentativas")
    
    # Validar CAPTCHA
    captcha_id = request.headers.get("X-Captcha-ID")
    if not captcha_id or not login_data.captcha_text:
        raise HTTPException(status_code=400, detail="CAPTCHA obrigatório")
    
    if not captcha_manager.validate_captcha(captcha_id, login_data.captcha_text, client_ip):
        raise HTTPException(status_code=400, detail="CAPTCHA inválido")
    
    # Buscar usuário
    user = crud.get_user_by_email(db, login_data.email)
    if not user or not user.verify_password(login_data.password):
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada")
    
    # Atualizar último login
    crud.update_last_login(db, user.id)
    
    # ✅ Dados para o token (com is_admin)
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
        "credits": user.credits,
        "is_admin": user.is_admin  # 🔥 ESSENCIAL
    }
    
    # 🎫 CRIAR PAR DE TOKENS
    # access_token: 15 minutos
    # refresh_token: 7 dias (armazenado no banco)
    tokens = jwt_manager.create_token_pair(user_data)
    
    # Salvar refresh token no banco
    user.set_refresh_token(
        tokens["refresh_token"],
        tokens["refresh_jti"],
        7  # 7 dias
    )
    db.commit()
    
    # 📦 Dados para o frontend (incluindo is_admin)
    response_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],  # 900 segundos = 15 minutos
        "user_name": user.name,
        "user_email": user.email,
        "workshop_name": user.workshop_name,
        "role": str(user.role),
        "plan": str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,  # ✅ PARA O FRONTEND
        "credits_display": "∞" if user.is_admin else str(user.credits),
        "message": "Login realizado com sucesso"
    }
    
    # Criar resposta
    response = JSONResponse(content=response_data)
    
    # 🍪 Definir cookies HTTP-only
    response = set_auth_cookies(
        response=response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"]  # 15 minutos
    )
    
    admin_tag = "👑 " if user.is_admin else ""
    logger.info(f"✅ {admin_tag}Login: {user.email} - Token válido por 15min")
    
    return response

# ==============================================
# VERIFICAÇÃO DE TOKEN (USADA PELO FRONTEND)
# ==============================================

@router.get("/check-token")
async def check_token(request: Request, db: Session = Depends(get_db)):
    """
    🔍 VERIFICAÇÃO DE TOKEN - CORAÇÃO DO SISTEMA
    ✅ Se token válido (<15min) → retorna OK
    ✅ Se token expirado (>15min) → tenta refresh
    ✅ Se refresh inválido → limpa tudo (força novo login)
    """
    
    # Tentar pegar token do cookie ou header
    access_token = request.cookies.get("access_token")
    if access_token and access_token.startswith("Bearer "):
        access_token = access_token.replace("Bearer ", "")
    
    if not access_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            access_token = auth_header.replace("Bearer ", "")
    
    refresh_token = request.cookies.get("refresh_token")
    
    # CASO 1: SEM TOKEN ALGUM
    if not access_token and not refresh_token:
        logger.info("🔍 Check-token: Sem tokens - redirecionar para login")
        return JSONResponse(
            status_code=401,
            content={
                "status": "no_token",
                "message": "Nenhum token encontrado",
                "action": "redirect_to_login"
            }
        )
    
    # Verificar access token atual
    if access_token:
        payload = await jwt_manager.verify_token_async(access_token, "access")
        
        # ✅ CASO 2: TOKEN VÁLIDO (menos de 15 minutos)
        if payload:
            # Buscar usuário para dados atualizados
            email = payload.get("sub") or payload.get("email")
            user = crud.get_user_by_email(db, email)
            
            if user and user.is_active:
                logger.info(f"✅ Token válido para {email} - ainda dentro dos 15min")
                
                # Calcular tempo restante
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
    
    # ❌ CASO 3: TOKEN EXPIRADO (>15 minutos) - TENTAR REFRESH
    if refresh_token:
        logger.info("🔄 Token expirado (>15min) - tentando refresh...")
        
        try:
            # Tentar gerar novo access token
            new_tokens = await jwt_manager.refresh_access_token(refresh_token, db)
            
            if new_tokens:
                # ✅ REFRESH BEM-SUCEDIDO - Novo token gerado
                logger.info("✅ Refresh bem-sucedido - novo token de 15min gerado")
                
                # Decodificar para pegar dados do usuário
                payload = jwt_manager.decode_token(new_tokens["access_token"])
                email = payload.get("sub") or payload.get("email")
                user = crud.get_user_by_email(db, email)
                
                # Criar resposta com novos tokens
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
                
                # Atualizar cookies
                response = set_auth_cookies(
                    response=response,
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens["refresh_token"],
                    expires_in=new_tokens["expires_in"]
                )
                
                return response
                
        except Exception as e:
            logger.error(f"❌ Erro no refresh: {e}")
    
    # ❌ CASO 4: REFRESH INVÁLIDO - LIMPAR TUDO
    logger.warning("❌ Refresh inválido - limpando tokens...")
    
    # Invalidar refresh token no banco se existir
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
            "action": "clear_storage_and_redirect"  # 🔥 FRONTEND DEVE LIMPAR LOCALSTORAGE
        }
    )
    
    # Limpar cookies
    response = clear_auth_cookies(response)
    
    return response

# ==============================================
# REFRESH MANUAL (SE PRECISAR)
# ==============================================

@router.post("/refresh")
async def refresh_token(
    refresh_data: schemas.TokenRefresh,
    db: Session = Depends(get_db)
):
    """Renova access token manualmente"""
    
    new_tokens = await jwt_manager.refresh_access_token(refresh_data.refresh_token, db)
    
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
    
    # Atualizar cookies
    response = set_auth_cookies(
        response=response,
        access_token=new_tokens["access_token"],
        refresh_token=new_tokens["refresh_token"],
        expires_in=new_tokens["expires_in"]
    )
    
    logger.info("✅ Token renovado manualmente")
    
    return response

# ==============================================
# LOGOUT - LIMPAR TUDO
# ==============================================

@router.post("/logout")
async def logout(
    refresh_data: Optional[schemas.TokenRefresh] = None,
    db: Session = Depends(get_db)
):
    """Logout - invalida tokens e limpa cookies"""
    
    if refresh_data and refresh_data.refresh_token:
        await jwt_manager.logout(refresh_data.refresh_token, db)
    
    response = JSONResponse(content={
        "status": "logged_out",
        "message": "Logout realizado",
        "action": "clear_storage"  # 🔥 FRONTEND DEVE LIMPAR LOCALSTORAGE
    })
    
    # Limpar cookies
    response = clear_auth_cookies(response)
    
    logger.info("✅ Logout - tokens invalidados e cookies limpos")
    
    return response

# ==============================================
# ROTAS PROTEGIDAS
# ==============================================

@router.get("/me", response_model=schemas.UserResponse)
async def get_me(
    current_user = Depends(get_current_active_user)
):
    """Retorna perfil do usuário atual"""
    return current_user

@router.put("/me", response_model=schemas.UserResponse)
async def update_me(
    user_update: schemas.UserUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza perfil do usuário"""
    
    update_data = user_update.dict(exclude_unset=True)
    
    if "password" in update_data:
        update_data["hashed_password"] = hasher.hash_password(update_data.pop("password"))
    
    updated = crud.update_user(db, current_user.id, update_data)
    return updated

@router.post("/change-password")
async def change_password(
    password_data: schemas.PasswordChange,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Troca de senha"""
    
    if not hasher.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(400, "Senha atual incorreta")
    
    new_hashed = hasher.hash_password(password_data.new_password)
    crud.update_user(db, current_user.id, {"hashed_password": new_hashed})
    
    # Invalidar refresh tokens por segurança
    current_user.revoke_refresh_token()
    db.commit()
    
    return {"message": "Senha alterada com sucesso"}

# ==============================================
# ROTAS DE ADMIN
# ==============================================

@router.get("/admin/users", response_model=List[schemas.UserResponse])
async def get_all_users(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Lista todos os usuários (admin)"""
    return crud.get_all_users(db, skip=skip, limit=limit)

@router.get("/admin/stats")
async def get_stats(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Estatísticas do sistema (admin)"""
    return crud.get_user_stats(db)

@router.post("/admin/make-admin")
async def make_admin(
    email: str,
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Torna um usuário admin"""
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    
    user.is_admin = True
    db.commit()
    
    logger.info(f"👑 Admin {current_user.email} tornou {email} admin")
    return {"message": f"{email} agora é admin"}

@router.post("/admin/remove-admin")
async def remove_admin(
    email: str,
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Remove privilégios de admin"""
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    
    user.is_admin = False
    db.commit()
    
    logger.info(f"👑 Admin {current_user.email} removeu admin de {email}")
    return {"message": f"Admin removido de {email}"}

@router.get("/admin/captcha-stats")
async def get_captcha_stats(
    current_user = Depends(get_current_admin_user)
):
    """Estatísticas de CAPTCHA (admin)"""
    return captcha_manager.get_stats()