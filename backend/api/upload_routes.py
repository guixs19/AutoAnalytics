# backend/api/upload_routes.py - VERSÃO 12.7 (LÓGICA DE CRÉDITOS FORTALECIDA)
"""
🚀 ROTAS DE UPLOAD - VERSÃO 12.7
================================================================================
✅ CORREÇÃO v12.7:
   - 🔥 NÃO BLOQUEIA UPLOAD por falta de créditos (apenas avisa)
   - 🔥 CRIA ANÁLISE MESMO SEM CRÉDITOS (status "pending_credit")
   - 🔥 PROCESSAMENTO ML CONTINUA MESMO SEM CRÉDITOS
   - 🔥 CRÉDITO CONSUMIDO NO FINAL DO ML (se disponível)
   - 🔥 SE NÃO TIVER CRÉDITOS, análise fica "pending_credit"
   - 🔥 USUÁRIO PODE ASSINAR PREMIUM E LIBERAR ANÁLISE
   - 🔥 ROTA /analysis/retry-credit/{id} para liberar análises pendentes

✅ CORREÇÃO v12.6:
   - 🔥 CRÉDITO CONSUMIDO AUTOMATICAMENTE quando o ML termina o processamento
   - 🔥 NÃO CONSUME no upload (apenas verifica se tem créditos)
   - 🔥 NÃO CONSUME no PDF (já foi consumido)
   - 🔥 1 análise = 1 crédito (independente do número de arquivos)

✅ MANTIDO v12.3:
   - Elegibilidade de créditos
   - Polling e progresso
   - Rate limiting
   - Validação de arquivos
================================================================================
"""

# ==============================================
# 🔥 IMPORTS
# ==============================================

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, or_
from typing import Optional, List, Dict, Any, Tuple
import logging
import os
import hashlib
import asyncio
import time
import json
import csv
import io
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from decimal import Decimal
import pandas as pd

from backend.database import get_db
from backend import models
from backend import crud
from backend.security import get_current_active_user
from backend.api.pow_routes import validate_pow_request

# 🔥 IMPORTAR FUNÇÕES DO CRUD V2.3
from backend.crud import (
    get_credit_eligibility,
    MAX_CREDITS_PREMIUM,
    INITIAL_FREE_CREDITS,
    deduct_credits,
    manage_credits_after_consumption
)

# ==============================================
# 🔥 IMPORTS COM FALLBACK
# ==============================================

logger = logging.getLogger(__name__)

_ml_available = False
_report_available = False
_preprocessing_available = False

try:
    from backend.preprocessing import process_file_content, pipeline
    _preprocessing_available = True
    logger.info("✅ preprocessing carregado")
except ImportError as e:
    logger.warning(f"⚠️ preprocessing não disponível: {e}")

try:
    from backend.ml.multi_analysis import analyze_multiple_files
    _ml_available = True
    logger.info("✅ multi_analysis carregado")
except ImportError as e:
    logger.warning(f"⚠️ multi_analysis não disponível: {e}")
    async def analyze_multiple_files(files, user_id=None, user_email=None, force_reload=False, db_session=None, process_id=None):
        logger.warning("⚠️ Usando fallback de multi_analysis")
        return {
            "success": True,
            "total_files": len(files),
            "processed_files": len(files),
            "failed_files": 0,
            "files": [{"filename": f.get("filename", "unknown"), "success": True} for f in files],
            "executive_score": {"nota_geral": 7.0},
            "executive_summary": "Análise concluída com sucesso (modo fallback).",
            "recommendations": ["📊 Recomendação 1", "📈 Recomendação 2"],
            "chart_data": {"weekly": {"revenue": [1000] * 7, "costs": [300] * 7}},
            "error": None
        }


    
    class MockReport:
        def to_dict(self): return {"content": "Relatório gerado (modo fallback)"}
    
    def build_executive_report(analysis_result, user_name):
        logger.warning("⚠️ Usando fallback de report_builder")
        return MockReport()
    
    class MockReportBuilder:
        def to_html(self, report): return "<html><body>Relatório</body></html>"
        def to_pdf(self, report): return b"PDF content"
    
    report_builder = MockReportBuilder()

# ==============================================
# 🔥 CONFIGURAÇÃO
# ==============================================

router = APIRouter(tags=["upload"])

class UploadConfig:
    """Configurações centralizadas com valores otimizados"""
    # Limites de arquivo
    MAX_FILE_SIZE = 200 * 1024  # 200KB
    MAX_FILES_PER_BATCH = 5
    MAX_FILES_MULTI_ANALYZE = 3
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv', '.parquet'}
    
    # Timeouts
    PROCESSING_TIMEOUT_SECONDS = 500  # 8.3 minutos
    UPLOAD_TIMEOUT_SECONDS = 60
    CHUNK_SIZE = 8192
    
    # Cache
    CACHE_TTL = 300  # 5 minutos
    CACHE_MAX_SIZE = 100
    
    # Rate Limit
    RATE_LIMIT_PER_USER = 30
    RATE_LIMIT_WINDOW = 3600  # 1 hora
    
    # Histórico
    HISTORY_PAGE_SIZE = 10
    MAX_HISTORY_DAYS = 90
    
    # 🔥 V12.7: Créditos - 1 por análise
    MAX_CREDITS_PREMIUM = MAX_CREDITS_PREMIUM
    INITIAL_FREE_CREDITS = INITIAL_FREE_CREDITS
    CREDITS_PER_ANALYSIS = 1
    
    # Status
    STATUS_LABELS = {
        "pending": "⏳ Pendente",
        "processing": "🔄 Processando", 
        "completed": "✅ Concluído",
        "error": "❌ Erro",
        "pending_credit": "💳 Aguardando crédito",
        "cancelled": "🚫 Cancelado"
    }
    
    STATUS_COLORS = {
        "pending": "#f5a623",
        "processing": "#4a9eff",
        "completed": "#48bb78",
        "error": "#f56565",
        "pending_credit": "#9f7aea",
        "cancelled": "#a0aec0"
    }


# ==============================================
# 🔥 DATACLASSES
# ==============================================

@dataclass
class UploadFileInfo:
    """Informações de um arquivo com validação avançada"""
    filename: str
    content: bytes
    file_size: int
    file_extension: str
    mime_type: Optional[str] = None
    error: Optional[str] = None
    _hash: Optional[str] = None
    _detected_encoding: Optional[str] = None
    _preview: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        return self.error is None
    
    @property
    def size_kb(self) -> float:
        return self.file_size / 1024
    
    @property
    def hash(self) -> str:
        if self._hash is None and self.content:
            self._hash = hashlib.md5(self.content).hexdigest()
        return self._hash or ""
    
    @property
    def detected_encoding(self) -> str:
        if self._detected_encoding is None and self.content:
            try:
                import chardet
                result = chardet.detect(self.content[:10000])
                self._detected_encoding = result.get('encoding', 'utf-8') if result else 'utf-8'
            except:
                self._detected_encoding = 'utf-8'
        return self._detected_encoding or 'utf-8'
    
    @property
    def preview(self) -> str:
        if self._preview is None and self.content:
            try:
                text = self.content[:500].decode(self.detected_encoding, errors='ignore')
                self._preview = text[:200] + ("..." if len(text) > 200 else "")
            except:
                self._preview = "Preview não disponível"
        return self._preview or ""


@dataclass
class AnalysisStats:
    """Estatísticas avançadas de análises"""
    total: int = 0
    completed: int = 0
    error: int = 0
    processing: int = 0
    pending: int = 0
    cancelled: int = 0
    pending_credit: int = 0
    total_rows: int = 0
    average_score: float = 0.0
    total_files_size: int = 0
    success_rate: float = 0.0
    avg_processing_time: float = 0.0
    last_analysis_at: Optional[datetime] = None


# ==============================================
# 🔥 RATE LIMITER
# ==============================================

