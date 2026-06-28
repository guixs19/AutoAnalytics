# main.py (na raiz) - VERSÃO PRODUÇÃO v4.3 (CORREÇÃO ROTA PLANOS)
"""
AutoAnalytics - Servidor Principal
================================================================================
🔥 CORREÇÕES v4.3:
- ✅ CORRIGIDO: Rota /planos sem fallback mascarado para index.html
- ✅ CORRIGIDO: Logs detalhados para identificar problemas de autenticação
- ✅ CORRIGIDO: Redirecionamento 302 com logs claros
- ✅ MELHORADO: Tratamento de erro 404/500 na rota planos
================================================================================
"""
from sqlalchemy.orm import Session
import sys
import os
import time
import asyncio
import secrets
import string
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Callable

# ==============================================
# 1. PATHS E CONFIGURAÇÃO INICIAL
# ==============================================

PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Configurar paths antes de qualquer import
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

print("=" * 75)
print("🚀 AUTOANALYTICS v4.3 - PRODUÇÃO")
print("=" * 75)
print(f"📂 Raiz: {PROJECT_ROOT}")
print(f"📂 Backend: {BACKEND_DIR}")
print(f"🌐 Frontend: {FRONTEND_DIR}")

# ==============================================
# 2. SETTINGS
# ==============================================

class Settings:
    """Configurações centralizadas da aplicação"""
    
    # App
    APP_NAME = "AutoAnalytics"
    VERSION = "4.3.0"
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    PORT = int(os.getenv("PORT", "8000"))
    
    # Diretórios
    BASE_DIR = str(BACKEND_DIR)
    TEMP_DIR = str(BACKEND_DIR / "temp")
    OUTPUT_DIR = str(BACKEND_DIR / "outputs")
    MODELS_DIR = str(BACKEND_DIR / "ml" / "models")
    DATA_DIR = str(BACKEND_DIR / "data")
    
    # Upload
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "204800"))
    MAX_FILES_PER_BATCH = 3
    ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls"]
    
    # Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_ENABLED = os.getenv("GEMINI_ENABLED", "true").lower() == "true"
    
    # JWT
    SECRET_KEY = os.getenv("SECRET_KEY", "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64)))
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Argon2
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536
    ARGON2_PARALLELISM = 4
    
    # CORS
    CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://localhost:3000,http://localhost:5173,https://autoanalytics.site")
    CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",")]
    
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
    }
    
    # Mercado Pago
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
    MP_ENVIRONMENT = os.getenv("MP_ENVIRONMENT", "production")
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
    
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/autoanalytics.db")
    
    # ML
    ML_MODEL_CACHE_ENABLED = os.getenv("ML_MODEL_CACHE_ENABLED", "true").lower() == "true"
    ML_MAX_FILE_SIZE_KB = int(os.getenv("ML_MAX_FILE_SIZE_KB", "200"))
    ML_MAX_FILES_PER_BATCH = int(os.getenv("ML_MAX_FILES_PER_BATCH", "3"))
    
    # Créditos
    MAX_CREDITS_BALANCE = 3
    INITIAL_FREE_CREDITS = 3
    PROMOTIONAL_PRICE = 97.00
    REGULAR_PRICE = 149.90
    TOTAL_PROMOTIONAL_SLOTS = 100
    DAYS_PREMIUM = 30

settings = Settings()

# ==============================================
# 3. CRIAÇÃO DE DIRETÓRIOS
# ==============================================

def create_directories() -> None:
    """Cria todos os diretórios necessários"""
    dirs = [
        settings.TEMP_DIR, 
        settings.OUTPUT_DIR, 
        settings.MODELS_DIR, 
        settings.DATA_DIR
    ]
    for dir_path in dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            print(f"   ✅ {dir_path}")
        except Exception as e:
            print(f"   ❌ Erro ao criar {dir_path}: {e}")

print("\n📁 Criando diretórios...")
create_directories()

# ==============================================
# 4. VERIFICAÇÃO DO FRONTEND
# ==============================================

def check_frontend() -> Dict[str, bool]:
    """Verifica quais arquivos do frontend estão disponíveis"""
    result = {
        "available": False,
        "login": False,
        "dashboard": False,
        "planos": False,
        "checkout": False,
        "js": False
    }
    
    if not FRONTEND_DIR.exists():
        print(f"   ❌ Frontend não encontrado em: {FRONTEND_DIR}")
        return result
    
    print(f"   ✅ Frontend encontrado em: {FRONTEND_DIR}")
    result["available"] = True
    
    html_files = {
        "login": FRONTEND_DIR / "login.html",
        "dashboard": FRONTEND_DIR / "index.html",
        "planos": FRONTEND_DIR / "planos.html",
        "checkout": FRONTEND_DIR / "checkout.html"
    }
    
    for name, path in html_files.items():
        if path.exists():
            result[name] = True
            print(f"   ✅ {path.name}")
        else:
            print(f"   ⚠️ {path.name} não encontrado")
    
    # Verificar JS
    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        result["js"] = True
        js_files = ["auth.js", "app.js", "dashboard.js", "payment.js", "pow-client.js"]
        for js_file in js_files:
            if (js_dir / js_file).exists():
                print(f"   ✅ js/{js_file}")
            else:
                print(f"   ⚠️ js/{js_file} não encontrado")
    else:
        os.makedirs(js_dir, exist_ok=True)
        print(f"   ✅ Pasta js criada")
    
    return result

