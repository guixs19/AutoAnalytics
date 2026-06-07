# backend/observability/discord_internal.py
"""
Sistema de Alertas Internos via Discord
Para uso APENAS do time AutoAnalytics
"""

import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Tipos de alerta para o time"""
    CLIENTE_NOVO = "🎉 NOVO CLIENTE"
    CLIENTE_PREMIUM = "💎 NOVO PREMIUM"
    PAGAMENTO = "💰 PAGAMENTO"
    ERRO_SISTEMA = "🔥 ERRO CRÍTICO"
    DEPLOY = "🚀 DEPLOY"
    MANUTENCAO = "🔧 MANUTENÇÃO"
    METRICA = "📊 MÉTRICA"
    SEGURANCA = "🔒 ALERTA SEGURANÇA"
    ANALISE = "📁 ANÁLISE CONCLUÍDA"


class DiscordInternal:
    """
    Webhook para canais INTERNOS do time
    Não expor para clientes!
    """
    
    def __init__(self):
        # Webhook específico para o canal do TIME
        self.webhook_url = os.getenv("DISCORD_INTERNAL_WEBHOOK", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._queue = []
        self._is_processing = False
        
        if not self.webhook_url:
            logger.warning("⚠️ DISCORD_INTERNAL_WEBHOOK não configurado")
            logger.info("   Os alertas internos serão mostrados apenas no console")
    
    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def send_alert(
        self,
        alert_type: AlertType,
        title: str,
        description: str = None,
        fields: Dict[str, Any] = None,
        color: int = None,
        mention_everyone: bool = False
    ):
        """
        Envia alerta para o canal interno do Discord
        """
        # Cores por tipo
        colors = {
            AlertType.CLIENTE_NOVO: 0x00ff00,      # Verde
            AlertType.CLIENTE_PREMIUM: 0xff00ff,    # Roxo
            AlertType.PAGAMENTO: 0x00ff00,          # Verde
            AlertType.ERRO_SISTEMA: 0xff0000,       # Vermelho
            AlertType.DEPLOY: 0x00aaff,             # Azul
            AlertType.MANUTENCAO: 0xffa500,         # Laranja
            AlertType.METRICA: 0x9b59b6,            # Roxo claro
            AlertType.SEGURANCA: 0xff0000,          # Vermelho
            AlertType.ANALISE: 0x2ecc71             # Verde claro
        }
        
        embed = {
            "title": f"{alert_type.value} - {title}",
            "color": color or colors.get(alert_type, 0x3498db),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": f"AutoAnalytics Time • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            }
        }
        
        if description:
            embed["description"] = description
        
        if fields:
            embed["fields"] = []
            for name, value in fields.items():
                embed["fields"].append({
                    "name": name.replace("_", " ").title(),
                    "value": str(value)[:1024],
                    "inline": len(str(value)) < 50
                })
        
        # Montar payload
        payload = {
            "embeds": [embed],
            "username": "AutoAnalytics Monitor",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"
        }
        
        if mention_everyone:
            payload["content"] = "@everyone"
        
        # Log no console
        self._log_console(alert_type, title, description, fields)
        
        # Enviar para Discord
        if self.webhook_url:
            await self._send_webhook(payload)
    
    def _log_console(self, alert_type: AlertType, title: str, description: str, fields: Dict):
        """Log no console colorido"""
        print(f"\n{'='*70}")
        print(f"🎯 {alert_type.value} - {title}")
        print(f"{'─'*70}")
        if description:
            print(f"📝 {description}")
        if fields:
            for key, value in fields.items():
                print(f"   📌 {key}: {value}")
        print(f"{'='*70}\n")
    
    async def _send_webhook(self, payload: Dict):
        """Envia webhook com retry"""
        session = await self._get_session()
        
        for attempt in range(3):
            try:
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status == 204:
                        logger.debug("✅ Alerta interno enviado")
                        return
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        await asyncio.sleep(retry_after)
                    else:
                        logger.warning(f"⚠️ Discord respondeu {resp.status}")
            except Exception as e:
                logger.error(f"❌ Erro no webhook: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
    
    async def close(self):
        if self._session:
            await self._session.close()


# ==============================================
# ALERTAS ESPECÍFICOS PARA O TIME
# ==============================================

discord = DiscordInternal()


async def alert_new_client(user_name: str, user_email: str, workshop: str, is_premium: bool = False):
    """🎉 Novo cliente se cadastrou"""
    await discord.send_alert(
        AlertType.CLIENTE_NOVO if not is_premium else AlertType.CLIENTE_PREMIUM,
        f"{'PREMIUM' if is_premium else 'GRÁTIS'} - {workshop}",
        description=f"{user_name} acabou de se cadastrar!",
        fields={
            "nome": user_name,
            "email": user_email,
            "oficina": workshop,
            "tipo": "PREMIUM" if is_premium else "GRÁTIS",
            "horario": datetime.now().strftime("%H:%M:%S")
        }
    )


async def alert_payment_received(user_name: str, amount: float, plan: str, payment_method: str):
    """💰 Pagamento recebido - comemoração do time"""
    await discord.send_alert(
        AlertType.PAGAMENTO,
        f"R$ {amount:.2f} - {plan}",
        description=f"Pagamento recebido de {user_name}",
        fields={
            "cliente": user_name,
            "valor": f"R$ {amount:.2f}",
            "plano": plan,
            "metodo": payment_method,
            "comissao_estimada": f"R$ {amount * 0.7:.2f}"  # Exemplo: 70% líquido
        }
    )


async def alert_system_error_critical(error: str, endpoint: str, user: str = None):
    """🔥 Erro crítico - precisa de atenção imediata"""
    await discord.send_alert(
        AlertType.ERRO_SISTEMA,
        "ERRO CRÍTICO NO SISTEMA",
        description=f"```{error[:500]}```",
        fields={
            "endpoint": endpoint,
            "usuario": user or "Sistema",
            "horario": datetime.now().strftime("%H:%M:%S")
        },
        mention_everyone=True  # Acorda todo mundo!
    )


async def alert_deploy_started(version: str, deployed_by: str):
    """🚀 Deploy iniciado"""
    await discord.send_alert(
        AlertType.DEPLOY,
        "Deploy Iniciado",
        description=f"Versão {version} sendo implantada",
        fields={
            "versao": version,
            "responsavel": deployed_by,
            "status": "🟡 Em andamento"
        }
    )


async def alert_deploy_completed(version: str, duration: float):
    """✅ Deploy concluído com sucesso"""
    await discord.send_alert(
        AlertType.DEPLOY,
        "Deploy Concluído ✅",
        description=f"Versão {version} no ar!",
        fields={
            "versao": version,
            "duracao": f"{duration:.2f} segundos",
            "status": "🟢 Online"
        }
    )


async def alert_daily_metrics(metrics: Dict):
    """📊 Relatório diário para o time"""
    await discord.send_alert(
        AlertType.METRICA,
        "Relatório Diário",
        description="Métricas das últimas 24h",
        fields={
            "👥 Novos usuários": metrics.get('new_users', 0),
            "💰 Receita": f"R$ {metrics.get('revenue', 0):.2f}",
            "📁 Análises": metrics.get('analyses_count', 0),
            "💎 Premium ativos": metrics.get('active_premium', 0),
            "⭐ Satisfação": f"{metrics.get('satisfaction', 0)}/5"
        }
    )


async def alert_suspicious_activity(user_email: str, action: str, ip: str, details: str):
    """🔒 Atividade suspeita - segurança"""
    await discord.send_alert(
        AlertType.SEGURANCA,
        "Atividade Suspeita Detectada",
        description=f"Usuário {user_email} realizou ação suspeita",
        fields={
            "usuario": user_email,
            "acao": action,
            "ip": ip,
            "detalhes": details,
            "recomendacao": "🔍 Verificar logs"
        }
    )


async def alert_analysis_completed(user_email: str, filename: str, rows: int):
    """📁 Análise concluída (métrica de uso)"""
    await discord.send_alert(
        AlertType.ANALISE,
        "Nova Análise Concluída",
        fields={
            "usuario": user_email,
            "arquivo": filename,
            "registros": rows,
            "horario": datetime.now().strftime("%H:%M")
        }
    )


# ==============================================
# TAREFA AUTOMÁTICA DE RELATÓRIO DIÁRIO
# ==============================================

async def schedule_daily_report():
    """Agenda relatório diário às 9h da manhã"""
    while True:
        now = datetime.now()
        # Próxima execução: 9h
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run = next_run + timedelta(days=1)
        
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        # Gerar relatório
        from backend.database import SessionLocal
        from backend import crud
        
        db = SessionLocal()
        try:
            metrics = {
                'new_users': crud.get_new_users_count(db, days=1),
                'revenue': crud.get_daily_revenue(db),
                'analyses_count': crud.get_daily_analyses_count(db),
                'active_premium': crud.get_active_premium_count(db),
                'satisfaction': 4.8  # Placeholder
            }
            await alert_daily_metrics(metrics)
        finally:
            db.close()


# ==============================================
# EXPORTAÇÕES
# ==============================================

__all__ = [
    'discord',
    'AlertType',
    'alert_new_client',
    'alert_payment_received',
    'alert_system_error_critical',
    'alert_deploy_started',
    'alert_deploy_completed',
    'alert_daily_metrics',
    'alert_suspicious_activity',
    'alert_analysis_completed',
    'schedule_daily_report'
]