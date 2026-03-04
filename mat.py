# diagnostico.py
import sys
import os
import traceback
from pathlib import Path

print("=" * 60)
print("🔍 AUTOANALYTICS - SISTEMA DE DIAGNÓSTICO")
print("=" * 60)

# Configurar paths
PROJECT_ROOT = Path(__file__).parent.absolute()
BACKEND_DIR = PROJECT_ROOT / "backend"

print(f"📂 Raiz do projeto: {PROJECT_ROOT}")
print(f"📂 Pasta backend: {BACKEND_DIR}")
print()

# Adicionar ao sys.path
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

print("🔧 Python path:")
for i, p in enumerate(sys.path[:5], 1):
    print(f"  {i}. {p}")
print()

# ==============================================
# DIAGNÓSTICO PASSO A PASSO
# ==============================================

def test_import(module_name, description):
    """Testa importação de módulo"""
    try:
        __import__(module_name)
        print(f"✅ {description}: OK")
        return True
    except Exception as e:
        print(f"❌ {description}: FALHOU")
        print(f"   Erro: {e}")
        traceback.print_exc(limit=1)
        return False

def test_import_from(module_name, attr_name, description):
    """Testa importação de atributo específico"""
    try:
        module = __import__(module_name, fromlist=[attr_name])
        getattr(module, attr_name)
        print(f"✅ {description}: OK")
        return True
    except Exception as e:
        print(f"❌ {description}: FALHOU")
        print(f"   Erro: {e}")
        return False

print("📋 TESTANDO IMPORTS BÁSICOS")
print("-" * 40)

# 1. Testar módulos base
test_import("backend.database", "database.py")
test_import("backend.models", "models.py")
test_import("backend.crud", "crud.py")
test_import("backend.security", "security.py")
print()

# 2. Testar configurações
test_import("backend.config.settings", "config/settings.py")
test_import_from("backend.config.settings", "settings", "settings import")
print()

# 3. Testar serviços
test_import("backend.config.file_manager", "file_manager.py")
test_import_from("backend.config.file_manager", "FileManager", "FileManager class")
print()

test_import("backend.preprocessing", "preprocessing.py")
test_import_from("backend.preprocessing", "DataPreprocessor", "DataPreprocessor class")
print()

# 4. Testar API
print("📋 TESTANDO IMPORTS DA API")
print("-" * 40)

# Testar imports individuais dos arquivos da API
print("Testando auth_routes.py...")
try:
    with open(BACKEND_DIR / "api" / "auth_routes.py", "r", encoding="utf-8") as f:
        content = f.read()
        print(f"   ✅ auth_routes.py encontrado ({len(content)} bytes)")
except Exception as e:
    print(f"   ❌ auth_routes.py não encontrado: {e}")

print("Testando routes.py...")
try:
    with open(BACKEND_DIR / "api" / "routes.py", "r", encoding="utf-8") as f:
        content = f.read()
        print(f"   ✅ routes.py encontrado ({len(content)} bytes)")
except Exception as e:
    print(f"   ❌ routes.py não encontrado: {e}")

print("Testando payment_routes.py...")
try:
    with open(BACKEND_DIR / "api" / "payment_routes.py", "r", encoding="utf-8") as f:
        content = f.read()
        print(f"   ✅ payment_routes.py encontrado ({len(content)} bytes)")
except Exception as e:
    print(f"   ❌ payment_routes.py não encontrado: {e}")
print()

# 5. Testar __init__.py
print("📋 TESTANDO __init__.py")
print("-" * 40)

api_init = BACKEND_DIR / "api" / "__init__.py"
if api_init.exists():
    with open(api_init, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if content:
            print(f"⚠️  __init__.py NÃO está vazio!")
            print(f"   Conteúdo: {content[:100]}...")
        else:
            print(f"✅ __init__.py está vazio (correto)")
else:
    print(f"✅ __init__.py não existe (criando vazio)")
    with open(api_init, "w") as f:
        f.write("# Arquivo vazio\n")
    print(f"   Arquivo criado: {api_init}")
print()

# 6. Testar importação completa
print("📋 TESTANDO IMPORTAÇÃO COMPLETA")
print("-" * 40)

try:
    print("Tentando importar backend.api.auth_routes...")
    from backend.api import auth_routes
    print(f"✅ auth_routes importado com sucesso!")
    print(f"   Router disponível: {hasattr(auth_routes, 'router')}")
except Exception as e:
    print(f"❌ Erro ao importar auth_routes:")
    print(f"   {e}")
    traceback.print_exc(limit=2)

try:
    print("\nTentando importar backend.api.routes...")
    from backend.api import routes
    print(f"✅ routes importado com sucesso!")
    print(f"   Router disponível: {hasattr(routes, 'router')}")
except Exception as e:
    print(f"❌ Erro ao importar routes:")
    print(f"   {e}")
    traceback.print_exc(limit=2)

try:
    print("\nTentando importar backend.api.payment_routes...")
    from backend.api import payment_routes
    print(f"✅ payment_routes importado com sucesso!")
    print(f"   Router disponível: {hasattr(payment_routes, 'router')}")
except Exception as e:
    print(f"❌ Erro ao importar payment_routes:")
    print(f"   {e}")
    traceback.print_exc(limit=2)

print("\n" + "=" * 60)
print("🔍 DIAGNÓSTICO CONCLUÍDO")
print("=" * 60)