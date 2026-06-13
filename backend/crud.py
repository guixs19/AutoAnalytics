# backend/crud.py - VERSÃO COMPLETA CORRIGIDA (COM FUSO UTC-3)
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, Union
import logging

from backend import models, schemas
from backend.security import hasher, jwt_manager

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔥 CORREÇÃO: Definir fuso horário de Brasília (UTC-3)
TZ_BRASIL = timezone(timedelta(hours=-3))

def _now_brasil() -> datetime:
    """Retorna datetime atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL)

def _today_brasil() -> date:
    """Retorna data atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL).date()


# ==============================================
# FUNÇÕES AUXILIARES
# ==============================================

def safe_commit(db: Session, error_msg: str = "Erro ao salvar no banco"):
    """Commit seguro com tratamento de erro"""
    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"{error_msg}: {e}")
        raise


# ==============================================
# USUÁRIOS - OPERAÇÕES BÁSICAS
# ==============================================

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """Busca usuário por email"""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    """Busca usuário por ID"""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    """Busca usuário por telefone"""
    if not phone:
        return None
    return db.query(models.User).filter(models.User.phone == phone).first()


def user_exists(db: Session, email: str, phone: Optional[str] = None) -> bool:
    """Verifica se usuário já existe por email ou telefone"""
    query = db.query(models.User).filter(models.User.email == email)
    if phone:
        query = query.or_(models.User.phone == phone)
    return query.first() is not None


def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """Cria usuário com hash Argon2 e validações"""
    
    # Verificar se já existe
    if user_exists(db, user.email, user.phone):
        raise ValueError("Email ou telefone já cadastrado")
    
    # Hash da senha
    hashed_password = hasher.hash_password(user.password)
    
    # 🔥 CORREÇÃO: usar _now_brasil() em vez de datetime.now()
    db_user = models.User(
        email=user.email.lower().strip(),
        name=user.name.strip(),
        hashed_password=hashed_password,
        workshop_name=user.workshop_name.strip() if user.workshop_name else None,
        phone=user.phone.strip() if user.phone else None,
        role=user.role or models.UserRole.USER,
        is_active=True,
        is_verified=False,
        created_at=_now_brasil(),  # 🔥 CORRIGIDO
        credits=3,  # 3 créditos grátis para novos usuários
        total_purchased=0,
        plan=models.UserPlan.BASICO,
        is_admin=False
    )
    
    db.add(db_user)
    safe_commit(db, "Erro ao criar usuário")
    db.refresh(db_user)
    
    logger.info(f"✅ Usuário criado: {db_user.email} (ID: {db_user.id}) - 3 créditos grátis")
    return db_user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """Autentica usuário usando Argon2"""
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
    else:
        update_data = user_update.copy()
    
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
    
    if 'name' in update_data:
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
    """Atualiza timestamp do último login"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.last_login = _now_brasil()  # 🔥 CORRIGIDO
        safe_commit(db, "Erro ao atualizar último login")
        db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    """Remove usuário (soft delete)"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.is_active = False
        db_user.email = f"deleted_{db_user.id}_{db_user.email}"
        db_user.phone = None
        db_user.refresh_token = None
        db_user.refresh_token_jti = None
        db_user.refresh_token_revoked = True
        
        safe_commit(db, "Erro ao desativar usuário")
        logger.info(f"✅ Usuário desativado: ID {user_id}")
        return True
    return False


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
    """Retorna string formatada para exibição de créditos"""
    if user.is_admin:
        return "∞"
    
    # Verificar se é premium (tem limite de 3)
    is_premium = user.plan == models.UserPlan.PREMIUM_MENSAL and user.is_premium()
    
    if is_premium:
        return f"{user.credits or 0}/3"
    
    return str(user.credits or 0)


def check_credits(user: models.User, required: int = 1) -> bool:
    """Verifica se usuário tem créditos suficientes"""
    if user.is_admin:
        return True
    return user.credits >= required


def add_credits(db: Session, user_id: int, amount: int, description: str = "") -> bool:
    """Adiciona créditos ao usuário"""
    user = get_user_by_id(db, user_id)
    if not user or amount <= 0:
        return False
    
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - créditos ilimitados")
        return True
    
    # Verificar limite para premium
    is_premium = user.plan == models.UserPlan.PREMIUM_MENSAL and user.is_premium()
    if is_premium:
        max_credits = 3
        if user.credits + amount > max_credits:
            logger.warning(f"⚠️ Premium {user.email} tentou exceder limite de {max_credits} créditos")
            return False
    
    user.add_credits(amount)
    safe_commit(db, "Erro ao adicionar créditos")
    logger.info(f"💰 {amount} créditos adicionados ao usuário {user_id}")
    return True


def deduct_credits(db: Session, user: models.User, amount: int = 1, description: str = "") -> bool:
    """Deduz créditos do usuário"""
    if not user or amount <= 0:
        return False
    
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - operação sem consumo")
        return True
    
    if not user.has_credits(amount):
        logger.warning(f"⚠️ Créditos insuficientes para {user.email}")
        return False
    
    user.deduct_credit(amount)
    safe_commit(db, "Erro ao deduzir créditos")
    logger.info(f"💰 {amount} créditos deduzidos de {user.email}")
    return True


def check_credits_db(db: Session, user_id: int, required: int = 1) -> bool:
    """Verifica créditos (versão com db)"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    if user.is_admin:
        return True
    return user.credits >= required


def transfer_credits(db: Session, from_user_id: int, to_user_id: int, amount: int) -> bool:
    """Transfere créditos entre usuários"""
    if amount <= 0:
        return False
    
    from_user = get_user_by_id(db, from_user_id)
    to_user = get_user_by_id(db, to_user_id)
    
    if not from_user or not to_user:
        return False
    
    if from_user.is_admin:
        to_user.add_credits(amount)
        safe_commit(db, "Erro ao transferir créditos")
        logger.info(f"👑 Admin {from_user.email} transferiu {amount} créditos")
        return True
    
    if not from_user.has_credits(amount):
        return False
    
    from_user.deduct_credit(amount)
    to_user.add_credits(amount)
    safe_commit(db, "Erro ao transferir créditos")
    logger.info(f"💰 {amount} créditos transferidos")
    return True


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
        models.User.refresh_token_expires > _now_brasil(),  # 🔥 CORRIGIDO
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
        models.User.refresh_token_expires < _now_brasil()  # 🔥 CORRIGIDO
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
# PLANO PREMIUM - OPERAÇÕES
# ==============================================

def activate_premium_plan(db: Session, user_id: int, payment_id: int = None) -> bool:
    """Ativa plano premium para usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    user.plan = models.UserPlan.PREMIUM_MENSAL
    user.premium_activated_at = _now_brasil()  # 🔥 CORRIGIDO
    user.premium_expires_at = _today_brasil() + timedelta(days=30)  # 🔥 CORRIGIDO
    
    safe_commit(db, "Erro ao ativar plano premium")
    logger.info(f"⭐ Plano premium ativado para usuário {user_id} (expira em 30 dias)")
    return True


def check_premium_status(db: Session, user_id: int) -> Dict[str, Any]:
    """Verifica status do plano premium"""
    user = get_user_by_id(db, user_id)
    if not user:
        return {"is_premium": False, "error": "Usuário não encontrado"}
    
    return {
        "is_premium": user.is_premium(),
        "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
        "activated_at": user.premium_activated_at,
        "expires_at": user.premium_expires_at,
        "days_left": user.get_premium_days_left(),
        "progress": user.get_premium_progress(),
        "credits_balance": user.credits or 0,
        "max_credits_balance": 3,
        "timezone": "America/Sao_Paulo (UTC-3)"  # 🔥 ADICIONADO
    }


def get_premium_users(db: Session) -> List[models.User]:
    """Retorna todos os usuários com plano premium ativo"""
    return db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at >= _today_brasil()  # 🔥 CORRIGIDO
    ).all()


def get_expired_premium_users(db: Session) -> List[models.User]:
    """Retorna usuários com plano premium expirado"""
    return db.query(models.User).filter(
        models.User.plan == models.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at < _today_brasil()  # 🔥 CORRIGIDO
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
        created_at=_now_brasil()  # 🔥 CORRIGIDO
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
        payment.approved_at = _now_brasil()  # 🔥 CORRIGIDO
    
    if mp_data:
        payment.payment_metadata = {**payment.payment_metadata, **mp_data}
    
    payment.updated_at = _now_brasil()  # 🔥 CORRIGIDO
    
    safe_commit(db, "Erro ao atualizar pagamento")
    db.refresh(payment)
    
    logger.info(f"💰 Pagamento {payment.mp_id} atualizado para {status}")
    return payment


def get_user_payments(db: Session, user_id: int, limit: int = 10) -> List[models.Payment]:
    """Retorna histórico de pagamentos do usuário"""
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id
    ).order_by(models.Payment.created_at.desc()).limit(limit).all()


