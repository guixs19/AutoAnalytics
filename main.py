# main.py (na raiz) - VERSÃO CORRIGIDA COM ARQUITETURA SAAS
import sys
import os
from pathlib import Path
from datetime import datetime
import secrets
import string
from sqlalchemy.orm import Session

print("=" * 60)
print("🚀 AUTOANALYTICS v2.0 - SERVIDOR COMPLETO COM JWT E PAGAMENTOS")
print("=" * 60)

# Configurar paths
PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"  # ou "front" se preferir

print(f"📂 Raiz do projeto: {PROJECT_ROOT}")
print(f"📂 Pasta backend: {BACKEND_DIR}")
print(f"🌐 Pasta frontend: {FRONTEND_DIR}")

# Verificar se backend existe
if not BACKEND_DIR.exists():
    print(f"❌ ERRO: Pasta 'backend' não encontrada!")
    print(f"📍 Procurando em: {BACKEND_DIR}")
    sys.exit(1)

# Adicionar ao sys.path
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

print(f"🔧 Python path configurado")
for i, p in enumerate(sys.path[:3], 1):
    print(f"  {i}. {p}")

# ==============================================
# CONFIGURAÇÕES COM SEGURANÇA
# ==============================================
class Settings:
    # App
    APP_NAME = "AutoAnalytics"
    DEBUG = True
    PORT = 8000
    BASE_DIR = str(BACKEND_DIR)
    
    # Paths
    TEMP_DIR = str(BACKEND_DIR / "temp")
    OUTPUT_DIR = str(BACKEND_DIR / "outputs")
    MODELS_DIR = str(BACKEND_DIR / "models")
    DATA_DIR = str(BACKEND_DIR / "data")
    
    # File limits
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls"]
    
    # Flowise / IA
    FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY", "")
    FLOWISE_URL = os.getenv("FLOWISE_URL", "https://cloud.flowiseai.com/api/v1/prediction/07284d0d-4185-425a-b1e3-3ee3f187ab32")
    
    # ========== 🔐 SEGURANÇA ==========
    # JWT
    SECRET_KEY = os.getenv("SECRET_KEY", "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64)))
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Argon2
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536  # 64 MB
    ARGON2_PARALLELISM = 4
    
    # CAPTCHA
    CAPTCHA_TYPE = os.getenv("CAPTCHA_TYPE", "recaptcha_v2")
    CAPTCHA_SITE_KEY = os.getenv("CAPTCHA_SITE_KEY", "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI")
    CAPTCHA_SECRET_KEY = os.getenv("CAPTCHA_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe")
    
    # Rate Limiting
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    # CORS
    CORS_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
    
    # Headers de segurança
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    }
    
    # ========== 💰 MERCADO PAGO ==========
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")
    
    # ========== 💎 DISCORD WEBHOOK ==========
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")

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
    
    index_path = FRONTEND_DIR / "index.html"
    login_path = FRONTEND_DIR / "login.html"
    planos_path = FRONTEND_DIR / "planos.html"
    checkout_path = FRONTEND_DIR / "checkout.html"
    
    if index_path.exists():
        print(f"✅ index.html (dashboard) encontrado!")
        dashboard_available = True
        frontend_available = True
    
    if login_path.exists():
        print(f"✅ login.html encontrado!")
        login_available = True
        frontend_available = True
    
    if planos_path.exists():
        print(f"✅ planos.html encontrado!")
    
    if checkout_path.exists():
        print(f"✅ checkout.html encontrado!")
    
    if not frontend_available:
        print(f"❌ Nenhum HTML encontrado no frontend!")
else:
    print(f"\n❌ Frontend não encontrado em: {FRONTEND_DIR}")

# Agora importar FastAPI
print("\n🔧 Importando FastAPI e dependências...")

try:
    from fastapi import FastAPI, APIRouter, Request, Depends, HTTPException, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse
    from fastapi.security import OAuth2PasswordBearer
    import uvicorn
    
    print("✅ FastAPI importado com sucesso!")
    
except ImportError as e:
    print(f"❌ Erro importando FastAPI: {e}")
    print("📦 Instale as dependências: pip install fastapi uvicorn")
    sys.exit(1)

# Inicializar app
app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="Sistema inteligente para oficinas mecânicas com autenticação JWT e sistema de créditos",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ==============================================
# MIDDLEWARE DE SEGURANÇA
# ==============================================

# CORS configurado
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para headers de segurança
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Adicionar headers de segurança
    for header, value in settings.SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response

# ==============================================
# ARQUITETURA CORRETA DE ARQUIVOS ESTÁTICOS
# ==============================================
if frontend_available:
    print("\n🌐 CONFIGURANDO ARQUIVOS ESTÁTICOS...")
    
    # 1️⃣ CORRETO: Montar arquivos estáticos com StaticFiles
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    print("✅ Arquivos estáticos montados em /static")
    print("   📁 Servindo: JS, CSS, imagens e HTMLs")
    
    # 2️⃣ Rotas específicas para páginas HTML (SEM conflito com API)
    
    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        """Página inicial - redireciona baseado em autenticação"""
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if token and dashboard_available:
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        elif login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        else:
            return JSONResponse({"message": "AutoAnalytics API", "docs": "/api/docs"})
    
    @app.get("/login", include_in_schema=False)
    async def login_page():
        """Página de login"""
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        return RedirectResponse(url="/")
    
    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_page(request: Request):
        """Dashboard protegido"""
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return RedirectResponse(url="/login")
        
        if dashboard_available:
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        raise HTTPException(status_code=404, detail="Dashboard não encontrado")
    
    @app.get("/planos", include_in_schema=False)
    async def planos_page(request: Request):
        """Página de planos protegida"""
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return RedirectResponse(url="/login")
        
        planos_path = FRONTEND_DIR / "planos.html"
        if planos_path.exists():
            return FileResponse(planos_path)
        raise HTTPException(status_code=404, detail="Planos não encontrado")
    
    @app.get("/checkout", include_in_schema=False)
    async def checkout_page(request: Request):
        """Página de checkout protegida"""
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return RedirectResponse(url="/login")
        
        checkout_path = FRONTEND_DIR / "checkout.html"
        if checkout_path.exists():
            return FileResponse(checkout_path)
        raise HTTPException(status_code=404, detail="Checkout não encontrado")
    
    # 3️⃣ IMPORTANTE: NÃO temos mais a rota genérica /{file_path:path}
    # Isso evita conflitos com as rotas da API!
    
    print("✅ Rotas HTML configuradas sem conflito com API")

# ==============================================
# API FALLBACK (se frontend não disponível)
# ==============================================
if not frontend_available:
    @app.get("/", response_class=JSONResponse)
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": "2.0.0",
            "status": "online",
            "message": "Frontend não encontrado. Servindo apenas API.",
            "endpoints": {
                "api_docs": "/api/docs",
                "auth_login": "/api/auth/login",
                "auth_register": "/api/auth/register",
                "payments_plans": "/api/payments/plans",
                "credits_status": "/api/user/credits"
            }
        }

# ==============================================
# CARREGAR MÓDULOS DE SEGURANÇA E AUTENTICAÇÃO
# ==============================================
print("\n📦 Carregando módulos de segurança e autenticação...")

# Inicializar banco de dados
db_path = PROJECT_ROOT / "autoanalytics.db"
print(f"🗄️  Banco de dados: {db_path}")

try:
    # Importar settings do backend.config primeiro
    from backend.config import settings as backend_settings
    
    # Atualizar settings do backend com nossas configurações
    for key, value in settings.__dict__.items():
        if not key.startswith('_'):
            setattr(backend_settings, key, value)
    
    print("✅ Configurações sincronizadas")
    
    # Importar database
    from backend.database import engine, Base, create_tables, SessionLocal, get_db
    
    # Criar tabelas
    create_tables()
    print("✅ Tabelas criadas/verificadas")
    
    # Importar security
    from backend.security import (
        hasher,
        jwt_manager,
        captcha_manager,
        rate_limiter,
        get_current_user,
        get_current_active_user,
        get_current_admin_user
    )
    print("✅ Módulos de segurança carregados")
    
    # Importar serviços
    from backend.services.daily_credits_service import DailyCreditsService
    print("✅ Módulo de créditos diários carregado")
    
    # Importar observability (opcional)
    try:
        from backend.observability.sentinel import (
            alert_system_startup,
            alert_system_error,
            alert_new_user,
            alert_payment_approved,
            alert_daily_credits_distributed
        )
        print("✅ Módulo de observability (Discord) carregado")
        DISCORD_ENABLED = bool(settings.DISCORD_WEBHOOK)
    except ImportError as e:
        print(f"⚠️  Módulo observability não encontrado: {e}")
        DISCORD_ENABLED = False
        
        # Funções dummy
        def alert_system_startup(**kwargs): pass
        def alert_system_error(**kwargs): pass
        def alert_new_user(**kwargs): pass
        def alert_payment_approved(**kwargs): pass
        def alert_daily_credits_distributed(**kwargs): pass
    
    AUTH_ENABLED = True
    
except Exception as e:
    print(f"❌ Erro CRÍTICO carregando módulos de segurança: {e}")
    print("🚨 Sistema não pode iniciar sem segurança!")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ==============================================
# REGISTRO DE ROTAS DA API COM PREFIXO
# ==============================================
print("\n📦 Registrando rotas da API...")

try:
    # Importar rotas
    from backend.api import auth_routes
    from backend.api import routes
    from backend.api import payment_routes
    
    # Incluir rotas com prefixo /api
    app.include_router(auth_routes.router, prefix="/api/auth", tags=["authentication"])
    print("✅ Rotas de autenticação: /api/auth/*")
    
    app.include_router(routes.router, prefix="/api", tags=["api"])
    print("✅ Rotas da API: /api/*")
    
    app.include_router(payment_routes.router, prefix="/api", tags=["payments"])
    print("✅ Rotas de pagamento: /api/payments/*")
    
    print("✅ Sistema de rotas configurado")
    
except Exception as e:
    print(f"❌ Erro carregando rotas: {e}")

# ==============================================
# MIDDLEWARE PARA LOG DE REQUESTS
# ==============================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    
    # Log apenas de rotas não-estáticas
    if not request.url.path.startswith('/static'):
        print(f"🌐 [{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Log de respostas com erro
    if response.status_code >= 400 and not request.url.path.startswith('/static'):
        process_time = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   ⚠️  Status: {response.status_code} | Tempo: {process_time:.2f}ms")
        
        # Alertar erros no Discord
        if response.status_code >= 500 and DISCORD_ENABLED:
            alert_system_error(
                error=Exception(f"HTTP {response.status_code}"),
                endpoint=request.url.path,
                user="sistema"
            )
    
    return response

# ==============================================
# ROTAS DA API
# ==============================================

@app.get("/api/user/credits", tags=["user"])
async def get_user_credits(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna os créditos do usuário atual"""
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
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/health", tags=["system"])
async def health_check():
    """Verifica saúde do sistema"""
    db_status = "connected" if db_path.exists() else "disconnected"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "security": {
            "enabled": True,
            "argon2": True,
            "jwt": True,
            "captcha": settings.CAPTCHA_TYPE,
            "rate_limiting": True
        },
        "database": db_status,
        "payments": {
            "enabled": bool(settings.MP_ACCESS_TOKEN)
        },
        "credits_system": {
            "enabled": True,
            "credits_per_day": 1
        },
        "discord": {
            "enabled": DISCORD_ENABLED
        },
        "frontend": {
            "available": frontend_available
        }
    }

@app.get("/api/security/info", tags=["security"])
async def security_info():
    """Retorna informações sobre as camadas de segurança"""
    return {
        "security_layers": {
            "password_hashing": {
                "algorithm": "Argon2"
            },
            "jwt": {
                "algorithm": settings.ALGORITHM,
                "access_token_expire": f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes"
            },
            "captcha": {
                "type": settings.CAPTCHA_TYPE,
                "enabled": bool(settings.CAPTCHA_SITE_KEY)
            }
        },
        "status": "active"
    }

# ==============================================
# ROTAS ADMIN (protegidas)
# ==============================================

@app.get("/api/admin/check-credits", tags=["admin"])
async def check_all_users_credits(
    current_user = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """ADMIN: Verifica créditos de todos os usuários"""
    try:
        from backend.models import User
        
        service = DailyCreditsService()
        users = db.query(User).filter(User.is_active == True).all()
        
        results = []
        for user in users:
            status = service.get_user_credit_status(db, user.id)
            results.append({
                "user_id": user.id,
                "email": user.email,
                "credits": status["current_credits"],
                "streak": status["streak_days"]
            })
        
        return {
            "success": True,
            "total_users": len(results),
            "users": results[:50]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==============================================
# EVENTO DE INICIALIZAÇÃO
# ==============================================
@app.on_event("startup")
async def startup_event():
    """Inicializa o sistema"""
    
    if DISCORD_ENABLED:
        try:
            alert_system_startup()
            print("✅ Alerta de startup enviado para o Discord")
        except Exception as e:
            print(f"⚠️  Erro ao enviar alerta: {e}")
    
    print(f"""
    🎉 {settings.APP_NAME} v2.0 INICIADO!
    
    📍 Diretório: {PROJECT_ROOT}
    🌐 Frontend: {'✅ Disponível' if frontend_available else '❌ Não disponível'}
    
    🔐 SEGURANÇA: Argon2 + JWT + CAPTCHA + Rate Limiting
    💰 PAGAMENTOS: {'✅ Configurado' if settings.MP_ACCESS_TOKEN else '❌ Não configurado'}
    💎 CRÉDITOS: 1 crédito por dia via upload
    💬 DISCORD: {'✅ Ativos' if DISCORD_ENABLED else '❌ Desativados'}
    
    🔗 URLs:
       {'🌐 Login: http://localhost:' + str(settings.PORT) + '/login' if login_available else ''}
       {'📊 Dashboard: http://localhost:' + str(settings.PORT) + '/dashboard' if dashboard_available else ''}
       📚 API Docs: http://localhost:{settings.PORT}/api/docs
       💎 Créditos API: http://localhost:{settings.PORT}/api/user/credits
       
    📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
    """)

# ==============================================
# MANIPULADOR DE ERROS
# ==============================================
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    """Manipula erros 404"""
    if request.url.path.startswith('/api/'):
        return JSONResponse(
            status_code=404,
            content={
                "error": "Endpoint não encontrado",
                "path": request.url.path,
                "suggestions": [
                    "/api/docs",
                    "/api/health",
                    "/api/auth/login",
                    "/api/user/credits"
                ]
            }
        )
    
    # Se for página não encontrada, redirecionar para login
    if login_available and not request.url.path.startswith('/static'):
        return RedirectResponse(url="/login")
    
    return JSONResponse(status_code=404, content={"error": "Página não encontrada"})

@app.exception_handler(500)
async def server_error_exception_handler(request: Request, exc):
    """Manipula erros 500"""
    print(f"❌ Erro 500 em {request.url.path}: {exc}")
    import traceback
    traceback.print_exc()
    
    if DISCORD_ENABLED:
        try:
            alert_system_error(error=exc, endpoint=request.url.path, user="sistema")
        except:
            pass
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Erro interno do servidor",
            "timestamp": datetime.now().isoformat()
        }
    )

# ==============================================
# MAIN EXECUTION
# ==============================================
if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"📍 Trabalhando de: {PROJECT_ROOT}")
    print("🛑 Pressione CTRL+C para parar\n")
    
    print("🔒 MODO SEGURO: Todas as camadas de segurança ativas")
    print("📁 ARQUIVOS ESTÁTICOS: /static/*")
    print("🌐 ROTAS HTML: /, /login, /dashboard, /planos, /checkout")
    print("🔌 API ROTAS: /api/*\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )