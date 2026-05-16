# backend/api/upload_routes.py - ROTAS DE UPLOAD E ANÁLISE
"""
Rotas para upload e processamento de arquivos
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
import time 
from backend.database import get_db
from backend import crud, models
from backend.security import get_current_active_user, jwt_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Armazenamento temporário para status de processamento
processing_status = {}

# ==============================================
# UPLOAD AUTOMÁTICO
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    request: Request,
    file: UploadFile = File(...),
    analysis_type: str = Form("auto"),
    ai_model: str = Form("auto"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Upload automático de arquivo para análise
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # Verificar créditos (exceto admin)
    if not current_user.is_admin:
        if current_user.credits <= 0:
            raise HTTPException(status_code=403, detail="Créditos insuficientes")
    
    # Validar arquivo
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo não selecionado")
    
    # Validar extensão
    allowed_extensions = ['.csv', '.xlsx', '.xls']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Formato não suportado. Use: {', '.join(allowed_extensions)}"
        )
    
    # Validar tamanho (15KB = 15360 bytes)
    MAX_SIZE = 15 * 1024  # 15KB
    content = await file.read()
    
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"Arquivo excede o limite de 15KB. Tamanho atual: {len(content)/1024:.2f}KB"
        )
    
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
        "ai_model": ai_model
    }
    
    # Deduzir crédito (exceto admin)
    if not current_user.is_admin:
        success = crud.deduct_credits(db, current_user, 1, f"Análise: {file.filename}")
        if not success:
            raise HTTPException(status_code=403, detail="Erro ao deduzir crédito")
    
    logger.info(f"✅ Upload recebido: {file.filename} ({len(content)} bytes) - Usuário: {current_user.email}")
    
    # Simular processamento em background
    import asyncio
    asyncio.create_task(simulate_processing(analysis_id, content, file.filename))
    
    return {
        "success": True,
        "message": "Arquivo recebido com sucesso! Processando...",
        "process_id": analysis_id,
        "id": analysis_id,
        "filename": file.filename,
        "status": "uploaded",
        "credits_remaining": current_user.credits - 1 if not current_user.is_admin else "∞"
    }


async def simulate_processing(process_id: str, content: bytes, filename: str):
    """Simula processamento em background"""
    
    # Atualiza status
    processing_status[process_id]["status"] = "analyzing"
    processing_status[process_id]["progress"] = 30
    
    await time.sleep(2)  # Simula tempo de processamento
    
    processing_status[process_id]["status"] = "processing"
    processing_status[process_id]["progress"] = 60
    
    await time.sleep(2)
    
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
    
    logger.info(f"✅ Processamento concluído: {process_id}")


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
    
    return user_analyses[:limit]


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
        "total_analises": len(user_analyses),
        "analises_hoje": analyses_today,
        "total_credits": current_user.credits,
        "is_admin": current_user.is_admin
    }


@router.get("/payments/balance")
async def get_balance(
    current_user = Depends(get_current_active_user)
):
    """Retorna saldo de créditos do usuário"""
    
    return {
        "success": True,
        "credits": current_user.credits,
        "plan": {
            "is_premium": current_user.plan == "premium_mensal",
            "name": current_user.plan
        }
    }


@router.get("/premium/status")
async def get_premium_status(
    current_user = Depends(get_current_active_user)
):
    """Retorna status do plano premium"""
    
    is_premium = current_user.plan == "premium_mensal"
    
    return {
        "has_premium": is_premium,
        "plan": {
            "name": current_user.plan,
            "is_premium": is_premium,
            "days_left": 30 if is_premium else 0
        }
    }


@router.post("/premium/check-daily")
async def check_daily_credit(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Verifica e adiciona crédito diário para premium"""
    
    if current_user.plan != "premium_mensal":
        return {"success": False, "message": "Plano premium não ativo"}
    
    # Verificar se já recebeu hoje
    # (implementar lógica de verificação diária)
    
    return {"success": True, "credits_added": 0, "message": "Verificação diária"}


# ==============================================
# FUNÇÃO PARA INCLUIR ROTAS NO MAIN
# ==============================================

def include_upload_routes(app):
    """Inclui as rotas de upload no app principal"""
    app.include_router(router, prefix="/api")
    logger.info("✅ Rotas de upload configuradas")