class RateLimiter:
    """Rate limiter por usuário com janela deslizante"""
    
    def __init__(self):
        self._requests: Dict[int, List[float]] = {}
        self._lock = asyncio.Lock()
    
    async def check_and_increment(self, user_id: int, limit: int = UploadConfig.RATE_LIMIT_PER_USER, window: int = UploadConfig.RATE_LIMIT_WINDOW) -> Tuple[bool, int]:
        async with self._lock:
            now = time.time()
            window_start = now - window
            
            if user_id not in self._requests:
                self._requests[user_id] = []
            
            self._requests[user_id] = [t for t in self._requests[user_id] if t > window_start]
            
            current_count = len(self._requests[user_id])
            if current_count >= limit:
                return False, current_count
            
            self._requests[user_id].append(now)
            return True, current_count + 1

_rate_limiter = RateLimiter()

# ==============================================
# 🔥 CACHE DE ESTATÍSTICAS
# ==============================================

class StatsCache:
    """Cache para estatísticas do usuário com TTL"""
    def __init__(self, ttl: int = 300):
        self._cache: Dict[int, Tuple[Dict[str, Any], float]] = {}
        self._ttl = ttl
    
    def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        if user_id in self._cache:
            data, timestamp = self._cache[user_id]
            if time.time() - timestamp < self._ttl:
                return data
            del self._cache[user_id]
        return None
    
    def set(self, user_id: int, data: Dict[str, Any]):
        self._cache[user_id] = (data, time.time())
    
    def clear(self, user_id: int = None):
        if user_id:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()

_stats_cache = StatsCache()


# ==============================================
# 🔥 FUNÇÕES DE VALIDAÇÃO
# ==============================================

def validate_file_advanced(file: UploadFile, idx: int) -> UploadFileInfo:
    """Valida um arquivo com verificações avançadas"""
    
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
    
    # Validar nome (segurança)
    if not re.match(r'^[a-zA-Z0-9_.\- ]+$', file.filename):
        return UploadFileInfo(
            filename=file.filename,
            content=b"",
            file_size=0,
            file_extension=file_ext,
            error="Nome do arquivo contém caracteres inválidos"
        )
    
    try:
        content = bytearray()
        total_size = 0
        chunk = file.file.read(UploadConfig.CHUNK_SIZE)
        
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
            chunk = file.file.read(UploadConfig.CHUNK_SIZE)
        
        if total_size == 0:
            return UploadFileInfo(
                filename=file.filename,
                content=b"",
                file_size=0,
                file_extension=file_ext,
                error="Arquivo vazio"
            )
        
        return UploadFileInfo(
            filename=file.filename,
            content=bytes(content),
            file_size=total_size,
            file_extension=file_ext,
            mime_type=file.content_type
        )
        
    except Exception as e:
        logger.error(f"❌ Erro ao ler arquivo {file.filename}: {e}")
        return UploadFileInfo(
            filename=file.filename or f"arquivo_{idx}",
            content=b"",
            file_size=0,
            file_extension=file_ext if 'file_ext' in locals() else "",
            error=str(e)
        )


async def validate_files_advanced(files: List[UploadFile]) -> Dict[str, Any]:
    """Valida múltiplos arquivos em paralelo com timeout"""
    
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(None, validate_file_advanced, file, idx)
                for idx, file in enumerate(files)
            ]),
            timeout=UploadConfig.UPLOAD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return {
            "valid": [],
            "invalid": [
                UploadFileInfo(
                    filename=f"arquivo_{idx}",
                    content=b"",
                    file_size=0,
                    file_extension="",
                    error="Timeout na validação"
                )
                for idx, _ in enumerate(files)
            ],
            "total": len(files),
            "valid_count": 0,
            "invalid_count": len(files)
        }
    
    valid_files = []
    invalid_files = []
    
    for result in results:
        if result.is_valid:
            valid_files.append(result)
        else:
            invalid_files.append(result)
    
    return {
        "valid": valid_files,
        "invalid": invalid_files,
        "total": len(files),
        "valid_count": len(valid_files),
        "invalid_count": len(invalid_files)
    }


# ==============================================
# 🔥 FUNÇÕES DE CRÉDITOS (VERSÃO 12.7 - FORTALECIDA)
# ==============================================

def get_user_credits_info(db: Session, user: models.User) -> Dict[str, Any]:
    """
    🔥 V12.7: Retorna informações completas de créditos do usuário COM ELEGIBILIDADE
    """
    user_refresh = db.query(models.User).filter(models.User.id == user.id).first()
    if not user_refresh:
        return {
            "balance": 0,
            "display": "0",
            "is_premium": False,
            "is_admin": False,
            "max_credits": None,
            "days_left_premium": 0,
            "can_receive_today": False,
            "at_max_limit": False,
            "reason": "Usuário não encontrado"
        }
    
    # 🔥 USAR ELEGIBILIDADE
    eligibility = get_credit_eligibility(db, user_refresh)
    
    is_premium = eligibility.get("is_premium", False)
    days_left = user_refresh.get_premium_days_left() if hasattr(user_refresh, 'get_premium_days_left') else 0
    
    return {
        "balance": int(user_refresh.credits) if user_refresh.credits else 0,
        "display": crud.get_credits_display(user_refresh) if hasattr(crud, 'get_credits_display') else str(user_refresh.credits or 0),
        "is_premium": is_premium,
        "is_admin": user_refresh.is_admin or False,
        "max_credits": MAX_CREDITS_PREMIUM if is_premium else None,
        "days_left_premium": days_left if is_premium else 0,
        "can_receive_today": eligibility.get("can_receive_today", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "received_today": eligibility.get("received_today", False),
        "reason": eligibility.get("reason", ""),
        "next_credit_date": eligibility.get("next_credit_date")
    }


def check_credits_advanced(db: Session, user: models.User, required: int) -> Dict[str, Any]:
    """
    🔥 V12.7: Verifica créditos com ELEGIBILIDADE e mensagens inteligentes
    🔥 V12.7: AGORA RETORNA informativo, NÃO BLOQUEIA
    
    Retorna informações detalhadas sobre:
    - Se tem créditos suficientes
    - Se é premium e pode receber crédito hoje
    - Sugestões personalizadas (FREE vs PREMIUM)
    """
    if user.is_admin:
        return {
            "valid": True,
            "message": "👑 Admin - créditos ilimitados",
            "available": "∞",
            "required": 0,
            "is_admin": True,
            "is_premium": True,
            "remaining_after": "∞",
            "can_proceed": True,
            "status": "admin"
        }
    
    # Buscar usuário atualizado
    user_refresh = db.query(models.User).filter(models.User.id == user.id).first()
    if not user_refresh:
        return {
            "valid": False,
            "message": "Usuário não encontrado",
            "available": 0,
            "required": required,
            "is_admin": False,
            "is_premium": False,
            "remaining_after": 0,
            "can_proceed": False,
            "status": "error"
        }
    
    # 🔥 USAR ELEGIBILIDADE
    eligibility = get_credit_eligibility(db, user_refresh)
    
    is_premium = eligibility.get("is_premium", False)
    current_credits = user_refresh.credits or 0
    can_receive_today = eligibility.get("can_receive_today", False)
    at_max_limit = eligibility.get("at_max_limit", False)
    reason = eligibility.get("reason", "")
    days_left = eligibility.get("days_left", 0)
    
    # 🔥 V12.7: SEMPRE PERMITE PROSSEGUIR (não bloqueia)
    # Apenas informa o status para o frontend
    
    if current_credits >= required:
        # ✅ TEM CRÉDITOS
        return {
            "valid": True,
            "message": f"✅ Créditos suficientes: {current_credits}",
            "available": current_credits,
            "required": required,
            "is_admin": False,
            "is_premium": is_premium,
            "can_receive_today": can_receive_today,
            "remaining_after": current_credits - required,
            "can_proceed": True,
            "status": "has_credits",
            "will_consume_at_end": True
        }
    else:
        # ❌ SEM CRÉDITOS SUFICIENTES
        # 🔥 PERMITE PROSSEGUIR, mas avisa que ficará pendente
        
        if is_premium and can_receive_today:
            return {
                "valid": False,
                "message": "⭐ Seus créditos premium acabaram! Você pode receber 1 crédito hoje.",
                "available": current_credits,
                "required": required,
                "is_admin": False,
                "is_premium": True,
                "suggestion": "Clique em 'Receber Crédito Diário' para ganhar 1 crédito grátis.",
                "can_receive_today": True,
                "remaining_after": 0,
                "can_proceed": True,  # 🔥 PERMITE PROSSEGUIR
                "status": "premium_can_receive",
                "will_consume_at_end": True,
                "pending_credit": True
            }
        elif is_premium and at_max_limit:
            return {
                "valid": False,
                "message": f"⚠️ Você atingiu o limite máximo de {MAX_CREDITS_PREMIUM} créditos.",
                "available": current_credits,
                "required": required,
                "is_admin": False,
                "is_premium": True,
                "suggestion": f"Gaste 1 crédito para poder receber mais.",
                "can_receive_today": False,
                "remaining_after": 0,
                "can_proceed": True,  # 🔥 PERMITE PROSSEGUIR
                "status": "premium_at_max",
                "will_consume_at_end": True,
                "pending_credit": True
            }
        elif is_premium and eligibility.get("received_today", False):
            return {
                "valid": False,
                "message": "📌 Você já recebeu seu crédito premium hoje. Volte amanhã!",
                "available": current_credits,
                "required": required,
                "is_admin": False,
                "is_premium": True,
                "suggestion": "Amanhã você receberá 1 crédito premium.",
                "can_receive_today": False,
                "remaining_after": 0,
                "can_proceed": True,  # 🔥 PERMITE PROSSEGUIR
                "status": "premium_received_today",
                "will_consume_at_end": True,
                "pending_credit": True
            }
        elif is_premium:
            return {
                "valid": False,
                "message": f"📌 {reason or 'Créditos insuficientes.'}",
                "available": current_credits,
                "required": required,
                "is_admin": False,
                "is_premium": True,
                "suggestion": "Aguarde o próximo ciclo de créditos.",
                "can_receive_today": False,
                "remaining_after": 0,
                "can_proceed": True,  # 🔥 PERMITE PROSSEGUIR
                "status": "premium_waiting",
                "will_consume_at_end": True,
                "pending_credit": True
            }
        else:
            # ❌ USUÁRIO FREE - SEM CRÉDITOS
            return {
                "valid": False,
                "message": f"💡 Seus créditos acabaram! Você tem {current_credits}, precisa de {required}.",
                "available": current_credits,
                "required": required,
                "is_admin": False,
                "is_premium": False,
                "suggestion": "Assine o plano Premium para receber 1 crédito por dia! 🚀",
                "can_receive_today": False,
                "remaining_after": 0,
                "can_proceed": True,  # 🔥 PERMITE PROSSEGUIR
                "status": "free_no_credits",
                "will_consume_at_end": True,
                "pending_credit": True
            }


# ==============================================
# 🔥 FUNÇÕES DE ESTATÍSTICAS DO USUÁRIO
# ==============================================

def get_user_analyses_count(db: Session, user_id: int) -> int:
    """Retorna o total de análises do usuário"""
    return db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id
    ).count()


def get_user_stats_advanced(db: Session, user_id: int) -> Dict[str, Any]:
    """Retorna estatísticas avançadas do usuário (V12.7 com pending_credit)"""
    
    # Total de análises
    total_analyses = get_user_analyses_count(db, user_id)
    
    # Análises por status
    status_counts = {}
    for status in UploadConfig.STATUS_LABELS.keys():
        count = db.query(models.Analysis).filter(
            models.Analysis.user_id == user_id,
            models.Analysis.status == status
        ).count()
        if count > 0:
            status_counts[status] = count
    
    # Análises hoje
    today = datetime.now().date()
    today_analyses = db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id,
        func.date(models.Analysis.uploaded_at) == today
    ).count()
    
    # Total de linhas processadas
    total_rows = db.query(func.sum(models.Analysis.rows_processed)).filter(
        models.Analysis.user_id == user_id,
        models.Analysis.status == "completed"
    ).first()
    total_rows = total_rows[0] or 0
    
    # Score médio
    scores = db.query(models.Analysis.confidence_score).filter(
        models.Analysis.user_id == user_id,
        models.Analysis.status == "completed",
        models.Analysis.confidence_score.isnot(None)
    ).all()
    
    avg_score = 0
    if scores:
        total_score = sum(s[0] for s in scores if s[0])
        avg_score = round(total_score / len(scores), 2) if scores else 0
    
    # Última análise
    last_analysis = db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id
    ).order_by(desc(models.Analysis.uploaded_at)).first()
    
    # Tempo médio de processamento
    avg_time = db.query(func.avg(models.Analysis.processing_time_ms)).filter(
        models.Analysis.user_id == user_id,
        models.Analysis.status == "completed"
    ).first()
    avg_processing_time = avg_time[0] or 0
    
    # 🔥 V12.7: Análises com créditos pendentes
    pending_credit = db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id,
        models.Analysis.status == "pending_credit"
    ).count()
    
    # 🔥 V12.7: Análises com créditos já consumidos
    credits_consumed = db.query(models.Analysis).filter(
        models.Analysis.user_id == user_id,
        models.Analysis.credits_consumed == True
    ).count()
    
    return {
        "total_analyses": total_analyses,
        "today_analyses": today_analyses,
        "status_counts": status_counts,
        "total_rows_processed": total_rows,
        "average_score": avg_score,
        "avg_processing_time_ms": round(avg_processing_time, 0) if avg_processing_time else 0,
        "last_analysis_at": last_analysis.uploaded_at.isoformat() if last_analysis and last_analysis.uploaded_at else None,
        "last_analysis_filename": last_analysis.filename if last_analysis else None,
        "pending_credit": pending_credit,
        "credits_consumed": credits_consumed
    }


# ==============================================
# 🔥🔥🔥 FUNÇÃO: ATUALIZAR PROGRESSO
# ==============================================

async def update_analysis_progress(db: Session, process_id: int, progress: int, message: str) -> bool:
    """
    🔥 Atualiza o progresso de uma análise no banco de dados
    Usada pelo processamento em background para informar o frontend via polling
    """
    try:
        analysis = db.query(models.Analysis).filter(models.Analysis.id == process_id).first()
        if analysis:
            analysis.progress = progress
            analysis.progress_message = message
            if progress < 100:
                analysis.status = "processing"
            db.commit()
            logger.info(f"📊 [Progresso] Análise {process_id}: {progress}% - {message}")
            return True
        else:
            logger.warning(f"⚠️ Análise {process_id} não encontrada para atualizar progresso")
            return False
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar progresso da análise {process_id}: {e}")
        db.rollback()
        return False


# ==============================================
# 🔥🔥🔥 FUNÇÃO: CONSUMIR CRÉDITO DA ANÁLISE (V12.7 - FORTALECIDA)
# ==============================================

