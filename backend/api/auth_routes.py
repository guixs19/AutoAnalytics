# backend/api/auth_routes.py - VERSÃO ATUALIZADA COM SUPORTE A ADMIN
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend import crud, schemas
from backend.security import (
    hasher,
    captcha_manager,      # ✅ NOVO: CAPTCHA próprio
    jwt_manager,
    rate_limiter,
    get_current_active_user,
    get_current_admin_user,
    check_captcha,
    oauth2_scheme,
    set_auth_cookies,
    clear_auth_cookies
)

router = APIRouter(tags=["authentication"])

# ==============================================
# ROTAS PÚBLICAS COM CAPTCHA PRÓPRIO
# ==============================================

@router.get("/captcha/generate")
async def generate_captcha(request: Request):
    """Gera CAPTCHA próprio e retorna imagem direta"""
    print("🔄 Gerando CAPTCHA próprio...")
    
    # Pegar IP do cliente para vincular ao CAPTCHA
    client_ip = request.client.host if request.client else "unknown"
    
    # Gerar imagem e ID (uso único, expira em 2 minutos)
    img_bytes, captcha_id = captcha_manager.generate_captcha_image(client_ip)
    
    print(f"✅ CAPTCHA gerado para IP {client_ip}: {captcha_id}")
    
    # Retornar imagem com headers especiais
    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={
            "X-Captcha-ID": captcha_id,  # ID único do CAPTCHA
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@router.post("/register")
async def register(
    request: Request,
    user_data: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Registro público com CAPTCHA próprio"""
    
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
    
    # 🔥 VALIDAR CAPTCHA PRÓPRIO
    captcha_id = request.headers.get("X-Captcha-ID")
    captcha_text = user_data.captcha_text
    
    if not captcha_id or not captcha_text:
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA ID e texto são obrigatórios"
        )
    
    # Validar CAPTCHA (uso único, 2 minutos, mesmo IP)
    if not captcha_manager.validate_captcha(captcha_id, captcha_text, client_ip):
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA inválido, expirado ou já utilizado"
        )
    
    print(f"✅ CAPTCHA validado para registro: {client_ip}")
    
    # Impede registro como admin via API pública
    if user_data.role == schemas.UserRole.ADMIN:
        user_data.role = schemas.UserRole.USER
    
    # Verificar se email já existe
    db_user = crud.get_user_by_email(db, email=user_data.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    # Criar usuário
    user = crud.create_user(db=db, user=user_data)
    
    print(f"✅ Usuário registrado: {user.email}")
    
    return user

@router.post("/login")
async def login(
    request: Request,
    login_data: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    """Login com CAPTCHA próprio - Retorna cookies HTTP-only"""
    
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
    
    # 🔥 VALIDAR CAPTCHA PRÓPRIO
    captcha_id = request.headers.get("X-Captcha-ID")
    captcha_text = login_data.captcha_text
    
    if not captcha_id or not captcha_text:
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA ID e texto são obrigatórios"
        )
    
    # Validar CAPTCHA (uso único, 2 minutos, mesmo IP)
    if not captcha_manager.validate_captcha(captcha_id, captcha_text, client_ip):
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA inválido, expirado ou já utilizado"
        )
    
    print(f"✅ CAPTCHA validado para login: {client_ip}")
    
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
    
    # ✅ INCLUIR IS_ADMIN NOS DADOS DO USUÁRIO
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
        "credits": user.credits,
        "is_admin": user.is_admin  # ✅ ADICIONADO
    }
    
    # Cria par de tokens
    tokens = jwt_manager.create_token_pair(user_data)
    
    # Salvar refresh token no banco
    user.set_refresh_token(
        tokens["refresh_token"], 
        tokens["refresh_jti"],
        7  # 7 dias
    )
    db.commit()
    
    # 🔥 CRIAR RESPOSTA COM COOKIES - INCLUINDO IS_ADMIN
    response_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "user_name": user.name,
        "user_email": user.email,
        "workshop_name": user.workshop_name,
        "role": str(user.role),
        "plan": str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,  # ✅ ADICIONADO
        "credits_display": "∞" if user.is_admin else str(user.credits),  # ✅ ADICIONADO
        "expires_in": tokens["expires_in"],
        "message": "Login realizado com sucesso"
    }
    
    # Criar resposta JSON
    response = JSONResponse(content=response_data)
    
    # Definir os cookies HTTP-only
    response = set_auth_cookies(
        response=response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"]
    )
    
    admin_tag = "👑 " if user.is_admin else ""
    print(f"✅ {admin_tag}Login bem-sucedido: {user.email} - Cookies definidos")
    
    return response

@router.post("/refresh")
async def refresh_token(
    refresh_data: schemas.TokenRefresh,
    db: Session = Depends(get_db)
):
    """Renova access token usando refresh token e atualiza cookies"""
    
    new_tokens = await jwt_manager.refresh_access_token(
        refresh_data.refresh_token, 
        db
    )
    
    if not new_tokens:
        raise HTTPException(
            status_code=401,
            detail="Refresh token inválido ou expirado"
        )
    
    # Criar resposta com novos tokens
    response_data = {
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": new_tokens["expires_in"],
        "message": "Token renovado com sucesso"
    }
    
    response = JSONResponse(content=response_data)
    
    # Atualizar os cookies com os novos tokens
    response = set_auth_cookies(
        response=response,
        access_token=new_tokens["access_token"],
        refresh_token=new_tokens["refresh_token"],
        expires_in=new_tokens["expires_in"]
    )
    
    print(f"✅ Token renovado - Cookies atualizados")
    
    return response

@router.post("/logout")
async def logout(
    refresh_data: schemas.TokenRefresh,
    db: Session = Depends(get_db)
):
    """Faz logout invalidando o refresh token no banco e removendo cookies"""
    
    success = await jwt_manager.logout(refresh_data.refresh_token, db)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Erro ao fazer logout"
        )
    
    # Criar resposta e remover cookies
    response = JSONResponse(content={
        "message": "Logout realizado com sucesso"
    })
    
    # Remover os cookies
    response = clear_auth_cookies(response)
    
    print(f"✅ Logout realizado - Cookies removidos")
    
    return response

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
        "is_admin": current_user.is_admin,  # ✅ ADICIONADO
        "credits": current_user.credits,
        "credits_display": "∞" if current_user.is_admin else str(current_user.credits),
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
    users = crud.get_all_users(db, skip=skip, limit=limit)
    return users

@router.get("/admin/stats")
async def get_user_stats_admin(
    current_user: schemas.UserResponse = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Estatísticas do sistema (somente admin)"""
    return crud.get_user_stats(db)

# ✅ NOVA ROTA: Tornar usuário admin (somente admin)
@router.post("/admin/make-admin")
async def make_user_admin(
    email: str,
    current_user: schemas.UserResponse = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Torna um usuário administrador (somente admin)"""
    user = crud.get_user_by_email(db, email)
    
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    
    if user.is_admin:
        return {"message": f"{email} já é administrador"}
    
    user.is_admin = True
    db.commit()
    
    print(f"👑 Admin {current_user.email} tornou {email} administrador")
    return {"message": f"{email} agora é administrador"}

# ✅ NOVA ROTA: Remover admin (somente admin)
@router.post("/admin/remove-admin")
async def remove_user_admin(
    email: str,
    current_user: schemas.UserResponse = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Remove privilégios de admin (somente admin)"""
    user = crud.get_user_by_email(db, email)
    
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    
    if not user.is_admin:
        return {"message": f"{email} não é administrador"}
    
    user.is_admin = False
    db.commit()
    
    print(f"👑 Admin {current_user.email} removeu admin de {email}")
    return {"message": f"Privilégios de admin removidos de {email}"}

# ==============================================
# ROTA DE ADMIN PARA VER CAPTCHAS ATIVOS (DEBUG)
# ==============================================

@router.get("/admin/captcha-stats")
async def get_captcha_stats(
    current_user: schemas.UserResponse = Depends(get_current_admin_user)
):
    """Retorna estatísticas dos CAPTCHAS ativos (somente admin)"""
    return captcha_manager.get_stats()