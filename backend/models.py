# backend/models.py - COM extend_existing EM TODAS AS CLASSES
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, Enum, ForeignKey, JSON, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from backend.database import Base
from backend.security import hasher


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    CLIENT = "client"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class UserPlan(str, enum.Enum):
    BASICO = "basico"
    PROFISSIONAL = "profissional"
    EMPRESARIAL = "empresarial"
    PREMIUM_MENSAL = "premium_mensal"


class User(Base):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}  # 🔥 CORREÇÃO AQUI
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    workshop_name = Column(String)
    phone = Column(String)
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime)
    
    # ✅ CAMPO ADMIN ADICIONADO AQUI
    is_admin = Column(Boolean, default=False)
    
    # Créditos
    credits = Column(Integer, default=0)
    total_purchased = Column(Integer, default=0)
    last_payment_date = Column(DateTime)
    
    # Plano premium
    plan = Column(Enum(UserPlan), default=UserPlan.BASICO)
    premium_activated_at = Column(DateTime, nullable=True)
    premium_expires_at = Column(Date, nullable=True)
    
    # Refresh token
    refresh_token = Column(Text, nullable=True)
    refresh_token_expires = Column(DateTime, nullable=True)
    refresh_token_revoked = Column(Boolean, default=False)
    refresh_token_jti = Column(String, nullable=True)
    last_refresh_at = Column(DateTime, nullable=True)
    
    # Relacionamentos
    analyses = relationship("Analysis", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    daily_credits = relationship("DailyCreditLog", back_populates="user", cascade="all, delete-orphan")
    
    def verify_password(self, password: str) -> bool:
        return hasher.verify_password(password, self.hashed_password)
    
    def set_password(self, password: str):
        self.hashed_password = hasher.hash_password(password)
    
    def has_credits(self, required: int = 1) -> bool:
        # ✅ ADMIN sempre tem créditos
        if self.is_admin:
            return True
        return self.credits >= required
    
    def deduct_credit(self, amount: int = 1) -> bool:
        # ✅ ADMIN não deduz créditos
        if self.is_admin:
            return True
        if self.credits >= amount:
            self.credits -= amount
            return True
        return False
    
    def add_credits(self, amount: int):
        self.credits += amount
        self.total_purchased += amount
        self.last_payment_date = datetime.now()
    
    def is_premium(self) -> bool:
        from datetime import date
        if self.plan != UserPlan.PREMIUM_MENSAL:
            return False
        if not self.premium_expires_at:
            return False
        return self.premium_expires_at >= date.today()
    
    def get_premium_days_left(self) -> int:
        from datetime import date
        if not self.is_premium():
            return 0
        return (self.premium_expires_at - date.today()).days
    
    def get_premium_progress(self) -> float:
        from datetime import date
        if not self.premium_activated_at or not self.premium_expires_at:
            return 0
        
        total_days = 30
        days_passed = (date.today() - self.premium_activated_at.date()).days
        if days_passed < 0:
            days_passed = 0
        elif days_passed > total_days:
            days_passed = total_days
        
        return round((days_passed / total_days) * 100, 1)
    
    # ===== MÉTODOS PARA REFRESH TOKEN =====
    def set_refresh_token(self, token: str, jti: str, expires_days: int = 7):
        from datetime import datetime, timedelta
        self.refresh_token = token
        self.refresh_token_jti = jti
        self.refresh_token_expires = datetime.utcnow() + timedelta(days=expires_days)
        self.refresh_token_revoked = False
        self.last_refresh_at = datetime.utcnow()
    
    def validate_refresh_token(self, token: str) -> bool:
        from datetime import datetime
        return (
            self.refresh_token == token and
            self.refresh_token_expires and
            self.refresh_token_expires > datetime.utcnow() and
            not self.refresh_token_revoked
        )
    
    def revoke_refresh_token(self):
        self.refresh_token_revoked = True
        self.refresh_token = None
        self.refresh_token_jti = None
        self.refresh_token_expires = None


class Payment(Base):
    __tablename__ = 'payments'
    __table_args__ = {'extend_existing': True}  # 🔥 CORREÇÃO AQUI
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    mp_id = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=False)
    credits = Column(Integer, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    
    payment_method = Column(String)
    payment_type = Column(String)
    
    qr_code = Column(Text)
    qr_code_base64 = Column(Text)
    qr_code_url = Column(String)
    checkout_url = Column(String)
    preference_id = Column(String)
    
    description = Column(String)
    payment_metadata = Column(JSON, default={})
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    
    user = relationship("User", back_populates="payments")
    daily_credit_logs = relationship("DailyCreditLog", back_populates="payment", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id,
            "mp_id": self.mp_id,
            "amount": self.amount,
            "credits": self.credits,
            "status": self.status.value if self.status else None,
            "payment_method": self.payment_method,
            "qr_code_base64": self.qr_code_base64,
            "qr_code_url": self.qr_code_url,
            "checkout_url": self.checkout_url,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None
        }


class DailyCreditLog(Base):
    __tablename__ = 'daily_credit_logs'
    __table_args__ = {'extend_existing': True}  # 🔥 CORREÇÃO AQUI
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    
    credits_added = Column(Integer, default=1)
    date = Column(Date, default=datetime.now().date)
    day_number = Column(Integer)
    total_after = Column(Integer)
    source = Column(String, default="daily_upload")  # ✅ ADICIONADO CAMPO SOURCE
    
    created_at = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="daily_credits")
    payment = relationship("Payment", back_populates="daily_credit_logs")
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "credits_added": self.credits_added,
            "date": self.date.isoformat() if self.date else None,
            "day_number": self.day_number,
            "total_after": self.total_after,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Analysis(Base):
    __tablename__ = 'analyses'
    __table_args__ = {'extend_existing': True}  # 🔥 CORREÇÃO AQUI
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename = Column(String)
    analysis_type = Column(String)
    status = Column(String, default="pending")
    ai_used = Column(Boolean, default=False)
    rows_processed = Column(Integer, default=0)
    columns_processed = Column(Integer, default=0)
    ai_report = Column(Text)
    report_path = Column(String)
    uploaded_at = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime)
    
    user = relationship("User", back_populates="analyses")