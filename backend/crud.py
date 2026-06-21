# backend/crud.py - VERSÃO COMPLETAMENTE SINCRONIZADA COM TODOS OS ARQUIVOS
"""
CRUD - Operações de banco de dados
SINCRONIZADO COM:
- models.py (UTC-3, hashed_password, UserPlan, PaymentStatus)
- schemas.py (UTC-3, default_factory)
- payment_service.py (sistema de créditos, preços dinâmicos)
- credits_consumer.py (consumo de créditos, verificação premium)
- daily_credits_service.py (créditos diários, limite de 3)
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, not_, desc, asc
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, Union
import logging

from backend import models, schemas
from backend.security import hasher, jwt_manager

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================
# 🔥 FUSO HORÁRIO DE BRASÍLIA (UTC-3)
# SINCRONIZADO COM models.py, schemas.py, daily_credits_service.py
# ==============================================

TZ_BRASIL = timezone(timedelta(hours=-3))

def _now_brasil() -> datetime:
    """Retorna datetime atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL)

def _today_brasil() -> date:
    """Retorna data atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL).date()

def _get_next_day_brasil(days_ahead: int = 1) -> date:
    """Retorna data futura no fuso horário de Brasília"""
    return _today_brasil() + timedelta(days=days_ahead)


# ==============================================
# CONSTANTES SINCRONIZADAS
# ==============================================

MAX_CREDITS_PREMIUM = 3  # 🔥 SINCRONIZADO com daily_credits_service.py
INITIAL_FREE_CREDITS = 3  # 🔥 SINCRONIZADO com create_user


# ==============================================
# FUNÇÕES AUXILIARES
# ==============================================

def safe_commit(db: Session, error_msg: str = "Erro ao salvar no banco") -> bool:
    """Commit seguro com tratamento de erro e rollback automático"""
    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"{error_msg}: {e}")
        raise

def _is_premium_user(user: models.User) -> bool:
    """
    🔥 FUNÇÃO AUXILIAR SINCRONIZADA COM credits_consumer.py
    Verifica se usuário tem plano premium ativo
    Lida corretamente com Enum do SQLAlchemy
    """
    if not user:
        return False
    
    # Usar método is_premium() do modelo se disponível
    if hasattr(user, 'is_premium') and callable(user.is_premium):
        return user.is_premium()
    
    # Fallback: verificar plan manualmente
    plan = user.plan
    
    if hasattr(plan, 'value'):
        return plan.value == "premium_mensal"
    elif hasattr(plan, 'name'):
        return plan.name == "PREMIUM_MENSAL"
    else:
        return plan == "premium_mensal"

def _get_plan_value(user: models.User) -> str:
    """
    🔥 FUNÇÃO AUXILIAR SINCRONIZADA COM credits_consumer.py
    Retorna o valor do plano como string
    Normaliza Enum para string de forma segura
    """
    if not user:
        return "basico"
    
    plan = user.plan
    
    if hasattr(plan, 'value'):
        return plan.value
    elif hasattr(plan, 'name'):
        return plan.name.lower()
    else:
        return str(plan).lower()


# ==============================================
# USUÁRIOS - OPERAÇÕES BÁSICAS
# ==============================================

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """Busca usuário por email"""
    if not email:
        return None
    return db.query(models.User).filter(models.User.email == email.lower().strip()).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    """Busca usuário por ID"""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    """Busca usuário por telefone"""
    if not phone:
        return None
    return db.query(models.User).filter(models.User.phone == phone.strip()).first()


def user_exists(db: Session, email: str, phone: Optional[str] = None) -> bool:
    """
    Verifica se usuário já existe por email ou telefone
    🔥 SINCRONIZADO: uso correto do or_()
    """
    email = email.lower().strip() if email else ""
    
    if phone:
        phone = phone.strip()
        return db.query(models.User).filter(
            or_(
                models.User.email == email,
                models.User.phone == phone
            )
        ).first() is not None
    
    return db.query(models.User).filter(models.User.email == email).first() is not None


# ==============================================
# 🔥 CREATE_USER - COMPLETAMENTE SINCRONIZADO
# ==============================================

def create_user(db: Session, user_data: Any) -> models.User:
    """
    Cria um novo usuário no banco de dados
    🔥 SINCRONIZADO COM:
    - models.py: hashed_password, UTC-3, 3 créditos iniciais
    - schemas.py: UserCreate
    - credits_consumer.py: 3 créditos grátis
    """
    
    # Captura o telefone com segurança
    phone_value = getattr(user_data, "phone", None)
    if phone_value:
        phone_value = phone_value.strip()
    
    # Captura workshop_name com segurança
    workshop_name = getattr(user_data, "workshop_name", None)
    if workshop_name:
        workshop_name = workshop_name.strip()
    
    # 🔥 CRIA USUÁRIO COM 3 CRÉDITOS GRÁTIS (sincronizado)
    db_user = models.User(
        name=user_data.name.strip(),
        email=user_data.email.lower().strip(),
        hashed_password=hasher.hash_password(user_data.password),  # ✅ hashed_password (models.py)
        workshop_name=workshop_name,
        phone=phone_value,
        role=models.UserRole.USER,
        plan=models.UserPlan.BASICO,
        credits=INITIAL_FREE_CREDITS,  # 🔥 3 créditos grátis
        is_active=True,
        is_admin=False,
        is_verified=False,
        created_at=_now_brasil()  # 🔥 UTC-3
    )
    
    db.add(db_user)
    safe_commit(db, "Erro ao criar usuário")
    db.refresh(db_user)
    
    logger.info(f"✅ Usuário criado: {db_user.email} (ID: {db_user.id}) - {INITIAL_FREE_CREDITS} créditos grátis")
    return db_user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """
    Autentica usuário usando Argon2
    🔥 SINCRONIZADO: atualiza last_login com UTC-3
    """
    user = get_user_by_email(db, email.lower().strip())
    
    if not user:
        logger.warning(f"Tentativa de login com email não cadastrado: {email}")
        return None
    
    if not user.is_active:
        logger.warning(f"Tentativa de login em conta inativa: {email}")
        return None
    
    if not user.verify_password(password):
        logger.warning(f"Senha incorreta para: {email}")
        return None
    
    # 🔥 Atualizar último login com UTC-3
    user.last_login = _now_brasil()
    safe_commit(db, "Erro ao atualizar último login")
    
    if user.is_admin:
        logger.info(f"👑 Admin logado: {email}")
    else:
        logger.info(f"✅ Login bem-sucedido: {email}")
    
    return user


def update_user(db: Session, user_id: int, user_update: Union[Dict, schemas.UserUpdate]) -> Optional[models.User]:
    """Atualiza usuário com validações"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None
    
    # Converter para dict se for Pydantic model
    if hasattr(user_update, 'dict'):
        update_data = user_update.dict(exclude_unset=True)
    elif hasattr(user_update, 'model_dump'):
        update_data = user_update.model_dump(exclude_unset=True)
    else:
        update_data = user_update.copy() if isinstance(user_update, dict) else {}
    
    # Validar email
    if 'email' in update_data:
        update_data['email'] = update_data['email'].lower().strip()
        existing = get_user_by_email(db, update_data['email'])
        if existing and existing.id != user_id:
            raise ValueError("Email já está em uso")
    
    # Validar telefone
    if 'phone' in update_data and update_data['phone']:
        update_data['phone'] = update_data['phone'].strip()
        existing = get_user_by_phone(db, update_data['phone'])
        if existing and existing.id != user_id:
            raise ValueError("Telefone já está em uso")
    
    # Limpar campos
    if 'name' in update_data and update_data['name']:
        update_data['name'] = update_data['name'].strip()
    
    if 'workshop_name' in update_data and update_data['workshop_name']:
        update_data['workshop_name'] = update_data['workshop_name'].strip()
    
    # 🔥 CORRIGIDO: usar hashed_password (sincronizado com models.py)
    if 'password' in update_data:
        update_data['hashed_password'] = hasher.hash_password(update_data.pop('password'))
    
    # Aplicar atualizações
    for key, value in update_data.items():
        if hasattr(db_user, key) and value is not None:
            setattr(db_user, key, value)
    
    safe_commit(db, "Erro ao atualizar usuário")
    db.refresh(db_user)
    
    logger.info(f"✅ Usuário atualizado: {db_user.email}")
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    """Remove usuário (soft delete)"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return False
    
    db_user.is_active = False
    db_user.email = f"deleted_{db_user.id}_{db_user.email}"
    db_user.phone = None
    db_user.refresh_token = None
    db_user.refresh_token_jti = None
    db_user.refresh_token_revoked = True
    
    safe_commit(db, "Erro ao desativar usuário")
    logger.info(f"✅ Usuário desativado: ID {user_id}")
    return True


# ==============================================
# ADMIN - FUNÇÕES ESPECÍFICAS
# ==============================================

def set_user_admin(db: Session, user_id: int, admin_status: bool = True) -> bool:
    """Torna um usuário admin ou remove privilégios de admin"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    user.is_admin = admin_status
    safe_commit(db, "Erro ao alterar status de admin")
    
    status = "agora é admin" if admin_status else "não é mais admin"
    logger.info(f"👑 Usuário {user.email} {status}")
    return True