async def consume_analysis_credit(
    db: Session,
    analysis: models.Analysis,
    user: models.User
) -> Tuple[bool, str]:
    """
    🔥 V12.7: Consome 1 crédito da análise (FORTALECIDA)
    Retorna (success, message)
    """
    if not analysis or not user:
        return False, "Dados inválidos"
    
    # Admin não consome créditos
    if user.is_admin:
        analysis.credits_consumed = True
        analysis.credits_consumed_at = datetime.now()
        analysis.credits_consumed_amount = 0
        analysis.credits_remaining_after = None
        analysis.status = "completed"
        db.commit()
        logger.info(f"👑 [CREDIT] Admin {user.email} - análise {analysis.id} marcada como consumida")
        return True, "Admin - créditos ilimitados"
    
    # Verificar se já consumiu
    if analysis.credits_consumed:
        return True, "Crédito já consumido anteriormente"
    
    # 🔥 V12.7: Verificar se tem créditos
    # Se não tiver, análise fica pendente (mas já foi processada)
    if user.credits < 1:
        # 🔥 Sem créditos - análise fica pendente
        analysis.status = "pending_credit"
        analysis.progress_message = "💡 Créditos insuficientes. Assine Premium para liberar os resultados."
        analysis.credits_error = "Créditos insuficientes"
        db.commit()
        logger.warning(f"⚠️ [CREDIT] Usuário {user.email} sem créditos para análise {analysis.id}")
        logger.info(f"📌 [CREDIT] Análise {analysis.id} em pending_credit - aguardando assinatura Premium")
        return False, "Créditos insuficientes. Análise aguardando créditos."
    
    try:
        # 🔥 CONSUMIR 1 CRÉDITO
        result = manage_credits_after_consumption(
            db=db,
            user=user,
            amount=1,
            description=f"Análise ML {analysis.id}: {analysis.filename[:50]}"
        )
        
        if result.get("success"):
            db.refresh(user)
            
            # Atualizar análise
            analysis.credits_consumed = True
            analysis.credits_consumed_at = datetime.now()
            analysis.credits_consumed_amount = 1
            analysis.credits_remaining_after = user.credits
            analysis.status = "completed"
            analysis.progress_message = "✅ Análise concluída com sucesso! PDF disponível."
            
            # Registrar bônus se houver
            if result.get("bonus_granted"):
                analysis.credits_bonus_granted = True
                analysis.credits_bonus_amount = result.get("bonus_amount", 0)
                logger.info(f"⭐ [CREDIT] Bônus concedido: +{result.get('bonus_amount')} crédito(s)")
            
            db.commit()
            
            logger.info(f"💰 [CREDIT] 1 crédito consumido para análise {analysis.id}")
            logger.info(f"💰 [CREDIT] Saldo restante: {user.credits}")
            
            return True, f"Crédito consumido com sucesso. Saldo: {user.credits}"
        else:
            error_msg = result.get("message", "Erro desconhecido ao consumir crédito")
            logger.error(f"❌ [CREDIT] Falha ao consumir crédito: {error_msg}")
            
            analysis.credits_error = error_msg
            analysis.status = "pending_credit"
            analysis.progress_message = f"⚠️ Erro: {error_msg[:100]}"
            db.commit()
            
            return False, error_msg
            
    except Exception as e:
        logger.error(f"❌ [CREDIT] Erro ao consumir crédito: {e}")
        db.rollback()
        
        analysis.credits_error = str(e)
        analysis.status = "pending_credit"
        analysis.progress_message = f"⚠️ Erro: {str(e)[:100]}"
        db.commit()
        
        return False, str(e)


# ==============================================
# 🔥🔥🔥 FUNÇÃO DE PROCESSAMENTO EM BACKGROUND (V12.7 - FORTALECIDA)
# ==============================================

