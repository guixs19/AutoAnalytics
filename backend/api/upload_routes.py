# backend/api/upload_routes.py - ROTAS DE UPLOAD E ANÁLISE
"""
Rotas para upload e processamento de arquivos
Suporte a múltiplos arquivos (até 3 por vez) com ML real
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging
import os
import uuid
from datetime import datetime, timedelta
import json
import asyncio
import time 
from backend.database import get_db
from backend import crud, models
from backend.security import get_current_active_user, jwt_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Armazenamento temporário para status de processamento
processing_status = {}

# Limites
MAX_FILE_SIZE = 15 * 1024  # 15KB
MAX_FILES_PER_BATCH = 3     # 🔥 Máximo de 3 arquivos por vez
ALLOWED_EXTENSIONS = ['.csv', '.xlsx', '.xls']


# ==============================================
# PROCESSAMENTO ML EM BACKGROUND PARA MÚLTIPLOS ARQUIVOS
# ==============================================

async def process_multiple_files_with_ml(files_to_process: List[tuple], user_email: str):
    """
    Processa múltiplos arquivos com o modelo de ML em background
    files_to_process: Lista de (process_id, content, filename)
    """
    from backend.ml.predict import predictor
    
    # Garantir que os modelos estão carregados
    await predictor.load_or_train_models()
    
    # Preparar dados para o predictor
    files_data = []
    for process_id, content, filename in files_to_process:
        files_data.append({
            'process_id': process_id,
            'content': content,
            'filename': filename
        })
    
    # Atualizar status para "processando"
    for process_id, _, filename in files_to_process:
        if process_id in processing_status:
            processing_status[process_id]['status'] = 'processing'
            processing_status[process_id]['progress'] = 20
            processing_status[process_id]['message'] = 'Iniciando análise com ML...'
            logger.info(f"🤖 Iniciando processamento ML para: {filename}")
    
    # Processar todos os arquivos com ML
    try:
        results = await predictor.predict_multiple_files(files_data)
        
        # Atualizar status para cada arquivo
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
                    
                    logger.info(f"✅ ML concluído: {result.get('filename')} - {result.get('stats', {}).get('rows', 0)} linhas")
                else:
                    processing_status[process_id]['status'] = 'error'
                    processing_status[process_id]['progress'] = 100
                    processing_status[process_id]['error'] = result.get('error', 'Erro desconhecido no processamento ML')
                    logger.error(f"❌ ML falhou: {result.get('filename')} - {result.get('error')}")
    
    except Exception as e:
        logger.error(f"❌ Erro no processamento ML em lote: {e}")
        for process_id, _, filename in files_to_process:
            if process_id in processing_status:
                processing_status[process_id]['status'] = 'error'
                processing_status[process_id]['error'] = str(e)
                processing_status[process_id]['progress'] = 100


# ==============================================
# UPLOAD MÚLTIPLO (ATÉ 3 ARQUIVOS) COM ML REAL
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    files: List[UploadFile] = File(...),  # 🔥 Aceita múltiplos arquivos
    analysis_type: str = Form("auto"),
    ai_model: str = Form("auto"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Upload de múltiplos arquivos para análise com ML real (até 3 por vez)
    Cada arquivo consome 1 crédito
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 1. Valida a quantidade de arquivos enviados no lote
    total_arquivos = len(files)
    
    if total_arquivos == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado")
    
    if total_arquivos > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite ultrapassado. Você pode enviar no máximo {MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📦 Recebendo lote de {total_arquivos} arquivo(s) de {current_user.email}")
    
    # 2. Verifica se o usuário tem créditos suficientes
    if not current_user.is_admin:
        if current_user.credits < total_arquivos:
            raise HTTPException(
                status_code=400, 
                detail=f"Créditos insuficientes. Você tentou processar {total_arquivos} arquivo(s), mas seu saldo atual é de {current_user.credits} crédito(s)."
            )
    
    # 3. Processa cada arquivo individualmente (validações)
    arquivos_processados = []
    arquivos_com_erro = []
    files_to_process = []  # Lista para processamento ML
    
    for idx, file in enumerate(files):
        try:
            # Validar nome do arquivo
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
            
            # Criar registro de análise
            analysis_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now()
            
            # Salvar em processing_status
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
                "message": "Arquivo recebido, aguardando processamento ML..."
            }
            
            # Adicionar à lista para processamento ML
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
    
    # 4. Deduz os créditos (apenas para arquivos validados com sucesso)
    credits_deducted = 0
    if not current_user.is_admin and len(arquivos_processados) > 0:
        success = crud.deduct_credits(db, current_user, len(arquivos_processados), 
                                      f"Processamento ML de {len(arquivos_processados)} arquivo(s): {', '.join([a['filename'] for a in arquivos_processados])}")
        if success:
            credits_deducted = len(arquivos_processados)
            logger.info(f"💰 Deduzidos {credits_deducted} crédito(s) de {current_user.email}")
            db.refresh(current_user)
    
    # 5. Iniciar processamento ML real em background (se houver arquivos)
    if files_to_process:
        logger.info(f"🤖 Iniciando processamento ML para {len(files_to_process)} arquivo(s)")
        asyncio.create_task(process_multiple_files_with_ml(files_to_process, current_user.email))
    
    # 6. Retornar resposta consolidada
    return {
        "success": len(arquivos_com_erro) == 0,
        "message": f"Processado {len(arquivos_processados)} de {total_arquivos} arquivo(s) - ML iniciado",
        "total_files": total_arquivos,
        "processed_files": arquivos_processados,
        "failed_files": arquivos_com_erro,
        "credits_deducted": credits_deducted,
        "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
        "batch_info": {
            "max_files_allowed": MAX_FILES_PER_BATCH,
            "uploaded": total_arquivos,
            "accepted": len(arquivos_processados),
            "failed": len(arquivos_com_erro),
            "ml_processing_started": len(files_to_process) > 0
        }
    }


# ==============================================
# STATUS DO PROCESSAMENTO
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
    
    # Verificar se o usuário é dono do processo ou admin
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Se for admin, adicionar badge
    if current_user.is_admin:
        status_data['is_admin_view'] = True
    
    return status_data


@router.get("/batch-status")
async def get_batch_status(
    process_ids: str,
    current_user = Depends(get_current_active_user)
):
    """
    Verifica status de múltiplos processos em lote
    Use: /batch-status?process_ids=id1,id2,id3
    """
    ids = process_ids.split(',')
    results = []
    
    for pid in ids:
        pid = pid.strip()
        if pid in processing_status:
            status_data = processing_status[pid]
            if status_data.get("user_email") == current_user.email or current_user.is_admin:
                results.append({
                    "process_id": pid,
                    "status": status_data.get("status"),
                    "progress": status_data.get("progress"),
                    "filename": status_data.get("filename"),
                    "message": status_data.get("message", ""),
                    "completed_at": status_data.get("completed_at"),
                    "analysis_info": status_data.get("analysis_info")
                })
    
    return {
        "success": True,
        "total": len(results),
        "processes": results
    }


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
                "file_size": data.get("file_size"),
                "analysis_info": data.get("analysis_info"),
                "prediction_stats": data.get("prediction_stats")
            })
    
    # Ordenar por data (mais recente primeiro)
    user_analyses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {
        "success": True,
        "total": len(user_analyses),
        "analyses": user_analyses[:limit],
        "max_files_per_batch": MAX_FILES_PER_BATCH,
        "max_file_size_kb": MAX_FILE_SIZE // 1024
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
    
    # Contar análises concluídas hoje
    for a in user_analyses:
        completed = a.get("completed_at")
        if completed:
            completed_date = datetime.fromisoformat(completed).date()
            if completed_date == today and a.get("status") == "completed":
                analyses_today += 1
    
    # Contar análises em andamento
    in_progress = len([a for a in user_analyses if a.get("status") not in ["completed", "error"]])
    
    return {
        "success": True,
        "total_analises": len(user_analyses),
        "analises_hoje": analyses_today,
        "analises_andamento": in_progress,
        "total_credits": current_user.credits if not current_user.is_admin else "∞",
        "is_admin": current_user.is_admin,
        "max_files_per_batch": MAX_FILES_PER_BATCH,
        "max_file_size_kb": MAX_FILE_SIZE // 1024,
        "ml_status": {
            "model_loaded": True,
            "supports_batch": True
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
    
    # Verificar permissão
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
        "completed_at": status_data.get("completed_at"),
        "file_size_kb": status_data.get("file_size", 0) / 1024 if status_data.get("file_size") else 0
    }


@router.get("/payments/balance")
async def get_balance(
    current_user = Depends(get_current_active_user)
):
    """Retorna saldo de créditos do usuário"""
    
    return {
        "success": True,
        "credits": current_user.credits if not current_user.is_admin else "∞",
        "credits_numeric": current_user.credits if not current_user.is_admin else 999999,
        "is_admin": current_user.is_admin,
        "plan": {
            "is_premium": current_user.plan == "premium_mensal",
            "name": current_user.plan
        },
        "max_files_per_batch": MAX_FILES_PER_BATCH,
        "max_file_size_kb": MAX_FILE_SIZE // 1024
    }


@router.get("/premium/status")
async def get_premium_status(
    current_user = Depends(get_current_active_user)
):
    """Retorna status do plano premium"""
    
    is_premium = current_user.plan == "premium_mensal"
    
    return {
        "success": True,
        "has_premium": is_premium,
        "plan": {
            "name": current_user.plan,
            "is_premium": is_premium,
            "days_left": current_user.get_premium_days_left() if hasattr(current_user, 'get_premium_days_left') else (30 if is_premium else 0)
        },
        "max_files_per_batch": MAX_FILES_PER_BATCH
    }


@router.post("/premium/check-daily")
async def check_daily_credit(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Verifica e adiciona crédito diário para premium"""
    
    if current_user.plan != "premium_mensal":
        return {"success": False, "message": "Plano premium não ativo"}
    
    from backend.scheduler.daily_credits_job import DailyCreditsService
    
    service = DailyCreditsService()
    result = service.check_and_add_daily_credit(db, current_user.id)
    
    # Atualizar o objeto do usuário
    db.refresh(current_user)
    
    return result


# ==============================================
# FUNÇÃO PARA INCLUIR ROTAS NO MAIN
# ==============================================

def include_upload_routes(app):
    """Inclui as rotas de upload no app principal"""
    app.include_router(router, prefix="/api")
    logger.info("✅ Rotas de upload configuradas (suporte a múltiplos arquivos com ML real)")