def get_all_admins(db: Session) -> List[models.User]:
    """Retorna todos os usuários admin"""
    return db.query(models.User).filter(models.User.is_admin == True).all()


# ==============================================
# CRÉDITOS - OPERAÇÕES (SINCRONIZADO COM credits_consumer.py E daily_credits_service.py)
# ==============================================

def get_user_credits(db: Session, user_id: int) -> int:
    """Retorna saldo de créditos do usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return 0
    
    if user.is_admin:
        return 999999
    
    return user.credits or 0


def get_credits_display(user: models.User) -> str:
    """
    Retorna string formatada para exibição de créditos
    🔥 SINCRONIZADO COM credits_consumer.py get_credits_display()
    
    Admin: "∞" (infinito)
    Premium: "X/3" (mostra limite)
    Usuário: número normal
    """
    if user.is_admin:
        return "∞"
    
    is_premium = _is_premium_user(user)
    
    if is_premium:
        return f"{user.credits or 0}/{MAX_CREDITS_PREMIUM}"
    
    return str(user.credits or 0)


def check_credits(user: models.User, required: int = 1) -> bool:
    """
    Verifica se usuário tem créditos suficientes
    🔥 SINCRONIZADO COM credits_consumer.py can_perform_analysis()
    """
    if user.is_admin:
        return True
    return (user.credits or 0) >= required


def add_credits(db: Session, user_id: int, amount: int, description: str = "") -> bool:
    """
    Adiciona créditos ao usuário com verificação de limite
    🔥 SINCRONIZADO COM:
    - credits_consumer.py add_credits_safe()
    - daily_credits_service.py (limite de 3 créditos para premium)
    """
    user = get_user_by_id(db, user_id)
    if not user or amount <= 0:
        logger.warning(f"⚠️ Tentativa inválida de adicionar {amount} créditos para user {user_id}")
        return False
    
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - créditos ilimitados (operação ignorada)")
        return True
    
    # 🔥 Verificar limite para premium (sincronizado com daily_credits_service)
    is_premium = _is_premium_user(user)
    max_credits = MAX_CREDITS_PREMIUM if is_premium else float('inf')
    
    if user.credits + amount > max_credits:
        logger.warning(f"⚠️ {user.email} excederia limite de {max_credits} créditos")
        return False
    
    old_credits = user.credits
    user.credits += amount
    
    safe_commit(db, f"Erro ao adicionar {amount} créditos para {user.email}")
    
    logger.info(f"💰 {user.email} recebeu +{amount} créditos ({description}). Antes: {old_credits}, Agora: {user.credits}")
    return True


def deduct_credits(db: Session, user: models.User, amount: int = 1, description: str = "") -> bool:
    """
    Deduz créditos do usuário
    🔥 SINCRONIZADO COM credits_consumer.py consume_analysis_credit()
    """
    if not user or amount <= 0:
        logger.warning(f"⚠️ Tentativa inválida de deduzir {amount} créditos")
        return False
    
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - operação sem consumo")
        return True
    
    if not user.has_credits(amount):
        logger.warning(f"⚠️ Créditos insuficientes para {user.email}. Tem: {user.credits}, Precisa: {amount}")
        return False
    
    old_credits = user.credits
    user.credits -= amount
    
    safe_commit(db, f"Erro ao deduzir {amount} créditos de {user.email}")
    
    # 🔥 Log específico para premium (sincronizado com credits_consumer.py)
    is_premium = _is_premium_user(user)
    if is_premium and user.credits < MAX_CREDITS_PREMIUM:
        logger.info(f"⭐ Premium {user.email} agora tem {user.credits}/{MAX_CREDITS_PREMIUM} créditos - pode receber mais")
    
    logger.info(f"💰 {user.email} consumiu {amount} crédito(s). Antes: {old_credits}, Agora: {user.credits}")
    return True


def check_credits_db(db: Session, user_id: int, required: int = 1) -> bool:
    """
    Verifica créditos (versão com db)
    🔥 SINCRONIZADO COM credits_consumer.py can_perform_analysis()
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    if user.is_admin:
        return True
    
    # Verificar se tem créditos suficientes
    has_credits = (user.credits or 0) >= required
    
    if not has_credits:
        is_premium = _is_premium_user(user)
        if is_premium and (user.credits or 0) >= MAX_CREDITS_PREMIUM:
            logger.warning(f"⚠️ Premium {user.email} atingiu limite de {MAX_CREDITS_PREMIUM} créditos")
    
    return has_credits


