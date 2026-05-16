# backend/api/auth_routes.py - VERSÃO COMPLETA COM TODAS AS ROTAS INCLUINDO REGISTER CORRIGIDO
"""
Rotas de autenticação com CAPTCHA de números rabiscados
"""

from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import secrets
import time

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
# DECORATORS PARA HIERARQUIA DE ADMIN
# ==============================================

def require_super_admin(func):
    """Decorator que só permite SUPER_ADMIN executar a função"""
    from functools import wraps
    @wraps(func)
    async def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Permissão de admin necessária")
        
        if not hasattr(current_user, 'admin_level') or current_user.admin_level != "super_admin":
            logger.warning(f"⚠️ Tentativa de acesso a super admin por: {current_user.email}")
            raise HTTPException(status_code=403, detail="Acesso restrito a super administradores")
        
        return await func(*args, **kwargs)
    return wrapper


def require_min_admin_level(required_level: str):
    """Decorator que exige nível mínimo de admin"""
    from functools import wraps
    levels = {"moderator": 1, "admin": 2, "super_admin": 3}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(status_code=401, detail="Não autenticado")
            
            if not current_user.is_admin:
                raise HTTPException(status_code=403, detail="Permissão de admin necessária")
            
            user_level = getattr(current_user, 'admin_level', None)
            if not user_level or levels.get(user_level, 0) < levels.get(required_level, 0):
                logger.warning(f"⚠️ Nível insuficiente: {current_user.email} ({user_level}) tentou acessar nível {required_level}")
                raise HTTPException(status_code=403, detail=f"Nível mínimo necessário: {required_level}")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ==============================================
# REGISTER - ROTA DE CADASTRO CORRIGIDA
# ==============================================

@router.post("/register")
async def register(
    register_data: schemas.UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Registro de novo usuário
    URL: /api/auth/register
    
    Body esperado:
    {
        "name": "Nome do usuário",
        "email": "email@exemplo.com",
        "password": "senha123",
        "workshop_name": "Oficina Exemplo" (opcional),
        "phone": "11999999999" (opcional),
        "captcha_text": "1234" (opcional, se usar CAPTCHA)
    }
    """
    
    client_ip = request.client.host if request.client else "unknown"
    
    # VALIDAÇÃO 1: CAPTCHA (opcional - pode ser obrigatório se preferir)
    captcha_id = request.headers.get("X-Captcha-ID")
    captcha_text = register_data.captcha_text
    
    # Se o CAPTCHA foi enviado, validar
    if captcha_id and captcha_text:
        if not await captcha_manager.validate_captcha_async(captcha_id, captcha_text, request):
            logger.warning(f"❌ CAPTCHA inválido no registro - IP: {client_ip}")
            raise HTTPException(
                status_code=400, 
                detail="❌ Código CAPTCHA incorreto! Digite os números que aparecem na imagem."
            )
        logger.info(f"✅ CAPTCHA validado para registro - IP: {client_ip}")
    
    # VALIDAÇÃO 2: Rate limiting para registro (evitar spam)
    ip_allowed = await rate_limiter.check_rate_limit(f"register_ip:{client_ip}", 5, 3600)  # 5 tentativas por hora
    
    if not ip_allowed:
        raise HTTPException(
            status_code=429, 
            detail="Muitas tentativas de registro deste IP. Aguarde 1 hora antes de tentar novamente."
        )
    
    # VALIDAÇÃO 3: Verificar se email já existe
    existing_user = crud.get_user_by_email(db, register_data.email)
    if existing_user:
        logger.warning(f"⚠️ Tentativa de registro com email existente: {register_data.email} - IP: {client_ip}")
        raise HTTPException(
            status_code=400, 
            detail="Este email já está cadastrado. Faça login ou recupere sua senha."
        )
    
    # VALIDAÇÃO 4: Senha forte
    if len(register_data.password) < 6:
        raise HTTPException(
            status_code=400, 
            detail="A senha deve ter no mínimo 6 caracteres."
        )
    
    # Criar usuário usando o crud.create_user (que já espera schemas.UserCreate)
    try:
        # O crud.create_user já faz o hash da senha e todas as validações
        new_user = crud.create_user(db, register_data)
        
        # Log de registro bem-sucedido
        logger.info(f"✅ NOVO USUÁRIO REGISTRADO: {new_user.email} - Nome: {new_user.name} - IP: {client_ip}")
        
        # Retornar sucesso
        return {
            "success": True,
            "message": "Cadastro realizado com sucesso! Agora você pode fazer login.",
            "user_id": new_user.id,
            "user_email": new_user.email,
            "user_name": new_user.name,
            "credits": new_user.credits,
            "redirect_to": "/login"
        }
        
    except ValueError as e:
        # Erro de validação (ex: email duplicado)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Erro ao registrar usuário: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Erro interno ao criar usuário. Tente novamente mais tarde."
        )


# ==============================================
# CAPTCHA ROUTES - ROTAS DE NÚMEROS RABISCADOS
# ==============================================

@router.get("/captcha/generate")
async def generate_captcha(request: Request, session_type: str = "login"):
    """
    Gera CAPTCHA com números distorcidos/rabiscados
    URL: /api/auth/captcha/generate
    O usuário deve reescrever os números que aparecem na imagem
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        
        # Rate limit: máximo 30 CAPTCHAs por 5 minutos
        allowed = await rate_limiter.check_rate_limit(f"captcha:{client_ip}", 30, 300)
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Muitas solicitações de CAPTCHA. Aguarde alguns minutos."
            )
        
        # Gerar imagem CAPTCHA
        img_bytes, captcha_id = await captcha_manager.generate_captcha_image_async(request, session_type)
        
        # Determinar o tipo de conteúdo
        content_type = "image/png" if img_bytes.startswith(b'\x89PNG') else "image/svg+xml"
        
        # Retornar imagem com headers
        return Response(
            content=img_bytes,
            media_type=content_type,
            headers={
                "X-Captcha-ID": captcha_id,
                "X-Captcha-Expires": "120",
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
                "Access-Control-Expose-Headers": "X-Captcha-ID, X-Captcha-Expires"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao gerar CAPTCHA: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar desafio: {str(e)}")


@router.post("/captcha/validate")
async def validate_captcha_endpoint(request: Request):
    """Valida resposta do CAPTCHA de números"""
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Corpo inválido")
    
    captcha_id = body.get("captcha_id")
    captcha_text = body.get("captcha_text")
    
    if not captcha_id or not captcha_text:
        raise HTTPException(status_code=400, detail="CAPTCHA ID e resposta são obrigatórios")
    
    valid = await captcha_manager.validate_captcha_async(captcha_id, captcha_text, request)
    
    return {
        "valid": valid,
        "message": "✅ Código correto!" if valid else "❌ Código incorreto. Digite os números que aparecem na imagem."
    }


@router.get("/captcha/status/{captcha_id}")
async def get_captcha_status(captcha_id: str):
    """Verifica status de um CAPTCHA"""
    # Verificar se existe no store
    if not hasattr(captcha_manager, 'store') or captcha_id not in captcha_manager.store._store:
        return {"status": "not_found", "message": "CAPTCHA não encontrado"}
    
    session = captcha_manager.store._store[captcha_id]
    
    if session.is_expired():
        return {"status": "expired", "message": "CAPTCHA expirado. Atualize a imagem."}
    
    if session.used:
        return {"status": "used", "message": "CAPTCHA já utilizado"}
    
    return {
        "status": "active",
        "expires_in": session.time_remaining(),
        "message": f"Desafio válido por {session.time_remaining()} segundos"
    }


# ==============================================
# LOGIN (com CAPTCHA de números)
# ==============================================

@router.post("/login")
async def login(
    login_data: schemas.UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Login com CAPTCHA de números (reescrever o que aparece na imagem)"""
    
    client_ip = request.client.host if request.client else "unknown"
    
    # VALIDAÇÃO 1: CAPTCHA
    captcha_id = request.headers.get("X-Captcha-ID") or login_data.captcha_id
    captcha_text = login_data.captcha_text
    
    if not captcha_id:
        raise HTTPException(status_code=400, detail="CAPTCHA não carregado. Recarregue a página.")
    
    if not captcha_text:
        raise HTTPException(status_code=400, detail="Digite os números que aparecem na imagem.")
    
    if not await captcha_manager.validate_captcha_async(captcha_id, captcha_text, request):
        logger.warning(f"❌ CAPTCHA incorreto - IP: {client_ip}")
        raise HTTPException(status_code=400, detail="❌ Código incorreto! Digite os números da imagem.")
    
    logger.info(f"✅ CAPTCHA validado para IP: {client_ip}")
    
    # VALIDAÇÃO 2: Rate limiting
    ip_allowed = await rate_limiter.check_rate_limit(f"login_ip:{client_ip}", 10, 900)
    email_allowed = await rate_limiter.check_rate_limit(f"login_email:{login_data.email}", 5, 900)
    
    if not ip_allowed or not email_allowed:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")
    
    # VALIDAÇÃO 3: Usuário - usando authenticate_user do crud
    user = crud.authenticate_user(db, login_data.email, login_data.password)
    
    if not user:
        logger.warning(f"❌ Falha de login - IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada.")
    
    # Atualizar último login
    crud.update_last_login(db, user.id)
    
    # Criar tokens
    user_data = {
        "sub": user.email,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
        "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
        "credits": user.credits,
        "is_admin": user.is_admin,
        "admin_level": user.admin_level if hasattr(user, 'admin_level') else None
    }
    
    tokens = jwt_manager.create_token_pair(user_data)
    
    # Salvar refresh token
    user.set_refresh_token(tokens["refresh_token"], tokens["refresh_jti"], 7)
    db.commit()
    
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
        "admin_level": user.admin_level if hasattr(user, 'admin_level') else None,
        "credits_display": "∞" if user.is_admin else str(user.credits),
        "message": "Login realizado com sucesso"
    }
    
    api_response = JSONResponse(content=response_data)
    api_response = set_auth_cookies(api_response, tokens["access_token"], tokens["refresh_token"], tokens["expires_in"])
    
    logger.info(f"✅ Login: {user.email} - IP: {client_ip}")
    
    return api_response


# ==============================================
# VERIFICAÇÃO DE TOKEN
# ==============================================

@router.get("/check-token")
async def check_token(request: Request, db: Session = Depends(get_db)):
    """Verifica status do token"""
    
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
            content={"status": "no_token", "message": "Nenhum token encontrado", "action": "redirect_to_login"}
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
                    "admin_level": user.admin_level if hasattr(user, 'admin_level') else None,
                    "credits": user.credits,
                    "credits_display": "∞" if user.is_admin else str(user.credits),
                    "expires_in": expires_in,
                    "action": "continue"
                }
    
    if refresh_token:
        logger.info("🔄 Token expirado - tentando refresh...")
        
        try:
            new_tokens = await jwt_manager.refresh_access_token(refresh_token, db, access_token)
            
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
                    "admin_level": user.admin_level if hasattr(user, 'admin_level') else None,
                    "credits": user.credits,
                    "credits_display": "∞" if user.is_admin else str(user.credits),
                    "action": "update_tokens"
                }
                
                response = JSONResponse(content=response_data)
                response = set_auth_cookies(response, new_tokens["access_token"], new_tokens["refresh_token"], new_tokens["expires_in"])
                
                return response
        except Exception as e:
            logger.error(f"❌ Erro no refresh: {e}")
    
    logger.warning("❌ Refresh inválido - limpando tokens...")
    
    if refresh_token:
        try:
            await jwt_manager.logout(refresh_token, db, access_token)
        except:
            pass
    
    response = JSONResponse(
        status_code=401,
        content={"status": "invalid", "message": "Sessão expirada. Faça login novamente.", "action": "clear_storage_and_redirect"}
    )
    response = clear_auth_cookies(response)
    
    return response


# ==============================================
# REFRESH MANUAL
# ==============================================

@router.post("/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    """Renova access token manualmente"""
    
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
        old_access_token = body.get("old_access_token")
    except:
        raise HTTPException(status_code=400, detail="Corpo inválido")
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token obrigatório")
    
    new_tokens = await jwt_manager.refresh_access_token(refresh_token, db, old_access_token)
    
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
    response = set_auth_cookies(response, new_tokens["access_token"], new_tokens["refresh_token"], new_tokens["expires_in"])
    
    return response


# ==============================================
# LOGOUT
# ==============================================

@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Logout - invalida tokens e limpa cookies"""
    
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        refresh_token = None
    
    access_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.replace("Bearer ", "")
    
    if refresh_token:
        await jwt_manager.logout(refresh_token, db, access_token)
    
    response = JSONResponse(content={"status": "logged_out", "message": "Logout realizado com sucesso", "action": "clear_storage"})
    response = clear_auth_cookies(response)
    
    return response


# ==============================================
# ROTAS PROTEGIDAS
# ==============================================

@router.get("/me")
async def get_me(current_user = Depends(get_current_active_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "workshop_name": current_user.workshop_name,
        "role": str(current_user.role),
        "plan": str(current_user.plan),
        "credits": current_user.credits,
        "is_admin": current_user.is_admin,
        "admin_level": current_user.admin_level if hasattr(current_user, 'admin_level') else None,
        "is_active": current_user.is_active
    }


@router.post("/change-password")
async def change_password(
    request: Request,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Troca de senha"""
    
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
    """Lista todos os usuários (admin nível 1+ pode ver)"""
    users = crud.get_all_users(db, skip=skip, limit=limit)
    
    result = []
    for u in users:
        user_data = {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "workshop_name": u.workshop_name,
            "role": str(u.role),
            "plan": str(u.plan),
            "credits": u.credits,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        
        if current_user.is_admin:
            user_data.update({
                "is_admin": u.is_admin,
                "admin_level": u.admin_level if hasattr(u, 'admin_level') and u.is_admin else None,
            })
        
        result.append(user_data)
    
    return result


@router.get("/admin/stats")
async def get_stats(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Estatísticas do sistema"""
    return crud.get_user_stats(db)


@router.get("/admin/captcha-stats")
async def get_captcha_stats(current_user = Depends(get_current_admin_user)):
    return captcha_manager.get_stats()


@router.post("/admin/make-admin")
async def make_admin(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Promove usuário a admin - VERSÃO SEGURA"""
    try:
        body = await request.json()
        email = body.get("email")
        admin_level = body.get("admin_level", "admin")
        reason = body.get("reason", "")
        
        if not email:
            raise HTTPException(400, "Email é obrigatório")
        
        current_level = getattr(current_user, 'admin_level', None)
        
        if not current_level:
            logger.warning(f"Admin sem nível definido: {current_user.email}")
            if admin_level not in ["admin", "moderator"]:
                raise HTTPException(403, "Admin sem nível definido só pode criar admins normais")
        else:
            if current_level == "moderator":
                raise HTTPException(403, "Moderadores não podem promover usuários")
            
            if admin_level == "admin" and current_level != "super_admin":
                raise HTTPException(403, "Apenas super administradores podem criar administradores")
        
        target_user = crud.get_user_by_email(db, email)
        if not target_user:
            raise HTTPException(404, "Usuário não encontrado")
        
        if target_user.is_admin:
            raise HTTPException(400, f"Usuário {email} já é administrador")
        
        if target_user.id == current_user.id:
            raise HTTPException(400, "Não é possível promover a si mesmo")
        
        admin_log = {
            "action": "make_admin",
            "admin_id": current_user.id,
            "admin_email": current_user.email,
            "admin_level": current_level,
            "target_email": email,
            "target_level": admin_level,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "ip": request.client.host if request.client else "unknown"
        }
        
        target_user.is_admin = True
        target_user.admin_level = admin_level
        target_user.admin_created_at = datetime.utcnow()
        target_user.admin_notes = reason
        
        if not hasattr(current_user, 'admin_actions_log') or not current_user.admin_actions_log:
            current_user.admin_actions_log = []
        current_user.admin_actions_log.append(admin_log)
        
        db.commit()
        
        logger.warning(f"🔐 NOVO ADMIN: {email} promovido a {admin_level} por {current_user.email}")
        
        return {
            "message": f"✅ {email} agora é {admin_level}",
            "admin_level": admin_level,
            "created_by": current_user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao promover admin: {e}")
        raise HTTPException(500, f"Erro interno: {str(e)}")


@router.post("/admin/remove-admin")
async def remove_admin(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Remove permissões de admin - VERSÃO SEGURA"""
    try:
        body = await request.json()
        email = body.get("email")
        reason = body.get("reason", "")
        
        if not email:
            raise HTTPException(400, "Email é obrigatório")
        
        target_user = crud.get_user_by_email(db, email)
        if not target_user:
            raise HTTPException(404, "Usuário não encontrado")
        
        if not target_user.is_admin:
            raise HTTPException(400, f"Usuário {email} não é administrador")
        
        target_level = getattr(target_user, 'admin_level', 'admin')
        current_level = getattr(current_user, 'admin_level', None)
        
        if target_level == "super_admin":
            raise HTTPException(403, "Não é possível remover super administrador")
        
        if current_level:
            level_priority = {"moderator": 1, "admin": 2, "super_admin": 3}
            if level_priority.get(target_level, 0) >= level_priority.get(current_level, 0):
                raise HTTPException(403, "Não é possível remover administrador de nível igual ou superior")
        
        if target_user.id == current_user.id:
            raise HTTPException(400, "Não é possível remover a si mesmo")
        
        admin_log = {
            "action": "remove_admin",
            "admin_id": current_user.id,
            "admin_email": current_user.email,
            "target_email": email,
            "target_previous_level": target_level,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "ip": request.client.host if request.client else "unknown"
        }
        
        target_user.is_admin = False
        target_user.admin_level = None
        target_user.admin_notes = f"Removido por {current_user.email} - {reason}"
        
        if not hasattr(current_user, 'admin_actions_log') or not current_user.admin_actions_log:
            current_user.admin_actions_log = []
        current_user.admin_actions_log.append(admin_log)
        
        db.commit()
        
        logger.warning(f"🔐 ADMIN REMOVIDO: {email} perdeu permissões por {current_user.email}")
        
        return {
            "message": f"✅ Permissões de admin removidas de {email}",
            "removed_by": current_user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao remover admin: {e}")
        raise HTTPException(500, f"Erro interno: {str(e)}")


@router.get("/admin/audit-log")
async def get_admin_audit_log(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = 100
):
    """Retorna log de ações administrativas (apenas super_admin)"""
    if getattr(current_user, 'admin_level', None) != "super_admin":
        raise HTTPException(403, "Apenas super administradores podem ver logs de auditoria")
    
    from backend.models import User
    admins = db.query(User).filter(User.is_admin == True).all()
    
    all_logs = []
    for admin in admins:
        if hasattr(admin, 'admin_actions_log') and admin.admin_actions_log:
            all_logs.extend(admin.admin_actions_log)
    
    all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    return {
        "logs": all_logs[:limit],
        "total": len(all_logs)
    }


# ==============================================
# HEALTH CHECK
# ==============================================

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "captcha": "active",
            "jwt": "active"
        }
    }


print("✅ auth_routes.py carregado com TODAS as rotas (CAPTCHA + LOGIN + REGISTER + ADMIN)")