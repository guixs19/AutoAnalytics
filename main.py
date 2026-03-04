# main.py (na raiz)
import sys
import os
from pathlib import Path
from datetime import datetime
import secrets
import string

print("=" * 60)
print("🚀 AUTOANALYTICS v2.0 - SERVIDOR COMPLETO COM JWT E PAGAMENTOS")
print("=" * 60)

# Configurar paths
PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

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
    CAPTCHA_SITE_KEY = os.getenv("CAPTCHA_SITE_KEY", "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI")  # Chave de teste
    CAPTCHA_SECRET_KEY = os.getenv("CAPTCHA_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe")  # Chave de teste
    
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
    planos_path = FRONTEND_DIR / "planos.html"  # NOVO
    checkout_path = FRONTEND_DIR / "checkout.html"  # NOVO
    
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
# CONFIGURAÇÃO DO FRONTEND
# ==============================================
if frontend_available:
    print("\n🌐 CONFIGURANDO FRONTEND...")
    
    # Servir arquivos estáticos
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    print("✅ Static files montados em /static")
    
    # Servir CSS e JS
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    print("✅ CSS e JS montados")
    
    # Login como página inicial
    if login_available:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def serve_login():
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        print("✅ Login configurado como página inicial")
    
    # Dashboard protegido
    @app.get("/dashboard", include_in_schema=False)
    async def serve_dashboard(request: Request):
        """Serve o dashboard (protegido por autenticação)"""
        # Verificar token via cookie ou header
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return RedirectResponse(url="/")
        
        if dashboard_available:
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        else:
            raise HTTPException(status_code=404, detail="Dashboard não encontrado")
    
    # NOVO: Página de planos
    @app.get("/planos.html", include_in_schema=False)
    async def serve_planos(request: Request):
        """Serve a página de planos"""
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return RedirectResponse(url="/")
        
        planos_path = FRONTEND_DIR / "planos.html"
        if planos_path.exists():
            return FileResponse(planos_path)
        else:
            raise HTTPException(status_code=404, detail="Página de planos não encontrada")
    
    # NOVO: Página de checkout
    @app.get("/checkout.html", include_in_schema=False)
    async def serve_checkout(request: Request):
        """Serve a página de checkout"""
        token = request.cookies.get("access_token") or \
                request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return RedirectResponse(url="/")
        
        checkout_path = FRONTEND_DIR / "checkout.html"
        if checkout_path.exists():
            return FileResponse(checkout_path)
        else:
            raise HTTPException(status_code=404, detail="Página de checkout não encontrada")
    
    # Rotas para arquivos específicos
    @app.get("/{filename:path}", include_in_schema=False)
    async def serve_frontend_files(filename: str):
        """Serve arquivos específicos do frontend"""
        file_path = FRONTEND_DIR / filename
        
        # Proteger acesso a arquivos sensíveis
        if ".." in filename or filename.startswith("/"):
            raise HTTPException(status_code=403, detail="Acesso negado")
        
        # Verificar se é um arquivo permitido
        if file_path.exists() and file_path.is_file():
            allowed_extensions = ['.html', '.css', '.js', '.png', '.jpg', 
                                 '.jpeg', '.gif', '.ico', '.svg', '.json']
            
            if file_path.suffix.lower() in allowed_extensions:
                return FileResponse(file_path)
        
        # Se não encontrado, redirecionar para login
        if login_available:
            return RedirectResponse(url="/")
        else:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    print("✅ Frontend configurado com rotas específicas")

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
                "payments_plans": "/api/payments/plans"
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
    # 🔥 CORREÇÃO: Importar settings do backend.config primeiro
    from backend.config import settings as backend_settings
    
    # Atualizar settings do backend com nossas configurações
    for key, value in settings.__dict__.items():
        if not key.startswith('_'):
            setattr(backend_settings, key, value)
    
    print("✅ Configurações sincronizadas")
    
    # Verificar/criar banco de dados
    from backend.database import engine, Base, create_tables
    
    # Criar tabelas
    create_tables()
    print("✅ Tabelas criadas/verificadas")
    
    # 🔥 CORREÇÃO: Importar TUDO do módulo security central
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
    
    # 🔥 CORREÇÃO: Importar rotas
    from backend.api import auth_routes
    from backend.api import routes
    from backend.api import payment_routes  # NOVO: Importar rotas de pagamento
    
    # Incluir rotas
    app.include_router(auth_routes.router, prefix="/api/auth", tags=["authentication"])
    print("✅ Rotas de autenticação carregadas")
    
    app.include_router(routes.router, prefix="/api", tags=["api"])
    print("✅ Rotas da API carregadas")
    
    app.include_router(payment_routes.router, prefix="/api", tags=["payments"])  # NOVO
    print("✅ Rotas de pagamento carregadas")
    
    AUTH_ENABLED = True
    
except Exception as e:
    print(f"❌ Erro CRÍTICO carregando módulos de segurança: {e}")
    print("🚨 Sistema não pode iniciar sem segurança!")
    print("💡 Verifique se o arquivo backend/security.py existe e está correto")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ==============================================
# MIDDLEWARE PARA LOG DE REQUESTS
# ==============================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    
    # Log de requests (ignorar estáticos)
    if not request.url.path.startswith('/static') and not request.url.path.startswith('/css') and not request.url.path.startswith('/js'):
        print(f"🌐 [{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Log de respostas com erro
    if response.status_code >= 400 and not request.url.path.startswith('/static'):
        process_time = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   ⚠️  Status: {response.status_code} | Tempo: {process_time:.2f}ms")
    
    return response

# ==============================================
# ROTAS GLOBAIS DA API
# ==============================================
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
            "enabled": bool(settings.MP_ACCESS_TOKEN),
            "mercadopago": bool(settings.MP_ACCESS_TOKEN)
        },
        "frontend": {
            "available": frontend_available,
            "login": login_available,
            "dashboard": dashboard_available
        }
    }