def transfer_credits(db: Session, from_user_id: int, to_user_id: int, amount: int) -> bool:
    """Transfere créditos entre usuários"""
    if amount <= 0:
        return False
    
    from_user = get_user_by_id(db, from_user_id)
    to_user = get_user_by_id(db, to_user_id)
    
    if not from_user or not to_user:
        return False
    
    if from_user.is_admin:
        return add_credits(db, to_user_id, amount, f"Transferência do admin {from_user.email}")
    
    if not from_user.has_credits(amount):
        return False
    
    # Deduzir do remetente
    from_user.credits -= amount
    
    # Adicionar ao destinatário (com verificação de limite)
    success = add_credits(db, to_user_id, amount, f"Transferência de {from_user.email}")
    
    if success:
        logger.info(f"💰 {amount} créditos transferidos de {from_user.email} para {to_user.email}")
    else:
        # Reverter dedução se falhou
        from_user.credits += amount
        safe_commit(db, "Erro ao reverter transferência")
    
    return success


# ==============================================
# CRÉDITOS DIÁRIOS - SUPORTE (SINCRONIZADO COM daily_credits_service.py)
# ==============================================

def get_daily_credit_logs(db: Session, user_id: int, days: int = 30, limit: int = None) -> List[models.DailyCreditLog]:
    """
    Retorna logs de créditos diários do usuário
    🔥 SINCRONIZADO COM daily_credits_service.py
    """
    query = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id
    ).order_by(desc(models.DailyCreditLog.date))
    
    if days:
        cutoff_date = _today_brasil() - timedelta(days=days)
        query = query.filter(models.DailyCreditLog.date >= cutoff_date)
    
    if limit:
        query = query.limit(limit)
    
    return query.all()


