# backend/api/upload_routes.py - VERSÃO 13.0 (REFATORADA + CACHE-AWARE)


# ==============================================
# 🔥 IMPORTS
# ==============================================

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form,
    Request, Query, BackgroundTasks
)
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Optional, List, Dict, Any, Tuple
import logging
import os
import hashlib
import asyncio
import time
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal

from backend.database import get_db
from backend import models
from backend import crud
from backend.security import get_current_active_user
from backend.api.pow_routes import validate_pow_request

from backend.crud import (
    get_credit_eligibility,
    MAX_CREDITS_PREMIUM,
    INITIAL_FREE_CREDITS,
    manage_credits_after_consumption,
)

# ==============================================
# 🔥 IMPORTS COM FALLBACK
# ==============================================

logger = logging.getLogger(__name__)

_ml_available = False
_preprocessing_available = False

try:
    from backend.preprocessing import process_file_content, pipeline  # noqa: F401
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

    async def analyze_multiple_files(
        files, user_id=None, user_email=None,
        force_reload=False, db_session=None, process_id=None
    ):
        logger.warning("⚠️ Usando fallback de multi_analysis")
        return {
            "success": True,
            "total_files": len(files),
            "processed_files": len(files),
            "failed_files": 0,
            "files": [{"filename": f.get("filename", "unknown"), "success": True} for f in files],
            "executive_score": {"nota_geral": 7.0},
            "executive_summary": "Análise concluída (modo fallback).",
            "recommendations": [],
            "chart_data": {"weekly": {"revenue": [1000] * 7, "costs": [300] * 7}},
            "error": None,
            "cache_hit": False,
        }


# ==============================================
# 🔥 CONFIGURAÇÃO
# ==============================================

router = APIRouter(tags=["upload"])


class UploadConfig:
    """Configurações centralizadas"""
    # Limites
    MAX_FILE_SIZE = 200 * 1024
    MAX_FILES_PER_BATCH = 5
    MAX_FILES_MULTI_ANALYZE = 3
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv', '.parquet'}

    # Timeouts
    PROCESSING_TIMEOUT_SECONDS = 500
    UPLOAD_TIMEOUT_SECONDS = 60
    CHUNK_SIZE = 8192

    # Rate limit
    RATE_LIMIT_PER_USER = 30
    RATE_LIMIT_WINDOW = 3600

    # Histórico
    HISTORY_PAGE_SIZE = 10

    # Créditos
    CREDITS_PER_FILE = 1
    CREDITS_PER_ANALYSIS = 1  # alias legado

    # Status
    STATUS_LABELS = {
        "pending": "⏳ Pendente",
        "processing": "🔄 Processando",
        "completed": "✅ Concluído",
        "error": "❌ Erro",
        "pending_credit": "💳 Aguardando crédito",
        "cancelled": "🚫 Cancelado",
    }
    STATUS_COLORS = {
        "pending": "#f5a623",
        "processing": "#4a9eff",
        "completed": "#48bb78",
        "error": "#f56565",
        "pending_credit": "#9f7aea",
        "cancelled": "#a0aec0",
    }


# ==============================================
# 🔥 DATACLASSES
# ==============================================

@dataclass
class UploadFileInfo:
    filename: str
    content: bytes
    file_size: int
    file_extension: str
    mime_type: Optional[str] = None
    error: Optional[str] = None
    _hash: Optional[str] = None
    _detected_encoding: Optional[str] = None

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
            except Exception:
                self._detected_encoding = 'utf-8'
        return self._detected_encoding or 'utf-8'


# ==============================================
# 🔥 RATE LIMITER
# ==============================================

class RateLimiter:
    def __init__(self):
        self._requests: Dict[int, List[float]] = {}
        self._lock = asyncio.Lock()

    async def check_and_increment(
        self, user_id: int,
        limit: int = UploadConfig.RATE_LIMIT_PER_USER,
        window: int = UploadConfig.RATE_LIMIT_WINDOW,
    ) -> Tuple[bool, int]:
        async with self._lock:
            now = time.time()
            window_start = now - window
            if user_id not in self._requests:
                self._requests[user_id] = []
            self._requests[user_id] = [t for t in self._requests[user_id] if t > window_start]
            current = len(self._requests[user_id])
            if current >= limit:
                return False, current
            self._requests[user_id].append(now)
            return True, current + 1


_rate_limiter = RateLimiter()


# ==============================================
# 🔥 VALIDAÇÃO DE ARQUIVOS
# ==============================================

