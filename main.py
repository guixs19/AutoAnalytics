# main.py (na raiz) - VERSÃO COMPLETA COM PoW INTEGRADO
import sys
import os
from pathlib import Path
from datetime import datetime
import secrets
import string
from sqlalchemy.orm import Session
import time
import asyncio

print("=" * 60)
print("🚀 AUTOANALYTICS v3.1 - COM GOOGLE GEMINI, CAPTCHA PRÓPRIO E PoW")
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
    DEBUG = True
    PORT = 8000
    BASE_DIR = str(BACKEND_DIR)
    
    TEMP_DIR = str(BACKEND_DIR / "temp")
    OUTPUT_DIR = str(BACKEND_DIR / "outputs")
    MODELS_DIR = str(BACKEND_DIR / "models")
    DATA_DIR = str(BACKEND_DIR / "data")
    
    MAX_FILE_SIZE = 100 * 1024 * 1024
    ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls"]
    
    # Google Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # JWT
    SECRET_KEY = os.getenv("SECRET_KEY", "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64)))
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Argon2
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536
    ARGON2_PARALLELISM = 4
    
    # CAPTCHA próprio
    CAPTCHA_TYPE = "custom"
    CAPTCHA_SITE_KEY = ""
    CAPTCHA_SECRET_KEY = ""
    CAPTCHA_EXPIRATION_SECONDS = 120
    
    # PoW (Proof of Work)
    ENABLE_POW = os.getenv("ENABLE_POW", "true").lower() == "true"
    POW_DEFAULT_COMPLEXITY = int(os.getenv("POW_DEFAULT_COMPLEXITY", "3"))
    POW_MAX_COMPLEXITY = int(os.getenv("POW_MAX_COMPLEXITY", "5"))
    POW_CHALLENGE_TTL = int(os.getenv("POW_CHALLENGE_TTL", "60"))
    
    # CORS
    CORS_ORIGINS = [
        "http://localhost:8000", 
        "http://127.0.0.1:8000", 
        "http://localhost:5500", 
        "http://127.0.0.1:5500",
        "http://localhost:3000"
    ]
    
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
    }
    
    # Mercado Pago
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    
    # Discord
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
    
    # Ambiente
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))

settings = Settings()

# Criar diretórios
for dir_path in [settings.TEMP_DIR, settings.OUTPUT_DIR, settings.MODELS_DIR, settings.DATA_DIR]:
    os.makedirs(dir_path, exist_ok=True)
    print(f"📁 Criado/verificado: {dir_path}")

# Verificar frontend
frontend_available = False
login_available = False
dashboard_available = False

if FRONTEND_DIR.exists():
    print(f"\n✅ FRONTEND ENCONTRADO!")
    
    if (FRONTEND_DIR / "index.html").exists():
        dashboard_available = True
        frontend_available = True
        print(f"✅ index.html (dashboard) encontrado!")
    
    if (FRONTEND_DIR / "login.html").exists():
        login_available = True
        frontend_available = True
        print(f"✅ login.html encontrado!")
    
    if (FRONTEND_DIR / "planos.html").exists():
        print(f"✅ planos.html encontrado!")
    
    if (FRONTEND_DIR / "checkout.html").exists():
        print(f"✅ checkout.html encontrado!")
    
    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        if (js_dir / "auth.js").exists():
            print(f"✅ auth.js encontrado!")
        if (js_dir / "pow-client.js").exists():
            print(f"✅ pow-client.js encontrado!")
        if (js_dir / "pow-worker.js").exists():
            print(f"✅ pow-worker.js encontrado!")
else:
    print(f"\n❌ Frontend não encontrado em: {FRONTEND_DIR}")

# Importar FastAPI
print("\n🔧 Importando FastAPI e dependências...")

try:
    from fastapi import FastAPI, Request, Depends, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
    import uvicorn
    print("✅ FastAPI importado")
except ImportError as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)

# Inicializar app
app = FastAPI(
    title=settings.APP_NAME,
    version="3.1.0",
    description="Sistema com Google Gemini para oficinas mecânicas - CAPTCHA próprio + PoW silencioso",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ==============================================
# MIDDLEWARE - CORS ATUALIZADO
# ==============================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Captcha-ID", 
        "X-Captcha-Expires",
        "X-PoW-Prefix",
        "X-PoW-Nonce",
        "X-PoW-Complexity"
    ]
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in settings.SECURITY_HEADERS.items():
        response.headers[header] = value
    return response

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    path = request.url.path
    if not path.startswith('/static'):
        print(f"🌐 [{datetime.now().strftime('%H:%M:%S')}] {request.method} {path}")
    response = await call_next(request)
    if response.status_code >= 400 and not path.startswith('/static'):
        process_time = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   ⚠️ Status: {response.status_code} | Tempo: {process_time:.2f}ms")
    return response

# ==============================================
# ARQUIVOS ESTÁTICOS
# ==============================================
if frontend_available:
    print("\n🌐 CONFIGURANDO ARQUIVOS ESTÁTICOS...")
    
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    print("✅ Arquivos estáticos montados em /static")
    
    # Servir arquivos JS específicos
    js_dir = FRONTEND_DIR / "js"
    
    @app.get("/js/auth.js", include_in_schema=False)
    async def serve_auth_js():
        auth_js_path = js_dir / "auth.js"
        if auth_js_path.exists():
            return FileResponse(auth_js_path, media_type="application/javascript")
        raise HTTPException(status_code=404, detail="auth.js não encontrado")
    
    @app.get("/js/pow-client.js", include_in_schema=False)
    async def serve_pow_client_js():
        pow_client_path = js_dir / "pow-client.js"
        if pow_client_path.exists():
            return FileResponse(pow_client_path, media_type="application/javascript")
        return Response(status_code=204)  # Não encontrado, mas não quebra
    
    @app.get("/js/pow-worker.js", include_in_schema=False)
    async def serve_pow_worker_js():
        pow_worker_path = js_dir / "pow-worker.js"
        if pow_worker_path.exists():
            return FileResponse(pow_worker_path, media_type="application/javascript")
        return Response(status_code=204)
    
    @app.get("/js/app.js", include_in_schema=False)
    async def serve_app_js():
        app_js_path = js_dir / "app.js"
        if app_js_path.exists():
            return FileResponse(app_js_path, media_type="application/javascript")
        raise HTTPException(status_code=404, detail="app.js não encontrado")
    
    @app.get("/js/dashboard.js", include_in_schema=False)
    async def serve_dashboard_js():
        dashboard_js_path = js_dir / "dashboard.js"
        if dashboard_js_path.exists():
            return FileResponse(dashboard_js_path, media_type="application/javascript")
        raise HTTPException(status_code=404, detail="dashboard.js não encontrado")
    
    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if token and dashboard_available:
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        elif login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        return JSONResponse({"message": "AutoAnalytics API com Gemini e PoW", "docs": "/api/docs"})
    
    @app.get("/login", include_in_schema=False)
    async def login_page():
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        return RedirectResponse(url="/")
    
    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_page(request: Request):
        token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return RedirectResponse(url="/login")
        if dashboard_available:
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        raise HTTPException(status_code=404, detail="Dashboard não encontrado")
    
    @app.get("/planos", include_in_schema=False)
    async def planos_page(request: Request):
        token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return RedirectResponse(url="/login")
        planos_path = FRONTEND_DIR / "planos.html"
        if planos_path.exists():
            return FileResponse(planos_path)
        raise HTTPException(status_code=404, detail="Planos não encontrado")
    
    @app.get("/checkout", include_in_schema=False)
    async def checkout_page(request: Request):
        token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return RedirectResponse(url="/login")
        checkout_path = FRONTEND_DIR / "checkout.html"
        if checkout_path.exists():
            return FileResponse(checkout_path)
        raise HTTPException(status_code=404, detail="Checkout não encontrado")
    
    print("✅ Rotas HTML configuradas")
    print("✅ Rotas de arquivos JS configuradas")

# ==============================================
# CARREGAR MÓDULOS
# ==============================================
print("\n📦 Carregando módulos...")

if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY in ["", "opcional", "sua_chave_aqui"]:
    print("⚠️ ALERTA: GEMINI_API_KEY não configurada!")
else:
    print(f"✅ Gemini API Key configurada (modelo: {settings.GEMINI_MODEL})")

db_path = PROJECT_ROOT / "autoanalytics.db"
print(f"🗄️ Banco de dados: {db_path}")

# Variável global para o pow_service
pow_service = None

try:
    from backend.config import settings as backend_settings
    for key, value in settings.__dict__.items():
        if not key.startswith('_'):
            setattr(backend_settings, key, value)
    
    from backend.database import engine, Base, create_tables, SessionLocal, get_db
    create_tables()
    print("✅ Tabelas criadas/verificadas")
    
    from backend.security import (
        hasher, jwt_manager, captcha_manager, rate_limiter,
        get_current_user, get_current_active_user, get_current_admin_user,
        set_auth_cookies, clear_auth_cookies
    )
    print("✅ Módulos de segurança carregados")
    
    # Importar PoW service se disponível
    try:
        from backend.services.pow_service import pow_service as _pow_service
        pow_service = _pow_service
        print(f"✅ PoW Service carregado (complexidade: {settings.POW_DEFAULT_COMPLEXITY})")
    except ImportError as e:
        print(f"⚠️ PoW Service não disponível: {e}")
    except Exception as e:
        print(f"⚠️ Erro ao carregar PoW Service: {e}")
    
    from backend.services.daily_credits_service import DailyCreditsService
    print("✅ Módulo de créditos diários carregado")
    
    AUTH_ENABLED = True
    
except Exception as e:
    print(f"❌ Erro ao carregar módulos: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

time.sleep(1)

# ==============================================
# REGISTRO DE ROTAS
# ==============================================
print("\n📦 Registrando rotas da API...")

try:
    from backend.api import auth_routes
    from backend.api import routes
    from backend.api import payment_routes
    
    if hasattr(auth_routes, 'captcha_manager'):
        auth_routes.captcha_manager = captcha_manager
    
    app.include_router(auth_routes.router, prefix="/api/auth", tags=["authentication"])
    print("✅ Rotas de autenticação: /api/auth/*")
    
    app.include_router(routes.router, prefix="/api", tags=["api"])
    print("✅ Rotas da API: /api/*")
    
    app.include_router(payment_routes.router, prefix="/api", tags=["payments"])
    print("✅ Rotas de pagamento: /api/payments/*")
    
    # Registrar rotas PoW se disponível
    if pow_service:
        try:
            from backend.api import pow_routes
            app.include_router(pow_routes.router, prefix="/api", tags=["proof-of-work"])
            print("✅ Rotas PoW: /api/pow/*")
        except ImportError:
            print("⚠️ Rotas PoW não disponíveis (pow_routes não encontrado)")
        except Exception as e:
            print(f"⚠️ Erro ao registrar rotas PoW: {e}")
    
    print("✅ Sistema de rotas configurado")
    
except Exception as e:
    print(f"❌ Erro ao registrar rotas: {e}")
    import traceback
    traceback.print_exc()

# ==============================================
# MIDDLEWARE PoW (se disponível)
# ==============================================
if settings.ENABLE_POW:
    try:
        from backend.middleware.pow_middleware import PoWMiddleware
        app.add_middleware(PoWMiddleware, enabled=settings.ENABLE_POW)
        print(f"✅ PoW Middleware ativado (complexidade: {settings.POW_DEFAULT_COMPLEXITY})")
    except ImportError:
        print("⚠️ PoW Middleware não disponível (pow_middleware não encontrado)")
    except Exception as e:
        print(f"⚠️ Erro ao ativar PoW Middleware: {e}")
else:
    print("⚠️ PoW desabilitado via configuração (ENABLE_POW=false)")

# ==============================================
# ROTAS DA API
# ==============================================

@app.get("/api/user/credits", tags=["user"])
async def get_user_credits(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        service = DailyCreditsService()
        credit_status = service.get_user_credit_status(db, current_user.id)
        
        return {
            "success": True,
            "credits": credit_status["current_credits"],
            "streak_days": credit_status["streak_days"],
            "received_today": credit_status["received_today"],
            "next_credit_in": credit_status.get("next_credit_in", "Amanhã"),
            "total_earned": credit_status["total_earned_all_time"]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/health", tags=["system"])
async def health_check():
    pow_status = "enabled" if (settings.ENABLE_POW and pow_service) else "disabled"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.1.0",
        "ai_provider": "Google Gemini",
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]),
        "gemini_model": settings.GEMINI_MODEL if settings.GEMINI_API_KEY else None,
        "security": {
            "enabled": True,
            "argon2": True,
            "jwt": {
                "access_expiry": f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes",
                "refresh_expiry": f"{settings.REFRESH_TOKEN_EXPIRE_DAYS} days"
            },
            "captcha": {
                "type": "CUSTOM_MATH",
                "expiration_seconds": settings.CAPTCHA_EXPIRATION_SECONDS,
                "single_use": True,
                "auto_invalidate": True,
                "challenge": "mathematical_sum (ex: 5 + 3 = ?)"
            },
            "pow": {
                "enabled": pow_status == "enabled",
                "default_complexity": settings.POW_DEFAULT_COMPLEXITY,
                "max_complexity": settings.POW_MAX_COMPLEXITY,
                "challenge_ttl": settings.POW_CHALLENGE_TTL,
                "description": "Silent Proof of Work for API protection"
            }
        },
        "database": "connected" if db_path.exists() else "disconnected",
        "frontend": {
            "available": frontend_available,
            "login": login_available,
            "dashboard": dashboard_available
        }
    }

@app.get("/api/security/info", tags=["security"])
async def security_info():
    pow_complexity = settings.POW_DEFAULT_COMPLEXITY
    if pow_service and hasattr(pow_service, 'default_complexity'):
        pow_complexity = pow_service.default_complexity
    
    return {
        "security_layers": {
            "password_hashing": {
                "algorithm": "Argon2id",
                "time_cost": settings.ARGON2_TIME_COST,
                "memory_cost": settings.ARGON2_MEMORY_COST
            },
            "jwt": {
                "algorithm": settings.ALGORITHM,
                "access_expiry_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
                "refresh_expiry_days": settings.REFRESH_TOKEN_EXPIRE_DAYS
            },
            "captcha": {
                "type": "CUSTOM_MATH",
                "challenge_type": "simple_sum",
                "expiration_seconds": settings.CAPTCHA_EXPIRATION_SECONDS,
                "expiration_minutes": 2,
                "single_use": True,
                "auto_invalidate_on_refresh": True,
                "example": "5 + 3 = ? (resposta: 8)"
            },
            "pow": {
                "type": "PROOF_OF_WORK",
                "enabled": settings.ENABLE_POW,
                "default_complexity": pow_complexity,
                "algorithm": "SHA-256",
                "validation": "prefix_hash_matching",
                "client": "Web Worker (non-blocking)",
                "protected_endpoints": [
                    "/api/upload",
                    "/api/upload-auto",
                    "/api/process",
                    "/api/predict",
                    "/api/generate-report"
                ]
            }
        },
        "ai_provider": "Google Gemini",
        "status": "active",
        "pow_available": pow_service is not None
    }

@app.get("/api/captcha/stats", tags=["security"])
async def captcha_stats(current_user = Depends(get_current_admin_user)):
    stats = captcha_manager.get_stats()
    return {"success": True, "stats": stats}

@app.get("/api/pow/stats", tags=["security"])
async def pow_stats(current_user = Depends(get_current_admin_user)):
    """Estatísticas do PoW (apenas admin)"""
    if pow_service and hasattr(pow_service, 'get_stats'):
        stats = pow_service.get_stats()
        return {"success": True, "stats": stats}
    return {"success": True, "stats": {"message": "PoW não disponível", "enabled": settings.ENABLE_POW}}

# ==============================================
# EVENTO DE INICIALIZAÇÃO
# ==============================================
@app.on_event("startup")
async def startup_event():
    print("\n🚀 Inicializando sistema...")
    
    try:
        asyncio.create_task(captcha_manager.store.start_cleanup_loop())
        print("✅ Cleanup loop do CAPTCHA iniciado")
    except Exception as e:
        print(f"⚠️ Erro ao iniciar cleanup do CAPTCHA: {e}")
    
    try:
        await jwt_manager.init_redis()
        print("✅ Redis (JWT) inicializado")
    except Exception as e:
        print(f"⚠️ Redis (JWT) não disponível: {e}")
    
    try:
        await rate_limiter.init_redis()
        print("✅ Redis (Rate Limiting) inicializado")
    except Exception as e:
        print(f"⚠️ Redis (Rate Limiting) não disponível: {e}")
    
    # Inicializar PoW service (se disponível)
    if pow_service:
        print(f"🧮 PoW Service ativo: complexity={settings.POW_DEFAULT_COMPLEXITY}, max={settings.POW_MAX_COMPLEXITY}")
    
    print("🧠 Inicializando modelos de Machine Learning...")
    try:
        from backend.ml.predict import predictor
        await predictor.load_or_train_models()
        print("✅ Modelos de ML carregados com sucesso!")
    except Exception as e:
        print(f"⚠️ Erro ao carregar modelos: {e}")
    
    try:
        from backend.gemini import gemini_service
        if gemini_service.api_key:
            print(f"✅ Google Gemini pronto para uso (modelo: {gemini_service.MODEL_NAME})")
        else:
            print("⚠️ Google Gemini não configurado")
    except Exception as e:
        print(f"⚠️ Erro ao verificar Gemini: {e}")
    
    captcha_stats = captcha_manager.get_stats()
    print(f"📊 CAPTCHA Store: {captcha_stats['total_active']} ativos, {captcha_stats['total_sessions']} sessões")
    
    gemini_status = "✅ CONFIGURADO" if (settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]) else "❌ NÃO CONFIGURADO"
    pow_status = "✅ ATIVO" if (settings.ENABLE_POW and pow_service) else "❌ DESABILITADO"
    
    print(f"""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                    🎉 {settings.APP_NAME} v3.1 INICIADO!                              ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🤖 GOOGLE GEMINI: {gemini_status:<59} ║
    ║     Modelo: {settings.GEMINI_MODEL if settings.GEMINI_API_KEY else 'N/A':<59} ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🔐 SEGURANÇA:                                                                ║
    ║     🔑 Argon2: ✅                                                             ║
    ║     🎫 JWT: ✅ (15min access, 7d refresh)                                     ║
    ║     🖼️ CAPTCHA: ✅ (Matemático - soma simples)                                ║
    ║        └─ 2 minutos de validade                                              ║
    ║        └─ Uso único                                                           ║
    ║     🧮 PoW: {pow_status:<58} ║
    ║        └─ Complexidade: {settings.POW_DEFAULT_COMPLEXITY} zeros ( ~{settings.POW_DEFAULT_COMPLEXITY * 100}ms )   ║
    ║        └─ Protege: uploads, análises, previsões                               ║
    ║     ⏱️ Rate Limiting: ✅                                                      ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🔗 URLs:                                                                    ║
    ║     🌐 Login: http://localhost:{settings.PORT}/login                         ║
    ║     📊 Dashboard: http://localhost:{settings.PORT}/dashboard                 ║
    ║     💳 Planos: http://localhost:{settings.PORT}/planos                       ║
    ║     📚 API Docs: http://localhost:{settings.PORT}/api/docs                   ║
    ║     🔐 Security Info: http://localhost:{settings.PORT}/api/security/info     ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S'):<71} ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """)

@app.on_event("shutdown")
async def shutdown_event():
    print("\n🛑 Desligando sistema...")
    
    try:
        await captcha_manager.store.stop_cleanup_loop()
        print("✅ Cleanup loop do CAPTCHA parado")
    except Exception as e:
        print(f"⚠️ Erro ao parar cleanup: {e}")
    
    try:
        if jwt_manager.redis_client:
            await jwt_manager.redis_client.close()
            print("✅ Conexão Redis fechada")
    except Exception as e:
        print(f"⚠️ Erro ao fechar Redis: {e}")
    
    print("👋 Sistema desligado com sucesso!")

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    if request.url.path.startswith('/api/'):
        return JSONResponse(
            status_code=404,
            content={
                "error": "Endpoint não encontrado",
                "path": request.url.path,
                "suggestions": ["/api/docs", "/api/health", "/api/auth/login", "/api/security/info"]
            }
        )
    if login_available and not request.url.path.startswith('/static'):
        return RedirectResponse(url="/login")
    return JSONResponse(status_code=404, content={"error": "Página não encontrada"})

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        if not request.url.path.startswith(('/api', '/static')):
            return RedirectResponse(url="/login")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 IA: Google Gemini")
    print(f"🔐 CAPTCHA: Matemático (soma simples - 2min validade)")
    print(f"🧮 PoW: {'ATIVO' if settings.ENABLE_POW else 'DESABILITADO'} (proteção silenciosa)")
    print("🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )