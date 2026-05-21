# backend/api/upload_routes.py - ROTAS DE UPLOAD E ANÁLISE
"""
Rotas para upload e processamento de arquivos
Suporte a múltiplos arquivos (até 3 por vez)
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
# UPLOAD MÚLTIPLO (ATÉ 3 ARQUIVOS)
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    files: List[UploadFile] = File(...),  # 🔥 Agora aceita múltiplos arquivos
    analysis_type: str = Form("auto"),
    ai_model: str = Form("auto"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Upload de múltiplos arquivos para análise (até 3 por vez)
    Cada arquivo consome 1 crédito
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # 1. Valida a quantidade de ficheiros enviados no lote
    total_arquivos = len(files)
    
    if total_arquivos == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado")
    
    if total_arquivos > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite ultrapassado. Você pode enviar no máximo {MAX_FILES_PER_BATCH} arquivos por vez."
        )
    
    logger.info(f"📦 Recebendo lote de {total_arquivos} arquivo(s) de {current_user.email}")
    
    # 2. Verifica se o utilizador tem créditos suficientes para o total de ficheiros
    if not current_user.is_admin:
        if current_user.credits < total_arquivos:
            raise HTTPException(
                status_code=400, 
                detail=f"Créditos insuficientes. Você tentou processar {total_arquivos} arquivo(s), mas seu saldo atual é de {current_user.credits} crédito(s)."
            )
    
    # 3. Processa cada arquivo individualmente
    resultados = []
    arquivos_processados = []
    arquivos_com_erro = []
    
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
                "batch_total": total_arquivos
            }
            
            # Iniciar processamento em background
            asyncio.create_task(simulate_processing(analysis_id, content, file.filename))
            
            arquivos_processados.append({
                "filename": file.filename,
                "process_id": analysis_id,
                "status": "processing"
            })
            
            resultados.append({
                "filename": file.filename,
                "process_id": analysis_id,
                "status": "accepted",
                "message": "Arquivo recebido e em processamento"
            })
            
            logger.info(f"✅ Arquivo {idx+1}/{total_arquivos} aceito: {file.filename}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo {file.filename}: {e}")
            arquivos_com_erro.append({
                "filename": file.filename,
                "error": str(e)
            })
    
    # 4. Deduz a quantidade exata de créditos (apenas para arquivos processados com sucesso)
    credits_deducted = 0
    if not current_user.is_admin and len(arquivos_processados) > 0:
        success = crud.deduct_credits(db, current_user, len(arquivos_processados), 
                                      f"Processamento de {len(arquivos_processados)} arquivo(s): {', '.join([a['filename'] for a in arquivos_processados])}")
        if success:
            credits_deducted = len(arquivos_processados)
            logger.info(f"💰 Deduzidos {credits_deducted} crédito(s) de {current_user.email}")
    
    # 5. Retornar resposta consolidada
    return {
        "success": len(arquivos_com_erro) == 0,
        "message": f"Processado {len(arquivos_processados)} de {total_arquivos} arquivo(s)",
        "total_files": total_arquivos,
        "processed_files": arquivos_processados,
        "failed_files": arquivos_com_erro,
        "credits_deducted": credits_deducted,
        "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
        "batch_info": {
            "max_files_allowed": MAX_FILES_PER_BATCH,
            "uploaded": total_arquivos,
            "accepted": len(arquivos_processados),
            "failed": len(arquivos_com_erro)
        }
    }


async def simulate_processing(process_id: str, content: bytes, filename: str):
    """Simula processamento em background"""
    
    # Atualiza status
    processing_status[process_id]["status"] = "analyzing"
    processing_status[process_id]["progress"] = 30
    
    await asyncio.sleep(2)  # Simula tempo de processamento
    
    processing_status[process_id]["status"] = "processing"
    processing_status[process_id]["progress"] = 60
    
    await asyncio.sleep(2)
    
    # Completa
    processing_status[process_id]["status"] = "completed"
    processing_status[process_id]["progress"] = 100
    processing_status[process_id]["completed_at"] = datetime.now().isoformat()
    processing_status[process_id]["analysis_info"] = {
        "rows_processed": 100,
        "columns_detected": 5,
        "model_used": "AutoML",
        "target_column": "auto_detected"
    }
    processing_status[process_id]["prediction_stats"] = {
        "total": 100,
        "accuracy": 0.94
    }
    
    logger.info(f"✅ Processamento concluído: {process_id} - {filename}")


@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user = Depends(get_current_active_user)
):
    """Verifica status do processamento"""
    
    if process_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    status_data = processing_status[process_id]
    
    # Verificar se o usuário é dono do processo ou admin
    if status_data.get("user_email") != current_user.email and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
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
                    "filename": status_data.get("filename")
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
    
    # Buscar do processing_status ou do banco
    user_analyses = []
    
    for pid, data in processing_status.items():
        if data.get("user_email") == current_user.email:
            user_analyses.append({
                "id": pid,
                "process_id": pid,
                "filename": data.get("filename"),
                "status": data.get("status"),
                "created_at": data.get("created_at"),
                "completed_at": data.get("completed_at")
            })
    
    # Ordenar por data (mais recente primeiro)
    user_analyses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {
        "success": True,
        "total": len(user_analyses),
        "analyses": user_analyses[:limit],
        "max_files_per_batch": MAX_FILES_PER_BATCH
    }


@router.get("/stats")
async def get_dashboard_stats(
    current_user = Depends(get_current_active_user)
):
    """Retorna estatísticas do dashboard"""
    
    # Contar análises do usuário
    user_analyses = [a for a in processing_status.values() 
                     if a.get("user_email") == current_user.email]
    
    analyses_today = 0
    today = datetime.now().date()
    
    for a in user_analyses:
        created = a.get("created_at")
        if created:
            created_date = datetime.fromisoformat(created).date()
            if created_date == today:
                analyses_today += 1
    
    return {
        "success": True,
        "total_analises": len(user_analyses),
        "analises_hoje": analyses_today,
        "total_credits": current_user.credits if not current_user.is_admin else "∞",
        "is_admin": current_user.is_admin,
        "max_files_per_batch": MAX_FILES_PER_BATCH,
        "max_file_size_kb": MAX_FILE_SIZE // 1024
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
        "max_files_per_batch": MAX_FILES_PER_BATCH
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
            "days_left": 30 if is_premium else 0
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
    
    # Importar serviço aqui para evitar circular import
    from backend.services.daily_credits_job import DailyCreditsService
    
    service = DailyCreditsService()
    result = service.check_and_add_daily_credit(db, current_user.id)
    
    return result


# ==============================================
# FUNÇÃO PARA INCLUIR ROTAS NO MAIN
# ==============================================

def include_upload_routes(app):
    """Inclui as rotas de upload no app principal"""
    app.include_router(router, prefix="/api")
    logger.info("✅ Rotas de upload configuradas (suporte a múltiplos arquivos)")