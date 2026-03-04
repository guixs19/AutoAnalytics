# backend/models.py - COM ARGON2 E PAGAMENTOS
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, Enum, ForeignKey, JSON
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
    
    # Relacionamentos
    analyses = relationship("Analysis", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    
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


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

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
    # ⚠️ CORREÇÃO: 'metadata' é palavra reservada, mudei para 'payment_metadata'
    payment_metadata = Column(JSON, default={})  
    
    # Datas
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    
    # Relacionamentos
    user = relationship("User", back_populates="payments")
    
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
            "payment_metadata": self.payment_metadata,  # Nome atualizado
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None
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