def validate_file_advanced(file: UploadFile, idx: int) -> UploadFileInfo:
    if not file.filename:
        return UploadFileInfo(f"arquivo_{idx}", b"", 0, "", error="Arquivo sem nome")

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in UploadConfig.ALLOWED_EXTENSIONS:
        return UploadFileInfo(
            file.filename, b"", 0, file_ext,
            error=f"Formato não suportado. Use: {', '.join(UploadConfig.ALLOWED_EXTENSIONS)}"
        )

    if not re.match(r'^[a-zA-Z0-9_.\- ]+$', file.filename):
        return UploadFileInfo(
            file.filename, b"", 0, file_ext,
            error="Nome do arquivo contém caracteres inválidos"
        )

    try:
        content = bytearray()
        total = 0
        chunk = file.file.read(UploadConfig.CHUNK_SIZE)
        while chunk:
            total += len(chunk)
            if total > UploadConfig.MAX_FILE_SIZE:
                return UploadFileInfo(
                    file.filename, b"", total, file_ext,
                    error=f"Arquivo excede {UploadConfig.MAX_FILE_SIZE // 1024}KB"
                )
            content.extend(chunk)
            chunk = file.file.read(UploadConfig.CHUNK_SIZE)

        if total == 0:
            return UploadFileInfo(file.filename, b"", 0, file_ext, error="Arquivo vazio")

        return UploadFileInfo(
            file.filename, bytes(content), total, file_ext,
            mime_type=file.content_type
        )
    except Exception as e:
        logger.error(f"❌ Erro ao ler {file.filename}: {e}")
        return UploadFileInfo(
            file.filename or f"arquivo_{idx}", b"", 0,
            file_ext if 'file_ext' in locals() else "",
            error=str(e)
        )


async def validate_files_advanced(files: List[UploadFile]) -> Dict[str, Any]:
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    None, validate_file_advanced, file, idx
                )
                for idx, file in enumerate(files)
            ]),
            timeout=UploadConfig.UPLOAD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return {
            "valid": [], "invalid": [],
            "total": len(files), "valid_count": 0,
            "invalid_count": len(files),
            "error": "Timeout na validação",
        }

    valid = [r for r in results if r.is_valid]
    invalid = [r for r in results if not r.is_valid]
    return {
        "valid": valid, "invalid": invalid,
        "total": len(files),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
    }


# ==============================================
# 🔥 SERVIÇO DE CRÉDITOS (REFATORADO)
# ==============================================

