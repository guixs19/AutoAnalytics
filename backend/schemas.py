# backend/schemas.py - VERSÃO COMPLETA E FUNCIONAL
from pydantic import BaseModel, EmailStr
from datetime import datetime
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

# ==============================================
# USER SCHEMAS
# ==============================================

class UserBase(BaseModel):
    email: EmailStr
    name: str
    workshop_name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole = UserRole.USER

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

# ==============================================
# TOKEN SCHEMAS
# ==============================================

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    user_name: str
    user_email: str
    workshop_name: Optional[str]
    role: UserRole

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class TokenRefresh(BaseModel):
    refresh_token: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

# ==============================================
# ADMIN SCHEMAS
# ==============================================

class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    workshop_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

class UserStats(BaseModel):
    total_users: int
    active_users: int
    admins: int
    managers: int
    users: int

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
# STATISTICS & DASHBOARD SCHEMAS
# ==============================================

class DashboardStats(BaseModel):
    total_analyses: int
    analyses_today: int
    ai_used_count: int
    total_users: int
    recent_analyses: List[Dict[str, Any]] = []

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