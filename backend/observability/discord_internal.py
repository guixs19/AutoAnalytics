# backend/observability/discord_internal.py
"""
Sistema de Alertas Internos via Discord
Para uso APENAS do time AutoAnalytics
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass, field
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
import traceback

# Tentar importar dependências opcionais
try:
    import aiohttp
    from aiohttp import ClientTimeout, ClientSession
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    import requests

try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

logger = logging.getLogger(__name__)

# Configurar logging com rotação
log_handler = RotatingFileHandler(
    'discord_alerts.log', 
    maxBytes=10_485_760,  # 10MB
    backupCount=5
)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(log_handler)


class AlertPriority(Enum):
    """Prioridade dos alertas"""
    LOW = "🔵"
    MEDIUM = "🟡"
    HIGH = "🔴"
    CRITICAL = "🔥"


class AlertType(Enum):
    """Tipos de alerta para o time"""
    CLIENTE_NOVO = ("🎉 NOVO CLIENTE", AlertPriority.MEDIUM)
    CLIENTE_PREMIUM = ("💎 NOVO PREMIUM", AlertPriority.HIGH)
    PAGAMENTO = ("💰 PAGAMENTO", AlertPriority.HIGH)
    ERRO_SISTEMA = ("🔥 ERRO CRÍTICO", AlertPriority.CRITICAL)
    DEPLOY = ("🚀 DEPLOY", AlertPriority.HIGH)
    MANUTENCAO = ("🔧 MANUTENÇÃO", AlertPriority.MEDIUM)
    METRICA = ("📊 MÉTRICA", AlertPriority.LOW)
    SEGURANCA = ("🔒 ALERTA SEGURANÇA", AlertPriority.CRITICAL)
    ANALISE = ("📁 ANÁLISE CONCLUÍDA", AlertPriority.LOW)
    PERFORMANCE = ("⚡ ALERTA PERFORMANCE", AlertPriority.HIGH)
    BACKUP = ("💾 BACKUP", AlertPriority.MEDIUM)
    
    def __init__(self, display: str, priority: AlertPriority):
        self.display = display
        self.priority = priority
    
    @property
    def color(self) -> int:
        """Cores por tipo e prioridade"""
        colors = {
            AlertPriority.LOW: 0x3498db,      # Azul
            AlertPriority.MEDIUM: 0xf39c12,   # Laranja
            AlertPriority.HIGH: 0xe67e22,     # Laranja escuro
            AlertPriority.CRITICAL: 0xe74c3c  # Vermelho
        }
        return colors.get(self.priority, 0x95a5a6)


@dataclass
class AlertConfig:
    """Configuração de alerta"""
    retry_attempts: int = 3
    retry_delay: float = 2.0
    rate_limit_per_minute: int = 30
    batch_size: int = 5
    batch_interval: float = 1.0
    enable_mentions: bool = True
    require_confirmation: bool = False


@dataclass
class AlertBatch:
    """Batch de alertas para enviar"""
    alerts: List[Dict] = field(default_factory=list)
    last_sent: datetime = field(default_factory=datetime.now)


class RateLimiter:
    """Rate limiter para evitar spam"""
    
    def __init__(self, max_requests: int = 30, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    async def acquire(self):
        """Adquirir permissão para enviar"""
        now = datetime.now()
        # Limpar requisições antigas
        self.requests = [r for r in self.requests 
                        if (now - r).total_seconds() < self.time_window]
        
        if len(self.requests) >= self.max_requests:
            oldest = self.requests[0]
            wait_time = self.time_window - (now - oldest).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        self.requests.append(now)


class DiscordInternal:
    """
    Webhook para canais INTERNOS do time
    Não expor para clientes!
    """
    
    def __init__(self, config: Optional[AlertConfig] = None):
        self.webhook_url = os.getenv("DISCORD_INTERNAL_WEBHOOK", "")
        self.test_webhook_url = os.getenv("DISCORD_TEST_WEBHOOK", "")
        self.config = config or AlertConfig()
        
        self._session: Optional[ClientSession] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._rate_limiter = RateLimiter(
            max_requests=self.config.rate_limit_per_minute
        )
        self._batch = AlertBatch()
        self._is_processing = False
        self._background_tasks: List[asyncio.Task] = []
        
        # Cache para evitar alertas duplicados
        self._cache: Dict[str, datetime] = {}
        self._cache_ttl = 300  # 5 minutos
        
        # Redis para cache distribuído (opcional)
        self._redis = None
        if HAS_REDIS and os.getenv("REDIS_URL"):
            self._setup_redis()
        
        if not self.webhook_url:
            logger.warning("⚠️ DISCORD_INTERNAL_WEBHOOK não configurado")
            logger.info("   Os alertas internos serão mostrados apenas no console")
        else:
            # Iniciar processador de fila
            self._background_tasks.append(
                asyncio.create_task(self._process_queue())
            )
    
    def _setup_redis(self):
        """Configurar Redis para cache distribuído"""
        async def init_redis():
            self._redis = await redis.from_url(os.getenv("REDIS_URL"))
        asyncio.create_task(init_redis())
    
    async def _get_session(self) -> ClientSession:
        """Obter sessão HTTP com timeout configurado"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
        return self._session
    
    async def _is_duplicate(self, alert_key: str) -> bool:
        """Verificar se alerta é duplicado"""
        if self._redis and self._redis is not None:
            return await self._redis.exists(f"alert:{alert_key}") > 0
        
        if alert_key in self._cache:
            if (datetime.now() - self._cache[alert_key]).total_seconds() < self._cache_ttl:
                return True
        return False
    
    async def _mark_as_sent(self, alert_key: str):
        """Marcar alerta como enviado"""
        if self._redis and self._redis is not None:
            await self._redis.setex(f"alert:{alert_key}", self._cache_ttl, "1")
        else:
            self._cache[alert_key] = datetime.now()
    
    async def send_alert(
        self,
        alert_type: AlertType,
        title: str,
        description: str = None,
        fields: Dict[str, Any] = None,
        color: int = None,
        mention_everyone: bool = False,
        mention_roles: List[str] = None,
        mention_users: List[str] = None,
        priority: AlertPriority = None,
        require_confirmation: bool = False,
        dedup_key: str = None
    ):
        """
        Envia alerta para o canal interno do Discord
        """
        # Verificar duplicação
        if dedup_key:
            alert_key = f"{alert_type.name}:{dedup_key}"
            if await self._is_duplicate(alert_key):
                logger.debug(f"Alerta duplicado ignorado: {alert_key}")
                return
            await self._mark_as_sent(alert_key)
        
        # Definir prioridade
        if priority is None:
            priority = alert_type.priority
        
        # Construir embed
        embed = self._build_embed(
            alert_type, title, description, fields, 
            color or alert_type.color
        )
        
        # Montar payload
        payload = {
            "embeds": [embed],
            "username": "AutoAnalytics Monitor",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"
        }
        
        # Adicionar menções
        content_parts = []
        if mention_everyone and self.config.enable_mentions:
            content_parts.append("@everyone")
        if mention_roles:
            content_parts.extend(mention_roles)
        if mention_users:
            content_parts.extend(mention_users)
        
        if content_parts:
            payload["content"] = " ".join(content_parts)
        
        # Log no console
        self._log_console(alert_type, title, description, fields, priority)
        
        # Adicionar à fila
        await self._queue.put({
            "payload": payload,
            "priority": priority.value,
            "require_confirmation": require_confirmation or self.config.require_confirmation
        })
    
    def _build_embed(self, alert_type: AlertType, title: str, 
                     description: str, fields: Dict, color: int) -> Dict:
        """Construir embed do Discord"""
        embed = {
            "title": f"{alert_type.display} - {title}",
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": f"AutoAnalytics Time • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            }
        }
        
        if description:
            embed["description"] = description[:2000]  # Limitar tamanho
        
        if fields:
            embed["fields"] = []
            for name, value in fields.items():
                embed["fields"].append({
                    "name": str(name).replace("_", " ").title()[:256],
                    "value": str(value)[:1024],
                    "inline": len(str(value)) < 50 and len(embed["fields"]) % 2 == 0
                })
        
        # Adicionar campo de prioridade se for crítico
        if alert_type.priority == AlertPriority.CRITICAL:
            if not embed.get("fields"):
                embed["fields"] = []
            embed["fields"].insert(0, {
                "name": "🚨 PRIORIDADE",
                "value": "CRÍTICA - Atenção imediata necessária!",
                "inline": False
            })
        
        return embed
    
    def _log_console(self, alert_type: AlertType, title: str, 
                     description: str, fields: Dict, priority: AlertPriority):
        """Log no console colorido com formatação melhorada"""
        separator = "═" * 80
        
        print(f"\n\033[36m{separator}\033[0m")
        print(f"{priority.value} \033[1;33m{alert_type.display}\033[0m - \033[1;32m{title}\033[0m")
        print(f"\033[90m{'─' * 80}\033[0m")
        
        if description:
            print(f"\033[37m📝 {description}\033[0m")
        
        if fields:
            for key, value in fields.items():
                print(f"   \033[36m📌 {key}:\033[0m \033[37m{value}\033[0m")
        
        print(f"\033[90m{separator}\033[0m\n")
        
        # Log estruturado
        logger.info(f"Alert: {alert_type.name} | {title} | Priority: {priority.name}")
    
    async def _process_queue(self):
        """Processar fila de alertas com batching e rate limiting"""
        self._is_processing = True
        
        while self._is_processing:
            try:
                # Processar em batch
                batch = []
                batch_size = self.config.batch_size
                
                # Coletar alertas do batch
                for _ in range(batch_size):
                    try:
                        alert = await asyncio.wait_for(
                            self._queue.get(), 
                            timeout=self.config.batch_interval
                        )
                        batch.append(alert)
                    except asyncio.TimeoutError:
                        break
                
                if batch:
                    await self._send_batch(batch)
                
                await asyncio.sleep(self.config.batch_interval)
                
            except Exception as e:
                logger.error(f"Erro no processamento da fila: {e}")
                await asyncio.sleep(5)
    
    async def _send_batch(self, batch: List[Dict]):
        """Enviar batch de alertas"""
        # Ordenar por prioridade
        batch.sort(key=lambda x: x["priority"])
        
        for alert in batch:
            await self._rate_limiter.acquire()
            await self._send_webhook(alert["payload"])
            
            # Pequena pausa entre envios
            await asyncio.sleep(0.5)
    
    async def _send_webhook(self, payload: Dict, is_test: bool = False):
        """Envia webhook com retry e fallback"""
        url = self.test_webhook_url if is_test else self.webhook_url
        
        if not url:
            logger.debug("Webhook URL não configurada")
            return
        
        session = await self._get_session()
        
        for attempt in range(self.config.retry_attempts):
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 204:
                        logger.debug("✅ Alerta interno enviado")
                        return
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limitado, aguardando {retry_after}s")
                        await asyncio.sleep(retry_after)
                    else:
                        error_text = await resp.text()
                        logger.warning(f"⚠️ Discord respondeu {resp.status}: {error_text}")
                        
            except aiohttp.ClientError as e:
                logger.error(f"❌ Erro de conexão: {e}")
            except Exception as e:
                logger.error(f"❌ Erro no webhook: {e}")
                logger.debug(traceback.format_exc())
            
            if attempt < self.config.retry_attempts - 1:
                wait_time = self.config.retry_delay * (2 ** attempt)
                logger.info(f"Tentativa {attempt + 1} falhou, retentando em {wait_time}s")
                await asyncio.sleep(wait_time)
        
        logger.error(f"❌ Falha ao enviar alerta após {self.config.retry_attempts} tentativas")
    
    async def send_test_alert(self) -> bool:
        """Enviar alerta de teste"""
        if not self.test_webhook_url:
            logger.warning("Webhook de teste não configurado")
            return False
        
        test_payload = {
            "embeds": [{
                "title": "🧪 Alerta de Teste",
                "description": "Este é um alerta de teste do sistema AutoAnalytics",
                "color": 0x00ff00,
                "timestamp": datetime.utcnow().isoformat()
            }],
            "username": "AutoAnalytics Test"
        }
        
        await self._send_webhook(test_payload, is_test=True)
        return True
    
    async def close(self):
        """Fechar conexões e limpar recursos"""
        self._is_processing = False
        
        # Aguardar fila ser processada
        await asyncio.sleep(2)
        
        if self._session:
            await self._session.close()
        
        # Cancelar tarefas em background
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        if self._redis and self._redis is not None:
            await self._redis.close()


# ==============================================
# DECORATOR PARA MONITORAMENTO
# ==============================================

def monitor_errors(alert_func: Callable = None, include_traceback: bool = True):
    """Decorator para monitorar erros em funções críticas"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e)
                if include_traceback:
                    error_msg += f"\n```python\n{traceback.format_exc()[:1500]}\n```"
                
                await alert_system_error_critical(
                    error=error_msg,
                    endpoint=func.__name__,
                    user=kwargs.get('user_email', 'Sistema')
                )
                raise
        return wrapper
    return decorator if alert_func is None else decorator(alert_func)


# ==============================================
# ALERTAS ESPECÍFICOS PARA O TIME
# ==============================================

discord = DiscordInternal()


async def alert_new_client(user_name: str, user_email: str, workshop: str, 
                          is_premium: bool = False, source: str = "web"):
    """🎉 Novo cliente se cadastrou"""
    await discord.send_alert(
        AlertType.CLIENTE_NOVO if not is_premium else AlertType.CLIENTE_PREMIUM,
        f"{'PREMIUM' if is_premium else 'GRÁTIS'} - {workshop}",
        description=f"🎊 {user_name} acabou de se cadastrar!",
        fields={
            "👤 Nome": user_name,
            "📧 Email": user_email,
            "🔧 Oficina": workshop,
            "💎 Tipo": "PREMIUM 🏆" if is_premium else "GRÁTIS",
            "📱 Origem": source,
            "⏰ Horário": datetime.now().strftime("%H:%M:%S")
        },
        dedup_key=f"new_client:{user_email}"
    )


async def alert_payment_received(user_name: str, amount: float, plan: str, 
                                 payment_method: str, payment_id: str = None):
    """💰 Pagamento recebido - comemoração do time"""
    commission = amount * 0.7  # 70% líquido
    
    await discord.send_alert(
        AlertType.PAGAMENTO,
        f"R$ {amount:.2f} - {plan}",
        description=f"💵 Pagamento recebido de {user_name}",
        fields={
            "👤 Cliente": user_name,
            "💰 Valor": f"R$ {amount:.2f}",
            "📋 Plano": plan,
            "💳 Método": payment_method,
            "💸 Comissão estimada": f"R$ {commission:.2f}",
            "🔖 ID": payment_id or "N/A"
        },
        priority=AlertPriority.HIGH,
        dedup_key=f"payment:{payment_id}" if payment_id else None
    )


async def alert_system_error_critical(error: str, endpoint: str, user: str = None):
    """🔥 Erro crítico - precisa de atenção imediata"""
    await discord.send_alert(
        AlertType.ERRO_SISTEMA,
        "ERRO CRÍTICO NO SISTEMA",
        description=error[:1900] if len(error) > 1900 else error,
        fields={
            "🔗 Endpoint": endpoint,
            "👤 Usuário": user or "Sistema",
            "⏰ Horário": datetime.now().strftime("%H:%M:%S"),
            "🔄 Status": "⚠️ Investigação necessária"
        },
        mention_everyone=True,  # Acorda todo mundo!
        priority=AlertPriority.CRITICAL
    )


async def alert_performance_issue(metric: str, value: float, threshold: float, 
                                   endpoint: str, duration: float):
    """⚡ Alerta de performance"""
    await discord.send_alert(
        AlertType.PERFORMANCE,
        f"Performance Degradada - {metric}",
        description=f"Métrica {metric} excedeu o limite",
        fields={
            "📊 Métrica": metric,
            "📈 Valor atual": f"{value:.2f}",
            "⚠️ Limite": f"{threshold:.2f}",
            "🔗 Endpoint": endpoint,
            "⏱️ Duração": f"{duration:.2f}s"
        },
        priority=AlertPriority.HIGH
    )


async def alert_deploy_started(version: str, deployed_by: str, environment: str = "production"):
    """🚀 Deploy iniciado"""
    await discord.send_alert(
        AlertType.DEPLOY,
        "Deploy Iniciado",
        description=f"Versão {version} sendo implantada em {environment}",
        fields={
            "📦 Versão": version,
            "👨‍💻 Responsável": deployed_by,
            "🌍 Ambiente": environment,
            "🟡 Status": "Em andamento..."
        },
        priority=AlertPriority.HIGH
    )


async def alert_deploy_completed(version: str, duration: float, 
                                 success: bool = True, errors: List[str] = None):
    """✅ Deploy concluído"""
    status = "✅ Concluído com sucesso!" if success else "❌ Falha no deploy"
    
    fields = {
        "📦 Versão": version,
        "⏱️ Duração": f"{duration:.2f} segundos",
        "🟢 Status": status
    }
    
    if errors:
        fields["❌ Erros"] = "\n".join(errors[:3])
    
    await discord.send_alert(
        AlertType.DEPLOY,
        "Deploy Finalizado",
        description=f"Deploy da versão {version} finalizado",
        fields=fields,
        priority=AlertPriority.HIGH if success else AlertPriority.CRITICAL
    )


async def alert_daily_metrics(metrics: Dict):
    """📊 Relatório diário para o time"""
    # Calcular tendências
    growth_rate = metrics.get('growth_rate', 0)
    growth_emoji = "📈" if growth_rate > 0 else "📉"
    
    await discord.send_alert(
        AlertType.METRICA,
        "Relatório Diário",
        description=f"{growth_emoji} Métricas das últimas 24h",
        fields={
            "👥 Novos usuários": metrics.get('new_users', 0),
            "💰 Receita": f"R$ {metrics.get('revenue', 0):.2f}",
            "📁 Análises": metrics.get('analyses_count', 0),
            "💎 Premium ativos": metrics.get('active_premium', 0),
            "⭐ Satisfação": f"{metrics.get('satisfaction', 0)}/5",
            "📊 Taxa de crescimento": f"{growth_rate:+.1f}%"
        },
        priority=AlertPriority.MEDIUM
    )


async def alert_suspicious_activity(user_email: str, action: str, ip: str, 
                                    details: str, severity: str = "medium"):
    """🔒 Atividade suspeita - segurança"""
    severity_color = {
        "low": "🟡 Baixa",
        "medium": "🟠 Média",
        "high": "🔴 Alta",
        "critical": "🔥 Crítica"
    }
    
    await discord.send_alert(
        AlertType.SEGURANCA,
        "Atividade Suspeita Detectada",
        description=f"⚠️ Usuário {user_email} realizou ação suspeita",
        fields={
            "👤 Usuário": user_email,
            "🎯 Ação": action,
            "🌐 IP": ip,
            "⚠️ Severidade": severity_color.get(severity, severity),
            "📝 Detalhes": details[:500],
            "🔍 Recomendação": "Verificar logs imediatamente" if severity in ["high", "critical"] else "Monitorar atividade"
        },
        mention_roles=["@SecurityTeam"] if severity in ["high", "critical"] else None,
        priority=AlertPriority.CRITICAL if severity == "critical" else AlertPriority.HIGH
    )


async def alert_analysis_completed(user_email: str, filename: str, 
                                   rows: int, duration: float):
    """📁 Análise concluída (métrica de uso)"""
    await discord.send_alert(
        AlertType.ANALISE,
        "Nova Análise Concluída",
        fields={
            "👤 Usuário": user_email,
            "📄 Arquivo": filename,
            "📊 Registros": f"{rows:,}",
            "⏱️ Tempo": f"{duration:.2f}s",
            "⏰ Horário": datetime.now().strftime("%H:%M")
        },
        priority=AlertPriority.LOW,
        dedup_key=f"analysis:{user_email}:{filename}"
    )


async def alert_backup_status(success: bool, backup_size: float, 
                              duration: float, error: str = None):
    """💾 Alerta de backup"""
    status = "✅ Sucesso" if success else "❌ Falha"
    
    fields = {
        "💾 Status": status,
        "📦 Tamanho": f"{backup_size:.2f} MB",
        "⏱️ Duração": f"{duration:.2f}s"
    }
    
    if error:
        fields["❌ Erro"] = error[:500]
    
    await discord.send_alert(
        AlertType.BACKUP,
        "Backup do Banco de Dados",
        description=f"Backup finalizado com {status.lower()}",
        fields=fields,
        priority=AlertPriority.CRITICAL if not success else AlertPriority.MEDIUM,
        mention_roles=["@Admins"] if not success else None
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
        
        try:
            # Gerar relatório
            from backend.database import SessionLocal
            from backend import crud
            
            db = SessionLocal()
            try:
                new_users = crud.get_new_users_count(db, days=1)
                prev_users = crud.get_new_users_count(db, days=2) - new_users
                growth_rate = ((new_users - prev_users) / prev_users * 100) if prev_users > 0 else 0
                
                metrics = {
                    'new_users': new_users,
                    'revenue': crud.get_daily_revenue(db),
                    'analyses_count': crud.get_daily_analyses_count(db),
                    'active_premium': crud.get_active_premium_count(db),
                    'satisfaction': crud.get_average_satisfaction(db),
                    'growth_rate': growth_rate
                }
                await alert_daily_metrics(metrics)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Erro ao gerar relatório diário: {e}")
            await alert_system_error_critical(
                error=f"Falha ao gerar relatório diário: {str(e)}",
                endpoint="schedule_daily_report"
            )


# ==============================================
# HEALTH CHECK E MONITORAMENTO
# ==============================================

async def health_check() -> Dict[str, Any]:
    """Verificar saúde do sistema de alertas"""
    status = {
        "webhook_configured": bool(discord.webhook_url),
        "queue_size": discord._queue.qsize(),
        "is_processing": discord._is_processing,
        "redis_available": discord._redis is not None,
        "session_active": discord._session is not None and not discord._session.closed
    }
    
    # Testar webhook se configurado
    if status["webhook_configured"]:
        try:
            await discord.send_test_alert()
            status["test_result"] = "success"
        except Exception as e:
            status["test_result"] = f"failed: {str(e)}"
    
    return status


# ==============================================
# EXPORTAÇÕES
# ==============================================

__all__ = [
    'discord',
    'AlertType',
    'AlertPriority',
    'AlertConfig',
    'monitor_errors',
    'alert_new_client',
    'alert_payment_received',
    'alert_system_error_critical',
    'alert_performance_issue',
    'alert_deploy_started',
    'alert_deploy_completed',
    'alert_daily_metrics',
    'alert_suspicious_activity',
    'alert_analysis_completed',
    'alert_backup_status',
    'schedule_daily_report',
    'health_check']