def has_received_daily_credit_today(db: Session, user_id: int) -> bool:
    """
    Verifica se o usuário já recebeu crédito diário hoje
    🔥 SINCRONIZADO COM daily_credits_service.py
    """
    today = _today_brasil()
    
    log = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        func.date(models.DailyCreditLog.date) == today
    ).first()
    
    return log is not None


def get_premium_credit_streak(db: Session, user_id: int) -> int:
    """
    Calcula o streak (dias seguidos) de créditos premium
    🔥 SINCRONIZADO COM daily_credits_service.py
    """
    logs = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        models.DailyCreditLog.source == "premium_daily"
    ).order_by(desc(models.DailyCreditLog.date)).all()
    
    if not logs:
        return 0
    
    # Verificar se o último log é de hoje
    today = _today_brasil()
    if logs[0].date != today:
        return 0
    
    # Calcular streak
    streak = 1
    for i in range(1, len(logs)):
        expected_date = today - timedelta(days=i)
        if logs[i].date == expected_date:
            streak += 1
        else:
            break
    
    return streak


def can_receive_daily_credit(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Verifica se o usuário premium pode receber crédito diário
    🔥 SINCRONIZADO COM daily_credits_service.py check_premium_daily_credit()
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return {"success": False, "error": "Usuário não encontrado"}
    
    # 👑 ADMIN
    if user.is_admin:
        return {
            "success": True,
            "can_receive": False,
            "message": "Admin tem créditos ilimitados",
            "is_premium": False,
            "is_admin": True
        }
    
    is_premium = _is_premium_user(user)
    
    if not is_premium:
        return {
            "success": True,
            "can_receive": False,
            "message": "Assine o plano premium para ganhar créditos diários",
            "is_premium": False
        }
    
    today = _today_brasil()
    current_credits = user.credits or 0
    
    # Verificar limite de créditos
    if current_credits >= MAX_CREDITS_PREMIUM:
        return {
            "success": True,
            "can_receive": False,
            "reason": "max_credits_reached",
            "message": f"⚠️ Você atingiu o limite máximo de {MAX_CREDITS_PREMIUM} créditos. Gaste alguns para receber mais!",
            "is_premium": True,
            "received_today": False,
            "credits_balance": current_credits,
            "max_credits": MAX_CREDITS_PREMIUM
        }
    
    # Verificar se já recebeu hoje
    received_today = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        func.date(models.DailyCreditLog.date) == today,
        models.DailyCreditLog.source == "premium_daily"
    ).first() is not None
    
    days_left = user.get_premium_days_left() if hasattr(user, 'get_premium_days_left') else 0
    
    next_credit_date = today if not received_today and days_left > 0 else _get_next_day_brasil(1)
    
    return {
        "success": True,
        "can_receive": not received_today and days_left > 0 and current_credits < MAX_CREDITS_PREMIUM,
        "received_today": received_today,
        "is_premium": True,
        "days_left": days_left,
        "credits_balance": current_credits,
        "max_credits": MAX_CREDITS_PREMIUM,
        "credits_until_limit": max(0, MAX_CREDITS_PREMIUM - current_credits),
        "next_credit_date": next_credit_date.isoformat() if next_credit_date else None,
        "timezone": "America/Sao_Paulo (UTC-3)",
        "today_date": today.isoformat()
    }