class CreditService:
    """
    🔥 Serviço centralizado de créditos com transações atômicas.

    REGRAS:
    - 1 arquivo = 1 crédito
    - Cache hit = 0 créditos
    - Idempotente via analysis.credits_consumed
    - Admin = ilimitado
    """

    @staticmethod
    def check_credits(
        db: Session,
        user: models.User,
        num_files: int,
        *,
        lock: bool = False,
    ) -> Dict[str, Any]:
        """
        Verifica créditos de forma atômica.
        Se lock=True, usa with_for_update() para evitar double-spend.
        """
        required = num_files * UploadConfig.CREDITS_PER_FILE

        # Admin bypass
        if user.is_admin:
            return {
                "can_proceed": True,
                "available": float('inf'),
                "required": required,
                "is_admin": True,
                "is_premium": True,
                "status": "admin",
                "message": f"👑 Admin - {num_files} arquivo(s)",
                "remaining_after": float('inf'),
            }

        # 1 query com lock opcional
        query = db.query(models.User).filter(models.User.id == user.id)
        if lock:
            query = query.with_for_update()
        user_db = query.first()

        if not user_db:
            return {
                "can_proceed": False, "available": 0, "required": required,
                "is_admin": False, "is_premium": False,
                "status": "error", "message": "Usuário não encontrado",
            }

        current = int(user_db.credits or 0)
        is_premium = CreditService._is_premium(user_db)

        if current >= required:
            return {
                "can_proceed": True,
                "available": current,
                "required": required,
                "is_admin": False,
                "is_premium": is_premium,
                "remaining_after": current - required,
                "status": "has_credits",
                "message": f"✅ {current} crédito(s) para {num_files} arquivo(s)",
            }

        missing = required - current
        suggestion = (
            "Aguarde o próximo crédito diário ou compre mais créditos."
            if is_premium
            else "Assine o Premium para receber 1 crédito por dia! 🚀"
        )
        return {
            "can_proceed": False,
            "available": current,
            "required": required,
            "missing": missing,
            "is_admin": False,
            "is_premium": is_premium,
            "remaining_after": 0,
            "status": "insufficient_credits",
            "message": (
                f"❌ Créditos insuficientes para {num_files} arquivo(s). "
                f"Você tem {current}, precisa de {required}."
            ),
            "suggestion": suggestion,
        }

    @staticmethod
    def consume(
        db: Session,
        analysis: models.Analysis,
        user: models.User,
        num_files: int,
        *,
        cache_hit: bool = False,
    ) -> Tuple[bool, str]:
        """
        🔥 V13.0: Consome créditos de forma ATÔMICA e IDEMPOTENTE.

        ⚠️ BUGFIX CRÍTICO:
        - Se cache_hit=True → NÃO consome créditos (0)
        - Se cache_hit=False → Consome N créditos (1 por arquivo)
        """
        if not analysis or not user:
            return False, "Dados inválidos"

        # ==========================================
        # 🔒 IDEMPOTÊNCIA (early return)
        # ==========================================
        if getattr(analysis, 'credits_consumed', False):
            logger.info(
                f"⚠️ [CREDIT-IDEMPOTENT] Análise {analysis.id} já consumiu "
                f"{analysis.credits_consumed_amount} crédito(s). Ignorando."
            )
            return True, f"Já consumido ({analysis.credits_consumed_amount})"

        # ==========================================
        # 👑 ADMIN
        # ==========================================
        if user.is_admin:
            CreditService._mark_consumed(db, analysis, user, 0, cache_hit=False, is_admin=True)
            logger.info(f"👑 [CREDIT-ADMIN] {user.email} - análise {analysis.id}")
            return True, "Admin - créditos ilimitados"

        # ==========================================
        # 📦 CACHE HIT → NÃO CONSOME (BUGFIX V13.0)
        # ==========================================
        if cache_hit:
            CreditService._mark_consumed(
                db, analysis, user, 0,
                cache_hit=True, is_admin=False
            )
            logger.info(
                f"📦 [CREDIT-CACHE-HIT] Análise {analysis.id} veio do cache — "
                f"0 crédito(s) consumido(s). Saldo mantido: {user.credits}"
            )
            return True, f"Resultado do cache — 0 crédito(s). Saldo: {user.credits}"

        # ==========================================
        # 💰 CONSUMO NORMAL
        # ==========================================
        required = num_files * UploadConfig.CREDITS_PER_FILE

        # Lock + recheck para evitar race condition
        user_db = (
            db.query(models.User)
            .filter(models.User.id == user.id)
            .with_for_update()
            .first()
        )
        if not user_db:
            return False, "Usuário não encontrado"

        if (user_db.credits or 0) < required:
            analysis.credits_error = f"Créditos insuficientes: {user_db.credits}/{required}"
            analysis.credits_needed = required
            analysis.status = "pending_credit"
            analysis.progress_message = (
                f"💡 Créditos insuficientes: {user_db.credits}/{required}."
            )
            db.commit()
            logger.warning(
                f"⚠️ [CREDIT-INSUFFICIENT] {user.email}: "
                f"{user_db.credits}/{required} para análise {analysis.id}"
            )
            return False, f"Créditos insuficientes. Precisa de {required}, tem {user_db.credits}."

        try:
            result = manage_credits_after_consumption(
                db=db,
                user=user_db,
                amount=required,
                description=f"Análise {analysis.id} ({num_files} arquivo(s))",
            )

            if not result.get("success"):
                error_msg = result.get("message", "Erro desconhecido")
                logger.error(f"❌ [CREDIT] Falha: {error_msg}")
                analysis.credits_error = error_msg
                analysis.status = "pending_credit"
                analysis.progress_message = f"⚠️ {error_msg[:100]}"
                db.commit()
                return False, error_msg

            db.refresh(user_db)

            CreditService._mark_consumed(
                db, analysis, user_db, required,
                cache_hit=False, is_admin=False
            )

            if result.get("bonus_granted"):
                analysis.credits_bonus_granted = True
                analysis.credits_bonus_amount = result.get("bonus_amount", 0)
                logger.info(f"⭐ [CREDIT-BONUS] +{result.get('bonus_amount')}")

            db.commit()
            logger.info(
                f"💰 [CREDIT-CONSUMED] {required} crédito(s) para análise "
                f"{analysis.id} ({num_files} arquivo(s)). Saldo: {user_db.credits}"
            )
            return True, f"{required} crédito(s) consumido(s). Saldo: {user_db.credits}"

        except Exception as e:
            logger.exception(f"❌ [CREDIT-ERROR] {e}")
            db.rollback()
            analysis.credits_error = str(e)
            analysis.status = "pending_credit"
            analysis.progress_message = f"⚠️ Erro: {str(e)[:100]}"
            db.commit()
            return False, str(e)

    @staticmethod
    def _mark_consumed(
        db: Session,
        analysis: models.Analysis,
        user: models.User,
        amount: int,
        *,
        cache_hit: bool,
        is_admin: bool,
    ) -> None:
        """Marca a análise como consumida (ou cache-hit) atomicamente."""
        analysis.credits_consumed = True
        analysis.credits_consumed_at = datetime.now()
        analysis.credits_consumed_amount = amount
        analysis.credits_remaining_after = (
            None if is_admin else int(user.credits or 0)
        )
        analysis.credits_needed = 0
        analysis.credits_error = None
        analysis.status = "completed"

        if cache_hit:
            analysis.progress_message = (
                f"✅ Análise concluída (cache) — 0 crédito(s). "
                f"Saldo: {user.credits}"
            )
        elif is_admin:
            analysis.progress_message = "✅ Análise concluída (Admin)."
        else:
            analysis.progress_message = (
                f"✅ Análise concluída! {amount} crédito(s) consumido(s). "
                f"Saldo: {user.credits}"
            )

        db.commit()

    @staticmethod
    def _is_premium(user: models.User) -> bool:
        try:
            if hasattr(user, 'is_premium') and callable(user.is_premium):
                return bool(user.is_premium())
            if hasattr(user, 'plan'):
                plan = user.plan
                if hasattr(plan, 'value'):
                    return plan.value == "premium_mensal"
                if hasattr(plan, 'name'):
                    return plan.name == "PREMIUM_MENSAL"
        except Exception:
            pass
        return False


# ==============================================
# 🔥 SERVIÇO DE ANÁLISE
# ==============================================

class AnalysisService:
    """Cria e persiste registros de análise."""

    @staticmethod
    def create_analysis(
        db: Session,
        user: models.User,
        valid_files: List[UploadFileInfo],
        analysis_type: str,
        client_ip: str,
        user_agent: Optional[str],
        pow_valid: bool,
    ) -> models.Analysis:
        analysis = models.Analysis(
            user_id=user.id,
            filename=" | ".join(f.filename for f in valid_files),
            file_size=sum(f.file_size for f in valid_files),
            analysis_type=analysis_type,
            status="processing",
            progress=10,
            progress_message=f"Processando {len(valid_files)} arquivo(s)...",
            uploaded_at=datetime.now(),
            processed_at=None,
            pow_verified=pow_valid,
            client_ip=client_ip,
            user_agent=user_agent[:255] if user_agent else None,
            credits_consumed=False,
            credits_consumed_at=None,
            credits_consumed_amount=0,
            credits_remaining_after=None,
            credits_error=None,
            credits_needed=len(valid_files),
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

    @staticmethod
    async def update_progress(
        db: Session, process_id: int, progress: int, message: str
    ) -> bool:
        try:
            analysis = (
                db.query(models.Analysis)
                .filter(models.Analysis.id == process_id)
                .first()
            )
            if not analysis:
                return False
            analysis.progress = progress
            analysis.progress_message = message
            if progress < 100:
                analysis.status = "processing"
            db.commit()
            logger.info(f"📊 [Progresso] Análise {process_id}: {progress}% - {message}")
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar progresso {process_id}: {e}")
            db.rollback()
            return False

    @staticmethod
    def persist_results(
        db: Session, analysis: models.Analysis, result: Dict[str, Any]
    ) -> None:
        analysis.chart_data = result.get('chart_data', {})
        analysis.insights = result.get('executive_summary', '')
        analysis.recommendations = result.get('recommendations', [])
        analysis.confidence_score = result.get('avg_score', 0)
        analysis.ai_report = result.get('general_conclusion', '')
        analysis.rows_processed = result.get('processed_files', 0)
        analysis.processing_time_ms = int(
            (datetime.now() - analysis.uploaded_at).total_seconds() * 1000
        )
        if result.get('executive_score'):
            analysis.executive_score = result['executive_score']
        db.commit()


# ==============================================
# 🔥 BACKGROUND PROCESSOR (REFATORADO + BUGFIX)
# ==============================================

class BackgroundProcessor:
    """
    🔥 Processa análise em background com BUGFIX de cache.

    FLUXO:
      1. analyze_multiple_files() → result
      2. Detecta cache_hit
      3. Persiste resultados
      4. Se cache_hit → NÃO consome créditos
      5. Se !cache_hit → consome N créditos
    """

    @staticmethod
    async def run(
        process_id: int,
        file_data_list: List[Dict[str, Any]],
        user_id: int,
        user_email: str,
        analysis_type: str,
        num_files: int,
        db: Session,
    ) -> None:
        start = time.time()
        try:
            logger.info(f"🔄 [BG] Iniciando processamento {process_id}")
            logger.info(f"   📁 Arquivos: {num_files} | 👤 {user_email} (ID: {user_id})")

            # ==========================================
            # 1. Progresso: 20%
            # ==========================================
            await AnalysisService.update_progress(
                db, process_id, 20, "Iniciando análise dos dados..."
            )

            # ==========================================
            # 2. Executar ML
            # ==========================================
            await AnalysisService.update_progress(
                db, process_id, 30, "Processando arquivos com IA..."
            )

            logger.info(f"🤖 [BG] Chamando analyze_multiple_files para {process_id}")

            analysis_result = await analyze_multiple_files(
                files=file_data_list,
                user_id=user_id,
                user_email=user_email,
                force_reload=False,
                db_session=db,
                process_id=process_id,
            )

            elapsed = (time.time() - start) * 1000
            logger.info(
                f"✅ [BG] analyze_multiple_files concluído para {process_id} "
                f"em {elapsed:.0f}ms"
            )

            # ==========================================
            # 3. 🔥 DETECTAR CACHE HIT (BUGFIX V13.0)
            # ==========================================
            cache_hit = bool(analysis_result.get('cache_hit', False))
            if cache_hit:
                logger.info(
                    f"📦 [BG] Análise {process_id} veio do CACHE "
                    f"— 0 crédito(s) será(ão) consumido(s)"
                )
            else:
                logger.info(
                    f"🔥 [BG] Análise {process_id} processada pelo ML "
                    f"— {num_files} crédito(s) será(ão) consumido(s)"
                )

            # ==========================================
            # 4. Progresso: 80%
            # ==========================================
            await AnalysisService.update_progress(
                db, process_id, 80, "Gerando relatório e insights..."
            )

            # ==========================================
            # 5. Buscar análise no banco
            # ==========================================
            analysis = (
                db.query(models.Analysis)
                .filter(models.Analysis.id == process_id)
                .first()
            )
            if not analysis:
                logger.error(f"❌ [BG] Análise {process_id} não encontrada")
                return

            # ==========================================
            # 6. Persistir resultados
            # ==========================================
            AnalysisService.persist_results(db, analysis, analysis_result)

            # ==========================================
            # 7. Consumir créditos (com cache-aware)
            # ==========================================
            user = (
                db.query(models.User)
                .filter(models.User.id == user_id)
                .first()
            )
            if not user:
                logger.error(f"❌ [BG] Usuário {user_id} não encontrado")
                analysis.status = "error"
                analysis.progress_message = "❌ Usuário não encontrado"
                db.commit()
                return

            success, message = CreditService.consume(
                db, analysis, user, num_files,
                cache_hit=cache_hit,  # 🔥 BUGFIX
            )

            if success:
                logger.info(f"✅ [BG] Análise {process_id}: {message}")
                if cache_hit:
                    analysis.progress_message = (
                        f"✅ Análise concluída (cache) — 0 crédito(s). "
                        f"Saldo: {user.credits}"
                    )
                else:
                    analysis.progress_message = "✅ Análise concluída! PDF disponível."
            else:
                logger.warning(f"⚠️ [BG] Análise {process_id}: {message}")
                analysis.progress_message = f"💡 {message[:100]}"
                analysis.status = "pending_credit"
                db.commit()
                return

            # ==========================================
            # 8. Finalizar
            # ==========================================
            db.commit()
            logger.info(f"✅ [BG] Processamento {process_id} concluído!")

        except Exception as e:
            logger.exception(f"❌ [BG] Erro no processamento {process_id}: {e}")
            try:
                analysis = (
                    db.query(models.Analysis)
                    .filter(models.Analysis.id == process_id)
                    .first()
                )
                if analysis:
                    analysis.status = "error"
                    analysis.progress_message = f"❌ Erro: {str(e)[:200]}"
                    db.commit()
                    logger.info(f"📊 [BG] Status {process_id} → 'error'")
            except Exception as db_err:
                logger.error(f"❌ [BG] Erro ao atualizar status: {db_err}")


# ==============================================
# 🔥 ROTAS: ESTATÍSTICAS
# ==============================================

@router.get("/analyses/count")
async def get_user_analyses_count_endpoint(
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        total = (
            db.query(models.Analysis)
            .filter(models.Analysis.user_id == current_user.id)
            .count()
        )
        return jsonable_encoder({
            "success": True,
            "total_analyses": total,
            "user_id": current_user.id,
            "email": current_user.email,
        })
    except Exception as e:
        logger.error(f"❌ Erro ao buscar total: {e}")
        return jsonable_encoder({"success": False, "error": str(e), "total_analyses": 0})


@router.get("/analyses/credits")
async def get_user_credits_status(
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        user = db.query(models.User).filter(models.User.id == current_user.id).first()
        if not user:
            return jsonable_encoder({"success": False, "error": "Usuário não encontrado"})

        eligibility = get_credit_eligibility(db, user)
        is_premium = CreditService._is_premium(user)
        days_left = (
            user.get_premium_days_left()
            if hasattr(user, 'get_premium_days_left') else 0
        )

        credits_info = {
            "balance": int(user.credits or 0),
            "display": (
                crud.get_credits_display(user)
                if hasattr(crud, 'get_credits_display')
                else str(user.credits or 0)
            ),
            "is_premium": is_premium,
            "is_admin": bool(user.is_admin),
            "max_credits": MAX_CREDITS_PREMIUM if is_premium else None,
            "days_left_premium": days_left if is_premium else 0,
            "can_receive_today": eligibility.get("can_receive_today", False),
            "at_max_limit": eligibility.get("at_max_limit", False),
            "received_today": eligibility.get("received_today", False),
            "reason": eligibility.get("reason", ""),
            "next_credit_date": eligibility.get("next_credit_date"),
        }

        return jsonable_encoder({
            "success": True,
            "credits": credits_info,
            "user": {
                "id": user.id, "email": user.email, "name": user.name,
                "is_premium": is_premium, "is_admin": bool(user.is_admin),
            },
            "credits_per_file": UploadConfig.CREDITS_PER_FILE,
        })
    except Exception as e:
        logger.error(f"❌ Erro ao buscar créditos: {e}")
        return jsonable_encoder({"success": False, "error": str(e)})


# ==============================================
# 🔥 ROTAS: PROGRESSO
# ==============================================

@router.get("/analysis/progress/{process_id}")
async def get_analysis_progress(
    process_id: int,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    analysis = (
        db.query(models.Analysis)
        .filter(
            models.Analysis.id == process_id,
            models.Analysis.user_id == current_user.id,
        )
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    if analysis.status == "pending_credit":
        return {
            "process_id": process_id,
            "status": "pending_credit",
            "progress": 95,
            "message": "💡 Análise processada! Assine Premium para liberar.",
            "result": None,
            "credits": {
                "needed": getattr(analysis, 'credits_needed', 1),
                "status": "pending",
                "retry_url": f"/api/analysis/retry-credit/{process_id}",
            },
        }

    if analysis.status == "completed":
        return {
            "process_id": process_id,
            "status": "completed",
            "progress": 100,
            "message": "✅ Análise concluída! PDF disponível.",
            "result": {
                "id": analysis.id,
                "filename": analysis.filename,
                "status": analysis.status,
                "rows_processed": analysis.rows_processed or 0,
                "confidence_score": float(analysis.confidence_score or 0),
                "chart_data": analysis.chart_data or {},
                "insights": analysis.insights or "",
                "recommendations": analysis.recommendations or [],
                "ai_report": analysis.ai_report or "",
                "processing_time_ms": analysis.processing_time_ms or 0,
                "credits": {
                    "consumed": getattr(analysis, 'credits_consumed', False),
                    "amount": getattr(analysis, 'credits_consumed_amount', 0),
                    "remaining": getattr(analysis, 'credits_remaining_after', None),
                },
            },
        }

    if analysis.status == "error":
        return {
            "process_id": process_id,
            "status": "error",
            "message": analysis.progress_message or "❌ Erro no processamento",
            "result": None,
        }

    return {
        "process_id": process_id,
        "status": analysis.status,
        "progress": analysis.progress or 0,
        "message": analysis.progress_message or "",
    }


# ==============================================
# 🔥 ROTA PRINCIPAL: UPLOAD MÚLTIPLO (V13.0)
# ==============================================

@router.post("/upload-multi-analyze")
async def upload_multi_analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(...),
    analysis_type: str = Form("auto"),
    report_format: str = Form("html"),
    callback_url: Optional[str] = Form(None),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 UPLOAD MÚLTIPLO - V13.0

    Regras:
      • 1 arquivo  = 1 crédito
      • 2 arquivos = 2 créditos
      • 3 arquivos = 3 créditos
      • Cache hit = 0 créditos 🔥
    """
    start = time.time()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    total_files = len(files)

    # ==========================================
    # 1. Validações básicas
    # ==========================================
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    if total_files > UploadConfig.MAX_FILES_MULTI_ANALYZE:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {UploadConfig.MAX_FILES_MULTI_ANALYZE} arquivos. Enviados: {total_files}",
        )

    logger.info(f"📚 [MULTI] {current_user.email} | {total_files} arquivos | IP: {client_ip}")

    # ==========================================
    # 2. Rate limit
    # ==========================================
    allowed, count = await _rate_limiter.check_and_increment(current_user.id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Limite de {UploadConfig.RATE_LIMIT_PER_USER} análises/hora excedido.",
                "current_count": count,
                "retry_after": UploadConfig.RATE_LIMIT_WINDOW,
            },
        )

    # ==========================================
    # 3. Validar arquivos
    # ==========================================
    validation = await validate_files_advanced(files)
    if validation["valid_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_files",
                "message": "Nenhum arquivo válido",
                "errors": [
                    {"filename": f.filename, "error": f.error}
                    for f in validation["invalid"]
                ],
            },
        )

    valid_files: List[UploadFileInfo] = validation["valid"]
    invalid_files: List[UploadFileInfo] = validation["invalid"]
    num_valid_files = len(valid_files)

    # ==========================================
    # 4. Verificar créditos (com lock para atomicidade)
    # ==========================================
    credit_check = CreditService.check_credits(
        db, current_user, num_valid_files, lock=True
    )

    logger.info(
        f"💰 [MULTI] {current_user.email}: {num_valid_files} arq = "
        f"{num_valid_files} crédito(s) | Saldo: {credit_check.get('available', 0)} | "
        f"Status: {credit_check.get('status')}"
    )

    if not credit_check["can_proceed"]:
        logger.warning(f"⛔ [MULTI] {current_user.email} BLOQUEADO: {credit_check.get('message')}")
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check.get("message"),
                "files_requested": num_valid_files,
                "credits_available": credit_check.get("available", 0),
                "credits_required": credit_check.get("required", 0),
                "credits_missing": credit_check.get("missing", 0),
                "is_premium": credit_check.get("is_premium", False),
                "suggestion": credit_check.get("suggestion", ""),
            },
        )

    # ==========================================
    # 5. Criar análise
    # ==========================================
    file_data_list = [
        {
            "content": f.content,
            "filename": f.filename,
            "file_size": f.file_size,
            "encoding": f.detected_encoding,
            "hash": f.hash,
        }
        for f in valid_files
    ]

    analysis_record = AnalysisService.create_analysis(
        db=db,
        user=current_user,
        valid_files=valid_files,
        analysis_type=analysis_type,
        client_ip=client_ip,
        user_agent=user_agent,
        pow_valid=pow_valid,
    )

    process_id = analysis_record.id
    logger.info(f"📝 [MULTI] Análise criada: ID {process_id}")

    # ==========================================
    # 6. Background task
    # ==========================================
    background_tasks.add_task(
        BackgroundProcessor.run,
        process_id=process_id,
        file_data_list=file_data_list,
        user_id=current_user.id,
        user_email=current_user.email,
        analysis_type=analysis_type,
        num_files=num_valid_files,
        db=db,
    )
    logger.info(f"🚀 [MULTI] Background task iniciada para {process_id}")

    # ==========================================
    # 7. Resposta
    # ==========================================
    credits_before = int(current_user.credits or 0)
    eligibility = get_credit_eligibility(db, current_user)

    return JSONResponse(
        content=jsonable_encoder({
            "success": True,
            "process_id": process_id,
            "status": "processing",
            "progress": 10,
            "message": (
                f"Processando {num_valid_files} arquivo(s). "
                f"{num_valid_files} crédito(s) será(ão) consumido(s)."
            ),
            "data": {
                "total_files": total_files,
                "valid_files": num_valid_files,
                "invalid_files": len(invalid_files),
                "files": (
                    [{"filename": f.filename, "size": f.file_size, "valid": True} for f in valid_files]
                    + [{"filename": f.filename, "error": f.error, "valid": False} for f in invalid_files]
                ),
            },
            "credits": {
                "before": credits_before,
                "consumed": 0,
                "remaining": credits_before,
                "credits_per_file": UploadConfig.CREDITS_PER_FILE,
                "files_uploaded": num_valid_files,
                "total_cost": num_valid_files,
                "status": "will_be_consumed_when_ready",
                "has_credits": True,
                "note": "🎯 Se o resultado vier do cache, NÃO consumirá créditos.",
            },
            "eligibility": {
                "is_premium": eligibility.get("is_premium", False),
                "can_receive_today": eligibility.get("can_receive_today", False),
                "at_max_limit": eligibility.get("at_max_limit", False),
                "received_today": eligibility.get("received_today", False),
                "days_left": eligibility.get("days_left", 0),
            },
            "polling": {
                "url": f"/api/analysis/progress/{process_id}",
                "interval_seconds": 2,
                "max_attempts": 300,
            },
            "timestamp": datetime.now().isoformat(),
        }),
        headers={
            "X-Process-Id": str(process_id),
            "X-Status": "processing",
            "X-Credits-Before": str(credits_before),
            "X-Credits-Per-File": str(UploadConfig.CREDITS_PER_FILE),
            "X-Files-Valid": str(num_valid_files),
            "X-Total-Cost": str(num_valid_files),
            "X-Poll-Url": f"/api/analysis/progress/{process_id}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ==============================================
# 🔥 ROTAS: HISTÓRICO E RESULTADO
# ==============================================

@router.get("/analyses/history")
async def get_analyses_history(
    request: Request,
    limit: int = Query(3, ge=1, le=UploadConfig.HISTORY_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("uploaded_at"),
    sort_order: str = Query("desc"),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(models.Analysis).filter(
            models.Analysis.user_id == current_user.id
        )
        if status:
            query = query.filter(models.Analysis.status == status)
        if search:
            query = query.filter(models.Analysis.filename.ilike(f"%{search}%"))

        order_col = {
            "score": models.Analysis.confidence_score,
            "rows": models.Analysis.rows_processed,
        }.get(sort_by, models.Analysis.uploaded_at)

        query = query.order_by(
            order_col.asc() if sort_order == "asc" else order_col.desc()
        )

        total = query.count()
        analyses = query.offset(offset).limit(limit).all()

        result = []
        for a in analyses:
            result.append({
                "id": a.id,
                "filename": a.filename,
                "file_size": a.file_size,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
                "status": a.status,
                "status_label": UploadConfig.STATUS_LABELS.get(a.status, a.status),
                "status_color": UploadConfig.STATUS_COLORS.get(a.status, "#a0aec0"),
                "rows_processed": a.rows_processed or 0,
                "score": float(a.confidence_score or 0),
                "credits_consumed": getattr(a, 'credits_consumed', False),
                "credits_consumed_amount": getattr(a, 'credits_consumed_amount', 0),
                "credits_remaining_after": getattr(a, 'credits_remaining_after', None),
            })

        return jsonable_encoder({
            "success": True,
            "analyses": result,
            "total": total,
            "limit": limit,
            "offset": offset,
            "credits_per_file": UploadConfig.CREDITS_PER_FILE,
        })
    except Exception as e:
        logger.error(f"❌ Erro no histórico: {e}")
        return jsonable_encoder({"success": False, "error": str(e), "analyses": [], "total": 0})


@router.get("/analysis/result/{analysis_id}")
async def get_analysis_result(
    analysis_id: int,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    analysis = (
        db.query(models.Analysis)
        .filter(
            models.Analysis.id == analysis_id,
            models.Analysis.user_id == current_user.id,
        )
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    if analysis.status == "pending_credit":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "pending_credit",
                "message": "💡 Análise aguardando créditos.",
                "credits_needed": getattr(analysis, 'credits_needed', 1),
                "retry_url": f"/api/analysis/retry-credit/{analysis_id}",
            },
        )

    predictions_summary = analysis.predictions_summary or {}

    return jsonable_encoder({
        "success": True,
        "id": analysis.id,
        "filename": analysis.filename,
        "status": analysis.status,
        "rows_processed": analysis.rows_processed or 0,
        "chart_data": analysis.chart_data or {},
        "insights": analysis.insights or "",
        "recommendations": analysis.recommendations or [],
        "ai_report": analysis.ai_report or "",
        "confidence_score": float(analysis.confidence_score or 0),
        "metrics": {
            "mean": float(predictions_summary.get("mean_prediction", 0)),
            "high_risk_percentage": float(predictions_summary.get("high_risk_percentage", 0)),
            "low_risk_percentage": float(predictions_summary.get("low_risk_percentage", 0)),
            "total_predictions": int(predictions_summary.get("total_predictions", 0)),
        },
        "credits": {
            "consumed": getattr(analysis, 'credits_consumed', False),
            "amount": getattr(analysis, 'credits_consumed_amount', 0),
            "remaining_after": getattr(analysis, 'credits_remaining_after', None),
            "was_cache_hit": getattr(analysis, 'credits_consumed_amount', 0) == 0
                and getattr(analysis, 'credits_consumed', False),
        },
    })


# ==============================================
# 🔥 ROTA: RETRY CRÉDITO
# ==============================================

@router.post("/analysis/retry-credit/{process_id}")
async def retry_analysis_credit(
    process_id: int,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    analysis = (
        db.query(models.Analysis)
        .filter(
            models.Analysis.id == process_id,
            models.Analysis.user_id == current_user.id,
        )
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    if getattr(analysis, 'credits_consumed', False):
        return {
            "success": True,
            "message": f"✅ Créditos já consumidos ({analysis.credits_consumed_amount}).",
            "analysis_id": process_id,
            "already_consumed": True,
        }

    if analysis.status != "pending_credit":
        return {
            "success": False,
            "message": f"Análise com status '{analysis.status}', não precisa de retry.",
        }

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    num_files = len(analysis.filename.split(" | ")) if analysis.filename else 1
    required = num_files * UploadConfig.CREDITS_PER_FILE

    if (user.credits or 0) < required:
        return {
            "success": False,
            "message": f"❌ Você tem {user.credits}, precisa de {required} para {num_files} arquivo(s).",
            "credits_needed": required,
            "credits_available": user.credits,
        }

    success, message = CreditService.consume(
        db, analysis, user, num_files, cache_hit=False
    )
    return {
        "success": success,
        "message": f"{'✅' if success else '❌'} {message}",
        "analysis_id": process_id,
        "status": "completed" if success else "pending_credit",
    }


# ==============================================
# 🔥 INIT LOG
# ==============================================

print("=" * 80)
print("🚀 UPLOAD_ROUTES.PY - VERSÃO 13.0 (REFATORADA + CACHE-AWARE)")
print("=" * 80)
print(f"   📁 Max arquivos: {UploadConfig.MAX_FILES_MULTI_ANALYZE}")
print(f"   📦 Max tamanho: {UploadConfig.MAX_FILE_SIZE // 1024}KB")
print(f"   🤖 ML Pipeline: {'✅' if _ml_available else '⚠️ Fallback'}")
print(f"   🔧 Preprocessing: {'✅' if _preprocessing_available else '⚠️ Fallback'}")
print(f"   🚦 Rate limit: {UploadConfig.RATE_LIMIT_PER_USER} req/h")
print(f"   💰 Créditos: {UploadConfig.CREDITS_PER_FILE} por arquivo")
print()
print("   🔥 NOVIDADES V13.0:")
print("      ✅ BUGFIX: Cache hit NÃO consome créditos")
print("      ✅ CreditService com with_for_update() (atomicidade)")
print("      ✅ AnalysisService + BackgroundProcessor (separação)")
print("      ✅ 1 query de crédito (era 3+)")
print("      ✅ Idempotência garantida (credits_consumed)")
print("      ✅ Logs estruturados por serviço")
print("=" * 80)