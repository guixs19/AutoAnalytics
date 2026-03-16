# backend/crud.py - VERSÃO COMPLETA COM SUPORTE A ADMIN
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Union
import logging

from backend import models, schemas
from backend.security import hasher, jwt_manager

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    
    # Criar usuário
    db_user = models.User(
        email=user.email.lower().strip(),
        name=user.name.strip(),
        hashed_password=hashed_password,
        workshop_name=user.workshop_name.strip() if user.workshop_name else None,
        phone=user.phone.strip() if user.phone else None,
        role=user.role or schemas.UserRole.USER,
        is_active=True,
        is_verified=False,
        created_at=datetime.now(),
        credits=0,
        total_purchased=0,
        plan=schemas.UserPlan.BASICO,
        is_admin=False  # ✅ NOVO: admin começa como False
    )
    
    db.add(db_user)
    safe_commit(db, "Erro ao criar usuário")
    db.refresh(db_user)
    
    logger.info(f"✅ Usuário criado: {db_user.email} (ID: {db_user.id})")
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
    
    # ✅ LOG PARA ADMIN
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
    
    # Converter para dict se for schema
    if hasattr(user_update, 'dict'):
        update_data = user_update.dict(exclude_unset=True)
    else:
        update_data = user_update.copy()
    
    # Tratamentos especiais
    if 'email' in update_data:
        update_data['email'] = update_data['email'].lower().strip()
        # Verificar se email já existe para outro usuário
        existing = get_user_by_email(db, update_data['email'])
        if existing and existing.id != user_id:
            raise ValueError("Email já está em uso")
    
    if 'phone' in update_data and update_data['phone']:
        update_data['phone'] = update_data['phone'].strip()
        # Verificar se telefone já existe para outro usuário
        existing = get_user_by_phone(db, update_data['phone'])
        if existing and existing.id != user_id:
            raise ValueError("Telefone já está em uso")
    
    if 'name' in update_data:
        update_data['name'] = update_data['name'].strip()
    
    if 'workshop_name' in update_data and update_data['workshop_name']:
        update_data['workshop_name'] = update_data['workshop_name'].strip()
    
    if 'password' in update_data:
        update_data['hashed_password'] = hasher.hash_password(update_data.pop('password'))
    
    # Atualizar campos
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
        db_user.last_login = datetime.now()
        safe_commit(db, "Erro ao atualizar último login")
        db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int) -> bool:
    """Remove usuário (soft delete ou hard delete)"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        # Soft delete: apenas desativa
        db_user.is_active = False
        db_user.email = f"deleted_{db_user.id}_{db_user.email}"  # Liberar email
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
# CRÉDITOS - OPERAÇÕES (ATUALIZADO)
# ==============================================

def get_user_credits(db: Session, user_id: int) -> int:
    """Retorna saldo de créditos do usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return 0
    
    # ✅ Admin retorna um número grande para compatibilidade
    if user.is_admin:
        return 999999
    
    return user.credits or 0

def get_credits_display(user: models.User) -> str:
    """Retorna string formatada para exibição de créditos"""
    if user.is_admin:
        return "∞"
    return str(user.credits or 0)

def add_credits(db: Session, user_id: int, amount: int, description: str = "") -> bool:
    """Adiciona créditos ao usuário com log"""
    user = get_user_by_id(db, user_id)
    if not user or amount <= 0:
        return False
    
    # ✅ Admin não precisa ganhar créditos
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - créditos ilimitados (add_credits ignorado)")
        return True
    
    user.add_credits(amount)
    
    safe_commit(db, "Erro ao adicionar créditos")
    logger.info(f"💰 {amount} créditos adicionados ao usuário {user_id}")
    return True

def deduct_credits(db: Session, user_id: int, amount: int = 1, description: str = "") -> bool:
    """Deduz créditos do usuário com log"""
    user = get_user_by_id(db, user_id)
    if not user or amount <= 0:
        return False
    
    # ✅ ADMIN NUNCA DEDUZ CRÉDITOS
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - operação sem consumo de créditos")
        return True
    
    if not user.has_credits(amount):
        logger.warning(f"⚠️ Créditos insuficientes para usuário {user_id}")
        return False
    
    user.deduct_credit(amount)
    
    safe_commit(db, "Erro ao deduzir créditos")
    logger.info(f"💰 {amount} créditos deduzidos do usuário {user_id}")
    return True

def check_credits(db: Session, user_id: int, required: int = 1) -> bool:
    """Verifica se usuário tem créditos suficientes"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    # ✅ ADMIN SEMPRE TEM CRÉDITOS
    if user.is_admin:
        return True
    
    return user.has_credits(required)

def transfer_credits(db: Session, from_user_id: int, to_user_id: int, amount: int) -> bool:
    """Transfere créditos entre usuários"""
    if amount <= 0:
        return False
    
    from_user = get_user_by_id(db, from_user_id)
    to_user = get_user_by_id(db, to_user_id)
    
    if not from_user or not to_user:
        return False
    
    # ✅ Admin que está transferindo não tem limite
    if from_user.is_admin:
        # Admin pode transferir sem ter créditos
        to_user.add_credits(amount)
        safe_commit(db, "Erro ao transferir créditos")
        logger.info(f"👑 Admin {from_user.email} transferiu {amount} créditos para {to_user.email}")
        return True
    
    # Usuário comum precisa ter créditos
    if not from_user.has_credits(amount):
        return False
    
    from_user.deduct_credit(amount)
    to_user.add_credits(amount)
    
    safe_commit(db, "Erro ao transferir créditos")
    logger.info(f"💰 {amount} créditos transferidos de {from_user_id} para {to_user_id}")
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
        models.User.refresh_token_expires > datetime.now(),
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
        models.User.refresh_token_expires < datetime.now()
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

def activate_premium_plan(db: Session, user_id: int, payment_id: int) -> bool:
    """Ativa plano premium para usuário"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    
    from datetime import date, timedelta
    
    user.plan = schemas.UserPlan.PREMIUM_MENSAL
    user.premium_activated_at = datetime.now()
    user.premium_expires_at = date.today() + timedelta(days=30)
    
    safe_commit(db, "Erro ao ativar plano premium")
    logger.info(f"⭐ Plano premium ativado para usuário {user_id}")
    return True

def check_premium_status(db: Session, user_id: int) -> Dict[str, Any]:
    """Verifica status do plano premium"""
    user = get_user_by_id(db, user_id)
    if not user:
        return {"is_premium": False}
    
    return {
        "is_premium": user.is_premium(),
        "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
        "activated_at": user.premium_activated_at,
        "expires_at": user.premium_expires_at,
        "days_left": user.get_premium_days_left(),
        "progress": user.get_premium_progress()
    }

def get_premium_users(db: Session) -> List[models.User]:
    """Retorna todos os usuários com plano premium ativo"""
    from datetime import date
    return db.query(models.User).filter(
        models.User.plan == schemas.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at >= date.today()
    ).all()

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
        created_at=datetime.now()
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
        payment.approved_at = datetime.now()
    
    if mp_data:
        payment.payment_metadata = {**payment.payment_metadata, **mp_data}
    
    payment.updated_at = datetime.now()
    
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
    threshold = datetime.now() - timedelta(minutes=minutes)
    return db.query(models.Payment).filter(
        models.Payment.status == models.PaymentStatus.PENDING,
        models.Payment.created_at < threshold
    ).all()

# ==============================================
# ANÁLISES - OPERAÇÕES
# ==============================================

def create_analysis(db: Session, analysis: schemas.AnalysisCreate, user_id: int) -> models.Analysis:
    """Cria registro de análise"""
    db_analysis = models.Analysis(
        **analysis.dict(),
        user_id=user_id,
        uploaded_at=datetime.now(),
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

# ==============================================
# ADMIN - OPERAÇÕES AVANÇADAS
# ==============================================

def get_all_users(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    role: Optional[schemas.UserRole] = None
) -> List[models.User]:
    """Lista usuários com filtros"""
    query = db.query(models.User)
    
    if active_only:
        query = query.filter(models.User.is_active == True)
    
    if role:
        query = query.filter(models.User.role == role)
    
    return query.offset(skip).limit(limit).all()

def get_users_by_role(db: Session, role: schemas.UserRole) -> List[models.User]:
    """Retorna usuários por role"""
    return db.query(models.User).filter(models.User.role == role).all()

def get_user_stats(db: Session) -> Dict[str, Any]:
    """Estatísticas detalhadas do sistema"""
    from datetime import date
    
    total = db.query(models.User).count()
    active = db.query(models.User).filter(models.User.is_active == True).count()
    
    # ✅ ADMIN STATS
    admins = db.query(models.User).filter(models.User.is_admin == True).count()
    
    # Por role
    role_admins = db.query(models.User).filter(models.User.role == schemas.UserRole.ADMIN).count()
    managers = db.query(models.User).filter(models.User.role == schemas.UserRole.MANAGER).count()
    users = db.query(models.User).filter(models.User.role == schemas.UserRole.USER).count()
    
    # Premium
    premium = db.query(models.User).filter(
        models.User.plan == schemas.UserPlan.PREMIUM_MENSAL,
        models.User.premium_expires_at >= date.today()
    ).count()
    
    # Créditos (excluindo admins do cálculo porque eles têm "infinito")
    total_credits = db.query(func.sum(models.User.credits)).filter(
        models.User.is_admin == False
    ).scalar() or 0
    avg_credits = db.query(func.avg(models.User.credits)).filter(
        models.User.is_admin == False
    ).scalar() or 0
    
    # Análises
    total_analyses = db.query(models.Analysis).count()
    analyses_today = db.query(models.Analysis).filter(
        func.date(models.Analysis.uploaded_at) == date.today()
    ).count()
    
    # Pagamentos
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
            "admins": admins,  # ✅ NOVO
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
        }
    }

def get_dashboard_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Estatísticas para dashboard do usuário"""
    user = get_user_by_id(db, user_id)
    
    # Análises do usuário
    analyses = get_user_analyses(db, user_id, limit=5)
    
    # Créditos (com display especial para admin)
    credits_info = {
        "balance": user.credits if user and not user.is_admin else 999999,
        "balance_display": get_credits_display(user) if user else "0",
        "total_purchased": user.total_purchased if user else 0,
        "is_admin": user.is_admin if user else False
    }
    
    # Premium
    premium_info = check_premium_status(db, user_id) if user else {"is_premium": False}
    
    # Pagamentos recentes
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
        "recent_analyses": [a.to_dict() if hasattr(a, 'to_dict') else {
            "id": a.id,
            "filename": a.filename,
            "status": a.status,
            "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None
        } for a in analyses],
        "recent_payments": [p.to_dict() if hasattr(p, 'to_dict') else {
            "id": p.id,
            "amount": p.amount,
            "credits": p.credits,
            "status": p.status.value if hasattr(p.status, 'value') else p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None
        } for p in payments],
        "timestamp": datetime.now().isoformat()
    }