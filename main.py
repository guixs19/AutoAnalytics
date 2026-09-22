# main.py (na raiz) - VERSÃO PRODUÇÃO v6.0
"""
AutoAnalytics - Servidor Principal
================================================================================
🔥 NOVIDADES v6.0:
- ✅ ADICIONADO: Support Routes (/api/support/*) - formulário de suporte via Gmail
- ✅ CORRIGIDO: load_dotenv() no topo (agora .env é carregado corretamente)
- ✅ MIGRADO: @app.on_event → lifespan (FastAPI moderno, sem deprecation)
- ✅ REFATORADO: helper _safe_register_router() para reduzir duplicação
- ✅ MELHORADO: timestamps com timezone UTC consistente com security.py
- ✅ MELHORADO: /api/health com status do support
- ✅ MELHORADO: logs de startup mais limpos e informativos
================================================================================
"""
import sys
import os
import time
import asyncio
import secrets
import string
import traceback
import logging
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, Callable, List

# ==============================================
# 0. CARREGAR .ENV (CRÍTICO - ANTES DE TUDO)
# ==============================================
PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

try:
    from dotenv import load_dotenv
    _env_path = PROJECT_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
        print(f"✅ .env carregado de: {_env_path}")
    else:
        load_dotenv(override=False)
        print(f"⚠️  .env não encontrado em {_env_path}, usando variáveis de ambiente")
except ImportError:
    print("⚠️  python-dotenv não instalado. Execute: pip install python-dotenv")

# Configurar paths antes de qualquer import
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

# ==============================================
# 1. LOGGING
# ==============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("autoanalytics")

print("=" * 75)
print("🚀 AUTOANALYTICS v6.0 - PRODUÇÃO (COM SUPPORT)")
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
    VERSION = "6.0.0"
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
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
    )
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Argon2
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536
    ARGON2_PARALLELISM = 4

    # CORS
    CORS_ORIGINS_STR = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,"
        "http://localhost:3000,http://localhost:5173,https://autoanalytics.site"
    )
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

    # 🔥 Support / Email
    GMAIL_USER = os.getenv("GMAIL_USER", "")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", GMAIL_USER)

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
# 3. DIRETÓRIOS
# ==============================================
def create_directories() -> None:
    for dir_path in [settings.TEMP_DIR, settings.OUTPUT_DIR, settings.MODELS_DIR, settings.DATA_DIR]:
        try:
            os.makedirs(dir_path, exist_ok=True)
            print(f"   ✅ {dir_path}")
        except Exception as e:
            print(f"   ❌ Erro ao criar {dir_path}: {e}")

print("\n📁 Criando diretórios...")
create_directories()

# ==============================================
# 4. FRONTEND
# ==============================================
def check_frontend() -> Dict[str, bool]:
    result = {"available": False, "login": False, "dashboard": False,
              "planos": False, "checkout": False, "js": False}

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

    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        result["js"] = True
        for js_file in ["auth.js", "app.js", "dashboard.js", "payment.js", "pow-client.js"]:
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
# 5. FASTAPI IMPORTS
# ==============================================
print("\n🔧 Importando FastAPI...")
try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import (
        FileResponse, JSONResponse, RedirectResponse, Response, HTMLResponse
    )
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    import uvicorn
    print("   ✅ FastAPI importado")
except ImportError as e:
    print(f"   ❌ Erro ao importar FastAPI: {e}")
    print("   💡 Execute: pip install fastapi uvicorn")
    sys.exit(1)

# ==============================================
# 6. HELPERS GLOBAIS
# ==============================================
_loaded_modules = {
    "auth": False, "registration": False, "payment": False,
    "upload": False, "pow": False, "gemini": False, "support": False,
}

def _now_utc() -> datetime:
    """Timestamp UTC consistente com security.py"""
    return datetime.now(timezone.utc)


def _safe_register_router(
    name: str,
    import_path: str,
    attr: str = "router",
    prefix: str = "",
    critical: bool = False,
) -> bool:
    """
    Registra um router com tratamento de erro padronizado.
    🔥 Reduz duplicação e melhora logs.
    """
    global _loaded_modules
    try:
        module = __import__(import_path, fromlist=[attr])
        router = getattr(module, attr)
        if prefix:
            app.include_router(router, prefix=prefix)
        else:
            app.include_router(router)
        _loaded_modules[name] = True
        print(f"   ✅ {name.capitalize()} Routes registradas ({prefix or 'sem prefixo'})")
        return True
    except ImportError as e:
        level = logger.error if critical else logger.warning
        level(f"❌ {name} Routes não disponível: {e}")
        if critical:
            print(f"   💡 Verifique se {import_path.replace('.', '/')}.py existe")
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao registrar {name}: {e}")
        if settings.DEBUG:
            traceback.print_exc()
        return False

# ==============================================
# 7. LIFESPAN (substitui @app.on_event)
# ==============================================
# Variáveis globais preenchidas durante o startup
pipeline = None
jwt_manager = None
hasher = None
rate_limiter = None
get_current_user = None
get_current_active_user = None
get_current_admin_user = None
get_current_active_superuser = None
set_auth_cookies = None
clear_auth_cookies = None
SessionLocal = None
AUTH_ENABLED = False
process_file_content = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    🔥 Substitui @app.on_event('startup') e @app.on_event('shutdown').
    Ciclo de vida moderno do FastAPI.
    """
    # ========== STARTUP ==========
    print("\n" + "=" * 75)
    print("🚀 INICIALIZANDO SISTEMA...")
    print("=" * 75)

    # 1. Sentinel
    try:
        from backend.observability.sentinel import startup_webhook
        await startup_webhook()
        print("   ✅ Sentinel inicializado")
    except ImportError:
        print("   ⚠️ Sentinel não disponível")
    except Exception as e:
        logger.warning(f"⚠️ Erro no Sentinel: {e}")

    # 2. Promoção
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            init_promotion(db)
            db.close()
        except Exception as e:
            logger.warning(f"⚠️ Erro na promoção: {e}")
    else:
        print("   ⚠️ SessionLocal não disponível - pulando promoção")

    # 3. ML Pipeline
    if pipeline is not None:
        try:
            if hasattr(pipeline, 'initialize'):
                await pipeline.initialize()
                print("   ✅ ML Pipeline inicializado")
        except Exception as e:
            logger.warning(f"⚠️ Erro no ML Pipeline: {e}")
    else:
        print("   ⚠️ Pipeline não disponível - pulando inicialização ML")

    # 4. Redis
    if jwt_manager is not None:
        try:
            if hasattr(jwt_manager, 'init_redis'):
                await jwt_manager.init_redis()
                print("   ✅ Redis inicializado")
        except Exception as e:
            logger.warning(f"⚠️ Erro no Redis: {e}")
    else:
        print("   ⚠️ JWT Manager não disponível - pulando Redis")

    # 5. PoW Service
    try:
        from backend.api.pow_routes import pow_service  # noqa
        print(f"   ✅ PoW Service inicializado")
        print(f"      🛡️  Prevenção replay: Ativa")
        print(f"      🔢 Dificuldade padrão: {settings.POW_DEFAULT_DIFFICULTY}")
    except ImportError:
        print("   ⚠️ PoW Service não disponível")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao inicializar PoW: {e}")

    # 6. 🔥 Support / Email check
    if settings.GMAIL_APP_PASSWORD and settings.GMAIL_USER:
        print(f"   ✅ Support configurado (destino: {settings.SUPPORT_EMAIL})")
    else:
        print("   ⚠️ Support NÃO configurado (faltam GMAIL_USER/GMAIL_APP_PASSWORD)")

    # 7. Verificar rotas registradas
    print("\n🔐 VERIFICANDO ROTAS REGISTRADAS...")
    auth_routes, pow_routes, upload_routes, payment_routes, support_routes = [], [], [], [], []

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
            if '/support' in path:
                support_routes.append(path)

    def _status(lst): return "✅" if lst else "❌"

    print(f"   Auth: {_status(auth_routes)} {len(auth_routes)} rotas")
    if auth_routes:
        for r in auth_routes[:3]:
            print(f"      📍 {r}")

    print(f"   PoW: {_status(pow_routes)} {len(pow_routes)} rotas")
    for r in pow_routes:
        print(f"      📍 {r}")

    print(f"   Upload: {_status(upload_routes)} {len(upload_routes)} rotas")
    for r in upload_routes[:5]:
        print(f"      📍 {r}")

    print(f"   Payments: {_status(payment_routes)} {len(payment_routes)} rotas")

    # 🔥 Support
    print(f"   Support: {_status(support_routes)} {len(support_routes)} rotas")
    for r in support_routes:
        print(f"      📍 {r}")

    # Verificação específica /analyses/history
    if any('/analyses/history' in r for r in upload_routes):
        print(f"   ✅ /analyses/history ENCONTRADA!")
    else:
        print(f"   ❌ /analyses/history NÃO ENCONTRADA!")

    # Banner final
    gemini_status = "✅" if (
        settings.GEMINI_API_KEY and
        settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]
    ) else "❌"
    ml_status = "✅" if (pipeline is not None and getattr(pipeline, 'is_initialized', False)) else "⚠️"
    support_status = "✅" if support_routes else "❌"

    print(f"""
    ╔═══════════════════════════════════════════════════════════════════════════════╗
    ║     🎉 AutoAnalytics v{settings.VERSION} - PRODUÇÃO                          ║
    ╠═══════════════════════════════════════════════════════════════════════════════╣
    ║  🌍 Ambiente: {settings.ENVIRONMENT.upper():<48}  ║
    ║  🤖 Gemini: {gemini_status} | 🤖 ML: {ml_status}                        ║
    ║  🔐 Auth: {_status(auth_routes)} | 🔒 PoW: {_status(pow_routes)} | 📤 Upload: {_status(upload_routes)}      ║
    ║  📩 Support: {support_status} | 💳 MP: {"✅" if settings.MP_ACCESS_TOKEN else "❌"}                            ║
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

    yield  # 🔥 Aqui o app fica rodando

    # ========== SHUTDOWN ==========
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
# 8. APP FASTAPI (com lifespan)
# ==============================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="AutoAnalytics - IA para Oficinas Mecânicas (COM PoW + Support)",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,   # 🔥 moderno
)

# ==============================================
# 9. MIDDLEWARES
# ==============================================
print("\n📊 Configurando middlewares...")

if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["autoanalytics.site", "www.autoanalytics.site", "localhost", "127.0.0.1"]
    )
    print("   ✅ TrustedHostMiddleware ativado")

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
print("   ✅ GZipMiddleware ativado")

try:
    from backend.observability.sentinel import LoggingMiddleware, get_metrics_collector
    metrics_collector = get_metrics_collector()
    app.add_middleware(LoggingMiddleware, metrics=metrics_collector)
    print("   ✅ LoggingMiddleware ativado")
except ImportError:
    print("   ⚠️ Sentinel não disponível")
except Exception as e:
    print(f"   ⚠️ Erro ao ativar Sentinel: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Auth-Required", "X-Redirect-To", "X-Process-Time"]
)
print(f"   ✅ CORS: {len(settings.CORS_ORIGINS)} origens permitidas")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    path = request.url.path
    method = request.method

    if not path.startswith('/static') and not path.startswith('/js') and path not in ['/favicon.ico', '/health']:
        logger.info(f"🌐 {method} {path}")

    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"❌ Erro na requisição {method} {path}: {e}")
        raise

    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

    if response.status_code >= 400 and not path.startswith('/static'):
        logger.warning(f"⚠️ {method} {path} → {response.status_code} ({process_time:.2f}ms)")

    for header, value in settings.SECURITY_HEADERS.items():
        response.headers[header] = value

    return response

# ==============================================
# 10. STATIC FILES
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

# ==============================================
# 11. ROTAS AUXILIARES
# ==============================================
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/health", include_in_schema=False)
async def health_check_simple():
    return Response(content="healthy\n", media_type="text/plain", status_code=200)

async def verify_token_from_request(request: Request) -> Optional[Dict]:
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
        from backend.security import jwt_manager as _jm
        return await _jm.verify_token(token, "access")
    except ImportError:
        return None
    except Exception as e:
        logger.warning(f"⚠️ Erro ao verificar token: {e}")
        return None

# ==============================================
# 12. ROTAS HTML
# ==============================================
print("\n🌐 Configurando rotas HTML...")

def serve_html_page(filename: str, fallback: Optional[str] = None) -> HTMLResponse:
    file_path = FRONTEND_DIR / filename
    if file_path.exists():
        try:
            return HTMLResponse(content=file_path.read_text(encoding="utf-8"), status_code=200)
        except Exception as e:
            logger.error(f"❌ Erro ao ler {filename}: {e}")

    if fallback:
        fb_path = FRONTEND_DIR / fallback
        if fb_path.exists():
            try:
                return HTMLResponse(content=fb_path.read_text(encoding="utf-8"), status_code=200)
            except Exception as e:
                logger.error(f"❌ Erro ao ler fallback: {e}")

    return HTMLResponse(content=f"<h1>Página não encontrada</h1><p>{filename} não disponível</p>", status_code=404)


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
# 13. CARREGAR MÓDULOS DO BACKEND
# ==============================================
print("\n📦 Carregando módulos do backend...")

# 13.1 Database
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

# 13.2 Security
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
        clear_auth_cookies as _clear_auth_cookies,
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

    class MockJWTManager:
        async def verify_token(self, token, token_type="access"): return None
        def create_token_pair(self, data): return {"access_token": "mock", "refresh_token": "mock", "expires_in": 3600}
        async def logout(self, refresh_token, db, access_token=None): return True
        async def refresh_access_token(self, refresh_token, db, old_access_token=None):
            return {"access_token": "mock", "refresh_token": "mock", "expires_in": 3600}
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

# 13.3 Models
try:
    from backend.models import User, Analysis, PromotionControl, Payment, DailyCreditLog  # noqa
    print("   ✅ Models carregados")
except ImportError as e:
    logger.warning(f"⚠️ Models não disponível: {e}")

# 13.4 CRUD
try:
    from backend import crud  # noqa
    print(f"   ✅ CRUD carregado")
except ImportError as e:
    logger.warning(f"⚠️ CRUD não disponível: {e}")

# 13.5 Services
try:
    from backend.services.daily_credits_service import DailyCreditsService  # noqa
    print("   ✅ DailyCreditsService carregado")
except ImportError as e:
    logger.warning(f"⚠️ DailyCreditsService não disponível: {e}")

try:
    from backend.services.credits_consumer import (  # noqa
        can_perform_analysis, consume_analysis_credit, get_credits_display
    )
    print("   ✅ CreditsConsumer carregado")
except ImportError as e:
    logger.warning(f"⚠️ CreditsConsumer não disponível: {e}")

# 13.6 ML Pipeline
print("   🤖 Carregando ML Pipeline...")
try:
    from backend.preprocessing import pipeline as _pipeline, process_file_content as _pfc
    pipeline = _pipeline
    process_file_content = _pfc
    print("   ✅ ML Pipeline carregado")
except ImportError as e:
    logger.warning(f"⚠️ ML Pipeline não disponível: {e}")
    print("   🔧 Usando fallback (ML desabilitado)")

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
        def clear_cache(self): pass

    pipeline = MockPipeline()

    async def _fallback_process_file_content(content, filename):
        return {"success": False, "error": "ML não disponível"}
    process_file_content = _fallback_process_file_content

print("   ✅ Módulos carregados com sucesso!")

# ==============================================
# 14. REGISTRO DE ROUTERS (refatorado)
# ==============================================
print("\n🔐 Registrando rotas...")

# Auth (com fallback registration)
_safe_register_router("auth", "backend.api.auth_routes", prefix="/api/auth")
_safe_register_router("registration", "backend.api.auth", prefix="/api/auth")
_safe_register_router("payment", "backend.api.payment_routes", prefix="/api")

# 🔥 Support (novo)
_safe_register_router("support", "backend.api.support")
# ℹ️  O support.py já define prefix="/api/support" internamente

# 🔥 Upload (crítico)
if _safe_register_router("upload", "backend.api.upload_routes", prefix="/api"):
    print("      POST   /api/upload-multi-analyze  ← 🔥 UPLOAD MÚLTIPLO")
    print("      POST   /api/upload-auto           ← 🔥 UPLOAD ÚNICO")
    print("      GET    /api/analyses/history      ← 🔥 HISTÓRICO")
    print("      GET    /api/analysis/result/{id}  ← 🔥 RESULTADO")
    print("      GET    /api/analyses/stats        ← 📊 ESTATÍSTICAS")
    print("      GET    /api/analyses/export/{fmt} ← 📥 EXPORTAÇÃO")
    print("      GET    /api/report/{analysis_id}  ← 📄 RELATÓRIO")

# PoW
if _safe_register_router("pow", "backend.api.pow_routes", prefix="/api"):
    print("      GET    /api/pow/challenge  ← 🔥 DESAFIO PoW")
    print("      POST   /api/pow/verify     ← 🔥 VERIFICAÇÃO PoW")
    print("      GET    /api/pow/health     ← 🔥 SAÚDE PoW")
    print("      GET    /api/pow/stats      ← 📊 ESTATÍSTICAS PoW")

# Gemini
_safe_register_router("gemini", "backend.api.routes", prefix="/api")

# 🔥 Detalhes do Support
if _loaded_modules["support"]:
    print("      POST   /api/support/send       ← 📩 Formulário de suporte (Gmail)")
    print("      GET    /api/support/health     ← 🩺 Health check do email")
    print("      GET    /api/support/stats      ← 📊 Métricas (admin)")
    print("      POST   /api/support/test       ← 🧪 Envio de teste (admin)")
    print("      GET    /api/support/fallbacks  ← 💾 Mensagens em fallback (admin)")

# ==============================================
# 15. ROTA DE DIAGNÓSTICO
# ==============================================
@app.get("/api/routes", tags=["system"])
async def list_all_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": route.name if hasattr(route, "name") else None,
            })

    filtered = [r for r in routes if not r["path"].startswith("/static") and not r["path"].startswith("/favicon")]

    grouped = {
        "auth": [r for r in filtered if "/auth" in r["path"]],
        "pow": [r for r in filtered if "/pow" in r["path"]],
        "upload": [r for r in filtered if any(x in r["path"] for x in ["/upload", "/analyses", "/analysis", "/report"])],
        "payments": [r for r in filtered if "/payments" in r["path"]],
        "support": [r for r in filtered if "/support" in r["path"]],
        "other": [r for r in filtered if not any(x in r["path"] for x in [
            "/auth", "/pow", "/upload", "/analyses", "/analysis",
            "/report", "/payments", "/support"
        ])],
    }

    return {
        "total": len(filtered),
        "grouped": grouped,
        "upload_routes_loaded": _loaded_modules["upload"],
        "pow_routes_loaded": _loaded_modules["pow"],
        "auth_routes_loaded": _loaded_modules["auth"],
        "support_routes_loaded": _loaded_modules["support"],
    }

# ==============================================
# 16. HEALTH CHECK
# ==============================================
@app.get("/api/health", tags=["system"])
async def health_check():
    ml_status = {}
    if pipeline is not None and hasattr(pipeline, 'get_status'):
        try:
            ml_status = pipeline.get_status()
        except Exception:
            ml_status = {"error": "Erro ao obter status do ML"}

    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append(route.path)

    return {
        "status": "healthy",
        "timestamp": _now_utc().isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "auth_enabled": AUTH_ENABLED,
        "auth_routes_loaded": _loaded_modules["auth"],
        "upload_routes_loaded": _loaded_modules["upload"],
        "pow_enabled": settings.POW_ENABLED,
        "pow_routes_loaded": _loaded_modules["pow"],
        "pow_default_difficulty": settings.POW_DEFAULT_DIFFICULTY,
        "gemini_configured": bool(
            settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]
        ),
        "support_routes_loaded": _loaded_modules["support"],
        "support_configured": bool(settings.GMAIL_USER and settings.GMAIL_APP_PASSWORD),
        "frontend_available": frontend_status["available"],
        "ml_pipeline": ml_status,
        "max_file_size_kb": settings.MAX_FILE_SIZE // 1024,
        "max_files_per_batch": settings.MAX_FILES_PER_BATCH,
        "total_routes": len(routes),
        "timezone": "America/Sao_Paulo (UTC-3)",
    }

# ==============================================
# 17. EXCEPTION HANDLERS
# ==============================================
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
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
    path = request.url.path
    if exc.status_code == 401 and not path.startswith('/api/'):
        return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Exceção não tratada: {exc}")
    if settings.DEBUG:
        traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": "Erro interno do servidor",
            "detail": str(exc) if settings.DEBUG else "Tente novamente mais tarde"
        }
    )

# ==============================================
# 18. PROMOÇÃO
# ==============================================
def init_promotion(db) -> None:
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
# 19. MAIN
# ==============================================
if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 Gemini: {'✅' if settings.GEMINI_API_KEY else '❌'}")
    print(f"🔐 Auth: {'✅' if AUTH_ENABLED else '❌'}")
    print(f"🔒 PoW: {'✅' if _loaded_modules['pow'] else '❌'}")
    print(f"📤 Upload: {'✅' if _loaded_modules['upload'] else '❌'}")
    print(f"📩 Support: {'✅' if _loaded_modules['support'] else '❌'}")
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