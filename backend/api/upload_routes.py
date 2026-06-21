# backend/api/upload_routes.py - VERSÃO COM PoW INTEGRADO
"""
Rotas para upload e processamento de arquivos
🔥 INTEGRADO COM PoW (Proof of Work)
🔥 Suporte a múltiplos arquivos (até 3 por vez)
🔥 Verificação de créditos antes do upload
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import os
import uuid
from datetime import datetime
import asyncio

from backend.database import get_db
from backend import crud, models
from backend.security import get_current_active_user
from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display

# 🔥 IMPORTA O PoW
from backend.api.pow_routes import validate_pow_request, pow_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Armazenamento temporário para status de processamento
processing_status = {}

# Limites
MAX_FILE_SIZE = 200 * 1024  # 200KB
MAX_FILES_PER_BATCH = 3     # Máximo de 3 arquivos por vez
ALLOWED_EXTENSIONS = ['.csv', '.xlsx', '.xls']


# ==============================================
# PROCESSAMENTO ML EM BACKGROUND (MANTIDO)
# ==============================================

async def process_multiple_files_with_ml(files_to_process: List[tuple], user_email: str, user_id: int, db: Session):
    """Processa múltiplos arquivos com ML (mantido igual)"""
    from backend.ml.predict import predictor
    
    await predictor.load_or_train_models()
    
    files_data = []
    for process_id, content, filename in files_to_process:
        files_data.append({
            'process_id': process_id,
            'content': content,
            'filename': filename
        })
    
    for process_id, _, filename in files_to_process:
        if process_id in processing_status:
            processing_status[process_id]['status'] = 'processing'
            processing_status[process_id]['progress'] = 20
            processing_status[process_id]['message'] = 'Iniciando análise com ML...'
    
    try:
        results = await predictor.predict_multiple_files(files_data)
        
        for result in results:
            process_id = result.get('process_id')
            if process_id and process_id in processing_status:
                if result.get('success'):
                    processing_status[process_id]['status'] = 'completed'
                    processing_status[process_id]['progress'] = 100
                    processing_status[process_id]['completed_at'] = datetime.now().isoformat()
                    processing_status[process_id]['analysis_info'] = {
                        'rows_processed': result.get('stats', {}).get('rows', 0),
                        'columns_detected': result.get('stats', {}).get('columns', 0),
                        'numeric_columns': result.get('stats', {}).get('numeric_columns', 0),
                        'categorical_columns': result.get('stats', {}).get('categorical_columns', 0),
                        'model_used': result.get('model_used', 'AutoML'),
                        'filename': result.get('filename'),
                        'predictions_summary': result.get('predictions_summary', {}),
                        'top_features': result.get('top_features', []),
                        'insights': result.get('insights', {})
                    }
                    processing_status[process_id]['prediction_stats'] = result.get('predictions_summary', {})
                    processing_status[process_id]['insights'] = result.get('insights', {})
                    
                    # Consumir crédito após análise bem-sucedida
                    from backend.database import SessionLocal
                    db_local = SessionLocal()
                    try:
                        from backend.models import User
                        user = db_local.query(User).filter(User.id == user_id).first()
                        if user and not user.is_admin:
                            success = consume_analysis_credit(user, db_local, 1)
                            if success:
                                processing_status[process_id]['credit_consumed'] = True
                                processing_status[process_id]['credits_remaining'] = user.credits
                    finally:
                        db_local.close()
                    
                else:
                    processing_status[process_id]['status'] = 'error'
                    processing_status[process_id]['error'] = result.get('error', 'Erro desconhecido')
    
    except Exception as e:
        logger.error(f"❌ Erro no processamento ML: {e}")
        for process_id, _, filename in files_to_process:
            if process_id in processing_status:
                processing_status[process_id]['status'] = 'error'
                processing_status[process_id]['error'] = str(e)


# ==============================================
# 🔥 UPLOAD COM VERIFICAÇÃO PoW
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    files: List[UploadFile] = File(...),
    analysis_type: str = Form("auto"),
    ai_model: str = Form("auto"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    # 🔥🔥🔥 DEPENDÊNCIA DO PoW - VALIDA AUTOMATICAMENTE
    pow_valid: bool = Depends(validate_pow_request)
):
    """
    Upload de múltiplos arquivos com VERIFICAÇÃO PoW OBRIGATÓRIA
    
    🔥 REQUER HEADERS:
    - X-PoW-Prefix: prefixo do desafio
    - X-PoW-Nonce: nonce resolvido
    - X-PoW-Complexity: complexidade do desafio
    
    🔥 FLUXO COMPLETO:
    1. Valida PoW (previne bots)
    2. Valida créditos (previne abuso)
    3. Processa arquivos
    4. Inicia ML em background
    5. Consome crédito após sucesso
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 🔥 O PoW JÁ FOI VALIDADO PELA DEPENDÊNCIA
    # Se chegou aqui, o PoW é válido!
    logger.info(f"✅ PoW validado para upload de {current_user.email}")
    
    # 1. Valida a quantidade de arquivos
    total_arquivos = len(files)
    
    if total_arquivos == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado")
    
    if total_arquivos > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite ultrapassado. Máximo {MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📦 Recebendo lote de {total_arquivos} arquivo(s) de {current_user.email}")
    
    # 2. Verifica créditos
    if not current_user.is_admin:
        if not can_perform_analysis(current_user, total_arquivos):
            credits_msg = f"Créditos insuficientes. Você tem {current_user.credits or 0} crédito(s) e tentou processar {total_arquivos} arquivo(s)."
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
            
            processing_status[analysis_id] = {
                "process_id": analysis_id,
                "status": "uploaded",
                "progress": 10,
                "filename": file.filename,
                "file_size": len(content),
                "user_id": current_user.id,
                "user_email": current_user.email,
                "created_at": datetime.now().isoformat(),
                "analysis_type": analysis_type,
                "ai_model": ai_model,
                "batch_index": idx,
                "batch_total": total_arquivos,
                "message": "Arquivo recebido, PoW validado, aguardando ML...",
                "credits_consumed": False,
                "pow_verified": True
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
    
    # 4. Iniciar ML em background
    if files_to_process:
        logger.info(f"🤖 Iniciando ML para {len(files_to_process)} arquivo(s)")
        asyncio.create_task(process_multiple_files_with_ml(
            files_to_process, 
            current_user.email, 
            current_user.id, 
            db
        ))
    
    # 5. Retornar resposta
    credits_display = get_credits_display(current_user)
    
    return {
        "success": len(arquivos_com_erro) == 0,
        "message": f"Processado {len(arquivos_processados)} de {total_arquivos} arquivo(s). PoW validado. Créditos serão consumidos após conclusão da análise.",
        "total_files": total_arquivos,
        "processed_files": arquivos_processados,
        "failed_files": arquivos_com_erro,
        "credits_before": current_user.credits if not current_user.is_admin else "∞",
        "credits_display": credits_display,
        "is_admin": current_user.is_admin,
        "pow": {
            "verified": True,
            "complexity": int(request.headers.get("X-PoW-Complexity", 0)),
            "method": "SHA-256"
        },
        "batch_info": {
            "max_files_allowed": MAX_FILES_PER_BATCH,
            "uploaded": total_arquivos,
            "accepted": len(arquivos_processados),
            "failed": len(arquivos_com_erro),
            "ml_processing_started": len(files_to_process) > 0,
            "credits_charged_after_success": True
        }
    }


# ==============================================
# DEMANDAS ROTAS (MANTIDAS IGUAIS)
# ==============================================

@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Verifica status do processamento"""
    if process_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    status_data = processing_status[process_id]
    
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return status_data


@router.get("/analyses/history")
async def get_analyses_history(
    current_user = Depends(get_current_active_user),
    limit: int = 10
):
    """Retorna histórico de análises"""
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
                "pow_verified": data.get("pow_verified", False)
            })
    
    user_analyses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {
        "success": True,
        "total": len(user_analyses),
        "analyses": user_analyses[:limit]
    }


@router.get("/stats")
async def get_dashboard_stats(
    current_user = Depends(get_current_active_user)
):
    """Retorna estatísticas do dashboard"""
    user_analyses = [a for a in processing_status.values() 
                     if a.get("user_email") == current_user.email]
    
    analyses_today = 0
    today = datetime.now().date()
    
    for a in user_analyses:
        completed = a.get("completed_at")
        if completed:
            completed_date = datetime.fromisoformat(completed).date()
            if completed_date == today and a.get("status") == "completed":
                analyses_today += 1
    
    in_progress = len([a for a in user_analyses if a.get("status") not in ["completed", "error"]])
    
    return {
        "success": True,
        "total_analises": len(user_analyses),
        "analises_hoje": analyses_today,
        "analises_andamento": in_progress,
        "total_credits": get_credits_display(current_user),
        "is_admin": current_user.is_admin,
        "pow_active": True
    }


print("✅ upload_routes.py carregado - COM PoW INTEGRADO")