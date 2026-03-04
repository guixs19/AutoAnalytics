# backend/crud.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from backend import models, schemas
from backend.security import hasher

# ============ USUÁRIOS ============
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    """Cria usuário com hash Argon2"""
    hashed_password = hasher.hash_password(user.password)
    
    db_user = models.User(
        email=user.email,
        name=user.name,
        hashed_password=hashed_password,
        workshop_name=user.workshop_name,
        phone=user.phone,
        role=user.role,
        is_active=True,
        is_verified=False,
        created_at=datetime.now(),
        credits=0,
        total_purchased=0
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, password: str):
    """Autentica usuário usando Argon2"""
    user = get_user_by_email(db, email)
    if not user:
        return None
    
    if not user.verify_password(password):
        return None
    
    return user

def update_user(db: Session, user_id: int, user_update: dict):
    """Atualiza usuário"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        for key, value in user_update.items():
            if hasattr(db_user, key) and value is not None:
                setattr(db_user, key, value)
        db.commit()
        db.refresh(db_user)
    return db_user

def update_last_login(db: Session, user_id: int):
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.last_login = datetime.now()
        db.commit()
        db.refresh(db_user)
    return db_user

# ============ CRÉDITOS ============
def get_user_credits(db: Session, user_id: int) -> int:
    user = get_user_by_id(db, user_id)
    return user.credits if user else 0

def add_credits(db: Session, user_id: int, amount: int) -> bool:
    user = get_user_by_id(db, user_id)
    if user:
        user.add_credits(amount)
        db.commit()
        db.refresh(user)
        return True
    return False

def deduct_credits(db: Session, user_id: int, amount: int = 1) -> bool:
    user = get_user_by_id(db, user_id)
    if user and user.deduct_credit(amount):
        db.commit()
        db.refresh(user)
        return True
    return False

def check_credits(db: Session, user_id: int, required: int = 1) -> bool:
    user = get_user_by_id(db, user_id)
    return user.has_credits(required) if user else False

# ============ PAGAMENTOS ============
def create_payment_record(
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
    payment_metadata: dict = None  # 🔥 CORRIGIDO: metadata -> payment_metadata
):
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
        payment_metadata=payment_metadata or {},  # 🔥 CORRIGIDO
        created_at=datetime.now()
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment

def get_payment_by_mp_id(db: Session, mp_id: str):
    """Busca pagamento pelo ID do Mercado Pago"""
    return db.query(models.Payment).filter(models.Payment.mp_id == mp_id).first()

def get_payment_by_preference_id(db: Session, preference_id: str):
    """Busca pagamento pelo ID da preferência (checkout)"""
    return db.query(models.Payment).filter(models.Payment.preference_id == preference_id).first()

def update_payment_status(
    db: Session, 
    payment_id: int, 
    status: models.PaymentStatus, 
    mp_data: dict = None
):
    """Atualiza status do pagamento"""
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if payment:
        payment.status = status
        if status == models.PaymentStatus.APPROVED:
            payment.approved_at = datetime.now()
        if mp_data:
            # 🔥 CORRIGIDO: metadata -> payment_metadata
            payment.payment_metadata = {**payment.payment_metadata, **mp_data}
        payment.updated_at = datetime.now()
        db.commit()
        db.refresh(payment)
    return payment

def get_user_payments(db: Session, user_id: int, limit: int = 10):
    """Retorna histórico de pagamentos do usuário"""
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id
    ).order_by(models.Payment.created_at.desc()).limit(limit).all()

# ============ ADMIN ============
def get_all_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()

def get_users_by_role(db: Session, role: schemas.UserRole):
    return db.query(models.User).filter(models.User.role == role).all()

def delete_user(db: Session, user_id: int):
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user

def get_user_stats(db: Session):
    total = db.query(models.User).count()
    active = db.query(models.User).filter(models.User.is_active == True).count()
    admins = db.query(models.User).filter(models.User.role == schemas.UserRole.ADMIN).count()
    managers = db.query(models.User).filter(models.User.role == schemas.UserRole.MANAGER).count()
    users = db.query(models.User).filter(models.User.role == schemas.UserRole.USER).count()
    
    return {
        "total_users": total,
        "active_users": active,
        "admins": admins,
        "managers": managers,
        "users": users
    }

# ============ ANÁLISES ============
def create_analysis(db: Session, analysis: schemas.AnalysisCreate, user_id: int):
    db_analysis = models.Analysis(
        **analysis.dict(),
        user_id=user_id,
        uploaded_at=datetime.now(),
        status="pending"
    )
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)
    return db_analysis

def get_user_analyses(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id
    ).order_by(models.Analysis.uploaded_at.desc()).offset(skip).limit(limit).all()

def get_analysis(db: Session, analysis_id: int):
    return db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()

def update_analysis(db: Session, analysis_id: int, updates: dict):
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        for key, value in updates.items():
            if hasattr(db_analysis, key) and value is not None:
                setattr(db_analysis, key, value)
        db.commit()
        db.refresh(db_analysis)
    return db_analysis

def delete_analysis(db: Session, analysis_id: int):
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db.delete(db_analysis)
        db.commit()
    return db_analysis

def get_all_analyses(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Analysis).offset(skip).limit(limit).all()