@app.get("/api/security/info", tags=["security"])
async def security_info():
    """Retorna informações sobre as camadas de segurança (sem dados sensíveis)"""
    return {
        "security_layers": {
            "password_hashing": {
                "algorithm": "Argon2",
                "time_cost": settings.ARGON2_TIME_COST,
                "memory_cost": f"{settings.ARGON2_MEMORY_COST / 1024:.0f} KB"
            },
            "jwt": {
                "algorithm": settings.ALGORITHM,
                "access_token_expire": f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes",
                "refresh_token_expire": f"{settings.REFRESH_TOKEN_EXPIRE_DAYS} days"
            },
            "captcha": {
                "type": settings.CAPTCHA_TYPE,
                "enabled": bool(settings.CAPTCHA_SITE_KEY)
            },
            "rate_limiting": {
                "login_attempts": "5 per 15 minutes",
                "register_attempts": "3 per hour",
                "redis_available": bool(settings.REDIS_HOST)
            },
            "headers": list(settings.SECURITY_HEADERS.keys())
        },
        "payments": {
            "enabled": bool(settings.MP_ACCESS_TOKEN)
        },
        "status": "active"
    }

# ==============================================
# ROTA PROTEGIDA DE TESTE
# ==============================================
@app.get("/api/protected-test", tags=["test"])
async def protected_test_endpoint(
    current_user = Depends(get_current_user)
):
    """Rota protegida por autenticação"""
    return {
        "message": "Acesso autorizado",
        "user": current_user.email,
        "role": current_user.role,
        "credits": current_user.credits,
        "timestamp": datetime.now().isoformat()
    }

# ==============================================
# DEBUG ROUTES
# ==============================================
@app.get("/api/debug/routes", include_in_schema=False)
async def debug_routes():
    """Lista todas as rotas disponíveis"""
    routes_list = []
    for route in app.routes:
        methods = route.methods if hasattr(route, 'methods') else []
        routes_list.append({
            "path": route.path,
            "methods": list(methods) if methods else [],
            "name": route.name if hasattr(route, 'name') else ""
        })
    
    return {
        "total_routes": len(routes_list),
        "routes": routes_list[:30]
    }

# ==============================================
# EVENTO DE INICIALIZAÇÃO
# ==============================================
@app.on_event("startup")
async def startup_event():
    print(f"""
    🎉 {settings.APP_NAME} v2.0 INICIADO!
    
    📍 Diretório: {PROJECT_ROOT}
    🔧 Backend: {settings.BASE_DIR}
    🌐 Frontend: {'✅ Disponível' if frontend_available else '❌ Não disponível'}
    
    🔐 SEGURANÇA:
       ✅ Argon2 (hash de senha)
       ✅ JWT (tokens de acesso)
       ✅ CAPTCHA ({settings.CAPTCHA_TYPE})
       ✅ Rate Limiting
    
    💰 PAGAMENTOS:
       {'✅ Mercado Pago configurado' if settings.MP_ACCESS_TOKEN else '❌ Mercado Pago não configurado'}
       {'✅ PIX disponível' if settings.MP_ACCESS_TOKEN else '❌ PIX indisponível'}
    
    🗄️  Banco de dados: {db_path.name}
    
    🔗 URLs:
       {'🌐 Login: http://localhost:' + str(settings.PORT) if login_available else ''}
       {'📊 Dashboard: http://localhost:' + str(settings.PORT) + '/dashboard' if dashboard_available else ''}
       {'💰 Planos: http://localhost:' + str(settings.PORT) + '/planos.html' if frontend_available else ''}
       📚 API Docs: http://localhost:{settings.PORT}/api/docs
       🩺 Health: http://localhost:{settings.PORT}/api/health
       🔐 Security Info: http://localhost:{settings.PORT}/api/security/info
    
    🔐 ENDPOINTS DE AUTENTICAÇÃO:
       👤 Login: POST http://localhost:{settings.PORT}/api/auth/login
       📝 Registro: POST http://localhost:{settings.PORT}/api/auth/register
       🔄 Refresh: POST http://localhost:{settings.PORT}/api/auth/refresh
       🚪 Logout: POST http://localhost:{settings.PORT}/api/auth/logout
    
    💰 ENDPOINTS DE PAGAMENTO:
       📋 Planos: GET http://localhost:{settings.PORT}/api/payments/plans
       💳 Saldo: GET http://localhost:{settings.PORT}/api/payments/balance
       📱 Criar PIX: POST http://localhost:{settings.PORT}/api/payments/create-pix
       🔗 Criar Checkout: POST http://localhost:{settings.PORT}/api/payments/create-checkout
       🔔 Webhook: POST http://localhost:{settings.PORT}/api/payments/webhook
       📜 Histórico: GET http://localhost:{settings.PORT}/api/payments/history
       
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
                    "/api/payments/plans"
                ]
            }
        )
    
    if login_available:
        return RedirectResponse(url="/")
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "Página não encontrada"}
        )

@app.exception_handler(500)
async def server_error_exception_handler(request: Request, exc):
    """Manipula erros 500"""
    print(f"❌ Erro 500 em {request.url.path}: {exc}")
    import traceback
    traceback.print_exc()
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
    if settings.MP_ACCESS_TOKEN:
        print("💰 MODO PAGAMENTO: Mercado Pago configurado")
    else:
        print("⚠️  MODO PAGAMENTO: Mercado Pago NÃO configurado (adicione MP_ACCESS_TOKEN no .env)")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )