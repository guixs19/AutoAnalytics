# backend/database.py - VERSÃO CORRIGIDA
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./autoanalytics.db")

# 🔥 CORREÇÃO: Só adiciona check_same_thread se for SQLite
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# 🔥 CORREÇÃO: Adiciona pool settings para PostgreSQL
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,      # Verifica se conexão está viva
    pool_size=10,            # Tamanho do pool de conexões
    max_overflow=20          # Conexões extras se necessário
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas!")