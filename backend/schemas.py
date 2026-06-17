# backend/schemas.py - VERSÃO CORRIGIDA (com default_factory e timezone)

from pydantic import BaseModel, EmailStr, Field, validator, field_validator
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

# 🔥 Definir fuso horário de Brasília (UTC-3) - mesmo do models.py
TZ_BRASIL = timezone(timedelta(hours=-3))

def _now_brasil() -> datetime:
    """Retorna datetime atual no fuso horário de Brasília (UTC-3)"""
    return datetime.now(TZ_BRASIL)


# ==============================================
# ENUMS
# ==============================================

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    CLIENT = "client"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class AnalysisType(str, Enum):
    CLIENTES = "clientes"
    SERVICOS = "servicos"
    ESTOQUE = "estoque"
    FINANCEIRO = "financeiro"

class AIModel(str, Enum):
    FLOWISE = "flowise"
    BASICO = "basico"

class UserPlan(str, Enum):
    BASICO = "basico"
    PROFISSIONAL = "profissional"
    EMPRESARIAL = "empresarial"
    PREMIUM_MENSAL = "premium_mensal"


# ==============================================
# USER SCHEMAS (COMPLETOS)
# ==============================================

class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    workshop_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    role: UserRole = UserRole.USER

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Nome é obrigatório')
        return v.strip()

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v:
            cleaned = ''.join(filter(str.isdigit, v))
            if len(cleaned) < 10:
                raise ValueError('Telefone deve ter pelo menos 10 dígitos')
        return v


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    captcha_text: Optional[str] = None
    captcha_id: Optional[str] = None
    session_type: Optional[str] = "register"
    is_admin: Optional[bool] = False
    credits: Optional[int] = 3

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Senha deve ter pelo menos 6 caracteres')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    captcha_text: Optional[str] = None
    captcha_id: Optional[str] = None
    session_type: Optional[str] = "login"


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    workshop_name: Optional[str] = Field(None, max_length=200)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    is_admin: Optional[bool] = None
    plan: Optional[UserPlan] = None
    credits: Optional[int] = None
    promotional_price_locked: Optional[bool] = None
    promotional_price: Optional[float] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Nome não pode estar vazio')
            return v.strip()
        return v


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_admin: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None
    credits: int = 0
    total_purchased: int = 0
    plan: UserPlan = UserPlan.BASICO
    premium_activated_at: Optional[datetime] = None
    premium_expires_at: Optional[date] = None
    promotional_price_locked: bool = False
    promotional_price: Optional[float] = None
    purchased_at_promotion: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserStats(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    admins: int
    role_admins: int
    managers: int
    users: int
    premium_users: int = 0
    total_credits_distributed: int = 0
    average_credits: float = 0
    premium_revenue: float = 0


# ==============================================
# PREMIUM SCHEMAS
# ==============================================

class PremiumStatus(BaseModel):
    is_premium: bool
    plan: UserPlan
    activated_at: Optional[datetime] = None
    expires_at: Optional[date] = None
    days_left: int = 0
    progress: float = 0
    credits_balance: int = 0
    max_credits_balance: int = 3
    timezone: str = "America/Sao_Paulo (UTC-3)"
    
    class Config:
        from_attributes = True


class DailyCreditLogBase(BaseModel):
    credits_added: int
    date: date
    day_number: int
    total_after: int


class DailyCreditLogCreate(DailyCreditLogBase):
    user_id: int
    payment_id: Optional[int] = None
    source: Optional[str] = "daily_upload"


class DailyCreditLogResponse(DailyCreditLogBase):
    id: int
    user_id: int
    payment_id: Optional[int] = None
    source: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class PremiumSummary(BaseModel):
    plan_name: str = "Premium Mensal"
    price: float = 58.90
    credits_per_day: int = 1
    total_days: int = 30
    total_credits: int = 30
    daily_cost: float = 1.96
    features: List[str] = [
        "1 crédito novo todo dia",
        "30 créditos no total",
        "Válido por 30 dias",
        "Menos de R$ 2,00 por dia"
    ]


# ==============================================
# PROMOTION SCHEMAS (VAGAS BRONZE - VITALÍCIO)
# ==============================================

class PromotionControlBase(BaseModel):
    total_slots: int = 100
    used_slots: int = 0
    promotional_price: float = 97.00
    regular_price: float = 149.90
    is_active: bool = True


class PromotionControlCreate(PromotionControlBase):
    pass


class PromotionControlUpdate(BaseModel):
    total_slots: Optional[int] = None
    used_slots: Optional[int] = None
    promotional_price: Optional[float] = None
    regular_price: Optional[float] = None
    is_active: Optional[bool] = None


class PromotionControlResponse(PromotionControlBase):
    id: int
    created_at: datetime
    updated_at: datetime
    remaining_slots: int
    has_available_slots: bool
    current_price: float
    
    class Config:
        from_attributes = True


class PromotionStatus(BaseModel):
    is_active: bool
    remaining_slots: int
    total_slots: int
    used_slots: int
    promotional_price: float
    regular_price: float
    current_price: float
    price_saved: float
    percentage_off: float
    slots_percentage: float
    has_available_slots: bool
    is_vitalicio: bool = True


# ==============================================
# TOKEN SCHEMAS
# ==============================================

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user_name: str
    user_email: str
    workshop_name: Optional[str] = None
    role: UserRole
    is_admin: bool = False
    plan: UserPlan = UserPlan.BASICO
    credits: int = 0
    promotional_price_locked: bool = False
    current_price: Optional[float] = None


class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_admin: Optional[bool] = False


class TokenRefresh(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 6:
            raise ValueError('Nova senha deve ter pelo menos 6 caracteres')
        return v


# ==============================================
# PAYMENT SCHEMAS
# ==============================================

class PaymentBase(BaseModel):
    amount: float = Field(..., gt=0)
    credits: int = Field(..., gt=0)
    payment_method: str
    description: Optional[str] = None


class PaymentCreate(PaymentBase):
    user_id: int
    mp_id: str
    preference_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None


class PaymentResponse(PaymentBase):
    id: int
    user_id: int
    mp_id: str
    status: PaymentStatus
    qr_code: Optional[str] = None
    qr_code_base64: Optional[str] = None
    qr_code_url: Optional[str] = None
    checkout_url: Optional[str] = None
    preference_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    daily_credit_logs: List[DailyCreditLogResponse] = []
    
    class Config:
        from_attributes = True


class PixPaymentResponse(BaseModel):
    success: bool
    payment_id: int
    mp_payment_id: str
    qr_code_base64: Optional[str] = None
    qr_code: Optional[str] = None
    expiration_date: Optional[str] = None
    credits: int
    amount: float
    status: str
    test_mode: bool = False
    promotional_applied: bool = False
    promotional_price: Optional[float] = None
    regular_price: Optional[float] = None


# ==============================================
# ANALYSIS SCHEMAS
# ==============================================

class AnalysisBase(BaseModel):
    filename: str
    analysis_type: AnalysisType = AnalysisType.CLIENTES


class AnalysisCreate(AnalysisBase):
    user_id: Optional[int] = None
    ai_model: AIModel = AIModel.FLOWISE


class AnalysisResponse(AnalysisBase):
    id: int
    user_id: Optional[int] = None
    status: str = "pending"
    ai_used: bool = False
    rows_processed: int = 0
    columns_processed: int = 0
    ai_report: Optional[str] = None
    report_path: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AnalysisUpdate(BaseModel):
    status: Optional[str] = None
    ai_used: Optional[bool] = None
    rows_processed: Optional[int] = None
    columns_processed: Optional[int] = None
    ai_report: Optional[str] = None
    report_path: Optional[str] = None
    processed_at: Optional[datetime] = None


class UploadResponse(BaseModel):
    message: str
    analysis_id: int
    filename: str
    status: str
    process_id: Optional[str] = None
    credits_remaining: Optional[int] = None


# ==============================================
# UPLOAD & PROCESSING SCHEMAS
# ==============================================

class FileUpload(BaseModel):
    analysis_type: AnalysisType = AnalysisType.CLIENTES
    ai_model: AIModel = AIModel.FLOWISE


class ProcessingStatus(BaseModel):
    process_id: str
    status: str
    progress: int = 0
    message: Optional[str] = None
    analysis_id: Optional[int] = None
    error: Optional[str] = None


class AnalysisResult(BaseModel):
    process_id: str
    status: str = "completed"
    analysis_id: int
    filename: str
    summary: Optional[dict] = None
    ai_response: Optional[dict] = None
    predictions: Optional[list] = None
    ai_used: bool = False
    download_url: Optional[str] = None
    created_at: datetime = Field(default_factory=_now_brasil)  # 🔥 CORRIGIDO


# ==============================================
# STATISTICS & DASHBOARD SCHEMAS
# ==============================================

class DashboardStats(BaseModel):
    total_analyses: int
    analyses_today: int
    ai_used_count: int
    total_users: int
    recent_analyses: List[Dict[str, Any]] = []
    credits_balance: int = 0
    premium_status: Optional[PremiumStatus] = None


class MLPrediction(BaseModel):
    id_registro: int
    valor_previsao: float
    classificacao: str
    cor: str
    icone: str
    confianca: float
    segmento: str
    acao_recomendada: str
    detalhes: Dict[str, Any]


# ==============================================
# AI RESPONSE SCHEMAS
# ==============================================

class AIAnalysisRequest(BaseModel):
    question: str
    data: Dict[str, Any]
    context: str = "oficina"


class AIAnalysisResponse(BaseModel):
    success: bool
    insights: List[str]
    recommendations: List[str]
    analysis: Optional[str] = None
    raw_response: Optional[str] = None
    ai_available: bool = True
    message: Optional[str] = None


# ==============================================
# FILE SCHEMAS
# ==============================================

class FileInfo(BaseModel):
    filename: str
    size: int
    extension: str
    uploaded_at: datetime = Field(default_factory=_now_brasil)  # 🔥 CORRIGIDO


class FileProcessResult(BaseModel):
    success: bool
    message: str
    filename: str
    rows: int
    columns: int
    sample_data: List[Dict[str, Any]] = []
    analysis: Dict[str, Any] = {}


# ==============================================
# ERROR SCHEMAS
# ==============================================

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: int = 400
    timestamp: datetime = Field(default_factory=_now_brasil)  # 🔥 CORRIGIDO


class ValidationError(BaseModel):
    field: str
    message: str
    value: Optional[Any] = None


# ==============================================
# SYSTEM SCHEMAS
# ==============================================

class HealthCheck(BaseModel):
    status: str
    timestamp: datetime = Field(default_factory=_now_brasil)  # 🔥 CORRIGIDO
    version: str
    database: str
    frontend: Dict[str, bool]
    services: Dict[str, str]


class SystemInfo(BaseModel):
    app_name: str
    version: str
    debug: bool
    port: int
    database: str
    paths: Dict[str, str]


# ==============================================
# PRICE SCHEMAS (para exibição no frontend)
# ==============================================

class PriceInfo(BaseModel):
    current_price: float
    regular_price: float
    promotional_price: float
    has_promotion: bool
    remaining_slots: int
    total_slots: int
    is_vitalicio: bool = True
    savings: float
    savings_percentage: float


print("✅ schemas.py carregado - CORRIGIDO: default_factory com UTC-3")