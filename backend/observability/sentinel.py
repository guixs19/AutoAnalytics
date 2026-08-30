# backend/observability/sentinel.py
"""
SENTINEL - Sistema de Observabilidade e Alertas (v2.2)
--------------------------------------------------------
Monitoramento, logs estruturados, alertas e métricas para o AutoAnalytics
COM MONITORAMENTO DE MODELO ML INTEGRADO
"""

import aiohttp
import asyncio
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Set
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps
import traceback
import time

# FastAPI
from fastapi import Request, Response, BackgroundTasks
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ==============================================
# ENUMS E CONSTANTES
# ==============================================

class AlertLevel(Enum):
    """Níveis de alerta com emojis e cores"""
    DEBUG = ("🐛", 0x6c757d)
    INFO = ("ℹ️", 0x0d6efd)
    SUCCESS = ("✅", 0x198754)
    WARNING = ("⚠️", 0xffc107)
    ERROR = ("🔥", 0xdc3545)
    CRITICAL = ("🚨", 0x8b0000)
    SUSPICIOUS = ("👮‍♂️", 0xfd7e14)
    PAYMENT = ("💰", 0x6f42c1)
    PREMIUM = ("💎", 0xd63384)
    SECURITY = ("🔒", 0x20c997)
    DATABASE = ("🗄️", 0x0dcaf0)
    CACHE = ("⚡", 0xffc107)
    MODEL = ("🧠", 0x6f42c1)
    
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
# GERENCIADOR DE TAREFAS EM BACKGROUND
# ==============================================

class BackgroundTaskManager:
    """
    Gerencia tarefas assíncronas em background
    Mantém referências para evitar garbage collection
    """
    
    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._shutdown = False
    
    async def create_task(self, coro, name: str = None) -> asyncio.Task:
        """Cria e gerencia uma tarefa em background"""
        if self._shutdown:
            logger.warning("⚠️ Sistema em shutdown, tarefa não será criada")
            return None
        
        task = asyncio.create_task(coro, name=name)
        
        async with self._lock:
            self._tasks.add(task)
        
        task.add_done_callback(self._remove_task)
        
        return task
    
    def _remove_task(self, task: asyncio.Task):
        """Remove tarefa do gerenciador quando concluída"""
        self._tasks.discard(task)
    
    def get_active_tasks(self) -> int:
        """Retorna número de tarefas ativas"""
        return len(self._tasks)
    
    async def cancel_all(self, timeout: float = 5.0):
        """Cancela todas as tarefas em background"""
        self._shutdown = True
        
        async with self._lock:
            tasks = list(self._tasks)
            if not tasks:
                return
            
            logger.info(f"⏳ Cancelando {len(tasks)} tarefas em background...")
            
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout
                )
                logger.info("✅ Tarefas canceladas com sucesso")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Timeout ({timeout}s) ao cancelar tarefas")
            finally:
                self._tasks.clear()


# Instância global do gerenciador
_background_manager = BackgroundTaskManager()


def get_background_manager() -> BackgroundTaskManager:
    """Retorna instância do gerenciador de tarefas"""
    return _background_manager


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
        self._shutdown = False
        
        # Filtros para evitar spam
        self._last_alert_time: Dict[str, float] = {}
        self._alert_cooldown = 60
        
        # Referências para tarefas em background
        self._background_tasks: Set[asyncio.Task] = set()
        
        if not self.webhook_url:
            logger.warning("⚠️ DISCORD_WEBHOOK não configurado no .env")
            logger.info("   Os alertas serão mostrados apenas no console e logs")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna sessão HTTP compartilhada"""
        if self._shutdown:
            raise RuntimeError("Webhook em shutdown")
        
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Content-Type": "application/json"}
            )
        return self._session
    
    async def close(self):
        """Fecha a sessão HTTP e cancela tasks pendentes"""
        self._shutdown = True
        
        logger.info("🔄 Fechando DiscordWebhook...")
        
        if self._session and not self._session.closed:
            try:
                await self._session.close()
                logger.debug("✅ Sessão HTTP fechada")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao fechar sessão HTTP: {e}")
            finally:
                self._session = None
        
        if self._background_tasks:
            logger.info(f"⏳ Cancelando {len(self._background_tasks)} tarefas pendentes...")
            
            for task in list(self._background_tasks):
                if not task.done():
                    task.cancel()
            
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=5.0
                )
                logger.debug("✅ Tarefas canceladas com sucesso")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Timeout ao cancelar tarefas, prosseguindo...")
            finally:
                self._background_tasks.clear()
        
        if self._queue:
            queue_size = len(self._queue)
            self._queue.clear()
            logger.info(f"🧹 Fila limpa: {queue_size} alertas descartados")
        
        logger.info("✅ DiscordWebhook finalizado com sucesso")
    
    def _should_send_alert(self, alert_key: str) -> bool:
        """Verifica se o alerta pode ser enviado (evita spam)"""
        now = time.time()
        last_time = self._last_alert_time.get(alert_key, 0)
        
        if now - last_time < self._alert_cooldown:
            return False
        
        self._last_alert_time[alert_key] = now
        return True
    
    async def send_alert(self, level: AlertLevel, title: str, **details):
        """Envia alerta para o Discord (assíncrono com retry)"""
        if self._shutdown:
            logger.warning("⚠️ Webhook em shutdown, alerta ignorado")
            return
        
        alert_key = f"{level.name}:{title[:50]}"
        
        self._log_to_console(level, title, details)
        self._metrics[f"alerts.{level.name.lower()}"] += 1
        
        if not self._should_send_alert(alert_key):
            logger.debug(f"🔄 Alerta {alert_key} ignorado (cooldown)")
            return
        
        if not self.webhook_url:
            return
        
        embed = self._create_embed(level, title, details)
        payload = {
            "embeds": [embed],
            "username": f"{self.app_name} Bot",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"
        }
        
        self._queue.append(payload)
        
        task = asyncio.create_task(self._process_queue())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
    
    def send_alert_sync(self, level: AlertLevel, title: str, **details):
        """Versão SÍNCRONA para compatibilidade"""
        if self._shutdown:
            logger.warning("⚠️ Webhook em shutdown, alerta ignorado")
            return
        
        alert_key = f"{level.name}:{title[:50]}"
        
        self._log_to_console(level, title, details)
        self._metrics[f"alerts.{level.name.lower()}"] += 1
        
        if not self._should_send_alert(alert_key) or not self.webhook_url:
            return
        
        embed = self._create_embed(level, title, details)
        payload = {
            "embeds": [embed],
            "username": f"{self.app_name} Bot",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"
        }
        
        self._queue.append(payload)
        
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._process_queue())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            asyncio.run(self._process_queue())
    
    def _log_to_console(self, level: AlertLevel, title: str, details: Dict[str, Any]):
        """Log formatado no console"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*60}")
        print(f"📢 [{timestamp}] {level.emoji} {level.name} - {title}")
        print(f"{'─'*60}")
        
        for key, value in details.items():
            if value is not None:
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
        
        for key, value in details.items():
            if value is not None:
                field_name = key.replace("_", " ").title()
                
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
                    field_value = str(value)[:1024]
                
                embed["fields"].append({
                    "name": field_name,
                    "value": field_value,
                    "inline": len(str(field_value)) < 50
                })
        
        if self.environment == "production":
            embed["fields"].append({
                "name": "🏭 Ambiente",
                "value": "PRODUÇÃO",
                "inline": True
            })
        
        return embed
    
    async def _process_queue(self):
        """Processa fila de alertas com retry"""
        if self._is_processing or self._shutdown:
            return
        
        self._is_processing = True
        
        try:
            while self._queue and not self._shutdown:
                payload = self._queue.pop(0)
                await self._send_with_retry(payload)
                await asyncio.sleep(1)
        finally:
            self._is_processing = False
    
    async def _send_with_retry(self, payload: Dict[str, Any], max_retries: int = 3):
        """Envia com retry automático"""
        if self._shutdown:
            return
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 204:
                        logger.debug("✅ Alerta enviado para o Discord")
                        return
                    elif response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"⏳ Rate limit Discord, aguardando {retry_after}s")
                        await asyncio.sleep(retry_after)
                    else:
                        logger.warning(f"⚠️ Discord respondeu com status {response.status}")
            except aiohttp.ClientError as e:
                logger.error(f"❌ Erro ao enviar para Discord (tentativa {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"❌ Erro inesperado: {e}")
                break
        
        if not self._shutdown:
            logger.error("❌ Falha ao enviar alerta após múltiplas tentativas")
    
    def get_metrics(self) -> Dict[str, int]:
        """Retorna métricas de alertas"""
        return dict(self._metrics)


# ==============================================
# METRICS COLLECTOR
# ==============================================

class MetricsCollector:
    """Coletor de métricas para monitoramento"""
    
    def __init__(self):
        self._metrics: Dict[str, Metric] = {}
        self._timers: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._max_histogram_samples = 1000
    
    def counter_inc(self, name: str, value: float = 1, labels: Dict[str, str] = None):
        key = self._get_key(name, labels)
        if key not in self._metrics:
            self._metrics[key] = Metric(name, MetricType.COUNTER, 0, labels or {})
        self._metrics[key].value += value
    
    def gauge_set(self, name: str, value: float, labels: Dict[str, str] = None):
        key = self._get_key(name, labels)
        if key not in self._metrics:
            self._metrics[key] = Metric(name, MetricType.GAUGE, value, labels or {})
        else:
            self._metrics[key].value = value
    
    def timer_start(self, name: str) -> str:
        timer_id = f"{name}_{time.time()}_{id(name)}"
        self._timers[timer_id] = time.time()
        return timer_id
    
    def timer_stop(self, timer_id: str, labels: Dict[str, str] = None):
        if timer_id not in self._timers:
            return
        duration = (time.time() - self._timers[timer_id]) * 1000
        del self._timers[timer_id]
        name = timer_id.split("_")[0]
        self.histogram_observe(f"{name}_duration_ms", duration, labels)
    
    def histogram_observe(self, name: str, value: float, labels: Dict[str, str] = None):
        self._histograms[f"{name}_{self._get_key('', labels)}"].append(value)
        if len(self._histograms[name]) > self._max_histogram_samples:
            self._histograms[name] = self._histograms[name][-self._max_histogram_samples:]
    
    def get_metrics(self) -> Dict[str, Any]:
        result = {}
        for key, metric in self._metrics.items():
            result[metric.name] = metric.value
        for name, values in self._histograms.items():
            if values:
                result[f"{name}_count"] = len(values)
                result[f"{name}_sum"] = sum(values)
                result[f"{name}_avg"] = sum(values) / len(values)
                result[f"{name}_max"] = max(values)
                result[f"{name}_min"] = min(values)
        return result
    
    def _get_key(self, name: str, labels: Dict[str, str] = None) -> str:
        if not labels:
            return name
        label_str = "_".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}_{label_str}"


# ==============================================
# LOGGING MIDDLEWARE
# ==============================================

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware para logging de requisições e métricas"""
    
    def __init__(self, app, metrics: MetricsCollector = None):
        super().__init__(app)
        self.metrics = metrics or MetricsCollector()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        logger.info(f"🌐 {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.counter_inc("http_requests_total", labels={"method": request.method, "status": str(response.status_code)})
            self.metrics.histogram_observe("http_request_duration_ms", duration_ms, labels={"method": request.method})
            
            if response.status_code >= 400:
                logger.warning(f"   ⚠️ Status: {response.status_code} | Duration: {duration_ms:.2f}ms")
            else:
                logger.debug(f"   ✅ Status: {response.status_code} | Duration: {duration_ms:.2f}ms")
            
            return response
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ Erro: {e} | Duration: {duration_ms:.2f}ms")
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
    """Decorator para monitorar funções automaticamente"""
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
# 🔥 MONITORAMENTO DO MODELO ML (NOVO)
# ==============================================

# Variável global para controlar o monitor
_model_monitor_task: Optional[asyncio.Task] = None


async def alert_model_status():
    """
    Envia alerta com status atual do modelo ML
    """
    webhook = get_webhook()
    
    try:
        import joblib
        import os
        from backend.database import SessionLocal
        from backend import models
        from datetime import datetime
        
        # 1. Carregar modelo
        model_path = '/app/backend/ml/models/office_model.pkl'
        if not os.path.exists(model_path):
            await webhook.send_alert(
                AlertLevel.ERROR,
                '❌ MODELO ML NÃO ENCONTRADO',
                caminho=model_path,
                acao='Re-treinar o modelo imediatamente!'
            )
            return
        
        data = joblib.load(model_path)
        metrics = data.get('metrics', {})
        
        # 2. Estatísticas do banco
        db = SessionLocal()
        try:
            total_analyses = db.query(models.Analysis).count()
            
            today = datetime.now().date()
            today_analyses = db.query(models.Analysis).filter(
                models.Analysis.uploaded_at >= today
            ).count()
            
            completed = db.query(models.Analysis).filter(
                models.Analysis.status == 'completed'
            ).count()
            failed = db.query(models.Analysis).filter(
                models.Analysis.status == 'failed'
            ).count()
            
        finally:
            db.close()
        
        # 3. Calcular saúde do modelo
        accuracy = metrics.get('test_accuracy', 0)
        samples = metrics.get('n_samples', 0)
        is_placeholder = metrics.get('is_placeholder', True)
        
        if is_placeholder:
            health = '🔴 USANDO PLACEHOLDER'
            health_color = AlertLevel.CRITICAL
        elif accuracy >= 0.90:
            health = '🟢 EXCELENTE'
            health_color = AlertLevel.SUCCESS
        elif accuracy >= 0.80:
            health = '🟡 BOM'
            health_color = AlertLevel.INFO
        elif accuracy >= 0.70:
            health = '🟠 REGULAR'
            health_color = AlertLevel.WARNING
        else:
            health = '🔴 RUIM - RE-TREINAR URGENTE'
            health_color = AlertLevel.ERROR
        
        # 4. Verificar se precisa re-treinar
        needs_retrain = False
        retrain_reason = ''
        
        if is_placeholder:
            needs_retrain = True
            retrain_reason = 'Modelo placeholder em uso'
        elif accuracy < 0.80:
            needs_retrain = True
            retrain_reason = f'Acurácia baixa: {accuracy:.2%}'
        elif samples >= 100:
            needs_retrain = True
            retrain_reason = f'{samples} amostras disponíveis'
        
        # 5. Enviar alerta
        await webhook.send_alert(
            health_color,
            f'🧠 STATUS DO MODELO ML',
            status=health,
            acuracia=f'{accuracy:.2%}',
            amostras=samples,
            features=len(data.get('features', [])),
            tipo=data.get('model_type', 'Unknown'),
            total_analises=total_analyses,
            analises_hoje=today_analyses,
            completadas=completed,
            falhas=failed,
            precisa_retreinar='✅ Sim' if needs_retrain else '❌ Não',
            motivo_retreino=retrain_reason if needs_retrain else 'N/A',
            ultimo_treino=metrics.get('trained_date', 'N/A')
        )
        
    except Exception as e:
        await webhook.send_alert(
            AlertLevel.ERROR,
            '❌ ERRO AO MONITORAR MODELO',
            erro=str(e),
            trace=traceback.format_exc()[:500]
        )


async def monitor_model_periodically(interval_hours: int = 24):
    """
    Monitora o modelo periodicamente e envia alertas
    """
    await alert_model_status()
    
    while True:
        await asyncio.sleep(interval_hours * 3600)
        await alert_model_status()


def start_model_monitoring(interval_hours: int = 24):
    """
    Inicia o monitoramento do modelo em background
    """
    global _model_monitor_task
    
    if _model_monitor_task and not _model_monitor_task.done():
        logger.info('📊 Monitor do modelo já está rodando')
        return
    
    logger.info(f'📊 Iniciando monitor do modelo (a cada {interval_hours}h)')
    _model_monitor_task = asyncio.create_task(monitor_model_periodically(interval_hours))
    logger.info('✅ Monitor do modelo iniciado')


async def stop_model_monitoring():
    """
    Para o monitoramento do modelo
    """
    global _model_monitor_task
    
    if _model_monitor_task:
        _model_monitor_task.cancel()
        try:
            await _model_monitor_task
        except asyncio.CancelledError:
            pass
        _model_monitor_task = None
        logger.info('🛑 Monitor do modelo parado')


# ==============================================
# FUNÇÕES ESPECÍFICAS DE ALERTA
# ==============================================

@monitor("payment_approved")
async def alert_payment_approved(user_email: str, amount: float, credits: int, plan: str, payment_id: str = None):
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


def alert_payment_approved_sync(user_email: str, amount: float, credits: int, plan: str, payment_id: str = None):
    webhook = get_webhook()
    webhook.send_alert_sync(
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


async def alert_premium_activated(user_email: str, credits: int, expires_at: str, plan: str = "Premium Mensal"):
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
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.WARNING,
        "⏰ PLANO PREMIUM PERTO DE EXPIRAR",
        usuario=user_email,
        dias_restantes=days_left,
        expira_em=expires_at,
        acao="Renovar para continuar recebendo créditos diários"
    )


async def alert_system_error(error: Exception, endpoint: str = None, user: str = None, context: Dict = None):
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
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.INFO,
        "👤 NOVO USUÁRIO REGISTRADO",
        email=user_email,
        nome=name,
        user_id=user_id,
        data=datetime.now().strftime("%d/%m/%Y %H:%M")
    )


def alert_new_user_sync(user_email: str, name: str, user_id: int = None):
    webhook = get_webhook()
    webhook.send_alert_sync(
        AlertLevel.INFO,
        "👤 NOVO USUÁRIO REGISTRADO",
        email=user_email,
        nome=name,
        user_id=user_id,
        data=datetime.now().strftime("%d/%m/%Y %H:%M")
    )


async def alert_suspicious_activity(user_email: str, action: str, details: str = None, ip: str = None):
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
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.WARNING,
        "🔐 TENTATIVAS DE LOGIN FALHAS",
        email=email,
        ip=ip,
        tentativas=attempts,
        alerta="Possível ataque de força bruta"
    )


async def alert_redis_connection_issue(error: str, retry_count: int = 0):
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
    webhook = get_webhook()
    await webhook.send_alert(
        AlertLevel.CRITICAL,
        "🗄️ PROBLEMA NO BANCO DE DADOS",
        erro=error,
        impacto="Sistema pode ficar indisponível",
        acao="⚠️ AÇÃO IMEDIATA NECESSÁRIA"
    )


async def alert_gemini_api_error(error: str, endpoint: str = None, user_email: str = None):
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
# CICLO DE VIDA DA APLICAÇÃO
# ==============================================

async def startup_webhook():
    """Função para ser chamada no startup do FastAPI"""
    logger.info("🚀 Inicializando sistema de observabilidade...")
    await alert_system_startup()
    await start_metrics_reporting()
    
    # 🔥 INICIAR MONITOR DO MODELO
    start_model_monitoring(interval_hours=24)
    
    logger.info("✅ Sistema de observabilidade pronto!")


async def shutdown_webhook():
    """Função para ser chamada no shutdown do FastAPI"""
    global _webhook_instance
    
    # 🔥 PARAR MONITOR DO MODELO
    await stop_model_monitoring()
    
    if _webhook_instance:
        logger.info("🔄 Fechando webhook e cancelando tarefas pendentes...")
        await _webhook_instance.close()
        logger.info("✅ Webhook finalizado com sucesso")
    
    await stop_metrics_reporting()
    
    manager = get_background_manager()
    await manager.cancel_all()
    logger.info(f"✅ {manager.get_active_tasks()} tarefas em background canceladas")


# ==============================================
# FUNÇÃO PARA USAR COM BACKGROUNDTASKS (FASTAPI)
# ==============================================

def add_alert_to_background(background_tasks: BackgroundTasks, alert_func: Callable, *args, **kwargs):
    """
    Adiciona um alerta para ser executado em background pelo FastAPI
    
    Uso:
        @router.post("/register")
        async def register(user: UserCreate, background_tasks: BackgroundTasks):
            add_alert_to_background(background_tasks, alert_new_user, user.email, user.name)
            return {"message": "OK"}
    """
    background_tasks.add_task(alert_func, *args, **kwargs)


# ==============================================
# INSTÂNCIAS GLOBAIS
# ==============================================

_webhook_instance: Optional[DiscordWebhook] = None
_metrics_collector: Optional[MetricsCollector] = None
_monitor_task: Optional[asyncio.Task] = None


def get_webhook() -> DiscordWebhook:
    global _webhook_instance
    if _webhook_instance is None:
        _webhook_instance = DiscordWebhook()
    return _webhook_instance


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


async def start_metrics_reporting(interval: int = 60):
    global _monitor_task
    if _monitor_task:
        return
    
    async def report_loop():
        logger.info("📊 Iniciando relatório periódico de métricas...")
        webhook = get_webhook()
        metrics = get_metrics_collector()
        
        while True:
            await asyncio.sleep(interval)
            all_metrics = metrics.get_metrics()
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
# EXPORTAÇÕES
# ==============================================

__all__ = [
    'AlertLevel',
    'DiscordWebhook',
    'MetricsCollector',
    'LoggingMiddleware',
    'BackgroundTaskManager',
    'get_webhook',
    'get_metrics_collector',
    'get_background_manager',
    'add_alert_to_background',
    'monitor',
    'alert_payment_approved',
    'alert_payment_approved_sync',
    'alert_payment_pending',
    'alert_payment_failed',
    'alert_premium_activated',
    'alert_daily_credits_distributed',
    'alert_premium_expiring_soon',
    'alert_system_error',
    'alert_system_startup',
    'alert_new_user',
    'alert_new_user_sync',
    'alert_suspicious_activity',
    'alert_failed_login',
    'alert_redis_connection_issue',
    'alert_database_connection_issue',
    'alert_gemini_api_error',
    'alert_model_status',
    'start_model_monitoring',
    'stop_model_monitoring',
    'startup_webhook',
    'shutdown_webhook',
    'start_metrics_reporting',
    'stop_metrics_reporting',
]

print("✅ sentinel.py v2.2 carregado - COM MONITORAMENTO DE MODELO ML!")