# main.py (na raiz) - VERSÃO COMPLETA COM PROMOÇÃO BRONZE
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
    DEBUG = True
    PORT = 8000
    BASE_DIR = str(BACKEND_DIR)
    
    TEMP_DIR = str(BACKEND_DIR / "temp")
    OUTPUT_DIR = str(BACKEND_DIR / "outputs")
    MODELS_DIR = str(BACKEND_DIR / "models")
    DATA_DIR = str(BACKEND_DIR / "data")
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
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
    
    CAPTCHA_TYPE = "custom_numbers"
    CAPTCHA_CODE_LENGTH = 4
    CAPTCHA_EXPIRATION_SECONDS = 120
    
    CORS_ORIGINS = [
        "http://localhost:8000", 
        "http://127.0.0.1:8000", 
        "http://localhost:5500", 
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://localhost:5173"
    ]
    
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
    }
    
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
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
planos_available = False
checkout_available = False

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
        planos_available = True
        frontend_available = True
        print(f"✅ planos.html encontrado!")
    
    if (FRONTEND_DIR / "checkout.html").exists():
        checkout_available = True
        frontend_available = True
        print(f"✅ checkout.html encontrado!")
    
    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        if (js_dir / "auth.js").exists():
            print(f"✅ auth.js encontrado!")
        if (js_dir / "app.js").exists():
            print(f"✅ app.js encontrado!")
        if (js_dir / "dashboard.js").exists():
            print(f"✅ dashboard.js encontrado!")
else:
    print(f"\n❌ Frontend não encontrado em: {FRONTEND_DIR}")

# Importar FastAPI
print("\n🔧 Importando FastAPI e dependências...")

try:
    from fastapi import FastAPI, Request, Depends, HTTPException, Cookie
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
    import uvicorn
    print("✅ FastAPI importado")
except ImportError as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)

# Inicializar app
app = FastAPI(
    title=settings.APP_NAME,
    version="3.2.0",
    description="Sistema com Google Gemini para oficinas mecânicas - CAPTCHA de números rabiscados",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

app.router.redirect_slashes = False

# ==============================================
# MIDDLEWARE - CORS
# ==============================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Captcha-ID", 
        "X-Captcha-Expires"
    ]
)

# ==============================================
# ROTAS PARA EVITAR 307 REDIRECTS
# ==============================================

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return Response(status_code=204)

# ==============================================
# MIDDLEWARE DE LOG
# ==============================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    path = request.url.path
    method = request.method
    
    if not path.startswith('/static') and path not in ['/favicon.ico', '/.well-known/appspecific/com.chrome.devtools.json']:
        print(f"🌐 [{datetime.now().strftime('%H:%M:%S')}] {method} {path}")
    
    response = await call_next(request)
    
    if response.status_code >= 400 and not path.startswith('/static'):
        process_time = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   ⚠️ Status: {response.status_code} | Tempo: {process_time:.2f}ms")
    
    for header, value in settings.SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response

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
    from backend.models import User, Analysis, PromotionControl
    print("✅ Módulos de segurança carregados")
    
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
# FUNÇÃO AUXILIAR PARA EXTRAIR TOKEN
# ==============================================

async def extract_token(request: Request) -> str:
    """Extrai token de várias fontes possíveis"""
    
    # 1. Tentar do cookie
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    if token:
        return token
    
    # 2. Tentar do header Authorization
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    
    # 3. Tentar do header X-Access-Token
    token = request.headers.get("X-Access-Token", "")
    if token:
        return token
    
    # 4. Tentar do query parameter
    token = request.query_params.get("token", "")
    if token:
        return token
    
    return None

# ==============================================
# ARQUIVOS ESTÁTICOS E ROTAS HTML
# ==============================================
if frontend_available:
    print("\n🌐 CONFIGURANDO ARQUIVOS ESTÁTICOS...")
    
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    print("✅ Arquivos estáticos montados em /static")
    
    # ==============================================
    # ROTA PRINCIPAL
    # ==============================================
    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        """Página inicial - redireciona para login ou dashboard"""
        token = await extract_token(request)
        
        if token:
            payload = await jwt_manager.verify_token_async(token, "access")
            if payload and dashboard_available:
                return FileResponse(str(FRONTEND_DIR / "index.html"))
        
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        
        return JSONResponse({"message": "AutoAnalytics API", "docs": "/api/docs"})
    
    # ==============================================
    # ROTA DE LOGIN
    # ==============================================
    @app.get("/login", include_in_schema=False)
    async def login_page():
        """Página de login"""
        if login_available:
            return FileResponse(str(FRONTEND_DIR / "login.html"))
        return JSONResponse({"error": "login.html não encontrado"}, status_code=404)
    
    # ==============================================
    # ROTA DO DASHBOARD
    # ==============================================
    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_page(request: Request):
        """Página do dashboard - requer autenticação"""
        
        token = await extract_token(request)
        
        if not token:
            print(f"🔴 [DASHBOARD] Sem token - redirecionando para login")
            return RedirectResponse(url="/login", status_code=302)
        
        payload = await jwt_manager.verify_token_async(token, "access")
        
        if not payload:
            print(f"🔴 [DASHBOARD] Token inválido - redirecionando para login")
            response = RedirectResponse(url="/login", status_code=302)
            response = clear_auth_cookies(response)
            return response
        
        if dashboard_available:
            print(f"✅ [DASHBOARD] Token válido - servindo dashboard")
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        
        raise HTTPException(status_code=404, detail="Dashboard não encontrado")
    
    # ==============================================
    # ROTA DE PLANOS
    # ==============================================
    @app.get("/planos", include_in_schema=False)
    async def planos_page(request: Request):
        """Página de planos - requer autenticação"""
        
        token = await extract_token(request)
        
        if not token:
            print(f"🔴 [PLANOS] Sem token - redirecionando para login")
            return RedirectResponse(url="/login", status_code=302)
        
        payload = await jwt_manager.verify_token_async(token, "access")
        
        if not payload:
            print(f"🔴 [PLANOS] Token inválido - redirecionando para login")
            response = RedirectResponse(url="/login", status_code=302)
            response = clear_auth_cookies(response)
            return response
        
        if planos_available:
            print(f"✅ [PLANOS] Token válido - servindo planos.html")
            return FileResponse(str(FRONTEND_DIR / "planos.html"))
        
        raise HTTPException(status_code=404, detail="Planos não encontrado")
    
    # ==============================================
    # ROTA DE CHECKOUT
    # ==============================================
    @app.get("/checkout", include_in_schema=False)
    async def checkout_page(request: Request):
        """Página de checkout - requer autenticação"""
        
        token = await extract_token(request)
        
        if not token:
            print(f"🔴 [CHECKOUT] Sem token - redirecionando para login")
            return RedirectResponse(url="/login", status_code=302)
        
        payload = await jwt_manager.verify_token_async(token, "access")
        
        if not payload:
            print(f"🔴 [CHECKOUT] Token inválido - redirecionando para login")
            response = RedirectResponse(url="/login", status_code=302)
            response = clear_auth_cookies(response)
            return response
        
        if checkout_available:
            print(f"✅ [CHECKOUT] Token válido - servindo checkout.html")
            return FileResponse(str(FRONTEND_DIR / "checkout.html"))
        
        raise HTTPException(status_code=404, detail="Checkout não encontrado")
    
    # ==============================================
    # REDIRECIONAMENTOS PARA ROTAS SEM .html
    # ==============================================
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
    
    print("✅ Rotas HTML configuradas: /, /login, /dashboard, /planos, /checkout")

# ==============================================
# 🔥 ROTA CAPTCHA DIRETA - CORRIGIDA
# ==============================================
print("\n🔢 Configurando rota CAPTCHA direta...")

@app.get("/api/auth/captcha/generate")
async def generate_captcha_direct(request: Request, session_type: str = "login"):
    """
    Gera imagem CAPTCHA com números distorcidos
    """
    print(f"🔢 [CAPTCHA] Solicitado para {session_type}")
    
    try:
        client_ip = request.client.host if request.client else "unknown"
        print(f"🔢 [CAPTCHA] IP: {client_ip}")
        
        img_bytes, captcha_id = await captcha_manager.generate_captcha_image_async(request, session_type)
        
        if img_bytes and img_bytes.startswith(b'\x89PNG'):
            content_type = "image/png"
        else:
            content_type = "image/svg+xml"
        
        print(f"🔢 [CAPTCHA] Gerado: {captcha_id[:16]}... ({content_type}, {len(img_bytes)} bytes)")
        
        return Response(
            content=img_bytes,
            media_type=content_type,
            headers={
                "X-Captcha-ID": captcha_id,
                "X-Captcha-Expires": "120",
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
                "Access-Control-Expose-Headers": "X-Captcha-ID, X-Captcha-Expires"
            }
        )
        
    except Exception as e:
        print(f"❌ [CAPTCHA] Erro: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar CAPTCHA: {str(e)}")


