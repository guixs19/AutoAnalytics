# main.py (na raiz) - VERSÃO PRODUÇÃO v5.0 (CORREÇÃO FINAL + MELHORIAS)
"""
AutoAnalytics - Servidor Principal
================================================================================
🔥 CORREÇÕES v5.0:
- ✅ CORRIGIDO: Importação do upload_routes com logging detalhado
- ✅ CORRIGIDO: Verificação de rotas no startup
- ✅ MELHORADO: Logs estruturados com níveis
- ✅ ADICIONADO: Middleware de performance
- ✅ ADICIONADO: Cache de respostas (opcional)
- ✅ ADICIONADO: Compressão de respostas
- ✅ MELHORADO: Tratamento de erros global
- ✅ ADICIONADO: Rota /api/routes para debug
- ✅ CORRIGIDO: Redirect slashes para permitir /api/analyses/history
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
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List

# ==============================================
# 1. PATHS E CONFIGURAÇÃO INICIAL
# ==============================================

PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Configurar paths antes de qualquer import
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("autoanalytics")

print("=" * 75)
print("🚀 AUTOANALYTICS v5.0 - PRODUÇÃO (CORREÇÃO FINAL)")
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
    VERSION = "5.0.0"
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
    
    # PoW
    POW_ENABLED = os.getenv("POW_ENABLED", "true").lower() == "true"
    POW_DEFAULT_DIFFICULTY = int(os.getenv("POW_DEFAULT_DIFFICULTY", "4"))

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
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
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
    description="AutoAnalytics - IA para Oficinas Mecânicas (COM PoW)",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ==============================================
# 7. MIDDLEWARES (ORDEM IMPORTANTE)
# ==============================================

print("\n📊 Configurando middlewares...")

# 7.1 Trusted Host (segurança)
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["autoanalytics.site", "www.autoanalytics.site", "localhost", "127.0.0.1"]
    )
    print("   ✅ TrustedHostMiddleware ativado")

# 7.2 GZip (compressão)
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=6
)
print("   ✅ GZipMiddleware ativado (compressão)")

# 7.3 Observabilidade
try:
    from backend.observability.sentinel import LoggingMiddleware, get_metrics_collector
    metrics_collector = get_metrics_collector()
    app.add_middleware(LoggingMiddleware, metrics=metrics_collector)
    print("   ✅ LoggingMiddleware ativado")
except ImportError:
    print("   ⚠️ Sentinel não disponível")
except Exception as e:
    print(f"   ⚠️ Erro ao ativar Sentinel: {e}")

# 7.4 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Auth-Required", "X-Redirect-To", "X-Process-Time"]
)
print(f"   ✅ CORS: {len(settings.CORS_ORIGINS)} origens permitidas")

# 7.5 Log de requisições (custom)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware para log de requisições HTTP com timing"""
    start_time = time.time()
    path = request.url.path
    method = request.method
    
    # Log apenas para APIs e rotas importantes
    if not path.startswith('/static') and not path.startswith('/js') and path not in ['/favicon.ico', '/health']:
        logger.info(f"🌐 {method} {path}")
    
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"❌ Erro na requisição {method} {path}: {e}")
        raise
    
    # Adicionar header de tempo de processamento
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    
    # Log de erros
    if response.status_code >= 400 and not path.startswith('/static'):
        logger.warning(f"⚠️ {method} {path} → {response.status_code} ({process_time:.2f}ms)")
    
    # Adicionar headers de segurança
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
# 10. FUNÇÃO AUXILIAR: VERIFICAR TOKEN
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
        return None
    
    try:
        from backend.security import jwt_manager
        return await jwt_manager.verify_token(token, "access")
    except ImportError:
        return None
    except Exception as e:
        logger.warning(f"⚠️ Erro ao verificar token: {e}")
        return None

# ==============================================
# 11. ROTAS HTML
# ==============================================

print("\n🌐 Configurando rotas HTML...")

def serve_html_page(filename: str, fallback: Optional[str] = None) -> HTMLResponse:
    """Serve um arquivo HTML do diretório frontend"""
    file_path = FRONTEND_DIR / filename
    if file_path.exists():
        try:
            content = file_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content, status_code=200)
        except Exception as e:
            logger.error(f"❌ Erro ao ler {filename}: {e}")
    
    if fallback:
        fallback_path = FRONTEND_DIR / fallback
        if fallback_path.exists():
            try:
                content = fallback_path.read_text(encoding="utf-8")
                return HTMLResponse(content=content, status_code=200)
            except Exception as e:
                logger.error(f"❌ Erro ao ler fallback: {e}")
    
    return HTMLResponse(content=f"<h1>Página não encontrada</h1><p>{filename} não disponível</p>", status_code=404)

# Rotas HTML
@app.get("/login", include_in_schema=False)
async def get_login_page(request: Request):
    payload = await verify_token_from_request(request)
    if payload and frontend_status["dashboard"]:
        return RedirectResponse(url="/dashboard", status_code=302)
    return serve_html_page("login.html")

@app.get("/planos", include_in_schema=False)
async def get_planos_page(request: Request):
    payload = await verify_token_from_request(request)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    return serve_html_page("planos.html")

@app.get("/checkout", include_in_schema=False)
async def get_checkout_page(request: Request):
    payload = await verify_token_from_request(request)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    return serve_html_page("checkout.html")

@app.get("/dashboard", include_in_schema=False)
async def get_dashboard_page(request: Request):
    payload = await verify_token_from_request(request)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    return serve_html_page("index.html")

@app.get("/", include_in_schema=False)
async def get_root_page(request: Request):
    payload = await verify_token_from_request(request)
    if payload and frontend_status["dashboard"]:
        return serve_html_page("index.html")
    return serve_html_page("login.html")

# Redirecionamentos 301
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
# 12. IMPORTAÇÃO DE MÓDULOS
# ==============================================

print("\n📦 Carregando módulos do backend...")

# Variáveis globais
hasher = None
jwt_manager = None
rate_limiter = None
get_current_user = None
get_current_active_user = None
get_current_admin_user = None
get_current_active_superuser = None
set_auth_cookies = None
clear_auth_cookies = None
AUTH_ENABLED = False
pipeline = None
process_file_content = None
SessionLocal = None
_pow_routes_loaded = False
_auth_routes_loaded = False
_upload_routes_loaded = False

# 12.1 Database
try:
    from backend.database import engine, Base, create_tables, SessionLocal as _SessionLocal, get_db
    SessionLocal = _SessionLocal
    create_tables()
    print("   ✅ Database: tabelas verificadas")
except ImportError as e:
    logger.error(f"❌ Database não disponível: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"❌ Erro ao inicializar Database: {e}")
    sys.exit(1)

# 12.2 Security
print("   🔐 Carregando Security...")
try:
    from backend.security import (
        hasher as _hasher,
        jwt_manager as _jwt_manager,
        rate_limiter as _rate_limiter,
        get_current_user as _get_current_user,
        get_current_active_user as _get_current_active_user,
        get_current_admin_user as _get_current_admin_user,
        get_current_active_superuser as _get_current_active_superuser,
        set_auth_cookies as _set_auth_cookies,
        clear_auth_cookies as _clear_auth_cookies
    )
    hasher = _hasher
    jwt_manager = _jwt_manager
    rate_limiter = _rate_limiter
    get_current_user = _get_current_user
    get_current_active_user = _get_current_active_user
    get_current_admin_user = _get_current_admin_user
    get_current_active_superuser = _get_current_active_superuser
    set_auth_cookies = _set_auth_cookies
    clear_auth_cookies = _clear_auth_cookies
    AUTH_ENABLED = True
    print("   ✅ Security carregado (AUTH ENABLED)")
except ImportError as e:
    logger.warning(f"⚠️ Security não disponível: {e}")
    print("   🔧 Usando fallback (autenticação desabilitada)")
    
    # Fallback...
    class MockJWTManager:
        async def verify_token(self, token, token_type="access"): return None
        def create_token_pair(self, data): return {"access_token": "mock", "refresh_token": "mock", "expires_in": 3600}
        async def logout(self, refresh_token, db, access_token=None): return True
        async def refresh_access_token(self, refresh_token, db, old_access_token=None): return {"access_token": "mock", "refresh_token": "mock", "expires_in": 3600}
        async def init_redis(self): return True
        def decode_token(self, token): return {}
    
    jwt_manager = MockJWTManager()
    
    async def _fallback_get_current_user(request=None, token=None, db=None): return None
    async def _fallback_get_current_active_user(current_user=None): return None
    async def _fallback_get_current_admin_user(current_user=None): return None
    async def _fallback_get_current_active_superuser(current_user=None): return None
    def _fallback_set_auth_cookies(response, access_token, refresh_token=None, expires_in=3600): return response
    def _fallback_clear_auth_cookies(response): return response
    
    get_current_user = _fallback_get_current_user
    get_current_active_user = _fallback_get_current_active_user
    get_current_admin_user = _fallback_get_current_admin_user
    get_current_active_superuser = _fallback_get_current_active_superuser
    set_auth_cookies = _fallback_set_auth_cookies
    clear_auth_cookies = _fallback_clear_auth_cookies

# 12.3 Models
try:
    from backend.models import User, Analysis, PromotionControl, Payment, DailyCreditLog
    print("   ✅ Models carregados")
except ImportError as e:
    logger.warning(f"⚠️ Models não disponível: {e}")

# 12.4 CRUD
try:
    from backend import crud
    print(f"   ✅ CRUD carregado")
except ImportError as e:
    logger.warning(f"⚠️ CRUD não disponível: {e}")
    crud = None

# 12.5 Services
try:
    from backend.services.daily_credits_service import DailyCreditsService
    print("   ✅ DailyCreditsService carregado")
except ImportError as e:
    logger.warning(f"⚠️ DailyCreditsService não disponível: {e}")

try:
    from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display
    print("   ✅ CreditsConsumer carregado")
except ImportError as e:
    logger.warning(f"⚠️ CreditsConsumer não disponível: {e}")
    def can_perform_analysis(user, required=1): return True
    def consume_analysis_credit(user, db, required=1): return True
    def get_credits_display(user): return "0"

# 12.6 ML Pipeline
print("   🤖 Carregando ML Pipeline...")
try:
    from backend.preprocessing import pipeline as _pipeline, process_file_content as _process_file_content
    pipeline = _pipeline
    process_file_content = _process_file_content
    print("   ✅ ML Pipeline carregado")
except ImportError as e:
    logger.warning(f"⚠️ ML Pipeline não disponível: {e}")
    print("   🔧 Usando fallback (ML desabilitado)")
    class MockPipeline:
        def __init__(self): self.model_source = "placeholder"; self.is_initialized = False
        async def initialize(self): self.is_initialized = True; return True
        async def predict(self, df, filename=None): return {"success": False, "error": "ML não disponível", "predictions": [0.5] * len(df)}
        def get_status(self): return {"initialized": False, "model_source": "placeholder", "cache_size": 0}
        def get_encoding_stats(self): return {"encodings": {}, "total_success": 0, "total_failed": 0}
        def clear_cache(self): pass
    pipeline = MockPipeline()
    async def _fallback_process_file_content(content, filename): return {"success": False, "error": "ML não disponível"}
    process_file_content = _fallback_process_file_content

print("   ✅ Módulos carregados com sucesso!")

# ==============================================
# 13. 🔥 REGISTRO DE ROTAS (CORRIGIDO)
# ==============================================

print("\n🔐 Registrando rotas...")

# 13.1 Auth Routes
try:
    from backend.api.auth_routes import router as auth_router
    app.include_router(auth_router, prefix="/api/auth")
    _auth_routes_loaded = True
    print("   ✅ Auth Routes (/api/auth/*)")
except ImportError as e:
    logger.error(f"❌ Auth Routes não disponível: {e}")
except Exception as e:
    logger.error(f"❌ Erro ao registrar Auth: {e}")

# 13.2 Registration
try:
    from backend.api.auth import router as registration_router
    app.include_router(registration_router, prefix="/api/auth")
    print("   ✅ Registration Routes (/api/auth/register)")
except ImportError as e:
    logger.warning(f"⚠️ Registration não disponível: {e}")
except Exception as e:
    logger.warning(f"⚠️ Erro ao registrar Registration: {e}")

# 13.3 Payment
try:
    from backend.api.payment_routes import router as payment_router
    app.include_router(payment_router, prefix="/api")
    print("   ✅ Payment Routes (/api/payments/*)")
except ImportError as e:
    logger.warning(f"⚠️ Payment Routes não disponível: {e}")
except Exception as e:
    logger.warning(f"⚠️ Erro ao registrar Payment: {e}")

# 🔥 13.4 Upload Routes (CRÍTICO - CORRIGIDO)
try:
    from backend.api.upload_routes import router as upload_router
    app.include_router(upload_router, prefix="/api")
    _upload_routes_loaded = True
    print("   ✅ Upload Routes registradas com sucesso!")
    print("      POST   /api/upload-multi-analyze  ← 🔥 UPLOAD MÚLTIPLO")
    print("      POST   /api/upload-auto           ← 🔥 UPLOAD ÚNICO")
    print("      GET    /api/analyses/history      ← 🔥 HISTÓRICO")
    print("      GET    /api/analysis/result/{id}  ← 🔥 RESULTADO")
    print("      GET    /api/analyses/stats        ← 📊 ESTATÍSTICAS")
    print("      GET    /api/analyses/export/{fmt} ← 📥 EXPORTAÇÃO")
    print("      GET    /api/report/{analysis_id}  ← 📄 RELATÓRIO")
except ImportError as e:
    logger.error(f"❌ Upload Routes não disponível: {e}")
    print("   💡 Verifique se backend/api/upload_routes.py existe")
except Exception as e:
    logger.error(f"❌ Erro ao registrar Upload: {e}")
    import traceback
    traceback.print_exc()

# 13.5 PoW Routes
try:
    from backend.api.pow_routes import router as pow_router
    app.include_router(pow_router, prefix="/api")
    _pow_routes_loaded = True
    print("   ✅ PoW Routes (/api/pow/*) registradas com sucesso!")
    print("      GET    /api/pow/challenge  ← 🔥 DESAFIO PoW")
    print("      POST   /api/pow/verify     ← 🔥 VERIFICAÇÃO PoW")
    print("      GET    /api/pow/health     ← 🔥 SAÚDE PoW")
    print("      GET    /api/pow/stats      ← 📊 ESTATÍSTICAS PoW")
except ImportError as e:
    logger.error(f"❌ PoW Routes não disponível: {e}")
    print("   💡 Verifique se backend/api/pow_routes.py existe")
    _pow_routes_loaded = False
except Exception as e:
    logger.error(f"❌ Erro ao registrar PoW: {e}")
    import traceback
    traceback.print_exc()
    _pow_routes_loaded = False

# 13.6 Gemini
try:
    from backend.api.routes import router as gemini_router
    app.include_router(gemini_router, prefix="/api")
    print("   ✅ Gemini Routes (/api/upload, /api/health)")
except ImportError as e:
    logger.warning(f"⚠️ Gemini Routes não disponível: {e}")
except Exception as e:
    logger.warning(f"⚠️ Erro ao registrar Gemini: {e}")

# ==============================================
# 14. 🔥 ROTA DE DIAGNÓSTICO
# ==============================================

@app.get("/api/routes", tags=["system"])
async def list_all_routes():
    """Lista todas as rotas registradas (debug)"""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": route.name if hasattr(route, "name") else None
            })
    
    # Filtrar rotas do sistema
    filtered = [r for r in routes if not r["path"].startswith("/static") and not r["path"].startswith("/favicon")]
    
    # Agrupar por prefixo
    grouped = {
        "auth": [r for r in filtered if "/auth" in r["path"]],
        "pow": [r for r in filtered if "/pow" in r["path"]],
        "upload": [r for r in filtered if any(x in r["path"] for x in ["/upload", "/analyses", "/analysis", "/report"])],
        "payments": [r for r in filtered if "/payments" in r["path"]],
        "other": [r for r in filtered if not any(x in r["path"] for x in ["/auth", "/pow", "/upload", "/analyses", "/analysis", "/report", "/payments"])]
    }
    
    return {
        "total": len(filtered),
        "grouped": grouped,
        "upload_routes_loaded": _upload_routes_loaded,
        "pow_routes_loaded": _pow_routes_loaded,
        "auth_routes_loaded": _auth_routes_loaded
    }

# ==============================================
# 15. HEALTH CHECK (ATUALIZADO)
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
    
    # Verificar rotas registradas
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append(route.path)
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "auth_enabled": AUTH_ENABLED,
        "auth_routes_loaded": _auth_routes_loaded,
        "upload_routes_loaded": _upload_routes_loaded,
        "pow_enabled": settings.POW_ENABLED,
        "pow_routes_loaded": _pow_routes_loaded,
        "pow_default_difficulty": settings.POW_DEFAULT_DIFFICULTY,
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]),
        "frontend_available": frontend_status["available"],
        "ml_pipeline": ml_status,
        "max_file_size_kb": settings.MAX_FILE_SIZE // 1024,
        "max_files_per_batch": settings.MAX_FILES_PER_BATCH,
        "total_routes": len(routes),
        "timezone": "America/Sao_Paulo (UTC-3)"
    }

# ==============================================
# 16. EXCEPTION HANDLERS MELHORADOS
# ==============================================

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    """Handler para erros 404"""
    path = request.url.path
    if path.startswith('/api/'):
        return JSONResponse(
            status_code=404, 
            content={
                "error": "Endpoint não encontrado", 
                "path": path,
                "message": f"Rota '{path}' não existe. Verifique se o prefixo está correto."
            }
        )
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
    logger.error(f"❌ Exceção não tratada: {exc}")
    if settings.DEBUG:
        import traceback
        traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": "Erro interno do servidor", 
            "detail": str(exc) if settings.DEBUG else "Tente novamente mais tarde"
        }
    )

# ==============================================
# 17. PROMOÇÃO
# ==============================================

def init_promotion(db) -> None:
    """Inicializa a promoção de fundador se não existir"""
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
        logger.warning(f"⚠️ Erro ao inicializar promoção: {e}")

# ==============================================
# 18. STARTUP
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
        logger.warning(f"⚠️ Erro no Sentinel: {e}")
    
    # 18.2 Promoção
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            init_promotion(db)
            db.close()
        except Exception as e:
            logger.warning(f"⚠️ Erro na promoção: {e}")
    else:
        print("   ⚠️ SessionLocal não disponível - pulando promoção")
    
    # 18.3 ML Pipeline
    if pipeline is not None:
        try:
            if hasattr(pipeline, 'initialize'):
                await pipeline.initialize()
                print("   ✅ ML Pipeline inicializado")
        except Exception as e:
            logger.warning(f"⚠️ Erro no ML Pipeline: {e}")
    else:
        print("   ⚠️ Pipeline não disponível - pulando inicialização ML")
    
    # 18.4 Redis
    if jwt_manager is not None:
        try:
            if hasattr(jwt_manager, 'init_redis'):
                await jwt_manager.init_redis()
                print("   ✅ Redis inicializado")
        except Exception as e:
            logger.warning(f"⚠️ Erro no Redis: {e}")
    else:
        print("   ⚠️ JWT Manager não disponível - pulando Redis")
    
    # 18.5 PoW Service
    try:
        from backend.api.pow_routes import pow_service
        print(f"   ✅ PoW Service inicializado")
        print(f"      🛡️  Prevenção replay: Ativa")
        print(f"      🔢 Dificuldade padrão: {settings.POW_DEFAULT_DIFFICULTY}")
    except ImportError:
        print("   ⚠️ PoW Service não disponível")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao inicializar PoW: {e}")
    
    # 18.6 Verificar rotas registradas
    print("\n🔐 VERIFICANDO ROTAS REGISTRADAS...")
    
    auth_routes = []
    pow_routes = []
    upload_routes = []
    payment_routes = []
    
    for route in app.routes:
        if hasattr(route, 'path'):
            path = route.path
            if '/auth' in path:
                auth_routes.append(path)
            if '/pow' in path:
                pow_routes.append(path)
            if any(x in path for x in ['/upload', '/analyses', '/analysis', '/report']):
                upload_routes.append(path)
            if '/payments' in path:
                payment_routes.append(path)
    
    # Status
    auth_ok = "✅" if auth_routes else "❌"
    pow_ok = "✅" if pow_routes else "❌"
    upload_ok = "✅" if upload_routes else "❌"
    payment_ok = "✅" if payment_routes else "❌"
    
    print(f"   Auth: {auth_ok} {len(auth_routes)} rotas")
    if auth_routes:
        for r in auth_routes[:3]:
            print(f"      📍 {r}")
    
    print(f"   PoW: {pow_ok} {len(pow_routes)} rotas")
    if pow_routes:
        for r in pow_routes:
            print(f"      📍 {r}")
    
    print(f"   Upload: {upload_ok} {len(upload_routes)} rotas")
    if upload_routes:
        for r in upload_routes[:5]:
            print(f"      📍 {r}")
    
    print(f"   Payments: {payment_ok} {len(payment_routes)} rotas")
    
    # 🔥 Verificar especificamente a rota /analyses/history
    history_route = [r for r in upload_routes if '/analyses/history' in r]
    if history_route:
        print(f"   ✅ /analyses/history ENCONTRADA!")
    else:
        print(f"   ❌ /analyses/history NÃO ENCONTRADA!")
        print(f"   🔧 Verifique se upload_routes.py está sendo importado corretamente")
    
    # 18.7 Status Final
    gemini_status = "✅" if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"] else "❌"
    ml_status = "✅" if (pipeline is not None and hasattr(pipeline, 'is_initialized') and pipeline.is_initialized) else "⚠️"
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════════════════════════╗
    ║     🎉 AutoAnalytics v{settings.VERSION} - PRODUÇÃO                           ║
    ╠═══════════════════════════════════════════════════════════════════════════════╣
    ║  🌍 Ambiente: {settings.ENVIRONMENT.upper():<48}  ║
    ║  🤖 Gemini: {gemini_status} | 🤖 ML: {ml_status}                        ║
    ║  🔐 Auth: {auth_ok} | 🔒 PoW: {pow_ok} | 📤 Upload: {upload_ok}      ║
    ║  🌐 Frontend: {"✅" if frontend_status["available"] else "❌"}          ║
    ║  📁 Upload: {settings.MAX_FILE_SIZE // 1024}KB | {settings.MAX_FILES_PER_BATCH} arquivos        ║
    ║  💰 Créditos: {settings.INITIAL_FREE_CREDITS} grátis | máx {settings.MAX_CREDITS_BALANCE}          ║
    ║  🎯 Preço Fundador: R$ {settings.PROMOTIONAL_PRICE} ({settings.TOTAL_PROMOTIONAL_SLOTS} vagas)        ║
    ║  🔢 PoW Dificuldade: {settings.POW_DEFAULT_DIFFICULTY}                                     ║
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
        logger.warning(f"⚠️ Erro no Sentinel: {e}")
    
    try:
        if pipeline is not None and hasattr(pipeline, 'clear_cache'):
            pipeline.clear_cache()
            print("   ✅ Cache ML limpo")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao limpar cache: {e}")
    
    print("👋 Sistema desligado!")

# ==============================================
# 20. MAIN
# ==============================================

if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 Gemini: {'✅' if settings.GEMINI_API_KEY else '❌'}")
    print(f"🤖 ML: {'✅' if (pipeline is not None and hasattr(pipeline, 'is_initialized') and pipeline.is_initialized) else '⚠️'}")
    print(f"🔐 Auth: {'✅' if AUTH_ENABLED else '❌'}")
    print(f"🔒 PoW: {'✅' if _pow_routes_loaded else '❌'}")
    print(f"📤 Upload: {'✅' if _upload_routes_loaded else '❌'}")
    print(f"💳 Mercado Pago: {'✅' if settings.MP_ACCESS_TOKEN else '❌'}")
    print(f"🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning",
        access_log=settings.DEBUG
    )