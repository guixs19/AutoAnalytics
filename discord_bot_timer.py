# test_discord.py - Script para testar comunicação com Discord (CORRIGIDO)
import requests
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Cores para o terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header():
    """Imprime cabeçalho bonito"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.PURPLE}🚀 TESTE DE COMUNICAÇÃO COM DISCORD WEBHOOK{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")

def get_webhook_url():
    """Pega URL do webhook do .env ou digitação manual"""
    url = os.getenv("DISCORD_WEBHOOK")
    
    if url:
        print(f"{Colors.GREEN}✅ Webhook encontrado no .env{Colors.RESET}")
        print(f"📌 URL: {url[:50]}...\n")
        return url
    else:
        print(f"{Colors.YELLOW}⚠️  Webhook não encontrado no .env{Colors.RESET}")
        url = input(f"{Colors.BLUE}📝 Digite a URL do webhook do Discord: {Colors.RESET}").strip()
        
        if not url:
            print(f"{Colors.RED}❌ URL não fornecida. Saindo...{Colors.RESET}")
            return None
        return url

def send_to_discord(webhook_url, content, level="info"):
    """Envia mensagem para o Discord"""
    
    # Cores diferentes para cada nível
    colors = {
        "info": 5814783,     # Azul
        "success": 3066993,   # Verde
        "warning": 16776960,  # Amarelo
        "error": 15158332,    # Vermelho
        "critical": 10038562, # Vermelho escuro
        "payment": 15844367,  # Roxo
        "premium": 15277667   # Rosa
    }
    
    # Emojis para cada nível
    emojis = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "🔥",
        "critical": "🚨",
        "payment": "💰",
        "premium": "💎"
    }
    
    # 🔧 CORREÇÃO: usar datetime.now(timezone.utc) em vez de utcnow()
    now_utc = datetime.now(timezone.utc)
    
    # Criar embed bonito
    embed = {
        "title": f"{emojis.get(level, '📢')} Teste de Comunicação - Discord Webhook",
        "color": colors.get(level, 5814783),
        "timestamp": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "footer": {
            "text": f"Teste • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        },
        "fields": [
            {
                "name": "📝 Mensagem",
                "value": content,
                "inline": False
            },
            {
                "name": "📊 Nível",
                "value": level.upper(),
                "inline": True
            },
            {
                "name": "🕒 Horário",
                "value": datetime.now().strftime("%H:%M:%S"),
                "inline": True
            }
        ]
    }
    
    # Se for mensagem de teste especial, adicionar mais campos
    if "teste" in content.lower():
        embed["fields"].append({
            "name": "🧪 Tipo de Teste",
            "value": "Manual via terminal",
            "inline": True
        })
    
    payload = {
        "embeds": [embed],
        "username": "AutoAnalytics Tester",
        "avatar_url": "https://i.imgur.com/4M34hi2.png"
    }
    
    try:
        print(f"{Colors.YELLOW}📤 Enviando mensagem...{Colors.RESET}")
        response = requests.post(webhook_url, json=payload, timeout=10)
        
        if response.status_code == 204:
            print(f"{Colors.GREEN}✅ Mensagem enviada com sucesso!{Colors.RESET}")
            return True
        else:
            print(f"{Colors.RED}❌ Erro {response.status_code}: {response.text}{Colors.RESET}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Erro na conexão: {e}{Colors.RESET}")
        return False

def show_menu():
    """Mostra menu de opções"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}📋 ESCOLHA O TIPO DE MENSAGEM:{Colors.RESET}")
    print(f"{Colors.BLUE}1.{Colors.RESET} ℹ️  Info - Mensagem simples")
    print(f"{Colors.BLUE}2.{Colors.RESET} ✅ Success - Operação concluída")
    print(f"{Colors.BLUE}3.{Colors.RESET} ⚠️  Warning - Alerta")
    print(f"{Colors.BLUE}4.{Colors.RESET} 🔥 Error - Erro no sistema")
    print(f"{Colors.BLUE}5.{Colors.RESET} 🚨 Critical - ERRO GRAVE")
    print(f"{Colors.BLUE}6.{Colors.RESET} 💰 Payment - Pagamento")
    print(f"{Colors.BLUE}7.{Colors.RESET} 💎 Premium - Plano Premium")
    print(f"{Colors.BLUE}8.{Colors.RESET} 📊 Status do Sistema")
    print(f"{Colors.BLUE}9.{Colors.RESET} 🧪 Mensagem Customizada")
    print(f"{Colors.BLUE}0.{Colors.RESET} {Colors.RED}Sair{Colors.RESET}")
    return input(f"\n{Colors.BOLD}👉 Escolha uma opção: {Colors.RESET}")

def get_message_by_option(option):
    """Retorna mensagem baseada na opção"""
    messages = {
        "1": ("info", "ℹ️ Sistema operando normalmente. Teste de comunicação realizado com sucesso."),
        "2": ("success", "✅ Upload realizado! Arquivo processado com sucesso."),
        "3": ("warning", "⚠️ Créditos baixos: Restam apenas 3 créditos. Considere comprar mais."),
        "4": ("error", "🔥 Erro no processamento: Falha na conexão com o banco de dados."),
        "5": ("critical", "🚨 ERRO CRÍTICO: Sistema de pagamentos indisponível! Verifique imediatamente."),
        "6": ("payment", "💰 NOVO PAGAMENTO: R$ 58,90 - Plano Premium Mensal (joao@email.com)"),
        "7": ("premium", "💎 ASSINANTE PREMIUM: 1 crédito diário ativado para usuario@email.com"),
        "8": ("info", "📊 STATUS DO SISTEMA:\n• Usuários ativos: 42\n• Uploads hoje: 15\n• Créditos distribuídos: 128\n• Discord: ✅ Online"),
    }
    return messages.get(option, ("info", "🧪 Mensagem de teste personalizada"))

def main():
    """Função principal"""
    print_header()
    
    # Pegar webhook URL
    webhook_url = get_webhook_url()
    if not webhook_url:
        return
    
    while True:
        option = show_menu()
        
        if option == "0":
            print(f"\n{Colors.GREEN}👋 Até mais!{Colors.RESET}")
            break
        
        if option == "9":
            # Mensagem customizada
            level = input(f"{Colors.BLUE}📋 Nível (info/success/warning/error/critical/payment/premium): {Colors.RESET}").strip().lower()
            if level not in ["info", "success", "warning", "error", "critical", "payment", "premium"]:
                level = "info"
            message = input(f"{Colors.BLUE}📝 Digite sua mensagem: {Colors.RESET}").strip()
            if not message:
                message = "Mensagem de teste"
        else:
            level, message = get_message_by_option(option)
        
        # Enviar mensagem
        print(f"\n{Colors.CYAN}📤 Enviando: [{level.upper()}] {message[:50]}...{Colors.RESET}")
        success = send_to_discord(webhook_url, message, level)
        
        if success:
            print(f"{Colors.GREEN}✅ Mensagem entregue! Verifique o Discord.{Colors.RESET}")
        else:
            print(f"{Colors.RED}❌ Falha no envio. Tente novamente.{Colors.RESET}")
        
        input(f"\n{Colors.YELLOW}⏎ Pressione Enter para continuar...{Colors.RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠️  Operação cancelada pelo usuário{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Erro inesperado: {e}{Colors.RESET}")