# ==============================================
# REFRESH TOKEN - OPERAÇÕES
# ==============================================

def save_refresh_token(db: Session, user_id: int, refresh_token: str, jti: str, expires_days: int = 7) -> bool:
    """Salva refresh token no banco"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    user.set_refresh_token(refresh_token, jti, expires_days)
    safe_commit(db, "Erro ao salvar refresh token")
    return True


def validate_refresh_token(db: Session, user_id: int, refresh_token: str) -> bool:
    """Valida refresh token de um usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    return user.validate_refresh_token(refresh_token)


def get_user_by_refresh_token(db: Session, refresh_token: str) -> Optional[models.User]:
    """Busca usuário pelo refresh token (válido)"""
    return db.query(models.User).filter(
        models.User.refresh_token == refresh_token,
        models.User.refresh_token_expires > _now_brasil(),
        models.User.refresh_token_revoked == False
    ).first()


def revoke_refresh_token(db: Session, user_id: int) -> bool:
    """Revoga refresh token de um usuário"""
    user = get_user_by_id(db, user_id)
    if user:
        user.revoke_refresh_token()
        safe_commit(db, "Erro ao revogar refresh token")
        return True
    return False


def revoke_all_user_refresh_tokens(db: Session, user_id: int) -> int:
    """Revoga todos os refresh tokens de um usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return 0
    
    user.revoke_refresh_token()
    safe_commit(db, "Erro ao revogar refresh tokens")
    return 1


def cleanup_expired_refresh_tokens(db: Session) -> int:
    """Remove tokens expirados (job agendado)"""
    expired = db.query(models.User).filter(
        models.User.refresh_token_expires < _now_brasil()
    ).all()
    
    count = 0
    for user in expired:
        user.refresh_token = None
        user.refresh_token_jti = None
        user.refresh_token_revoked = True
        count += 1
    
    if count > 0:
        safe_commit(db, "Erro ao limpar tokens expirados")
        logger.info(f"🧹 {count} refresh tokens expirados limpos")
    
    return count


# ==============================================
# PLANO PREMIUM - OPERAÇÕES (SINCRONIZADO COM TODOS OS ARQUIVOS)
# ==============================================

def activate_premium_plan(db: Session, user_id: int, payment_id: int = None) -> bool:
    """
    Ativa plano premium para usuário
    🔥 SINCRONIZADO COM models.py e payment_service.py
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    user.plan = models.UserPlan.PREMIUM_MENSAL
    user.premium_activated_at = _now_brasil()
    user.premium_expires_at = _today_brasil() + timedelta(days=30)
    
    safe_commit(db, "Erro ao ativar plano premium")
    logger.info(f"⭐ Plano premium ativado para usuário {user_id} (expira em 30 dias)")
    return True


def check_premium_status(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Verifica status do plano premium
    🔥 SINCRONIZADO COM daily_credits_service.py e credits_consumer.py
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return {"is_premium": False, "error": "Usuário não encontrado"}
    
    is_premium = user.is_premium() if hasattr(user, 'is_premium') else False
    
    return {
        "is_premium": is_premium,
        "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
        "activated_at": user.premium_activated_at,
        "expires_at": user.premium_expires_at,
        "days_left": user.get_premium_days_left() if hasattr(user, 'get_premium_days_left') else 0,
        "progress": user.get_premium_progress() if hasattr(user, 'get_premium_progress') else 0,
        "credits_balance": user.credits or 0,
        "max_credits_balance": MAX_CREDITS_PREMIUM,
        "timezone": "America/Sao_Paulo (UTC-3)"
    }


def get_premium_users(db: Session) -> List[models.User]:
    """Retorna todos os usuários com plano premium ativo"""
    return db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at >= _today_brasil()
    ).all()


def get_expired_premium_users(db: Session) -> List[models.User]:
    """Retorna usuários com plano premium expirado"""
    return db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at < _today_brasil()
    ).all()


def downgrade_expired_premium(db: Session) -> int:
    """Rebaixa usuários com premium expirado para plano básico"""
    expired_users = get_expired_premium_users(db)
    count = 0
    
    for user in expired_users:
        user.plan = models.UserPlan.BASICO
        user.premium_activated_at = None
        user.premium_expires_at = None
        count += 1
    
    if count > 0:
        safe_commit(db, "Erro ao rebaixar planos expirados")
        logger.info(f"⭐ {count} usuários tiveram plano premium expirado e foram rebaixados")
    
    return count


# ==============================================
# PAGAMENTOS - OPERAÇÕES (SINCRONIZADO COM payment_service.py)
# ==============================================

