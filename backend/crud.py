# backend/crud.py - VERSÃO 2.1 COM CHART_DATA
"""
CRUD - Operações de banco de dados
VERSÃO: 2.1 - COM SUPORTE A CHART_DATA E POW
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, not_, desc, asc, text
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
# ==============================================

TZ_BRASIL = timezone(timedelta(hours=-3))

def _now_brasil() -> datetime:
    return datetime.now(TZ_BRASIL)

def _today_brasil() -> date:
    return datetime.now(TZ_BRASIL).date()

def _get_next_day_brasil(days_ahead: int = 1) -> date:
    return _today_brasil() + timedelta(days=days_ahead)


# ==============================================
# 🔥 FUNÇÕES BLINDADAS DE TIMEZONE
# ==============================================

def _is_datetime_expired(db_datetime: Optional[datetime]) -> bool:
    if db_datetime is None:
        return True
    naive_db = db_datetime.replace(tzinfo=None) if db_datetime.tzinfo else db_datetime
    naive_now = datetime.utcnow()
    return naive_db < naive_now

def _is_datetime_valid(db_datetime: Optional[datetime]) -> bool:
    return not _is_datetime_expired(db_datetime)


# ==============================================
# CONSTANTES
# ==============================================

MAX_CREDITS_PREMIUM = 3
INITIAL_FREE_CREDITS = 3


# ==============================================
# FUNÇÕES AUXILIARES
# ==============================================

def safe_commit(db: Session, error_msg: str = "Erro ao salvar no banco") -> bool:
    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"{error_msg}: {e}")
        raise

def _is_premium_user(user: models.User) -> bool:
    if not user:
        return False
    if hasattr(user, 'is_premium') and callable(user.is_premium):
        return user.is_premium()
    plan = user.plan
    if hasattr(plan, 'value'):
        return plan.value == "premium_mensal"
    elif hasattr(plan, 'name'):
        return plan.name == "PREMIUM_MENSAL"
    return plan == "premium_mensal"

def _get_plan_value(user: models.User) -> str:
    if not user:
        return "basico"
    plan = user.plan
    if hasattr(plan, 'value'):
        return plan.value
    elif hasattr(plan, 'name'):
        return plan.name.lower()
    return str(plan).lower()

def sanitize_string(value: str) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        value = str(value)
    dangerous = ['<', '>', '"', "'", ';', '=', '(', ')', '{', '}']
    for char in dangerous:
        value = value.replace(char, '')
    return value[:255]


# ==============================================
# USUÁRIOS - OPERAÇÕES BÁSICAS
# ==============================================

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    if not email:
        return None
    return db.query(models.User).filter(models.User.email == email.lower().strip()).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    if not phone:
        return None
    return db.query(models.User).filter(models.User.phone == phone.strip()).first()

def user_exists(db: Session, email: str, phone: Optional[str] = None) -> bool:
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


def create_user(db: Session, user_data: Any) -> models.User:
    phone_value = getattr(user_data, "phone", None)
    if phone_value:
        phone_value = phone_value.strip()
    
    workshop_name = getattr(user_data, "workshop_name", None)
    if workshop_name:
        workshop_name = workshop_name.strip()
    
    db_user = models.User(
        name=user_data.name.strip(),
        email=user_data.email.lower().strip(),
        hashed_password=hasher.hash_password(user_data.password),
        workshop_name=workshop_name,
        phone=phone_value,
        role=models.UserRole.USER,
        plan=models.UserPlan.BASICO,
        credits=INITIAL_FREE_CREDITS,
        is_active=True,
        is_admin=False,
        is_verified=False,
        created_at=_now_brasil()
    )
    
    db.add(db_user)
    safe_commit(db, "Erro ao criar usuário")
    db.refresh(db_user)
    
    logger.info(f"✅ Usuário criado: {db_user.email} (ID: {db_user.id}) - {INITIAL_FREE_CREDITS} créditos grátis")
    return db_user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
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
    
    update_last_login(db, user.id)
    
    if user.is_admin:
        logger.info(f"👑 Admin logado: {email}")
    else:
        logger.info(f"✅ Login bem-sucedido: {email}")
    
    return user


def update_user(db: Session, user_id: int, user_update: Union[Dict, schemas.UserUpdate]) -> Optional[models.User]:
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None
    
    if hasattr(user_update, 'dict'):
        update_data = user_update.dict(exclude_unset=True)
    elif hasattr(user_update, 'model_dump'):
        update_data = user_update.model_dump(exclude_unset=True)
    else:
        update_data = user_update.copy() if isinstance(user_update, dict) else {}
    
    if 'email' in update_data:
        update_data['email'] = update_data['email'].lower().strip()
        existing = get_user_by_email(db, update_data['email'])
        if existing and existing.id != user_id:
            raise ValueError("Email já está em uso")
    
    if 'phone' in update_data and update_data['phone']:
        update_data['phone'] = update_data['phone'].strip()
        existing = get_user_by_phone(db, update_data['phone'])
        if existing and existing.id != user_id:
            raise ValueError("Telefone já está em uso")
    
    if 'name' in update_data and update_data['name']:
        update_data['name'] = update_data['name'].strip()
    
    if 'workshop_name' in update_data and update_data['workshop_name']:
        update_data['workshop_name'] = update_data['workshop_name'].strip()
    
    if 'password' in update_data:
        update_data['hashed_password'] = hasher.hash_password(update_data.pop('password'))
    
    for key, value in update_data.items():
        if hasattr(db_user, key) and value is not None:
            setattr(db_user, key, value)
    
    safe_commit(db, "Erro ao atualizar usuário")
    db.refresh(db_user)
    
    logger.info(f"✅ Usuário atualizado: {db_user.email}")
    return db_user


def update_last_login(db: Session, user_id: int) -> Optional[models.User]:
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.last_login = _now_brasil()
        safe_commit(db, "Erro ao atualizar último login")
        db.refresh(db_user)
        logger.debug(f"✅ Último login atualizado para: {db_user.email}")
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
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
# ADMIN
# ==============================================

def set_user_admin(db: Session, user_id: int, admin_status: bool = True) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    user.is_admin = admin_status
    safe_commit(db, "Erro ao alterar status de admin")
    status = "agora é admin" if admin_status else "não é mais admin"
    logger.info(f"👑 Usuário {user.email} {status}")
    return True

def get_all_admins(db: Session) -> List[models.User]:
    return db.query(models.User).filter(models.User.is_admin == True).all()


# ==============================================
# CRÉDITOS
# ==============================================

def get_user_credits(db: Session, user_id: int) -> int:
    user = get_user_by_id(db, user_id)
    if not user:
        return 0
    if user.is_admin:
        return 999999
    return user.credits or 0

def get_credits_display(user: models.User) -> str:
    if user.is_admin:
        return "∞"
    is_premium = _is_premium_user(user)
    if is_premium:
        return f"{user.credits or 0}/{MAX_CREDITS_PREMIUM}"
    return str(user.credits or 0)

def check_credits(user: models.User, required: int = 1) -> bool:
    if user.is_admin:
        return True
    return (user.credits or 0) >= required

def add_credits(db: Session, user_id: int, amount: int, description: str = "") -> bool:
    user = get_user_by_id(db, user_id)
    if not user or amount <= 0:
        logger.warning(f"⚠️ Tentativa inválida de adicionar {amount} créditos")
        return False
    
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - créditos ilimitados")
        return True
    
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
    
    is_premium = _is_premium_user(user)
    if is_premium and user.credits < MAX_CREDITS_PREMIUM:
        logger.info(f"⭐ Premium {user.email} agora tem {user.credits}/{MAX_CREDITS_PREMIUM} créditos")
    
    logger.info(f"💰 {user.email} consumiu {amount} crédito(s). Antes: {old_credits}, Agora: {user.credits}")
    return True

def check_credits_db(db: Session, user_id: int, required: int = 1) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    if user.is_admin:
        return True
    return (user.credits or 0) >= required

def transfer_credits(db: Session, from_user_id: int, to_user_id: int, amount: int) -> bool:
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
    from_user.credits -= amount
    success = add_credits(db, to_user_id, amount, f"Transferência de {from_user.email}")
    if success:
        logger.info(f"💰 {amount} créditos transferidos de {from_user.email} para {to_user.email}")
    else:
        from_user.credits += amount
        safe_commit(db, "Erro ao reverter transferência")
    return success


# ==============================================
# CRÉDITOS DIÁRIOS
# ==============================================

def get_daily_credit_logs(db: Session, user_id: int, days: int = 30, limit: int = None) -> List[models.DailyCreditLog]:
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
    today = _today_brasil()
    log = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        func.date(models.DailyCreditLog.date) == today
    ).first()
    return log is not None

def get_premium_credit_streak(db: Session, user_id: int) -> int:
    logs = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        models.DailyCreditLog.source == "premium_daily"
    ).order_by(desc(models.DailyCreditLog.date)).all()
    if not logs:
        return 0
    today = _today_brasil()
    if logs[0].date != today:
        return 0
    streak = 1
    for i in range(1, len(logs)):
        expected_date = today - timedelta(days=i)
        if logs[i].date == expected_date:
            streak += 1
        else:
            break
    return streak

def can_receive_daily_credit(db: Session, user_id: int) -> Dict[str, Any]:
    user = get_user_by_id(db, user_id)
    if not user:
        return {"success": False, "error": "Usuário não encontrado"}
    if user.is_admin:
        return {"success": True, "can_receive": False, "message": "Admin tem créditos ilimitados", "is_premium": False, "is_admin": True}
    
    is_premium = _is_premium_user(user)
    if not is_premium:
        return {"success": True, "can_receive": False, "message": "Assine o plano premium para ganhar créditos diários", "is_premium": False}
    
    today = _today_brasil()
    current_credits = user.credits or 0
    
    if current_credits >= MAX_CREDITS_PREMIUM:
        return {
            "success": True,
            "can_receive": False,
            "reason": "max_credits_reached",
            "message": f"⚠️ Você atingiu o limite máximo de {MAX_CREDITS_PREMIUM} créditos.",
            "is_premium": True,
            "received_today": False,
            "credits_balance": current_credits,
            "max_credits": MAX_CREDITS_PREMIUM
        }
    
    received_today = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        func.date(models.DailyCreditLog.date) == today,
        models.DailyCreditLog.source == "premium_daily"
    ).first() is not None
    
    days_left = user.get_premium_days_left() if hasattr(user, 'get_premium_days_left') else 0
    
    return {
        "success": True,
        "can_receive": not received_today and days_left > 0 and current_credits < MAX_CREDITS_PREMIUM,
        "received_today": received_today,
        "is_premium": True,
        "days_left": days_left,
        "credits_balance": current_credits,
        "max_credits": MAX_CREDITS_PREMIUM,
        "credits_until_limit": max(0, MAX_CREDITS_PREMIUM - current_credits),
        "next_credit_date": today.isoformat() if not received_today and days_left > 0 else _get_next_day_brasil(1).isoformat(),
        "timezone": "America/Sao_Paulo (UTC-3)",
        "today_date": today.isoformat()
    }


# ==============================================
# REFRESH TOKEN
# ==============================================

def save_refresh_token(db: Session, user_id: int, refresh_token: str, jti: str, expires_days: int = 7) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    user.set_refresh_token(refresh_token, jti, expires_days)
    safe_commit(db, "Erro ao salvar refresh token")
    return True

def validate_refresh_token(db: Session, user_id: int, refresh_token: str) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    return user.validate_refresh_token(refresh_token)

def get_user_by_refresh_token(db: Session, refresh_token: str) -> Optional[models.User]:
    users = db.query(models.User).filter(
        models.User.refresh_token == refresh_token,
        models.User.refresh_token_revoked == False
    ).all()
    for user in users:
        if _is_datetime_valid(user.refresh_token_expires):
            return user
    return None

def revoke_refresh_token(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if user:
        user.revoke_refresh_token()
        safe_commit(db, "Erro ao revogar refresh token")
        return True
    return False

def revoke_all_user_refresh_tokens(db: Session, user_id: int) -> int:
    user = get_user_by_id(db, user_id)
    if not user:
        return 0
    user.revoke_refresh_token()
    safe_commit(db, "Erro ao revogar refresh tokens")
    return 1

def cleanup_expired_refresh_tokens(db: Session) -> int:
    users = db.query(models.User).filter(models.User.refresh_token.isnot(None)).all()
    count = 0
    for user in users:
        if _is_datetime_expired(user.refresh_token_expires):
            user.refresh_token = None
            user.refresh_token_jti = None
            user.refresh_token_revoked = True
            count += 1
    if count > 0:
        safe_commit(db, "Erro ao limpar tokens expirados")
        logger.info(f"🧹 {count} refresh tokens expirados limpos")
    return count


# ==============================================
# PLANO PREMIUM
# ==============================================

def activate_premium_plan(db: Session, user_id: int, payment_id: int = None) -> bool:
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
    return db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at >= _today_brasil()
    ).all()

def get_expired_premium_users(db: Session) -> List[models.User]:
    return db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at < _today_brasil()
    ).all()

def downgrade_expired_premium(db: Session) -> int:
    expired_users = get_expired_premium_users(db)
    count = 0
    for user in expired_users:
        user.plan = models.UserPlan.BASICO
        user.premium_activated_at = None
        user.premium_expires_at = None
        count += 1
    if count > 0:
        safe_commit(db, "Erro ao rebaixar planos expirados")
        logger.info(f"⭐ {count} usuários tiveram plano premium expirado")
    return count


# ==============================================
# PAGAMENTOS
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
    return db.query(models.Payment).filter(models.Payment.mp_id == mp_id).first()

def get_payment_by_preference_id(db: Session, preference_id: str) -> Optional[models.Payment]:
    return db.query(models.Payment).filter(models.Payment.preference_id == preference_id).first()

def update_payment_status(db: Session, payment_id: int, status: models.PaymentStatus, mp_data: dict = None) -> Optional[models.Payment]:
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
    return db.query(models.Payment).filter(models.Payment.user_id == user_id).order_by(desc(models.Payment.created_at)).limit(limit).all()

def get_pending_payments(db: Session, minutes: int = 30) -> List[models.Payment]:
    threshold = _now_brasil() - timedelta(minutes=minutes)
    return db.query(models.Payment).filter(
        models.Payment.status == models.PaymentStatus.PENDING,
        models.Payment.created_at < threshold
    ).all()

def get_approved_payments_by_user(db: Session, user_id: int) -> List[models.Payment]:
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id,
        models.Payment.status == models.PaymentStatus.APPROVED
    ).order_by(desc(models.Payment.approved_at)).all()


# ==============================================
# 🔥🔥🔥 ANÁLISES - VERSÃO UNIFICADA COM POW E CHART_DATA
# ==============================================

def create_analysis(
    db: Session,
    user_id: int,
    filename: str,
    analysis_type: str = "auto",
    status: str = "pending",
    # 🔥 NOVOS PARÂMETROS OPCIONAIS
    pow_data: Dict[str, Any] = None,
    client_ip: str = None,
    user_agent: str = None,
) -> models.Analysis:
    """
    🔥 Cria uma análise com suporte a PoW
    
    Args:
        db: Sessão do banco
        user_id: ID do usuário
        filename: Nome do arquivo
        analysis_type: Tipo de análise
        status: Status inicial
        pow_data: Dados do PoW (opcional)
        client_ip: IP do cliente (opcional)
        user_agent: User Agent (opcional)
    
    Returns:
        Analysis: Análise criada
    """
    analysis = models.Analysis(
        user_id=user_id,
        filename=sanitize_string(filename)[:255],
        analysis_type=analysis_type,
        status=status,
        uploaded_at=_now_brasil(),
        # 🔥 PoW data (opcional)
        pow_challenge=pow_data.get('challenge') if pow_data else None,
        pow_nonce=pow_data.get('nonce') if pow_data else None,
        pow_difficulty=pow_data.get('difficulty', 4) if pow_data else 4,
        pow_verified=pow_data.get('verified', False) if pow_data else False,
        pow_verified_at=_now_brasil() if pow_data and pow_data.get('verified') else None,
        pow_algorithm=pow_data.get('algorithm', 'SHA-256') if pow_data else 'SHA-256',
        # 🔥 Security
        client_ip=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        rate_limit_applied=False,
    )
    
    db.add(analysis)
    safe_commit(db, "Erro ao criar análise")
    db.refresh(analysis)
    
    logger.info(f"📊 Análise criada: {filename} (ID: {analysis.id}) - PoW: {analysis.pow_verified}")
    return analysis


def get_analysis(db: Session, analysis_id: int) -> Optional[models.Analysis]:
    """Busca análise por ID (já inclui todos os campos, incluindo chart_data)"""
    return db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()


def get_user_analyses(
    db: Session, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 100,
    status: Optional[str] = None
) -> List[models.Analysis]:
    """Retorna análises do usuário com filtros (inclui chart_data)"""
    query = db.query(models.Analysis).filter(models.Analysis.user_id == user_id)
    if status:
        query = query.filter(models.Analysis.status == status)
    return query.order_by(desc(models.Analysis.uploaded_at)).offset(skip).limit(limit).all()


def update_analysis(db: Session, analysis_id: int, updates: dict) -> Optional[models.Analysis]:
    """Atualiza análise (aceita qualquer campo, incluindo chart_data)"""
    db_analysis = get_analysis(db, analysis_id)
    if not db_analysis:
        return None
    
    for key, value in updates.items():
        if hasattr(db_analysis, key) and value is not None:
            setattr(db_analysis, key, value)
    
    safe_commit(db, "Erro ao atualizar análise")
    db.refresh(db_analysis)
    return db_analysis


def update_analysis_pow_verification(
    db: Session,
    analysis_id: int,
    verified: bool = True,
) -> Optional[models.Analysis]:
    """Atualiza a verificação PoW de uma análise"""
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        return None
    analysis.pow_verified = verified
    analysis.pow_verified_at = _now_brasil() if verified else None
    safe_commit(db, "Erro ao atualizar verificação PoW")
    db.refresh(analysis)
    logger.info(f"🔐 PoW da análise {analysis_id}: {verified}")
    return analysis


def update_analysis_metrics(
    db: Session,
    analysis_id: int,
    metrics: Dict[str, Any],
) -> Optional[models.Analysis]:
    """
    🔥 Atualiza métricas de uma análise
    """
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        return None
    
    # Métricas de performance
    if 'processing_time_ms' in metrics:
        analysis.processing_time_ms = metrics['processing_time_ms']
    if 'pow_solve_time_ms' in metrics:
        analysis.pow_solve_time_ms = metrics['pow_solve_time_ms']
    if 'upload_time_ms' in metrics:
        analysis.upload_time_ms = metrics['upload_time_ms']
    
    # Métricas de ML
    if 'encoding_used' in metrics:
        analysis.encoding_used = metrics['encoding_used'][:20]
    if 'model_used' in metrics:
        analysis.model_used = metrics['model_used'][:50]
    if 'confidence_score' in metrics:
        analysis.confidence_score = metrics['confidence_score']
    
    safe_commit(db, "Erro ao atualizar métricas da análise")
    db.refresh(analysis)
    logger.info(f"📊 Métricas atualizadas para análise {analysis_id}")
    return analysis


def update_analysis_data_metrics(
    db: Session,
    analysis_id: int,
    data: Dict[str, Any],
) -> Optional[models.Analysis]:
    """
    🔥 Atualiza métricas de dados de uma análise
    """
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        return None
    
    if 'total_rows' in data:
        analysis.total_rows = data['total_rows']
    if 'total_columns' in data:
        analysis.total_columns = data['total_columns']
    if 'numeric_columns' in data:
        analysis.numeric_columns = data['numeric_columns']
    if 'categorical_columns' in data:
        analysis.categorical_columns = data['categorical_columns']
    
    safe_commit(db, "Erro ao atualizar métricas de dados da análise")
    db.refresh(analysis)
    logger.info(f"📊 Métricas de dados atualizadas para análise {analysis_id}")
    return analysis


def update_analysis_results(
    db: Session,
    analysis_id: int,
    results: Dict[str, Any],
) -> Optional[models.Analysis]:
    """
    🔥 Atualiza resultados de uma análise (inclui chart_data)
    """
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        return None
    
    # 🔥 Resultados principais
    if 'predictions_summary' in results:
        analysis.predictions_summary = results['predictions_summary']
    if 'insights' in results:
        analysis.insights = results['insights']
    if 'recommendations' in results:
        analysis.recommendations = results['recommendations']
    
    # 🔥 NOVO: chart_data
    if 'chart_data' in results:
        analysis.chart_data = results['chart_data']
        logger.info(f"📊 chart_data salvo para análise {analysis_id}")
    
    if 'status' in results:
        analysis.status = results['status']
    
    if results.get('status') == 'completed':
        analysis.processed_at = _now_brasil()
        analysis.rows_processed = analysis.total_rows
    
    safe_commit(db, "Erro ao atualizar resultados da análise")
    db.refresh(analysis)
    logger.info(f"📊 Resultados atualizados para análise {analysis_id}")
    return analysis


def get_user_analyses_with_pow(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Analysis]:
    """Busca análises do usuário (já inclui todos os campos)"""
    return get_user_analyses(db, user_id, skip, limit)


def get_analyses_with_pow_stats(
    db: Session,
    user_id: int,
) -> Dict[str, Any]:
    """
    🔥 Retorna estatísticas de PoW para um usuário
    """
    analyses = db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id
    ).all()
    
    total = len(analyses)
    pow_verified = len([a for a in analyses if a.pow_verified])
    with_challenge = len([a for a in analyses if a.pow_challenge])
    
    return {
        "total_analyses": total,
        "pow_verified": pow_verified,
        "pow_verified_percentage": round((pow_verified / total * 100), 1) if total > 0 else 0,
        "with_challenge": with_challenge,
        "avg_difficulty": round(sum([a.pow_difficulty for a in analyses if a.pow_difficulty]) / total, 1) if total > 0 else 0,
        "avg_processing_time_ms": round(sum([a.processing_time_ms or 0 for a in analyses]) / total, 1) if total > 0 else 0,
        "encodings_used": list(set([a.encoding_used for a in analyses if a.encoding_used])),
        "models_used": list(set([a.model_used for a in analyses if a.model_used])),
    }


def delete_analysis(db: Session, analysis_id: int) -> bool:
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db.delete(db_analysis)
        safe_commit(db, "Erro ao deletar análise")
        return True
    return False


def get_recent_analyses(db: Session, limit: int = 10) -> List[models.Analysis]:
    return db.query(models.Analysis).order_by(desc(models.Analysis.uploaded_at)).limit(limit).all()


# ==============================================
# 🔥 CHART_DATA - OPERAÇÕES ESPECÍFICAS
# ==============================================

def update_analysis_chart_data(
    db: Session,
    analysis_id: int,
    chart_data: Dict[str, Any],
) -> Optional[models.Analysis]:
    """
    🔥 Atualiza apenas o chart_data de uma análise
    
    Args:
        db: Sessão do banco
        analysis_id: ID da análise
        chart_data: Dados para o gráfico (weekly, monthly, performance)
    
    Returns:
        Analysis: Análise atualizada ou None se não encontrada
    """
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        logger.warning(f"⚠️ Análise {analysis_id} não encontrada para atualizar chart_data")
        return None
    
    analysis.chart_data = chart_data
    safe_commit(db, "Erro ao atualizar chart_data da análise")
    db.refresh(analysis)
    
    logger.info(f"📊 ChartData atualizado para análise {analysis_id}")
    logger.debug(f"   Weekly: {len(chart_data.get('weekly', {}).get('revenue', []))} dias")
    logger.debug(f"   Monthly: {len(chart_data.get('monthly', {}).get('revenue', []))} meses")
    return analysis


def get_analysis_chart_data(
    db: Session,
    analysis_id: int,
) -> Optional[Dict[str, Any]]:
    """
    🔥 Retorna apenas o chart_data de uma análise
    
    Args:
        db: Sessão do banco
        analysis_id: ID da análise
    
    Returns:
        Dict: chart_data ou None se não encontrado
    """
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        return None
    return analysis.chart_data


def has_chart_data(
    db: Session,
    analysis_id: int,
) -> bool:
    """
    🔥 Verifica se uma análise tem chart_data
    
    Args:
        db: Sessão do banco
        analysis_id: ID da análise
    
    Returns:
        bool: True se tem chart_data
    """
    analysis = get_analysis(db, analysis_id)
    if not analysis:
        return False
    return analysis.chart_data is not None and bool(analysis.chart_data)


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
    return db.query(models.User).filter(models.User.role == role).all()


def get_user_stats(db: Session) -> Dict[str, Any]:
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
# SESSÃO E LOGOUT
# ==============================================

def clear_user_session(db: Session, user_id: int, logout_all_devices: bool = True) -> bool:
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
    user = get_user_by_id(db, user_id)
    if not user:
        return {"error": "Usuário não encontrado"}
    
    has_valid_token = False
    if user.refresh_token and user.refresh_token_expires:
        has_valid_token = _is_datetime_valid(user.refresh_token_expires) and not user.refresh_token_revoked
    
    return {
        "user_id": user.id,
        "user_email": user.email,
        "is_admin": user.is_admin,
        "has_refresh_token": bool(user.refresh_token),
        "refresh_token_valid": has_valid_token,
        "refresh_token_expires_at": user.refresh_token_expires.isoformat() if user.refresh_token_expires else None,
        "refresh_token_revoked": user.refresh_token_revoked,
        "session_active": has_valid_token,
        "needs_cleanup": _is_datetime_expired(user.refresh_token_expires) if user.refresh_token_expires else False,
        "timezone": "America/Sao_Paulo (UTC-3)"
    }


def force_logout_user(db: Session, email: str, reason: str = "Admin action") -> bool:
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
    users = db.query(models.User).filter(
        models.User.refresh_token.isnot(None),
        models.User.refresh_token_revoked == False
    ).all()
    count = 0
    for user in users:
        if _is_datetime_expired(user.refresh_token_expires):
            user.refresh_token = None
            user.refresh_token_jti = None
            user.refresh_token_revoked = True
            user.refresh_token_expires = None
            count += 1
    if count > 0:
        safe_commit(db, "Erro ao limpar sessões órfãs")
        logger.info(f"🧹 {count} sessões órfãs limpas")
    return count


def complete_logout(db: Session, user_id: int, refresh_token: str = None) -> bool:
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


# ==============================================
# SISTEMA DE MENSAGENS
# ==============================================

def count_user_analyses(db: Session, user_id: int) -> int:
    try:
        try:
            db.execute(text("SELECT 1 FROM analyses LIMIT 1"))
        except Exception as e:
            logger.warning(f"⚠️ Tabela 'analyses' não existe: {e}")
            return 0
        return db.query(models.Analysis).filter(models.Analysis.user_id == user_id).count()
    except Exception as e:
        logger.warning(f"⚠️ Erro ao contar análises do usuário {user_id}: {e}")
        return 0


def calculate_user_segment(db: Session, user: models.User) -> Dict[str, Any]:
    if not user:
        return {"segment": "regular", "analyses_count": 0, "days_since_creation": 0, "is_premium": False, "credits": 0, "has_ever_used": False}
    
    is_premium = _is_premium_user(user)
    if is_premium:
        logger.info(f"📊 [Segment] Usuário {user.email} é PREMIUM")
        return {"segment": "premium", "analyses_count": 0, "days_since_creation": 0, "is_premium": True, "credits": user.credits or 0, "has_ever_used": True}
    
    analyses_count = count_user_analyses(db, user.id)
    days_since_creation = 999
    if user.created_at:
        created_naive = user.created_at.replace(tzinfo=None) if user.created_at.tzinfo else user.created_at
        now_naive = _now_brasil().replace(tzinfo=None)
        days_since_creation = (now_naive - created_naive).days
    
    is_new = days_since_creation < 7 and analyses_count == 0 and user.credits == 3
    if is_new:
        logger.info(f"📊 [Segment] Usuário {user.email} é NOVO")
        return {"segment": "new", "analyses_count": analyses_count, "days_since_creation": days_since_creation, "is_premium": False, "credits": user.credits or 0, "has_ever_used": False}
    
    has_ever_used = analyses_count > 0 or user.credits < 3
    logger.info(f"📊 [Segment] Usuário {user.email} é REGULAR")
    return {"segment": "regular", "analyses_count": analyses_count, "days_since_creation": days_since_creation, "is_premium": False, "credits": user.credits or 0, "has_ever_used": has_ever_used}


def get_message_config(segment: str, credits: int, is_admin: bool = False) -> Dict[str, Any]:
    if is_admin:
        return {"message_id": "admin_welcome", "title": "👑 Painel Administrativo", "icon": "fa-crown", "color": "premium", "message": "Você tem acesso ilimitado a todas as funcionalidades do sistema.", "show_action": True, "action_text": "Ir para Dashboard", "action_url": "/dashboard", "priority": 0, "dismissible": True}
    
    if segment == "premium":
        if credits >= 3:
            return {"message_id": "premium_full", "title": "🌟 Créditos no Máximo!", "icon": "fa-star", "color": "premium", "message": "Seus créditos estão no máximo (3/3)! Use-os para não acumular e perder.", "show_action": True, "action_text": "Fazer Análise", "action_url": "/dashboard", "priority": 1, "dismissible": True}
        elif credits == 2:
            return {"message_id": "premium_two", "title": "⭐ Créditos Disponíveis", "icon": "fa-star-half-alt", "color": "premium", "message": "Você tem 2 créditos. Use-os ou perca-os!", "show_action": True, "action_text": "Fazer Análise", "action_url": "/dashboard", "priority": 1, "dismissible": True}
        elif credits == 1:
            return {"message_id": "premium_one", "title": "✨ Último Crédito!", "icon": "fa-star", "color": "warning", "message": "Depois de gastar, novos créditos serão gerados amanhã. 🎯", "show_action": True, "action_text": "Usar Agora", "action_url": "/dashboard", "priority": 2, "dismissible": True}
        else:
            return {"message_id": "premium_zero", "title": "🔄 Créditos Esgotados", "icon": "fa-sync", "color": "info", "message": "Todos os créditos gastos! Novos créditos estarão disponíveis amanhã. Volte amanhã! 🌅", "show_action": True, "action_text": "Ver Status", "action_url": "/dashboard", "priority": 1, "dismissible": True}
    
    if segment == "new":
        if credits == 3:
            return {"message_id": "new_welcome", "title": "👋 Bem-vindo ao AutoAnalytics!", "icon": "fa-rocket", "color": "success", "message": "🎉 Você ganhou 3 créditos para testar o sistema. Faça sua primeira análise agora!", "show_action": True, "action_text": "🚀 Começar Análise", "action_url": "/dashboard", "priority": 2, "dismissible": True}
        elif credits == 2:
            return {"message_id": "new_two", "title": "⚡ Continue testando!", "icon": "fa-bolt", "color": "warning", "message": "Você gastou 1 crédito! Agora você tem 2 créditos restantes. Não perca a chance! 💪", "show_action": True, "action_text": "Usar Crédito", "action_url": "/dashboard", "priority": 1, "dismissible": True}
        elif credits == 1:
            return {"message_id": "new_one", "title": "🔥 Último crédito!", "icon": "fa-fire", "color": "warning", "message": "Use seu último crédito sabiamente e veja o poder do AutoAnalytics. ⚡", "show_action": True, "action_text": "Usar Agora", "action_url": "/dashboard", "priority": 2, "dismissible": True}
        else:
            return {"message_id": "new_zero", "title": "🎉 Você testou o sistema!", "icon": "fa-gem", "color": "info", "message": "Que bom que você testou o AutoAnalytics! 💎 Se quiser mais relatórios, não perca nossas promoções exclusivas.", "show_action": True, "action_text": "💎 Ver Planos", "action_url": "/planos", "priority": 2, "dismissible": True}
    
    if credits > 0:
        credit_text = "crédito" if credits == 1 else "créditos"
        return {"message_id": f"regular_{credits}", "title": "💰 Créditos Disponíveis", "icon": "fa-coins", "color": "info", "message": f"Você tem {credits} {credit_text} disponíveis. Use-os antes que expirem! ⏰", "show_action": True, "action_text": "Usar Créditos", "action_url": "/dashboard", "priority": 1, "dismissible": True}
    else:
        return {"message_id": "regular_zero", "title": "🚀 Quer mais análises?", "icon": "fa-crown", "color": "primary", "message": "Seus créditos acabaram! 😅 Assine o plano Premium e tenha análises ilimitadas. 🏆", "show_action": True, "action_text": "👑 Ver Planos Premium", "action_url": "/planos", "priority": 2, "dismissible": True}


def get_full_user_context(db: Session, user: models.User) -> Dict[str, Any]:
    if not user:
        return {"segment": "regular", "ui_context": {"segment": "regular", "credits": 0, "max_credits": MAX_CREDITS_PREMIUM, "is_premium": False, "is_admin": False, "display_name": "Usuário", "workshop_name": "Oficina", "credit_display": "0", "analyses_count": 0, "days_since_creation": 0}, "message_config": get_message_config("regular", 0, False)}
    
    segment_data = calculate_user_segment(db, user)
    segment = segment_data["segment"]
    credits = user.credits or 0
    is_premium = segment_data["is_premium"]
    is_admin = user.is_admin
    analyses_count = segment_data["analyses_count"]
    days_since_creation = segment_data["days_since_creation"]
    message_config = get_message_config(segment, credits, is_admin)
    
    ui_context = {
        "segment": segment,
        "credits": credits,
        "max_credits": MAX_CREDITS_PREMIUM,
        "is_premium": is_premium,
        "is_admin": is_admin,
        "display_name": user.name or "Usuário",
        "workshop_name": user.workshop_name or "Oficina",
        "credit_display": "∞" if is_admin else get_credits_display(user),
        "analyses_count": analyses_count,
        "days_since_creation": days_since_creation
    }
    
    logger.info(f"📊 [Context] Usuário {user.email}: segment={segment}, credits={credits}, msg={message_config.get('message_id')}")
    return {"segment": segment, "ui_context": ui_context, "message_config": message_config}


# ==============================================
# PRINTS DE CARREGAMENTO
# ==============================================

print("=" * 70)
print("✅ crud.py v2.1 carregado - COM CHART_DATA!")
print("   🔥 create_analysis() unificada com suporte a PoW")
print("   🔥 update_analysis_metrics() → Métricas de performance")
print("   🔥 update_analysis_data_metrics() → Métricas de dados")
print("   🔥 update_analysis_results() → Resultados + chart_data")
print("   🔥 update_analysis_chart_data() → Atualização específica")
print("   🔥 get_analysis_chart_data() → Busca específica")
print("   🔥 has_chart_data() → Verificação")
print("   🔥 get_analyses_with_pow_stats() → Estatísticas de PoW")
print("   🔥 get_user_analyses() → Já inclui todos os campos")
print("   🔥 UTC-3 (Brasília) mantido para criação de registros")
print("=" * 70)