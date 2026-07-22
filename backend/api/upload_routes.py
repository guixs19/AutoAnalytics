# backend/api/upload_routes.py - VERSÃO ATUALIZADA v2.0
"""
🔥 Rotas para upload e processamento de arquivos
✅ INTEGRADO COM POW_ROUTES.PY V2.0
✅ SUPORTE A MÚLTIPLOS ARQUIVOS (até 3 por vez)
✅ VERIFICAÇÃO DE CRÉDITOS E PoW
✅ RATE LIMITER (Proteção contra abuso)
✅ MÉTRICAS DE POW SALVAS NO BANCO
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Optional, Tuple, List, Any
import logging
import os
import uuid
from datetime import datetime
import json
import asyncio
import time

from backend.database import get_db
from backend import crud, models
from backend.security import get_current_active_user
from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display

# 🔥🔥🔥 RATE LIMITER
from backend.security import rate_limiter

# 🔥🔥🔥 PoW (NOVA VERSÃO)
from backend.api.pow_routes import validate_pow_request, pow_service, PoWConfig

# 🔥🔥🔥 ML Pipeline
from backend.preprocessing import process_file_content, pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Armazenamento temporário para status de processamento
processing_status = {}

# Limites
MAX_FILE_SIZE = 200 * 1024  # 200KB
MAX_FILES_PER_BATCH = 3
ALLOWED_EXTENSIONS = ['.csv', '.xlsx', '.xls']

# 🔥 CONSTANTES DO RATE LIMITER
RATE_LIMIT_UPLOAD_PER_IP = 10      # 10 uploads por IP
RATE_LIMIT_UPLOAD_PER_USER = 5     # 5 uploads por usuário
RATE_LIMIT_WINDOW_SECONDS = 60     # Em 60 segundos


# ==============================================
# 🔥 FUNÇÃO: VALIDAÇÃO DE CRÉDITOS
# ==============================================

def validate_credits(user, total_files: int) -> Dict[str, Any]:
    """Valida se o usuário tem créditos suficientes"""
    if user.is_admin:
        return {"valid": True, "credits_needed": 0, "credits_available": "∞", "message": "Admin - créditos ilimitados"}
    
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


# ==============================================
# 🔥 FUNÇÃO: CRIAR ANÁLISE COM POW METRICS
# ==============================================

def create_analysis_with_pow_metrics(
    db: Session,
    user_id: int,
    filename: str,
    file_size: int,
    analysis_type: str,
    ai_model: str,
    request: Request,
    pow_valid: bool,
    pow_difficulty: int,
    client_ip: str,
    user_agent: Optional[str] = None,
) -> models.Analysis:
    """
    🔥 Cria uma análise com métricas de PoW
    """
    # 🔥 Obter dados do PoW dos headers
    nonce = request.headers.get(PoWConfig.HEADER_NONCE)
    challenge = request.headers.get(PoWConfig.HEADER_CHALLENGE)
    
    # 🔥 Criar análise
    analysis = models.Analysis(
        user_id=user_id,
        filename=filename,
        file_size=file_size,
        analysis_type=analysis_type,
        ai_model=ai_model,
        status="pending",
        uploaded_at=datetime.now(),
        # 🔥 Dados do PoW
        pow_challenge=challenge,
        pow_nonce=nonce,
        pow_difficulty=pow_difficulty,
        pow_verified=pow_valid,
        pow_verified_at=datetime.now() if pow_valid else None,
        pow_algorithm=PoWConfig.ALGORITHM,
        # 🔥 Segurança
        client_ip=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        rate_limit_applied=False,  # Será atualizado se necessário
        # 🔥 Métricas de tempo (serão atualizadas depois)
        processing_time_ms=None,
        upload_time_ms=None,
    )
    
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    
    logger.info(f"📊 Análise criada: {filename} (ID: {analysis.id}) - PoW: {pow_valid}")
    return analysis


# ==============================================
# 🔥 PROCESSAMENTO ML COM PIPELINE
# ==============================================

async def process_single_file_with_pipeline(
    content: bytes,
    filename: str,
    process_id: str,
    user_id: int,
    db: Session
) -> Dict[str, Any]:
    """
    🔥 Processa um único arquivo com o ML Pipeline
    """
    try:
        # 1. Processar com o pipeline
        result = await process_file_content(content, filename)
        
        # 2. Atualizar status
        if result.get("success"):
            processing_status[process_id]['status'] = 'completed'
            processing_status[process_id]['progress'] = 100
            processing_status[process_id]['completed_at'] = datetime.now().isoformat()
            processing_status[process_id]['analysis_info'] = {
                'rows_processed': result.get('processed_rows', 0),
                'columns_detected': result.get('metadata', {}).get('stats', {}).get('columns', 0),
                'numeric_columns': result.get('metadata', {}).get('stats', {}).get('numeric_columns', 0),
                'categorical_columns': result.get('metadata', {}).get('stats', {}).get('categorical_columns', 0),
                'model_used': result.get('model_used', 'AutoML'),
                'filename': filename,
                'predictions_summary': result.get('metrics', {}),
                'insights': result.get('insights', {}),
                'encoding_used': result.get('encoding_used')
            }
            processing_status[process_id]['prediction_stats'] = result.get('metrics', {})
            processing_status[process_id]['insights'] = result.get('insights', {})
            processing_status[process_id]['recommendations'] = result.get('recommendations', [])
            processing_status[process_id]['encoding_used'] = result.get('encoding_used')
            
            logger.info(f"✅ Pipeline ML concluído: {filename} - {result.get('processed_rows', 0)} linhas")
            
            # 🔥 CONSUMIR CRÉDITO APÓS ANÁLISE BEM-SUCEDIDA
            from backend.database import SessionLocal
            db_local = SessionLocal()
            try:
                from backend.models import User
                user = db_local.query(User).filter(User.id == user_id).first()
                if user and not user.is_admin:
                    success = consume_analysis_credit(user, db_local, 1)
                    if success:
                        logger.info(f"💰 Crédito consumido para análise {process_id}")
                        processing_status[process_id]['credit_consumed'] = True
                        processing_status[process_id]['credits_remaining'] = user.credits
                    else:
                        logger.warning(f"⚠️ Falha ao consumir crédito para {user.email}")
            finally:
                db_local.close()
            
            return {"success": True, "result": result}
        else:
            processing_status[process_id]['status'] = 'error'
            processing_status[process_id]['progress'] = 100
            processing_status[process_id]['error'] = result.get('error', 'Erro desconhecido no ML')
            logger.error(f"❌ Pipeline ML falhou: {filename} - {result.get('error')}")
            return {"success": False, "error": result.get('error')}
            
    except Exception as e:
        logger.error(f"❌ Erro no processamento ML: {e}")
        processing_status[process_id]['status'] = 'error'
        processing_status[process_id]['error'] = str(e)
        processing_status[process_id]['progress'] = 100
        return {"success": False, "error": str(e)}


async def process_multiple_files_with_ml(files_to_process: List[tuple], user_id: int, db: Session):
    """
    🔥 Processa múltiplos arquivos com o ML Pipeline
    """
    logger.info(f"🤖 Iniciando pipeline ML para {len(files_to_process)} arquivo(s)")
    
    # Atualizar status para "processando"
    for process_id, _, filename in files_to_process:
        if process_id in processing_status:
            processing_status[process_id]['status'] = 'processing'
            processing_status[process_id]['progress'] = 20
            processing_status[process_id]['message'] = 'Iniciando ML Pipeline...'
    
    # Processar cada arquivo
    results = []
    for idx, (process_id, content, filename) in enumerate(files_to_process):
        logger.info(f"📁 [{idx+1}/{len(files_to_process)}] Processando: {filename}")
        
        # Atualizar progresso
        if process_id in processing_status:
            processing_status[process_id]['progress'] = 30 + (idx * 30)
            processing_status[process_id]['message'] = f'Processando arquivo {idx+1}/{len(files_to_process)}...'
        
        result = await process_single_file_with_pipeline(content, filename, process_id, user_id, db)
        results.append(result)
    
    logger.info(f"✅ Pipeline ML concluído: {len([r for r in results if r.get('success')])}/{len(results)} sucesso")
    return results


# ==============================================
# 🔥 UPLOAD COM RATE LIMITER + PoW (V2.0)
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    # 🔥 1️⃣ VALIDAÇÃO PoW (via Dependency)
    pow_valid: bool = Depends(validate_pow_request),
    # 🔥 2️⃣ ARQUIVOS
    files: List[UploadFile] = File(...),
    analysis_type: str = Form("auto"),
    ai_model: str = Form("auto"),
    # 🔥 3️⃣ USUÁRIO
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    🔥 UPLOAD COM DUPLA PROTEÇÃO: PoW + Rate Limiter
    
    FLUXO:
    1. ✅ PoW validado (bloqueia bots)
    2. ✅ Rate Limiter (bloqueia abuso)
    3. ✅ Verifica créditos
    4. ✅ Processa com ML Pipeline
    5. ✅ Retorna resultados com métricas de PoW
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    start_time = time.time()
    
    # 🔥 Obter dados do PoW dos headers
    pow_nonce = request.headers.get(PoWConfig.HEADER_NONCE)
    pow_challenge = request.headers.get(PoWConfig.HEADER_CHALLENGE)
    pow_difficulty = request.headers.get(PoWConfig.HEADER_COMPLEXITY, PoWConfig.DEFAULT_DIFFICULTY)
    
    logger.info(f"📤 [UPLOAD] Requisição de {current_user.email} | IP: {client_ip}")
    logger.info(f"   📁 Arquivos: {len(files)}")
    logger.info(f"   🔐 PoW validado: {pow_valid}")
    logger.info(f"   🔐 PoW difficulty: {pow_difficulty}")
    logger.info(f"   🔐 PoW challenge: {pow_challenge[:8] if pow_challenge else 'N/A'}...")
    
    # ==============================================
    # 🔥 1. VALIDA QUANTIDADE DE ARQUIVOS
    # ==============================================
    
    total_arquivos = len(files)
    
    if total_arquivos == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado")
    
    if total_arquivos > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite ultrapassado. Máximo {MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📦 Lote de {total_arquivos} arquivo(s) recebido")
    
    # ==============================================
    # 🔥 2. RATE LIMITER (Proteção contra abuso)
    # ==============================================
    
    # Rate limit por IP
    ip_rate_key = f"upload_ip:{client_ip}"
    is_ip_allowed = await rate_limiter.check_rate_limit(
        ip_rate_key,
        max_requests=RATE_LIMIT_UPLOAD_PER_IP,
        window=RATE_LIMIT_WINDOW_SECONDS
    )
    
    if not is_ip_allowed:
        logger.warning(f"❌ Rate limit excedido para IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitos uploads. Aguarde {RATE_LIMIT_WINDOW_SECONDS} segundos.",
                "retry_after": RATE_LIMIT_WINDOW_SECONDS,
                "type": "ip",
                "limit": RATE_LIMIT_UPLOAD_PER_IP
            }
        )
    
    # Rate limit por usuário
    user_rate_key = f"upload_user:{current_user.id}"
    is_user_allowed = await rate_limiter.check_rate_limit(
        user_rate_key,
        max_requests=RATE_LIMIT_UPLOAD_PER_USER,
        window=RATE_LIMIT_WINDOW_SECONDS
    )
    
    if not is_user_allowed:
        logger.warning(f"❌ Rate limit excedido para usuário: {current_user.email}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitos uploads. Aguarde {RATE_LIMIT_WINDOW_SECONDS} segundos.",
                "retry_after": RATE_LIMIT_WINDOW_SECONDS,
                "type": "user",
                "limit": RATE_LIMIT_UPLOAD_PER_USER
            }
        )
    
    logger.info(f"✅ Rate limits OK para {current_user.email}")
    
    # ==============================================
    # 🔥 3. VERIFICA CRÉDITOS
    # ==============================================
    
    credit_check = validate_credits(current_user, total_arquivos)
    
    if not credit_check["valid"]:
        logger.warning(f"❌ Créditos insuficientes: {current_user.email} (tem {credit_check['credits_available']}, precisa {credit_check['credits_needed']})")
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
    
    arquivos_processados = []
    arquivos_com_erro = []
    files_to_process = []
    analyses_created = []
    
    for idx, file in enumerate(files):
        try:
            # Validar nome
            if not file.filename:
                arquivos_com_erro.append({
                    "filename": f"arquivo_{idx}",
                    "error": "Arquivo sem nome"
                })
                continue
            
            # Validar extensão
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                arquivos_com_erro.append({
                    "filename": file.filename,
                    "error": f"Formato não suportado. Use: {', '.join(ALLOWED_EXTENSIONS)}"
                })
                continue
            
            # Validar tamanho
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                arquivos_com_erro.append({
                    "filename": file.filename,
                    "error": f"Arquivo excede o limite de {MAX_FILE_SIZE//1024}KB. Tamanho: {len(content)/1024:.2f}KB"
                })
                continue
            
            # 🔥 Criar análise com métricas de PoW
            analysis = create_analysis_with_pow_metrics(
                db=db,
                user_id=current_user.id,
                filename=file.filename,
                file_size=len(content),
                analysis_type=analysis_type,
                ai_model=ai_model,
                request=request,
                pow_valid=pow_valid,
                pow_difficulty=int(pow_difficulty) if pow_difficulty else PoWConfig.DEFAULT_DIFFICULTY,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            analyses_created.append(analysis)
            
            # Criar ID de processo
            process_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now()
            
            processing_status[process_id] = {
                "process_id": process_id,
                "status": "uploaded",
                "progress": 10,
                "filename": file.filename,
                "file_size": len(content),
                "user_id": current_user.id,
                "user_email": current_user.email,
                "analysis_id": analysis.id,
                "created_at": timestamp.isoformat(),
                "analysis_type": analysis_type,
                "ai_model": ai_model,
                "batch_index": idx,
                "batch_total": total_arquivos,
                "message": "Arquivo recebido, iniciando ML Pipeline...",
                "credits_consumed": False,
                "encoding_used": None,
                # 🔥 NOVOS CAMPOS
                "rate_limit": {
                    "ip_limit": RATE_LIMIT_UPLOAD_PER_IP,
                    "user_limit": RATE_LIMIT_UPLOAD_PER_USER,
                    "window_seconds": RATE_LIMIT_WINDOW_SECONDS
                },
                "pow_validated": pow_valid,
                "pow_difficulty": int(pow_difficulty) if pow_difficulty else 4,
                "pow_challenge": pow_challenge,
                "pow_nonce": pow_nonce,
            }
            
            files_to_process.append((process_id, content, file.filename))
            
            arquivos_processados.append({
                "filename": file.filename,
                "process_id": process_id,
                "analysis_id": analysis.id,
                "status": "processing"
            })
            
            logger.info(f"✅ Arquivo {idx+1}/{total_arquivos} aceito: {file.filename} (análise ID: {analysis.id})")
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo {file.filename}: {e}")
            arquivos_com_erro.append({
                "filename": file.filename if hasattr(file, 'filename') else f"arquivo_{idx}",
                "error": str(e)
            })
    
    # ==============================================
    # 🔥 5. INICIAR ML PIPELINE EM BACKGROUND
    # ==============================================
    
    if files_to_process:
        logger.info(f"🤖 Iniciando ML Pipeline para {len(files_to_process)} arquivo(s)")
        asyncio.create_task(process_multiple_files_with_ml(
            files_to_process, 
            current_user.id, 
            db
        ))
    
    # ==============================================
    # 🔥 6. RESPOSTA
    # ==============================================
    
    processing_time_ms = (time.time() - start_time) * 1000
    credits_display = get_credits_display(current_user)
    
    # Estatísticas do pipeline
    pipeline_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    encoding_stats = pipeline.get_encoding_stats() if hasattr(pipeline, 'get_encoding_stats') else {}
    
    # 🔥 Estatísticas do PoW
    pow_stats = pow_service.get_stats() if hasattr(pow_service, 'get_stats') else {}
    
    return {
        "success": len(arquivos_com_erro) == 0,
        "message": f"Processado {len(arquivos_processados)} de {total_arquivos} arquivo(s). ML Pipeline iniciado.",
        "total_files": total_arquivos,
        "processed_files": arquivos_processados,
        "failed_files": arquivos_com_erro,
        "credits_before": current_user.credits if not current_user.is_admin else "∞",
        "credits_display": credits_display,
        "is_admin": current_user.is_admin,
        "processing_time_ms": processing_time_ms,
        "batch_info": {
            "max_files_allowed": MAX_FILES_PER_BATCH,
            "uploaded": total_arquivos,
            "accepted": len(arquivos_processados),
            "failed": len(arquivos_com_erro),
            "ml_processing_started": len(files_to_process) > 0,
            "credits_charged_after_success": True,
            "ml_pipeline": {
                "available": True,
                "encoding_detection": "auto",
                "model_source": pipeline_status.get('model_source', 'unknown')
            }
        },
        # 🔥 INFORMAÇÕES DE SEGURANÇA
        "security": {
            "pow_validated": pow_valid,
            "pow_difficulty": int(pow_difficulty) if pow_difficulty else 4,
            "pow_algorithm": PoWConfig.ALGORITHM,
            "pow_challenge": pow_challenge[:8] + "..." if pow_challenge else None,
            "rate_limit": {
                "ip_limit": RATE_LIMIT_UPLOAD_PER_IP,
                "user_limit": RATE_LIMIT_UPLOAD_PER_USER,
                "window_seconds": RATE_LIMIT_WINDOW_SECONDS
            },
            "client_ip": client_ip,
            "pow_stats": {
                "total_challenges_verified": pow_stats.get("challenges", {}).get("verified", 0),
                "replay_attacks_blocked": pow_stats.get("challenges", {}).get("replay_attacks_blocked", 0),
            }
        },
        # 🔥 ESTATÍSTICAS DE ENCODING
        "encoding_stats": encoding_stats,
        "timestamp": datetime.now().isoformat()
    }


# ==============================================
# 🔥 ROTA: STATUS DO PROCESSAMENTO
# ==============================================

@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Verifica status do processamento (inclui resultados do ML)"""
    
    if process_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    status_data = processing_status[process_id]
    
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Adicionar encoding se disponível
    if 'encoding_used' in status_data:
        status_data['encoding_used'] = status_data['encoding_used']
    
    return status_data


# ==============================================
# 🔥 ROTA: HISTÓRICO DE ANÁLISES
# ==============================================

@router.get("/analyses/history")
async def get_analyses_history(
    current_user = Depends(get_current_active_user),
    limit: int = 10
):
    """Retorna histórico de análises do usuário"""
    user_analyses = []
    
    for pid, data in processing_status.items():
        if data.get("user_email") == current_user.email:
            user_analyses.append({
                "id": pid,
                "process_id": pid,
                "filename": data.get("filename"),
                "status": data.get("status"),
                "progress": data.get("progress", 0),
                "created_at": data.get("created_at"),
                "completed_at": data.get("completed_at"),
                "credits_consumed": data.get("credits_consumed", False),
                "encoding_used": data.get("encoding_used"),
                "has_insights": bool(data.get("insights")),
                # 🔥 NOVO
                "pow_validated": data.get("pow_validated", False),
                "pow_difficulty": data.get("pow_difficulty"),
                "rate_limit_info": data.get("rate_limit", {})
            })
    
    user_analyses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {
        "success": True,
        "total": len(user_analyses),
        "analyses": user_analyses[:limit],
        "ml_pipeline": {
            "available": True,
            "encoding_support": "auto"
        }
    }


# ==============================================
# 🔥 ROTA: RESULTADO COMPLETO
# ==============================================

@router.get("/analysis/result/{process_id}")
async def get_analysis_result(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Retorna o resultado completo de uma análise específica"""
    
    if process_id not in processing_status:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    status_data = processing_status[process_id]
    
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if status_data.get("status") != "completed":
        return {
            "success": False,
            "message": "Análise ainda não concluída",
            "status": status_data.get("status"),
            "progress": status_data.get("progress")
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
        "credit_consumed": status_data.get("credits_consumed", False),
        "encoding_used": status_data.get("encoding_used"),
        "model_used": status_data.get("analysis_info", {}).get("model_used"),
        # 🔥 NOVO
        "rate_limit_info": status_data.get("rate_limit", {}),
        "pow_validated": status_data.get("pow_validated", False),
        "pow_difficulty": status_data.get("pow_difficulty"),
        "processing_time_ms": status_data.get("processing_time_ms")
    }


# ==============================================
# 🔥 ROTA: STATUS DO PIPELINE
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
        "rate_limiter": {
            "upload_ip_limit": RATE_LIMIT_UPLOAD_PER_IP,
            "upload_user_limit": RATE_LIMIT_UPLOAD_PER_USER,
            "window_seconds": RATE_LIMIT_WINDOW_SECONDS
        },
        "pow": {
            "enabled": True,
            "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
            "algorithm": PoWConfig.ALGORITHM,
        }
    }


# ==============================================
# 🔥 ROTA: ESTATÍSTICAS DE SEGURANÇA
# ==============================================

@router.get("/security-stats")
async def get_security_stats(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna estatísticas de segurança (apenas admin)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado. Requer permissão de administrador.")
    
    # Contar análises por status
    total_analyses = len(processing_status)
    completed = len([p for p in processing_status.values() if p.get('status') == 'completed'])
    processing = len([p for p in processing_status.values() if p.get('status') == 'processing'])
    error = len([p for p in processing_status.values() if p.get('status') == 'error'])
    
    # Contar por encoding
    encoding_counts = {}
    for p in processing_status.values():
        enc = p.get('encoding_used')
        if enc:
            encoding_counts[enc] = encoding_counts.get(enc, 0) + 1
    
    # 🔥 Estatísticas de PoW
    pow_stats = pow_service.get_stats() if hasattr(pow_service, 'get_stats') else {}
    
    # 🔥 Contar análises com PoW validado
    pow_validated_count = len([p for p in processing_status.values() if p.get('pow_validated') == True])
    
    return {
        "success": True,
        "total_analyses": total_analyses,
        "by_status": {
            "completed": completed,
            "processing": processing,
            "error": error
        },
        "encoding_distribution": encoding_counts,
        "rate_limiter": {
            "ip_limit": RATE_LIMIT_UPLOAD_PER_IP,
            "user_limit": RATE_LIMIT_UPLOAD_PER_USER,
            "window_seconds": RATE_LIMIT_WINDOW_SECONDS
        },
        "pow": {
            "enabled": True,
            "default_difficulty": PoWConfig.DEFAULT_DIFFICULTY,
            "algorithm": PoWConfig.ALGORITHM,
            "total_validated": pow_stats.get("challenges", {}).get("verified", 0),
            "analyses_with_pow": pow_validated_count,
            "replay_attacks_blocked": pow_stats.get("challenges", {}).get("replay_attacks_blocked", 0),
        },
        "timestamp": datetime.now().isoformat()
    }


print("=" * 60)
print("🔥 upload_routes.py - VERSÃO V2.0 COM INTEGRAÇÃO POW")
print(f"   🚦 Rate Limiter: {RATE_LIMIT_UPLOAD_PER_IP}/IP + {RATE_LIMIT_UPLOAD_PER_USER}/usuário em {RATE_LIMIT_WINDOW_SECONDS}s")
print(f"   🔐 PoW: {PoWConfig.ALGORITHM} com dificuldade adaptativa")
print("   🧠 ML Pipeline: Encoding automático + RandomForest/Ensemble/AutoML")
print("   📁 Limites: 3 arquivos, 200KB cada")
print("   📊 Métricas de PoW salvas no banco")
print("=" * 60)