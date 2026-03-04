# backend/api/auth_routes.py
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
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

@router.post("/captcha/generate")
async def generate_captcha():
    """Gera CAPTCHA próprio (para versão custom)"""
    if captcha_manager.captcha_type == "custom":
        return captcha_manager.generate_custom_captcha()
    else:
        return {
            "site_key": captcha_manager.site_key,
            "type": captcha_manager.captcha_type
        }

@router.post("/register")
async def register(
    request: Request,
    user_data: schemas.UserCreate,
    db: Session = Depends(get_db),
    captcha_valid: bool = Depends(check_captcha)
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
    db: Session = Depends(get_db),
    captcha_valid: bool = Depends(check_captcha)
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
        "role": user.role.value if hasattr(user.role, 'value') else user.role
    })
    
    return {
        **tokens,
        "user_name": user.name,
        "user_email": user.email,
        "workshop_name": user.workshop_name,
        "role": user.role
    }

@router.post("/refresh")
async def refresh_token(
    refresh_data: schemas.TokenRefresh
):
    """Renova access token usando refresh token"""
    
    new_tokens = await jwt_manager.refresh_access_token(refresh_data.refresh_token)
    
    if not new_tokens:
        raise HTTPException(
            status_code=401,
            detail="Refresh token inválido ou expirado"
        )
    
    return new_tokens

@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme)
):
    """Faz logout invalidando o token atual"""
    
    await jwt_manager.logout(token)
    
    return {"message": "Logout realizado com sucesso"}

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