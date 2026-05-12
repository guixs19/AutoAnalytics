# backend/api/routes.py - VERSÃO REFATORADA
"""
ROUTES.PY - Versão limpa usando Service Factory
✅ Sem imports dinâmicos no meio do código
✅ Injeção de dependências via FastAPI
✅ Foco apenas nas rotas
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import uuid
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import traceback
import logging

# ==============================================
# IMPORTS CENTRALIZADOS (todos no topo)
# ==============================================

# FastAPI e dependências
from functools import wraps

# Banco de dados e modelos
from backend.database import get_db
from backend import crud, schemas
from backend.auth import get_current_user
from backend.models import User, UserPlan
from backend.crud import get_credits_display, check_credits, deduct_credits

# Configurações
from backend.config.settings import settings

# Service Factory (em vez de imports dinâmicos)
from backend.services.service_factory import (
    get_service_factory,
    get_file_manager,
    get_preprocessor,
    get_gemini_service,
    get_predictor,
    get_daily_credits_service,
    is_gemini_available
)

# Utilitários
from backend.utils.analytics_helpers import (
    normalize_predictions,
    calculate_prediction_stats,
    auto_detect_target
)

# Configurar logging
logger = logging.getLogger(__name__)

# ==============================================
# INICIALIZAÇÃO
# ==============================================

router = APIRouter()

# Cache em memória para processamentos ativos
processing_cache = {}

# Obtém fábrica de serviços e verifica disponibilidade
service_factory = get_service_factory()
SERVICES_STATUS = service_factory.get_status()
CRITICAL_SERVICES_OK = service_factory.get_critical_services_status()

logger.info(f"📊 Status dos serviços: {SERVICES_STATUS}")
logger.info(f"✅ Serviços críticos OK: {CRITICAL_SERVICES_OK}")


# ==============================================
# DEPENDÊNCIAS INJETADAS (FastAPI style)
# ==============================================

async def get_available_preprocessor():
    """Dependency que fornece o preprocessador se disponível"""
    if not service_factory.is_available('preprocessor'):
        raise HTTPException(
            status_code=503,
            detail="Preprocessador não disponível"
        )
    preprocessor = get_preprocessor()
    if preprocessor is None:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível inicializar o preprocessador"
        )
    return preprocessor


async def get_available_gemini():
    """Dependency que fornece o Gemini se disponível"""
    if not is_gemini_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "GeminiService indisponível",
                "message": "O serviço de IA não está configurado. Verifique GEMINI_API_KEY no .env",
                "action": "Contate o administrador do sistema"
            }
        )
    gemini = get_gemini_service()
    if gemini is None:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível inicializar o GeminiService"
        )
    return gemini


async def get_available_predictor():
    """Dependency que fornece o predictor se disponível"""
    if not service_factory.is_available('predictor'):
        return None  # Predictor é opcional
    return get_predictor()


# ==============================================
# FUNÇÕES AUXILIARES
# ==============================================

def update_status(process_id: str, status: str, progress: int, message: str = ""):
    """Atualiza status do processamento no cache"""
    if process_id in processing_cache:
        processing_cache[process_id].update({
            "status": status,
            "progress": progress,
            "updated_at": datetime.now().isoformat(),
            "stage": message or status
        })
        logger.debug(f"   [{progress}%] {message}")


def check_user_credits_before_upload(user: User, db: Session) -> Dict:
    """Verifica créditos antes do upload"""
    if user.is_admin:
        return {
            "can_proceed": True,
            "credits_display": "∞",
            "credits_remaining": "∞",
            "message": "👑 Admin - créditos ilimitados",
            "is_admin": True
        }
    
    if user.credits <= 0:
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        if is_premium:
            return {
                "can_proceed": False,
                "credits_display": "0",
                "credits_remaining": 0,
                "message": "Você usou todos seus créditos. Amanhã você ganha mais 1 do plano premium!",
                "suggestion": "Volte amanhã ou compre mais créditos",
                "is_premium": True
            }
        else:
            return {
                "can_proceed": False,
                "credits_display": "0",
                "credits_remaining": 0,
                "message": "Você não tem créditos suficientes",
                "suggestion": "Compre créditos na página de planos",
                "is_premium": False
            }
    
    return {
        "can_proceed": True,
        "credits_display": str(user.credits),
        "credits_remaining": user.credits - 1,
        "credits_before": user.credits,
        "message": f"Você tem {user.credits} créditos. Esta análise consumirá 1 crédito."
    }


def update_user_credits_after_upload(db: Session, user: User, filename: str, is_admin: bool = False) -> Dict:
    """Atualiza créditos após upload"""
    if is_admin or user.is_admin:
        return {
            "success": True,
            "credits_before": "∞",
            "credits_after": "∞",
            "credits_display": "∞",
            "message": "👑 Admin - créditos ilimitados, nenhum crédito foi consumido",
            "credits_consumed": 0
        }
    
    credits_before = user.credits
    
    success = deduct_credits(db, user, 1, f"Análise Gemini: {filename}")
    
    if success:
        db.refresh(user)
        return {
            "success": True,
            "credits_before": credits_before,
            "credits_after": user.credits,
            "credits_display": str(user.credits),
            "message": f"1 crédito consumido. Saldo restante: {user.credits}",
            "credits_consumed": 1
        }
    else:
        return {
            "success": False,
            "credits_before": credits_before,
            "credits_after": credits_before,
            "credits_display": str(credits_before),
            "message": "Erro ao consumir crédito",
            "credits_consumed": 0
        }


# ==============================================
# ENDPOINTS PÚBLICOS
# ==============================================

@router.get("/test")
async def test_endpoint():
    """Endpoint de teste público com diagnóstico completo"""
    return {
        "message": "API funcionando com Google Gemini!",
        "timestamp": datetime.now().isoformat(),
        "services_status": SERVICES_STATUS,
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "missing_critical": service_factory.get_missing_critical_services(),
        "gemini_available": is_gemini_available()
    }


@router.get("/health")
async def health_check():
    """Health check com diagnóstico detalhado"""
    return {
        "status": "healthy" if CRITICAL_SERVICES_OK else "degraded",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api": "online",
            "file_manager": "online" if SERVICES_STATUS.get("file_manager") else "offline",
            "preprocessor": "online" if SERVICES_STATUS.get("preprocessor") else "offline",
            "ai_service": "online" if SERVICES_STATUS.get("gemini") else "offline",
            "ai_provider": "Google Gemini",
            "gemini_api_key": "configured" if SERVICES_STATUS.get("gemini_api_configured") else "missing",
            "predictor": "online" if SERVICES_STATUS.get("predictor") else "offline",
            "automl": "online" if SERVICES_STATUS.get("automl") else "offline",
            "boosting_ensemble": "online" if SERVICES_STATUS.get("boosting") else "offline",
            "daily_credits": "online" if SERVICES_STATUS.get("daily_credits") else "offline",
            "jwt_auth": "enabled"
        },
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "recommendations": [
            "Configure GEMINI_API_KEY no arquivo .env" if not SERVICES_STATUS.get("gemini_api_configured") else None,
            "Verifique a instalação dos pacotes necessários" if not SERVICES_STATUS.get("gemini") else None,
            "Execute: pip install -r requirements.txt" if not SERVICES_STATUS.get("file_manager") else None
        ]
    }


# ==============================================
# ENDPOINT DE UPLOAD (USANDO DEPENDÊNCIAS INJETADAS)
# ==============================================

@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    analysis_type: str = Query("clientes"),
    ai_model: str = Query("gemini"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    preprocessor: Any = Depends(get_available_preprocessor),
    gemini_service: Any = Depends(get_available_gemini),
    predictor: Any = Depends(get_available_predictor)
):
    """
    Upload de arquivo para análise com Google Gemini
    ✅ Usa injeção de dependências para serviços
    """
    try:
        logger.info(f"📥 Upload: {file.filename}, Usuário: {current_user.email} (Admin: {current_user.is_admin})")
        
        # Verifica créditos
        credit_check = check_user_credits_before_upload(current_user, db)
        
        if not credit_check["can_proceed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Créditos insuficientes",
                    "message": credit_check["message"],
                    "suggestion": credit_check.get("suggestion", "Compre mais créditos"),
                    "credits": current_user.credits,
                    "credits_display": get_credits_display(current_user),
                    "required": 1,
                    "redirect": "/planos.html"
                }
            )
        
        # Valida arquivo
        if not file.filename:
            raise HTTPException(400, "Nome do arquivo inválido")
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Formato {ext} não suportado. Use: {settings.ALLOWED_EXTENSIONS}")
        
        content = await file.read()
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(400, f"Arquivo muito grande. Máximo: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB")
        
        # Salva arquivo usando FileManager via factory
        FileManager = service_factory.get_service('file_manager')
        if FileManager is None:
            raise HTTPException(503, "FileManager não disponível. Contate o administrador.")
        
        temp_path = await FileManager.save_upload(content, file.filename)
        
        # Cria registro no banco
        process_id = str(uuid.uuid4())
        
        analysis_data = schemas.AnalysisCreate(
            filename=file.filename,
            analysis_type=analysis_type
        )
        
        db_analysis = crud.create_analysis(
            db=db,
            analysis=analysis_data,
            user_id=current_user.id
        )
        
        processing_cache[process_id] = {
            "process_id": process_id,
            "analysis_id": db_analysis.id,
            "user_id": current_user.id,
            "user_email": current_user.email,
            "filename": file.filename,
            "analysis_type": analysis_type,
            "status": "uploaded",
            "progress": 0,
            "started_at": datetime.now().isoformat(),
            "is_admin": current_user.is_admin,
            "is_premium": current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
        }
        
        # Task em background (usando as dependências injetadas)
        async def process_file_background():
            await _process_upload(
                process_id=process_id,
                temp_path=temp_path,
                file=file,
                analysis_type=analysis_type,
                current_user=current_user,
                db=db,
                preprocessor=preprocessor,
                gemini_service=gemini_service,
                predictor=predictor
            )
        
        background_tasks.add_task(process_file_background)
        
        return {
            "message": "Arquivo recebido para processamento com Google Gemini",
            "process_id": process_id,
            "analysis_id": db_analysis.id,
            "status": "processing",
            "ai_provider": "gemini",
            "services_available": SERVICES_STATUS
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro no upload: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"Erro interno: {str(e)}")


async def _process_upload(
    process_id: str,
    temp_path: str,
    file: UploadFile,
    analysis_type: str,
    current_user: User,
    db: Session,
    preprocessor,
    gemini_service,
    predictor
):
    """Processamento em background - separado para clareza"""
    credits_update_result = None
    
    try:
        update_status(process_id, "processing", 10, "Iniciando processamento...")
        
        update_status(process_id, "processing", 30, "Pré-processando dados...")
        result = await preprocessor.process_file(temp_path)
        
        if result.get("status") != "success":
            raise Exception(result.get("message", "Erro no pré-processamento"))
        
        predictions = []
        prediction_stats = {}
        ml_insights = {}
        
        if predictor and result.get("dataframe_numeric") is not None:
            df_numeric = result["dataframe_numeric"]
            if not df_numeric.empty:
                update_status(process_id, "processing", 50, "Gerando previsões...")
                predictions = await predictor.predict_for_office(df_numeric)
                prediction_stats = calculate_prediction_stats(predictions)
                
                if hasattr(predictor, 'get_ml_insights_for_gemini'):
                    ml_insights = predictor.get_ml_insights_for_gemini(df_numeric, predictions)
        
        update_status(process_id, "processing", 70, "Analisando com Google Gemini...")
        
        ai_response = await gemini_service.analyze_office_data(
            analysis_type,
            {
                "data_summary": result.get("metadata", {}),
                "prediction_stats": prediction_stats,
                "ml_insights": ml_insights,
                "filename": file.filename,
                "workshop": current_user.workshop_name,
                "total_records": len(result.get("dataframe", [])),
                "timestamp": datetime.now().isoformat()
            }
        )
        
        if not ai_response.get('success', False):
            logger.warning(f"⚠️ Gemini retornou erro: {ai_response.get('message', 'Unknown error')}")
        
        update_status(process_id, "processing", 90, "Gerando relatório...")
        
        credits_update_result = update_user_credits_after_upload(
            db, current_user, file.filename, current_user.is_admin
        )
        
        # Atualiza cache com sucesso
        processing_cache[process_id].update({
            "status": "completed",
            "progress": 100,
            "completed_at": datetime.now().isoformat(),
            "ai_provider": "gemini",
            "gemini_success": ai_response.get('success', False),
            "ai_response": ai_response,
            "prediction_stats": prediction_stats,
            "credits": credits_update_result
        })
        
        # Atualiza banco com resultado
        crud.update_analysis(
            db=db,
            analysis_id=processing_cache[process_id]["analysis_id"],
            updates={
                "status": "completed",
                "result": {
                    "ai_response": ai_response,
                    "prediction_stats": prediction_stats,
                    "ml_insights": ml_insights
                },
                "completed_at": datetime.now()
            }
        )
        
        logger.info(f"✅ Processamento concluído com Gemini: {process_id}")
        
    except Exception as e:
        logger.error(f"❌ Erro no processamento: {e}")
        traceback.print_exc()
        update_status(process_id, "error", 0, f"Erro: {str(e)}")
        
        processing_cache[process_id].update({
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "completed_at": datetime.now().isoformat()
        })
        
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


# ==============================================
# ENDPOINTS DE STATUS
# ==============================================

@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user: User = Depends(get_current_user)
):
    """Retorna status do processamento"""
    if process_id not in processing_cache:
        raise HTTPException(404, "Processo não encontrado")
    
    process_data = processing_cache[process_id].copy()
    
    if process_data.get("user_id") != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Acesso negado")
    
    return process_data


# ==============================================
# ADMIN DIAGNOSTICS
# ==============================================

@router.get("/admin/diagnostics")
async def get_diagnostics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Endpoint de diagnóstico detalhado (apenas admin)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Acesso negado. Apenas administradores.")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "services": SERVICES_STATUS,
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "missing_critical": service_factory.get_missing_critical_services(),
        "gemini_available": is_gemini_available(),
        "environment": {
            "python_version": os.sys.version,
            "debug_mode": settings.DEBUG if hasattr(settings, 'DEBUG') else False
        },
        "cache_size": len(processing_cache),
        "active_processes": list(processing_cache.keys())[:10]  # Limita a 10
    }


print("✅ routes.py carregado - ")