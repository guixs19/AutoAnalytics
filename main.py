# main.py (na raiz) - VERSÃO COMPLETAMENTE CORRIGIDA
import sys
import os
from pathlib import Path
from datetime import datetime, date
import secrets
import string
from sqlalchemy.orm import Session
from sqlalchemy import func
import time
import asyncio

print("=" * 60)
print("🚀 AUTOANALYTICS v3.2 - COM GOOGLE GEMINI E CAPTCHA DE NÚMEROS")
print("=" * 60)

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
    VERSION = "3.2.0"
    
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    PORT = int(os.getenv("PORT", "8000"))
    
    BASE_DIR = str(BACKEND_DIR)
    TEMP_DIR = str(BACKEND_DIR / "temp")
    OUTPUT_DIR = str(BACKEND_DIR / "outputs")
    MODELS_DIR = str(BACKEND_DIR / "models")
    DATA_DIR = str(BACKEND_DIR / "data")
    
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "204800"))
    ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls"]
    
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    SECRET_KEY = os.getenv("SECRET_KEY", "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64)))
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536
    ARGON2_PARALLELISM = 4
    
    CAPTCHA_TYPE = os.getenv("CAPTCHA_TYPE", "custom_numbers")
    CAPTCHA_CODE_LENGTH = int(os.getenv("CAPTCHA_CODE_LENGTH", "4"))
    CAPTCHA_EXPIRATION_SECONDS = int(os.getenv("CAPTCHA_EXPIRATION_SECONDS", "120"))
    DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
    
    CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://localhost:3000,http://localhost:5173")
    CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",")]
    
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
    }
    
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
    
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/autoanalytics.db")

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
    
    # Verificar arquivos HTML principais
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
    
    if checkout_html.exists():
        checkout_available = True
        frontend_available = True
        print(f"   ✅ checkout.html")
    
    # Verificar diretório JS
    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        js_files = ["auth.js", "app.js", "dashboard.js", "payment.js", "pow-client.js", "pow-worker.js"]
        for js_file in js_files:
            if (js_dir / js_file).exists():
                print(f"   ✅ js/{js_file}")
            else:
                print(f"   ⚠️ js/{js_file} não encontrado")
    else:
        print(f"   ❌ Pasta js não encontrada em {js_dir}")
    
    # Verificar diretório CSS
    css_dir = FRONTEND_DIR / "css"
    if css_dir.exists():
        if (css_dir / "style.css").exists():
            print(f"   ✅ css/style.css")
    else:
        print(f"   ⚠️ Pasta css não encontrada")
else:
    print(f"   ❌ Frontend NÃO encontrado em: {FRONTEND_DIR}")
    print(f"   🔧 Criando frontend/js para você...")
    os.makedirs(FRONTEND_DIR / "js", exist_ok=True)
    os.makedirs(FRONTEND_DIR / "css", exist_ok=True)

# ==============================================
# IMPORTAR FASTAPI
# ==============================================
print("\n🔧 Importando FastAPI...")

try:
    from fastapi import FastAPI, Request, Depends, HTTPException, Cookie
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
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
    description="Sistema com Google Gemini para oficinas mecânicas - CAPTCHA de números rabiscados",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

app.router.redirect_slashes = False

# ==============================================
# 🔥 MIDDLEWARE DE LOGGING DO SENTINEL
# ==============================================
print("\n📊 Configurando middleware de observabilidade...")

try:
    from backend.observability.sentinel import LoggingMiddleware, get_metrics_collector
    
    # Adicionar middleware de logging
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
        "X-Captcha-ID", 
        "X-Captcha-Expires",
        "X-Auth-Required",
        "X-Redirect-To"
    ]
)
print(f"   ✅ CORS configurado para: {settings.CORS_ORIGINS}")

# ==============================================
# ROTAS PARA EVITAR 307 REDIRECTS
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
# 🔥 MIDDLEWARE DE LOG MANUAL (fallback)
# ==============================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    path = request.url.path
    method = request.method
    
    if not path.startswith('/static') and path not in ['/favicon.ico', '/.well-known/appspecific/com.chrome.devtools.json', '/health']:
        print(f"🌐 [{datetime.now().strftime('%H:%M:%S')}] {method} {path}")
    
    response = await call_next(request)
    
    # DEBUG: Log de erros 404 em arquivos estáticos
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
# ROTAS HTML
# ==============================================
if frontend_available:
    print("\n🌐 Configurando rotas HTML...")
    
    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        from backend.security import jwt_manager
        
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):  # 🔥 LINHA 349 CORRIGIDA!
            token = token.replace("Bearer ", "")
        
        if token:
            payload = await jwt_manager.verify_token_async(token, "access")
            if payload and dashboard_available:
                return FileResponse(str(FRONTEND_DIR / "index.html"))
        
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        
        return JSONResponse({"message": "AutoAnalytics API", "docs": "/api/docs"})
    
    @app.get("/login", include_in_schema=False)
    async def login_page():
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        return JSONResponse({"error": "login.html não encontrado"}, status_code=404)
    
    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_page(request: Request):
        from backend.security import jwt_manager
        
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):  # 🔥 LINHA CORRIGIDA
            token = token.replace("Bearer ", "")
        
        if not token:
            return JSONResponse(status_code=401, content={"error": "Não autenticado", "redirect": "/login"})
        
        payload = await jwt_manager.verify_token_async(token, "access")
        if not payload:
            return JSONResponse(status_code=401, content={"error": "Token inválido", "redirect": "/login"})
        
        if dashboard_available:
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        
        raise HTTPException(status_code=404, detail="Dashboard não encontrado")
    
    @app.get("/planos", include_in_schema=False)
    async def planos_page(request: Request):
        from backend.security import jwt_manager
        
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):  # 🔥 LINHA CORRIGIDA
            token = token.replace("Bearer ", "")
        
        if not token:
            return JSONResponse(status_code=401, content={"error": "Não autenticado", "redirect": "/login"})
        
        payload = await jwt_manager.verify_token_async(token, "access")
        if not payload:
            return JSONResponse(status_code=401, content={"error": "Token inválido", "redirect": "/login"})
        
        if planos_available:
            return FileResponse(str(FRONTEND_DIR / "planos.html"))
        
        raise HTTPException(status_code=404, detail="Planos não encontrado")
    
    @app.get("/checkout", include_in_schema=False)
    async def checkout_page(request: Request):
        from backend.security import jwt_manager
        
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):  # 🔥 LINHA CORRIGIDA
            token = token.replace("Bearer ", "")
        
        if not token:
            return JSONResponse(status_code=401, content={"error": "Não autenticado", "redirect": "/login"})
        
        payload = await jwt_manager.verify_token_async(token, "access")
        if not payload:
            return JSONResponse(status_code=401, content={"error": "Token inválido", "redirect": "/login"})
        
        if checkout_available:
            return FileResponse(str(FRONTEND_DIR / "checkout.html"))
        
        raise HTTPException(status_code=404, detail="Checkout não encontrado")
    
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
# FUNÇÃO AUXILIAR PARA EXTRAIR TOKEN
# ==============================================
async def extract_token(request: Request) -> str:
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):  # 🔥 LINHA CORRIGIDA
        token = token.replace("Bearer ", "")
    if token:
        return token
    
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):  # 🔥 LINHA CORRIGIDA
        return auth_header.replace("Bearer ", "")
    
    token = request.headers.get("X-Access-Token", "")
    if token:
        return token
    
    token = request.query_params.get("token", "")
    if token:
        return token
    
    return None

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
    print("   ⚠️ backend.config.settings não encontrado, usando configurações locais")
    backend_settings = settings

try:
    from backend.database import engine, Base, create_tables, SessionLocal, get_db
    create_tables()
    print("   ✅ Tabelas criadas/verificadas")
except ImportError as e:
    print(f"   ❌ Erro ao importar database: {e}")
    sys.exit(1)

try:
    from backend.security import (
        hasher, jwt_manager, captcha_manager, rate_limiter,
        get_current_user, get_current_active_user, get_current_admin_user,
        set_auth_cookies, clear_auth_cookies
    )
    from backend.models import User, Analysis, PromotionControl
    print("   ✅ Módulos de segurança carregados")
except ImportError as e:
    print(f"   ❌ Erro ao importar security: {e}")
    sys.exit(1)

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

AUTH_ENABLED = True
print("   ✅ Autenticação habilitada")

time.sleep(1)

# ==============================================
# ROTA CAPTCHA
# ==============================================
print("\n🔢 Configurando rota CAPTCHA...")

@app.get("/api/auth/captcha/generate")
async def generate_captcha_direct(request: Request, session_type: str = "login"):
    print(f"🔢 [CAPTCHA] Solicitado para {session_type}")
    try:
        img_bytes, captcha_id = await captcha_manager.generate_captcha_image_async(request, session_type)
        content_type = "image/png" if img_bytes and img_bytes.startswith(b'\x89PNG') else "image/svg+xml"
        return Response(
            content=img_bytes,
            media_type=content_type,
            headers={
                "X-Captcha-ID": captcha_id,
                "X-Captcha-Expires": str(settings.CAPTCHA_EXPIRATION_SECONDS),
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
                "Access-Control-Expose-Headers": "X-Captcha-ID, X-Captcha-Expires"
            }
        )
    except Exception as e:
        print(f"❌ [CAPTCHA] Erro: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar CAPTCHA: {str(e)}")

@app.get("/api/auth/captcha/test", include_in_schema=False)
async def test_captcha():
    try:
        img_bytes, captcha_id = await captcha_manager.generate_captcha_image_async(None, "test")
        return {"success": True, "message": "CAPTCHA funcionando", "captcha_id": captcha_id[:16], "size_bytes": len(img_bytes)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# ==============================================
# 🔥 REGISTRO DE TODAS AS ROTAS DOS ROUTERS (CORRIGIDO)
# ==============================================
print("\n📦 Registrando rotas dos routers...")

try:
    # 🔥 1. Rotas de autenticação - CORRIGIDO
    from backend.api.auth_routes import router as auth_router
    from backend.api.auth import router as registration_router  # ← auth.py
    
    # 🔥 AMBOS COM O MESMO PREFIXO /api/auth
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(registration_router, prefix="/api/auth")  # ← CORRIGIDO: antes era "/api"
    
    print("   ✅ Rotas AUTH: /api/auth/login, /api/auth/register, /api/auth/check-token, /api/auth/refresh, /api/auth/logout, /api/auth/me")
    
    # 2. Rotas de pagamento
    try:
        from backend.api.payment_routes import router as payment_router
        app.include_router(payment_router, prefix="/api")
        print("   ✅ Rotas PAYMENT: /api/payments/*, /api/plans, /api/balance")
    except ImportError as e:
        print(f"   ⚠️ Payment routes não disponível: {e}")
    
    # 3. Rotas de upload múltiplo
    try:
        from backend.api.upload_routes import router as upload_router
        app.include_router(upload_router, prefix="/api")
        print("   ✅ Rotas UPLOAD: /api/upload-auto, /api/status, /api/analyses/history, /api/stats")
    except ImportError as e:
        print(f"   ⚠️ Upload routes não disponível: {e}")
    
    # 4. Rotas gerais com Gemini
    try:
        from backend.api.routes import router as gemini_router
        app.include_router(gemini_router, prefix="/api")
        print("   ✅ Rotas GEMINI: /api/upload, /api/health, /api/test, /api/results")
    except ImportError as e:
        print(f"   ⚠️ Gemini routes não disponível: {e}")
    
    # 5. Rotas Proof of Work
    try:
        from backend.api.pow_routes import router as pow_router
        app.include_router(pow_router, prefix="/api")
        print("   ✅ Rotas POW: /api/pow/*")
    except ImportError:
        print("   ⚠️ POW não disponível")
    
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
        "frontend": {"available": frontend_available, "path": str(FRONTEND_DIR.absolute())}
    }

# ==============================================
# FUNÇÃO PARA INICIALIZAR PROMOÇÃO
# ==============================================
def init_promotion(db: Session):
    from backend.models import PromotionControl
    promo = db.query(PromotionControl).first()
    if not promo:
        promo = PromotionControl()
        db.add(promo)
        db.commit()
        print("   ✅ Promoção Bronze inicializada")
    else:
        print(f"   ✅ Promoção Bronze: {promo.get_remaining_slots()} vagas restantes")

# ==============================================
# 🔥 EVENTO DE STARTUP COM SENTINEL
# ==============================================
@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 60)
    print("🚀 INICIALIZANDO SISTEMA...")
    print("=" * 60)
    
    # 🔥 Inicializar Sentinel (observabilidade)
    try:
        from backend.observability.sentinel import startup_webhook
        await startup_webhook()
        print("   ✅ Sentinel (observabilidade) inicializado")
    except ImportError as e:
        print(f"   ⚠️ Sentinel não disponível: {e}")
    except Exception as e:
        print(f"   ⚠️ Erro ao iniciar Sentinel: {e}")
    
    # Inicializar promoção
    try:
        db = SessionLocal()
        init_promotion(db)
        db.close()
    except Exception as e:
        print(f"   ⚠️ Erro ao inicializar promoção: {e}")
    
    # Iniciar cleanup do CAPTCHA
    try:
        asyncio.create_task(captcha_manager.store.start_cleanup_loop())
        print("   ✅ Cleanup loop do CAPTCHA iniciado")
    except Exception as e:
        print(f"   ⚠️ Erro ao iniciar cleanup do CAPTCHA: {e}")
    
    gemini_status = "✅" if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"] else "❌"
    
    print(f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║     🎉 {settings.APP_NAME} v{settings.VERSION} INICIADO!                         ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║  🌍 Ambiente: {settings.ENVIRONMENT.upper():<45} ║
    ║  🤖 Gemini: {gemini_status} | 🔢 CAPTCHA: {settings.CAPTCHA_TYPE}     ║
    ║  📊 Observabilidade: ✅ ativa                                     ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║  🔗 Endpoints principais:                                          ║
    ║     POST /api/auth/register  ← 🔥 ROTA CORRIGIDA                 ║
    ║     POST /api/auth/login                                         ║
    ║     POST /api/upload-auto (múltiplos arquivos)                    ║
    ║     GET  /api/analyses/history                                    ║
    ║     GET  /api/plans                                               ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║  🌐 Páginas:                                                      ║
    ║     http://localhost:{settings.PORT}/                             ║
    ║     http://localhost:{settings.PORT}/login                        ║
    ║     http://localhost:{settings.PORT}/dashboard                    ║
    ║     http://localhost:{settings.PORT}/planos                       ║
    ║     http://localhost:{settings.PORT}/api/docs                     ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║  📁 Frontend: {FRONTEND_DIR.absolute()}                              ║
    ║  🗄️  Database: {db_path}                                           ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)

# ==============================================
# 🔥 EVENTO DE SHUTDOWN COM SENTINEL
# ==============================================
@app.on_event("shutdown")
async def shutdown_event():
    print("\n🛑 Desligando sistema...")
    
    # 🔥 Finalizar Sentinel
    try:
        from backend.observability.sentinel import shutdown_webhook
        await shutdown_webhook()
        print("   ✅ Sentinel finalizado com sucesso")
    except ImportError as e:
        print(f"   ⚠️ Sentinel não disponível: {e}")
    except Exception as e:
        print(f"   ⚠️ Erro ao finalizar Sentinel: {e}")
    
    # Parar cleanup do CAPTCHA
    try:
        await captcha_manager.store.stop_cleanup_loop()
        print("   ✅ Cleanup loop do CAPTCHA parado")
    except Exception as e:
        print(f"   ⚠️ Erro ao parar cleanup do CAPTCHA: {e}")
    
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
        return JSONResponse(status_code=401, content={"error": exc.detail, "redirect": "/login"})
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

# ==============================================
# MAIN
# ==============================================
if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 IA: Google Gemini")
    print(f"🔢 CAPTCHA: {settings.CAPTCHA_TYPE} ({settings.CAPTCHA_CODE_LENGTH} dígitos)")
    print(f"📊 Observabilidade: ✅ ativa")
    print(f"🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning"
    )