def create_payment(
    db: Session,
    user_id: int,
    mp_id: str,
    amount: float,
    credits: int,
    payment_method: str,
    qr_code: str = None,
    qr_code_base64: str = None,
    qr_code_url: str = None,
    checkout_url: str = None,
    preference_id: str = None,
    description: str = None,
    payment_metadata: dict = None
) -> models.Payment:
    """Cria registro de pagamento"""
    
    payment = models.Payment(
        user_id=user_id,
        mp_id=mp_id,
        amount=amount,
        credits=credits,
        status=models.PaymentStatus.PENDING,
        payment_method=payment_method,
        qr_code=qr_code,
        qr_code_base64=qr_code_base64,
        qr_code_url=qr_code_url,
        checkout_url=checkout_url,
        preference_id=preference_id,
        description=description,
        payment_metadata=payment_metadata or {},
        created_at=_now_brasil()
    )
    
    db.add(payment)
    safe_commit(db, "Erro ao criar pagamento")
    db.refresh(payment)
    
    logger.info(f"💰 Pagamento criado: {mp_id} (R$ {amount})")
    return payment


def get_payment_by_mp_id(db: Session, mp_id: str) -> Optional[models.Payment]:
    """Busca pagamento pelo ID do Mercado Pago"""
    return db.query(models.Payment).filter(models.Payment.mp_id == mp_id).first()


def get_payment_by_preference_id(db: Session, preference_id: str) -> Optional[models.Payment]:
    """Busca pagamento pelo ID da preferência"""
    return db.query(models.Payment).filter(models.Payment.preference_id == preference_id).first()


def update_payment_status(
    db: Session, 
    payment_id: int, 
    status: models.PaymentStatus, 
    mp_data: dict = None
) -> Optional[models.Payment]:
    """Atualiza status do pagamento"""
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        return None
    
    payment.status = status
    if status == models.PaymentStatus.APPROVED:
        payment.approved_at = _now_brasil()
    
    if mp_data:
        payment.payment_metadata = {**payment.payment_metadata, **mp_data}
    
    payment.updated_at = _now_brasil()
    
    safe_commit(db, "Erro ao atualizar pagamento")
    db.refresh(payment)
    
    logger.info(f"💰 Pagamento {payment.mp_id} atualizado para {status}")
    return payment


def get_user_payments(db: Session, user_id: int, limit: int = 10) -> List[models.Payment]:
    """Retorna histórico de pagamentos do usuário"""
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id
    ).order_by(desc(models.Payment.created_at)).limit(limit).all()


def get_pending_payments(db: Session, minutes: int = 30) -> List[models.Payment]:
    """Retorna pagamentos pendentes há mais de X minutos"""
    threshold = _now_brasil() - timedelta(minutes=minutes)
    return db.query(models.Payment).filter(
        models.Payment.status == models.PaymentStatus.PENDING,
        models.Payment.created_at < threshold
    ).all()


def get_approved_payments_by_user(db: Session, user_id: int) -> List[models.Payment]:
    """Retorna pagamentos aprovados do usuário"""
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id,
        models.Payment.status == models.PaymentStatus.APPROVED
    ).order_by(desc(models.Payment.approved_at)).all()


# ==============================================
# ANÁLISES - OPERAÇÕES
# ==============================================

def create_analysis(db: Session, analysis: schemas.AnalysisCreate, user_id: int) -> models.Analysis:
    """Cria registro de análise"""
    db_analysis = models.Analysis(
        **analysis.dict(),
        user_id=user_id,
        uploaded_at=_now_brasil(),
        status="pending"
    )
    db.add(db_analysis)
    safe_commit(db, "Erro ao criar análise")
    db.refresh(db_analysis)
    return db_analysis


def get_analysis(db: Session, analysis_id: int) -> Optional[models.Analysis]:
    """Busca análise por ID"""
    return db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()


def get_user_analyses(
    db: Session, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 100,
    status: Optional[str] = None
) -> List[models.Analysis]:
    """Retorna análises do usuário com filtros"""
    query = db.query(models.Analysis).filter(models.Analysis.user_id == user_id)
    
    if status:
        query = query.filter(models.Analysis.status == status)
    
    return query.order_by(desc(models.Analysis.uploaded_at)).offset(skip).limit(limit).all()


def update_analysis(db: Session, analysis_id: int, updates: dict) -> Optional[models.Analysis]:
    """Atualiza análise"""
    db_analysis = get_analysis(db, analysis_id)
    if not db_analysis:
        return None
    
    for key, value in updates.items():
        if hasattr(db_analysis, key) and value is not None:
            setattr(db_analysis, key, value)
    
    safe_commit(db, "Erro ao atualizar análise")
    db.refresh(db_analysis)
    return db_analysis


def delete_analysis(db: Session, analysis_id: int) -> bool:
    """Remove análise"""
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db.delete(db_analysis)
        safe_commit(db, "Erro ao deletar análise")
        return True
    return False


