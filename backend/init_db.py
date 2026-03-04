# backend/init_db.py - CRIA ADMIN E USUÁRIOS DE TESTE
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import engine
from backend.models import Base, User, UserRole
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.api.auth import get_password_hash

def init_database():
    """Inicializa o banco de dados com usuários de exemplo"""
    print("🗄️  Inicializando banco de dados...")
    
    # Criar tabelas
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas")
    
    # Criar usuários
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
        
        # ============ GESTOR ============
        manager = db.query(User).filter(User.email == "gestor@oficina.com").first()
        if not manager:
            manager = User(
                email="gestor@oficina.com",
                name="Gestor da Oficina",
                hashed_password=get_password_hash("Gestor@123"),
                workshop_name="Oficina Central",
                phone="(11) 98888-8888",
                role=UserRole.MANAGER,
                is_active=True,
                is_verified=True
            )
            db.add(manager)
            print("👔 Gestor criado")
        
        # ============ MECÂNICO 1 ============
        mecanico1 = db.query(User).filter(User.email == "joao@oficina.com").first()
        if not mecanico1:
            mecanico1 = User(
                email="joao@oficina.com",
                name="João Mecânico",
                hashed_password=get_password_hash("Joao@123"),
                workshop_name="Oficina Central",
                phone="(11) 97777-7777",
                role=UserRole.USER,
                is_active=True,
                is_verified=True
            )
            db.add(mecanico1)
            print("🔧 Mecânico João criado")
        
        # ============ MECÂNICO 2 ============
        mecanico2 = db.query(User).filter(User.email == "maria@oficina.com").first()
        if not mecanico2:
            mecanico2 = User(
                email="maria@oficina.com",
                name="Maria Mecânica",
                hashed_password=get_password_hash("Maria@123"),
                workshop_name="Oficina Central",
                phone="(11) 96666-6666",
                role=UserRole.USER,
                is_active=True,
                is_verified=True
            )
            db.add(mecanico2)
            print("🔧 Mecânica Maria criada")
        
        # ============ CLIENTE EXEMPLO ============
        cliente = db.query(User).filter(User.email == "cliente@email.com").first()
        if not cliente:
            cliente = User(
                email="cliente@email.com",
                name="Cliente Exemplo",
                hashed_password=get_password_hash("Cliente@123"),
                workshop_name="Oficina do Cliente",
                phone="(11) 95555-5555",
                role=UserRole.CLIENT,
                is_active=True,
                is_verified=False
            )
            db.add(cliente)
            print("👤 Cliente exemplo criado")
        
        db.commit()
        
        # Contagem
        total = db.query(User).count()
        admins = db.query(User).filter(User.role == UserRole.ADMIN).count()
        managers = db.query(User).filter(User.role == UserRole.MANAGER).count()
        users = db.query(User).filter(User.role == UserRole.USER).count()
        clients = db.query(User).filter(User.role == UserRole.CLIENT).count()
        
        print(f"\n🎉 Banco de dados inicializado!")
        print(f"📊 Estatísticas:")
        print(f"   👑 Admins: {admins}")
        print(f"   👔 Gestores: {managers}")
        print(f"   🔧 Usuários: {users}")
        print(f"   👤 Clientes: {clients}")
        print(f"   📈 Total: {total}")
        
        print(f"\n🔐 CREDENCIAIS PARA TESTE:")
        print(f"   👑 Admin: admin@autoanalytics.com / Admin@123")
        print(f"   👔 Gestor: gestor@oficina.com / Gestor@123")
        print(f"   🔧 Mecânico: joao@oficina.com / Joao@123")
        print(f"   🔧 Mecânica: maria@oficina.com / Maria@123")
        print(f"   👤 Cliente: cliente@email.com / Cliente@123")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_database()