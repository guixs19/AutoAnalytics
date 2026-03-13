# backend/api/auth_routes.py - VERSÃO CORRIGIDA COM IMAGEM DIRETA
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend import crud, schemas
from backend.security import (
    hasher,
    captcha_manager,
    jwt_manager,
    rate_limiter,
    get_current_active_user,
    get_current_admin_user,
    check_captcha,
    oauth2_scheme
)

router = APIRouter(tags=["authentication"])

# ==============================================
# ROTAS PÚBLICAS COM CAPTCHA
# ==============================================

# 🔥 CORRIGIDO: Agora retorna imagem direta em vez de JSON
@router.get("/captcha/generate")
async def generate_captcha():
    """Gera CAPTCHA próprio e retorna imagem direta"""
    print("🔄 Gerando CAPTCHA...")
    
    if captcha_manager.captcha_type == "custom":
        # Gerar imagem e ID
        img_bytes, captcha_id = captcha_manager.generate_custom_captcha_image()
        
        # 🔥 IMPORTANTE: Retornar imagem com headers especiais
        return Response(
            content=img_bytes,
            media_type="image/png",
            headers={
                "X-Captcha-ID": captcha_id,  # Enviar ID no header
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    else:
        return {
            "site_key": captcha_manager.site_key,
            "type": captcha_manager.captcha_type
        }

@router.post("/register")
async def register(
    request: Request,
    user_data: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Registro público com CAPTCHA obrigatório"""
    
    # Rate limiting por IP
    client_ip = request.client.host
    allowed = await rate_limiter.check_rate_limit(
        f"register:{client_ip}", 
        max_requests=3,
        window=3600
    )
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de registro. Tente novamente mais tarde."
        )
    
    # 🔥 VALIDAR CAPTCHA CUSTOMIZADO
    if captcha_manager.captcha_type == "custom":
        captcha_id = request.headers.get("X-Captcha-ID")
        captcha_text = user_data.captcha_text
        
        if not captcha_id or not captcha_text:
            raise HTTPException(
                status_code=400,
                detail="CAPTCHA ID e texto são obrigatórios"
            )
        
        if not captcha_manager.validate_custom_captcha(captcha_id, captcha_text):
            raise HTTPException(
                status_code=400,
                detail="CAPTCHA inválido"
            )
    
    # Impede registro como admin via API pública
    if user_data.role == schemas.UserRole.ADMIN:
        user_data.role = schemas.UserRole.USER
    
    # Verificar se email já existe
    db_user = crud.get_user_by_email(db, email=user_data.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    # Criar usuário
    user = crud.create_user(db=db, user=user_data)
    
    return user

@router.post("/login", response_model=schemas.Token)
async def login(
    request: Request,
    login_data: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    """Login com CAPTCHA obrigatório"""
    
    # Rate limiting por email e IP
    client_ip = request.client.host
    
    # Tentativas por IP
    ip_allowed = await rate_limiter.check_rate_limit(
        f"login_ip:{client_ip}",
        max_requests=10,
        window=900
    )
    
    # Tentativas por email
    email_allowed = await rate_limiter.check_rate_limit(
        f"login_email:{login_data.email}",
        max_requests=5,
        window=900
    )
    
    if not ip_allowed or not email_allowed:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Tente novamente mais tarde."
        )
    
    # 🔥 VALIDAR CAPTCHA CUSTOMIZADO
    if captcha_manager.captcha_type == "custom":
        captcha_id = request.headers.get("X-Captcha-ID")
        captcha_text = login_data.captcha_text
        
        if not captcha_id or not captcha_text:
            raise HTTPException(
                status_code=400,
                detail="CAPTCHA ID e texto são obrigatórios"
            )
        
        if not captcha_manager.validate_custom_captcha(captcha_id, captcha_text):
            raise HTTPException(
                status_code=400,
                detail="CAPTCHA inválido"
            )
    
    # Buscar usuário
    user = crud.get_user_by_email(db, email=login_data.email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )
    
    # Verificar senha com Argon2
    if not user.verify_password(login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada"
        )
    
    # Atualiza último login
    crud.update_last_login(db, user.id)
    
    # Cria par de tokens
    tokens = jwt_manager.create_token_pair({
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
        "credits": user.credits
    })
    
    # Salvar refresh token no banco
    user.set_refresh_token(
        tokens["refresh_token"], 
        tokens["refresh_jti"],
        7  # 7 dias
    )
    db.commit()
    
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "user_name": user.name,
        "user_email": user.email,
        "workshop_name": user.workshop_name,
        "role": user.role,
        "plan": user.plan,
        "credits": user.credits,
        "expires_in": tokens["expires_in"]
    }

@router.post("/refresh")
async def refresh_token(
    refresh_data: schemas.TokenRefresh,
    db: Session = Depends(get_db)
):
    """Renova access token usando refresh token"""
    
    new_tokens = await jwt_manager.refresh_access_token(
        refresh_data.refresh_token, 
        db
    )
    
    if not new_tokens:
        raise HTTPException(
            status_code=401,
            detail="Refresh token inválido ou expirado"
        )
    
    return new_tokens

@router.post("/logout")
async def logout(
    refresh_data: schemas.TokenRefresh,
    db: Session = Depends(get_db)
):
    """Faz logout invalidando o refresh token no banco"""
    
    success = await jwt_manager.logout(refresh_data.refresh_token, db)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Erro ao fazer logout"
        )
    
    return {"message": "Logout realizado com sucesso"}

# ==============================================
# ROTA DE VALIDAÇÃO DE TOKEN (NOVA)
# ==============================================

@router.get("/check-token")
async def check_token(
    current_user: schemas.UserResponse = Depends(get_current_active_user)
):
    """
    Verifica se o token atual é válido.
    Se o token for inválido, o 'get_current_active_user' vai lançar 401 automaticamente.
    Se for válido, entra aqui e confirmamos ao frontend.
    """
    print(f"✅ Token válido para usuário: {current_user.email}")
    
    return {
        "status": "ok",
        "message": "Token válido",
        "user": current_user.email,
        "name": current_user.name,
        "expires_in": jwt_manager.access_expire_minutes * 60
    }

# ==============================================
# ROTAS PROTEGIDAS
# ==============================================

@router.get("/me", response_model=schemas.UserResponse)
async def get_my_profile(
    current_user: schemas.UserResponse = Depends(get_current_active_user)
):
    """Retorna perfil do usuário logado"""
    return current_user

@router.put("/me", response_model=schemas.UserResponse)
async def update_my_profile(
    user_update: schemas.UserUpdate,
    current_user: schemas.UserResponse = Depends(get_current_active_user),
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
    current_user: schemas.UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Troca de senha com verificação da atual"""
    
    if not hasher.verify_password(password_data.current_password, 
                                  current_user.hashed_password):
        raise HTTPException(400, "Senha atual incorreta")
    
    new_hashed = hasher.hash_password(password_data.new_password)
    
    crud.update_user(db, current_user.id, {"hashed_password": new_hashed})
    
    return {"message": "Senha alterada com sucesso"}

# ==============================================
# ROTAS DE ADMIN
# ==============================================

@router.get("/admin/users", response_model=List[schemas.UserResponse])
async def get_all_users_admin(
    current_user: schemas.UserResponse = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Lista todos os usuários (somente admin)"""
    return crud.get_all_users(db, skip=skip, limit=limit)

@router.get("/admin/stats")
async def get_user_stats_admin(
    current_user: schemas.UserResponse = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Estatísticas do sistema (somente admin)"""
    return crud.get_user_stats(db)