def get_recent_analyses(db: Session, limit: int = 10) -> List[models.Analysis]:
    """Retorna análises recentes (para admin)"""
    return db.query(models.Analysis).order_by(
        desc(models.Analysis.uploaded_at)
    ).limit(limit).all()


def count_user_analyses(db: Session, user_id: int) -> int:
    """Conta quantas análises o usuário já fez"""
    return db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id
    ).count()


# ==============================================
# ADMIN - OPERAÇÕES AVANÇADAS
# ==============================================

def get_all_users(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    role: Optional[models.UserRole] = None,
    search: Optional[str] = None
) -> List[models.User]:
    """Lista usuários com filtros"""
    query = db.query(models.User)
    
    if active_only:
        query = query.filter(models.User.is_active == True)
    
    if role:
        query = query.filter(models.User.role == role)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.User.email.ilike(search_term),
                models.User.name.ilike(search_term),
                models.User.workshop_name.ilike(search_term)
            )
        )
    
    return query.offset(skip).limit(limit).all()


def get_users_by_role(db: Session, role: models.UserRole) -> List[models.User]:
    """Retorna usuários por role"""
    return db.query(models.User).filter(models.User.role == role).all()


def get_user_stats(db: Session) -> Dict[str, Any]:
    """Estatísticas detalhadas do sistema"""
    total = db.query(models.User).count()
    active = db.query(models.User).filter(models.User.is_active == True).count()
    
    admins = db.query(models.User).filter(models.User.is_admin == True).count()
    
    role_admins = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).count()
    managers = db.query(models.User).filter(models.User.role == models.UserRole.MANAGER).count()
    users = db.query(models.User).filter(models.User.role == models.UserRole.USER).count()
    
    premium = db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at >= _today_brasil()
    ).count()
    
    total_credits = db.query(func.sum(models.User.credits)).filter(
        models.User.is_admin == False
    ).scalar() or 0
    avg_credits = db.query(func.avg(models.User.credits)).filter(
        models.User.is_admin == False
    ).scalar() or 0
    
    total_analyses = db.query(models.Analysis).count()
    analyses_today = db.query(models.Analysis).filter(
        func.date(models.Analysis.uploaded_at) == _today_brasil()
    ).count()
    
    total_payments = db.query(models.Payment).count()
    approved_payments = db.query(models.Payment).filter(
        models.Payment.status == models.PaymentStatus.APPROVED
    ).count()
    total_revenue = db.query(func.sum(models.Payment.amount)).filter(
        models.Payment.status == models.PaymentStatus.APPROVED
    ).scalar() or 0
    
    return {
        "users": {
            "total": total,
            "active": active,
            "inactive": total - active,
            "admins": admins,
            "role_admins": role_admins,
            "managers": managers,
            "users": users,
            "premium": premium
        },
        "credits": {
            "total_in_system": total_credits,
            "average_per_user": round(avg_credits, 2),
            "admins_have_unlimited": admins,
            "max_credits_premium": MAX_CREDITS_PREMIUM
        },
        "analyses": {
            "total": total_analyses,
            "today": analyses_today
        },
        "payments": {
            "total": total_payments,
            "approved": approved_payments,
            "total_revenue": total_revenue
        },
        "timezone": "America/Sao_Paulo (UTC-3)"
    }


def get_dashboard_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Estatísticas para dashboard do usuário"""
    user = get_user_by_id(db, user_id)
    
    analyses = get_user_analyses(db, user_id, limit=5)
    
    credits_info = {
        "balance": user.credits if user and not user.is_admin else 999999,
        "balance_display": get_credits_display(user) if user else "0",
        "total_purchased": user.total_purchased if user else 0,
        "is_admin": user.is_admin if user else False,
        "max_credits_premium": MAX_CREDITS_PREMIUM
    }
    
    premium_info = check_premium_status(db, user_id) if user else {"is_premium": False}
    
    payments = get_user_payments(db, user_id, limit=3)
    
    return {
        "user": {
            "name": user.name if user else "",
            "email": user.email if user else "",
            "workshop": user.workshop_name if user else "",
            "is_admin": user.is_admin if user else False
        },
        "credits": credits_info,
        "premium": premium_info,
        "recent_analyses": [{
            "id": a.id,
            "filename": a.filename,
            "status": a.status,
            "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None
        } for a in analyses],
        "recent_payments": [{
            "id": p.id,
            "amount": p.amount,
            "credits": p.credits,
            "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
            "created_at": p.created_at.isoformat() if p.created_at else None
        } for p in payments],
        "timestamp": _now_brasil().isoformat(),
        "timezone": "America/Sao_Paulo (UTC-3)"
    }


# ==============================================
# SESSÃO E LOGOUT COMPLETO
# ==============================================

def clear_user_session(db: Session, user_id: int, logout_all_devices: bool = True) -> bool:
    """Limpa completamente a sessão do usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        logger.warning(f"⚠️ Tentativa de limpar sessão de usuário inexistente: ID {user_id}")
        return False
    
    user.revoke_refresh_token()
    
    if logout_all_devices:
        user.refresh_token = None
        user.refresh_token_jti = None
        user.refresh_token_revoked = True
        user.refresh_token_expires = None
        
        if hasattr(user, 'session_metadata'):
            user.session_metadata = None
        if hasattr(user, 'last_active_at'):
            user.last_active_at = None
    
    safe_commit(db, "Erro ao limpar sessão do usuário")
    
    device_msg = "todos os dispositivos" if logout_all_devices else "dispositivo atual"
    logger.info(f"🔓 Sessão encerrada para usuário {user.email} ({device_msg})")
    
    return True


def get_user_session_info(db: Session, user_id: int) -> Dict[str, Any]:
    """Retorna informações da sessão atual do usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return {"error": "Usuário não encontrado"}
    
    has_valid_token = False
    if user.refresh_token and user.refresh_token_expires:
        has_valid_token = user.refresh_token_expires > _now_brasil() and not user.refresh_token_revoked
    
    return {
        "user_id": user.id,
        "user_email": user.email,
        "is_admin": user.is_admin,
        "has_refresh_token": bool(user.refresh_token),
        "refresh_token_valid": has_valid_token,
        "refresh_token_expires_at": user.refresh_token_expires.isoformat() if user.refresh_token_expires else None,
        "refresh_token_revoked": user.refresh_token_revoked,
        "session_active": has_valid_token,
        "needs_cleanup": user.refresh_token_expires and user.refresh_token_expires < _now_brasil() if user.refresh_token_expires else False,
        "timezone": "America/Sao_Paulo (UTC-3)"
    }


def force_logout_user(db: Session, email: str, reason: str = "Admin action") -> bool:
    """Força logout de um usuário (para administradores)"""
    user = get_user_by_email(db, email)
    if not user:
        logger.warning(f"⚠️ Tentativa de force logout em usuário inexistente: {email}")
        return False
    
    user.revoke_refresh_token()
    user.refresh_token = None
    user.refresh_token_jti = None
    user.refresh_token_revoked = True
    user.refresh_token_expires = None
    
    safe_commit(db, f"Erro ao forçar logout do usuário {email}")
    
    logger.warning(f"⚠️ FORCE LOGOUT: Usuário {email} foi desconectado por {reason}")
    
    return True


def cleanup_orphaned_sessions(db: Session, older_than_days: int = 30) -> int:
    """Limpeza de sessões órfãs"""
    cutoff_date = _now_brasil() - timedelta(days=older_than_days)
    
    users_with_expired_tokens = db.query(models.User).filter(
        models.User.refresh_token_expires < cutoff_date,
        models.User.refresh_token.isnot(None)
    ).all()
    
    count = 0
    for user in users_with_expired_tokens:
        user.refresh_token = None
        user.refresh_token_jti = None
        user.refresh_token_revoked = True
        user.refresh_token_expires = None
        count += 1
    
    if count > 0:
        safe_commit(db, "Erro ao limpar sessões órfãs")
        logger.info(f"🧹 {count} sessões órfãs limpas (inativas há {older_than_days}+ dias)")
    
    return count


def complete_logout(db: Session, user_id: int, refresh_token: str = None) -> bool:
    """Logout completo - versão unificada"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    if refresh_token:
        if user.refresh_token == refresh_token:
            user.revoke_refresh_token()
        else:
            logger.warning(f"⚠️ Tentativa de logout com token inválido para usuário {user.email}")
            return False
    else:
        user.revoke_refresh_token()
    
    user.refresh_token = None
    user.refresh_token_jti = None
    user.refresh_token_revoked = True
    
    safe_commit(db, "Erro ao realizar logout completo")
    
    logger.info(f"🔓 Logout completo: {user.email}")
    
    return True


print("✅ crud.py carregado - COMPLETAMENTE SINCRONIZADO com:")
print("   - models.py (hashed_password, UTC-3, UserPlan, PaymentStatus)")
print("   - schemas.py (UTC-3, default_factory)")
print("   - payment_service.py (preços dinâmicos, promoções)")
print("   - credits_consumer.py (consumo de créditos, verificação premium)")
print("   - daily_credits_service.py (créditos diários, limite de 3)")
print(f"   - MAX_CREDITS_PREMIUM = {MAX_CREDITS_PREMIUM}")
print(f"   - INITIAL_FREE_CREDITS = {INITIAL_FREE_CREDITS}")