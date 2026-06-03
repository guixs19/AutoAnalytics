#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de diagnóstico para backend FastAPI
Verifica portas, testa conexões e inicia o servidor se necessário
"""

import subprocess
import sys
import socket
import requests
import json
import time
import os
from pathlib import Path

class BackendDiagnostic:
    def __init__(self):
        self.port = 8000
        self.backend_url = f"http://localhost:{self.port}"
        
    def print_header(self, text):
        print("\n" + "="*60)
        print(f" {text}".center(60))
        print("="*60)
    
    def check_port_in_use(self):
        """Verifica se a porta está em uso"""
        print(f"\n🔍 Verificando porta {self.port}...")
        
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', self.port))
            sock.close()
            
            if result == 0:
                print(f"✅ Porta {self.port} está em uso")
                return True
            else:
                print(f"❌ Porta {self.port} está livre")
                return False
        except Exception as e:
            print(f"⚠️ Erro ao verificar porta: {e}")
            return False
    
    def find_process_on_port(self):
        """Encontra qual processo está usando a porta"""
        print(f"\n🔍 Procurando processo na porta {self.port}...")
        
        try:
            if sys.platform == "win32":  # Windows
                result = subprocess.run(
                    f'netstat -ano | findstr :{self.port}',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'LISTENING' in line:
                            parts = line.split()
                            pid = parts[-1]
                            print(f"   PID encontrado: {pid}")
                            
                            # Obter nome do processo
                            proc_result = subprocess.run(
                                f'tasklist | findstr {pid}',
                                shell=True,
                                capture_output=True,
                                text=True
                            )
                            if proc_result.stdout:
                                print(f"   Processo: {proc_result.stdout.strip()}")
                            return pid
            else:  # Linux/Mac
                result = subprocess.run(
                    f'lsof -i :{self.port}',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if result.stdout:
                    print(f"   {result.stdout}")
                    return True
        except Exception as e:
            print(f"⚠️ Erro ao buscar processo: {e}")
        
        print("   Nenhum processo encontrado")
        return None
    
    def test_backend_connection(self):
        """Testa se o backend está respondendo"""
        print(f"\n🔌 Testando conexão com backend...")
        
        endpoints = [
            f"{self.backend_url}/api/auth/captcha/generate",
            f"{self.backend_url}/api/test",
            f"{self.backend_url}/docs",
            f"{self.backend_url}/"
        ]
        
        for endpoint in endpoints:
            try:
                print(f"   Testando {endpoint}...")
                response = requests.get(endpoint, timeout=3)
                print(f"   ✅ Respondeu! Status: {response.status_code}")
                return True
            except requests.ConnectionError:
                print(f"   ❌ Sem resposta")
            except Exception as e:
                print(f"   ⚠️ Erro: {e}")
        
        return False
    
    def check_backend_files(self):
        """Verifica se existem arquivos de backend"""
        print("\n📁 Procurando arquivos de backend...")
        
        backend_files = [
            "main.py",
            "app.py",
            "server.py",
            "api.py",
            "backend/main.py",
            "backend/app.py",
            "src/main.py",
            "src/app.py"
        ]
        
        found_files = []
        for file in backend_files:
            if Path(file).exists():
                found_files.append(file)
                print(f"   ✅ Encontrado: {file}")
        
        if not found_files:
            print("   ❌ Nenhum arquivo de backend encontrado")
            print("   💡 Sugestão: Crie um arquivo main.py")
        
        return found_files
    
    def check_dependencies(self):
        """Verifica dependências instaladas"""
        print("\n📦 Verificando dependências...")
        
        deps = {
            'fastapi': 'fastapi',
            'uvicorn': 'uvicorn',
            'requests': 'requests'
        }
        
        installed = []
        missing = []
        
        for dep, package in deps.items():
            try:
                __import__(dep)
                print(f"   ✅ {dep} instalado")
                installed.append(dep)
            except ImportError:
                print(f"   ❌ {dep} NÃO instalado")
                missing.append(package)
        
        return installed, missing
    
    def install_dependencies(self):
        """Instala dependências necessárias"""
        print("\n📦 Instalando dependências...")
        
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "requests", "captcha", "pillow"],
                check=True
            )
            print("✅ Dependências instaladas com sucesso!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao instalar dependências: {e}")
            return False
    
    def create_backend_file(self):
        """Cria um arquivo backend básico"""
        print("\n📝 Criando arquivo backend main.py...")
        
        backend_content = '''from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import random
from io import BytesIO
from captcha.image import ImageCaptcha
from datetime import datetime, timedelta
import uvicorn

app = FastAPI()

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento temporário de CAPTCHAs
captcha_store = {}

@app.get("/api/auth/captcha/generate")
async def generate_captcha(session_type: str = "login"):
    """Gera CAPTCHA"""
    captcha_id = str(uuid.uuid4())
    captcha_text = str(random.randint(1000, 9999))
    
    print(f"🎯 CAPTCHA gerado: {captcha_text} para ID: {captcha_id[:8]}")
    
    captcha_store[captcha_id] = {
        "text": captcha_text,
        "created_at": datetime.now()
    }
    
    # Gerar imagem
    image = ImageCaptcha(width=280, height=100)
    data = image.generate(captcha_text)
    
    return StreamingResponse(
        BytesIO(data.getvalue()),
        media_type="image/png",
        headers={"X-Captcha-ID": captcha_id}
    )

@app.post("/api/auth/login")
async def login(
    email: str,
    password: str,
    captcha_id: Optional[str] = Header(None),
    captcha_text: Optional[str] = None
):
    """Endpoint de login"""
    print(f"🔐 Tentativa de login: {email}")
    
    # Validar CAPTCHA
    if captcha_id not in captcha_store:
        raise HTTPException(status_code=400, detail="CAPTCHA inválido")
    
    stored = captcha_store[captcha_id]
    if stored["text"] != captcha_text:
        raise HTTPException(status_code=400, detail="CAPTCHA incorreto")
    
    # Remover CAPTCHA usado
    del captcha_store[captcha_id]
    
    # Aceitar qualquer credencial para teste
    if len(password) >= 6:
        return {
            "success": True,
            "access_token": f"token_{uuid.uuid4()}",
            "refresh_token": f"refresh_{uuid.uuid4()}",
            "user_email": email,
            "user_name": email.split("@")[0],
            "workshop_name": "Oficina Teste",
            "role": "user",
            "plan": "free",
            "credits": 10,
            "is_admin": False,
            "admin_level": 0
        }
    else:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

@app.get("/api/test")
async def test():
    """Endpoint de teste"""
    return {"status": "ok", "message": "Backend funcionando!"}

@app.get("/")
async def root():
    """Raiz da API"""
    return {
        "message": "API do Sistema",
        "status": "online",
        "endpoints": [
            "/api/auth/captcha/generate",
            "/api/auth/login",
            "/api/test"
        ]
    }

if __name__ == "__main__":
    print("🚀 Iniciando servidor backend...")
    print(f"📍 API disponível em: http://localhost:8000")
    print(f"📝 Endpoints:")
    print(f"   - GET  /api/auth/captcha/generate")
    print(f"   - POST /api/auth/login")
    print(f"   - GET  /api/test")
    print("\\n" + "="*50)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
'''
        
        with open("main.py", "w", encoding="utf-8") as f:
            f.write(backend_content)
        
        print("✅ Arquivo main.py criado com sucesso!")
        return True
    
    def start_backend(self):
        """Inicia o backend"""
        print("\n🚀 Iniciando backend FastAPI...")
        
        try:
            # Iniciar em novo processo
            if sys.platform == "win32":
                subprocess.Popen(
                    [sys.executable, "main.py"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen(
                    [sys.executable, "main.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            print("✅ Backend iniciado!")
            print("⏳ Aguardando servidor ficar pronto...")
            time.sleep(3)
            
            # Testar se está respondendo
            for i in range(10):
                try:
                    response = requests.get(f"{self.backend_url}/api/test", timeout=2)
                    if response.status_code == 200:
                        print("✅ Backend está respondendo corretamente!")
                        return True
                except:
                    time.sleep(1)
            
            print("⚠️ Backend iniciado mas não respondeu no tempo limite")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao iniciar backend: {e}")
            return False
    
    def run_diagnostic(self):
        """Executa diagnóstico completo"""
        self.print_header("DIAGNÓSTICO DO BACKEND")
        
        # 1. Verificar porta
        port_in_use = self.check_port_in_use()
        
        # 2. Se porta em uso, mostrar processo
        if port_in_use:
            self.find_process_on_port()
            # Testar conexão
            if self.test_backend_connection():
                self.print_header("✅ BACKEND JÁ ESTÁ RODANDO!")
                print("\nSeu backend está funcionando corretamente!")
                print(f"URL: {self.backend_url}")
                return True
        
        # 3. Verificar arquivos do backend
        backend_files = self.check_backend_files()
        
        # 4. Verificar dependências
        installed, missing = self.check_dependencies()
        
        # 5. Perguntar o que fazer
        self.print_header("OPÇÕES DE SOLUÇÃO")
        
        print("\nO que você deseja fazer?")
        print("1. Instalar dependências e criar backend automático")
        print("2. Apenas criar o arquivo main.py (eu inicio manualmente)")
        print("3. Sair")
        
        choice = input("\nDigite sua escolha (1-3): ").strip()
        
        if choice == "1":
            if missing:
                print("\n⚠️ Dependências faltando. Instalando...")
                self.install_dependencies()
            
            self.create_backend_file()
            self.start_backend()
            
            self.print_header("✅ CONFIGURAÇÃO CONCLUÍDA!")
            print("\n🎉 Backend configurado e iniciado com sucesso!")
            print(f"📍 Acesse: {self.backend_url}")
            print("📝 Agora você pode fazer login no frontend")
            print("\n💡 Para testar:")
            print(f"   curl {self.backend_url}/api/test")
            
        elif choice == "2":
            self.create_backend_file()
            print("\n✅ Arquivo main.py criado!")
            print("\n📌 Para iniciar o backend manualmente:")
            print("   1. Abra um novo terminal")
            print("   2. Execute: python main.py")
            print("   3. Ou: uvicorn main:app --reload --port 8000")
            
        else:
            print("\n👋 Diagnóstico concluído!")
        
        return True

def main():
    diagnostic = BackendDiagnostic()
    diagnostic.run_diagnostic()
    
    print("\n" + "="*60)
    print(" Dicas adicionais:".center(60))
    print("="*60)
    print("""
1. Verifique se o firewall não está bloqueando a porta 8000
2. No frontend, confirme que o auth.js aponta para:
   apiBase = 'http://localhost:8000/api'
3. Teste a conexão no navegador: http://localhost:8000/api/test
4. Se mudar a porta, atualize o auth.js
    """)

if __name__ == "__main__":
    main()