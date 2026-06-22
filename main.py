# main.py (na raiz) - VERSÃO FINAL ATUALIZADA
# 🔥 CAPTCHA REMOVIDO COMPLETAMENTE
# 🔥 TOKENS OTIMIZADOS (15min access, 7 dias refresh, jti, blacklist com TTL)
# 🔥 ML PIPELINE INTEGRADO
# 🔥 SUPORTE A MÚLTIPLOS ARQUIVOS
# 🔥 SISTEMA DE CRÉDITOS COMPLETO
# 🔥 PREÇO FUNDADOR VITALÍCIO

import sys
import os
from pathlib import Path
from datetime import datetime
import secrets
import string
from sqlalchemy.orm import Session
import time
import asyncio

print("=" * 70)
print("🚀 AUTOANALYTICS v3.3 - GOOGLE GEMINI (SEM CAPTCHA)")
print("🔐 Tokens: 15min access | 7 dias refresh | jti | blacklist com TTL")
print("💰 Créditos: 3 grátis | 1/dia premium | limite 3")
print("🎯 Preço Fundador: R$ 97,00 (100 vagas) | Vitalício")
print("🤖 ML Pipeline: RandomForest + AutoML + Boosting")
print("📁 Upload: até 3 arquivos | 200KB cada")
print("=" * 70)

# Configurar paths
PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

print(f"📂 Raiz do projeto: {PROJECT_ROOT}")
print(f"📂 Pasta backend: {BACKEND_DIR}")
print(f"🌐 Pasta frontend: {FRONTEND_DIR}")

if not BACKEND_DIR.exists():
    print(f"❌ ERRO: Pasta 'backend' não encontrada!")
    sys.exit(1)

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

print(f"🔧 Python path configurado")

# ==============================================
# CONFIGURAÇÕES
# ==============================================
class Settings:
    APP_NAME = "AutoAnalytics"
    VERSION = "3.3.0"
    
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    PORT = int(os.getenv("PORT", "8000"))
    
    BASE_DIR = str(BACKEND_DIR)
    TEMP_DIR = str(BACKEND_DIR / "temp")
    OUTPUT_DIR = str(BACKEND_DIR / "outputs")
    MODELS_DIR = str(BACKEND_DIR / "ml" / "models")
    DATA_DIR = str(BACKEND_DIR / "data")
    
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "204800"))  # 200KB
    MAX_FILES_PER_BATCH = 3
    ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls"]
    
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_ENABLED = os.getenv("GEMINI_ENABLED", "true").lower() == "true"
    
    # 🔥 JWT - CONFIGURAÇÕES OTIMIZADAS
    SECRET_KEY = os.getenv("SECRET_KEY", "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64)))
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))  # 15 minutos
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))       # 7 dias
    
    # 🔥 ARGON2 - HASH DE SENHA
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536
    ARGON2_PARALLELISM = 4
    
    # 🔥 CAPTCHA DESABILITADO
    DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
    
    # 🔥 CORS
    CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://localhost:3000,http://localhost:5173,https://autoanalytics.site")
    CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",")]
    
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
    }
    
    # 🔥 MERCADO PAGO
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
    MP_ENVIRONMENT = os.getenv("MP_ENVIRONMENT", "production")
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
    
    # 🔥 REDIS
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    # 🔥 DATABASE
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/autoanalytics.db")
    
    # 🔥 ML CONFIG
    ML_MODEL_CACHE_ENABLED = os.getenv("ML_MODEL_CACHE_ENABLED", "true").lower() == "true"
    ML_MAX_FILE_SIZE_KB = int(os.getenv("ML_MAX_FILE_SIZE_KB", "200"))
    ML_MAX_FILES_PER_BATCH = int(os.getenv("ML_MAX_FILES_PER_BATCH", "3"))
    
    # 🔥 CRÉDITOS
    MAX_CREDITS_BALANCE = 3
    INITIAL_FREE_CREDITS = 3
    PROMOTIONAL_PRICE = 97.00
    REGULAR_PRICE = 149.90
    TOTAL_PROMOTIONAL_SLOTS = 100
    DAYS_PREMIUM = 30

settings = Settings()

# Criar diretórios
print("\n📁 Verificando diretórios...")
for dir_path in [settings.TEMP_DIR, settings.OUTPUT_DIR, settings.MODELS_DIR, settings.DATA_DIR]:
    os.makedirs(dir_path, exist_ok=True)
    print(f"   ✅ {dir_path}")

# Verificar frontend
print("\n🌐 Verificando frontend...")
frontend_available = False
login_available = False
dashboard_available = False
planos_available = False
checkout_available = False

if FRONTEND_DIR.exists():
    print(f"   ✅ Frontend encontrado em: {FRONTEND_DIR}")
    
    index_html = FRONTEND_DIR / "index.html"
    login_html = FRONTEND_DIR / "login.html"
    planos_html = FRONTEND_DIR / "planos.html"
    checkout_html = FRONTEND_DIR / "checkout.html"
    
    if index_html.exists():
        dashboard_available = True
        frontend_available = True
        print(f"   ✅ index.html (dashboard)")
    else:
        print(f"   ❌ index.html não encontrado em {index_html}")
    
    if login_html.exists():
        login_available = True
        frontend_available = True
        print(f"   ✅ login.html")
    else:
        print(f"   ❌ login.html não encontrado em {login_html}")
    
    if planos_html.exists():
        planos_available = True
        frontend_available = True
        print(f"   ✅ planos.html")
    else:
        print(f"   ⚠️ planos.html não encontrado em {planos_html}")
    
    if checkout_html.exists():
        checkout_available = True
        frontend_available = True
        print(f"   ✅ checkout.html")
    else:
        print(f"   ⚠️ checkout.html não encontrado em {checkout_html}")
    
    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        js_files = [
            "auth.js", "app.js", "dashboard.js", "payment.js", 
            "pow-client.js", "pow-worker.js"
        ]
        for js_file in js_files:
            if (js_dir / js_file).exists():
                print(f"   ✅ js/{js_file}")
            else:
                print(f"   ⚠️ js/{js_file} não encontrado")
    else:
        print(f"   ❌ Pasta js não encontrada em {js_dir}")
        os.makedirs(js_dir, exist_ok=True)
        print(f"   ✅ Pasta js criada")
    
    css_dir = FRONTEND_DIR / "css"
    if css_dir.exists():
        if (css_dir / "style.css").exists():
            print(f"   ✅ css/style.css")
        else:
            print(f"   ⚠️ css/style.css não encontrado")
    else:
        print(f"   ⚠️ Pasta css não encontrada")
        os.makedirs(css_dir, exist_ok=True)
        print(f"   ✅ Pasta css criada")
else:
    print(f"   ❌ Frontend NÃO encontrado em: {FRONTEND_DIR}")
    os.makedirs(FRONTEND_DIR / "js", exist_ok=True)
    os.makedirs(FRONTEND_DIR / "css", exist_ok=True)

# ==============================================
# IMPORTAR FASTAPI
# ==============================================
print("\n🔧 Importando FastAPI...")

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, HTMLResponse
    import uvicorn
    print("   ✅ FastAPI importado")
except ImportError as e:
    print(f"   ❌ Erro: {e}")
    sys.exit(1)

# ==============================================
# INICIALIZAR APP FASTAPI
# ==============================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="AutoAnalytics - IA para Oficinas Mecânicas (SEM CAPTCHA)",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

app.router.redirect_slashes = False

# ==============================================
# MIDDLEWARE DE LOGGING
# ==============================================
print("\n📊 Configurando middleware de observabilidade...")

try:
    from backend.observability.sentinel import LoggingMiddleware, get_metrics_collector
    metrics_collector = get_metrics_collector()
    app.add_middleware(LoggingMiddleware, metrics=metrics_collector)
    print("   ✅ LoggingMiddleware do Sentinel ativado")
except ImportError as e:
    print(f"   ⚠️ Sentinel não disponível: {e}")
except Exception as e:
    print(f"   ⚠️ Erro ao ativar Sentinel: {e}")

# ==============================================
# MIDDLEWARE CORS
# ==============================================
print("\n🔐 Configurando CORS...")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Auth-Required",
        "X-Redirect-To"
    ]
)
print(f"   ✅ CORS configurado para: {settings.CORS_ORIGINS}")

# ==============================================
# ROTAS AUXILIARES
# ==============================================
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return Response(status_code=204)

@app.get("/health", include_in_schema=False)
async def health_check_simple():
    return Response(content="healthy\n", media_type="text/plain", status_code=200)

# ==============================================
# MIDDLEWARE DE LOG MANUAL
# ==============================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    path = request.url.path
    method = request.method
    
    if not path.startswith('/static') and path not in ['/favicon.ico', '/.well-known/appspecific/com.chrome.devtools.json', '/health']:
        print(f"🌐 [{datetime.now().strftime('%H:%M:%S')}] {method} {path}")
    
    response = await call_next(request)
    
    if response.status_code == 404 and path.startswith('/static'):
        print(f"   ❌ ERRO 404 - Arquivo estático não encontrado: {path}")
        relative_path = path.replace('/static/', '')
        possible_paths = [
            FRONTEND_DIR / relative_path,
            FRONTEND_DIR / "js" / relative_path,
            FRONTEND_DIR / "css" / relative_path,
            FRONTEND_DIR / "assets" / relative_path,
        ]
        for p in possible_paths:
            if p.exists():
                print(f"      ✓ Arquivo encontrado em: {p}")
            else:
                print(f"      ✗ Não encontrado: {p}")
    
    if response.status_code >= 400 and not path.startswith('/static'):
        process_time = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   ⚠️ Status: {response.status_code} | Tempo: {process_time:.2f}ms")
    
    for header, value in settings.SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response

# ==============================================
# ARQUIVOS ESTÁTICOS
# ==============================================
if frontend_available:
    print("\n📁 Configurando arquivos estáticos...")
    
    static_dir = FRONTEND_DIR.absolute()
    print(f"   📂 Servindo arquivos estáticos de: {static_dir}")
    
    if static_dir.exists():
        try:
            app.mount("/static", StaticFiles(directory=str(static_dir), html=False), name="static")
            print(f"   ✅ Arquivos estáticos montados em /static")
            
            print(f"\n   📋 Arquivos disponíveis em /static:")
            for item in static_dir.iterdir():
                if item.is_dir():
                    print(f"      📁 {item.name}/")
                    for subitem in item.iterdir():
                        print(f"         📄 {subitem.name}")
                else:
                    print(f"      📄 {item.name}")
        except Exception as e:
            print(f"   ❌ Erro ao montar arquivos estáticos: {e}")
    else:
        print(f"   ❌ Diretório não encontrado: {static_dir}")
else:
    print("\n⚠️ Frontend não disponível, apenas API será servida")

# ==============================================
# ROTAS HTML - SEM CAPTCHA
# ==============================================
if frontend_available:
    print("\n🌐 Configurando rotas HTML...")
    
    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        from backend.security import jwt_manager
        
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):
            token = token.replace("Bearer ", "")
        
        if token:
            payload = await jwt_manager.verify_token(token, "access")
            if payload and dashboard_available:
                return FileResponse(str(FRONTEND_DIR / "index.html"))
        
        if login_available:
            return RedirectResponse(url="/login", status_code=302)
        
        return JSONResponse({"message": "AutoAnalytics API", "docs": "/api/docs"})
    
    @app.get("/login", include_in_schema=False)
    async def login_page(request: Request):
        from backend.security import jwt_manager
        
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):
            token = token.replace("Bearer ", "")
        
        if token:
            payload = await jwt_manager.verify_token(token, "access")
            if payload and dashboard_available:
                return RedirectResponse(url="/dashboard", status_code=302)
        
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        return JSONResponse({"error": "login.html não encontrado"}, status_code=404)
    
    @app.get("/dashboard", response_class=HTMLResponse)
    async def route_dashboard(request: Request):
        from backend.security import jwt_manager
        
        access_token = request.cookies.get("access_token")
        if access_token and access_token.startswith("Bearer "):
            access_token = access_token.replace("Bearer ", "")
        
        if not access_token:
            print(f"🔴 [DASHBOARD] Sem token - redirecionando para /login")
            return RedirectResponse(url="/login", status_code=303)
        
        try:
            payload = await jwt_manager.verify_token(access_token, "access")
            
            if not payload:
                print(f"🔴 [DASHBOARD] Token inválido - redirecionando para /login")
                return RedirectResponse(url="/login", status_code=303)
            
            if dashboard_available:
                file_path = FRONTEND_DIR / "index.html"
                if not file_path.exists():
                    print(f"❌ [DASHBOARD] index.html não encontrado em {file_path}")
                    return HTMLResponse(
                        content="<h1>Erro: index.html não encontrado</h1>",
                        status_code=404
                    )
                
                print(f"✅ [DASHBOARD] Token válido - entregando dashboard")
                return HTMLResponse(content=file_path.read_text(encoding="utf-8"))
            else:
                return HTMLResponse(
                    content="<h1>Erro: Dashboard não disponível</h1>",
                    status_code=404
                )
                
        except Exception as e:
            print(f"❌ [DASHBOARD] Erro: {e} - redirecionando para /login")
            return RedirectResponse(url="/login", status_code=303)
    
    @app.get("/planos", response_class=HTMLResponse)
    async def route_planos(request: Request):
        from backend.security import jwt_manager
        
        access_token = request.cookies.get("access_token")
        if access_token and access_token.startswith("Bearer "):
            access_token = access_token.replace("Bearer ", "")
        
        if not access_token:
            print(f"🔴 [PLANOS] Sem token - redirecionando para /login")
            return RedirectResponse(url="/login", status_code=303)
        
        try:
            payload = await jwt_manager.verify_token(access_token, "access")
            
            if not payload:
                print(f"🔴 [PLANOS] Token inválido - redirecionando para /login")
                return RedirectResponse(url="/login", status_code=303)
            
            if planos_available:
                file_path = FRONTEND_DIR / "planos.html"
                if not file_path.exists():
                    print(f"❌ [PLANOS] planos.html não encontrado em {file_path}")
                    return HTMLResponse(
                        content="<h1>Erro: planos.html não encontrado</h1>",
                        status_code=404
                    )
                
                print(f"✅ [PLANOS] Token válido - entregando planos")
                return HTMLResponse(content=file_path.read_text(encoding="utf-8"))
            else:
                return HTMLResponse(
                    content="<h1>Erro: Página de planos não disponível</h1>",
                    status_code=404
                )
                
        except Exception as e:
            print(f"❌ [PLANOS] Erro: {e} - redirecionando para /login")
            return RedirectResponse(url="/login", status_code=303)
    
    @app.get("/checkout", response_class=HTMLResponse)
    async def route_checkout(request: Request):
        from backend.security import jwt_manager
        
        access_token = request.cookies.get("access_token")
        if access_token and access_token.startswith("Bearer "):
            access_token = access_token.replace("Bearer ", "")
        
        if not access_token:
            print(f"🔴 [CHECKOUT] Sem token - redirecionando para /login")
            return RedirectResponse(url="/login", status_code=303)
        
        try:
            payload = await jwt_manager.verify_token(access_token, "access")
            
            if not payload:
                print(f"🔴 [CHECKOUT] Token inválido - redirecionando para /login")
                return RedirectResponse(url="/login", status_code=303)
            
            if checkout_available:
                file_path = FRONTEND_DIR / "checkout.html"
                if not file_path.exists():
                    print(f"❌ [CHECKOUT] checkout.html não encontrado em {file_path}")
                    return HTMLResponse(
                        content="<h1>Erro: checkout.html não encontrado</h1>",
                        status_code=404
                    )
                
                print(f"✅ [CHECKOUT] Token válido - entregando checkout")
                return HTMLResponse(content=file_path.read_text(encoding="utf-8"))
            else:
                return HTMLResponse(
                    content="<h1>Erro: Página de checkout não disponível</h1>",
                    status_code=404
                )
                
        except Exception as e:
            print(f"❌ [CHECKOUT] Erro: {e} - redirecionando para /login")
            return RedirectResponse(url="/login", status_code=303)
    
    # Redirecionamentos
    @app.get("/planos.html", include_in_schema=False)
    async def redirect_planos_html():
        return RedirectResponse(url="/planos", status_code=301)
    
    @app.get("/dashboard.html", include_in_schema=False)
    async def redirect_dashboard_html():
        return RedirectResponse(url="/dashboard", status_code=301)
    
    @app.get("/login.html", include_in_schema=False)
    async def redirect_login_html():
        return RedirectResponse(url="/login", status_code=301)
    
    @app.get("/checkout.html", include_in_schema=False)
    async def redirect_checkout_html():
        return RedirectResponse(url="/checkout", status_code=301)
    
    print("   ✅ Rotas HTML: /, /login, /dashboard, /planos, /checkout")

# ==============================================
# CARREGAR MÓDULOS DO BACKEND
# ==============================================
print("\n📦 Carregando módulos do backend...")

if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY in ["", "opcional", "sua_chave_aqui"]:
    print("   ⚠️ GEMINI_API_KEY não configurada!")
else:
    print(f"   ✅ Gemini API Key configurada (modelo: {settings.GEMINI_MODEL})")

db_path = Path(settings.DATABASE_URL.replace("sqlite:///", "")) if settings.DATABASE_URL.startswith("sqlite") else PROJECT_ROOT / "autoanalytics.db"
print(f"   🗄️ Banco de dados: {db_path}")

try:
    from backend.config import settings as backend_settings
    for key, value in settings.__dict__.items():
        if not key.startswith('_'):
            try:
                setattr(backend_settings, key, value)
            except Exception as e:
                print(f"   ⚠️ Não foi possível setar {key}: {e}")
    print("   ✅ Configurações sincronizadas com backend.config")
except ImportError:
    print("   ⚠️ backend.config.settings não encontrado")
    backend_settings = settings

try:
    from backend.database import engine, Base, create_tables, SessionLocal, get_db
    create_tables()
    print("   ✅ Tabelas criadas/verificadas")
except ImportError as e:
    print(f"   ❌ Erro ao importar database: {e}")
    sys.exit(1)

# 🔥 IMPORTANDO SEGURANÇA
try:
    from backend.security import (
        hasher, jwt_manager, rate_limiter,
        get_current_user, get_current_active_user, get_current_admin_user,
        set_auth_cookies, clear_auth_cookies
    )
    from backend.models import User, Analysis, PromotionControl, Payment, DailyCreditLog
    print("   ✅ Módulos de segurança carregados (SEM CAPTCHA)")
    print("   🔐 Tokens: 15min access | 7 dias refresh | jti | blacklist com TTL")
except ImportError as e:
    print(f"   ❌ Erro ao importar security: {e}")
    sys.exit(1)

# 🔥 IMPORTAR CRUD
try:
    from backend import crud
    print(f"   ✅ CRUD carregado (MAX_CREDITS_PREMIUM = {crud.MAX_CREDITS_PREMIUM})")
except ImportError as e:
    print(f"   ⚠️ CRUD não disponível: {e}")

# 🔥 IMPORTAR SERVIÇOS
try:
    from backend.services.daily_credits_service import DailyCreditsService
    print("   ✅ DailyCreditsService carregado")
except ImportError as e:
    print(f"   ⚠️ DailyCreditsService não disponível: {e}")
    class DailyCreditsService:
        def get_user_credit_status(self, db, user_id):
            return {"current_credits": 10, "streak_days": 0, "received_today": False, "can_receive_more": False}
        def check_and_add_daily_credit(self, db, user_id):
            return {"success": False, "credits_added": 0, "message": "Serviço indisponível"}
        def get_premium_summary(self, db, user_id):
            return {"has_premium": False, "credits": {"current_balance": 0}, "max_credits": 3}
    DailyCreditsService = DailyCreditsService

try:
    from backend.services.credits_consumer import (
        can_perform_analysis, consume_analysis_credit, get_credits_display
    )
    print("   ✅ CreditsConsumer carregado")
except ImportError as e:
    print(f"   ⚠️ CreditsConsumer não disponível: {e}")

# 🔥 IMPORTAR ML PIPELINE
try:
    from backend.ml.preprocessing import pipeline, process_file_content
    print("   ✅ ML Pipeline carregado")
    print(f"      📊 Modelo: {pipeline.model_source if hasattr(pipeline, 'model_source') else 'desconhecido'}")
    print(f"      🔤 Encoding: automático (chardet)")
    print(f"      💾 Cache: TTL 60s")
except ImportError as e:
    print(f"   ⚠️ ML Pipeline não disponível: {e}")
    # Criar pipeline mock
    class MockPipeline:
        def __init__(self):
            self.model_source = "placeholder"
            self.is_initialized = False
        async def initialize(self):
            self.is_initialized = True
            return True
        async def predict(self, df, filename=None):
            return {"success": False, "error": "ML não disponível"}
        def get_status(self):
            return {"initialized": False, "model_source": "placeholder"}
        def get_encoding_stats(self):
            return {"encodings": {}, "total_success": 0}
    pipeline = MockPipeline()
    
    async def process_file_content(content, filename):
        return {"success": False, "error": "ML não disponível"}

AUTH_ENABLED = True
print("   ✅ Autenticação habilitada")

time.sleep(1)

# ==============================================
# REGISTRO DE ROTAS
# ==============================================
print("\n📦 Registrando rotas dos routers...")

try:
    from backend.api.auth_routes import router as auth_router
    from backend.api.auth import router as registration_router
    
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(registration_router, prefix="/api/auth")
    
    print("   ✅ Rotas AUTH:")
    print("      POST   /api/auth/login     ← 🔥 SEM CAPTCHA")
    print("      POST   /api/auth/register  ← 🔥 SEM CAPTCHA")
    print("      POST   /api/auth/refresh   ← 🔥 RENOVA TOKEN")
    print("      POST   /api/auth/logout    ← 🔥 REVOGA TOKEN")
    print("      GET    /api/auth/check-token")
    print("      GET    /api/auth/me")
    print("   ❌ CAPTCHA: REMOVIDO COMPLETAMENTE")
    
    try:
        from backend.api.payment_routes import router as payment_router
        app.include_router(payment_router, prefix="/api")
        print("   ✅ Rotas PAYMENT:")
        print("      GET    /api/payments/plans")
        print("      GET    /api/payments/balance")
        print("      GET    /api/payments/promotion-status")
        print("      POST   /api/payments/create-pix")
        print("      GET    /api/payments/pix-qrcode/{id}")
        print("      GET    /api/payments/status/{id}")
        print("      POST   /api/payments/cancel/{id}")
        print("      GET    /api/payments/subscription-status")
        print("      POST   /api/payments/premium/check-daily")
        print("      POST   /api/payments/webhook")
        print("      💰 Preço Fundador: R$ 97,00 (100 vagas)")
        print("      🔒 Preço Vitalício: para quem comprou na promoção")
    except ImportError as e:
        print(f"   ⚠️ Payment routes não disponível: {e}")
    
    try:
        from backend.api.upload_routes import router as upload_router
        app.include_router(upload_router, prefix="/api")
        print("   ✅ Rotas UPLOAD:")
        print("      POST   /api/upload-auto (até 3 arquivos)")
        print("      GET    /api/status/{process_id}")
        print("      GET    /api/analyses/history")
        print("      GET    /api/analysis/result/{process_id}")
        print("      📁 ML Pipeline: encodings automático")
        print("      💰 Consumo de crédito após análise")
    except ImportError as e:
        print(f"   ⚠️ Upload routes não disponível: {e}")
    
    try:
        from backend.api.routes import router as gemini_router
        app.include_router(gemini_router, prefix="/api")
        print("   ✅ Rotas GEMINI: /api/upload, /api/health, /api/test, /api/results, /api/status, /api/admin/diagnostics")
    except ImportError as e:
        print(f"   ⚠️ Gemini routes não disponível: {e}")
    
    try:
        from backend.api.pow_routes import router as pow_router
        app.include_router(pow_router, prefix="/api")
        print("   ✅ Rotas POW:")
        print("      GET    /api/pow/challenge")
        print("      POST   /api/pow/verify")
        print("      GET    /api/pow/stats")
        print("      GET    /api/pow/health")
        print("      🔒 SHA-256 Anti-Bot")
        print("      ⏰ Challenge TTL: 120s")
    except ImportError as e:
        print(f"   ⚠️ POW não disponível: {e}")
    
    print("   ✅ TODOS OS ROUTERS REGISTRADOS!")
    
except Exception as e:
    print(f"   ❌ Erro ao registrar routers: {e}")
    import traceback
    traceback.print_exc()

# ==============================================
# ROTA HEALTH DETALHADA
# ==============================================
@app.get("/api/health", tags=["system"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.VERSION,
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]),
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "captcha_enabled": False,
        "auth": {
            "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
            "algorithm": settings.ALGORITHM,
            "blacklist": "Redis com TTL"
        },
        "credits": {
            "max_balance": settings.MAX_CREDITS_BALANCE,
            "initial_free": settings.INITIAL_FREE_CREDITS,
            "premium_daily": 1
        },
        "promotion": {
            "price": settings.PROMOTIONAL_PRICE,
            "regular_price": settings.REGULAR_PRICE,
            "total_slots": settings.TOTAL_PROMOTIONAL_SLOTS,
            "vitalicio": True
        },
        "ml_pipeline": {
            "available": pipeline.is_initialized if hasattr(pipeline, 'is_initialized') else False,
            "model_source": pipeline.model_source if hasattr(pipeline, 'model_source') else "unknown",
            "encoding": "auto (chardet)",
            "cache": "TTL 60s"
        },
        "frontend": {
            "available": frontend_available, 
            "path": str(FRONTEND_DIR.absolute())
        },
        "max_file_size_kb": settings.MAX_FILE_SIZE // 1024,
        "max_files_per_batch": settings.MAX_FILES_PER_BATCH,
        "timezone": "America/Sao_Paulo (UTC-3)"
    }

