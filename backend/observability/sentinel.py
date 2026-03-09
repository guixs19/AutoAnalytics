import os
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
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

class Sentinel:
    def __init__(self, webhook_url: str = None, app_name: str = "SaaS-DataML"):
        self.webhook = webhook_url or os.getenv("DISCORD_WEBHOOK")
        self.app_name = app_name
        self.session = requests.Session()
        self.alert_count = 0
        self.last_alerts = []
        
    def _format_message(self, level: AlertLevel, title: str, details: Dict = None) -> dict:
        """Formata mensagem para Discord com embed"""
        
        colors = {
            AlertLevel.INFO: 5814783,      # Azul
            AlertLevel.SUCCESS: 3066993,    # Verde
            AlertLevel.WARNING: 16776960,   # Amarelo
            AlertLevel.ERROR: 15158332,     # Vermelho
            AlertLevel.CRITICAL: 10038562,  # Vermelho escuro
            AlertLevel.SUSPICIOUS: 10181046 # Laranja
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
                        "value": str(value)[:1024],  # Limite do Discord
                        "inline": True
                    })
            
            # Divide em duas colunas
            for i in range(0, len(fields), 2):
                embed["fields"] = fields[i:i+2]
        
        return {"embeds": [embed]}
    
    def alert(self, level: AlertLevel, title: str, **details):
        """Envia alerta para Discord"""
        
        if not self.webhook:
            print(f"⚠️ Webhook não configurado: {title}")
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
        
        # Mantém só últimos 10
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
    
    # Alertas especializados
    def payment_approved(self, user_id: str, amount: float, plan: str):
        """Alerta de pagamento aprovado"""
        self.alert(
            AlertLevel.SUCCESS,
            "💳 Novo Pagamento",
            usuario=user_id,
            valor=f"R$ {amount:.2f}",
            plano=plan,
            status="Aprovado"
        )
    
    def payment_suspicious(self, user_id: str, amount: float, reason: str):
        """Alerta de pagamento suspeito"""
        self.alert(
            AlertLevel.SUSPICIOUS,
            "🚨 Pagamento Suspeito",
            usuario=user_id,
            valor=f"R$ {amount:.2f}",
            motivo=reason,
            acao="Revisão manual necessária"
        )
    
    def model_training(self, status: str, model_name: str, metrics: Dict = None):
        """Alerta de treinamento de modelo"""
        details = {
            "modelo": model_name,
            "status": status
        }
        if metrics:
            details.update({
                "acuracia": f"{metrics.get('accuracy', 0):.2%}",
                "perda": f"{metrics.get('loss', 0):.4f}"
            })
        
        level = AlertLevel.SUCCESS if status == "concluído" else AlertLevel.WARNING
        self.alert(level, "🧠 Treinamento ML", **details)
    
    def system_error(self, error: Exception, endpoint: str = None, user_id: str = None):
        """Alerta de erro do sistema"""
        self.alert(
            AlertLevel.ERROR,
            "🔥 Erro no Sistema",
            endpoint=endpoint or "N/A",
            usuario=user_id or "Anônimo",
            erro=type(error).__name__,
            mensagem=str(error)[:200]
        )
    
    def data_upload(self, user_id: str, filename: str, size_mb: float, rows: int = None):
        """Alerta de upload de dados"""
        details = {
            "usuario": user_id,
            "arquivo": filename,
            "tamanho": f"{size_mb:.2f} MB"
        }
        if rows:
            details["linhas"] = f"{rows:,}"
            
        self.alert(
            AlertLevel.INFO,
            "📁 Dados Carregados",
            **details
        )

# Singleton instance
_sentinel_instance = None

def get_sentinel():
    global _sentinel_instance
    if _sentinel_instance is None:
        _sentinel_instance = Sentinel()
    return _sentinel_instance

# Decorator para monitoramento automático
def monitor_errors(alert_type: str = None):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                sentinel = get_sentinel()
                sentinel.system_error(
                    e,
                    endpoint=func.__name__,
                    user_id=kwargs.get('user_id')
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                sentinel = get_sentinel()
                sentinel.system_error(
                    e,
                    endpoint=func.__name__,
                    user_id=kwargs.get('user_id')
                )
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator