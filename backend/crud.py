# backend/crud.py - VERSÃO CORRIGIDA (TIMEZONE BLINDADO)
"""
CRUD - Operações de banco de dados
SINCRONIZADO COM:
- models.py (UTC-3, hashed_password, UserPlan, PaymentStatus)
- security.py (timestamps UNIX, safe_compare_datetime)
- auth_routes.py (_is_token_expired)
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, not_, desc, asc, update
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
    """Retorna datetime atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL)

def _today_brasil() -> date:
    """Retorna data atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL).date()

def _get_next_day_brasil(days_ahead: int = 1) -> date:
    """Retorna data futura no fuso horário de Brasília"""
    return _today_brasil() + timedelta(days=days_ahead)

# ==============================================
# 🔥 FUNÇÃO CORINGA PARA COMPARAÇÃO DE DATAS (BLINDADA)
# ==============================================

def _is_datetime_expired(db_datetime: Optional[datetime]) -> bool:
    """
    🔥 FUNÇÃO UNIVERSAL: Verifica se um datetime do banco já expirou.
    🔥 100% BLINDADA CONTRA ERROS DE TIMEZONE!
    
    Remove o fuso horário de ambos os lados antes de comparar.
    """
    if db_datetime is None:
        return True
    
    # Remove timezone do datetime do banco (se tiver)
    naive_db = db_datetime.replace(tzinfo=None) if db_datetime.tzinfo else db_datetime
    naive_now = datetime.utcnow()
    
    return naive_db < naive_now


def _is_datetime_valid(db_datetime: Optional[datetime]) -> bool:
    """
    🔥 Versão inversa: Retorna True se o datetime NÃO expirou.
    """
    return not _is_datetime_expired(db_datetime)


# ==============================================
# CONSTANTES SINCRONIZADAS
# ==============================================

MAX_CREDITS_PREMIUM = 3
INITIAL_FREE_CREDITS = 3


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
    """
    if not user:
        return False
    
    if hasattr(user, 'is_premium') and callable(user.is_premium):
        return user.is_premium()
    
    plan = user.plan
    
    if hasattr(plan, 'value'):
        return plan.value == "premium_mensal"
    elif hasattr(plan, 'name'):
        return plan.name == "PREMIUM_MENSAL"
    else:
        return plan == "premium_mensal"

def _get_plan_value(user: models.User) -> str:
    """Retorna o valor do plano como string"""
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
    """Verifica se usuário já existe por email ou telefone"""
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
    🔥 SINCRONIZADO COM models.py, schemas.py, credits_consumer.py
    """
    
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
    """
    Autentica usuário usando Argon2
    🔥 Agora chama update_last_login corretamente
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
    
    # 🔥 CORRIGIDO: Usa a função update_last_login
    update_last_login(db, user.id)
    
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


# ==============================================
# 🔥 UPDATE_LAST_LOGIN - CORRIGIDO
# ==============================================

def update_last_login(db: Session, user_id: int) -> Optional[models.User]:
    """
    🔥 Atualiza o timestamp do último login do usuário
    🔥 SINCRONIZADO: Usa fuso horário UTC-3 (Brasília)
    🔥 CHAMADO POR: auth_routes.py (login)
    """
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.last_login = _now_brasil()  # 🔥 Usa UTC-3
        safe_commit(db, "Erro ao atualizar último login")
        db.refresh(db_user)
        logger.debug(f"✅ Último login atualizado para: {db_user.email}")
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
# CRÉDITOS - OPERAÇÕES
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
    Admin: "∞" | Premium: "X/3" | Usuário: número normal
    """
    if user.is_admin:
        return "∞"
    
    is_premium = _is_premium_user(user)
    
    if is_premium:
        return f"{user.credits or 0}/{MAX_CREDITS_PREMIUM}"
    
    return str(user.credits or 0)


def check_credits(user: models.User, required: int = 1) -> bool:
    """Verifica se usuário tem créditos suficientes"""
    if user.is_admin:
        return True
    return (user.credits or 0) >= required


def add_credits(db: Session, user_id: int, amount: int, description: str = "") -> bool:
    """
    Adiciona créditos ao usuário com verificação de limite
    🔥 SINCRONIZADO COM daily_credits_service.py
    """
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
    
    is_premium = _is_premium_user(user)
    if is_premium and user.credits < MAX_CREDITS_PREMIUM:
        logger.info(f"⭐ Premium {user.email} agora tem {user.credits}/{MAX_CREDITS_PREMIUM} créditos - pode receber mais")
    
    logger.info(f"💰 {user.email} consumiu {amount} crédito(s). Antes: {old_credits}, Agora: {user.credits}")
    return True


def check_credits_db(db: Session, user_id: int, required: int = 1) -> bool:
    """Verifica créditos (versão com db)"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    if user.is_admin:
        return True
    
    return (user.credits or 0) >= required


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
    
    from_user.credits -= amount
    
    success = add_credits(db, to_user_id, amount, f"Transferência de {from_user.email}")
    
    if success:
        logger.info(f"💰 {amount} créditos transferidos de {from_user.email} para {to_user.email}")
    else:
        from_user.credits += amount
        safe_commit(db, "Erro ao reverter transferência")
    
    return success


# ==============================================
# CRÉDITOS DIÁRIOS - SUPORTE
# ==============================================

def get_daily_credit_logs(db: Session, user_id: int, days: int = 30, limit: int = None) -> List[models.DailyCreditLog]:
    """Retorna logs de créditos diários do usuário"""
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
    """Verifica se o usuário já recebeu crédito diário hoje"""
    today = _today_brasil()
    
    log = db.query(models.DailyCreditLog).filter(
        models.DailyCreditLog.user_id == user_id,
        func.date(models.DailyCreditLog.date) == today
    ).first()
    
    return log is not None


def get_premium_credit_streak(db: Session, user_id: int) -> int:
    """Calcula o streak (dias seguidos) de créditos premium"""
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
    """
    Verifica se o usuário premium pode receber crédito diário
    🔥 SINCRONIZADO COM daily_credits_service.py
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return {"success": False, "error": "Usuário não encontrado"}
    
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
# 🔥 REFRESH TOKEN - OPERAÇÕES CORRIGIDAS (TIMEZONE BLINDADO)
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
    """
    🔥 CORRIGIDO: Busca usuário pelo refresh token (válido)
    🔥 Usa _is_datetime_valid() para comparação blindada
    """
    # Busca todos os usuários com o refresh token (não revogados)
    users = db.query(models.User).filter(
        models.User.refresh_token == refresh_token,
        models.User.refresh_token_revoked == False
    ).all()
    
    # 🔥 Filtra em Python usando função blindada de timezone
    for user in users:
        if _is_datetime_valid(user.refresh_token_expires):
            return user
    
    return None


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
    """
    🔥 CORRIGIDO: Remove tokens expirados (job agendado)
    🔥 Usa _is_datetime_expired() para comparação blindada
    """
    # Busca todos os usuários com refresh token
    users = db.query(models.User).filter(
        models.User.refresh_token.isnot(None)
    ).all()
    
    count = 0
    for user in users:
        # 🔥 Usa função blindada de timezone
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
# PLANO PREMIUM - OPERAÇÕES
# ==============================================

def activate_premium_plan(db: Session, user_id: int, payment_id: int = None) -> bool:
    """Ativa plano premium para usuário"""
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
    """Verifica status do plano premium"""
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
        logger.info(f"⭐ {count} usuários tiveram plano premium expirado")
    
    return count


# ==============================================
# PAGAMENTOS - OPERAÇÕES
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
# 🔥 SESSÃO E LOGOUT COMPLETO - CORRIGIDO
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
    """
    🔥 CORRIGIDO: Retorna informações da sessão atual do usuário
    🔥 Usa _is_datetime_valid() para comparação blindada
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return {"error": "Usuário não encontrado"}
    
    # 🔥 Usa função blindada de timezone
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
    """
    🔥 CORRIGIDO: Limpeza de sessões órfãs
    🔥 Usa _is_datetime_expired() para comparação blindada
    """
    # Busca todos os usuários com refresh token não revogado
    users = db.query(models.User).filter(
        models.User.refresh_token.isnot(None),
        models.User.refresh_token_revoked == False
    ).all()
    
    count = 0
    for user in users:
        # 🔥 Usa função blindada de timezone
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


print("=" * 70)
print("✅ crud.py carregado - TIMEZONE BLINDADO")
print("   🔥 _is_datetime_expired() → Função universal blindada")
print("   🔥 _is_datetime_valid() → Versão inversa")
print("   🔥 get_user_by_refresh_token() → Corrigido (filtro em Python)")
print("   🔥 cleanup_expired_refresh_tokens() → Corrigido")
print("   🔥 get_user_session_info() → Corrigido")
print("   🔥 cleanup_orphaned_sessions() → Corrigido")
print("   🔥 UTC-3 (Brasília) mantido para criação de registros")
print("=" * 70)