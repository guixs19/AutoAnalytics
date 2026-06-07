# backend/observability/sentinel.py
"""
SENTINEL - Sistema de Observabilidade e Alertas (v2.0)
--------------------------------------------------------
Monitoramento, logs estruturados, alertas e métricas para o AutoAnalytics
"""

import aiohttp
import asyncio
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps
import traceback
import time

# FastAPI
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ==============================================
# ENUMS E CONSTANTES
# ==============================================

class AlertLevel(Enum):
    """Níveis de alerta com emojis e cores"""
    DEBUG = ("🐛", 0x6c757d)      # Cinza
    INFO = ("ℹ️", 0x0d6efd)        # Azul
    SUCCESS = ("✅", 0x198754)     # Verde
    WARNING = ("⚠️", 0xffc107)     # Amarelo
    ERROR = ("🔥", 0xdc3545)       # Vermelho
    CRITICAL = ("🚨", 0x8b0000)    # Vermelho escuro
    SUSPICIOUS = ("👮‍♂️", 0xfd7e14)  # Laranja
    PAYMENT = ("💰", 0x6f42c1)     # Roxo
    PREMIUM = ("💎", 0xd63384)     # Rosa
    SECURITY = ("🔒", 0x20c997)    # Verde-água
    DATABASE = ("🗄️", 0x0dcaf0)    # Ciano
    CACHE = ("⚡", 0xffc107)        # Amarelo
    
    def __init__(self, emoji: str, color: int):
        self.emoji = emoji
        self.color = color


class MetricType(Enum):
    """Tipos de métricas"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """Estrutura de métrica"""
    name: str
    type: MetricType
    value: float = 0
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat()
        }


# ==============================================
# DISCORD WEBHOOK ASSÍNCRONO
# ==============================================

class DiscordWebhook:
    """
    Envia alertas para o Discord via Webhook (assíncrono com retry)
    """
    
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK", "") or os.getenv("WEBHOOK_URL", "")
        self.app_name = "AutoAnalytics"
        self.version = "3.2.0"
        self.environment = os.getenv("ENVIRONMENT", "development")
        self._session: Optional[aiohttp.ClientSession] = None
        self._queue: List[Dict[str, Any]] = []
        self._is_processing = False
        self._metrics: Dict[str, int] = defaultdict(int)
        
        # Filtros para evitar spam
        self._last_alert_time: Dict[str, float] = {}
        self._alert_cooldown = 60  # segundos
        
        if not self.webhook_url:
            logger.warning("⚠️ DISCORD_WEBHOOK não configurado no .env")
            logger.info("   Os alertas serão mostrados apenas no console e logs")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna sessão HTTP compartilhada"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Content-Type": "application/json"}
            )
        return self._session
    
    async def close(self):
        """Fecha a sessão HTTP"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def _should_send_alert(self, alert_key: str) -> bool:
        """Verifica se o alerta pode ser enviado (evita spam)"""
        now = time.time()
        last_time = self._last_alert_time.get(alert_key, 0)
        
        if now - last_time < self._alert_cooldown:
            return False
        
        self._last_alert_time[alert_key] = now
        return True
    
    async def send_alert(self, level: AlertLevel, title: str, **details):
        """
        Envia alerta para o Discord (assíncrono com retry)
        """
        alert_key = f"{level.name}:{title[:50]}"
        
        # Mostrar no console sempre (formatação melhorada)
        self._log_to_console(level, title, details)
        
        # Incrementar métrica
        self._metrics[f"alerts.{level.name.lower()}"] += 1
        
        # Verificar cooldown para Discord
        if not self._should_send_alert(alert_key):
            logger.debug(f"🔄 Alerta {alert_key} ignorado (cooldown)")
            return
        
        # Se não tem webhook, apenas log
        if not self.webhook_url:
            return
        
        # Criar embed bonito
        embed = self._create_embed(level, title, details)
        
        payload = {
            "embeds": [embed],
            "username": f"{self.app_name} Bot",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"
        }
        
        # Adicionar ao queue e processar
        self._queue.append(payload)
        asyncio.create_task(self._process_queue())
    
    def _log_to_console(self, level: AlertLevel, title: str, details: Dict[str, Any]):
        """Log formatado no console"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*60}")
        print(f"📢 [{timestamp}] {level.emoji} {level.name} - {title}")
        print(f"{'─'*60}")
        
        for key, value in details.items():
            if value is not None:
                # Formatar valor
                if isinstance(value, float):
                    if any(word in key.lower() for word in ["price", "valor", "amount", "preço"]):
                        formatted = f"R$ {value:,.2f}"
                    else:
                        formatted = f"{value:.4f}"
                elif isinstance(value, datetime):
                    formatted = value.strftime("%d/%m/%Y %H:%M:%S")
                elif isinstance(value, dict):
                    formatted = json.dumps(value, ensure_ascii=False)[:100]
                else:
                    formatted = str(value)
                
                # Formatar nome da chave
                key_name = key.replace("_", " ").title()
                print(f"   📌 {key_name}: {formatted}")
        
        print(f"{'='*60}\n")
    
    def _create_embed(self, level: AlertLevel, title: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Cria embed para Discord"""
        embed = {
            "title": f"{level.emoji} {title}",
            "color": level.color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": f"{self.app_name} v{self.version} • {self.environment} • {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            },
            "fields": []
        }
        
        # Adicionar detalhes como campos
        for key, value in details.items():
            if value is not None:
                field_name = key.replace("_", " ").title()
                
                # Formatar valor
                if isinstance(value, float):
                    if any(word in key.lower() for word in ["price", "valor", "amount", "preço"]):
                        field_value = f"R$ {value:,.2f}"
                    else:
                        field_value = f"{value:.4f}"
                elif isinstance(value, datetime):
                    field_value = value.strftime("%d/%m/%Y %H:%M:%S")
                elif isinstance(value, dict):
                    field_value = json.dumps(value, ensure_ascii=False)[:500]
                else:
                    field_value = str(value)[:1024]  # Limite do Discord
                
                embed["fields"].append({
                    "name": field_name,
                    "value": field_value,
                    "inline": len(str(field_value)) < 50  # Inline se for curto
                })
        
        # Adicionar ambiente em produção
        if self.environment == "production":
            embed["fields"].append({
                "name": "🏭 Ambiente",
                "value": "PRODUÇÃO",
                "inline": True
            })
        
        return embed
    
    async def _process_queue(self):
        """Processa fila de alertas com retry"""
        if self._is_processing:
            return
        
        self._is_processing = True
        
        try:
            while self._queue:
                payload = self._queue.pop(0)
                await self._send_with_retry(payload)
                await asyncio.sleep(1)  # Rate limit do Discord
        
        finally:
            self._is_processing = False
    
    async def _send_with_retry(self, payload: Dict[str, Any], max_retries: int = 3):
        """Envia com retry automático"""
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 204:
                        logger.debug("✅ Alerta enviado para o Discord")
                        return
                    elif response.status == 429:
                        # Rate limit, esperar
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"⏳ Rate limit Discord, aguardando {retry_after}s")
                        await asyncio.sleep(retry_after)
                    else:
                        logger.warning(f"⚠️ Discord respondeu com status {response.status}")
                        
            except aiohttp.ClientError as e:
                logger.error(f"❌ Erro ao enviar para Discord (tentativa {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Backoff exponencial
        
        logger.error("❌ Falha ao enviar alerta após múltiplas tentativas")
    
    def get_metrics(self) -> Dict[str, int]:
        """Retorna métricas de alertas"""
        return dict(self._metrics)


# ==============================================
# METRICS COLLECTOR
# ==============================================

class MetricsCollector:
    """
    Coletor de métricas para monitoramento
    """
    
    def __init__(self):
        self._metrics: Dict[str, Metric] = {}
        self._timers: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._max_histogram_samples = 1000
    
    def counter_inc(self, name: str, value: float = 1, labels: Dict[str, str] = None):
        """Incrementa contador"""
        key = self._get_key(name, labels)
        
        if key not in self._metrics:
            self._metrics[key] = Metric(name, MetricType.COUNTER, 0, labels or {})
        
        self._metrics[key].value += value
    
    def gauge_set(self, name: str, value: float, labels: Dict[str, str] = None):
        """Define valor de gauge"""
        key = self._get_key(name, labels)
        
        if key not in self._metrics:
            self._metrics[key] = Metric(name, MetricType.GAUGE, value, labels or {})
        else:
            self._metrics[key].value = value
    
    def timer_start(self, name: str) -> str:
        """Inicia timer (retorna ID para parar)"""
        timer_id = f"{name}_{time.time()}_{id(name)}"
        self._timers[timer_id] = time.time()
        return timer_id
    
    def timer_stop(self, timer_id: str, labels: Dict[str, str] = None):
        """Para timer e registra duração"""
        if timer_id not in self._timers:
            return
        
        duration = (time.time() - self._timers[timer_id]) * 1000  # ms
        del self._timers[timer_id]
        
        # Extrair nome do timer
        name = timer_id.split("_")[0]
        self.histogram_observe(f"{name}_duration_ms", duration, labels)
    
    def histogram_observe(self, name: str, value: float, labels: Dict[str, str] = None):
        """Adiciona observação ao histograma"""
        self._histograms[f"{name}_{self._get_key('', labels)}"].append(value)
        
        # Limitar tamanho
        if len(self._histograms[name]) > self._max_histogram_samples:
            self._histograms[name] = self._histograms[name][-self._max_histogram_samples:]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Retorna todas as métricas"""
        result = {}
        
        # Métricas básicas
        for key, metric in self._metrics.items():
            result[metric.name] = metric.value
        
        # Estatísticas de histogramas
        for name, values in self._histograms.items():
            if values:
                result[f"{name}_count"] = len(values)
                result[f"{name}_sum"] = sum(values)
                result[f"{name}_avg"] = sum(values) / len(values)
                result[f"{name}_max"] = max(values)
                result[f"{name}_min"] = min(values)
        
        return result
    
    def _get_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Gera chave única para métrica"""
        if not labels:
            return name
        
        label_str = "_".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}_{label_str}"


# ==============================================
# LOGGING MIDDLEWARE
# ==============================================

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para logging de requisições e métricas
    """
    
    def __init__(self, app, metrics: MetricsCollector = None):
        super().__init__(app)
        self.metrics = metrics or MetricsCollector()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # Log da requisição
        logger.info(f"🌐 {request.method} {request.url.path}")
        
        # Processar requisição
        try:
            response = await call_next(request)
            
            # Registrar métricas
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.counter_inc(f"http_requests_total", labels={"method": request.method, "status": str(response.status_code)})
            self.metrics.histogram_observe(f"http_request_duration_ms", duration_ms, labels={"method": request.method})
            
            # Log de status
            if response.status_code >= 400:
                logger.warning(f"   ⚠️ Status: {response.status_code} | Duration: {duration_ms:.2f}ms")
            else:
                logger.debug(f"   ✅ Status: {response.status_code} | Duration: {duration_ms:.2f}ms")
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ Erro: {e} | Duration: {duration_ms:.2f}ms")
            
            # Enviar alerta
            webhook = get_webhook()
            await webhook.send_alert(
                AlertLevel.ERROR,
                "Erro na requisição",
                endpoint=request.url.path,
                method=request.method,
                error=str(e),
                duration_ms=f"{duration_ms:.2f}"
            )
            raise


# ==============================================
# DECORATOR PARA MONITORAMENTO
# ==============================================

def monitor(metric_name: str = None):
    """
    Decorator para monitorar funções automaticamente
    
    Uso:
        @monitor("payment_process")
        async def process_payment(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            metrics = get_metrics_collector()
            name = metric_name or func.__name__
            
            metrics.counter_inc(f"{name}_calls_total")
            timer_id = metrics.timer_start(name)
            
            try:
                result = await func(*args, **kwargs)
                metrics.counter_inc(f"{name}_success_total")
                return result
            except Exception as e:
                metrics.counter_inc(f"{name}_errors_total")
                raise
            finally:
                metrics.timer_stop(timer_id)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            metrics = get_metrics_collector()
            name = metric_name or func.__name__
            
            metrics.counter_inc(f"{name}_calls_total")
            start = time.time()
            
            try:
                result = func(*args, **kwargs)
                metrics.counter_inc(f"{name}_success_total")
                return result
            except Exception as e:
                metrics.counter_inc(f"{name}_errors_total")
                raise
            finally:
                duration = (time.time() - start) * 1000
                metrics.histogram_observe(f"{name}_duration_ms", duration)
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# ==============================================
# FUNÇÕES ESPECÍFICAS DE ALERTA
# ==============================================

# Pagamentos
@monitor("payment_approved")
async def alert_payment_approved(user_email: str, amount: float, credits: int, plan: str, payment_id: str = None):
    """💰 Pagamento aprovado"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.PAYMENT,
        "💰 NOVO PAGAMENTO APROVADO",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        creditos=credits,
        plano=plan,
        payment_id=payment_id,
        status="✅ Aprovado"
    )


async def alert_payment_pending(user_email: str, amount: float, method: str, payment_id: str = None):
    """⏳ Pagamento pendente"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.INFO,
        "⏳ PAGAMENTO PENDENTE",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        metodo=method,
        payment_id=payment_id,
        status="Aguardando pagamento"
    )


async def alert_payment_failed(user_email: str, amount: float, error: str, payment_id: str = None):
    """❌ Falha no pagamento"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.ERROR,
        "❌ FALHA NO PAGAMENTO",
        usuario=user_email,
        valor=f"R$ {amount:.2f}",
        erro=error,
        payment_id=payment_id,
        status="Rejeitado"
    )


# Plano Premium
async def alert_premium_activated(user_email: str, credits: int, expires_at: str, plan: str = "Premium Mensal"):
    """💎 Novo assinante premium"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.PREMIUM,
        "💎 NOVO ASSINANTE PREMIUM",
        usuario=user_email,
        creditos_iniciais=credits,
        expira_em=expires_at,
        plano=plan,
        mensagem="🎉 1 crédito por dia durante 30 dias!"
    )


async def alert_daily_credits_distributed(user_email: str, day: int, credits: int, total: int):
    """📅 Crédito diário distribuído"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.SUCCESS,
        "📅 CRÉDITO DIÁRIO ADICIONADO",
        usuario=user_email,
        dia=f"{day}/30",
        creditos_hoje=credits,
        saldo_atual=total,
        mensagem="+1 crédito disponível! 🎯"
    )


async def alert_premium_expiring_soon(user_email: str, days_left: int, expires_at: str = None):
    """⏰ Plano premium perto de expirar"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.WARNING,
        "⏰ PLANO PREMIUM PERTO DE EXPIRAR",
        usuario=user_email,
        dias_restantes=days_left,
        expira_em=expires_at,
        acao="Renovar para continuar recebendo créditos diários"
    )


# Sistema
async def alert_system_error(error: Exception, endpoint: str = None, user: str = None, context: Dict = None):
    """🔥 Erro no sistema"""
    webhook = get_webhook()
    error_trace = traceback.format_exc()
    
    await webhook.send_alert(
        AlertLevel.ERROR,
        "🔥 ERRO NO SISTEMA",
        endpoint=endpoint or "Desconhecido",
        usuario=user or "Sistema",
        erro=type(error).__name__,
        mensagem=str(error)[:200],
        trace=error_trace[:500] if error_trace else None,
        contexto=json.dumps(context, ensure_ascii=False)[:200] if context else None
    )


async def alert_system_startup():
    """🚀 Sistema iniciado"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.SUCCESS,
        "🚀 SISTEMA INICIADO",
        versao="3.2.0",
        ambiente=os.getenv("ENVIRONMENT", "development"),
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        status="✅ Online"
    )


async def alert_new_user(user_email: str, name: str, user_id: int = None):
    """👤 Novo usuário registrado"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.INFO,
        "👤 NOVO USUÁRIO REGISTRADO",
        email=user_email,
        nome=name,
        user_id=user_id,
        data=datetime.now().strftime("%d/%m/%Y %H:%M")
    )


# Segurança
async def alert_suspicious_activity(user_email: str, action: str, details: str = None, ip: str = None):
    """👮‍♂️ Atividade suspeita detectada"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.SUSPICIOUS,
        "👮‍♂️ ATIVIDADE SUSPEITA",
        usuario=user_email,
        acao=action,
        ip=ip,
        detalhes=details,
        alerta="🔍 Investigação necessária"
    )


async def alert_failed_login(email: str, ip: str, attempts: int = None):
    """🔐 Múltiplas tentativas de login falhas"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.WARNING,
        "🔐 TENTATIVAS DE LOGIN FALHAS",
        email=email,
        ip=ip,
        tentativas=attempts,
        alerta="Possível ataque de força bruta"
    )


# Cache e Database
async def alert_redis_connection_issue(error: str, retry_count: int = 0):
    """⚡ Problema de conexão com Redis"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.WARNING,
        "⚡ PROBLEMA NO REDIS",
        erro=error,
        tentativas=retry_count,
        impacto="Blacklist e rate limiting afetados",
        acao="Verificar container do Redis"
    )


async def alert_database_connection_issue(error: str):
    """🗄️ Problema de conexão com banco de dados"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.CRITICAL,
        "🗄️ PROBLEMA NO BANCO DE DADOS",
        erro=error,
        impacto="Sistema pode ficar indisponível",
        acao="⚠️ AÇÃO IMEDIATA NECESSÁRIA"
    )