def get_pending_payments(db: Session, minutes: int = 30) -> List[models.Payment]:
    """Retorna pagamentos pendentes há mais de X minutos"""
    threshold = _now_brasil() - timedelta(minutes=minutes)  # 🔥 CORRIGIDO
    return db.query(models.Payment).filter(
        models.Payment.status == models.PaymentStatus.PENDING,
        models.Payment.created_at < threshold
    ).all()


def get_approved_payments_by_user(db: Session, user_id: int) -> List[models.Payment]:
    """Retorna pagamentos aprovados do usuário"""
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id,
        models.Payment.status == models.PaymentStatus.APPROVED
    ).order_by(models.Payment.approved_at.desc()).all()


# ==============================================
# ANÁLISES - OPERAÇÕES
# ==============================================

def create_analysis(db: Session, analysis: schemas.AnalysisCreate, user_id: int) -> models.Analysis:
    """Cria registro de análise"""
    db_analysis = models.Analysis(
        **analysis.dict(),
        user_id=user_id,
        uploaded_at=_now_brasil(),  # 🔥 CORRIGIDO
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
    
    return query.order_by(models.Analysis.uploaded_at.desc()).offset(skip).limit(limit).all()


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
        models.Analysis.uploaded_at.desc()
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
    role: Optional[models.UserRole] = None
) -> List[models.User]:
    """Lista usuários com filtros"""
    query = db.query(models.User)
    
    if active_only:
        query = query.filter(models.User.is_active == True)
    
    if role:
        query = query.filter(models.User.role == role)
    
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
        models.User.premium_expires_at >= _today_brasil()  # 🔥 CORRIGIDO
    ).count()
    
    total_credits = db.query(func.sum(models.User.credits)).filter(
        models.User.is_admin == False
    ).scalar() or 0
    avg_credits = db.query(func.avg(models.User.credits)).filter(
        models.User.is_admin == False
    ).scalar() or 0
    
    total_analyses = db.query(models.Analysis).count()
    analyses_today = db.query(models.Analysis).filter(
        func.date(models.Analysis.uploaded_at) == _today_brasil()  # 🔥 CORRIGIDO
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
            "admins_have_unlimited": admins
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
        "timezone": "America/Sao_Paulo (UTC-3)"  # 🔥 ADICIONADO
    }


def get_dashboard_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Estatísticas para dashboard do usuário"""
    user = get_user_by_id(db, user_id)
    
    analyses = get_user_analyses(db, user_id, limit=5)
    
    credits_info = {
        "balance": user.credits if user and not user.is_admin else 999999,
        "balance_display": get_credits_display(user) if user else "0",
        "total_purchased": user.total_purchased if user else 0,
        "is_admin": user.is_admin if user else False
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
        "timestamp": _now_brasil().isoformat(),  # 🔥 CORRIGIDO
        "timezone": "America/Sao_Paulo (UTC-3)"  # 🔥 ADICIONADO
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
        has_valid_token = user.refresh_token_expires > _now_brasil() and not user.refresh_token_revoked  # 🔥 CORRIGIDO
    
    return {
        "user_id": user.id,
        "user_email": user.email,
        "is_admin": user.is_admin,
        "has_refresh_token": bool(user.refresh_token),
        "refresh_token_valid": has_valid_token,
        "refresh_token_expires_at": user.refresh_token_expires.isoformat() if user.refresh_token_expires else None,
        "refresh_token_revoked": user.refresh_token_revoked,
        "session_active": has_valid_token,
        "needs_cleanup": user.refresh_token_expires and user.refresh_token_expires < _now_brasil() if user.refresh_token_expires else False,  # 🔥 CORRIGIDO
        "timezone": "America/Sao_Paulo (UTC-3)"  # 🔥 ADICIONADO
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
    cutoff_date = _now_brasil() - timedelta(days=older_than_days)  # 🔥 CORRIGIDO
    
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


print("✅ crud.py carregado com correções de fuso UTC-3")