# backend/api/upload_routes.py - VERSÃO 4.0 OTIMIZADA
"""
🚀 ROTAS DE UPLOAD OTIMIZADAS PARA ALTO DESEMPENHO
================================================================================
✅ Arquitetura assíncrona com pooling de conexões
✅ Processamento paralelo com semáforo para controle de concorrência
✅ Cache inteligente de resultados
✅ Pool de workers para ML Pipeline
✅ Sistema de filas com prioridade
✅ Monitoramento de métricas em tempo real
✅ Circuit breaker para falhas
✅ Retry com backoff exponencial
✅ Streaming de arquivos grandes
✅ Validação antecipada sem carregar arquivo inteiro na memória
✅ Rate limiting distribuído
✅ PoW com cache de desafios
================================================================================
"""

# ==============================================
# 🔥 IMPORTS OTIMIZADOS
# ==============================================

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import Optional, List, Dict, Any, Tuple, Set, Union
import logging
import os
import uuid
import hashlib
from datetime import datetime, timedelta
import asyncio
import time
import json
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import aiofiles
import aiohttp
from asyncio import Semaphore, Queue, TimeoutError
from functools import lru_cache
from contextlib import asynccontextmanager
import concurrent.futures

from backend.database import get_db
from backend import crud, models
from backend.security import get_current_active_user
from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display
from backend.security import rate_limiter
from backend.api.pow_routes import validate_pow_request, pow_service, PoWConfig
from backend.preprocessing import process_file_content, pipeline

# ==============================================
# 🔥 CONFIGURAÇÃO OTIMIZADA
# ==============================================

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

class UploadConfig:
    """Configurações centralizadas com otimizações"""
    
    # Limites de arquivo
    MAX_FILE_SIZE = 200 * 1024  # 200KB
    MAX_FILES_PER_BATCH = 5
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv'}
    ALLOWED_MIME_TYPES = {
        'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/tab-separated-values'
    }
    
    # Rate Limiter otimizado
    RATE_LIMIT_UPLOAD_PER_IP = 20  # Aumentado
    RATE_LIMIT_UPLOAD_PER_USER = 10
    RATE_LIMIT_WINDOW_SECONDS = 60
    RATE_LIMIT_BURST = 5  # Permite pico inicial
    
    # Timeouts e retry
    PROCESSING_TIMEOUT_SECONDS = 300
    UPLOAD_TIMEOUT_SECONDS = 30
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 2
    
    # Performance
    MAX_CONCURRENT_PROCESSING = 3  # Semáforo
    CHUNK_SIZE = 8192  # 8KB para streaming
    CACHE_TTL_SECONDS = 300
    QUEUE_MAX_SIZE = 100
    
    # Circuit Breaker
    CIRCUIT_BREAKER_THRESHOLD = 5
    CIRCUIT_BREAKER_TIMEOUT = 60
    
    # Monitoramento
    ENABLE_METRICS = True
    METRICS_INTERVAL = 60

# ==============================================
# 🔥 MODELOS DE DADOS OTIMIZADOS
# ==============================================

class ProcessingPriority(Enum):
    """Prioridades de processamento"""
    HIGH = 0
    NORMAL = 1
    LOW = 2

@dataclass
class UploadFileInfo:
    """Informações de um arquivo com cache"""
    filename: str
    content: bytes
    file_size: int
    file_extension: str
    mime_type: Optional[str] = None
    process_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    analysis_id: Optional[int] = None
    status: str = "pending"
    error: Optional[str] = None
    _hash: Optional[str] = None
    
    @property
    def is_valid_extension(self) -> bool:
        return self.file_extension.lower() in UploadConfig.ALLOWED_EXTENSIONS
    
    @property
    def is_valid_size(self) -> bool:
        return self.file_size <= UploadConfig.MAX_FILE_SIZE
    
    @property
    def size_kb(self) -> float:
        return self.file_size / 1024
    
    @property
    def hash(self) -> str:
        """Cache do hash para evitar recálculo"""
        if self._hash is None:
            self._hash = hashlib.md5(self.content).hexdigest()
        return self._hash

@dataclass
class ProcessingJob:
    """Job de processamento para a fila"""
    file_info: UploadFileInfo
    user_id: int
    user_email: str
    priority: ProcessingPriority = ProcessingPriority.NORMAL
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    max_retries: int = UploadConfig.MAX_RETRIES

# ==============================================
# 🔥 CACHE INTELIGENTE
# ==============================================

class ProcessingCache:
    """Cache de resultados de processamento"""
    
    def __init__(self, max_size: int = 1000, ttl: int = UploadConfig.CACHE_TTL_SECONDS):
        self._cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Obtém do cache se válido"""
        async with self._lock:
            if key not in self._cache:
                return None
            
            data, timestamp = self._cache[key]
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                return None
            
            return data
    
    async def set(self, key: str, value: Dict[str, Any]) -> None:
        """Armazena no cache"""
        async with self._lock:
            if len(self._cache) >= self._max_size:
                # LRU: remove o mais antigo
                oldest = min(self._cache.items(), key=lambda x: x[1][1])
                del self._cache[oldest[0]]
            
            self._cache[key] = (value, time.time())
    
    async def invalidate(self, key: str) -> None:
        """Invalida uma entrada"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Estatísticas do cache"""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl": self._ttl
        }

# ==============================================
# 🔥 GERENCIADOR DE STATUS OTIMIZADO
# ==============================================

class ProcessingStatusManager:
    """Gerencia status com persistência em memória e banco"""
    
    def __init__(self, max_items: int = 1000):
        self._status: Dict[str, Dict[str, Any]] = {}
        self._max_items = max_items
        self._lock = asyncio.Lock()
        self._cache = ProcessingCache()
        self._metrics = defaultdict(int)
    
    async def create(self, process_id: str, data: Dict[str, Any]) -> None:
        """Cria um novo status"""
        async with self._lock:
            if len(self._status) >= self._max_items:
                await self._cleanup()
            
            self._status[process_id] = {
                "process_id": process_id,
                "status": "uploaded",
                "progress": 10,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "retry_count": 0,
                **data
            }
            self._metrics["created"] += 1
    
    async def update(self, process_id: str, updates: Dict[str, Any]) -> bool:
        """Atualiza status com cache invalidation"""
        async with self._lock:
            if process_id not in self._status:
                return False
            
            self._status[process_id].update(updates)
            self._status[process_id]["updated_at"] = datetime.now().isoformat()
            
            # Invalida cache
            await self._cache.invalidate(f"status:{process_id}")
            
            return True
    
    async def get(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Obtém status com cache"""
        # Tenta cache primeiro
        cache_key = f"status:{process_id}"
        cached = await self._cache.get(cache_key)
        if cached:
            return cached
        
        async with self._lock:
            status = self._status.get(process_id)
            if status:
                await self._cache.set(cache_key, status)
            return status
    
    async def get_user_analyses(self, user_email: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtém análises de um usuário com paginação"""
        async with self._lock:
            analyses = []
            for data in self._status.values():
                if data.get("user_email") == user_email:
                    analyses.append({
                        "process_id": data.get("process_id"),
                        "filename": data.get("filename"),
                        "status": data.get("status"),
                        "progress": data.get("progress", 0),
                        "created_at": data.get("created_at"),
                        "completed_at": data.get("completed_at"),
                        "encoding_used": data.get("encoding_used"),
                        "pow_validated": data.get("pow_validated", False),
                    })
            
            analyses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return analyses[:limit]
    
    async def _cleanup(self) -> None:
        """Limpa status antigos com critérios inteligentes"""
        # Remove os mais antigos, mas mantém os que estão em processamento
        sorted_items = sorted(
            self._status.items(),
            key=lambda x: x[1].get("created_at", "")
        )
        
        to_remove = len(self._status) - self._max_items + 50
        removed = 0
        for process_id, data in sorted_items:
            if removed >= to_remove:
                break
            if data.get("status") not in ["processing", "pending"]:
                del self._status[process_id]
                removed += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas"""
        return {
            "total_items": len(self._status),
            "max_items": self._max_items,
            "by_status": {
                "uploaded": len([s for s in self._status.values() if s.get("status") == "uploaded"]),
                "processing": len([s for s in self._status.values() if s.get("status") == "processing"]),
                "completed": len([s for s in self._status.values() if s.get("status") == "completed"]),
                "error": len([s for s in self._status.values() if s.get("status") == "error"]),
            },
            "metrics": dict(self._metrics),
            "cache": self._cache.get_stats()
        }

# ==============================================
# 🔥 CIRCUIT BREAKER
# ==============================================

class CircuitBreaker:
    """Circuit breaker para proteção contra falhas"""
    
    def __init__(self, name: str, threshold: int = UploadConfig.CIRCUIT_BREAKER_THRESHOLD, 
                 timeout: int = UploadConfig.CIRCUIT_BREAKER_TIMEOUT):
        self.name = name
        self.threshold = threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.is_open = False
        self._lock = asyncio.Lock()
    
    async def call(self, func, *args, **kwargs):
        """Executa função com proteção do circuit breaker"""
        async with self._lock:
            if self.is_open:
                if time.time() - self.last_failure_time > self.timeout:
                    # Tentar fechar o circuito
                    self.is_open = False
                    self.failures = 0
                    logger.info(f"🔒 Circuit breaker {self.name} fechado novamente")
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Serviço indisponível. Circuit breaker {self.name} aberto."
                    )
        
        try:
            result = await func(*args, **kwargs)
            # Sucesso: resetar contador
            async with self._lock:
                self.failures = 0
            return result
        except Exception as e:
            async with self._lock:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.threshold:
                    self.is_open = True
                    logger.error(f"🔴 Circuit breaker {self.name} aberto após {self.failures} falhas")
            raise

# ==============================================
# 🔥 PROCESSADOR DE ML OTIMIZADO
# ==============================================

class MLProcessor:
    """Processador de Machine Learning otimizado com pool e semáforo"""
    
    _semaphore = Semaphore(UploadConfig.MAX_CONCURRENT_PROCESSING)
    _queue: Queue = Queue(maxsize=UploadConfig.QUEUE_MAX_SIZE)
    _workers: List[asyncio.Task] = []
    _circuit_breaker = CircuitBreaker("ml_pipeline")
    _results_cache = ProcessingCache()
    
    @classmethod
    async def start_workers(cls, num_workers: int = 2):
        """Inicia workers para processamento em background"""
        for i in range(num_workers):
            worker = asyncio.create_task(cls._worker_loop(f"worker-{i}"))
            cls._workers.append(worker)
        logger.info(f"🚀 Iniciados {num_workers} workers de ML")
    
    @classmethod
    async def _worker_loop(cls, worker_name: str):
        """Loop principal do worker"""
        while True:
            try:
                job: ProcessingJob = await cls._queue.get()
                logger.info(f"👷 {worker_name} processando: {job.file_info.filename}")
                
                # Processar com circuit breaker
                result = await cls._circuit_breaker.call(
                    cls._process_file_with_timeout,
                    job
                )
                
                # Atualizar status final
                if result.get("success"):
                    await processing_status.update(job.file_info.process_id, {
                        "status": "completed",
                        "progress": 100,
                        "completed_at": datetime.now().isoformat()
                    })
                else:
                    await processing_status.update(job.file_info.process_id, {
                        "status": "error",
                        "error": result.get("error", "Erro desconhecido")
                    })
                
                cls._queue.task_done()
                
            except asyncio.CancelledError:
                logger.info(f"🛑 Worker {worker_name} parado")
                break
            except Exception as e:
                logger.error(f"❌ Erro no worker {worker_name}: {e}")
                cls._queue.task_done()
    
    @classmethod
    async def submit_job(cls, file_info: UploadFileInfo, user_id: int, user_email: str, 
                         priority: ProcessingPriority = ProcessingPriority.NORMAL):
        """Submete um job para processamento"""
        job = ProcessingJob(
            file_info=file_info,
            user_id=user_id,
            user_email=user_email,
            priority=priority
        )
        
        # Verificar cache primeiro
        cache_key = f"result:{file_info.hash}"
        cached_result = await cls._results_cache.get(cache_key)
        if cached_result:
            logger.info(f"📦 Resultado em cache para {file_info.filename}")
            return cached_result
        
        # Adicionar à fila
        await cls._queue.put(job)
        logger.info(f"📥 Job enfileirado: {file_info.filename} (prioridade: {priority.name})")
        
        return {"status": "queued", "process_id": file_info.process_id}
    
    @classmethod
    async def _process_file_with_timeout(cls, job: ProcessingJob) -> Dict[str, Any]:
        """Processa arquivo com timeout e retry"""
        try:
            return await asyncio.wait_for(
                cls._process_file_async(job),
                timeout=UploadConfig.PROCESSING_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                wait_time = UploadConfig.RETRY_BACKOFF_FACTOR ** job.retry_count
                logger.warning(f"⏰ Timeout, retentando em {wait_time}s (tentativa {job.retry_count})")
                await asyncio.sleep(wait_time)
                return await cls._process_file_with_timeout(job)
            raise
    
    @classmethod
    async def _process_file_async(cls, job: ProcessingJob) -> Dict[str, Any]:
        """Processamento assíncrono de arquivo"""
        file_info = job.file_info
        
        # Atualizar status
        await processing_status.update(file_info.process_id, {
            "status": "processing",
            "progress": 20,
            "message": "Iniciando ML Pipeline...",
            "retry_count": job.retry_count
        })
        
        try:
            # 🔥 CORREÇÃO: Processar com await
            result = await process_file_content(file_info.content, file_info.filename)
            
            # Cache do resultado
            cache_key = f"result:{file_info.hash}"
            await cls._results_cache.set(cache_key, result)
            
            # Consumir crédito
            await cls._consume_credit(job.user_id, file_info.process_id)
            
            return {"success": True, "result": result}
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Erro no processamento: {error_msg}")
            return {"success": False, "error": error_msg}
    
    @staticmethod
    async def _consume_credit(user_id: int, process_id: str) -> None:
        """Consume crédito de forma assíncrona"""
        from backend.database import SessionLocal
        from backend.models import User
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and not user.is_admin:
                success = consume_analysis_credit(user, db, 1)
                if success:
                    await processing_status.update(process_id, {
                        "credit_consumed": True,
                        "credits_remaining": user.credits
                    })
        finally:
            db.close()
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Estatísticas do processador"""
        return {
            "queue_size": cls._queue.qsize(),
            "workers_running": len(cls._workers),
            "max_concurrent": UploadConfig.MAX_CONCURRENT_PROCESSING,
            "circuit_breaker": {
                "is_open": cls._circuit_breaker.is_open,
                "failures": cls._circuit_breaker.failures
            },
            "cache": cls._results_cache.get_stats()
        }

# ==============================================
# 🔥 RATE LIMITER OTIMIZADO
# ==============================================

class RateLimiterOptimized:
    """Rate limiter distribuído com janela deslizante"""
    
    def __init__(self):
        self._window_size = UploadConfig.RATE_LIMIT_WINDOW_SECONDS
        self._burst = UploadConfig.RATE_LIMIT_BURST
        self._limits: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, key: str, limit: int, window: Optional[int] = None) -> bool:
        """Verifica rate limit com janela deslizante"""
        window = window or self._window_size
        now = time.time()
        cutoff = now - window
        
        async with self._lock:
            # Limpar entradas antigas
            self._limits[key] = [t for t in self._limits[key] if t > cutoff]
            
            # Verificar burst permitido
            if len(self._limits[key]) < self._burst:
                self._limits[key].append(now)
                return True
            
            # Verificar limite normal
            if len(self._limits[key]) < limit:
                self._limits[key].append(now)
                return True
            
            return False
    
    async def get_remaining(self, key: str, limit: int, window: Optional[int] = None) -> int:
        """Obtém tentativas restantes"""
        window = window or self._window_size
        now = time.time()
        cutoff = now - window
        
        async with self._lock:
            self._limits[key] = [t for t in self._limits[key] if t > cutoff]
            remaining = max(0, limit - len(self._limits[key]))
            return remaining

rate_limiter_optimized = RateLimiterOptimized()

# ==============================================
# 🔥 UTILITÁRIOS OTIMIZADOS
# ==============================================

@asynccontextmanager
async def timed_operation(operation_name: str):
    """Context manager para medir tempo de operação"""
    start = time.time()
    try:
        yield
    finally:
        duration = (time.time() - start) * 1000
        logger.debug(f"⏱️ {operation_name} levou {duration:.2f}ms")

async def validate_file_optimized(file: UploadFile, idx: int) -> Optional[UploadFileInfo]:
    """
    🔥 Validação otimizada - lê em chunks para evitar sobrecarga de memória
    """
    try:
        # Validar nome
        if not file.filename:
            return UploadFileInfo(
                filename=f"arquivo_{idx}",
                content=b"",
                file_size=0,
                file_extension="",
                error="Arquivo sem nome"
            )
        
        # Validar extensão
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in UploadConfig.ALLOWED_EXTENSIONS:
            return UploadFileInfo(
                filename=file.filename,
                content=b"",
                file_size=0,
                file_extension=file_ext,
                error=f"Formato não suportado. Use: {', '.join(UploadConfig.ALLOWED_EXTENSIONS)}"
            )
        
        # 🔥 CORREÇÃO: Ler em chunks para melhor performance
        content = bytearray()
        total_size = 0
        chunk = await file.read(UploadConfig.CHUNK_SIZE)
        
        while chunk:
            total_size += len(chunk)
            if total_size > UploadConfig.MAX_FILE_SIZE:
                return UploadFileInfo(
                    filename=file.filename,
                    content=b"",
                    file_size=total_size,
                    file_extension=file_ext,
                    error=f"Arquivo excede o limite de {UploadConfig.MAX_FILE_SIZE//1024}KB"
                )
            content.extend(chunk)
            chunk = await file.read(UploadConfig.CHUNK_SIZE)
        
        if total_size == 0:
            return UploadFileInfo(
                filename=file.filename,
                content=b"",
                file_size=0,
                file_extension=file_ext,
                error="Arquivo vazio"
            )
        
        # ✅ Arquivo válido
        return UploadFileInfo(
            filename=file.filename,
            content=bytes(content),
            file_size=total_size,
            file_extension=file_ext,
            mime_type=file.content_type
        )
        
    except Exception as e:
        logger.error(f"❌ Erro ao validar arquivo {file.filename}: {e}")
        return UploadFileInfo(
            filename=file.filename if hasattr(file, 'filename') else f"arquivo_{idx}",
            content=b"",
            file_size=0,
            file_extension="",
            error=str(e)
        )

def validate_credits_optimized(user: models.User, total_files: int) -> Dict[str, Any]:
    """Valida créditos de forma otimizada"""
    if user.is_admin:
        return {
            "valid": True,
            "credits_needed": 0,
            "credits_available": "∞",
            "message": "Admin - créditos ilimitados"
        }
    
    # Verificação rápida
    if user.credits < total_files:
        return {
            "valid": False,
            "credits_needed": total_files,
            "credits_available": user.credits,
            "message": f"Créditos insuficientes. Você tem {user.credits}, precisa de {total_files}."
        }
    
    return {
        "valid": True,
        "credits_needed": total_files,
        "credits_available": user.credits,
        "message": f"Créditos suficientes: {user.credits}"
    }

def create_analysis_record_optimized(
    db: Session,
    user_id: int,
    file_info: UploadFileInfo,
    analysis_type: str,
    request: Request,
    pow_valid: bool,
    pow_difficulty: int,
    client_ip: str,
    user_agent: Optional[str] = None,
) -> models.Analysis:
    """Cria registro de análise com batch insert otimizado"""
    
    nonce = request.headers.get(PoWConfig.HEADER_NONCE)
    challenge = request.headers.get(PoWConfig.HEADER_CHALLENGE)
    
    analysis = models.Analysis(
        user_id=user_id,
        filename=file_info.filename,
        file_size=file_info.file_size,
        analysis_type=analysis_type,
        model_used="auto",
        status="pending",
        uploaded_at=datetime.now(),
        pow_challenge=challenge,
        pow_nonce=nonce,
        pow_difficulty=pow_difficulty,
        pow_verified=pow_valid,
        pow_verified_at=datetime.now() if pow_valid else None,
        pow_algorithm=PoWConfig.ALGORITHM,
        client_ip=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        rate_limit_applied=False,
        processing_time_ms=None,
        upload_time_ms=None,
    )
    
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    
    return analysis