async def process_analysis_background(
    process_id: int,
    file_data_list: List[Dict[str, Any]],
    user_id: int,
    user_email: str,
    analysis_type: str,
    db: Session
):
    """
    🔥 PROCESSAMENTO EM BACKGROUND (V12.7 - FORTALECIDA)
    - Executa o ML mesmo sem créditos
    - Salva resultados
    - 🔥 TENTA CONSUMIR 1 CRÉDITO AUTOMATICAMENTE quando termina
    - 🔥 Se não tiver créditos, análise fica com status "pending_credit"
    - 🔥 Marca credits_consumed = True se consumiu
    - 🔥 PDF fica disponível SEM consumo adicional (após liberação)
    """
    try:
        logger.info(f"🔄 [BACKGROUND] Iniciando processamento {process_id}")
        logger.info(f"   📁 Arquivos: {len(file_data_list)}")
        logger.info(f"   👤 Usuário: {user_email} (ID: {user_id})")
        
        # ==========================================
        # 1. ATUALIZAR PROGRESSO: 20%
        # ==========================================
        
        await update_analysis_progress(db, process_id, 20, "Iniciando análise dos dados...")
        
        # ==========================================
        # 2. CARREGAR MÓDULOS ML
        # ==========================================
        
        from backend.ml.multi_analysis import analyze_multiple_files
        
        # ==========================================
        # 3. ATUALIZAR PROGRESSO: 30%
        # ==========================================
        
        await update_analysis_progress(db, process_id, 30, "Processando arquivos com IA...")
        
        # ==========================================
        # 4. EXECUTAR ANÁLISE ML (MESMO SEM CRÉDITOS)
        # ==========================================
        
        logger.info(f"🤖 [BACKGROUND] Chamando analyze_multiple_files para {process_id}")
        
        analysis_result = await analyze_multiple_files(
            files=file_data_list,
            user_id=user_id,
            user_email=user_email,
            force_reload=False,
            db_session=db,
            process_id=process_id
        )
        
        logger.info(f"✅ [BACKGROUND] analyze_multiple_files concluído para {process_id}")
        
        # ==========================================
        # 5. ATUALIZAR PROGRESSO: 80%
        # ==========================================
        
        await update_analysis_progress(db, process_id, 80, "Gerando relatório e insights...")
        
        # ==========================================
        # 6. BUSCAR A ANÁLISE NO BANCO
        # ==========================================
        
        analysis = db.query(models.Analysis).filter(models.Analysis.id == process_id).first()
        if not analysis:
            logger.error(f"❌ [BACKGROUND] Análise {process_id} não encontrada")
            return
        
        # ==========================================
        # 7. SALVAR RESULTADOS (MESMO SEM CRÉDITOS)
        # ==========================================
        
        chart_data = analysis_result.get('chart_data', {})
        executive_score = analysis_result.get('executive_score', {})
        executive_summary = analysis_result.get('executive_summary', '')
        recommendations = analysis_result.get('recommendations', [])
        avg_score = analysis_result.get('avg_score', 0)
        general_conclusion = analysis_result.get('general_conclusion', '')
        processed_files = analysis_result.get('processed_files', 0)
        
        # Salva todos os resultados (disponíveis mesmo em pending_credit)
        analysis.chart_data = chart_data
        analysis.insights = executive_summary
        analysis.recommendations = recommendations
        analysis.confidence_score = avg_score
        analysis.ai_report = general_conclusion
        analysis.rows_processed = processed_files
        analysis.processing_time_ms = int((datetime.now() - analysis.uploaded_at).total_seconds() * 1000)
        
        if executive_score:
            analysis.executive_score = executive_score
        
        # ==========================================
        # 8. 🔥🔥🔥 TENTAR CONSUMIR 1 CRÉDITO (V12.7)
        # ==========================================
        
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if user:
            credit_success, credit_message = await consume_analysis_credit(db, analysis, user)
            
            if credit_success:
                logger.info(f"✅ [BACKGROUND] Análise {process_id} concluída e crédito consumido!")
                logger.info(f"💰 [BACKGROUND] {credit_message}")
                analysis.progress_message = "✅ Análise concluída com sucesso! PDF disponível."
            else:
                # ❌ Falha ao consumir crédito - análise fica pendente
                logger.warning(f"⚠️ [BACKGROUND] Análise {process_id} em status 'pending_credit'")
                logger.info(f"📌 [BACKGROUND] Usuário pode assinar Premium e usar /analysis/retry-credit/{process_id}")
                analysis.progress_message = f"💡 Análise processada! {credit_message[:100]}"
                analysis.status = "pending_credit"
                db.commit()
                return
        else:
            logger.error(f"❌ [BACKGROUND] Usuário {user_id} não encontrado")
            analysis.status = "error"
            analysis.progress_message = "❌ Usuário não encontrado"
            db.commit()
            return
        
        # ==========================================
        # 9. FINALIZAR
        # ==========================================
        
        db.commit()
        
        logger.info(f"✅ [BACKGROUND] Processamento {process_id} concluído com sucesso!")
        logger.info(f"💰 [BACKGROUND] Crédito consumido, PDF disponível sem custo adicional")
        
    except Exception as e:
        logger.error(f"❌ [BACKGROUND] Erro no processamento {process_id}: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            analysis = db.query(models.Analysis).filter(models.Analysis.id == process_id).first()
            if analysis:
                analysis.status = "error"
                analysis.progress_message = f"❌ Erro: {str(e)[:200]}"
                db.commit()
                logger.info(f"📊 [BACKGROUND] Status da análise {process_id} atualizado para 'error'")
        except Exception as db_error:
            logger.error(f"❌ [BACKGROUND] Erro ao atualizar status de erro: {db_error}")


# ==============================================
# 🔥 ROTA: ESTATÍSTICAS DO USUÁRIO
# ==============================================

@router.get("/analyses/count")
async def get_user_analyses_count_endpoint(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 Retorna o total de análises do usuário
    """
    try:
        total = get_user_analyses_count(db, current_user.id)
        return jsonable_encoder({
            "success": True,
            "total_analyses": total,
            "user_id": current_user.id,
            "email": current_user.email
        })
    except Exception as e:
        logger.error(f"❌ Erro ao buscar total de análises: {e}")
        return jsonable_encoder({
            "success": False,
            "error": str(e),
            "total_analyses": 0
        })


@router.get("/analyses/credits")
async def get_user_credits_status(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 V12.7: Retorna status detalhado de créditos e análises do usuário
    """
    try:
        user = db.query(models.User).filter(models.User.id == current_user.id).first()
        if not user:
            return jsonable_encoder({
                "success": False,
                "error": "Usuário não encontrado"
            })
        
        stats = get_user_stats_advanced(db, user.id)
        credits_info = get_user_credits_info(db, user)
        
        return jsonable_encoder({
            "success": True,
            "credits": credits_info,
            "analyses": stats,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "is_premium": credits_info.get("is_premium", False),
                "is_admin": user.is_admin or False
            },
            "credits_per_analysis": UploadConfig.CREDITS_PER_ANALYSIS
        })
    except Exception as e:
        logger.error(f"❌ Erro ao buscar status de créditos: {e}")
        return jsonable_encoder({
            "success": False,
            "error": str(e)
        })


# ==============================================
# 🔥🔥🔥 ROTA: PROGRESSO DA ANÁLISE (POLLING) - V12.7
# ==============================================

@router.get("/analysis/progress/{process_id}")
async def get_analysis_progress(
    process_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 CONSULTA PROGRESSO DA ANÁLISE (V12.7)
    Retorna status completo, incluindo se o crédito foi consumido
    """
    analysis = db.query(models.Analysis).filter(
        models.Analysis.id == process_id,
        models.Analysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    # 🔥 V12.7: Verifica se a análise está com crédito pendente
    if analysis.status == "pending_credit":
        return {
            "process_id": process_id,
            "status": "pending_credit",
            "progress": 95,
            "message": "💡 Análise processada! Assine Premium para liberar os resultados.",
            "result": None,
            "credits": {
                "needed": UploadConfig.CREDITS_PER_ANALYSIS,
                "status": "pending",
                "message": "Análise aguardando 1 crédito para finalizar.",
                "action": "Assine Premium ou receba crédito diário",
                "retry_url": f"/api/analysis/retry-credit/{process_id}"
            },
            "can_receive_credit": current_user.is_premium() and current_user.credits < MAX_CREDITS_PREMIUM
        }
    
    if analysis.status == "completed":
        result_data = {
            "id": analysis.id,
            "filename": analysis.filename,
            "file_size": analysis.file_size,
            "status": analysis.status,
            "rows_processed": analysis.rows_processed or 0,
            "model_used": analysis.model_used or "AutoML",
            "analysis_type": analysis.analysis_type or "auto",
            "uploaded_at": analysis.uploaded_at.isoformat() if analysis.uploaded_at else None,
            "processed_at": analysis.processed_at.isoformat() if analysis.processed_at else None,
            "encoding_used": analysis.encoding_used,
            "pow_verified": analysis.pow_verified,
            "processing_time_ms": analysis.processing_time_ms or 0,
            "confidence_score": float(analysis.confidence_score) if analysis.confidence_score else 0,
            "chart_data": analysis.chart_data or {},
            "insights": analysis.insights or {},
            "recommendations": analysis.recommendations or [],
            "ai_report": analysis.ai_report or "",
            "executive_summary": analysis.insights or "",
            "metrics": {
                "mean": float(analysis.confidence_score) if analysis.confidence_score else 0,
                "high_risk_percentage": 0,
                "low_risk_percentage": 0,
                "total_predictions": analysis.rows_processed or 0,
                "processing_time_ms": analysis.processing_time_ms or 0
            },
            "executive_score": {},
            # 🔥 V12.7: Status de créditos - JÁ CONSUMIDO
            "credits": {
                "consumed": analysis.credits_consumed if hasattr(analysis, 'credits_consumed') else False,
                "consumed_at": analysis.credits_consumed_at.isoformat() if hasattr(analysis, 'credits_consumed_at') and analysis.credits_consumed_at else None,
                "amount_consumed": analysis.credits_consumed_amount if hasattr(analysis, 'credits_consumed_amount') else 0,
                "remaining_after": analysis.credits_remaining_after if hasattr(analysis, 'credits_remaining_after') else None,
                "credits_needed": UploadConfig.CREDITS_PER_ANALYSIS,
                "message": "✅ Crédito consumido automaticamente na conclusão da análise." if analysis.credits_consumed else "Aguardando consumo de crédito..."
            }
        }
        
        if hasattr(analysis, 'executive_score') and analysis.executive_score:
            result_data["executive_score"] = analysis.executive_score
        
        logger.info(f"📊 [POLLING] Retornando análise {process_id} - créditos consumidos: {analysis.credits_consumed if hasattr(analysis, 'credits_consumed') else False}")
        
        return {
            "process_id": process_id,
            "status": "completed",
            "progress": 100,
            "message": "✅ Análise concluída! PDF disponível para download.",
            "result": result_data,
            "credits_consumed": analysis.credits_consumed if hasattr(analysis, 'credits_consumed') else False
        }
    
    if analysis.status == "processing":
        return {
            "process_id": process_id,
            "status": "processing",
            "progress": analysis.progress or 0,
            "message": analysis.progress_message or "🔄 Processando...",
            "result": None
        }
    
    if analysis.status == "error":
        return {
            "process_id": process_id,
            "status": "error",
            "message": analysis.progress_message or "❌ Erro no processamento",
            "result": None
        }
    
    return {
        "process_id": process_id,
        "status": analysis.status,
        "progress": analysis.progress or 0,
        "message": analysis.progress_message or ""
    }


# ==============================================
# 🔥🔥🔥 ROTA PRINCIPAL: UPLOAD MÚLTIPLO (V12.7 - NÃO BLOQUEIA)
# ==============================================

@router.post("/upload-multi-analyze")
async def upload_multi_analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(..., description="Arquivos para análise (máx 3)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    report_format: str = Form("html", description="Formato do relatório: html, pdf, json"),
    callback_url: Optional[str] = Form(None, description="URL para callback após conclusão"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 UPLOAD MÚLTIPLO COM POLLING (VERSÃO 12.7)
    
    ✅ RETORNA process_id IMEDIATAMENTE
    ✅ FRONTEND FAZ POLLING para acompanhar progresso
    ✅ PROCESSAMENTO ML EM BACKGROUND (MESMO SEM CRÉDITOS)
    ✅ 🔥 NÃO BLOQUEIA POR FALTA DE CRÉDITOS
    ✅ 🔥 CRÉDITOS CONSUMIDOS AUTOMATICAMENTE QUANDO O ML TERMINA
    ✅ 🔥 SE NÃO TIVER CRÉDITOS, análise fica "pending_credit"
    ✅ VERIFICAÇÃO DE ELEGIBILIDADE INTELIGENTE (INFORMATIVA)
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    
    total_files = len(files)
    
    # ==========================================
    # PASSO 1: VALIDAR QUANTIDADE
    # ==========================================
    
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > UploadConfig.MAX_FILES_MULTI_ANALYZE:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {UploadConfig.MAX_FILES_MULTI_ANALYZE} arquivos por vez. Enviados: {total_files}"
        )
    
    logger.info(f"📚 [MULTI-UPLOAD] {current_user.email} | {total_files} arquivos | IP: {client_ip}")
    
    # ==========================================
    # PASSO 2: RATE LIMIT
    # ==========================================
    
    allowed, count = await _rate_limiter.check_and_increment(current_user.id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Limite de {UploadConfig.RATE_LIMIT_PER_USER} análises por hora excedido.",
                "current_count": count,
                "limit": UploadConfig.RATE_LIMIT_PER_USER,
                "retry_after": UploadConfig.RATE_LIMIT_WINDOW
            }
        )
    
    # ==========================================
    # PASSO 3: 🔥 VERIFICAR CRÉDITOS (V12.7 - NÃO BLOQUEIA)
    # ==========================================
    
    credit_check = check_credits_advanced(db, current_user, UploadConfig.CREDITS_PER_ANALYSIS)
    
    # 🔥 V12.7: NUNCA BLOQUEIA POR FALTA DE CRÉDITOS
    # Apenas registra e informa o frontend
    has_credits = credit_check.get("valid", False)
    will_be_pending = not has_credits and credit_check.get("can_proceed", True)
    
    logger.info(f"💰 [MULTI-UPLOAD] Usuário {current_user.email} - Créditos: {credit_check.get('available', 0)}")
    logger.info(f"💰 [MULTI-UPLOAD] Status: {credit_check.get('status', 'unknown')}")
    
    if not has_credits:
        logger.warning(f"⚠️ [MULTI-UPLOAD] Usuário {current_user.email} SEM CRÉDITOS - análise ficará pendente")
        logger.info(f"📌 [MULTI-UPLOAD] Mensagem: {credit_check.get('message', '')}")
    
    # ==========================================
    # PASSO 4: VALIDAR ARQUIVOS
    # ==========================================
    
    validation_result = await validate_files_advanced(files)
    
    if validation_result["valid_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_files",
                "message": "Nenhum arquivo válido para processar",
                "errors": [
                    {"filename": f.filename, "error": f.error}
                    for f in validation_result["invalid"]
                ]
            }
        )
    
    valid_files = validation_result["valid"]
    invalid_files = validation_result["invalid"]
    
    file_data_list = [
        {
            'content': f.content,
            'filename': f.filename,
            'file_size': f.file_size,
            'encoding': f.detected_encoding,
            'hash': f.hash
        }
        for f in valid_files
    ]
    
    # ==========================================
    # PASSO 5: CRIAR ANÁLISE (V12.7 COM STATUS ADEQUADO)
    # ==========================================
    
    # 🔥 V12.7: Determina o status inicial
    if has_credits:
        initial_status = "processing"
        initial_message = "Arquivos validados. Iniciando análise..."
    else:
        initial_status = "processing"  # 🔥 Começa processing, depois vai para pending_credit
        initial_message = "Arquivos validados. Iniciando análise (crédito será verificado ao final)..."
    
    analysis_record = models.Analysis(
        user_id=current_user.id,
        filename=" | ".join([f.filename for f in valid_files]),
        file_size=sum([f.file_size for f in valid_files]),
        analysis_type=analysis_type,
        status=initial_status,
        progress=10,
        progress_message=initial_message,
        uploaded_at=datetime.now(),
        processed_at=None,
        pow_verified=pow_valid,
        client_ip=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        # 🔥 V12.7: Campos de crédito
        credits_consumed=False,
        credits_consumed_at=None,
        credits_consumed_amount=0,
        credits_remaining_after=None,
        credits_error=None,
        credits_needed=UploadConfig.CREDITS_PER_ANALYSIS if not has_credits else 0
    )
    db.add(analysis_record)
    db.commit()
    db.refresh(analysis_record)
    
    process_id = analysis_record.id
    
    logger.info(f"📝 [MULTI-UPLOAD] Análise criada: ID {process_id} para {current_user.email}")
    logger.info(f"💰 [MULTI-UPLOAD] Análise {process_id} - crédito será consumido no final do ML")
    if not has_credits:
        logger.info(f"📌 [MULTI-UPLOAD] Análise {process_id} ficará em 'pending_credit' após processamento")
    
    # ==========================================
    # PASSO 6: INICIAR PROCESSAMENTO EM BACKGROUND
    # ==========================================
    
    background_tasks.add_task(
        process_analysis_background,
        process_id=process_id,
        file_data_list=file_data_list,
        user_id=current_user.id,
        user_email=current_user.email,
        analysis_type=analysis_type,
        db=db
    )
    
    logger.info(f"🚀 [MULTI-UPLOAD] Background task iniciada para análise {process_id}")
    
    # ==========================================
    # PASSO 7: RESPOSTA IMEDIATA (V12.7)
    # ==========================================
    
    credits_before = current_user.credits
    files_uploaded = len(valid_files)
    
    eligibility = get_credit_eligibility(db, current_user)
    
    # 🔥 V12.7: Mensagem personalizada
    if has_credits:
        credit_message = f"1 crédito será consumido automaticamente quando a análise estiver pronta."
        credit_status = "will_be_consumed_when_ready"
    else:
        credit_message = f"💡 Você está sem créditos. A análise será processada, mas os resultados ficarão bloqueados até você assinar Premium ou receber créditos."
        credit_status = "pending_credit_after_processing"
    
    response_data = {
        "success": True,
        "process_id": process_id,
        "status": "processing",
        "progress": 10,
        "message": "Processamento iniciado. O crédito será verificado ao final.",
        "data": {
            "total_files": total_files,
            "valid_files": files_uploaded,
            "invalid_files": len(invalid_files),
            "files": [
                {"filename": f.filename, "size": f.file_size, "valid": True}
                for f in valid_files
            ] + [
                {"filename": f.filename, "error": f.error, "valid": False}
                for f in invalid_files
            ]
        },
        "credits": {
            "before": credits_before,
            "consumed": 0,
            "remaining": credits_before,
            "credits_per_analysis": UploadConfig.CREDITS_PER_ANALYSIS,
            "files_uploaded": files_uploaded,
            "total_cost": UploadConfig.CREDITS_PER_ANALYSIS,
            "status": credit_status,
            "message": credit_message,
            "has_credits": has_credits,
            "will_be_pending": not has_credits,
            "status_detail": credit_check.get("status", "unknown"),
            "suggestion": credit_check.get("suggestion", ""),
            "can_receive_today": credit_check.get("can_receive_today", False)
        },
        "eligibility": {
            "is_premium": eligibility.get("is_premium", False),
            "can_receive_today": eligibility.get("can_receive_today", False),
            "at_max_limit": eligibility.get("at_max_limit", False),
            "received_today": eligibility.get("received_today", False),
            "days_left": eligibility.get("days_left", 0),
            "reason": eligibility.get("reason", "")
        },
        "polling": {
            "url": f"/api/analysis/progress/{process_id}",
            "interval_seconds": 2,
            "max_attempts": 300
        },
        "timestamp": datetime.now().isoformat()
    }
    
    response_headers = {
        "X-Process-Id": str(process_id),
        "X-Status": "processing",
        "X-Credits-Before": str(credits_before),
        "X-Credits-Per-Analysis": str(UploadConfig.CREDITS_PER_ANALYSIS),
        "X-Files-Valid": str(files_uploaded),
        "X-Poll-Url": f"/api/analysis/progress/{process_id}",
        "X-Is-Premium": str(eligibility.get("is_premium", False)),
        "X-Can-Receive-Today": str(eligibility.get("can_receive_today", False)),
        "X-Has-Credits": str(has_credits),
        "X-Will-Be-Pending": str(not has_credits),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    return JSONResponse(
        content=jsonable_encoder(response_data),
        headers=response_headers
    )


# ==============================================
# 🔥 ROTA: HISTÓRICO (V12.7 COM STATUS DE CRÉDITO)
# ==============================================

@router.get("/analyses/history")
async def get_analyses_history(
    request: Request,
    limit: int = Query(3, ge=1, le=UploadConfig.HISTORY_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    start_date: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Buscar por nome do arquivo"),
    sort_by: Optional[str] = Query("uploaded_at", description="Ordenar por: uploaded_at, score, rows"),
    sort_order: Optional[str] = Query("desc", description="asc ou desc"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Retorna histórico de análises com filtros avançados (V12.7)"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"📊 [HISTORY] {current_user.email} | IP: {client_ip} | limit: {limit}, offset: {offset}")
        
        query = db.query(models.Analysis).filter(
            models.Analysis.user_id == current_user.id
        )
        
        if status:
            query = query.filter(models.Analysis.status == status)
        
        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(models.Analysis.uploaded_at >= start)
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(models.Analysis.uploaded_at < end)
            except ValueError:
                pass
        
        if search:
            query = query.filter(
                models.Analysis.filename.ilike(f"%{search}%")
            )
        
        if sort_by == "score":
            order_col = models.Analysis.confidence_score
        elif sort_by == "rows":
            order_col = models.Analysis.rows_processed
        else:
            order_col = models.Analysis.uploaded_at
        
        if sort_order == "asc":
            query = query.order_by(order_col.asc())
        else:
            query = query.order_by(order_col.desc())
        
        total = query.count()
        analyses = query.offset(offset).limit(limit).all()
        
        result = []
        for analysis in analyses:
            predictions = analysis.predictions_summary or {}
            result.append({
                "id": analysis.id,
                "process_id": str(analysis.id),
                "filename": analysis.filename,
                "file_size": analysis.file_size,
                "file_size_formatted": f"{analysis.file_size/1024:.1f}KB" if analysis.file_size else "0KB",
                "uploaded_at": analysis.uploaded_at.isoformat() if analysis.uploaded_at else None,
                "uploaded_at_formatted": analysis.uploaded_at.strftime("%d/%m/%Y %H:%M") if analysis.uploaded_at else None,
                "status": analysis.status,
                "status_label": UploadConfig.STATUS_LABELS.get(analysis.status, analysis.status),
                "status_color": UploadConfig.STATUS_COLORS.get(analysis.status, "#a0aec0"),
                "rows_processed": analysis.rows_processed or 0,
                "model_used": analysis.model_used or "AutoML",
                "analysis_type": analysis.analysis_type or "auto",
                "chart_data": analysis.chart_data or {},
                "predictions_summary": predictions,
                "insights": analysis.insights or {},
                "recommendations": analysis.recommendations or [],
                "processed_at": analysis.processed_at.isoformat() if analysis.processed_at else None,
                "score": float(predictions.get('mean_prediction', 0)),
                "high_risk": float(predictions.get('high_risk_percentage', 0)),
                "low_risk": float(predictions.get('low_risk_percentage', 0)),
                "processing_time_ms": analysis.processing_time_ms,
                "pow_verified": analysis.pow_verified,
                # 🔥 V12.7: Status de créditos
                "credits_consumed": analysis.credits_consumed if hasattr(analysis, 'credits_consumed') else False,
                "credits_consumed_at": analysis.credits_consumed_at.isoformat() if hasattr(analysis, 'credits_consumed_at') and analysis.credits_consumed_at else None,
                "credits_remaining_after": analysis.credits_remaining_after if hasattr(analysis, 'credits_remaining_after') else None,
                "credits_error": analysis.credits_error if hasattr(analysis, 'credits_error') else None,
                "credits_needed": analysis.credits_needed if hasattr(analysis, 'credits_needed') else 0,
                "can_retry": analysis.status == "pending_credit"
            })
        
        return jsonable_encoder({
            "success": True,
            "analyses": result,
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {
                "status": status,
                "start_date": start_date,
                "end_date": end_date,
                "search": search,
                "sort_by": sort_by,
                "sort_order": sort_order
            },
            "credits_per_analysis": UploadConfig.CREDITS_PER_ANALYSIS
        })
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar histórico: {e}")
        return jsonable_encoder({
            "success": False,
            "error": str(e),
            "analyses": [],
            "total": 0
        })


# ==============================================
# 🔥 ROTA: RESULTADO DA ANÁLISE (V12.7)
# ==============================================

@router.get("/analysis/result/{analysis_id}")
async def get_analysis_result(
    analysis_id: int,
    include_predictions: bool = Query(False, description="Incluir predições detalhadas"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Busca resultado completo de uma análise (V12.7)"""
    try:
        analysis = db.query(models.Analysis).filter(
            models.Analysis.id == analysis_id,
            models.Analysis.user_id == current_user.id
        ).first()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Análise não encontrada")
        
        if analysis.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Acesso negado")
        
        # 🔥 V12.7: Se estiver pending_credit, retorna erro informativo
        if analysis.status == "pending_credit":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "pending_credit",
                    "message": "💡 Esta análise está aguardando créditos. Assine Premium ou receba crédito diário.",
                    "credits_needed": UploadConfig.CREDITS_PER_ANALYSIS,
                    "retry_url": f"/api/analysis/retry-credit/{analysis_id}",
                    "can_receive_credit": current_user.is_premium() and current_user.credits < MAX_CREDITS_PREMIUM
                }
            )
        
        predictions_summary = analysis.predictions_summary or {}
        
        result = {
            "success": True,
            "id": analysis.id,
            "filename": analysis.filename,
            "file_size": analysis.file_size,
            "file_size_formatted": f"{analysis.file_size/1024:.1f}KB" if analysis.file_size else "0KB",
            "status": analysis.status,
            "status_label": UploadConfig.STATUS_LABELS.get(analysis.status, analysis.status),
            "status_color": UploadConfig.STATUS_COLORS.get(analysis.status, "#a0aec0"),
            "rows_processed": analysis.rows_processed or 0,
            "model_used": analysis.model_used or "AutoML",
            "analysis_type": analysis.analysis_type or "auto",
            "uploaded_at": analysis.uploaded_at.isoformat() if analysis.uploaded_at else None,
            "processed_at": analysis.processed_at.isoformat() if analysis.processed_at else None,
            "encoding_used": analysis.encoding_used,
            "pow_verified": analysis.pow_verified,
            "client_ip": analysis.client_ip,
            "chart_data": analysis.chart_data or {},
            "insights": analysis.insights or {},
            "recommendations": analysis.recommendations or [],
            "ai_report": analysis.ai_report or "",
            "created_at": analysis.uploaded_at.isoformat() if analysis.uploaded_at else None,
            "updated_at": analysis.processed_at.isoformat() if analysis.processed_at else None,
            "processing_time_ms": analysis.processing_time_ms,
            "total_rows": analysis.total_rows,
            "total_columns": analysis.total_columns,
            "numeric_columns": analysis.numeric_columns,
            "categorical_columns": analysis.categorical_columns,
            "confidence_score": float(analysis.confidence_score) if analysis.confidence_score else 0,
            "metrics": {
                "mean": float(predictions_summary.get("mean_prediction", 0)),
                "std": float(predictions_summary.get("std_prediction", 0)),
                "min": float(predictions_summary.get("min_prediction", 0)),
                "max": float(predictions_summary.get("max_prediction", 0)),
                "high_risk_percentage": float(predictions_summary.get("high_risk_percentage", 0)),
                "medium_risk_percentage": float(predictions_summary.get("medium_risk_percentage", 0)),
                "low_risk_percentage": float(predictions_summary.get("low_risk_percentage", 0)),
                "total_predictions": int(predictions_summary.get("total_predictions", 0))
            },
            # 🔥 V12.7: Status de créditos
            "credits": {
                "consumed": analysis.credits_consumed if hasattr(analysis, 'credits_consumed') else False,
                "consumed_at": analysis.credits_consumed_at.isoformat() if hasattr(analysis, 'credits_consumed_at') and analysis.credits_consumed_at else None,
                "amount_consumed": analysis.credits_consumed_amount if hasattr(analysis, 'credits_consumed_amount') else 0,
                "remaining_after": analysis.credits_remaining_after if hasattr(analysis, 'credits_remaining_after') else None,
                "credits_needed": UploadConfig.CREDITS_PER_ANALYSIS,
                "error": analysis.credits_error if hasattr(analysis, 'credits_error') else None
            }
        }
        
        if include_predictions and analysis.predictions:
            result["predictions"] = [float(p) for p in analysis.predictions]
        
        return jsonable_encoder(result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar análise {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar análise: {str(e)}")


# ==============================================
# 🔥 ROTA: UPLOAD AUTO (V12.7 - NÃO BLOQUEIA)
# ==============================================

@router.post("/upload-auto")
async def upload_auto_optimized(
    request: Request,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(..., description="Arquivos para upload (máx 5)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 UPLOAD ÚNICO - Versão otimizada (V12.7)
    🔥 NÃO BLOQUEIA POR FALTA DE CRÉDITOS
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    total_files = len(files)
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > UploadConfig.MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {UploadConfig.MAX_FILES_PER_BATCH} arquivos por vez"
        )
    
    logger.info(f"📤 [UPLOAD] {current_user.email} | {total_files} arquivos | IP: {client_ip}")
    
    # 🔥 V12.7: Verifica créditos (NÃO BLOQUEIA)
    credit_check = check_credits_advanced(db, current_user, UploadConfig.CREDITS_PER_ANALYSIS)
    
    has_credits = credit_check.get("valid", False)
    
    if not has_credits:
        logger.warning(f"⚠️ [UPLOAD] Usuário {current_user.email} SEM CRÉDITOS")
        logger.info(f"📌 [UPLOAD] Mensagem: {credit_check.get('message', '')}")
    
    validation_result = await validate_files_advanced(files)
    
    if validation_result["valid_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_files",
                "message": "Nenhum arquivo válido",
                "errors": [
                    {"filename": f.filename, "error": f.error}
                    for f in validation_result["invalid"]
                ]
            }
        )
    
    # 🔥 V12.7: NÃO CONSOLE CRÉDITOS AQUI
    eligibility = get_credit_eligibility(db, current_user)
    
    response_data = {
        "success": True,
        "message": f"Processado {validation_result['valid_count']} de {total_files} arquivo(s)",
        "data": {
            "valid_files": [{"filename": f.filename, "size": f.file_size} for f in validation_result["valid"]],
            "invalid_files": [{"filename": f.filename, "error": f.error} for f in validation_result["invalid"]]
        },
        "credits": {
            "before": current_user.credits if not current_user.is_admin else "∞",
            "consumed": 0,
            "remaining": current_user.credits if not current_user.is_admin else "∞",
            "display": crud.get_credits_display(current_user) if hasattr(crud, 'get_credits_display') else str(current_user.credits or 0),
            "credits_per_analysis": UploadConfig.CREDITS_PER_ANALYSIS,
            "files_uploaded": validation_result["valid_count"],
            "total_cost": UploadConfig.CREDITS_PER_ANALYSIS,
            "status": "will_be_consumed_when_ready" if has_credits else "pending_credit_after_processing",
            "message": "1 crédito será consumido automaticamente quando a análise estiver pronta." if has_credits else "💡 Você está sem créditos. A análise será processada, mas os resultados ficarão bloqueados até você assinar Premium.",
            "has_credits": has_credits,
            "suggestion": credit_check.get("suggestion", "")
        },
        "eligibility": {
            "is_premium": eligibility.get("is_premium", False),
            "can_receive_today": eligibility.get("can_receive_today", False),
            "at_max_limit": eligibility.get("at_max_limit", False),
            "received_today": eligibility.get("received_today", False),
            "days_left": eligibility.get("days_left", 0)
        },
        "timestamp": datetime.now().isoformat()
    }
    
    return jsonable_encoder(response_data)


# ==============================================
# 🔥 ROTA: REPROCESSAR ANÁLISE COM CRÉDITO PENDENTE (V12.7)
# ==============================================

@router.post("/analysis/retry-credit/{process_id}")
async def retry_analysis_credit(
    process_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 V12.7: Tenta novamente consumir o crédito de uma análise pendente
    """
    analysis = db.query(models.Analysis).filter(
        models.Analysis.id == process_id,
        models.Analysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    if analysis.status != "pending_credit":
        return {
            "success": False,
            "message": f"Análise está com status '{analysis.status}', não precisa de retry."
        }
    
    # Buscar usuário
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Verificar se tem créditos agora
    if user.credits < 1:
        return {
            "success": False,
            "message": "❌ Você ainda não tem créditos. Assine Premium ou receba crédito diário.",
            "credits_needed": UploadConfig.CREDITS_PER_ANALYSIS,
            "can_receive_credit": user.is_premium() and user.credits < MAX_CREDITS_PREMIUM,
            "suggestion": "Assine Premium para receber 1 crédito por dia!"
        }
    
    # Tentar consumir crédito novamente
    credit_success, credit_message = await consume_analysis_credit(db, analysis, user)
    
    if credit_success:
        return {
            "success": True,
            "message": f"✅ Crédito consumido com sucesso! {credit_message}",
            "analysis_id": process_id,
            "status": "completed"
        }
    else:
        return {
            "success": False,
            "message": f"❌ Falha ao consumir crédito: {credit_message}",
            "analysis_id": process_id,
            "status": "pending_credit"
        }


# ==============================================
# 🔥 INICIALIZAÇÃO
# ==============================================

print("=" * 80)
print("🚀 UPLOAD_ROUTES.PY - VERSÃO 12.7 (LÓGICA DE CRÉDITOS FORTALECIDA)")
print("=" * 80)
print(f"   📁 Limites: {UploadConfig.MAX_FILES_PER_BATCH} arquivos, {UploadConfig.MAX_FILE_SIZE//1024}KB cada")
print(f"   🔥 Multi-analyze: até {UploadConfig.MAX_FILES_MULTI_ANALYZE} arquivos")
print(f"   📊 Report Builder: { '✅' if _report_available else '⚠️ Fallback'}")
print(f"   🤖 ML Pipeline: { '✅' if _ml_available else '⚠️ Fallback'}")
print(f"   🔧 Preprocessing: { '✅' if _preprocessing_available else '⚠️ Fallback'}")
print(f"   🚦 Rate Limit: {UploadConfig.RATE_LIMIT_PER_USER} req/hora")
print(f"   ⏱️ Timeout: {UploadConfig.PROCESSING_TIMEOUT_SECONDS}s")
print(f"")
print(f"   🔥 CORREÇÃO V12.7 (LÓGICA FORTALECIDA):")
print(f"      - ✅ NÃO BLOQUEIA UPLOAD por falta de créditos")
print(f"      - ✅ CRIA ANÁLISE MESMO SEM CRÉDITOS")
print(f"      - ✅ PROCESSAMENTO ML CONTINUA MESMO SEM CRÉDITOS")
print(f"      - ✅ SE NÃO TIVER CRÉDITOS, análise fica 'pending_credit'")
print(f"      - ✅ USUÁRIO PODE ASSINAR PREMIUM E LIBERAR ANÁLISE")
print(f"      - ✅ ROTA /analysis/retry-credit/{id} para liberar")
print(f"")
print(f"   ✅ MANTIDO V12.6:")
print(f"      - ✅ CRÉDITO CONSUMIDO AUTOMATICAMENTE quando o ML termina")
print(f"      - ✅ NÃO CONSUME no upload (apenas verifica)")
print(f"      - ✅ NÃO CONSUME no PDF (já foi consumido)")
print(f"      - ✅ 1 análise = 1 crédito")
print("=" * 80)