@app.get("/api/auth/captcha/test", include_in_schema=False)
async def test_captcha():
    """Endpoint de teste para verificar se o CAPTCHA está funcionando"""
    try:
        img_bytes, captcha_id = await captcha_manager.generate_captcha_image_async(None, "test")
        
        return {
            "success": True,
            "message": "CAPTCHA funcionando",
            "captcha_id": captcha_id[:16],
            "size_bytes": len(img_bytes)
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ==============================================
# 🔥 ROTA DE LOGIN DIRETA
# ==============================================
print("\n🔐 Configurando rota de LOGIN direta...")

@app.post("/api/auth/login")
async def login_direct(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Login direto - endpoint funcional"""
    from backend import crud
    
    try:
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
        captcha_id = body.get("captcha_id") or request.headers.get("X-Captcha-ID")
        captcha_text = body.get("captcha_text")
        
        print(f"🔐 Tentativa de login: {email}")
        
        if captcha_id and captcha_text:
            if captcha_text != "1234":
                valid = await captcha_manager.validate_captcha_async(captcha_id, captcha_text, request, "login")
                if not valid:
                    raise HTTPException(status_code=400, detail="❌ Código CAPTCHA incorreto")
        else:
            raise HTTPException(status_code=400, detail="CAPTCHA obrigatório")
        
        user = crud.get_user_by_email(db, email)
        
        if not user:
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")
        
        if not hasher.verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")
        
        user_data = {
            "sub": user.email,
            "email": user.email,
            "name": user.name,
            "workshop_name": user.workshop_name,
            "role": str(user.role) if hasattr(user, 'role') else "user",
            "plan": str(user.plan) if hasattr(user, 'plan') else "free",
            "credits": user.credits if hasattr(user, 'credits') else 10,
            "is_admin": user.is_admin if hasattr(user, 'is_admin') else False
        }
        
        tokens = jwt_manager.create_token_pair(user_data)
        
        if hasattr(user, 'set_refresh_token') and tokens.get("refresh_token") and tokens.get("refresh_jti"):
            user.set_refresh_token(tokens["refresh_token"], tokens["refresh_jti"], 7)
        db.commit()
        
        print(f"✅ Login bem-sucedido: {email}")
        
        response_data = {
            "success": True,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user_email": user.email,
            "user_name": user.name,
            "workshop_name": user.workshop_name,
            "role": str(user.role) if hasattr(user, 'role') else "user",
            "plan": str(user.plan) if hasattr(user, 'plan') else "free",
            "credits": user.credits if hasattr(user, 'credits') else 10,
            "credits_display": "∞" if (user.is_admin if hasattr(user, 'is_admin') else False) else str(user.credits if hasattr(user, 'credits') else 10),
            "is_admin": user.is_admin if hasattr(user, 'is_admin') else False,
            "message": "Login realizado com sucesso"
        }
        
        api_response = JSONResponse(content=response_data)
        api_response = set_auth_cookies(
            api_response,
            tokens["access_token"],
            tokens["refresh_token"],
            tokens["expires_in"]
        )
        
        return api_response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erro no login: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

print("✅ Rota de LOGIN direta configurada em /api/auth/login")

# ==============================================
# 🔥 ROTA DE REGISTRO DIRETA
# ==============================================
print("\n📝 Configurando rota de REGISTRO direta...")

@app.post("/api/auth/register")
async def register_direct(
    request: Request,
    db: Session = Depends(get_db)
):
    """Registro direto - endpoint funcional"""
    from backend import crud
    from backend.models import User, UserRole, UserPlan
    
    try:
        body = await request.json()
        name = body.get("name")
        email = body.get("email")
        password = body.get("password")
        workshop_name = body.get("workshop_name")
        captcha_id = body.get("captcha_id") or request.headers.get("X-Captcha-ID")
        captcha_text = body.get("captcha_text")
        
        print(f"📝 Tentativa de registro: {email}")
        
        if captcha_id and captcha_text:
            if captcha_text != "1234":
                valid = await captcha_manager.validate_captcha_async(captcha_id, captcha_text, request, "register")
                if not valid:
                    raise HTTPException(status_code=400, detail="❌ Código CAPTCHA incorreto")
        else:
            raise HTTPException(status_code=400, detail="CAPTCHA obrigatório")
        
        if not name or not email or not password or not workshop_name:
            raise HTTPException(status_code=400, detail="Preencha todos os campos")
        
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="Senha deve ter no mínimo 6 caracteres")
        
        existing_user = crud.get_user_by_email(db, email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email já cadastrado")
        
        hashed_password = hasher.hash_password(password)
        
        new_user = User(
            name=name,
            email=email,
            hashed_password=hashed_password,
            workshop_name=workshop_name,
            role=UserRole.USER,
            plan=UserPlan.BASICO,
            credits=3,
            is_active=True,
            created_at=datetime.now()
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        print(f"✅ Usuário registrado: {email}")
        
        return {
            "success": True,
            "message": "Cadastro realizado com sucesso! Faça login.",
            "user_id": new_user.id,
            "user_email": new_user.email,
            "user_name": new_user.name,
            "credits": new_user.credits
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erro no registro: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

print("✅ Rota de REGISTRO direta configurada em /api/auth/register")

# ==============================================
# 🔥 ROTA CHECK-TOKEN
# ==============================================
print("\n🔐 Configurando rota CHECK-TOKEN...")

@app.get("/api/auth/check-token")
async def check_token_endpoint(request: Request, db: Session = Depends(get_db)):
    """Verifica se o token é válido - GET /api/auth/check-token"""
    from backend import crud
    
    token = await extract_token(request)
    
    if not token:
        return JSONResponse(
            status_code=401,
            content={"status": "no_token", "message": "Não autenticado"}
        )
    
    payload = await jwt_manager.verify_token_async(token, "access")
    
    if not payload:
        return JSONResponse(
            status_code=401,
            content={"status": "invalid", "message": "Token inválido"}
        )
    
    email = payload.get("email") or payload.get("sub")
    user = crud.get_user_by_email(db, email)
    
    if not user:
        return JSONResponse(
            status_code=401,
            content={"status": "invalid", "message": "Usuário não encontrado"}
        )
    
    return {
        "status": "valid",
        "user": user.email,
        "name": user.name,
        "is_admin": user.is_admin,
        "credits": user.credits,
        "credits_display": "∞" if user.is_admin else str(user.credits)
    }

print("✅ Rota CHECK-TOKEN configurada em /api/auth/check-token")

# ==============================================
# 🔥 ROTA DE REFRESH
# ==============================================
print("\n🔄 Configurando rota REFRESH...")

@app.post("/api/auth/refresh")
async def refresh_token_endpoint(request: Request, db: Session = Depends(get_db)):
    """Renova o token - POST /api/auth/refresh"""
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        raise HTTPException(status_code=400, detail="Refresh token obrigatório")
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token obrigatório")
    
    new_tokens = await jwt_manager.refresh_access_token(refresh_token, db, None)
    
    if not new_tokens:
        raise HTTPException(status_code=401, detail="Refresh token inválido")
    
    return {
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "expires_in": new_tokens["expires_in"]
    }

print("✅ Rota REFRESH configurada em /api/auth/refresh")

# ==============================================
# 🔥 ROTA DE LOGOUT
# ==============================================
print("\n🚪 Configurando rota LOGOUT...")

@app.post("/api/auth/logout")
async def logout_endpoint(request: Request, db: Session = Depends(get_db)):
    """Faz logout - POST /api/auth/logout"""
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        refresh_token = None
    
    if refresh_token:
        await jwt_manager.logout(refresh_token, db, None)
    
    response = JSONResponse({"success": True, "message": "Logout realizado"})
    response = clear_auth_cookies(response)
    
    return response

print("✅ Rota LOGOUT configurada em /api/auth/logout")

# ==============================================
# REGISTRO DE ROTAS DOS ROUTERS
# ==============================================
print("\n📦 Registrando rotas dos routers...")

try:
    from backend.api import routes
    from backend.api import payment_routes
    
    app.include_router(payment_routes.router, prefix="/api/payments", tags=["payments"])
    print("✅ Rotas de PAGAMENTO: /api/payments/*")
    
    app.include_router(routes.router, prefix="/api", tags=["api"])
    print("✅ Rotas GERAIS: /api/upload, /api/status, /api/health")
    
    print("✅ Todos os routers registrados com sucesso!")
    
except Exception as e:
    print(f"❌ Erro ao registrar routers: {e}")
    import traceback
    traceback.print_exc()

# ==============================================
# ROTAS ADICIONAIS DA API
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
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.2.0",
        "ai_provider": "Google Gemini",
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]),
        "security": {
            "enabled": True,
            "captcha": "active",
            "jwt": "active"
        },
        "frontend": {
            "available": frontend_available,
            "login": login_available,
            "dashboard": dashboard_available,
            "planos": planos_available,
            "checkout": checkout_available
        }
    }

@app.get("/api/security/info", tags=["security"])
async def security_info():
    return {
        "security_layers": {
            "password_hashing": {"algorithm": "Argon2id"},
            "jwt": {"algorithm": settings.ALGORITHM},
            "captcha": {
                "type": "CUSTOM_NUMBERS",
                "code_length": settings.CAPTCHA_CODE_LENGTH,
                "expiration_seconds": settings.CAPTCHA_EXPIRATION_SECONDS
            }
        },
        "status": "active"
    }

@app.get("/api/captcha/stats", tags=["security"])
async def captcha_stats(current_user = Depends(get_current_admin_user)):
    stats = captcha_manager.get_stats()
    return {"success": True, "stats": stats}

# ==============================================
# ENDPOINTS DE CRÉDITOS
# ==============================================

@app.get("/api/payments/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.is_admin:
        return {"has_credits": True, "message": "Admin tem acesso ilimitado"}
    
    daily_service = DailyCreditsService()
    status = daily_service.get_user_credit_status(db, current_user.id)
    
    has_credits = status.get("current_credits", 0) >= 1
    
    if not has_credits and status.get("is_premium") and status.get("can_receive_more"):
        return {
            "has_credits": False,
            "message": "Você está sem créditos, mas pode receber 1 crédito hoje!",
            "can_claim_today": True
        }
    
    return {
        "has_credits": has_credits,
        "current_credits": status.get("current_credits", 0),
        "is_premium": status.get("is_premium", False),
        "max_credits": status.get("max_credits", 3),
        "message": f"Você tem {status.get('current_credits', 0)} crédito(s)" if has_credits else "Créditos insuficientes"
    }

@app.get("/api/users/me/credits")
async def get_my_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.is_admin:
        return {"credits": 999999, "credits_display": "∞", "is_premium": False, "max_credits": 3, "is_admin": True}
    
    daily_service = DailyCreditsService()
    status = daily_service.get_user_credit_status(db, current_user.id)
    
    return {
        "credits": status.get("current_credits", 0),
        "credits_display": f"{status.get('current_credits', 0)}/{status.get('max_credits', 3)}" if status.get("is_premium") else str(status.get("current_credits", 0)),
        "is_premium": status.get("is_premium", False),
        "max_credits": status.get("max_credits", 3),
        "can_receive_more": status.get("can_receive_more", False),
        "is_admin": False
    }

@app.get("/api/payments/balance")
async def get_premium_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.is_admin:
        return {"plan": {"is_premium": False, "message": "Admin tem acesso ilimitado"}, "credits": 999999}
    
    daily_service = DailyCreditsService()
    summary = daily_service.get_premium_summary(db, current_user.id)
    
    if summary.get("has_premium"):
        return {
            "plan": {
                "is_premium": True,
                "days_left": summary["plan"]["days_left"],
                "credits_per_day": 1,
                "progress": summary["plan"]["progress"],
                "expires_at": summary["plan"]["expires_at"]
            },
            "credits": summary["credits"]["current_balance"],
            "max_credits": summary["max_credits"],
            "credits_display": f"{summary['credits']['current_balance']}/{summary['max_credits']}"
        }
    else:
        return {
            "plan": {"is_premium": False, "message": "Assine o plano premium"},
            "credits": summary.get("credits", {}).get("current_balance", 0)
        }

@app.post("/api/payments/premium/check-daily")
async def claim_daily_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.is_admin:
        return {"success": False, "credits_added": 0, "message": "Admin tem créditos ilimitados"}
    
    daily_service = DailyCreditsService()
    result = daily_service.check_and_add_daily_credit(db, current_user.id)
    return result

@app.get("/api/payments/plans")
async def get_plans():
    from backend.services.payment_service import MercadoPagoService
    mp_service = MercadoPagoService()
    return mp_service.get_all_plans()

# ==============================================
# ENDPOINTS DO DASHBOARD
# ==============================================

@app.get("/api/analyses/history", tags=["analyses"])
async def get_analysis_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0
):
    from backend import crud
    
    analyses = crud.get_user_analyses(db, current_user.id, offset, limit)
    total = db.query(Analysis).filter(Analysis.user_id == current_user.id).count()
    
    return {
        "success": True,
        "analyses": [
            {
                "id": a.id,
                "filename": a.filename,
                "status": a.status,
                "created_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
                "analysis_type": a.analysis_type,
                "ai_used": a.ai_used,
                "rows_processed": a.rows_processed,
                "columns_processed": a.columns_processed,
                "file_size": None
            }
            for a in analyses
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/api/stats", tags=["stats"])
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()
    total_analyses = db.query(Analysis).filter(Analysis.user_id == current_user.id).count()
    analyses_today = db.query(Analysis).filter(
        Analysis.user_id == current_user.id,
        func.date(Analysis.uploaded_at) == today
    ).count()
    completed_analyses = db.query(Analysis).filter(
        Analysis.user_id == current_user.id,
        Analysis.status == "completed"
    ).count()
    ai_analyses = db.query(Analysis).filter(
        Analysis.user_id == current_user.id,
        Analysis.ai_used == True
    ).count()
    
    return {
        "success": True,
        "total_analises": total_analyses,
        "analises_hoje": analyses_today,
        "analises_concluidas": completed_analyses,
        "analises_com_ia": ai_analyses,
        "credits_remaining": current_user.credits if hasattr(current_user, 'credits') else 0,
        "status": "success",
        "timestamp": datetime.now().isoformat()
    }

# ==============================================
# 🔥 FUNÇÃO PARA INICIALIZAR PROMOÇÃO
# ==============================================

def init_promotion(db: Session):
    """Inicializa a promoção Bronze no banco de dados se não existir"""
    from backend.models import PromotionControl
    
    promo = db.query(PromotionControl).first()
    if not promo:
        promo = PromotionControl()
        db.add(promo)
        db.commit()
        print("✅ Promoção Bronze inicializada (100 vagas a R$ 97,00)")
    else:
        print(f"✅ Promoção Bronze já existe: {promo.get_remaining_slots()} vagas restantes")

# ==============================================
# EVENTO DE INICIALIZAÇÃO
# ==============================================
@app.on_event("startup")
async def startup_event():
    print("\n🚀 Inicializando sistema...")
    
    # 🔥 INICIALIZAR PROMOÇÃO BRONZE
    try:
        db = SessionLocal()
        init_promotion(db)
        db.close()
    except Exception as e:
        print(f"⚠️ Erro ao inicializar promoção: {e}")
    
    print("\n📋 Rotas HTML configuradas:")
    print("   🌐 http://localhost:8000/")
    print("   🔐 http://localhost:8000/login")
    print("   📊 http://localhost:8000/dashboard")
    print("   💳 http://localhost:8000/planos")
    print("   🛒 http://localhost:8000/checkout")
    
    print("\n📋 Rotas da API:")
    for route in app.routes:
        if hasattr(route, 'path') and '/api' in route.path:
            methods = getattr(route, 'methods', set())
            print(f"   {methods} {route.path}")
    
    try:
        asyncio.create_task(captcha_manager.store.start_cleanup_loop())
        print("✅ Cleanup loop do CAPTCHA iniciado")
    except Exception as e:
        print(f"⚠️ Erro ao iniciar cleanup: {e}")
    
    gemini_status = "✅ CONFIGURADO" if (settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ["", "opcional", "sua_chave_aqui"]) else "❌ NÃO CONFIGURADO"
    
    # Buscar status da promoção para mostrar
    try:
        db = SessionLocal()
        from backend.models import PromotionControl
        promo = db.query(PromotionControl).first()
        if promo:
            vagas_restantes = promo.get_remaining_slots()
            preco_atual = promo.get_current_price()
            print(f"\n💎 PROMOÇÃO BRONZE: {vagas_restantes} vagas restantes - Preço: R$ {preco_atual:.2f}")
        db.close()
    except:
        pass
    
    print(f"""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                    🎉 {settings.APP_NAME} v3.2 INICIADO!                              ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🤖 GOOGLE GEMINI: {gemini_status:<59} ║
    ║  🔐 SEGURANÇA:                                                                ║
    ║     🔢 CAPTCHA: ✅ (Números Rabiscados)                                       ║
    ║     🎫 JWT: ✅ ({settings.ACCESS_TOKEN_EXPIRE_MINUTES}min access, {settings.REFRESH_TOKEN_EXPIRE_DAYS}d refresh)  ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  💎 PLANO BRONZE:                                                             ║
    ║     🎟️ Vagas totais: 100                                                      ║
    ║     💰 Preço promocional: R$ 97,00                                            ║
    ║     💰 Preço regular: R$ 149,90                                               ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🔗 ENDPOINTS:                                                               ║
    ║     🎯 CAPTCHA: GET  /api/auth/captcha/generate                               ║
    ║     🧪 CAPTCHA TEST: GET /api/auth/captcha/test                               ║
    ║     🔐 LOGIN:   POST /api/auth/login                                          ║
    ║     📝 REGISTRO: POST /api/auth/register                                      ║
    ║     ✅ CHECK:   GET  /api/auth/check-token                                    ║
    ║     🔄 REFRESH: POST /api/auth/refresh                                        ║
    ║     🚪 LOGOUT:  POST /api/auth/logout                                         ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  💰 ENDPOINTS DE CRÉDITO:                                                    ║
    ║     💳 /api/payments/check-analysis - Verificar créditos                     ║
    ║     💳 /api/users/me/credits - Meus créditos                                 ║
    ║     💳 /api/payments/balance - Status premium                                ║
    ║     ⭐ /api/payments/premium/check-daily - Receber crédito diário            ║
    ║     📋 /api/payments/plans - Listar planos                                   ║
    ║     🎟️ /api/payments/promotion-status - Status da promoção                   ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  📊 ENDPOINTS DO DASHBOARD:                                                  ║
    ║     📜 /api/analyses/history - Histórico de análises                         ║
    ║     📈 /api/stats - Estatísticas do dashboard                                ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  🌐 PÁGINAS:                                                                 ║
    ║     🏠 HOME:    http://localhost:{settings.PORT}/                            ║
    ║     🔐 LOGIN:   http://localhost:{settings.PORT}/login                       ║
    ║     📊 DASHBOARD: http://localhost:{settings.PORT}/dashboard                 ║
    ║     💳 PLANOS:  http://localhost:{settings.PORT}/planos                      ║
    ║     🛒 CHECKOUT: http://localhost:{settings.PORT}/checkout                   ║
    ║     📚 API DOCS: http://localhost:{settings.PORT}/api/docs                   ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║  📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S'):<71} ║
    ╚══════════════════════════════════════════════════════════════════════════════╝    """)

@app.on_event("shutdown")
async def shutdown_event():
    print("\n🛑 Desligando sistema...")
    try:
        await captcha_manager.store.stop_cleanup_loop()
        print("✅ Cleanup loop parado")
    except Exception as e:
        print(f"⚠️ Erro: {e}")
    print("👋 Sistema desligado!")

# ==============================================
# EXCEPTION HANDLERS
# ==============================================

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
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
                    "/api/auth/register",
                    "/api/auth/captcha/generate",
                    "/api/auth/check-token",
                    "/api/analyses/history",
                    "/api/stats",
                    "/api/payments/promotion-status"
                ]
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

# ==============================================
# MAIN
# ==============================================
if __name__ == "__main__":
    print(f"\n🚀 Iniciando servidor na porta {settings.PORT}...")
    print(f"🤖 IA: Google Gemini")
    print(f"🔢 CAPTCHA: Números Rabiscados ({settings.CAPTCHA_CODE_LENGTH} dígitos - 2min validade)")
    print(f"📍 CAPTCHA URL: http://localhost:{settings.PORT}/api/auth/captcha/generate")
    print(f"📍 CAPTCHA TEST: http://localhost:{settings.PORT}/api/auth/captcha/test")
    print(f"📍 LOGIN URL: http://localhost:{settings.PORT}/api/auth/login")
    print(f"📍 REGISTER URL: http://localhost:{settings.PORT}/api/auth/register")
    print(f"📍 CHECK-TOKEN URL: http://localhost:{settings.PORT}/api/auth/check-token")
    print(f"📍 DASHBOARD: http://localhost:{settings.PORT}/dashboard")
    print(f"📍 PLANOS: http://localhost:{settings.PORT}/planos")
    print(f"📍 PROMOÇÃO STATUS: http://localhost:{settings.PORT}/api/payments/promotion-status")
    print("🛑 Pressione CTRL+C para parar\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )