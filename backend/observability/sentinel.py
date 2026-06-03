# backend/observability/sentinel.py
"""
SENTINEL - Sistema de Observabilidade e Alertas
-----------------------------------------------
Monitoramento, logs estruturados e alertas para o AutoAnalytics
"""

import requests
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import traceback

class AlertLevel(Enum):
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "🔥"
    CRITICAL = "🚨"
    SUSPICIOUS = "👮‍♂️"
    PAYMENT = "💰"
    PREMIUM = "💎"

class DiscordWebhook:
    """
    Envia alertas para o Discord via Webhook
    """
    
    def __init__(self, webhook_url: str = None):
        # Pega a URL do webhook do ambiente ou usa a que você passar
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK", "") or os.getenv("WEBHOOK_URL", "")
        self.app_name = "AutoAnalytics"
        
        if not self.webhook_url:
            print("⚠️  AVISO: DISCORD_WEBHOOK não configurado no .env")
            print("   Os alertas serão mostrados apenas no console")
    
    def send_alert(self, level: AlertLevel, title: str, **details):
        """
        Envia alerta para o Discord
        """
        # Cores do Discord (em decimal)
        colors = {
            AlertLevel.INFO: 5814783,        # Azul
            AlertLevel.SUCCESS: 3066993,      # Verde
            AlertLevel.WARNING: 16776960,     # Amarelo
            AlertLevel.ERROR: 15158332,       # Vermelho
            AlertLevel.CRITICAL: 10038562,    # Vermelho escuro
            AlertLevel.SUSPICIOUS: 10181046,  # Laranja
            AlertLevel.PAYMENT: 15844367,      # Roxo
            AlertLevel.PREMIUM: 15277667       # Rosa/roxo claro
        }
        
        # Criar o embed bonito
        embed = {
            "title": f"{level.value} {title}",
            "color": colors.get(level, 5814783),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": f"{self.app_name} • {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            },
            "fields": []
        }
        
        # Adicionar detalhes como campos
        for key, value in details.items():
            if value is not None:
                # Formatar nome do campo
                field_name = key.replace("_", " ").title()
                
                # Formatar valor
                if isinstance(value, float):
                    if "preço" in key.lower() or "valor" in key.lower() or "amount" in key.lower():
                        field_value = f"R$ {value:.2f}"
                    else:
                        field_value = str(value)
                elif isinstance(value, datetime):
                    field_value = value.strftime("%d/%m/%Y %H:%M")
                else:
                    field_value = str(value)
                
                embed["fields"].append({
                    "name": field_name,
                    "value": field_value[:1024],  # Limite do Discord
                    "inline": True
                })
        
        # Payload completo
        payload = {
            "embeds": [embed],
            "username": "AutoAnalytics Bot",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"  # Opcional
        }
        
        # Mostrar no console sempre
        print(f"\n📢 [{level.value}] {title}")
        for key, value in details.items():
            print(f"   📌 {key}: {value}")
        
        # Enviar para o Discord se tiver webhook configurado
        if self.webhook_url:
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
                
                if response.status_code == 204:
                    print(f"   ✅ Alerta enviado para o Discord")
                else:
                    print(f"   ⚠️  Erro no Discord: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Erro ao enviar para Discord: {e}")
        else:
            print(f"   ⚠️  Discord não configurado (só mostrado no console)")
        
        return True


# ==============================================
# INSTÂNCIA GLOBAL (SINGLETON)
# ==============================================

_webhook_instance = None

def get_webhook():
    """Retorna instância única do webhook"""
    global _webhook_instance
    if _webhook_instance is None:
        _webhook_instance = DiscordWebhook()
    return _webhook_instance


# ==============================================
# FUNÇÕES ESPECÍFICAS DE ALERTA
# ==============================================

# Alertas de Pagamento
def alert_payment_approved(user_email: str, amount: float, credits: int, plan: str):
    """💰 Pagamento aprovado"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.PAYMENT,
        "💰 NOVO PAGAMENTO APROVADO",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        creditos=credits,
        plano=plan,
        status="✅ Aprovado"
    )


def alert_payment_pending(user_email: str, amount: float, method: str):
    """⏳ Pagamento pendente"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.INFO,
        "⏳ PAGAMENTO PENDENTE",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        metodo=method,
        status="Aguardando pagamento"
    )


