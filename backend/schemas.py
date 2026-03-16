# backend/schemas.py - VERSÃO COMPLETA COM PLANO PREMIUM E CORREÇÕES
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum

# ==============================================
# ENUMS
# ==============================================

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    CLIENT = "client"

class AnalysisType(str, Enum):
    CLIENTES = "clientes"
    SERVICOS = "servicos"
    ESTOQUE = "estoque"
    FINANCEIRO = "financeiro"

class AIModel(str, Enum):
    FLOWISE = "flowise"
    BASICO = "basico"

# NOVO ENUM PARA PLANOS
class UserPlan(str, Enum):
    BASICO = "basico"
    PROFISSIONAL = "profissional"
    EMPRESARIAL = "empresarial"
    PREMIUM_MENSAL = "premium_mensal"  # 1 crédito por dia durante 30 dias

# ==============================================
# USER SCHEMAS (ATUALIZADOS)
# ==============================================

class UserBase(BaseModel):
    email: EmailStr
    name: str
    workshop_name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole = UserRole.USER

class UserCreate(UserBase):
    password: str
    captcha_text: Optional[str] = None  # 🔥 ADICIONADO: captcha para registro

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    captcha_text: Optional[str] = None  # 🔥 ADICIONADO: captcha para login

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    # ===== NOVOS CAMPOS =====
    credits: int = 0
    total_purchased: int = 0
    plan: UserPlan = UserPlan.BASICO
    premium_activated_at: Optional[datetime] = None
    premium_expires_at: Optional[date] = None
    
    class Config:
        from_attributes = True

# ==============================================
# PREMIUM SCHEMAS (NOVOS)
# ==============================================

class PremiumStatus(BaseModel):
    """Status detalhado do plano premium"""
    is_premium: bool
    plan: UserPlan
    activated_at: Optional[datetime] = None
    expires_at: Optional[date] = None
    days_remaining: int = 0
    days_passed: int = 0
    total_days: int = 30
    progress_percentage: float = 0
    
    # Créditos
    credits_received: int = 0  # Total de créditos recebidos até hoje
    credits_remaining_to_receive: int = 0  # Créditos que ainda vai receber
    current_balance: int = 0  # Saldo atual
    
    # Status de hoje
    received_today: bool = False
    next_credit_date: Optional[date] = None
    
    class Config:
        from_attributes = True

class DailyCreditLogBase(BaseModel):
    """Base para log de crédito diário"""
    credits_added: int
    date: date
    day_number: int
    total_after: int

class DailyCreditLogCreate(DailyCreditLogBase):
    user_id: int
    payment_id: Optional[int] = None

class DailyCreditLogResponse(DailyCreditLogBase):
    """Resposta com log de crédito diário"""
    id: int
    user_id: int
    payment_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class PremiumSummary(BaseModel):
    """Resumo do plano premium para dashboard"""
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
# TOKEN SCHEMAS
# ==============================================

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    user_name: str
    user_email: str
    workshop_name: Optional[str] = None
    role: UserRole
    # NOVO: incluir plano no token
    plan: UserPlan = UserPlan.BASICO
    credits: int = 0

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class TokenRefresh(BaseModel):
    refresh_token: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

# ==============================================
# ADMIN SCHEMAS (ATUALIZADOS)
# ==============================================

class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    workshop_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    # NOVOS CAMPOS
    plan: Optional[UserPlan] = None
    credits: Optional[int] = None

class UserStats(BaseModel):
    total_users: int
    active_users: int
    admins: int
    managers: int
    users: int
    # NOVOS CAMPOS
    premium_users: int = 0
    total_credits_distributed: int = 0
    premium_revenue: float = 0

# ==============================================
# PAYMENT SCHEMAS (ATUALIZADOS)
# ==============================================

class PaymentBase(BaseModel):
    amount: float
    credits: int
    payment_method: str
    description: Optional[str] = None

class PaymentCreate(PaymentBase):
    user_id: int
    mp_id: str
    payment_metadata: Optional[Dict[str, Any]] = None

class PaymentResponse(PaymentBase):
    id: int
    user_id: int
    mp_id: str
    status: str
    qr_code: Optional[str] = None
    qr_code_base64: Optional[str] = None
    checkout_url: Optional[str] = None
    preference_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    
    # NOVO
    daily_credit_logs: List[DailyCreditLogResponse] = []
    
    class Config:
        from_attributes = True

class PixPaymentResponse(BaseModel):
    """Resposta específica para pagamento PIX"""
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
    credits_remaining: Optional[int] = None  # NOVO

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
    created_at: datetime = datetime.now()

# ==============================================
# STATISTICS & DASHBOARD SCHEMAS (ATUALIZADOS)
# ==============================================

class DashboardStats(BaseModel):
    total_analyses: int
    analyses_today: int
    ai_used_count: int
    total_users: int
    recent_analyses: List[Dict[str, Any]] = []
    
    # NOVOS CAMPOS
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
    uploaded_at: datetime = datetime.now()

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
    timestamp: datetime = datetime.now()

class ValidationError(BaseModel):
    field: str
    message: str
    value: Optional[Any] = None

# ==============================================
# SYSTEM SCHEMAS
# ==============================================

class HealthCheck(BaseModel):
    status: str
    timestamp: datetime
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