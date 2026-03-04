#!/usr/bin/env python3
"""
GERENCIADOR DO BANCO DE DADOS AUTOANALYTICS
===========================================
Script para verificar, backup, deletar e recriar o banco de dados
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

# Cores para terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    """Imprime cabeçalho colorido"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text:^60}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")

def print_success(text):
    """Imprime mensagem de sucesso"""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_warning(text):
    """Imprime mensagem de alerta"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_error(text):
    """Imprime mensagem de erro"""
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_info(text):
    """Imprime informação"""
    print(f"{Colors.BLUE}📊 {text}{Colors.END}")

def get_project_root():
    """Obtém a raiz do projeto"""
    return Path(__file__).parent.absolute()

def check_database():
    """Verifica o estado atual do banco de dados"""
    project_root = get_project_root()
    db_path = project_root / "autoanalytics.db"
    
    print_header("VERIFICAÇÃO DO BANCO DE DADOS")
    
    if not db_path.exists():
        print_error("Banco de dados NÃO encontrado!")
        print(f"Caminho: {db_path}")
        return False
    
    print_success(f"Banco encontrado: {db_path}")
    print_info(f"Tamanho: {db_path.stat().st_size / 1024:.1f} KB")
    print_info(f"Modificado: {datetime.fromtimestamp(db_path.stat().st_mtime).strftime('%d/%m/%Y %H:%M:%S')}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Lista tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print_info(f"Total de tabelas: {len(tables)}")
        for table in tables:
            table_name = table[0]
            # Conta registros
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"   📁 {table_name}: {count} registros")
                
                # Mostra colunas
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                for col in columns[:3]:  # Mostra apenas 3 primeiras colunas
                    print(f"      • {col[1]} ({col[2]})")
                if len(columns) > 3:
                    print(f"      • ... e mais {len(columns)-3} colunas")
                    
            except sqlite3.OperationalError as e:
                print(f"   ❌ {table_name}: Erro - {str(e)[:50]}...")
        
        conn.close()
        return True
        
    except Exception as e:
        print_error(f"Erro ao acessar banco: {str(e)}")
        return False

def backup_database():
    """Cria backup do banco atual"""
    project_root = get_project_root()
    db_path = project_root / "autoanalytics.db"
    backup_dir = project_root / "backups"
    
    if not db_path.exists():
        print_error("Não há banco para fazer backup!")
        return None
    
    # Cria diretório de backups se não existir
    backup_dir.mkdir(exist_ok=True)
    
    # Nome do backup com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"autoanalytics_backup_{timestamp}.db"
    backup_path = backup_dir / backup_name
    
    try:
        shutil.copy2(db_path, backup_path)
        print_success(f"Backup criado: {backup_path}")
        return backup_path
    except Exception as e:
        print_error(f"Erro ao criar backup: {e}")
        return None

def delete_database():
    """Deleta o banco de dados atual"""
    project_root = get_project_root()
    db_path = project_root / "autoanalytics.db"
    
    if not db_path.exists():
        print_warning("Banco já não existe!")
        return True
    
    try:
        # Confirmação
        print_warning(f"⚠️  ATENÇÃO: Você vai deletar o banco!")
        print(f"   Arquivo: {db_path}")
        print(f"   Tamanho: {db_path.stat().st_size / 1024:.1f} KB")
        
        confirm = input(f"\n{Colors.RED}Tem certeza? (digite 'SIM' para confirmar): {Colors.END}")
        
        if confirm.upper() == 'SIM':
            db_path.unlink()
            print_success("Banco deletado com sucesso!")
            return True
        else:
            print_warning("Operação cancelada pelo usuário.")
            return False
            
    except Exception as e:
        print_error(f"Erro ao deletar banco: {e}")
        return False

def recreate_database():
    """Recria o banco de dados do zero"""
    print_header("RECRIANDO BANCO DE DADOS")
    
    # Adiciona o caminho para imports
    project_root = get_project_root()
    backend_dir = project_root / "backend"
    
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(backend_dir))
    
    try:
        # Para qualquer processo Python em execução
        print_info("Parando servidores Python...")
        os.system("taskkill /F /IM python.exe 2>nul")
        
        # Importa e executa init_db
        print_info("Importando módulos...")
        from backend.database import engine, Base
        from backend.models import User, Analysis
        
        # Dropa e cria tabelas
        print_info("Recriando tabelas...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        print_success("Tabelas recriadas com sucesso!")
        
        # Agora executa o init_db.py para criar usuários
        print_info("Criando usuários de exemplo...")
        exec(open(backend_dir / "init_db.py").read())
        
        print_success("✅ Banco recriado com sucesso!")
        return True
        
    except ImportError as e:
        print_error(f"Erro de importação: {e}")
        print("Tentando método alternativo...")
        
        # Método alternativo: Executa init_db.py diretamente
        try:
            os.system(f'cd "{project_root}" && python backend/init_db.py')
            print_success("Banco recriado via init_db.py")
            return True
        except Exception as e2:
            print_error(f"Erro ao executar init_db.py: {e2}")
            return False
            
    except Exception as e:
        print_error(f"Erro ao recriar banco: {e}")
        return False

def show_menu():
    """Mostra menu interativo"""
    while True:
        print_header("GERENCIADOR DO BANCO AUTOANALYTICS")
        print(f"{Colors.BOLD}Selecione uma opção:{Colors.END}")
        print("1. 🔍 Verificar estado do banco")
        print("2. 💾 Criar backup do banco")
        print("3. 🗑️  Deletar banco atual")
        print("4. 🚀 Recriar banco do zero")
        print("5. 🔄 Fazer backup + recriar (recomendado)")
        print("6. 📊 Ver backups existentes")
        print("7. 📋 Ver SQL das tabelas")
        print("0. ❌ Sair")
        
        choice = input(f"\n{Colors.YELLOW}Opção: {Colors.END}").strip()
        
        if choice == '1':
            check_database()
        elif choice == '2':
            backup_database()
        elif choice == '3':
            delete_database()
        elif choice == '4':
            recreate_database()
        elif choice == '5':
            print_header("BACKUP + RECRIAÇÃO")
            if backup_database():
                if delete_database():
                    recreate_database()
        elif choice == '6':
            show_backups()
        elif choice == '7':
            show_sql_schema()
        elif choice == '0':
            print_success("Saindo... Até logo! 👋")
            break
        else:
            print_error("Opção inválida!")
        
        input(f"\n{Colors.YELLOW}Pressione Enter para continuar...{Colors.END}")

def show_backups():
    """Mostra backups existentes"""
    project_root = get_project_root()
    backup_dir = project_root / "backups"
    
    print_header("BACKUPS EXISTENTES")
    
    if not backup_dir.exists():
        print_warning("Nenhum backup encontrado!")
        return
    
    backups = list(backup_dir.glob("*.db"))
    backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not backups:
        print_warning("Nenhum backup encontrado!")
        return
    
    print_info(f"Total de backups: {len(backups)}")
    for i, backup in enumerate(backups, 1):
        size_kb = backup.stat().st_size / 1024
        mod_time = datetime.fromtimestamp(backup.stat().st_mtime)
        print(f"{i:2}. 📁 {backup.name}")
        print(f"     Tamanho: {size_kb:.1f} KB")
        print(f"     Data: {mod_time.strftime('%d/%m/%Y %H:%M:%S')}")

def show_sql_schema():
    """Mostra o SQL das tabelas"""
    project_root = get_project_root()
    db_path = project_root / "autoanalytics.db"
    
    if not db_path.exists():
        print_error("Banco não encontrado!")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        print_header("SQL DAS TABELAS")
        
        # Pega o SQL de criação de cada tabela
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = cursor.fetchall()
        
        for table_name, sql in tables:
            print(f"\n{Colors.BOLD}📋 TABELA: {table_name}{Colors.END}")
            print(f"{sql}")
            
            # Mostra índices da tabela
            cursor.execute(f"SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}'")
            indices = cursor.fetchall()
            if indices:
                print(f"\n   🔍 ÍNDICES:")
                for idx_name, idx_sql in indices:
                    print(f"      {idx_sql}")
        
        conn.close()
        
    except Exception as e:
        print_error(f"Erro ao ler schema: {e}")

def auto_fix():
    """Correção automática para erro 'no such column'"""
    print_header("CORREÇÃO AUTOMÁTICA")
    print_info("Diagnosticando problema...")
    
    project_root = get_project_root()
    db_path = project_root / "autoanalytics.db"
    
    if not db_path.exists():
        print_error("Banco não existe!")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Verifica se a coluna 'role' existe
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'role' not in columns:
            print_warning("Coluna 'role' não encontrada na tabela users!")
            print("Isso causa o erro 'no such column: users.role'")
            
            confirm = input(f"\n{Colors.YELLOW}Deseja corrigir automaticamente? (S/N): {Colors.END}")
            if confirm.upper() == 'S':
                conn.close()
                return recreate_database()
            else:
                print_warning("Correção cancelada.")
                return False
        else:
            print_success("Coluna 'role' encontrada!")
            return True
            
    except Exception as e:
        print_error(f"Erro no diagnóstico: {e}")
        return False

def main():
    """Função principal"""
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║     🗄️  GERENCIADOR DO BANCO AUTOANALYTICS v1.0     ║")
    print("║            por: Seu Assistente IA                    ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    # Verifica se estamos na pasta certa
    project_root = get_project_root()
    print(f"{Colors.BLUE}📂 Diretório: {project_root}{Colors.END}")
    
    # Verifica se é a pasta do projeto
    if not (project_root / "backend").exists():
        print_error("Pasta 'backend' não encontrada!")
        print("Execute este script da raiz do projeto AutoAnalytics.")
        return
    
    # Menu principal ou execução direta
    if len(sys.argv) > 1:
        # Modo linha de comando
        command = sys.argv[1].lower()
        if command == "check":
            check_database()
        elif command == "backup":
            backup_database()
        elif command == "delete":
            delete_database()
        elif command == "recreate":
            recreate_database()
        elif command == "fix":
            auto_fix()
        elif command == "auto":
            print("Executando correção automática...")
            auto_fix()
        else:
            print_error(f"Comando desconhecido: {command}")
            print("Comandos disponíveis: check, backup, delete, recreate, fix, auto")
    else:
        # Modo interativo
        show_menu()

if __name__ == "__main__":
    main()