def alert_payment_failed(user_email: str, amount: float, error: str):
    """❌ Falha no pagamento"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.ERROR,
        "❌ FALHA NO PAGAMENTO",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        erro=error,
        status="Rejeitado"
    )


def alert_suspicious_payment(user_email: str, amount: float, reason: str):
    """🚨 Pagamento suspeito"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.CRITICAL,
        "🚨 PAGAMENTO SUSPEITO",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        motivo=reason,
        acao="🔍 Revisão manual necessária"
    )


# Alertas do Plano Premium
def alert_premium_activated(user_email: str, credits: int, expires_at: str):
    """💎 Novo assinante premium"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.PREMIUM,
        "💎 NOVO ASSINANTE PREMIUM",
        usuario=user_email,
        creditos_iniciais=credits,
        expira_em=expires_at,
        plano="Premium Mensal - R$ 58,90",
        mensagem="🎉 1 crédito por dia durante 30 dias!"
    )


def alert_daily_credits_distributed(user_email: str, day: int, credits: int, total: int):
    """📅 Crédito diário distribuído"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.SUCCESS,
        "📅 CRÉDITO DIÁRIO ADICIONADO",
        usuario=user_email,
        dia=f"{day}/30",
        creditos_hoje=credits,
        saldo_atual=total,
        mensagem="+1 crédito disponível! 🎯"
    )


def alert_premium_expiring_soon(user_email: str, days_left: int):
    """⏰ Plano premium perto de expirar"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.WARNING,
        "⏰ PLANO PREMIUM PERTO DE EXPIRAR",
        usuario=user_email,
        dias_restantes=days_left,
        acao="Renovar para continuar recebendo créditos diários"
    )


# Alertas de Sistema
def alert_system_error(error: Exception, endpoint: str = None, user: str = None):
    """🔥 Erro no sistema"""
    webhook = get_webhook()
    error_trace = traceback.format_exc()
    
    webhook.send_alert(
        AlertLevel.ERROR,
        "🔥 ERRO NO SISTEMA",
        endpoint=endpoint or "Desconhecido",
        usuario=user or "Sistema",
        erro=type(error).__name__,
        mensagem=str(error)[:200],
        trace=error_trace[:500] if error_trace else None
    )


def alert_system_startup():
    """🚀 Sistema iniciado"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.SUCCESS,
        "🚀 SISTEMA INICIADO",
        versao="3.2.0",
        ambiente=os.getenv("ENVIRONMENT", "development"),
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        status="✅ Online"
    )


def alert_new_user(user_email: str, name: str):
    """👤 Novo usuário registrado"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.INFO,
        "👤 NOVO USUÁRIO REGISTRADO",
        email=user_email,
        nome=name,
        data=datetime.now().strftime("%d/%m/%Y %H:%M")
    )


# Alertas de ML
def alert_training_started(model: str, data_size: int):
    """🧠 Treinamento iniciado"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.INFO,
        "🧠 TREINAMENTO INICIADO",
        modelo=model,
        dados=f"{data_size} registros",
        status="Processando..."
    )


def alert_training_completed(model: str, accuracy: float, time: float):
    """✅ Treinamento concluído"""
    webhook = get_webhook()
    webhook.send_alert(
        AlertLevel.SUCCESS,
        "✅ TREINAMENTO CONCLUÍDO",
        modelo=model,
        acuracia=f"{accuracy:.2%}",
        tempo=f"{time:.2f}s",
        status="Modelo pronto para uso"
    )


# ==============================================
# COMPATIBILIDADE
# ==============================================

# ✅ Para compatibilidade com código antigo que usa get_sentinel
get_sentinel = get_webhook

# ✅ Para compatibilidade com payment_service.py
def get_webhook_safe():
    """Versão segura que nunca retorna None"""
    return get_webhook()


# ==============================================
# EXPORTAÇÕES
# ==============================================

__all__ = [
    'AlertLevel',
    'DiscordWebhook',
    'get_webhook',
    'get_sentinel',  # Para compatibilidade
    'get_webhook_safe',  # Versão segura
    'alert_payment_approved',
    'alert_payment_pending',
    'alert_payment_failed',
    'alert_suspicious_payment',
    'alert_premium_activated',
    'alert_daily_credits_distributed',
    'alert_premium_expiring_soon',
    'alert_system_error',
    'alert_system_startup',
    'alert_new_user',
    'alert_training_started',
    'alert_training_completed'
]


print("✅ sentinel.py carregado - Sistema de observabilidade ativo")""