print("\n🌐 Verificando frontend...")
frontend_status = check_frontend()

# ==============================================
# 5. IMPORTAÇÃO FASTAPI
# ==============================================

print("\n🔧 Importando FastAPI...")

try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, HTMLResponse
    import uvicorn
    print("   ✅ FastAPI importado")
except ImportError as e:
    print(f"   ❌ Erro ao importar FastAPI: {e}")
    print("   💡 Execute: pip install fastapi uvicorn")
    sys.exit(1)

# ==============================================
# 6. APP FASTAPI
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
# 7. MIDDLEWARES
# ==============================================

print("\n📊 Configurando middlewares...")

# 7.1 Observabilidade
try:
    from backend.observability.sentinel import LoggingMiddleware, get_metrics_collector
    metrics_collector = get_metrics_collector()
    app.add_middleware(LoggingMiddleware, metrics=metrics_collector)
    print("   ✅ LoggingMiddleware ativado")
except ImportError:
    print("   ⚠️ Sentinel não disponível")
except Exception as e:
    print(f"   ⚠️ Erro ao ativar Sentinel: {e}")

# 7.2 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Auth-Required", "X-Redirect-To"]
)
print(f"   ✅ CORS: {len(settings.CORS_ORIGINS)} origens permitidas")

# 7.3 Log de requisições
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware para log de requisições HTTP"""
    start_time = datetime.now()
    path = request.url.path
    method = request.method
    
    if not path.startswith('/static') and path not in ['/favicon.ico', '/health']:
        print(f"🌐 [{start_time.strftime('%H:%M:%S')}] {method} {path}")
    
    try:
        response = await call_next(request)
    except Exception as e:
        print(f"   ❌ Erro na requisição: {e}")
        raise
    
    if response.status_code >= 400 and not path.startswith('/static'):
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   ⚠️ {response.status_code} | {elapsed:.2f}ms")
    
    for header, value in settings.SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response

# ==============================================
# 8. ARQUIVOS ESTÁTICOS
# ==============================================

if frontend_status["available"]:
    print("\n📁 Configurando arquivos estáticos...")
    static_dir = FRONTEND_DIR.absolute()
    
    if static_dir.exists():
        try:
            app.mount("/static", StaticFiles(directory=str(static_dir), html=False), name="static")
            print(f"   ✅ /static → {static_dir}")
        except Exception as e:
            print(f"   ❌ Erro ao montar /static: {e}")
    else:
        print(f"   ❌ Diretório não encontrado: {static_dir}")

# ==============================================
# 9. ROTAS AUXILIARES
# ==============================================

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/health", include_in_schema=False)
async def health_check_simple():
    return Response(content="healthy\n", media_type="text/plain", status_code=200)

# ==============================================
# 10. 🔥 ROTAS HTML - CORRIGIDAS
# ==============================================

print("\n🌐 Configurando rotas HTML...")

def serve_html_page(filename: str, fallback: Optional[str] = None) -> HTMLResponse:
    """
    Serve um arquivo HTML do diretório frontend
    """
    file_path = FRONTEND_DIR / filename
    if file_path.exists():
        try:
            content = file_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content, status_code=200)
        except Exception as e:
            print(f"   ❌ Erro ao ler {filename}: {e}")
    
    if fallback:
        fallback_path = FRONTEND_DIR / fallback
        if fallback_path.exists():
            try:
                content = fallback_path.read_text(encoding="utf-8")
                return HTMLResponse(content=content, status_code=200)
            except Exception as e:
                print(f"   ❌ Erro ao ler fallback: {e}")
    
    return HTMLResponse(content=f"<h1>Página não encontrada</h1><p>{filename} não disponível</p>", status_code=404)

# ==============================================
# 🔥 VERIFICAÇÃO DE TOKEN (FUNÇÃO AUXILIAR)
# ==============================================

async def verify_token_from_request(request: Request) -> Optional[Dict]:
    """Verifica token JWT da requisição (cookies ou header)"""
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    if not token:
        # 🔥 Log para debug
        print(f"   ⚠️ Token não encontrado em cookies nem headers")
        return None
    
    try:
        from backend.security import jwt_manager
        return await jwt_manager.verify_token(token, "access")
    except ImportError:
        print(f"   ⚠️ jwt_manager não disponível")
        return None
    except Exception as e:
        print(f"   ⚠️ Erro ao verificar token: {e}")
        return None

# ==============================================
# 🔥 ROTAS HTML PRINCIPAIS
# ==============================================

# 1. Página de Login
@app.get("/login", include_in_schema=False)
async def get_login_page(request: Request):
    """Serve a página de login"""
    payload = await verify_token_from_request(request)
    if payload and frontend_status["dashboard"]:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    login_path = FRONTEND_DIR / "login.html"
    if login_path.exists():
        try:
            content = login_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler login.html: {e}")
    
    return JSONResponse(status_code=404, content={"error": "login.html não encontrado"})

# ==============================================
# 2. 🔥 Página de Planos - CORRIGIDA (SEM FALLBACK MASCARADO)
# ==============================================

@app.get("/planos", include_in_schema=False)
async def get_planos_page(request: Request):
    """
    Serve a página de planos
    🔥 CORRIGIDO: Sem fallback mascarado para index.html
    🔥 Logs detalhados para identificar problemas de autenticação
    """
    # 1. Verificar autenticação
    payload = await verify_token_from_request(request)
    
    if not payload:
        print("⚠️ [Auth] Token não encontrado na requisição para /planos. Redirecionando para login.")
        return RedirectResponse(url="/login", status_code=302)
    
    print(f"✅ [Auth] Token validado para /planos. Usuário: {payload.get('email', 'desconhecido')}")
    
    # 2. Tentar servir planos.html
    planos_path = FRONTEND_DIR / "planos.html"
    if planos_path.exists():
        try:
            content = planos_path.read_text(encoding="utf-8")
            print(f"✅ [Planos] planos.html servido com sucesso ({len(content)} bytes)")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"❌ [Planos] Erro ao ler planos.html: {e}")
            return JSONResponse(
                status_code=500, 
                content={"error": f"Erro ao ler página de planos: {str(e)}"}
            )
    
    # 3. Arquivo não encontrado
    print(f"❌ [Planos] Ficheiro não encontrado: {planos_path.absolute()}")
    return JSONResponse(
        status_code=404, 
        content={"error": "Página de planos (planos.html) não encontrada"}
    )

# 3. Página de Checkout
@app.get("/checkout", include_in_schema=False)
async def get_checkout_page(request: Request):
    """Serve a página de checkout"""
    payload = await verify_token_from_request(request)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    
    checkout_path = FRONTEND_DIR / "checkout.html"
    if checkout_path.exists():
        try:
            content = checkout_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler checkout.html: {e}")
    
    return JSONResponse(status_code=404, content={"error": "checkout.html não encontrado"})

# 4. Dashboard (Raiz - /dashboard)
@app.get("/dashboard", include_in_schema=False)
async def get_dashboard_page(request: Request):
    """Serve a página do dashboard (index.html)"""
    payload = await verify_token_from_request(request)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        try:
            content = index_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler index.html: {e}")
    
    return JSONResponse(status_code=404, content={"error": "index.html não encontrado"})

# 5. Raiz (/)
@app.get("/", include_in_schema=False)
async def get_root_page(request: Request):
    """Serve a página inicial"""
    payload = await verify_token_from_request(request)
    
    if payload and frontend_status["dashboard"]:
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            try:
                content = index_path.read_text(encoding="utf-8")
                return HTMLResponse(content=content)
            except Exception as e:
                print(f"   ❌ Erro ao ler index.html: {e}")
    
    login_path = FRONTEND_DIR / "login.html"
    if login_path.exists():
        try:
            content = login_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler login.html: {e}")
    
    return JSONResponse({"message": "AutoAnalytics API", "docs": "/api/docs"})


# ==============================================
# 🔥 REDIRECIONAMENTOS (301 - Moved Permanently)
# ==============================================

@app.get("/index.html", include_in_schema=False)
async def redirect_index_html():
    return RedirectResponse(url="/", status_code=301)

@app.get("/planos.html", include_in_schema=False)
async def redirect_planos_html():
    return RedirectResponse(url="/planos", status_code=301)

@app.get("/login.html", include_in_schema=False)
async def redirect_login_html():
    return RedirectResponse(url="/login", status_code=301)

@app.get("/checkout.html", include_in_schema=False)
async def redirect_checkout_html():
    return RedirectResponse(url="/checkout", status_code=301)

@app.get("/dashboard.html", include_in_schema=False)
async def redirect_dashboard_html():
    return RedirectResponse(url="/dashboard", status_code=301)


print("   ✅ Rotas HTML: /, /login, /dashboard, /planos, /checkout")

# ==============================================
# 11. 🔥 IMPORTAÇÃO DE MÓDULOS (CORRIGIDA)
# ==============================================

print("\n📦 Carregando módulos do backend...")

# 🔥 Variáveis globais
hasher = None
jwt_manager = None
rate_limiter = None
get_current_user = None
get_current_active_user = None
get_current_admin_user = None
set_auth_cookies = None
clear_auth_cookies = None
AUTH_ENABLED = False
pipeline = None
process_file_content = None
SessionLocal = None

# 11.1 Database
try:
    from backend.database import engine, Base, create_tables, SessionLocal as _SessionLocal, get_db
    SessionLocal = _SessionLocal
    create_tables()
    print("   ✅ Database: tabelas verificadas")
except ImportError as e:
    print(f"   ❌ Database não disponível: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Erro ao inicializar Database: {e}")
    sys.exit(1)

# 11.2 Security
print("   🔐 Carregando Security...")

try:
    from backend.security import (
        hasher as _hasher,
        jwt_manager as _jwt_manager,
        rate_limiter as _rate_limiter,
        get_current_user as _get_current_user,
        get_current_active_user as _get_current_active_user,
        get_current_admin_user as _get_current_admin_user,
        set_auth_cookies as _set_auth_cookies,
        clear_auth_cookies as _clear_auth_cookies
    )
    hasher = _hasher
    jwt_manager = _jwt_manager
    rate_limiter = _rate_limiter
    get_current_user = _get_current_user
    get_current_active_user = _get_current_active_user
    get_current_admin_user = _get_current_admin_user
    set_auth_cookies = _set_auth_cookies
    clear_auth_cookies = _clear_auth_cookies
    AUTH_ENABLED = True
    print("   ✅ Security carregado (AUTH ENABLED)")
except ImportError as e:
    print(f"   ⚠️ Security não disponível: {e}")
    print("   🔧 Usando fallback (autenticação desabilitada)")
    
    # ===== FALLBACK: FUNÇÕES MOCK =====
    class MockJWTManager:
        async def verify_token(self, token, token_type="access"):
            return None
        def create_token_pair(self, data):
            return {"access_token": "mock_token", "refresh_token": "mock_refresh", "expires_in": 3600}
        async def logout(self, refresh_token, db, access_token=None):
            return True
        async def refresh_access_token(self, refresh_token, db, old_access_token=None):
            return {"access_token": "mock_token", "refresh_token": "mock_refresh", "expires_in": 3600}
        async def init_redis(self):
            return True
        def decode_token(self, token):
            return {}
    
    jwt_manager = MockJWTManager()
    rate_limiter = None
    
    async def _fallback_get_current_user(request=None, token=None, db=None):
        return None
    
    async def _fallback_get_current_active_user(current_user=None):
        return None
    
    async def _fallback_get_current_admin_user(current_user=None):
        return None
    
    def _fallback_set_auth_cookies(response, access_token, refresh_token=None, expires_in=3600):
        return response
    
    def _fallback_clear_auth_cookies(response):
        return response
    
    get_current_user = _fallback_get_current_user
    get_current_active_user = _fallback_get_current_active_user
    get_current_admin_user = _fallback_get_current_admin_user
    set_auth_cookies = _fallback_set_auth_cookies
    clear_auth_cookies = _fallback_clear_auth_cookies

# 11.3 Models
try:
    from backend.models import User, Analysis, PromotionControl, Payment, DailyCreditLog
    print("   ✅ Models carregados")
except ImportError as e:
    print(f"   ⚠️ Models não disponível: {e}")
    class User: pass
    class Analysis: pass
    class PromotionControl: pass
    class Payment: pass
    class DailyCreditLog: pass

# 11.4 CRUD
try:
    from backend import crud
    print(f"   ✅ CRUD carregado")
except ImportError as e:
    print(f"   ⚠️ CRUD não disponível: {e}")
    crud = None

# 11.5 Services
try:
    from backend.services.daily_credits_service import DailyCreditsService
    print("   ✅ DailyCreditsService carregado")
except ImportError as e:
    print(f"   ⚠️ DailyCreditsService não disponível: {e}")
    class DailyCreditsService:
        def get_user_credit_status(self, db, user_id):
            return {"current_credits": 3, "streak_days": 0, "received_today": False}
        def check_and_add_daily_credit(self, db, user_id):
            return {"success": False, "credits_added": 0, "message": "Serviço indisponível"}
    DailyCreditsService = DailyCreditsService

try:
    from backend.services.credits_consumer import (
        can_perform_analysis, consume_analysis_credit, get_credits_display
    )
    print("   ✅ CreditsConsumer carregado")
except ImportError as e:
    print(f"   ⚠️ CreditsConsumer não disponível: {e}")
    def can_perform_analysis(user, required=1): return True
    def consume_analysis_credit(user, db, required=1): return True
    def get_credits_display(user): return "0"

# 🔥 11.6 ML Pipeline - CORRIGIDO (caminho backend.ml.preprocessing)
print("   🤖 Carregando ML Pipeline...")

try:
    from backend.ml.preprocessing import pipeline as _pipeline, process_file_content as _process_file_content
    pipeline = _pipeline
    process_file_content = _process_file_content
    print("   ✅ ML Pipeline carregado de backend.ml.preprocessing")
    if hasattr(pipeline, 'model_source'):
        print(f"      📊 Modelo: {pipeline.model_source}")
    print(f"      🔤 Encoding: automático (chardet)")
    print(f"      💾 Cache: TTL 60s")
except ImportError as e:
    print(f"   ⚠️ ML Pipeline não disponível: {e}")
    print("   🔧 Usando fallback (ML desabilitado)")
    
    # ===== FALLBACK: MOCK PIPELINE =====
    class MockPipeline:
        def __init__(self):
            self.model_source = "placeholder"
            self.is_initialized = False
        async def initialize(self):
            self.is_initialized = True
            return True
        async def predict(self, df, filename=None):
            return {"success": False, "error": "ML não disponível", "predictions": [0.5] * len(df)}
        def get_status(self):
            return {"initialized": False, "model_source": "placeholder", "cache_size": 0}
        def get_encoding_stats(self):
            return {"encodings": {}, "total_success": 0, "total_failed": 0}
        def clear_cache(self):
            pass
    pipeline = MockPipeline()
    
    async def _fallback_process_file_content(content, filename):
        return {"success": False, "error": "ML não disponível"}
    process_file_content = _fallback_process_file_content

print("   ✅ Módulos carregados com sucesso!")

# ==============================================
# 12. 🔥 REGISTRO DE ROTAS DE AUTENTICAÇÃO (CORRIGIDO)
# ==============================================

print("\n🔐 Registrando rotas de autenticação...")

# 🔥 VERIFICAÇÃO: Importa auth_routes com fallback detalhado
try:
    from backend.api.auth_routes import router as auth_router
    app.include_router(auth_router, prefix="/api/auth")
    print("   ✅ Rotas de Autenticação (auth_routes) registradas com sucesso!")
    print("      POST   /api/auth/login     ← 🔥 LOGIN")
    print("      POST   /api/auth/refresh")
    print("      POST   /api/auth/logout")
    print("      GET    /api/auth/check-token")
    print("      GET    /api/auth/me")
    print("      GET    /api/auth/session-status")
    
    _auth_routes_loaded = True
    
except ImportError as e:
    print(f"   ❌ ERRO CRÍTICO ao importar auth_routes: {e}")
    print("   💡 Verifique se o arquivo backend/api/auth_routes.py existe")
    import traceback
    traceback.print_exc()
    _auth_routes_loaded = False
    
    # 🔥 CRIA ROTAS DE AUTENTICAÇÃO MANUALMENTE (FALLBACK)
    print("   🔧 Criando rotas de autenticação MANUALMENTE (FALLBACK)...")
    
    @app.post("/api/auth/login")
    async def fallback_login():
        return {"error": "Sistema de autenticação indisponível", "status": "error", "message": "Contate o administrador"}
    
    @app.post("/api/auth/refresh")
    async def fallback_refresh():
        return {"error": "Sistema de autenticação indisponível", "status": "error"}
    
    @app.post("/api/auth/logout")
    async def fallback_logout():
        return {"success": True, "message": "Logout realizado"}
    
    @app.get("/api/auth/check-token")
    async def fallback_check_token():
        return {"status": "invalid", "message": "Sistema de autenticação indisponível"}
    
    @app.get("/api/auth/me")
    async def fallback_me():
        return {"error": "Sistema de autenticação indisponível", "status": "error"}
    
    @app.get("/api/auth/session-status")
    async def fallback_session_status():
        return {"authenticated": False, "message": "Sistema de autenticação indisponível"}
    
    print("   ⚠️ Rotas de autenticação MANUAIS criadas (FALLBACK)")

except Exception as e:
    print(f"   ❌ ERRO ao registrar auth_routes: {e}")
    import traceback
    traceback.print_exc()
    _auth_routes_loaded = False

# 🔥 REGISTRO (SEPARADO - NÃO QUEBRA O LOGIN)
try:
    from backend.api.auth import router as registration_router
    app.include_router(registration_router, prefix="/api/auth")
    print("   ✅ Rotas de Cadastro (auth) registradas com sucesso!")
    print("      POST   /api/auth/register  ← 🔥 REGISTRO")
except ImportError as e:
    print(f"   ⚠️ Módulo de cadastro (auth.py) não disponível: {e}")
    print("   💡 O login continua funcionando, apenas o registro não estará disponível.")
    
    # 🔥 CRIA ROTA DE REGISTRO MANUAL (FALLBACK)
    @app.post("/api/auth/register")
    async def fallback_register():
        return {"error": "Sistema de registro indisponível", "status": "error"}
    
    print("   ⚠️ Rota de registro MANUAL criada (FALLBACK)")
except Exception as e:
    print(f"   ⚠️ Erro ao registrar auth.py: {e}")

# ==============================================
# 13. 🔥 OUTRAS ROTAS (COM FALLBACK E PoW)
# ==============================================

print("\n📦 Registrando outras rotas...")

# Payment
try:
    from backend.api.payment_routes import router as payment_router
    app.include_router(payment_router, prefix="/api")
    print("   ✅ Payment Routes (/api/payments/*)")
except ImportError as e:
    print(f"   ⚠️ Payment Routes não disponível: {e}")
except Exception as e:
    print(f"   ⚠️ Erro ao registrar Payment: {e}")

# Upload
try:
    from backend.api.upload_routes import router as upload_router
    app.include_router(upload_router, prefix="/api")
    print("   ✅ Upload Routes (/api/upload-auto, /api/status)")
except ImportError as e:
    print(f"   ⚠️ Upload Routes não disponível: {e}")
except Exception as e:
    print(f"   ⚠️ Erro ao registrar Upload: {e}")

# Gemini
try:
    from backend.api.routes import router as gemini_router
    app.include_router(gemini_router, prefix="/api")
    print("   ✅ Gemini Routes (/api/upload, /api/health)")
except ImportError as e:
    print(f"   ⚠️ Gemini Routes não disponível: {e}")
except Exception as e:
    print(f"   ⚠️ Erro ao registrar Gemini: {e}")

# 🔥 PoW - VERIFICAR SE ESTÁ REGISTRADO
try:
    from backend.api.pow_routes import router as pow_router
    app.include_router(pow_router, prefix="/api")  # → /api/pow/challenge
    print("   ✅ PoW Routes (/api/pow/*) registradas com sucesso!")
    print("      GET    /api/pow/challenge  ← 🔥 DESAFIO PoW")
    print("      POST   /api/pow/verify     ← 🔥 VERIFICAÇÃO PoW")
    print("      GET    /api/pow/health     ← 🔥 SAÚDE PoW")
    print("      GET    /api/pow/stats      ← 📊 ESTATÍSTICAS PoW (admin)")
    _pow_routes_loaded = True
except ImportError as e:
    print(f"   ❌ PoW Routes não disponível: {e}")
    print("   💡 Verifique se backend/api/pow_routes.py existe")
    _pow_routes_loaded = False
except Exception as e:
    print(f"   ❌ Erro ao registrar PoW: {e}")
    import traceback
    traceback.print_exc()
    _pow_routes_loaded = False

# ==============================================
# 14. 🔥 ROTA DE COMPATIBILIDADE - premium-status (CORRIGIDA)
# ==============================================

# 🔥 Função para obter db de forma segura
def get_db_safe():
    """Obtém a sessão do banco de dados de forma segura"""
    try:
        if SessionLocal is not None:
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()
        else:
            yield None
    except Exception:
        yield None

@app.get("/api/payments/premium-status", tags=["payments"])
async def get_premium_status_compat(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_safe)
):
    """
    🔥 ROTA DE COMPATIBILIDADE PARA O FRONTEND
    Esta rota é chamada pelo loadPremiumStatus() no payment.js
    """
    try:
        if current_user is None:
            return JSONResponse(
                status_code=401,
                content={"is_premium": False, "error": "Não autenticado"}
            )
        
        # Verificar se é admin
        if hasattr(current_user, 'is_admin') and current_user.is_admin:
            return {
                "is_premium": True,
                "days_left": 999,
                "is_admin": True,
                "credits_balance": "∞",
                "max_credits_balance": settings.MAX_CREDITS_BALANCE,
                "plan": "admin",
                "can_receive_today": False,
                "received_today": True,
                "promotional_price_locked": False,
                "promotional_price": None,
                "is_vitalicio": False,
                "next_credit_date": None,
                "activated_at": None,
                "expires_at": None,
                "days_used": 0
            }
        
        # Usar CRUD para verificar status premium
        if crud is not None and db is not None:
            premium_status = crud.check_premium_status(db, current_user.id)
            is_premium = premium_status.get("is_premium", False)
            days_left = premium_status.get("days_left", 0)
            
            # Verificar créditos
            user = crud.get_user_by_id(db, current_user.id)
            credits = user.credits if user else 0
            
            # Verificar se já recebeu crédito hoje
            received_today = False
            if is_premium and user:
                today = datetime.now().date()
                log = db.query(DailyCreditLog).filter(
                    DailyCreditLog.user_id == user.id,
                    DailyCreditLog.date == today,
                    DailyCreditLog.source == "premium_daily"
                ).first()
                received_today = log is not None
            
            return {
                "is_premium": is_premium,
                "days_left": max(0, days_left),
                "is_admin": False,
                "credits_balance": credits,
                "max_credits_balance": settings.MAX_CREDITS_BALANCE,
                "plan": "premium_mensal" if is_premium else "free",
                "can_receive_today": is_premium and not received_today and credits < settings.MAX_CREDITS_BALANCE,
                "received_today": received_today,
                "promotional_price_locked": user.promotional_price_locked if user else False,
                "promotional_price": user.promotional_price if user else None,
                "is_vitalicio": user.promotional_price_locked if user else False,
                "next_credit_date": None,
                "activated_at": premium_status.get("activated_at"),
                "expires_at": premium_status.get("expires_at"),
                "days_used": 0
            }
        else:
            # Fallback: retorna dados básicos
            return {
                "is_premium": False,
                "days_left": 0,
                "is_admin": False,
                "credits_balance": 0,
                "max_credits_balance": settings.MAX_CREDITS_BALANCE,
                "plan": "free",
                "can_receive_today": False,
                "received_today": False,
                "promotional_price_locked": False,
                "promotional_price": None,
                "is_vitalicio": False,
                "next_credit_date": None,
                "activated_at": None,
                "expires_at": None,
                "days_used": 0
            }
    except Exception as e:
        print(f"   ⚠️ Erro em /premium-status: {e}")
        return {
            "is_premium": False,
            "days_left": 0,
            "is_admin": False,
            "credits_balance": 0,
            "max_credits_balance": settings.MAX_CREDITS_BALANCE,
            "plan": "free",
            "can_receive_today": False,
            "received_today": False,
            "promotional_price_locked": False,
            "promotional_price": None,
            "is_vitalicio": False,
            "next_credit_date": None,
            "activated_at": None,
            "expires_at": None,
            "days_used": 0
        }

print("   ✅ Rota de compatibilidade /api/payments/premium-status")

# ==============================================
# 15. 🔥 VERIFICAÇÃO FINAL DAS ROTAS
# ==============================================

print("\n📋 Verificando rotas registradas...")
auth_routes_found = []
pow_routes_found = []
payment_routes_found = []

for route in app.routes:
    if hasattr(route, 'path'):
        if '/auth' in route.path:
            auth_routes_found.append(route.path)
        if '/pow' in route.path:
            pow_routes_found.append(route.path)
        if '/payments' in route.path:
            payment_routes_found.append(route.path)

if auth_routes_found:
    print(f"   ✅ Rotas /auth encontradas: {len(auth_routes_found)}")
    for r in auth_routes_found[:5]:
        print(f"      📍 {r}")
else:
    print("   ❌ NENHUMA ROTA /auth ENCONTRADA!")
    print("   ⚠️ O LOGIN NÃO VAI FUNCIONAR!")

if pow_routes_found:
    print(f"   ✅ Rotas /pow encontradas: {len(pow_routes_found)}")
    for r in pow_routes_found[:5]:
        print(f"      📍 {r}")
else:
    print("   ❌ NENHUMA ROTA /pow ENCONTRADA!")
    print("   ⚠️ O PoW NÃO VAI FUNCIONAR!")

if payment_routes_found:
    print(f"   ✅ Rotas /payments encontradas: {len(payment_routes_found)}")
    for r in payment_routes_found[:5]:
        print(f"      📍 {r}")

print("   ✅ Verificação de rotas concluída!")

# ==============================================
# 16. HEALTH CHECK (ATUALIZADO COM PoW)
# ==============================================

@app.get("/api/health", tags=["system"])
async def health_check():
    """Verificação de saúde do sistema"""
    ml_status = {}
    if pipeline is not None and hasattr(pipeline, 'get_status'):
        try:
            ml_status = pipeline.get_status()
        except Exception:
            ml_status = {"error": "Erro ao obter status do ML"}
    
    # Verificar auth
    auth_status = "✅" if AUTH_ENABLED else "❌"
    auth_routes_ok = len(auth_routes_found) > 0
    
    # Verificar PoW
    pow_routes_ok = len(pow_routes_found) > 0
    pow_status = "✅" if pow_routes_ok else "❌"
    
    return {
        "status": "healthy" if (auth_routes_ok and pow_routes_ok) else "degraded",
        "timestamp": datetime.now().isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "auth_enabled": AUTH_ENABLED,
        "auth_status": auth_status,
        "auth_routes_registered": auth_routes_ok,
        "pow_status": pow_status,
        "pow_routes_registered": pow_routes_ok,
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]),
        "frontend_available": frontend_status["available"],
        "ml_pipeline": ml_status,
        "max_file_size_kb": settings.MAX_FILE_SIZE // 1024,
        "max_files_per_batch": settings.MAX_FILES_PER_BATCH,
        "timezone": "America/Sao_Paulo (UTC-3)"
    }

# ==============================================
# 17. INICIALIZAÇÃO DA PROMOÇÃO
# ==============================================

def init_promotion(db) -> None:
    """
    Inicializa a promoção de fundador se não existir
    """
    try:
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
            print(f"   ✅ Promoção criada: {settings.TOTAL_PROMOTIONAL_SLOTS} vagas a R$ {settings.PROMOTIONAL_PRICE}")
        else:
            remaining = promo.get_remaining_slots()
            print(f"   ✅ Promoção ativa: {remaining}/{settings.TOTAL_PROMOTIONAL_SLOTS} vagas")
            if remaining <= 0:
                print(f"   ⚠️ PROMOÇÃO ESGOTADA! Preço: R$ {settings.REGULAR_PRICE}")
    except Exception as e:
        print(f"   ⚠️ Erro ao inicializar promoção: {e}")

# ==============================================
# 18. STARTUP (ATUALIZADO COM PoW)
# ==============================================

@app.on_event("startup")
async def startup_event():
    """Evento executado na inicialização do servidor"""
    print("\n" + "=" * 75)
    print("🚀 INICIALIZANDO SISTEMA...")
    print("=" * 75)
    
    # 18.1 Sentinel
    try:
        from backend.observability.sentinel import startup_webhook
        await startup_webhook()
        print("   ✅ Sentinel inicializado")
    except ImportError:
        print("   ⚠️ Sentinel não disponível")
    except Exception as e:
        print(f"   ⚠️ Erro no Sentinel: {e}")
    
    # 18.2 Promoção
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            init_promotion(db)
            db.close()
        except Exception as e:
            print(f"   ⚠️ Erro na promoção: {e}")
    else:
        print("   ⚠️ SessionLocal não disponível - pulando promoção")
    
    # 18.3 ML Pipeline
    if pipeline is not None:
        try:
            if hasattr(pipeline, 'initialize'):
                await pipeline.initialize()
                print("   ✅ ML Pipeline inicializado")
        except Exception as e:
            print(f"   ⚠️ Erro no ML Pipeline: {e}")
    else:
        print("   ⚠️ Pipeline não disponível - pulando inicialização ML")
    
    # 18.4 Redis
    if jwt_manager is not None:
        try:
            if hasattr(jwt_manager, 'init_redis'):
                await jwt_manager.init_redis()
                print("   ✅ Redis inicializado")
        except Exception as e:
            print(f"   ⚠️ Erro no Redis: {e}")
    else:
        print("   ⚠️ JWT Manager não disponível - pulando Redis")
    
    # 🔥 18.5 PoW Service
    try:
        from backend.api.pow_routes import pow_service
        print(f"   ✅ PoW Service inicializado")
        print(f"      🛡️  Prevenção replay: Ativa")
    except ImportError:
        print("   ⚠️ PoW Service não disponível")
    except Exception as e:
        print(f"   ⚠️ Erro ao inicializar PoW: {e}")
    
    # 18.6 Verificar rotas
    print("\n🔐 Verificando rotas registradas...")
    auth_routes = []
    pow_routes = []
    payment_routes = []
    
    for route in app.routes:
        if hasattr(route, 'path'):
            if '/auth' in route.path:
                auth_routes.append(route.path)
            if '/pow' in route.path:
                pow_routes.append(route.path)
            if '/payments' in route.path:
                payment_routes.append(route.path)
    
    if auth_routes:
        print(f"   ✅ Rotas /auth encontradas: {len(auth_routes)}")
        for r in auth_routes[:5]:
            print(f"      📍 {r}")
    else:
        print("   ❌ NENHUMA ROTA /auth ENCONTRADA!")
        print("   ⚠️ O LOGIN NÃO VAI FUNCIONAR!")
    
    if pow_routes:
        print(f"   ✅ Rotas /pow encontradas: {len(pow_routes)}")
        for r in pow_routes[:5]:
            print(f"      📍 {r}")
    else:
        print("   ❌ NENHUMA ROTA /pow ENCONTRADA!")
        print("   ⚠️ O PoW NÃO VAI FUNCIONAR!")
    
    if payment_routes:
        print(f"   ✅ Rotas /payments encontradas: {len(payment_routes)}")
        for r in payment_routes[:5]:
            print(f"      📍 {r}")
    
    # 18.7 Status Final
    gemini_status = "✅" if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"] else "❌"
    ml_status = "✅" if (pipeline is not None and hasattr(pipeline, 'is_initialized') and pipeline.is_initialized) else "⚠️"
    auth_ok = "✅" if auth_routes else "❌"
    pow_ok = "✅" if pow_routes else "❌"
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════════════════════════╗
    ║     🎉 AutoAnalytics v{settings.VERSION} - PRODUÇÃO                           ║
    ╠═══════════════════════════════════════════════════════════════════════════════╣
    ║  🌍 Ambiente: {settings.ENVIRONMENT.upper():<48}  ║
    ║  🤖 Gemini: {gemini_status} | 🤖 ML: {ml_status}                        ║
    ║  🔐 Auth: {auth_ok} | 🔒 PoW: {pow_ok}                  ║
    ║  🌐 Frontend: {"✅" if frontend_status["available"] else "❌"}          ║
    ║  📁 Upload: {settings.MAX_FILE_SIZE // 1024}KB | {settings.MAX_FILES_PER_BATCH} arquivos        ║
    ║  💰 Créditos: {settings.INITIAL_FREE_CREDITS} grátis | máx {settings.MAX_CREDITS_BALANCE}          ║
    ║  🎯 Preço Fundador: R$ {settings.PROMOTIONAL_PRICE} ({settings.TOTAL_PROMOTIONAL_SLOTS} vagas)        ║
    ╠═══════════════════════════════════════════════════════════════════════════════╣
    ║  🔗 API Docs: http://localhost:{settings.PORT}/api/docs                     ║
    ║  🌐 Páginas: /, /login, /dashboard, /planos, /checkout                      ║
    ║  🕐 Timezone: America/Sao_Paulo (UTC-3)                                    ║
    ╚═══════════════════════════════════════════════════════════════════════════════╝
    """)

# ==============================================
# 19. SHUTDOWN
# ==============================================

@app.on_event("shutdown")
async def shutdown_event():
    """Evento executado no desligamento do servidor"""
    print("\n🛑 Desligando sistema...")
    
    try:
        from backend.observability.sentinel import shutdown_webhook
        await shutdown_webhook()
        print("   ✅ Sentinel finalizado")
    except ImportError:
        print("   ⚠️ Sentinel não disponível")
    except Exception as e:
        print(f"   ⚠️ Erro no Sentinel: {e}")
    
    try:
        if pipeline is not None and hasattr(pipeline, 'clear_cache'):
            pipeline.clear_cache()
            print("   ✅ Cache ML limpo")
    except Exception as e:
        print(f"   ⚠️ Erro ao limpar cache: {e}")
    
    print("👋 Sistema desligado!")

# ==============================================
# 20. EXCEPTION HANDLERS
# ==============================================

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    """Handler para erros 404"""
    path = request.url.path
    if path.startswith('/api/'):
        return JSONResponse(status_code=404, content={"error": "Endpoint não encontrado", "path": path})
    return JSONResponse(status_code=404, content={"error": "Página não encontrada"})

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handler para exceções HTTP"""
    path = request.url.path
    if exc.status_code == 401 and not path.startswith('/api/'):
        return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handler para exceções não tratadas"""
    print(f"❌ Exceção não tratada: {exc}")
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"error": "Erro interno do servidor", "detail": str(exc) if settings.DEBUG else "Tente novamente mais tarde"}
    )

# ==============================================
# 21. MAIN
# ==============================================

if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 Gemini: {'✅' if settings.GEMINI_API_KEY else '❌'}")
    
    # 🔥 Verificação segura do pipeline
    pipeline_ok = pipeline is not None and hasattr(pipeline, 'is_initialized')
    print(f"🤖 ML: {'✅' if pipeline_ok else '⚠️'}")
    
    print(f"🔐 Auth: {'✅' if AUTH_ENABLED else '❌'}")
    print(f"🔒 PoW: {'✅' if _pow_routes_loaded else '❌'}")
    print(f"💳 Mercado Pago: {'✅' if settings.MP_ACCESS_TOKEN else '❌'}")
    print(f"🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning"
    )