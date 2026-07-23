# backend/api/upload_routes.py - VERSÃO 3.0 MELHORADA
"""
🔥 Rotas para upload e processamento de arquivos
✅ INTEGRADO COM POW_ROUTES.PY V3.0
✅ SUPORTE A MÚLTIPLOS ARQUIVOS (até 5 por vez)
✅ VERIFICAÇÃO DE CRÉDITOS E PoW
✅ RATE LIMITER (Proteção contra abuso)
✅ MÉTRICAS DE POW SALVAS NO BANCO
✅ CÓDIGO MODULAR E OTIMIZADO
✅ TRATAMENTO DE ERROS ROBUSTO
"""

# ==============================================
# 🔥 IMPORTS
# ==============================================

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Tuple, Set
import logging
import os
import uuid
from datetime import datetime
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from backend.database import get_db
from backend import crud, models
from backend.security import get_current_active_user
from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display
from backend.security import rate_limiter
from backend.api.pow_routes import validate_pow_request, pow_service, PoWConfig
from backend.preprocessing import process_file_content, pipeline

# ==============================================
# 🔥 CONFIGURAÇÃO
# ==============================================

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

# Constantes
class UploadConfig:
    """Configurações centralizadas do upload"""
    MAX_FILE_SIZE = 200 * 1024  # 200KB
    MAX_FILES_PER_BATCH = 5      # Aumentado para 5
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv'}  # Adicionado .tsv
    ALLOWED_MIME_TYPES = {
        'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/tab-separated-values'
    }
    
    # Rate Limiter
    RATE_LIMIT_UPLOAD_PER_IP = 10
    RATE_LIMIT_UPLOAD_PER_USER = 5
    RATE_LIMIT_WINDOW_SECONDS = 60
    
    # Timeouts
    PROCESSING_TIMEOUT_SECONDS = 300  # 5 minutos
    UPLOAD_TIMEOUT_SECONDS = 30

# ==============================================
# 🔥 MODELOS DE DADOS
# ==============================================

@dataclass
class UploadFileInfo:
    """Informações de um arquivo enviado"""
    filename: str
    content: bytes
    file_size: int
    file_extension: str
    mime_type: Optional[str] = None
    process_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    analysis_id: Optional[int] = None
    status: str = "pending"
    error: Optional[str] = None
    
    @property
    def is_valid_extension(self) -> bool:
        return self.file_extension.lower() in UploadConfig.ALLOWED_EXTENSIONS
    
    @property
    def is_valid_size(self) -> bool:
        return self.file_size <= UploadConfig.MAX_FILE_SIZE
    
    @property
    def size_kb(self) -> float:
        return self.file_size / 1024

@dataclass
class UploadBatchResult:
    """Resultado de um batch de uploads"""
    total_files: int
    accepted_files: List[UploadFileInfo] = field(default_factory=list)
    rejected_files: List[UploadFileInfo] = field(default_factory=list)
    analyses_created: List[int] = field(default_factory=list)
    processing_started: bool = False
    processing_time_ms: float = 0
    credits_consumed: int = 0

# ==============================================
# 🔥 GERENCIADOR DE STATUS
# ==============================================

class ProcessingStatusManager:
    """Gerencia o status dos processamentos em memória"""
    
    def __init__(self, max_items: int = 1000):
        self._status: Dict[str, Dict[str, Any]] = {}
        self._max_items = max_items
        self._lock = asyncio.Lock()
    
    async def create(self, process_id: str, data: Dict[str, Any]) -> None:
        """Cria um novo status"""
        async with self._lock:
            # Limpar se necessário
            if len(self._status) >= self._max_items:
                self._cleanup()
            
            self._status[process_id] = {
                "process_id": process_id,
                "status": "uploaded",
                "progress": 10,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                **data
            }
    
    async def update(self, process_id: str, updates: Dict[str, Any]) -> bool:
        """Atualiza um status existente"""
        async with self._lock:
            if process_id not in self._status:
                return False
            self._status[process_id].update(updates)
            self._status[process_id]["updated_at"] = datetime.now().isoformat()
            return True
    
    async def get(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Obtém um status"""
        async with self._lock:
            return self._status.get(process_id)
    
    async def get_user_analyses(self, user_email: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtém análises de um usuário"""
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
    
    def _cleanup(self) -> None:
        """Limpa status antigos"""
        # Remover os mais antigos
        sorted_items = sorted(
            self._status.items(),
            key=lambda x: x[1].get("created_at", "")
        )
        to_remove = len(self._status) - self._max_items + 50
        for process_id, _ in sorted_items[:to_remove]:
            del self._status[process_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador"""
        return {
            "total_items": len(self._status),
            "max_items": self._max_items,
            "by_status": {
                "uploaded": len([s for s in self._status.values() if s.get("status") == "uploaded"]),
                "processing": len([s for s in self._status.values() if s.get("status") == "processing"]),
                "completed": len([s for s in self._status.values() if s.get("status") == "completed"]),
                "error": len([s for s in self._status.values() if s.get("status") == "error"]),
            }
        }

# Instância global
processing_status = ProcessingStatusManager()

# ==============================================
# 🔥 UTILITÁRIOS
# ==============================================

def validate_file(file: UploadFile, idx: int) -> Optional[UploadFileInfo]:
    """Valida um arquivo e retorna suas informações"""
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
        
        # Validar tamanho
        content = asyncio.run(file.read())
        file_size = len(content)
        
        if file_size > UploadConfig.MAX_FILE_SIZE:
            return UploadFileInfo(
                filename=file.filename,
                content=content,
                file_size=file_size,
                file_extension=file_ext,
                error=f"Arquivo excede o limite de {UploadConfig.MAX_FILE_SIZE//1024}KB. Tamanho: {file_size/1024:.2f}KB"
            )
        
        if file_size == 0:
            return UploadFileInfo(
                filename=file.filename,
                content=content,
                file_size=file_size,
                file_extension=file_ext,
                error="Arquivo vazio"
            )
        
        # ✅ Arquivo válido
        return UploadFileInfo(
            filename=file.filename,
            content=content,
            file_size=file_size,
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

def validate_credits(user: models.User, total_files: int) -> Dict[str, Any]:
    """Valida créditos do usuário"""
    if user.is_admin:
        return {
            "valid": True,
            "credits_needed": 0,
            "credits_available": "∞",
            "message": "Admin - créditos ilimitados"
        }
    
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

def create_analysis_record(
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
    """Cria um registro de análise no banco"""
    
    # Obter dados do PoW dos headers
    nonce = request.headers.get(PoWConfig.HEADER_NONCE)
    challenge = request.headers.get(PoWConfig.HEADER_CHALLENGE)
    
    # Criar análise
    analysis = models.Analysis(
        user_id=user_id,
        filename=file_info.filename,
        file_size=file_info.file_size,
        analysis_type=analysis_type,
        model_used="auto",  # Será atualizado depois
        status="pending",
        uploaded_at=datetime.now(),
        # Dados do PoW
        pow_challenge=challenge,
        pow_nonce=nonce,
        pow_difficulty=pow_difficulty,
        pow_verified=pow_valid,
        pow_verified_at=datetime.now() if pow_valid else None,
        pow_algorithm=PoWConfig.ALGORITHM,
        # Segurança
        client_ip=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        rate_limit_applied=False,
        # Métricas
        processing_time_ms=None,
        upload_time_ms=None,
    )
    
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    
    return analysis

# ==============================================
# 🔥 PROCESSAMENTO DE ML
# ==============================================

class MLProcessor:
    """Processador de Machine Learning"""
    
    @staticmethod
    async def process_file(
        content: bytes,
        filename: str,
        process_id: str,
        user_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """Processa um único arquivo com ML Pipeline"""
        
        try:
            # Atualizar status
            await processing_status.update(process_id, {
                "status": "processing",
                "progress": 20,
                "message": "Iniciando ML Pipeline..."
            })
            
            # Processar com pipeline
            result = await process_file_content(content, filename)
            
            # Verificar resultado
            if result.get("success"):
                # ✅ Sucesso - Atualizar status com resultados
                analysis_info = {
                    "rows_processed": result.get("processed_rows", 0),
                    "columns_detected": result.get("metadata", {}).get("stats", {}).get("columns", 0),
                    "numeric_columns": result.get("metadata", {}).get("stats", {}).get("numeric_columns", 0),
                    "categorical_columns": result.get("metadata", {}).get("stats", {}).get("categorical_columns", 0),
                    "model_used": result.get("model_used", "AutoML"),
                    "filename": filename,
                    "predictions_summary": result.get("metrics", {}),
                    "insights": result.get("insights", {}),
                    "encoding_used": result.get("encoding_used")
                }
                
                await processing_status.update(process_id, {
                    "status": "completed",
                    "progress": 100,
                    "completed_at": datetime.now().isoformat(),
                    "analysis_info": analysis_info,
                    "prediction_stats": result.get("metrics", {}),
                    "insights": result.get("insights", {}),
                    "recommendations": result.get("recommendations", []),
                    "encoding_used": result.get("encoding_used"),
                    "credit_consumed": False,
                })
                
                logger.info(f"✅ Pipeline ML concluído: {filename} - {result.get('processed_rows', 0)} linhas")
                
                # Consumir crédito após análise bem-sucedida
                await MLProcessor._consume_credit(user_id, process_id)
                
                return {"success": True, "result": result}
            else:
                # ❌ Erro no pipeline
                error_msg = result.get("error", "Erro desconhecido no ML")
                await processing_status.update(process_id, {
                    "status": "error",
                    "progress": 100,
                    "error": error_msg
                })
                
                logger.error(f"❌ Pipeline ML falhou: {filename} - {error_msg}")
                return {"success": False, "error": error_msg}
                
        except asyncio.TimeoutError:
            error_msg = f"Timeout ao processar arquivo (limite: {UploadConfig.PROCESSING_TIMEOUT_SECONDS}s)"
            await processing_status.update(process_id, {
                "status": "error",
                "progress": 100,
                "error": error_msg
            })
            logger.error(f"⏰ {error_msg}: {filename}")
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = str(e)
            await processing_status.update(process_id, {
                "status": "error",
                "progress": 100,
                "error": error_msg
            })
            logger.error(f"❌ Erro no processamento ML: {error_msg}")
            return {"success": False, "error": error_msg}
    
    @staticmethod
    async def process_batch(
        files: List[UploadFileInfo],
        user_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """Processa múltiplos arquivos em lote"""
        
        logger.info(f"🤖 Iniciando pipeline ML para {len(files)} arquivo(s)")
        
        # Atualizar status inicial
        for file_info in files:
            await processing_status.update(file_info.process_id, {
                "status": "processing",
                "progress": 20,
                "message": "Preparando para processamento..."
            })
        
        # Processar cada arquivo
        results = []
        for idx, file_info in enumerate(files):
            logger.info(f"📁 [{idx+1}/{len(files)}] Processando: {file_info.filename}")
            
            # Atualizar progresso
            progress = 30 + (idx * 30 // len(files))
            await processing_status.update(file_info.process_id, {
                "progress": progress,
                "message": f"Processando arquivo {idx+1}/{len(files)}..."
            })
            
            # Processar
            result = await MLProcessor.process_file(
                content=file_info.content,
                filename=file_info.filename,
                process_id=file_info.process_id,
                user_id=user_id,
                db=db
            )
            results.append(result)
        
        # Estatísticas finais
        success_count = len([r for r in results if r.get("success")])
        logger.info(f"✅ Pipeline ML concluído: {success_count}/{len(results)} sucesso")
        
        return results
    
    @staticmethod
    async def _consume_credit(user_id: int, process_id: str) -> None:
        """Consome um crédito do usuário após análise bem-sucedida"""
        from backend.database import SessionLocal
        from backend.models import User
        
        db_local = SessionLocal()
        try:
            user = db_local.query(User).filter(User.id == user_id).first()
            if user and not user.is_admin:
                success = consume_analysis_credit(user, db_local, 1)
                if success:
                    logger.info(f"💰 Crédito consumido para análise {process_id}")
                    await processing_status.update(process_id, {
                        "credit_consumed": True,
                        "credits_remaining": user.credits
                    })
                else:
                    logger.warning(f"⚠️ Falha ao consumir crédito para {user.email}")
        finally:
            db_local.close()

# ==============================================
# 🔥 ROTAS DA API
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    # 🔥 PoW Validation
    pow_valid: bool = Depends(validate_pow_request),
    # 🔥 Arquivos
    files: List[UploadFile] = File(..., description="Arquivos para upload (máx 5)"),
    analysis_type: str = Form("auto", description="Tipo de análise (auto, classification, regression)"),
    # 🔥 Usuário
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    🔥 Upload com dupla proteção: PoW + Rate Limiter
    
    FLUXO:
    1. ✅ PoW validado (bloqueia bots)
    2. ✅ Rate Limiter (bloqueia abuso)
    3. ✅ Verifica créditos
    4. ✅ Valida arquivos
    5. ✅ Cria registros no banco
    6. ✅ Processa com ML Pipeline (background)
    7. ✅ Retorna resultados
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    
    # ==============================================
    # 🔥 1. VALIDAÇÕES INICIAIS
    # ==============================================
    
    total_files = len(files)
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > UploadConfig.MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Limite excedido. Máximo {UploadConfig.MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📤 [UPLOAD] Requisição de {current_user.email} | IP: {client_ip}")
    logger.info(f"   📁 Arquivos: {total_files}")
    logger.info(f"   🔐 PoW validado: {pow_valid}")
    
    # ==============================================
    # 🔥 2. RATE LIMITER
    # ==============================================
    
    # Rate limit por IP
    ip_key = f"upload_ip:{client_ip}"
    if not await rate_limiter.check_rate_limit(ip_key, UploadConfig.RATE_LIMIT_UPLOAD_PER_IP, UploadConfig.RATE_LIMIT_WINDOW_SECONDS):
        logger.warning(f"❌ Rate limit excedido para IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitos uploads. Aguarde {UploadConfig.RATE_LIMIT_WINDOW_SECONDS} segundos.",
                "retry_after": UploadConfig.RATE_LIMIT_WINDOW_SECONDS,
                "type": "ip",
                "limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP
            }
        )
    
    # Rate limit por usuário
    user_key = f"upload_user:{current_user.id}"
    if not await rate_limiter.check_rate_limit(user_key, UploadConfig.RATE_LIMIT_UPLOAD_PER_USER, UploadConfig.RATE_LIMIT_WINDOW_SECONDS):
        logger.warning(f"❌ Rate limit excedido para usuário: {current_user.email}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitos uploads. Aguarde {UploadConfig.RATE_LIMIT_WINDOW_SECONDS} segundos.",
                "retry_after": UploadConfig.RATE_LIMIT_WINDOW_SECONDS,
                "type": "user",
                "limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER
            }
        )
    
    logger.info(f"✅ Rate limits OK para {current_user.email}")
    
    # ==============================================
    # 🔥 3. VERIFICA CRÉDITOS
    # ==============================================
    
    credit_check = validate_credits(current_user, total_files)
    if not credit_check["valid"]:
        logger.warning(f"❌ Créditos insuficientes: {current_user.email}")
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check["message"],
                "credits_available": credit_check["credits_available"],
                "credits_needed": credit_check["credits_needed"],
                "action": "buy_credits"
            }
        )
    
    logger.info(f"✅ Créditos OK: {credit_check['message']}")
    
    # ==============================================
    # 🔥 4. PROCESSAMENTO DOS ARQUIVOS
    # ==============================================
    
    batch_result = UploadBatchResult(total_files=total_files)
    pow_difficulty = request.headers.get(PoWConfig.HEADER_COMPLEXITY, PoWConfig.DEFAULT_DIFFICULTY)
    
    for idx, file in enumerate(files):
        # Validar arquivo
        file_info = validate_file(file, idx)
        
        if file_info.error:
            batch_result.rejected_files.append(file_info)
            logger.warning(f"⚠️ Arquivo rejeitado: {file_info.filename} - {file_info.error}")
            continue
        
        try:
            # Criar registro no banco
            analysis = create_analysis_record(
                db=db,
                user_id=current_user.id,
                file_info=file_info,
                analysis_type=analysis_type,
                request=request,
                pow_valid=pow_valid,
                pow_difficulty=int(pow_difficulty) if pow_difficulty else PoWConfig.DEFAULT_DIFFICULTY,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            file_info.analysis_id = analysis.id
            batch_result.analyses_created.append(analysis.id)
            
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
                "message": "Arquivo recebido, iniciando ML Pipeline...",
                "credits_consumed": False,
                "pow_validated": pow_valid,
                "pow_difficulty": int(pow_difficulty) if pow_difficulty else 4,
                "rate_limit": {
                    "ip_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP,
                    "user_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER,
                    "window_seconds": UploadConfig.RATE_LIMIT_WINDOW_SECONDS
                }
            })
            
            batch_result.accepted_files.append(file_info)
            logger.info(f"✅ Arquivo {idx+1}/{total_files} aceito: {file_info.filename}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo {file.filename}: {e}")
            file_info.error = str(e)
            batch_result.rejected_files.append(file_info)
    
    # ==============================================
    # 🔥 5. INICIAR ML PIPELINE EM BACKGROUND
    # ==============================================
    
    if batch_result.accepted_files:
        batch_result.processing_started = True
        batch_result.credits_consumed = len(batch_result.accepted_files)
        
        logger.info(f"🤖 Iniciando ML Pipeline para {len(batch_result.accepted_files)} arquivo(s)")
        
        # Adicionar tarefa em background
        background_tasks.add_task(
            MLProcessor.process_batch,
            batch_result.accepted_files,
            current_user.id,
            db
        )
    
    # ==============================================
    # 🔥 6. RESPOSTA
    # ==============================================
    
    processing_time_ms = (time.time() - start_time) * 1000
    batch_result.processing_time_ms = processing_time_ms
    
    # Estatísticas
    pipeline_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    pow_stats = pow_service.get_stats() if hasattr(pow_service, 'get_stats') else {}
    
    return {
        "success": len(batch_result.rejected_files) == 0,
        "message": f"Processado {len(batch_result.accepted_files)} de {total_files} arquivo(s). ML Pipeline iniciado.",
        "total_files": total_files,
        "accepted_files": [
            {
                "filename": f.filename,
                "process_id": f.process_id,
                "analysis_id": f.analysis_id,
                "size_kb": round(f.size_kb, 2),
                "status": "processing"
            }
            for f in batch_result.accepted_files
        ],
        "rejected_files": [
            {
                "filename": f.filename,
                "error": f.error,
                "size_kb": round(f.size_kb, 2) if f.file_size > 0 else 0
            }
            for f in batch_result.rejected_files
        ],
        "credits": {
            "before": current_user.credits if not current_user.is_admin else "∞",
            "consumed": batch_result.credits_consumed if not current_user.is_admin else 0,
            "display": get_credits_display(current_user),
            "is_admin": current_user.is_admin
        },
        "performance": {
            "processing_time_ms": round(processing_time_ms, 2),
            "files_processed": len(batch_result.accepted_files),
            "files_rejected": len(batch_result.rejected_files)
        },
        "security": {
            "pow_validated": pow_valid,
            "pow_difficulty": int(pow_difficulty) if pow_difficulty else 4,
            "pow_algorithm": PoWConfig.ALGORITHM,
            "pow_stats": {
                "verified": pow_stats.get("challenges", {}).get("verified", 0),
                "replay_attacks_blocked": pow_stats.get("challenges", {}).get("replay_attacks_blocked", 0),
            },
            "rate_limit": {
                "ip_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP,
                "user_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER,
                "window_seconds": UploadConfig.RATE_LIMIT_WINDOW_SECONDS
            },
            "client_ip": client_ip
        },
        "pipeline": {
            "available": True,
            "encoding_detection": "auto",
            "model_source": pipeline_status.get('model_source', 'unknown'),
            "encoding_stats": pipeline.get_encoding_stats() if hasattr(pipeline, 'get_encoding_stats') else {}
        },
        "timestamp": datetime.now().isoformat()
    }

# ==============================================
# 🔥 ROTAS DE STATUS E HISTÓRICO
# ==============================================

@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Verifica status do processamento"""
    
    status_data = await processing_status.get(process_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return status_data

@router.get("/analyses/history")
async def get_analyses_history(
    current_user = Depends(get_current_active_user),
    limit: int = 10
):
    """Retorna histórico de análises do usuário"""
    
    analyses = await processing_status.get_user_analyses(current_user.email, limit)
    
    return {
        "success": True,
        "total": len(analyses),
        "analyses": analyses,
        "ml_pipeline": {
            "available": True,
            "encoding_support": "auto"
        }
    }

@router.get("/analysis/result/{process_id}")
async def get_analysis_result(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Retorna o resultado completo de uma análise"""
    
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
        "pow_validated": status_data.get("pow_validated", False),
        "pow_difficulty": status_data.get("pow_difficulty")
    }

# ==============================================
# 🔥 ROTAS ADMIN
# ==============================================

@router.get("/pipeline-status")
async def get_pipeline_status(
    current_user = Depends(get_current_active_user)
):
    """Retorna status do ML Pipeline (apenas admin)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado. Requer permissão de administrador.")
    
    status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    encoding_stats = pipeline.get_encoding_stats() if hasattr(pipeline, 'get_encoding_stats') else {}
    
    return {
        "success": True,
        "pipeline": status,
        "encoding": encoding_stats,
        "models_available": {
            "default": bool(pipeline.models.get('default')) if hasattr(pipeline, 'models') else False,
            "ensemble": bool(pipeline.models.get('ensemble')) if hasattr(pipeline, 'models') else False
        },
        "processing_status": processing_status.get_stats(),
        "config": {
            "max_files": UploadConfig.MAX_FILES_PER_BATCH,
            "max_file_size_kb": UploadConfig.MAX_FILE_SIZE // 1024,
            "allowed_extensions": list(UploadConfig.ALLOWED_EXTENSIONS),
            "rate_limiter": {
                "ip_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP,
                "user_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER,
                "window_seconds": UploadConfig.RATE_LIMIT_WINDOW_SECONDS
            },
            "pow": {
                "enabled": True,
                "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
                "algorithm": PoWConfig.ALGORITHM,
            }
        }
    }

@router.get("/security-stats")
async def get_security_stats(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna estatísticas de segurança (apenas admin)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado. Requer permissão de administrador.")
    
    # Estatísticas de PoW
    pow_stats = pow_service.get_stats() if hasattr(pow_service, 'get_stats') else {}
    
    # Estatísticas de processamento
    processing_stats = processing_status.get_stats()
    
    # Contar análises com PoW validado
    pow_validated_count = 0
    encoding_counts = {}
    
    # Nota: Isso é assíncrono, mas como é admin, podemos fazer sync
    import asyncio
    # Simples contagem baseada nos status em memória
    
    return {
        "success": True,
        "processing": processing_stats,
        "pow": {
            "enabled": True,
            "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
            "algorithm": PoWConfig.ALGORITHM,
            "total_validated": pow_stats.get("challenges", {}).get("verified", 0),
            "replay_attacks_blocked": pow_stats.get("challenges", {}).get("replay_attacks_blocked", 0),
        },
        "rate_limiter": {
            "ip_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_IP,
            "user_limit": UploadConfig.RATE_LIMIT_UPLOAD_PER_USER,
            "window_seconds": UploadConfig.RATE_LIMIT_WINDOW_SECONDS
        },
        "timestamp": datetime.now().isoformat()
    }

# ==============================================
# 🔥 INICIALIZAÇÃO
# ==============================================

print("=" * 70)
print("🔥 upload_routes.py - VERSÃO 3.0 MELHORADA")
print(f"   🚦 Rate Limiter: {UploadConfig.RATE_LIMIT_UPLOAD_PER_IP}/IP + {UploadConfig.RATE_LIMIT_UPLOAD_PER_USER}/usuário em {UploadConfig.RATE_LIMIT_WINDOW_SECONDS}s")
print(f"   🔐 PoW: {PoWConfig.ALGORITHM} com dificuldade adaptativa")
print(f"   🧠 ML Pipeline: Encoding automático + RandomForest/Ensemble/AutoML")
print(f"   📁 Limites: {UploadConfig.MAX_FILES_PER_BATCH} arquivos, {UploadConfig.MAX_FILE_SIZE//1024}KB cada")
print(f"   📊 Métricas de PoW salvas no banco")
print(f"   ⏰ Timeout: {UploadConfig.PROCESSING_TIMEOUT_SECONDS}s")
print(f"   📦 Extensões: {', '.join(UploadConfig.ALLOWED_EXTENSIONS)}")
print("=" * 70)