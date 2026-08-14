# backend/models.py - VERSÃO 2.6 COM CREDITS_NEEDED
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, Enum, ForeignKey, JSON, Date, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime, date, timedelta, timezone
import enum
from typing import Dict, Any, Optional, List, Union  # 🔥 ADICIONAR ESTA LINHA

from backend.database import Base
from backend.security import hasher
"""
🔥 Models - AutoAnalytics
Versão: 2.6 - Com campo credits_needed

🔥 NOVIDADES v2.6:
   - ✅ ADICIONADO: credits_needed - Créditos necessários para liberar a análise

🔥 NOVIDADES v2.5:
   - ✅ ADICIONADO: received_initial_credits - Controle de créditos iniciais
   - ✅ ADICIONADO: Método has_received_initial_credits()
   - ✅ ADICIONADO: Método mark_initial_credits_received()

🔥 MELHORIAS v2.4:
   - ✅ ADICIONADO: credits_consumed - Indica se o crédito foi consumido
   - ✅ ADICIONADO: credits_consumed_at - Data do consumo do crédito
   - ✅ ADICIONADO: credits_consumed_amount - Quantidade consumida (1)
   - ✅ ADICIONADO: credits_remaining_after - Saldo após consumo
   - ✅ ADICIONADO: credits_error - Erro no consumo de crédito
   - ✅ ADICIONADO: credits_bonus_granted - Se bônus foi concedido
   - ✅ ADICIONADO: credits_bonus_amount - Quantidade de bônus

🔥 MANTIDO v2.3:
   - last_bonus_at - Controle de último bônus recebido
   - bonus_count - Total de bônus recebidos
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, Enum, ForeignKey, JSON, Date, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime, date, timedelta, timezone
import enum

from backend.database import Base
from backend.security import hasher

# 🔥 FUSO HORÁRIO DE BRASÍLIA (UTC-3)
TZ_BRASIL = timezone(timedelta(hours=-3))

def _now_brasil() -> datetime:
    """Retorna datetime atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL)

def _today_brasil() -> date:
    """Retorna data atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL).date()


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
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    workshop_name = Column(String)
    phone = Column(String)
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=_now_brasil)
    last_login = Column(DateTime, onupdate=_now_brasil)
    
    is_admin = Column(Boolean, default=False)
    
    # Créditos
    credits = Column(Integer, default=0)
    total_purchased = Column(Integer, default=0)
    last_payment_date = Column(DateTime, onupdate=_now_brasil)
    
    # 🔥 CONTROLE DE CRÉDITOS INICIAIS (NOVO v2.5)
    received_initial_credits = Column(Boolean, default=False, nullable=False, comment="Indica se o usuário já recebeu os créditos iniciais")
    
    # 🔥 NOVOS CAMPOS PARA CONTROLE DE BÔNUS PREMIUM
    last_bonus_at = Column(DateTime, nullable=True, comment="Última vez que recebeu bônus premium por zerar créditos")
    bonus_count = Column(Integer, default=0, comment="Número total de bônus premium recebidos")
    
    # Plano premium
    plan = Column(Enum(UserPlan), default=UserPlan.BASICO)
    premium_activated_at = Column(DateTime, nullable=True)
    premium_expires_at = Column(Date, nullable=True)
    
    # Promoção
    promotional_price_locked = Column(Boolean, default=False)
    promotional_price = Column(Float, nullable=True)
    purchased_at_promotion = Column(DateTime, nullable=True)
    
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
    
    # ===== MÉTODOS =====
    def verify_password(self, password: str) -> bool:
        return hasher.verify_password(password, self.hashed_password)
    
    def set_password(self, password: str):
        self.hashed_password = hasher.hash_password(password)
    
    def has_credits(self, required: int = 1) -> bool:
        if self.is_admin:
            return True
        return self.credits >= required
    
    def deduct_credit(self, amount: int = 1) -> bool:
        if self.is_admin:
            return True
        if self.credits >= amount:
            self.credits -= amount
            return True
        return False
    
    def add_credits(self, amount: int):
        self.credits += amount
        self.total_purchased += amount
        self.last_payment_date = _now_brasil()
    
    # 🔥 NOVOS MÉTODOS PARA CRÉDITOS INICIAIS (v2.5)
    def has_received_initial_credits(self) -> bool:
        """Verifica se o usuário já recebeu os créditos iniciais"""
        return self.received_initial_credits
    
    def mark_initial_credits_received(self):
        """Marca que o usuário já recebeu os créditos iniciais"""
        self.received_initial_credits = True
    
    # 🔥 NOVOS MÉTODOS PARA BÔNUS
    def has_received_bonus_today(self) -> bool:
        """Verifica se o usuário já recebeu bônus hoje"""
        if not self.last_bonus_at:
            return False
        return self.last_bonus_at.date() == _today_brasil()
    
    def mark_bonus_received(self):
        """Marca que o usuário recebeu bônus hoje"""
        self.last_bonus_at = _now_brasil()
        self.bonus_count = (self.bonus_count or 0) + 1
    
    def can_receive_bonus_today(self) -> bool:
        """Verifica se o usuário pode receber bônus hoje (apenas premium)"""
        if not self.is_premium():
            return False
        if self.has_received_bonus_today():
            return False
        return True
    
    def is_premium(self) -> bool:
        if self.plan != UserPlan.PREMIUM_MENSAL:
            return False
        if not self.premium_expires_at:
            return False
        return self.premium_expires_at >= _today_brasil()
    
    def get_premium_days_left(self) -> int:
        if not self.is_premium():
            return 0
        return (self.premium_expires_at - _today_brasil()).days
    
    def get_premium_progress(self) -> float:
        if not self.premium_activated_at or not self.premium_expires_at:
            return 0
        total_days = 30
        days_passed = (_today_brasil() - self.premium_activated_at.date()).days
        if days_passed < 0:
            days_passed = 0
        elif days_passed > total_days:
            days_passed = total_days
        return round((days_passed / total_days) * 100, 1)
    
    def get_current_price(self) -> float:
        if self.promotional_price_locked and self.promotional_price:
            return self.promotional_price
        return 97.00
    
    # Refresh Token
    def set_refresh_token(self, token: str, jti: str, expires_days: int = 7):
        self.refresh_token = token
        self.refresh_token_jti = jti
        self.refresh_token_expires = _now_brasil() + timedelta(days=expires_days)
        self.refresh_token_revoked = False
        self.last_refresh_at = _now_brasil()
    
    def validate_refresh_token(self, token: str) -> bool:
        return (
            self.refresh_token == token and
            self.refresh_token_expires and
            self.refresh_token_expires > _now_brasil() and
            not self.refresh_token_revoked
        )
    
    def revoke_refresh_token(self):
        self.refresh_token_revoked = True
        self.refresh_token = None
        self.refresh_token_jti = None
        self.refresh_token_expires = None


class Payment(Base):
    __tablename__ = 'payments'
    __table_args__ = {'extend_existing': True}
    
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
    
    created_at = Column(DateTime, default=_now_brasil)
    updated_at = Column(DateTime, default=_now_brasil, onupdate=_now_brasil)
    approved_at = Column(DateTime, nullable=True)
    
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
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    
    credits_added = Column(Integer, default=1)
    date = Column(Date, default=_today_brasil)
    day_number = Column(Integer)
    total_after = Column(Integer)
    source = Column(String, default="daily_upload")
    
    created_at = Column(DateTime, default=_now_brasil)
    
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


# ==============================================
# 🔥🔥🔥 ANALYSIS - VERSÃO 2.6 COM CREDITS_NEEDED
# ==============================================
               
class Analysis(Base):
    __tablename__ = 'analyses'
    __table_args__ = {'extend_existing': True}
    
    # ===== CAMPOS EXISTENTES =====
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True, comment="Tamanho do arquivo em bytes")
    analysis_type = Column(String, nullable=False, default="auto")
    status = Column(String, default="pending")
    ai_used = Column(Boolean, default=False)
    rows_processed = Column(Integer, default=0)
    columns_processed = Column(Integer, default=0)
    ai_report = Column(Text, nullable=True)
    report_path = Column(String, nullable=True)
    
    uploaded_at = Column(DateTime, default=_now_brasil)
    processed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="analyses")
    
    # ==========================================
    # 🔥 CAMPOS POW E SEGURANÇA
    # ==========================================
    
    pow_challenge = Column(String(64), nullable=True, comment="Desafio PoW usado no upload")
    pow_nonce = Column(String(64), nullable=True, comment="Nonce PoW usado no upload")
    pow_difficulty = Column(Integer, default=4, comment="Dificuldade do PoW (número de zeros)")
    pow_verified = Column(Boolean, default=False, comment="PoW foi verificado pelo backend")
    pow_verified_at = Column(DateTime, nullable=True, comment="Data da verificação PoW")
    pow_algorithm = Column(String(20), default="SHA-256", comment="Algoritmo usado")
    
    # Segurança
    client_ip = Column(String(45), nullable=True, comment="IP do cliente")
    user_agent = Column(String(255), nullable=True, comment="User Agent do cliente")
    rate_limit_applied = Column(Boolean, default=False, comment="Rate limit foi aplicado")
    
    # Métricas de performance
    processing_time_ms = Column(Integer, nullable=True, comment="Tempo total de processamento em ms")
    pow_solve_time_ms = Column(Integer, nullable=True, comment="Tempo de resolução do PoW em ms")
    upload_time_ms = Column(Integer, nullable=True, comment="Tempo de upload em ms")
    
    # Métricas de ML
    encoding_used = Column(String(20), nullable=True, comment="Encoding detectado no arquivo")
    model_used = Column(String(50), nullable=True, comment="Modelo ML utilizado")
    confidence_score = Column(Float, nullable=True, comment="Score de confiança do modelo")
    
    # Métricas de dados
    total_rows = Column(Integer, default=0, comment="Total de linhas processadas")
    total_columns = Column(Integer, default=0, comment="Total de colunas processadas")
    numeric_columns = Column(Integer, default=0, comment="Colunas numéricas")
    categorical_columns = Column(Integer, default=0, comment="Colunas categóricas")
    
    # ==========================================
    # 🔥 CHART_DATA PARA GRÁFICOS
    # ==========================================
    
    chart_data = Column(JSON, nullable=True, comment="Dados para renderização de gráficos")
    
    # ==========================================
    # 🔥 PROGRESSO PARA POLLING
    # ==========================================
    
    progress = Column(Integer, default=0, comment="Progresso do processamento (0-100)")
    progress_message = Column(String(255), default="Aguardando início...", comment="Mensagem de progresso")
    
    # ==========================================
    # 🔥🔥🔥 CAMPOS DE CRÉDITO (V2.6 - NOVOS)
    # ==========================================
    
    # 🔥 V2.6: Créditos necessários para liberar a análise
    credits_needed = Column(Integer, default=1, comment="Créditos necessários para liberar a análise")
    
    # V2.4: Controle de consumo
    credits_consumed = Column(Boolean, default=False, comment="Indica se o crédito foi consumido")
    credits_consumed_at = Column(DateTime, nullable=True, comment="Data do consumo do crédito")
    credits_consumed_amount = Column(Integer, default=0, comment="Quantidade consumida (1)")
    credits_remaining_after = Column(Integer, nullable=True, comment="Saldo após consumo")
    credits_error = Column(String(255), nullable=True, comment="Erro no consumo de crédito")
    credits_bonus_granted = Column(Boolean, default=False, comment="Se bônus foi concedido")
    credits_bonus_amount = Column(Integer, default=0, comment="Quantidade de bônus")
    
    # ==========================================
    # RESULTADOS
    # ==========================================
    
    predictions_summary = Column(JSON, nullable=True, comment="Resumo das predições")
    insights = Column(JSON, nullable=True, comment="Insights gerados")
    recommendations = Column(JSON, nullable=True, comment="Recomendações geradas")
    executive_score = Column(JSON, nullable=True, comment="Score executivo")
    
    # ===== MÉTODOS =====
    
    def set_pow_data(self, challenge: str, nonce: str, difficulty: int = 4):
        self.pow_challenge = challenge
        self.pow_nonce = nonce
        self.pow_difficulty = difficulty
        self.pow_algorithm = "SHA-256"
    
    def verify_pow(self):
        self.pow_verified = True
        self.pow_verified_at = _now_brasil()
    
    def set_processing_metrics(self, metrics: dict):
        if 'processing_time_ms' in metrics:
            self.processing_time_ms = metrics['processing_time_ms']
        if 'pow_solve_time_ms' in metrics:
            self.pow_solve_time_ms = metrics['pow_solve_time_ms']
        if 'upload_time_ms' in metrics:
            self.upload_time_ms = metrics['upload_time_ms']
        if 'encoding_used' in metrics:
            self.encoding_used = metrics['encoding_used']
        if 'model_used' in metrics:
            self.model_used = metrics['model_used']
        if 'confidence_score' in metrics:
            self.confidence_score = metrics['confidence_score']
    
    def set_data_metrics(self, data: dict):
        if 'total_rows' in data:
            self.total_rows = data['total_rows']
        if 'total_columns' in data:
            self.total_columns = data['total_columns']
        if 'numeric_columns' in data:
            self.numeric_columns = data['numeric_columns']
        if 'categorical_columns' in data:
            self.categorical_columns = data['categorical_columns']
    
    def set_results(self, results: dict):
        if 'predictions_summary' in results:
            self.predictions_summary = results['predictions_summary']
        if 'insights' in results:
            self.insights = results['insights']
        if 'recommendations' in results:
            self.recommendations = results['recommendations']
        if 'chart_data' in results:
            self.chart_data = results['chart_data']
        if 'executive_score' in results:
            self.executive_score = results['executive_score']
    
    # 🔥 NOVOS MÉTODOS PARA CRÉDITOS
    def mark_credit_consumed(self, amount: int = 1, remaining: int = None):
        """Marca que o crédito foi consumido"""
        self.credits_consumed = True
        self.credits_consumed_at = _now_brasil()
        self.credits_consumed_amount = amount
        if remaining is not None:
            self.credits_remaining_after = remaining
    
    def mark_credit_error(self, error: str):
        """Marca erro no consumo de crédito"""
        self.credits_error = error
    
    def mark_bonus_granted(self, amount: int = 1):
        """Marca que bônus foi concedido"""
        self.credits_bonus_granted = True
        self.credits_bonus_amount = amount
    
    def has_credit_consumed(self) -> bool:
        """Verifica se o crédito já foi consumido"""
        return self.credits_consumed
    
    def is_pending_credit(self) -> bool:
        """Verifica se está aguardando crédito"""
        return self.status == "pending_credit" or (not self.credits_consumed and self.status == "completed")
    
    def needs_credits(self) -> bool:
        """Verifica se a análise precisa de créditos para ser liberada"""
        return not self.credits_consumed and self.status in ["completed", "pending_credit"]
    
    def get_credits_status(self) -> Dict[str, Any]:
        """Retorna o status completo dos créditos da análise"""
        return {
            "needed": self.credits_needed or 1,
            "consumed": self.credits_consumed,
            "consumed_at": self.credits_consumed_at.isoformat() if self.credits_consumed_at else None,
            "amount_consumed": self.credits_consumed_amount,
            "remaining_after": self.credits_remaining_after,
            "error": self.credits_error,
            "bonus_granted": self.credits_bonus_granted,
            "bonus_amount": self.credits_bonus_amount,
            "is_pending": self.is_pending_credit()
        }
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "analysis_type": self.analysis_type,
            "status": self.status,
            "ai_used": self.ai_used,
            "rows_processed": self.rows_processed,
            "columns_processed": self.columns_processed,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "pow_verified": self.pow_verified,
            "pow_difficulty": self.pow_difficulty,
            "pow_algorithm": self.pow_algorithm,
            "client_ip": self.client_ip,
            "rate_limit_applied": self.rate_limit_applied,
            "processing_time_ms": self.processing_time_ms,
            "encoding_used": self.encoding_used,
            "model_used": self.model_used,
            "confidence_score": self.confidence_score,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "numeric_columns": self.numeric_columns,
            "categorical_columns": self.categorical_columns,
            "chart_data": self.chart_data,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "predictions_summary": self.predictions_summary,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "executive_score": self.executive_score,
            # 🔥 CAMPOS DE CRÉDITO (V2.6)
            "credits_needed": self.credits_needed,
            "credits_consumed": self.credits_consumed,
            "credits_consumed_at": self.credits_consumed_at.isoformat() if self.credits_consumed_at else None,
            "credits_consumed_amount": self.credits_consumed_amount,
            "credits_remaining_after": self.credits_remaining_after,
            "credits_error": self.credits_error,
            "credits_bonus_granted": self.credits_bonus_granted,
            "credits_bonus_amount": self.credits_bonus_amount,
            "is_pending_credit": self.is_pending_credit()
        }


# ==============================================
# 🔥 PROMOTION CONTROL
# ==============================================

class PromotionControl(Base):
    __tablename__ = 'promotion_control'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    total_slots = Column(Integer, default=100)
    used_slots = Column(Integer, default=0)
    promotional_price = Column(Float, default=97.00)
    regular_price = Column(Float, default=149.90)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=_now_brasil)
    updated_at = Column(DateTime, default=_now_brasil, onupdate=_now_brasil)
    
    def get_remaining_slots(self) -> int:
        return max(0, self.total_slots - self.used_slots)
    
    def has_available_slots(self) -> bool:
        return self.get_remaining_slots() > 0 and self.is_active
    
    def get_current_price(self) -> float:
        return self.promotional_price if self.has_available_slots() else self.regular_price
    
    def use_slot(self) -> bool:
        if self.has_available_slots():
            self.used_slots += 1
            self.updated_at = _now_brasil()
            return True
        return False
    
    def reset_promotion(self):
        self.used_slots = 0
        self.is_active = True
        self.updated_at = _now_brasil()


# ==============================================
# 🔥 BLACKLISTED TOKEN
# ==============================================

class BlacklistedToken(Base):
    __tablename__ = 'blacklisted_tokens'
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(512), unique=True, index=True, nullable=False)
    jti = Column(String(255), unique=True, index=True, nullable=True)
    blacklisted_at = Column(DateTime, default=_now_brasil, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    def __repr__(self):
        return f"<BlacklistedToken jti={self.jti[:8] if self.jti else 'None'}... expires={self.expires_at}>"


print("=" * 70)
print("🔥 models.py v2.6 carregado - COM CREDITS_NEEDED!")
print("   ✅ NOVO CAMPO (v2.6):")
print("      - credits_needed: Créditos necessários para liberar a análise")
print("      - needs_credits(): Verifica se precisa de créditos")
print("      - get_credits_status(): Status completo dos créditos")
print("   ✅ NOVO CAMPO (v2.5):")
print("      - received_initial_credits: Controle de créditos iniciais")
print("      - has_received_initial_credits(): Verifica se já recebeu")
print("      - mark_initial_credits_received(): Marca como recebido")
print("   ✅ ANÁLISES:")
print("      - Analysis com campos PoW")
print("      - Analysis com file_size")
print("      - Analysis com métricas de performance")
print("      - Analysis com chart_data para gráficos")
print("      - Analysis com progress para polling")
print("   ✅ CRÉDITOS (v2.4):")
print("      - credits_consumed: Indica se o crédito foi consumido")
print("      - credits_consumed_at: Data do consumo")
print("      - credits_consumed_amount: Quantidade consumida (1)")
print("      - credits_remaining_after: Saldo após consumo")
print("      - credits_error: Erro no consumo")
print("      - credits_bonus_granted: Bônus concedido")
print("      - credits_bonus_amount: Quantidade de bônus")
print("   ✅ USUÁRIOS (v2.3):")
print("      - last_bonus_at: controle de bônus premium")
print("      - bonus_count: total de bônus recebidos")
print("   ✅ Datetimes sincronizados com UTC-3 (Brasília)")
print("=" * 70)