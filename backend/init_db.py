# backend/init_db.py - ADICIONAR SUPORTE A POSTGRESQL
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import engine, SessionLocal
from backend.models import Base, User, UserRole
from backend.api.auth import get_password_hash
from sqlalchemy import text

def init_database():
    """Inicializa o banco de dados com usuários de exemplo"""
    print("🗄️  Inicializando banco de dados...")
    
    # 🔥 NOVO: Verificar tipo do banco
    is_postgres = "postgresql" in str(engine.url)
    print(f"📊 Conectando ao banco: {'PostgreSQL' if is_postgres else 'SQLite'}")
    
    # Criar extensão para PostgreSQL (UUID, etc)
    if is_postgres:
        with engine.connect() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
                conn.commit()
                print("✅ Extensão UUID habilitada no PostgreSQL")
            except Exception as e:
                print(f"⚠️ Extensão UUID: {e}")
    
    # Criar tabelas
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas/verificadas")
    
    # Resto do código permanece IGUAL...
    db = SessionLocal()
    try:
        # ============ ADMIN PRINCIPAL ============
        admin = db.query(User).filter(User.email == "admin@autoanalytics.com").first()
        if not admin:
            admin = User(
                email="admin@autoanalytics.com",
                name="Administrador Principal",
                hashed_password=get_password_hash("Admin@123"),
                workshop_name="Oficina Central",
                phone="(11) 99999-9999",
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True
            )
            db.add(admin)
            print("👑 Admin principal criado")
        
        # ... resto dos usuários (igual ao seu arquivo atual) ...
        
        db.commit()
        
        # Contagem
        total = db.query(User).count()
        print(f"\n🎉 Banco de dados inicializado com {total} usuários!")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_database()