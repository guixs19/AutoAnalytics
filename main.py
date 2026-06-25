 # main.py (na raiz) - VERSÃO PRODUÇÃO v3.8 (ROTAS HTML CORRIGIDAS)
"""
AutoAnalytics - Servidor Principal
================================================================================
🔥 CORREÇÕES v3.8:
- ✅ Rotas HTML corrigidas para servir os arquivos corretamente
- ✅ /login → login.html
- ✅ /planos → planos.html
- ✅ /dashboard → index.html
- ✅ / → index.html (com verificação de token)
- ✅ Fallback para rotas não encontradas
- ✅ Caminhos padronizados para servir arquivos estáticos
================================================================================
"""

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
print("🚀 AUTOANALYTICS v3.8 - PRODUÇÃO")
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
    VERSION = "3.8.0"
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
    from fastapi import FastAPI, Request, HTTPException
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
        return None
    
    try:
        from backend.security import jwt_manager
        return await jwt_manager.verify_token(token, "access")
    except ImportError:
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
    # Verifica se já está autenticado
    payload = await verify_token_from_request(request)
    if payload and frontend_status["dashboard"]:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    # Verifica se o arquivo existe
    login_path = FRONTEND_DIR / "login.html"
    if login_path.exists():
        try:
            content = login_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler login.html: {e}")
    
    return JSONResponse(status_code=404, content={"error": "login.html não encontrado"})


# 2. Página de Planos
@app.get("/planos", include_in_schema=False)
async def get_planos_page(request: Request):
    """Serve a página de planos"""
    # Verifica autenticação
    payload = await verify_token_from_request(request)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    
    # Tenta servir planos.html
    planos_path = FRONTEND_DIR / "planos.html"
    if planos_path.exists():
        try:
            content = planos_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler planos.html: {e}")
    
    # Fallback: index.html
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        try:
            content = index_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            print(f"   ❌ Erro ao ler index.html: {e}")
    
    return JSONResponse(status_code=404, content={"error": "Página de planos não encontrada"})


# 3. Página de Checkout
@app.get("/checkout", include_in_schema=False)
async def get_checkout_page(request: Request):
    """Serve a página de checkout"""
    # Verifica autenticação
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
    # Verifica autenticação
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
    # Verifica se está autenticado
    payload = await verify_token_from_request(request)
    
    if payload and frontend_status["dashboard"]:
        # Se autenticado, vai para o dashboard
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            try:
                content = index_path.read_text(encoding="utf-8")
                return HTMLResponse(content=content)
            except Exception as e:
                print(f"   ❌ Erro ao ler index.html: {e}")
    
    # Se não autenticado, vai para o login
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
# 11. IMPORTAÇÃO DE MÓDULOS (COM FALLBACK SEGURO)
# ==============================================

# ================================================
# 🔥 OUTRAS ROTAS (COM FALLBACK)
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

# PoW
try:
    from backend.api.pow_routes import router as pow_router
    app.include_router(pow_router, prefix="/api")
    print("   ✅ PoW Routes (/api/pow/*)")
except ImportError as e:
    print(f"   ⚠️ PoW Routes não disponível: {e}")
except Exception as e:
    print(f"   ⚠️ Erro ao registrar PoW: {e}")

# ==============================================
# 🔥 VERIFICAÇÃO FINAL
# ==============================================

print("\n📋 Verificando rotas registradas...")
auth_routes_found = []
for route in app.routes:
    if hasattr(route, 'path') and '/auth' in route.path:
        auth_routes_found.append(route.path)

if auth_routes_found:
    print(f"   ✅ Rotas /auth encontradas: {len(auth_routes_found)}")
    for r in auth_routes_found[:10]:
        print(f"      📍 {r}")
else:
    print("   ❌ NENHUMA ROTA /auth ENCONTRADA!")
    print("   ⚠️ O LOGIN NÃO VAI FUNCIONAR!")

print("   ✅ Registro de rotas concluído!")

# ==============================================
# 14. HEALTH CHECK
# ==============================================

@app.get("/api/health", tags=["system"])
async def health_check():
    """Verificação de saúde do sistema"""
    ml_status = {}
    if hasattr(pipeline, 'get_status'):
        try:
            ml_status = pipeline.get_status()
        except Exception:
            ml_status = {"error": "Erro ao obter status do ML"}
    
    # Verificar se auth está funcionando
    auth_status = "✅" if AUTH_ENABLED else "❌"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "auth_enabled": AUTH_ENABLED,
        "auth_status": auth_status,
        "auth_routes_registered": len([r for r in app.routes if hasattr(r, 'path') and '/auth' in r.path]) > 0,
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]),
        "frontend_available": frontend_status["available"],
        "ml_pipeline": ml_status,
        "max_file_size_kb": settings.MAX_FILE_SIZE // 1024,
        "max_files_per_batch": settings.MAX_FILES_PER_BATCH,
        "timezone": "America/Sao_Paulo (UTC-3)"
    }

# ==============================================
# 15. INICIALIZAÇÃO DA PROMOÇÃO
# ==============================================

def init_promotion(db) -> None:
    """
    Inicializa a promoção de fundador se não existir
    🔥 CORRIGIDO: Removeu a tipagem : Session para evitar erro de importação
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
# 16. STARTUP
# ==============================================

@app.on_event("startup")
async def startup_event():
    """Evento executado na inicialização do servidor"""
    print("\n" + "=" * 75)
    print("🚀 INICIALIZANDO SISTEMA...")
    print("=" * 75)
    
    # 16.1 Sentinel
    try:
        from backend.observability.sentinel import startup_webhook
        await startup_webhook()
        print("   ✅ Sentinel inicializado")
    except ImportError:
        print("   ⚠️ Sentinel não disponível")
    except Exception as e:
        print(f"   ⚠️ Erro no Sentinel: {e}")
    
    # 16.2 Promoção
    try:
        db = SessionLocal()
        init_promotion(db)
        db.close()
    except Exception as e:
        print(f"   ⚠️ Erro na promoção: {e}")
    
    # 16.3 ML Pipeline
    try:
        if hasattr(pipeline, 'initialize'):
            await pipeline.initialize()
            print("   ✅ ML Pipeline inicializado")
    except Exception as e:
        print(f"   ⚠️ Erro no ML Pipeline: {e}")
    
    # 16.4 Redis
    try:
        if jwt_manager and hasattr(jwt_manager, 'init_redis'):
            await jwt_manager.init_redis()
            print("   ✅ Redis inicializado")
    except Exception as e:
        print(f"   ⚠️ Erro no Redis: {e}")
    
    # 16.5 Verificar rotas de auth
    print("\n🔐 Verificando rotas registradas...")
    auth_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and '/auth' in route.path:
            auth_routes.append(route.path)
    
    if auth_routes:
        print(f"   ✅ Rotas /auth encontradas: {len(auth_routes)}")
        for r in auth_routes:
            print(f"      📍 {r}")
    else:
        print("   ❌ NENHUMA ROTA /auth ENCONTRADA!")
        print("   ⚠️ O LOGIN NÃO VAI FUNCIONAR!")
    
    # 16.6 Status Final
    gemini_status = "✅" if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"] else "❌"
    ml_status = "✅" if (hasattr(pipeline, 'is_initialized') and pipeline.is_initialized) else "⚠️"
    auth_ok = "✅" if auth_routes else "❌"
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════════════════════════╗
    ║     🎉 AutoAnalytics v{settings.VERSION} - PRODUÇÃO                           ║
    ╠═══════════════════════════════════════════════════════════════════════════════╣
    ║  🌍 Ambiente: {settings.ENVIRONMENT.upper():<48}  ║
    ║  🤖 Gemini: {gemini_status} | 🤖 ML: {ml_status}                        ║
    ║  🔐 Auth: {auth_ok} | 🌐 Frontend: {"✅" if frontend_status["available"] else "❌"}          ║
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
# 17. SHUTDOWN
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
        if hasattr(pipeline, 'clear_cache'):
            pipeline.clear_cache()
            print("   ✅ Cache ML limpo")
    except Exception as e:
        print(f"   ⚠️ Erro ao limpar cache: {e}")
    
    print("👋 Sistema desligado!")

# ==============================================
# 18. EXCEPTION HANDLERS
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
# 19. MAIN
# ==============================================

if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 Gemini: {'✅' if settings.GEMINI_API_KEY else '❌'}")
    print(f"🤖 ML: {'✅' if hasattr(pipeline, 'is_initialized') else '⚠️'}")
    print(f"🔐 Auth: {'✅' if AUTH_ENABLED else '❌'}")
    print(f"💳 Mercado Pago: {'✅' if settings.MP_ACCESS_TOKEN else '❌'}")
    print(f"🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning"
    )