# ML / Gemini
async def alert_gemini_api_error(error: str, endpoint: str = None, user_email: str = None):
    """🤖 Erro na API do Gemini"""
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.ERROR,
        "🤖 ERRO NA API GEMINI",
        erro=error,
        endpoint=endpoint,
        usuario=user_email,
        acao="Verificar chave API e quota"
    )


# ==============================================
# INSTÂNCIAS GLOBAIS
# ==============================================

_webhook_instance: Optional[DiscordWebhook] = None
_metrics_collector: Optional[MetricsCollector] = None
_monitor_task: Optional[asyncio.Task] = None


def get_webhook() -> DiscordWebhook:
    """Retorna instância única do webhook"""
    global _webhook_instance
    if _webhook_instance is None:
        _webhook_instance = DiscordWebhook()
    return _webhook_instance


def get_metrics_collector() -> MetricsCollector:
    """Retorna instância única do coletor de métricas"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


async def start_metrics_reporting(interval: int = 60):
    """Inicia relatório periódico de métricas"""
    global _monitor_task
    
    if _monitor_task:
        return
    
    async def report_loop():
        logger.info("📊 Iniciando relatório periódico de métricas...")
        webhook = get_webhook()
        metrics = get_metrics_collector()
        
        while True:
            await asyncio.sleep(interval)
            
            # Coletar métricas
            all_metrics = metrics.get_metrics()
            
            # Enviar alerta de saúde se houver problemas
            error_count = all_metrics.get("http_requests_total", {}).get("status=5xx", 0)
            if error_count > 10:
                await webhook.send_alert(
                    AlertLevel.WARNING,
                    "⚠️ ALTO NÍVEL DE ERROS",
                    erros_5xx=error_count,
                    periodo=f"{interval}s",
                    metricas=str(all_metrics)[:200]
                )
            
            logger.debug(f"📊 Métricas: {all_metrics}")
    
    _monitor_task = asyncio.create_task(report_loop())
    logger.info("✅ Relatório periódico de métricas iniciado")


async def stop_metrics_reporting():
    """Para relatório periódico de métricas"""
    global _monitor_task
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None
        logger.info("🛑 Relatório de métricas parado")


# ==============================================
# COMPATIBILIDADE (versões síncronas para código legado)
# ==============================================

# Versões síncronas (para código que não usa async)
def alert_payment_approved_sync(user_email: str, amount: float, credits: int, plan: str):
    """Versão síncrona para compatibilidade"""
    webhook = get_webhook()
    asyncio.create_task(alert_payment_approved(user_email, amount, credits, plan))


def alert_system_startup_sync():
    """Versão síncrona para compatibilidade"""
    webhook = get_webhook()
    asyncio.create_task(alert_system_startup())


def alert_new_user_sync(user_email: str, name: str):
    """Versão síncrona para compatibilidade"""
    webhook = get_webhook()
    asyncio.create_task(alert_new_user(user_email, name))


# ==============================================
# EXPORTAÇÕES
# ==============================================

__all__ = [
    # Classes principais
    'AlertLevel',
    'DiscordWebhook',
    'MetricsCollector',
    'LoggingMiddleware',
    
    # Instâncias
    'get_webhook',
    'get_metrics_collector',
    
    # Decorators
    'monitor',
    
    # Alertas de Pagamento
    'alert_payment_approved',
    'alert_payment_pending',
    'alert_payment_failed',
    'alert_suspicious_activity',
    
    # Alertas de Premium
    'alert_premium_activated',
    'alert_daily_credits_distributed',
    'alert_premium_expiring_soon',
    
    # Alertas de Sistema
    'alert_system_error',
    'alert_system_startup',
    'alert_new_user',
    
    # Alertas de Segurança
    'alert_failed_login',
    'alert_redis_connection_issue',
    'alert_database_connection_issue',
    
    # Alertas de ML
    'alert_gemini_api_error',
    
    # Versões síncronas (compatibilidade)
    'alert_payment_approved_sync',
    'alert_system_startup_sync',
    'alert_new_user_sync',
    
    # Utilitários
    'start_metrics_reporting',
    'stop_metrics_reporting',
]

print("✅ sentinel.py v2.0 carregado - Sistema de observabilidade atualizado")