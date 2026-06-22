# backend/api/upload_routes.py - VERSÃO ATUALIZADA COM ML PIPELINE
"""
Rotas para upload e processamento de arquivos
🔥 INTEGRADO COM ML PIPELINE (preprocessing.py)
🔥 SUPORTE A MÚLTIPLOS ARQUIVOS (até 3 por vez)
🔥 VERIFICAÇÃO DE CRÉDITOS E PoW
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
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

# 🔥🔥🔥 NOVO: Importa o pipeline de ML
from backend.preprocessing import process_file_content, pipeline

# 🔥 PoW (se existir)
try:
    from backend.api.pow_routes import validate_pow_request
except ImportError:
    # Fallback se PoW não estiver disponível
    async def validate_pow_request(*args, **kwargs):
        return True

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Armazenamento temporário para status de processamento
processing_status = {}

# Limites
MAX_FILE_SIZE = 200 * 1024  # 200KB
MAX_FILES_PER_BATCH = 3
ALLOWED_EXTENSIONS = ['.csv', '.xlsx', '.xls']


# ==============================================
# 🔥 PROCESSAMENTO ML COM PIPELINE (NOVO)
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
    Usa o novo preprocessing.py
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
    Usa o novo preprocessing.py
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
# 🔥 UPLOAD COM PIPELINE ML (NOVO)
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    files: List[UploadFile] = File(...),
    analysis_type: str = Form("auto"),
    ai_model: str = Form("auto"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Upload de múltiplos arquivos com ML Pipeline
    🔥 VERIFICAÇÃO DE CRÉDITOS ANTES DO UPLOAD
    🔥 CONSUMO DE CRÉDITOS APÓS ANÁLISE BEM-SUCEDIDA
    🔥 ML PIPELINE COM ENCODING AUTOMÁTICO
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 1. Valida quantidade
    total_arquivos = len(files)
    
    if total_arquivos == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado")
    
    if total_arquivos > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite ultrapassado. Máximo {MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📦 Recebendo lote de {total_arquivos} arquivo(s) de {current_user.email}")
    
    # 2. Verifica créditos ANTES do upload
    if not current_user.is_admin:
        if not can_perform_analysis(current_user, total_arquivos):
            credits_msg = f"Créditos insuficientes. Você tem {current_user.credits or 0} crédito(s)."
            logger.warning(f"❌ {credits_msg}")
            raise HTTPException(status_code=400, detail=credits_msg)
    
    # 3. Processa cada arquivo
    arquivos_processados = []
    arquivos_com_erro = []
    files_to_process = []
    
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
            
            # Criar registro
            analysis_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now()
            
            processing_status[analysis_id] = {
                "process_id": analysis_id,
                "status": "uploaded",
                "progress": 10,
                "filename": file.filename,
                "file_size": len(content),
                "user_id": current_user.id,
                "user_email": current_user.email,
                "created_at": timestamp.isoformat(),
                "analysis_type": analysis_type,
                "ai_model": ai_model,
                "batch_index": idx,
                "batch_total": total_arquivos,
                "message": "Arquivo recebido, iniciando ML Pipeline...",
                "credits_consumed": False,
                "encoding_used": None  # Será preenchido pelo pipeline
            }
            
            files_to_process.append((analysis_id, content, file.filename))
            
            arquivos_processados.append({
                "filename": file.filename,
                "process_id": analysis_id,
                "status": "processing"
            })
            
            logger.info(f"✅ Arquivo {idx+1}/{total_arquivos} aceito: {file.filename}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo {file.filename}: {e}")
            arquivos_com_erro.append({
                "filename": file.filename if hasattr(file, 'filename') else f"arquivo_{idx}",
                "error": str(e)
            })
    
    # 4. Iniciar ML Pipeline em background
    if files_to_process:
        logger.info(f"🤖 Iniciando ML Pipeline para {len(files_to_process)} arquivo(s)")
        asyncio.create_task(process_multiple_files_with_ml(
            files_to_process, 
            current_user.id, 
            db
        ))
    
    # 5. Resposta
    credits_display = get_credits_display(current_user)
    
    # 🔥 Adicionar informações do pipeline
    pipeline_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    
    return {
        "success": len(arquivos_com_erro) == 0,
        "message": f"Processado {len(arquivos_processados)} de {total_arquivos} arquivo(s). ML Pipeline iniciado.",
        "total_files": total_arquivos,
        "processed_files": arquivos_processados,
        "failed_files": arquivos_com_erro,
        "credits_before": current_user.credits if not current_user.is_admin else "∞",
        "credits_display": credits_display,
        "is_admin": current_user.is_admin,
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
        }
    }


# ==============================================
# STATUS DO PROCESSAMENTO (MANTIDO)
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
                "has_insights": bool(data.get("insights"))
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
        "filename": status_data.get("filename"),
        "analysis_info": status_data.get("analysis_info", {}),
        "prediction_stats": status_data.get("prediction_stats", {}),
        "insights": status_data.get("insights", {}),
        "recommendations": status_data.get("recommendations", []),
        "completed_at": status_data.get("completed_at"),
        "credit_consumed": status_data.get("credits_consumed", False),
        "encoding_used": status_data.get("encoding_used"),
        "model_used": status_data.get("analysis_info", {}).get("model_used")
    }


# ==============================================
# ESTATÍSTICAS DO PIPELINE
# ==============================================

@router.get("/pipeline-status")
async def get_pipeline_status(
    current_user = Depends(get_current_active_user)
):
    """Retorna status do ML Pipeline"""
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
        }
    }


print("✅ upload_routes.py atualizado com ML Pipeline")
print("   🔥 process_file_content() → Novo pipeline")
print("   🔥 Suporte a encoding automático")
print("   🔥 Insights e recomendações")