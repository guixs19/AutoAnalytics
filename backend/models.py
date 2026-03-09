# backend/models.py - COM ARGON2, PAGAMENTOS E PLANO PREMIUM
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

# NOVO ENUM PARA PLANOS
class UserPlan(str, enum.Enum):
    BASICO = "basico"
    PROFISSIONAL = "profissional"
    EMPRESARIAL = "empresarial"
    PREMIUM_MENSAL = "premium_mensal"  # 1 crédito por dia durante 30 dias

class User(Base):
    __tablename__ = "users"
    
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
    
    # ===== SISTEMA DE CRÉDITOS =====
    credits = Column(Integer, default=0)
    total_purchased = Column(Integer, default=0)
    last_payment_date = Column(DateTime)
    
    # ===== NOVOS CAMPOS PARA PLANO PREMIUM =====
    plan = Column(Enum(UserPlan), default=UserPlan.BASICO)
    premium_activated_at = Column(DateTime, nullable=True)  # Quando ativou o premium
    premium_expires_at = Column(Date, nullable=True)        # Quando expira (30 dias depois)
    
    # Relacionamentos
    analyses = relationship("Analysis", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    daily_credits = relationship("DailyCreditLog", back_populates="user", cascade="all, delete-orphan")  # NOVO
    
    def verify_password(self, password: str) -> bool:
        """Verifica senha usando Argon2"""
        return hasher.verify_password(password, self.hashed_password)
    
    def set_password(self, password: str):
        """Define senha usando Argon2"""
        self.hashed_password = hasher.hash_password(password)
    
    def has_credits(self, required: int = 1) -> bool:
        """Verifica se usuário tem créditos suficientes"""
        return self.credits >= required
    
    def deduct_credit(self, amount: int = 1):
        """Deduz créditos do usuário"""
        if self.credits >= amount:
            self.credits -= amount
            return True
        return False
    
    def add_credits(self, amount: int):
        """Adiciona créditos ao usuário"""
        self.credits += amount
        self.total_purchased += amount
        self.last_payment_date = datetime.now()
    
    # ===== NOVOS MÉTODOS PARA PLANO PREMIUM =====
    def is_premium(self) -> bool:
        """Verifica se usuário tem plano premium ativo"""
        from datetime import date
        if self.plan != UserPlan.PREMIUM_MENSAL:
            return False
        if not self.premium_expires_at:
            return False
        return self.premium_expires_at >= date.today()
    
    def get_premium_days_left(self) -> int:
        """Retorna dias restantes do plano premium"""
        from datetime import date
        if not self.is_premium():
            return 0
        return (self.premium_expires_at - date.today()).days
    
    def get_premium_progress(self) -> float:
        """Retorna progresso do plano premium em porcentagem"""
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


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Dados da transação
    mp_id = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=False)
    credits = Column(Integer, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    
    # Método de pagamento
    payment_method = Column(String)
    payment_type = Column(String)
    
    # URLs e QR Code
    qr_code = Column(Text)
    qr_code_base64 = Column(Text)
    qr_code_url = Column(String)
    checkout_url = Column(String)
    preference_id = Column(String)
    
    # Dados adicionais
    description = Column(String)
    payment_metadata = Column(JSON, default={})  
    
    # Datas
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    
    # Relacionamentos
    user = relationship("User", back_populates="payments")
    daily_credit_logs = relationship("DailyCreditLog", back_populates="payment", cascade="all, delete-orphan")  # NOVO
    
    def to_dict(self):
        return {
            "id": self.id,
            "mp_id": self.mp_id,
            "amount": self.amount,
            "credits": self.credits,
            "status": self.status.value,
            "payment_method": self.payment_method,
            "qr_code_base64": self.qr_code_base64,
            "qr_code_url": self.qr_code_url,
            "checkout_url": self.checkout_url,
            "description": self.description,
            "payment_metadata": self.payment_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None
        }


# ===== NOVO MODELO: DailyCreditLog =====
class DailyCreditLog(Base):
    """Registro de créditos diários do plano premium"""
    __tablename__ = "daily_credit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)
    
    # Dados do crédito
    credits_added = Column(Integer, default=1)  # Sempre 1
    date = Column(Date, default=datetime.now().date)  # Data da distribuição
    day_number = Column(Integer)  # Dia 1 a 30
    total_after = Column(Integer)  # Saldo após adicionar
    
    # Metadados
    created_at = Column(DateTime, default=datetime.now)
    
    # Relacionamentos
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
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Analysis(Base):
    __tablename__ = "analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
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