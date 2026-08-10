# backend/api/upload_routes.py - VERSÃO 12.1 (COM POLLING E PROGRESSO)
"""
🚀 ROTAS DE UPLOAD - VERSÃO 12.1
================================================================================
✅ NOVIDADES v12.1:
   - 🔥 RESPOSTA IMEDIATA: Retorna process_id sem esperar o ML
   - 🔥 POLLING: Rota /analysis/progress/{id} para acompanhamento
   - 🔥 BACKGROUND: Processamento ML em background com atualização de progresso
   - 🔥 PROGRESSO: Salva progress (0-100) e progress_message no banco
   - 🔥 FEEDBACK: Frontend pode mostrar barra de progresso em tempo real

✅ MANTIDO v12.0:
   - 🔥 REFATORAÇÃO: consume_credits_advanced() aceita amount (int)
   - 🔥 HEADERS: X-Credits-* para sincronização com frontend
   - 🔥 RESPOSTA: credits_per_file, files_uploaded, total_cost
   - 🔥 CACHE: Headers no-cache para evitar dados desatualizados
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
    async def analyze_multiple_files(files, user_id=None, user_email=None, force_reload=False):
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

try:
    from backend.ml.report_builder import report_builder, ReportFormat, build_executive_report
    _report_available = True
    logger.info("✅ report_builder carregado")
except ImportError as e:
    logger.warning(f"⚠️ report_builder não disponível: {e}")
    class ReportFormat(str, Enum):
        HTML = "html"
        PDF = "pdf"
        JSON = "json"
    
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
    PROCESSING_TIMEOUT_SECONDS = 500  # 5 minutos
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
    
    # Créditos
    MAX_CREDITS_PREMIUM = 3
    INITIAL_FREE_CREDITS = 3
    CREDITS_PER_FILE = 1
    
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
# 🔥 FUNÇÕES DE CRÉDITOS (VERSÃO 12.0 - REFATORADA)
# ==============================================

def get_user_credits_info(db: Session, user: models.User) -> Dict[str, Any]:
    """
    🔥 Retorna informações completas de créditos do usuário
    """
    user_refresh = db.query(models.User).filter(models.User.id == user.id).first()
    if not user_refresh:
        return {
            "balance": 0,
            "display": "0",
            "is_premium": False,
            "is_admin": False,
            "max_credits": None,
            "days_left_premium": 0
        }
    
    is_premium = user_refresh.is_premium() if hasattr(user_refresh, 'is_premium') else False
    days_left = user_refresh.get_premium_days_left() if hasattr(user_refresh, 'get_premium_days_left') else 0
    
    return {
        "balance": int(user_refresh.credits) if user_refresh.credits else 0,
        "display": crud.get_credits_display(user_refresh) if hasattr(crud, 'get_credits_display') else str(user_refresh.credits or 0),
        "is_premium": is_premium,
        "is_admin": user_refresh.is_admin or False,
        "max_credits": UploadConfig.MAX_CREDITS_PREMIUM if is_premium else None,
        "days_left_premium": days_left if is_premium else 0,
        "can_receive_daily": False
    }


def check_credits_advanced(db: Session, user: models.User, required: int) -> Dict[str, Any]:
    """
    🔥 Verifica créditos com refresh da sessão e integração com crud
    """
    if user.is_admin:
        return {
            "valid": True,
            "message": "👑 Admin - créditos ilimitados",
            "available": "∞",
            "required": 0,
            "is_admin": True,
            "is_premium": True,
            "remaining_after": "∞"
        }
    
    # Buscar usuário atualizado da sessão
    user_refresh = db.query(models.User).filter(models.User.id == user.id).first()
    if not user_refresh:
        return {
            "valid": False,
            "message": "Usuário não encontrado",
            "available": 0,
            "required": required,
            "is_admin": False,
            "is_premium": False,
            "remaining_after": 0
        }
    
    is_premium = user_refresh.is_premium() if hasattr(user_refresh, 'is_premium') else False
    current_credits = user_refresh.credits or 0
    
    if current_credits < required:
        return {
            "valid": False,
            "message": f"Créditos insuficientes. Você tem {current_credits}, precisa de {required}.",
            "available": current_credits,
            "required": required,
            "is_admin": False,
            "is_premium": is_premium,
            "suggestion": "Adquira o plano Premium para receber 3 créditos por dia." if not is_premium else "Aguarde a renovação diária dos créditos.",
            "remaining_after": 0
        }
    
    return {
        "valid": True,
        "message": f"✅ Créditos suficientes: {current_credits}",
        "available": current_credits,
        "required": required,
        "is_admin": False,
        "is_premium": is_premium,
        "remaining_after": current_credits - required
    }


def consume_credits_advanced(
    db: Session, 
    user: models.User, 
    amount: int = 1,
    description: str = "Upload"
) -> Dict[str, Any]:
    """
    🔥 V12.0: Consome créditos usando crud.deduct_credits()
    """
    
    if user.is_admin:
        return {
            "success": True,
            "message": "👑 Admin - créditos ilimitados",
            "consumed": 0,
            "remaining": "∞",
            "is_admin": True
        }
    
    try:
        # Buscar usuário novamente dentro da sessão atual
        user_refresh = db.query(models.User).filter(models.User.id == user.id).first()
        
        if not user_refresh:
            logger.error(f"❌ Usuário {user.id} não encontrado na sessão")
            return {
                "success": False,
                "message": "Usuário não encontrado na sessão",
                "consumed": 0,
                "remaining": 0,
                "is_admin": False
            }
        
        credits_before = user_refresh.credits
        
        # Verificar se tem créditos suficientes
        if user_refresh.credits < amount:
            logger.warning(f"⚠️ Créditos insuficientes: {user_refresh.credits} < {amount}")
            return {
                "success": False,
                "message": f"Créditos insuficientes. Você tem {user_refresh.credits}, precisa de {amount}.",
                "consumed": 0,
                "remaining": user_refresh.credits,
                "is_admin": False,
                "needed": amount
            }
        
        # 🔥 CONSUME A QUANTIDADE ESPECIFICADA
        success = crud.deduct_credits(db, user_refresh, amount, description)
        
        if not success:
            db.rollback()
            return {
                "success": False,
                "message": "Falha ao consumir créditos",
                "consumed": 0,
                "remaining": user_refresh.credits,
                "is_admin": False
            }
        
        db.commit()
        db.refresh(user_refresh)
        
        # Atualizar o objeto original com os novos dados
        user.credits = user_refresh.credits
        
        # Obter display formatado
        display = crud.get_credits_display(user_refresh) if hasattr(crud, 'get_credits_display') else str(user_refresh.credits or 0)
        
        logger.info(f"💰 {amount} crédito(s) consumido(s) para {user.email}. Saldo: {user_refresh.credits}")
        
        return {
            "success": True,
            "message": f"✅ {amount} crédito(s) consumido(s)",
            "consumed": amount,
            "remaining": user_refresh.credits,
            "before": credits_before,
            "is_admin": False,
            "display": display
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro ao consumir créditos: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Erro ao consumir créditos: {str(e)}",
            "consumed": 0,
            "remaining": user.credits if user else 0,
            "error": str(e),
            "is_admin": False
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
    """Retorna estatísticas avançadas do usuário"""
    
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
    
    return {
        "total_analyses": total_analyses,
        "today_analyses": today_analyses,
        "status_counts": status_counts,
        "total_rows_processed": total_rows,
        "average_score": avg_score,
        "avg_processing_time_ms": round(avg_processing_time, 0) if avg_processing_time else 0,
        "last_analysis_at": last_analysis.uploaded_at.isoformat() if last_analysis and last_analysis.uploaded_at else None,
        "last_analysis_filename": last_analysis.filename if last_analysis else None
    }


# ==============================================
# 🔥🔥🔥 FUNÇÃO DE PROCESSAMENTO EM BACKGROUND (CORRIGIDA)
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
    🔥 PROCESSAMENTO EM BACKGROUND
    Executa o ML e atualiza o progresso no banco de dados
    """
    try:
        logger.info(f"🔄 [BACKGROUND] Iniciando processamento {process_id}")
        
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
        # 🔥🔥🔥 4. EXECUTAR ANÁLISE ML (CORRIGIDO)
        # ==========================================
        
        analysis_result = await analyze_multiple_files(
            files=file_data_list,
            user_id=user_id,
            user_email=user_email,
            force_reload=False,
            db_session=db,           # 🔥 NOVO: Passa a sessão do banco
            process_id=process_id     # 🔥 NOVO: Passa o ID da análise
        )
        
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
        # 7. SALVAR RESULTADOS
        # ==========================================
        
        # Extrair dados do resultado
        chart_data = analysis_result.get('chart_data', {})
        executive_score = analysis_result.get('executive_score', {})
        executive_summary = analysis_result.get('executive_summary', '')
        recommendations = analysis_result.get('recommendations', [])
        avg_score = analysis_result.get('avg_score', 0)
        general_conclusion = analysis_result.get('general_conclusion', '')
        processed_files = analysis_result.get('processed_files', 0)
        
        # Atualizar análise
        analysis.status = "completed"
        analysis.progress = 100
        analysis.progress_message = "Análise concluída com sucesso!"
        analysis.processed_at = datetime.now()
        analysis.rows_processed = processed_files
        analysis.chart_data = chart_data
        analysis.insights = executive_summary
        analysis.recommendations = recommendations
        analysis.confidence_score = avg_score
        analysis.ai_report = general_conclusion
        analysis.processing_time_ms = int((datetime.now() - analysis.uploaded_at).total_seconds() * 1000)
        
        # Salvar executive_score se disponível
        if executive_score:
            analysis.executive_score = executive_score
        
        db.commit()
        
        # ==========================================
        # 8. CONSUMIR CRÉDITOS
        # ==========================================
        
        # Buscar usuário para consumir créditos
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            credit_result = consume_credits_advanced(
                db=db,
                user=user,
                amount=len(file_data_list),
                description=f"Análise de {len(file_data_list)} arquivo(s)"
            )
            
            if credit_result["success"]:
                logger.info(f"💰 [BACKGROUND] {len(file_data_list)} crédito(s) consumidos")
            else:
                logger.warning(f"⚠️ [BACKGROUND] Falha ao consumir créditos: {credit_result.get('message')}")
        
        # ==========================================
        # 9. FINALIZAR
        # ==========================================
        
        logger.info(f"✅ [BACKGROUND] Processamento {process_id} concluído com sucesso")
        
    except Exception as e:
        logger.error(f"❌ [BACKGROUND] Erro no processamento {process_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Atualizar status de erro
        analysis = db.query(models.Analysis).filter(models.Analysis.id == process_id).first()
        if analysis:
            analysis.status = "error"
            analysis.progress_message = f"Erro: {str(e)[:200]}"
            db.commit()


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
    🔥 Retorna status detalhado de créditos e análises do usuário
    """
    try:
        # Buscar usuário atualizado
        user = db.query(models.User).filter(models.User.id == current_user.id).first()
        if not user:
            return jsonable_encoder({
                "success": False,
                "error": "Usuário não encontrado"
            })
        
        # Estatísticas
        stats = get_user_stats_advanced(db, user.id)
        credits_info = get_user_credits_info(db, user)
        
        return jsonable_encoder({
            "success": True,
            "credits": credits_info,
            "analyses": stats,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name
            }
        })
    except Exception as e:
        logger.error(f"❌ Erro ao buscar status de créditos: {e}")
        return jsonable_encoder({
            "success": False,
            "error": str(e)
        })


# ==============================================
# 🔥🔥🔥 ROTA NOVA: PROGRESSO DA ANÁLISE (POLLING)
# ==============================================

@router.get("/analysis/progress/{process_id}")
async def get_analysis_progress(
    process_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 CONSULTA PROGRESSO DA ANÁLISE
    Frontend usa para mostrar barra de progresso em tempo real
    """
    analysis = db.query(models.Analysis).filter(
        models.Analysis.id == process_id,
        models.Analysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    # 🔥 SE JÁ CONCLUÍDA, RETORNAR RESULTADOS COMPLETOS
    if analysis.status == "completed":
        return {
            "process_id": process_id,
            "status": "completed",
            "progress": 100,
            "message": "Concluído!",
            "result": {
                "chart_data": analysis.chart_data or {},
                "executive_score": analysis.executive_score or {},
                "executive_summary": analysis.insights or "",
                "recommendations": analysis.recommendations or [],
                "confidence_score": analysis.confidence_score or 0,
                "rows_processed": analysis.rows_processed or 0,
                "processing_time_ms": analysis.processing_time_ms or 0
            }
        }
    
    # 🔥 SE EM PROCESSAMENTO, RETORNAR PROGRESSO
    if analysis.status == "processing":
        return {
            "process_id": process_id,
            "status": "processing",
            "progress": analysis.progress or 0,
            "message": analysis.progress_message or "Processando...",
            "result": None
        }
    
    # 🔥 SE ERRO
    if analysis.status == "error":
        return {
            "process_id": process_id,
            "status": "error",
            "message": analysis.progress_message or "Erro no processamento",
            "result": None
        }
    
    # 🔥 FALLBACK: Outros status
    return {
        "process_id": process_id,
        "status": analysis.status,
        "progress": analysis.progress or 0,
        "message": analysis.progress_message or ""
    }


# ==============================================
# 🔥🔥🔥 ROTA PRINCIPAL MODIFICADA: UPLOAD MÚLTIPLO (VERSÃO 12.1)
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
    🔥 UPLOAD MÚLTIPLO COM POLLING (VERSÃO 12.1)
    
    ✅ RETORNA process_id IMEDIATAMENTE
    ✅ FRONTEND FAZ POLLING para acompanhar progresso
    ✅ PROCESSAMENTO ML EM BACKGROUND
    ✅ CRÉDITOS CONSUMIDOS APÓS CONCLUSÃO
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
    # PASSO 3: VALIDAR CRÉDITOS (1 POR ARQUIVO)
    # ==========================================
    
    credit_check = check_credits_advanced(db, current_user, total_files)
    if not credit_check["valid"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check["message"],
                "credits_available": credit_check["available"],
                "credits_needed": credit_check["required"],
                "suggestion": credit_check.get("suggestion"),
                "files_uploaded": total_files,
                "credits_per_file": UploadConfig.CREDITS_PER_FILE
            }
        )
    
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
    
    # Preparar dados para o multi_analysis
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
    # 🔥🔥🔥 PASSO 5: CRIAR ANÁLISE COM STATUS "processing"
    # ==========================================
    
    analysis_record = models.Analysis(
        user_id=current_user.id,
        filename=" | ".join([f.filename for f in valid_files]),
        file_size=sum([f.file_size for f in valid_files]),
        analysis_type=analysis_type,
        status="processing",
        progress=10,
        progress_message="Arquivos validados. Iniciando análise...",
        uploaded_at=datetime.now(),
        processed_at=None,
        pow_verified=pow_valid,
        client_ip=client_ip,
        user_agent=user_agent[:255] if user_agent else None
    )
    db.add(analysis_record)
    db.commit()
    db.refresh(analysis_record)
    
    process_id = analysis_record.id  # 🔥 ID para polling
    
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
    
    # ==========================================
    # PASSO 7: RESPOSTA IMEDIATA (SEM ESPERAR ML)
    # ==========================================
    
    # 🔥 Calcular créditos (ainda não consumidos)
    credits_before = current_user.credits
    files_uploaded = len(valid_files)
    credits_per_file = UploadConfig.CREDITS_PER_FILE
    total_cost = files_uploaded * credits_per_file
    
    response_data = {
        "success": True,
        "process_id": process_id,
        "status": "processing",
        "progress": 10,
        "message": "Processamento iniciado. Use /analysis/progress/{id} para acompanhar.",
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
            "consumed": 0,  # 🔥 Será consumido após conclusão
            "remaining": credits_before,
            "credits_per_file": credits_per_file,
            "files_uploaded": files_uploaded,
            "total_cost": total_cost,
            "status": "pending_consumption"
        },
        "polling": {
            "url": f"/api/analysis/progress/{process_id}",
            "interval_seconds": 2,
            "max_attempts": 60
        },
        "timestamp": datetime.now().isoformat()
    }
    
    # 🔥 HEADERS PARA SINCRONIZAÇÃO
    response_headers = {
        "X-Process-Id": str(process_id),
        "X-Status": "processing",
        "X-Credits-Before": str(credits_before),
        "X-Files-Valid": str(files_uploaded),
        "X-Poll-Url": f"/api/analysis/progress/{process_id}",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    return JSONResponse(
        content=jsonable_encoder(response_data),
        headers=response_headers
    )


# ==============================================
# 🔥 FUNÇÕES AUXILIARES (MANTIDAS)
# ==============================================

async def process_with_multi_analysis_advanced(
    file_data_list: List[Dict[str, Any]],
    user_id: int,
    user_email: str,
    timeout: int = UploadConfig.PROCESSING_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """Processa múltiplos arquivos com timeout e fallback"""
    logger.info(f"📚 Processando {len(file_data_list)} arquivos com multi_analysis...")
    
    if not _ml_available:
        logger.warning("⚠️ ML não disponível, usando fallback")
        return {
            "success": True,
            "total_files": len(file_data_list),
            "processed_files": len(file_data_list),
            "failed_files": 0,
            "files": [
                {
                    "filename": f.get("filename", "unknown"),
                    "success": True,
                    "processed_rows": 0,
                    "metrics": {"mean_prediction": 0.65},
                    "chart_data": {"weekly": {"revenue": [1000] * 7}},
                    "insights": {},
                    "recommendations": []
                }
                for f in file_data_list
            ],
            "executive_score": {"nota_geral": 7.0},
            "executive_summary": "Análise concluída (modo fallback).",
            "recommendations": [],
            "chart_data": {"weekly": {"revenue": [1000] * 7, "costs": [300] * 7}},
            "error": None
        }
    
    try:
        result = await asyncio.wait_for(
            analyze_multiple_files(
                files=file_data_list,
                user_id=user_id,
                user_email=user_email,
                force_reload=False
            ),
            timeout=timeout
        )
        
        logger.info(f"✅ Análise multi_analysis concluída: {result.get('processed_files', 0)} arquivos processados")
        return result
        
    except asyncio.TimeoutError:
        logger.error(f"❌ Timeout na análise ({timeout}s)")
        return {
            "success": False,
            "error": f"Timeout: análise excedeu {timeout} segundos",
            "total_files": len(file_data_list),
            "processed_files": 0,
            "failed_files": len(file_data_list),
            "files": [],
            "executive_score": {},
            "executive_summary": "",
            "recommendations": [],
            "chart_data": {}
        }
    except Exception as e:
        logger.error(f"❌ Erro no multi_analysis: {e}")
        return {
            "success": False,
            "error": str(e),
            "total_files": len(file_data_list),
            "processed_files": 0,
            "failed_files": len(file_data_list),
            "files": [],
            "executive_score": {},
            "executive_summary": "",
            "recommendations": [],
            "chart_data": {}
        }


def generate_report_advanced(
    analysis_result: Dict[str, Any],
    user_name: str,
    format: str = "html"
) -> Dict[str, Any]:
    """Gera relatório executivo com fallback"""
    logger.info(f"📄 Gerando relatório em {format}...")
    
    if not _report_available:
        logger.warning("⚠️ Report builder não disponível, usando fallback")
        content = f"""
        <html>
        <head><title>Relatório Executivo</title></head>
        <body>
            <h1>📊 Relatório Executivo</h1>
            <p>Usuário: {user_name}</p>
            <p>Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
            <pre>{json.dumps(analysis_result, indent=2, ensure_ascii=False, default=str)[:1000]}</pre>
        </body>
        </html>
        """
        return {
            "content": content,
            "content_type": "text/html",
            "extension": "html",
            "filename": f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        }
    
    try:
        report = build_executive_report(
            analysis_result=analysis_result,
            user_name=user_name
        )
        
        format_map = {
            'html': ('text/html', 'html', report_builder.to_html(report)),
            'pdf': ('application/pdf', 'pdf', report_builder.to_pdf(report)),
            'json': ('application/json', 'json', json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str))
        }
        
        content_type, extension, content = format_map.get(format.lower(), format_map['html'])
        
        return {
            "content": content,
            "content_type": content_type,
            "extension": extension,
            "filename": f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar relatório: {e}")
        return {
            "content": json.dumps({"error": str(e), "analysis": analysis_result}, indent=2, ensure_ascii=False, default=str),
            "content_type": "application/json",
            "extension": "json",
            "filename": f"relatorio_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }


def save_analyses_advanced(
    db: Session,
    user_id: int,
    results: List[Dict[str, Any]],
    analysis_type: str,
    pow_valid: bool,
    client_ip: str,
    user_agent: str = None
) -> List[int]:
    """Salva análises com dados completos"""
    analyses_ids = []
    
    for result in results:
        try:
            metrics = result.get('metrics', {})
            chart_data = result.get('chart_data', {})
            
            analysis = models.Analysis(
                user_id=user_id,
                filename=result.get('filename', 'unknown'),
                file_size=result.get('file_size', 0),
                analysis_type=analysis_type,
                model_used=result.get('model_used', 'default'),
                status="completed" if result.get('success') else "error",
                rows_processed=result.get('processed_rows', 0),
                uploaded_at=datetime.now(),
                processed_at=datetime.now() if result.get('success') else None,
                encoding_used=result.get('encoding_used'),
                pow_verified=pow_valid,
                client_ip=client_ip,
                user_agent=user_agent[:255] if user_agent else None,
                chart_data=chart_data,
                predictions_summary=metrics,
                insights=result.get('insights', {}),
                recommendations=result.get('recommendations', []),
                total_rows=result.get('processed_rows', 0),
                total_columns=metrics.get('total_columns', 0),
                numeric_columns=metrics.get('numeric_columns', 0),
                categorical_columns=metrics.get('categorical_columns', 0),
                confidence_score=float(metrics.get('mean_prediction', 0)) if metrics.get('mean_prediction') else 0
            )
            db.add(analysis)
            db.flush()
            analyses_ids.append(analysis.id)
            
            logger.info(f"✅ Análise salva: ID {analysis.id} - {result.get('filename')}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar análise: {e}")
    
    db.commit()
    logger.info(f"✅ {len(analyses_ids)} análises salvas")
    
    return analyses_ids


async def send_callback(callback_url: str, result: Dict[str, Any]):
    """Envia callback para URL configurada"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(callback_url, json=jsonable_encoder(result), timeout=10) as response:
                if response.status == 200:
                    logger.info(f"✅ Callback enviado com sucesso para {callback_url}")
                else:
                    logger.warning(f"⚠️ Callback retornou status {response.status} para {callback_url}")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar callback: {e}")


# ==============================================
# 🔥 ROTAS LEGADAS (HISTÓRICO E RESULTADO)
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
    """Retorna histórico de análises com filtros avançados"""
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
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar histórico: {e}")
        return jsonable_encoder({
            "success": False,
            "error": str(e),
            "analyses": [],
            "total": 0
        })


@router.get("/analysis/result/{analysis_id}")
async def get_analysis_result(
    analysis_id: int,
    include_predictions: bool = Query(False, description="Incluir predições detalhadas"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Busca resultado completo de uma análise"""
    try:
        analysis = db.query(models.Analysis).filter(
            models.Analysis.id == analysis_id,
            models.Analysis.user_id == current_user.id
        ).first()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Análise não encontrada")
        
        if analysis.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Acesso negado")
        
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


@router.post("/upload-auto")
async def upload_auto_optimized(
    request: Request,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(..., description="Arquivos para upload (máx 5)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """🔥 UPLOAD ÚNICO - Versão otimizada com fallback"""
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
    
    # 🔥 V12.0: Verifica 1 crédito por arquivo
    credit_check = check_credits_advanced(db, current_user, total_files)
    if not credit_check["valid"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check["message"],
                "credits_available": credit_check["available"],
                "credits_needed": credit_check["required"],
                "credits_per_file": UploadConfig.CREDITS_PER_FILE,
                "files_uploaded": total_files
            }
        )
    
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
    
    # 🔥 V12.0: Consome 1 crédito por arquivo válido
    credit_result = consume_credits_advanced(
        db=db,
        user=current_user,
        amount=validation_result["valid_count"],
        description=f"Upload de {validation_result['valid_count']} arquivo(s)"
    )
    
    response_data = {
        "success": True,
        "message": f"Processado {validation_result['valid_count']} de {total_files} arquivo(s)",
        "data": {
            "valid_files": [{"filename": f.filename, "size": f.file_size} for f in validation_result["valid"]],
            "invalid_files": [{"filename": f.filename, "error": f.error} for f in validation_result["invalid"]]
        },
        "credits": {
            "before": current_user.credits if not current_user.is_admin else "∞",
            "consumed": validation_result["valid_count"] if not current_user.is_admin else 0,
            "remaining": current_user.credits - validation_result["valid_count"] if not current_user.is_admin else "∞",
            "display": crud.get_credits_display(current_user) if hasattr(crud, 'get_credits_display') else str(current_user.credits or 0),
            "credits_per_file": UploadConfig.CREDITS_PER_FILE,
            "files_uploaded": validation_result["valid_count"],
            "total_cost": validation_result["valid_count"]
        },
        "timestamp": datetime.now().isoformat()
    }
    
    return jsonable_encoder(response_data)


# ==============================================
# 🔥 INICIALIZAÇÃO
# ==============================================

print("=" * 80)
print("🚀 UPLOAD_ROUTES.PY - VERSÃO 12.1 (COM POLLING E PROGRESSO)")
print("=" * 80)
print(f"   📁 Limites: {UploadConfig.MAX_FILES_PER_BATCH} arquivos, {UploadConfig.MAX_FILE_SIZE//1024}KB cada")
print(f"   🔥 Multi-analyze: até {UploadConfig.MAX_FILES_MULTI_ANALYZE} arquivos")
print(f"   📊 Report Builder: { '✅' if _report_available else '⚠️ Fallback'}")
print(f"   🤖 ML Pipeline: { '✅' if _ml_available else '⚠️ Fallback'}")
print(f"   🔧 Preprocessing: { '✅' if _preprocessing_available else '⚠️ Fallback'}")
print(f"   🚦 Rate Limit: {UploadConfig.RATE_LIMIT_PER_USER} req/hora")
print(f"   ⏱️ Timeout: {UploadConfig.PROCESSING_TIMEOUT_SECONDS}s")
print(f"   💰 Créditos: {UploadConfig.INITIAL_FREE_CREDITS} grátis | máx premium {UploadConfig.MAX_CREDITS_PREMIUM}")
print(f"   📌 Regra: 1 arquivo = 1 crédito = 1 análise")
print(f"")
print(f"   ✅ NOVIDADES V12.1:")
print(f"      - 🔥 RESPOSTA IMEDIATA: Retorna process_id sem esperar o ML")
print(f"      - 🔥 POLLING: Rota /analysis/progress/{id} para acompanhamento")
print(f"      - 🔥 BACKGROUND: Processamento ML em background com atualização de progresso")
print(f"      - 🔥 PROGRESSO: Salva progress (0-100) e progress_message no banco")
print(f"      - 🔥 FEEDBACK: Frontend pode mostrar barra de progresso em tempo real")
print(f"")
print(f"   ✅ MANTIDO V12.0:")
print(f"      - 🔥 REFATORAÇÃO: consume_credits_advanced() aceita amount (int)")
print(f"      - 🔥 HEADERS: X-Credits-* para sincronização com frontend")
print(f"      - 🔥 RESPOSTA: credits_per_file, files_uploaded, total_cost")
print("=" * 80)