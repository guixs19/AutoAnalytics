import os
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import requests
from functools import wraps

class AlertLevel(Enum):
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "🔥"
    CRITICAL = "🚨"
    SUSPICIOUS = "👮‍♂️"
    PAYMENT = "💰"

class Sentinel:
    def __init__(self, webhook_url: str = None, app_name: str = "AutoAnalytics"):
        self.webhook = webhook_url or os.getenv("DISCORD_WEBHOOK")
        self.app_name = app_name
        self.session = requests.Session()
        self.alert_count = 0
        self.last_alerts = []
        
    def _format_message(self, level: AlertLevel, title: str, details: Dict = None) -> dict:
        """Formata mensagem para Discord com embed"""
        
        colors = {
            AlertLevel.INFO: 5814783,        # Azul
            AlertLevel.SUCCESS: 3066993,      # Verde
            AlertLevel.WARNING: 16776960,     # Amarelo
            AlertLevel.ERROR: 15158332,       # Vermelho
            AlertLevel.CRITICAL: 10038562,    # Vermelho escuro
            AlertLevel.SUSPICIOUS: 10181046,  # Laranja
            AlertLevel.PAYMENT: 15844367       # Roxo
        }
        
        embed = {
            "title": f"{level.value} {title}",
            "color": colors.get(level, 5814783),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"{self.app_name} • Alert #{self.alert_count + 1}"}
        }
        
        if details:
            fields = []
            for key, value in details.items():
                if value is not None:
                    fields.append({
                        "name": key.replace("_", " ").title(),
                        "value": str(value)[:1024],
                        "inline": True
                    })
            
            if fields:
                embed["fields"] = fields
        
        return {"embeds": [embed]}
    
    def alert(self, level: AlertLevel, title: str, **details):
        """Envia alerta para Discord"""
        
        if not self.webhook:
            print(f"⚠️ Webhook não configurado: {title}")
            # Mesmo sem webhook, mostra no console
            print(f"[{level.value}] {title} - {details}")
            return
            
        self.alert_count += 1
        payload = self._format_message(level, title, details)
        
        # Guarda último alerta
        self.last_alerts.append({
            "timestamp": datetime.now(),
            "level": level.value,
            "title": title,
            "details": details
        })
        
        if len(self.last_alerts) > 10:
            self.last_alerts.pop(0)
        
        try:
            response = self.session.post(
                self.webhook,
                json=payload,
                timeout=3
            )
            response.raise_for_status()
        except Exception as e:
            print(f"❌ Erro ao enviar alerta: {e}")
    
    # ========== ALERTAS ESPECIALIZADOS PARA PAGAMENTOS ==========
    
    def payment_received(self, user_id: int, user_email: str, amount: float, credits: int, plan: str, payment_method: str):
        """💰 Novo pagamento recebido"""
        self.alert(
            AlertLevel.PAYMENT,
            "💰 Novo Pagamento Recebido",
            usuario=f"ID: {user_id} | {user_email}",
            valor=f"R$ {amount:.2f}",
            creditos=credits,
            plano=plan,
            metodo=payment_method.upper(),
            status="✅ APROVADO"
        )
    
    def payment_pending(self, user_id: int, user_email: str, amount: float, payment_method: str):
        """⏳ Pagamento pendente"""
        self.alert(
            AlertLevel.INFO,
            "⏳ Pagamento Pendente",
            usuario=f"ID: {user_id} | {user_email}",
            valor=f"R$ {amount:.2f}",
            metodo=payment_method.upper(),
            status="AGUARDANDO"
        )
    
    def payment_failed(self, user_id: int, user_email: str, amount: float, error: str, payment_method: str):
        """❌ Falha no pagamento"""
        self.alert(
            AlertLevel.ERROR,
            "❌ Falha no Pagamento",
            usuario=f"ID: {user_id} | {user_email}",
            valor=f"R$ {amount:.2f}",
            erro=error,
            metodo=payment_method.upper(),
            acao="✅ Sistema continuou normalmente"
        )
    
    def suspicious_payment(self, user_id: int, user_email: str, amount: float, reason: str, payment_method: str):
        """🚨 Pagamento suspeito - requer atenção"""
        self.alert(
            AlertLevel.CRITICAL,
            "🚨 PAGAMENTO SUSPEITO",
            usuario=f"ID: {user_id} | {user_email}",
            valor=f"R$ {amount:.2f}",
            motivo=reason,
            metodo=payment_method.upper(),
            acao="🔍 REVISÃO MANUAL NECESSÁRIA"
        )
    
    def credits_added(self, user_id: int, user_email: str, credits: int, total_credits: int, payment_id: int):
        """💎 Créditos adicionados à conta"""
        self.alert(
            AlertLevel.SUCCESS,
            "💎 Créditos Adicionados",
            usuario=f"ID: {user_id} | {user_email}",
            creditos_adicionados=credits,
            saldo_total=total_credits,
            pagamento=f"#{payment_id}",
            mensagem="✅ Pronto para usar!"
        )
    
    def low_credits(self, user_id: int, user_email: str, credits: int):
        """⚠️ Usuário com créditos baixos"""
        self.alert(
            AlertLevel.WARNING,
            "⚠️ Créditos Baixos",
            usuario=f"ID: {user_id} | {user_email}",
            creditos_restantes=credits,
            mensagem="Considere comprar mais créditos"
        )
    
    def first_payment(self, user_id: int, user_email: str, amount: float, plan: str):
        """🎉 Primeiro pagamento do usuário"""
        self.alert(
            AlertLevel.SUCCESS,
            "🎉 PRIMEIRO PAGAMENTO!",
            usuario=f"ID: {user_id} | {user_email}",
            valor=f"R$ {amount:.2f}",
            plano=plan,
            mensagem="Novo cliente convertido! 🥳"
        )
    
    def payment_refunded(self, user_id: int, user_email: str, amount: float, reason: str, payment_id: int):
        """↩️ Pagamento reembolsado"""
        self.alert(
            AlertLevel.WARNING,
            "↩️ Reembolso Processado",
            usuario=f"ID: {user_id} | {user_email}",
            valor=f"R$ {amount:.2f}",
            motivo=reason,
            pagamento=f"#{payment_id}",
            status="⚠️ Créditos removidos"
        )

# Singleton instance
_sentinel_instance = None

def get_sentinel():
    global _sentinel_instance
    if _sentinel_instance is None:
        _sentinel_instance = Sentinel()
    return _sentinel_instance