# ==============================================
# FUNÇÃO PARA INICIALIZAR PROMOÇÃO
# ==============================================
def init_promotion(db: Session):
    from backend.models import PromotionControl
    promo = db.query(PromotionControl).first()
    if not promo:
        promo = PromotionControl(
            total_slots=settings.TOTAL_PROMOTIONAL_SLOTS,
            used_slots=0,
            promotional_price=settings.PROMOTIONAL_PRICE,
            regular_price=settings.REGULAR_PRICE,
            is_active=True
        )
        db.add(promo)
        db.commit()
        print(f"   ✅ Promoção Bronze inicializada: {settings.TOTAL_PROMOTIONAL_SLOTS} vagas a R$ {settings.PROMOTIONAL_PRICE}")
    else:
        remaining = promo.get_remaining_slots()
        print(f"   ✅ Promoção Bronze: {remaining}/{settings.TOTAL_PROMOTIONAL_SLOTS} vagas restantes")
        if remaining <= 0:
            print(f"   ⚠️ PROMOÇÃO ESGOTADA! Preço cheio: R$ {settings.REGULAR_PRICE}")

# ==============================================
# EVENTO DE STARTUP
# ==============================================
@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 70)
    print("🚀 INICIALIZANDO SISTEMA...")
    print("=" * 70)
    
    try:
        from backend.observability.sentinel import startup_webhook
        await startup_webhook()
        print("   ✅ Sentinel (observabilidade) inicializado")
    except ImportError as e:
        print(f"   ⚠️ Sentinel não disponível: {e}")
    except Exception as e:
        print(f"   ⚠️ Erro ao iniciar Sentinel: {e}")
    
    try:
        db = SessionLocal()
        init_promotion(db)
        db.close()
    except Exception as e:
        print(f"   ⚠️ Erro ao inicializar promoção: {e}")
    
    # 🔥 INICIALIZAR ML PIPELINE
    try:
        if hasattr(pipeline, 'initialize'):
            await pipeline.initialize()
            print("   ✅ ML Pipeline inicializado")
            if hasattr(pipeline, 'get_status'):
                status = pipeline.get_status()
                print(f"      📊 Modelo: {status.get('model_source', 'unknown')}")
                print(f"      💾 Cache: {status.get('cache_size', 0)} itens")
    except Exception as e:
        print(f"   ⚠️ Erro ao inicializar ML Pipeline: {e}")
    
    # 🔥 INICIALIZAR REDIS (opcional)
    try:
        from backend.security import jwt_manager
        await jwt_manager.init_redis()
        print("   ✅ Redis inicializado (JWT blacklist)")
    except Exception as e:
        print(f"   ⚠️ Erro ao inicializar Redis: {e}")
    
    # ❌ SEM CAPTCHA
    print("   ❌ CAPTCHA: REMOVIDO COMPLETAMENTE")
    
    gemini_status = "✅" if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"] else "❌"
    frontend_status = "✅" if frontend_available else "❌"
    ml_status = "✅" if (hasattr(pipeline, 'is_initialized') and pipeline.is_initialized) else "⚠️"
    
    print(f"""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║     🎉 {settings.APP_NAME} v{settings.VERSION} INICIADO!                         ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🌍 Ambiente: {settings.ENVIRONMENT.upper():<50} ║
    ║  🤖 Gemini: {gemini_status} | 🔢 CAPTCHA: ❌ REMOVIDO                      ║
    ║  🤖 ML Pipeline: {ml_status} | 📊 Observabilidade: ✅ ativa                ║
    ║  🌐 Frontend: {frontend_status}                                             ║
    ║  📁 Limite: {settings.MAX_FILE_SIZE // 1024}KB | {settings.MAX_FILES_PER_BATCH} arquivos/vez        ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  💰 CRÉDITOS:                                                               ║
    ║     Grátis: {settings.INITIAL_FREE_CREDITS} iniciais                                ║
    ║     Premium: 1/dia | Máximo: {settings.MAX_CREDITS_BALANCE} acumulados                  ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🎯 PREÇO FUNDADOR:                                                         ║
    ║     Promocional: R$ {settings.PROMOTIONAL_PRICE:.2f} ({settings.TOTAL_PROMOTIONAL_SLOTS} vagas)       ║
    ║     Regular: R$ {settings.REGULAR_PRICE:.2f}                                  ║
    ║     Vitalício: ✅ para quem comprar na promoção                            ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🔐 TOKENS:                                                                ║
    ║     Access Token: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutos                    ║
    ║     Refresh Token: {settings.REFRESH_TOKEN_EXPIRE_DAYS} dias                      ║
    ║     Algoritmo: {settings.ALGORITHM}                                          ║
    ║     Blacklist: Redis com TTL (fallback DB)                                 ║
    ║     jti: UUID único por token                                              ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🔗 Endpoints principais:                                                  ║
    ║     POST /api/auth/register  ← 🔥 SEM CAPTCHA                             ║
    ║     POST /api/auth/login     ← 🔥 SEM CAPTCHA                             ║
    ║     POST /api/auth/refresh   ← 🔥 RENOVA TOKEN                            ║
    ║     POST /api/auth/logout    ← 🔥 REVOGA TOKEN                            ║
    ║     POST /api/upload-auto (múltiplos arquivos)                            ║
    ║     POST /api/payments/create-pix (PIX real)                              ║
    ║     GET  /api/payments/promotion-status (vagas)                           ║
    ║     GET  /api/pow/challenge (PoW anti-bot)                                ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🌐 Páginas:                                                              ║
    ║     http://localhost:{settings.PORT}/                                     ║
    ║     http://localhost:{settings.PORT}/login                                ║
    ║     http://localhost:{settings.PORT}/dashboard                            ║
    ║     http://localhost:{settings.PORT}/planos                               ║
    ║     http://localhost:{settings.PORT}/checkout                             ║
    ║     http://localhost:{settings.PORT}/api/docs                             ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  📁 Frontend: {FRONTEND_DIR.absolute():<50} ║
    ║  🗄️  Database: {db_path}                                                 ║
    ║  🕐 Timezone: America/Sao_Paulo (UTC-3)                                  ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """)

# ==============================================
# EVENTO DE SHUTDOWN
# ==============================================
@app.on_event("shutdown")
async def shutdown_event():
    print("\n🛑 Desligando sistema...")
    
    try:
        from backend.observability.sentinel import shutdown_webhook
        await shutdown_webhook()
        print("   ✅ Sentinel finalizado com sucesso")
    except ImportError as e:
        print(f"   ⚠️ Sentinel não disponível: {e}")
    except Exception as e:
        print(f"   ⚠️ Erro ao finalizar Sentinel: {e}")
    
    # 🔥 LIMPAR CACHE DO ML
    try:
        if hasattr(pipeline, 'clear_cache'):
            pipeline.clear_cache()
            print("   ✅ Cache do ML Pipeline limpo")
    except Exception as e:
        print(f"   ⚠️ Erro ao limpar cache ML: {e}")
    
    print("   ❌ CAPTCHA: REMOVIDO")
    print("👋 Sistema desligado!")

# ==============================================
# EXCEPTION HANDLERS
# ==============================================
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    path = request.url.path
    if path.startswith('/api/'):
        return JSONResponse(status_code=404, content={"error": "Endpoint não encontrado", "path": path})
    return JSONResponse(status_code=404, content={"error": "Página não encontrada"})

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    path = request.url.path
    if exc.status_code == 401 and not path.startswith('/api/'):
        return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

# ==============================================
# MAIN
# ==============================================
if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 IA: Google Gemini")
    print(f"🤖 ML: RandomForest + AutoML + Boosting")
    print(f"🔐 Access Token: {settings.ACCESS_TOKEN_EXPIRE_MINUTES}min")
    print(f"🔐 Refresh Token: {settings.REFRESH_TOKEN_EXPIRE_DAYS}dias")
    print(f"🔢 CAPTCHA: ❌ REMOVIDO")
    print(f"💰 Créditos: {settings.INITIAL_FREE_CREDITS} grátis | {settings.MAX_CREDITS_BALANCE} máx")
    print(f"🎯 Preço Fundador: R$ {settings.PROMOTIONAL_PRICE} ({settings.TOTAL_PROMOTIONAL_SLOTS} vagas)")
    print(f"📊 Observabilidade: ✅ ativa")
    print(f"📁 Limite: {settings.MAX_FILE_SIZE // 1024}KB | {settings.MAX_FILES_PER_BATCH} arquivos")
    print(f"🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning"
    )