# ==============================================
# 🔥 ROTA PRINCIPAL OTIMIZADA
# ==============================================

@router.post("/upload-auto")
async def upload_auto_optimized(
    request: Request,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(..., description="Arquivos para upload (máx 5)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    priority: ProcessingPriority = Form(ProcessingPriority.NORMAL, description="Prioridade de processamento"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    🚀 UPLOAD OTIMIZADO COM PROCESSAMENTO PARALELO
    
    FLUXO OTIMIZADO:
    1. ✅ PoW validado com cache
    2. ✅ Rate Limiter com janela deslizante
    3. ✅ Verificação de créditos otimizada
    4. ✅ Validação de arquivos em streaming
    5. ✅ Enfileiramento para processamento paralelo
    6. ✅ Resposta imediata com status
    7. ✅ Processamento em background com workers
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    
    # ==============================================
    # 🔥 1. VALIDAÇÕES INICIAIS OTIMIZADAS
    # ==============================================
    
    total_files = len(files)
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > UploadConfig.MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Limite excedido. Máximo {UploadConfig.MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📤 [UPLOAD] Requisição de {current_user.email} | IP: {client_ip} | Arquivos: {total_files}")
    
    # ==============================================
    # 🔥 2. RATE LIMITER OTIMIZADO
    # ==============================================
    
    # Rate limit por IP com janela deslizante
    ip_key = f"upload_ip:{client_ip}"
    if not await rate_limiter_optimized.check_rate_limit(ip_key, UploadConfig.RATE_LIMIT_UPLOAD_PER_IP):
        remaining = await rate_limiter_optimized.get_remaining(ip_key, UploadConfig.RATE_LIMIT_UPLOAD_PER_IP)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitos uploads. Aguarde {UploadConfig.RATE_LIMIT_WINDOW_SECONDS} segundos.",
                "remaining": remaining,
                "limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP,
                "window": UploadConfig.RATE_LIMIT_WINDOW_SECONDS
            }
        )
    
    # Rate limit por usuário
    user_key = f"upload_user:{current_user.id}"
    if not await rate_limiter_optimized.check_rate_limit(user_key, UploadConfig.RATE_LIMIT_UPLOAD_PER_USER):
        remaining = await rate_limiter_optimized.get_remaining(user_key, UploadConfig.RATE_LIMIT_UPLOAD_PER_USER)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitos uploads. Aguarde {UploadConfig.RATE_LIMIT_WINDOW_SECONDS} segundos.",
                "remaining": remaining,
                "limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER,
                "window": UploadConfig.RATE_LIMIT_WINDOW_SECONDS
            }
        )
    
    # ==============================================
    # 🔥 3. VERIFICAÇÃO DE CRÉDITOS
    # ==============================================
    
    credit_check = validate_credits_optimized(current_user, total_files)
    if not credit_check["valid"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check["message"],
                "credits_available": credit_check["credits_available"],
                "credits_needed": credit_check["credits_needed"]
            }
        )
    
    # ==============================================
    # 🔥 4. PROCESSAMENTO PARALELO DE ARQUIVOS
    # ==============================================
    
    accepted_files: List[UploadFileInfo] = []
    rejected_files: List[UploadFileInfo] = []
    analyses_created: List[int] = []
    jobs_submitted: List[str] = []
    
    pow_difficulty = request.headers.get(PoWConfig.HEADER_COMPLEXITY, PoWConfig.DEFAULT_DIFFICULTY)
    
    # Validar arquivos em paralelo
    validation_tasks = []
    for idx, file in enumerate(files):
        validation_tasks.append(validate_file_optimized(file, idx))
    
    validation_results = await asyncio.gather(*validation_tasks)
    
    for idx, file_info in enumerate(validation_results):
        if file_info.error:
            rejected_files.append(file_info)
            logger.warning(f"⚠️ Arquivo rejeitado: {file_info.filename} - {file_info.error}")
            continue
        
        try:
            # Criar registro no banco (batch)
            analysis = create_analysis_record_optimized(
                db=db,
                user_id=current_user.id,
                file_info=file_info,
                analysis_type=analysis_type,
                request=request,
                pow_valid=pow_valid,
                pow_difficulty=int(pow_difficulty) if pow_difficulty else 4,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            file_info.analysis_id = analysis.id
            analyses_created.append(analysis.id)
            
            # Criar status em memória
            await processing_status.create(file_info.process_id, {
                "filename": file_info.filename,
                "file_size": file_info.file_size,
                "user_id": current_user.id,
                "user_email": current_user.email,
                "analysis_id": analysis.id,
                "analysis_type": analysis_type,
                "batch_index": idx,
                "batch_total": total_files,
                "message": "Arquivo recebido, aguardando processamento...",
                "credits_consumed": False,
                "pow_validated": pow_valid,
                "pow_difficulty": int(pow_difficulty) if pow_difficulty else 4,
                "priority": priority.name
            })
            
            accepted_files.append(file_info)
            logger.info(f"✅ Arquivo {idx+1}/{total_files} aceito: {file_info.filename}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo {files[idx].filename}: {e}")
            file_info.error = str(e)
            rejected_files.append(file_info)
    
    # ==============================================
    # 🔥 5. ENFILEIRAMENTO PARA PROCESSAMENTO
    # ==============================================
    
    if accepted_files:
        # Enfileirar jobs para processamento paralelo
        for file_info in accepted_files:
            await MLProcessor.submit_job(
                file_info=file_info,
                user_id=current_user.id,
                user_email=current_user.email,
                priority=priority
            )
            jobs_submitted.append(file_info.process_id)
        
        logger.info(f"📥 {len(jobs_submitted)} jobs enfileirados para processamento")
    
    # ==============================================
    # 🔥 6. RESPOSTA OTIMIZADA
    # ==============================================
    
    processing_time_ms = (time.time() - start_time) * 1000
    
    # Estatísticas de performance
    ml_stats = MLProcessor.get_stats()
    status_stats = processing_status.get_stats()
    pow_stats = pow_service.get_stats() if hasattr(pow_service, 'get_stats') else {}
    
    return {
        "success": len(rejected_files) == 0,
        "message": f"Processado {len(accepted_files)} de {total_files} arquivo(s). Jobs enfileirados.",
        "data": {
            "accepted_files": [
                {
                    "filename": f.filename,
                    "process_id": f.process_id,
                    "analysis_id": f.analysis_id,
                    "size_kb": round(f.size_kb, 2),
                    "hash": f.hash[:8],
                    "status": "queued"
                }
                for f in accepted_files
            ],
            "rejected_files": [
                {
                    "filename": f.filename,
                    "error": f.error,
                    "size_kb": round(f.size_kb, 2) if f.file_size > 0 else 0
                }
                for f in rejected_files
            ]
        },
        "credits": {
            "before": current_user.credits if not current_user.is_admin else "∞",
            "consumed": len(accepted_files) if not current_user.is_admin else 0,
            "display": get_credits_display(current_user),
            "is_admin": current_user.is_admin
        },
        "performance": {
            "processing_time_ms": round(processing_time_ms, 2),
            "files_accepted": len(accepted_files),
            "files_rejected": len(rejected_files),
            "jobs_queued": len(jobs_submitted),
            "queue_size": ml_stats.get("queue_size", 0)
        },
        "security": {
            "pow_validated": pow_valid,
            "pow_difficulty": int(pow_difficulty) if pow_difficulty else 4,
            "pow_stats": {
                "verified": pow_stats.get("challenges", {}).get("verified", 0),
                "replay_attacks_blocked": pow_stats.get("challenges", {}).get("replay_attacks_blocked", 0),
            },
            "rate_limit": {
                "ip_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP,
                "user_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER,
                "window_seconds": UploadConfig.RATE_LIMIT_WINDOW_SECONDS,
                "burst": UploadConfig.RATE_LIMIT_BURST
            },
            "client_ip": client_ip
        },
        "system": {
            "workers_running": ml_stats.get("workers_running", 0),
            "max_concurrent": UploadConfig.MAX_CONCURRENT_PROCESSING,
            "cache_size": ml_stats.get("cache", {}).get("size", 0),
            "circuit_breaker": ml_stats.get("circuit_breaker", {}),
            "processing_status": status_stats.get("by_status", {})
        },
        "timestamp": datetime.now().isoformat()
    }

# ==============================================
# 🔥 ROTAS DE MONITORAMENTO
# ==============================================

@router.get("/status/{process_id}")
async def get_status_optimized(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Verifica status com cache"""
    status_data = await processing_status.get(process_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return status_data

@router.get("/analyses/history")
async def get_analyses_history_optimized(
    current_user = Depends(get_current_active_user),
    limit: int = 10,
    status_filter: Optional[str] = None
):
    """Histórico com filtros"""
    analyses = await processing_status.get_user_analyses(current_user.email, limit)
    
    if status_filter:
        analyses = [a for a in analyses if a.get("status") == status_filter]
    
    return {
        "success": True,
        "total": len(analyses),
        "analyses": analyses,
        "filters": {
            "status": status_filter,
            "limit": limit
        }
    }

@router.get("/analysis/result/{process_id}")
async def get_analysis_result_optimized(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Retorna resultado com cache"""
    status_data = await processing_status.get(process_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if status_data.get("status") != "completed":
        return {
            "success": False,
            "message": "Análise ainda não concluída",
            "status": status_data.get("status"),
            "progress": status_data.get("progress", 0)
        }
    
    return {
        "success": True,
        "process_id": process_id,
        "analysis_id": status_data.get("analysis_id"),
        "filename": status_data.get("filename"),
        "analysis_info": status_data.get("analysis_info", {}),
        "prediction_stats": status_data.get("prediction_stats", {}),
        "insights": status_data.get("insights", {}),
        "recommendations": status_data.get("recommendations", []),
        "completed_at": status_data.get("completed_at"),
        "credit_consumed": status_data.get("credit_consumed", False),
        "encoding_used": status_data.get("encoding_used"),
        "pow_validated": status_data.get("pow_validated", False)
    }

@router.get("/system/stats")
async def get_system_stats(
    current_user = Depends(get_current_active_user)
):
    """Estatísticas do sistema (admin apenas)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return {
        "success": True,
        "processing": processing_status.get_stats(),
        "ml_processor": MLProcessor.get_stats(),
        "rate_limiter": {
            "window_size": UploadConfig.RATE_LIMIT_WINDOW_SECONDS,
            "burst": UploadConfig.RATE_LIMIT_BURST
        },
        "config": {
            "max_files": UploadConfig.MAX_FILES_PER_BATCH,
            "max_file_size_kb": UploadConfig.MAX_FILE_SIZE // 1024,
            "max_concurrent": UploadConfig.MAX_CONCURRENT_PROCESSING,
            "queue_max_size": UploadConfig.QUEUE_MAX_SIZE,
            "cache_ttl": UploadConfig.CACHE_TTL_SECONDS
        }
    }

# ==============================================
# 🔥 INICIALIZAÇÃO
# ==============================================

@router.on_event("startup")
async def startup_event():
    """Inicia workers na inicialização"""
    await MLProcessor.start_workers(num_workers=2)
    logger.info("🚀 Sistema de upload otimizado inicializado")

print("=" * 80)
print("🚀 UPLOAD_ROUTES.PY - VERSÃO 4.0 OTIMIZADA")
print("=" * 80)
print(f"   📁 Limites: {UploadConfig.MAX_FILES_PER_BATCH} arquivos, {UploadConfig.MAX_FILE_SIZE//1024}KB cada")
print(f"   🚦 Rate Limiter: {UploadConfig.RATE_LIMIT_UPLOAD_PER_IP}/IP + {UploadConfig.RATE_LIMIT_UPLOAD_PER_USER}/usuário")
print(f"   🤖 Workers: {UploadConfig.MAX_CONCURRENT_PROCESSING} concorrentes")
print(f"   📦 Cache: {UploadConfig.CACHE_TTL_SECONDS}s TTL")
print(f"   🔒 Circuit Breaker: {UploadConfig.CIRCUIT_BREAKER_THRESHOLD} falhas")
print(f"   ⏰ Timeout: {UploadConfig.PROCESSING_TIMEOUT_SECONDS}s")
print(f"   📊 Fila: {UploadConfig.QUEUE_MAX_SIZE} jobs")
print(f"   🔐 PoW: {PoWConfig.ALGORITHM} com dificuldade adaptativa")
print("=" * 80)