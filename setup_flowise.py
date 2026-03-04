#!/usr/bin/env python3
"""
Configuração do Flowise Cloud para AutoAnalytics
"""

import os
from dotenv import load_dotenv

def setup_flowise():
    print("🔧 CONFIGURAÇÃO DO FLOWISE CLOUD")
    print("="*50)
    
    # Carregar ou criar .env
    if not os.path.exists(".env"):
        print("📝 Criando arquivo .env...")
        with open(".env", "w") as f:
            f.write("""# AutoAnalytics - Configuração
APP_NAME=AutoAnalytics
DEBUG=True
PORT=8000

# SUA URL DO FLOWISE
FLOWISE_URL=https://cloud.flowiseai.com/api/v1/prediction/07284d0d-4185-425a-b1e3-3ee3f187ab32

# Se seu flow precisar de API Key, coloque aqui
FLOWISE_API_KEY=

# Configurações de segurança
SECRET_KEY=mude-esta-chave-para-uma-segura

# Paths
MODEL_PATH=models/trained_model.h5
SCALER_PATH=models/scaler.pkl
""")
    
    load_dotenv()
    
    print("✅ Configuração carregada!")
    print(f"\n🌐 Sua URL do Flowise:")
    print(f"   {os.getenv('FLOWISE_URL')}")
    
    print("\n📋 Próximos passos:")
    print("1. Verifique se seu flow no Flowise está publicado")
    print("2. Teste o flow diretamente no Flowise Cloud")
    print("3. Execute: python test_flowise.py")
    print("4. Inicie o sistema: python backend/main.py")
    print("\n🎯 Dica: Configure seu flow para receber:")
    print("   - question: string (pergunta/contexto)")
    print("   - data: object (dados para análise)")
    print("   - context: string (tipo de análise)")

if __name__ == "__main__":
    setup_flowise()