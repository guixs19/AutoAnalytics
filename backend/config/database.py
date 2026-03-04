# backend/database.py - VERSÃO FINAL CORRIGIDA
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

print("🔧 Configurando banco de dados...")

# URL DO BANCO
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# SE NÃO TIVER URL OU FOR VAZIO, USA SQLITE
if not DATABASE_URL or DATABASE_URL == "":
    print("📁 Usando SQLite local (autoanalytics.db)")
    DATABASE_URL = "sqlite:///./autoanalytics.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}  # ✅ SÓ para SQLite!
    )
else:
    print(f"🔗 URL do banco detectada: {DATABASE_URL[:50]}...")
    
    # VERIFICA SE É POSTGRESQL
    if DATABASE_URL.startswith("postgresql://"):
        print("🐘 Configurando PostgreSQL...")
        
        # ✅ PARA POSTGRESQL: SEM connect_args!
        engine = create_engine(DATABASE_URL)
    else:
        print("📁 Configurando SQLite...")
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False}
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

print("✅ Banco de dados configurado com sucesso!")