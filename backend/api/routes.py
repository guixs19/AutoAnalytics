# backend/api/routes.py - VERSÃO OTIMIZADA COM SERVICE FACTORY
"""
ROUTES.PY - Versão limpa usando Service Factory
✅ Sem imports dinâmicos no meio do código
✅ Injeção de dependências via FastAPI
✅ Foco apenas nas rotas
"""

# backend/api/routes.py - VERSÃO CORRIGIDA (IMPORT DO SECURITY)

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

# Banco de dados e modelos
from backend.database import get_db
from backend import crud, schemas
from backend.security import get_current_user  # <--- CORRIGIDO
from backend.models import User, UserPlan
from backend.crud import get_credits_display, check_credits, deduct_credits

# Configurações
from backend.config.settings import settings

# Service Factory (centralizado)
from backend.services.service_factory import (
    get_service_factory,
    get_file_manager,
    get_preprocessor,
    get_gemini_service,
    get_predictor,
    get_daily_credits_service,
    is_gemini_available
)

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar logging
logger = logging.getLogger(__name__)

# ==============================================
# INICIALIZAÇÃO
# ==============================================

router = APIRouter()

# Cache em memória para processamentos ativos
processing_cache = {}

# Obtém fábrica de serviços
service_factory = get_service_factory()
SERVICES_STATUS = service_factory.get_status()
CRITICAL_SERVICES_OK = service_factory.get_critical_services_status()

logger.info(f"📊 Status dos serviços: {SERVICES_STATUS}")
logger.info(f"✅ Serviços críticos OK: {CRITICAL_SERVICES_OK}")


# ==============================================
# DEPENDÊNCIAS INJETADAS
# ==============================================

async def get_available_preprocessor():
    """Dependency que fornece o preprocessador se disponível"""
    if not service_factory.is_available('preprocessor'):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "preprocessor_unavailable",
                "message": "Preprocessador não disponível. Contate o administrador."
            }
        )
    preprocessor = get_preprocessor()
    if preprocessor is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "preprocessor_init_failed",
                "message": "Não foi possível inicializar o preprocessador"
            }
        )
    return preprocessor


async def get_available_gemini():
    """Dependency que fornece o Gemini se disponível"""
    if not is_gemini_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "gemini_unavailable",
                "message": "O serviço de IA não está configurado. Verifique GEMINI_API_KEY no arquivo .env",
                "action": "Contate o administrador do sistema para configurar a chave da API"
            }
        )
    gemini = get_gemini_service()
    if gemini is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "gemini_init_failed",
                "message": "Não foi possível inicializar o serviço Gemini"
            }
        )
    return gemini


async def get_available_predictor():
    """Dependency que fornece o predictor se disponível (opcional)"""
    if not service_factory.is_available('predictor'):
        return None  # Predictor é opcional
    return get_predictor()


async def get_file_manager_dependency():
    """Dependency que fornece o FileManager"""
    FileManager = service_factory.get_service('file_manager')
    if FileManager is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "file_manager_unavailable",
                "message": "Gerenciador de arquivos não disponível"
            }
        )
    return FileManager


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
                "message": "Você usou todos seus créditos diários. Amanhã você ganha mais créditos!",
                "suggestion": "Volte amanhã ou adquira o plano premium",
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
        "message": f"Você tem {user.credits} crédito(s). Esta análise consumirá 1 crédito."
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
            "message": f"✅ 1 crédito consumido. Saldo restante: {user.credits}",
            "credits_consumed": 1
        }
    else:
        return {
            "success": False,
            "credits_before": credits_before,
            "credits_after": credits_before,
            "credits_display": str(credits_before),
            "message": "❌ Erro ao consumir crédito",
            "credits_consumed": 0
        }


def calculate_prediction_stats(predictions: List) -> Dict:
    """Calcula estatísticas das previsões"""
    if not predictions:
        return {}
    
    try:
        df = pd.DataFrame(predictions)
        return {
            "total_predictions": len(predictions),
            "prediction_distribution": df.value_counts().to_dict() if not df.empty else {},
            "unique_predictions": df.nunique().to_dict() if not df.empty else {},
            "most_common": df.mode().iloc[0].to_dict() if not df.empty and len(df) > 0 else {}
        }
    except Exception as e:
        logger.warning(f"Erro ao calcular stats de previsões: {e}")
        return {"total_predictions": len(predictions)}


# ==============================================
# ENDPOINTS PÚBLICOS
# ==============================================

@router.get("/test")
async def test_endpoint():
    """Endpoint de teste público com diagnóstico completo"""
    return {
        "success": True,
        "message": "API funcionando com Google Gemini!",
        "timestamp": datetime.now().isoformat(),
        "services_status": SERVICES_STATUS,
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "missing_critical": service_factory.get_missing_critical_services(),
        "gemini_available": is_gemini_available(),
        "version": "3.2.0"
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
    analysis_type: str = Query("clientes", description="Tipo de análise: clientes, vendas, orcamentos"),
    ai_model: str = Query("gemini", description="Modelo de IA a ser usado"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    preprocessor: Any = Depends(get_available_preprocessor),
    gemini_service: Any = Depends(get_available_gemini),
    predictor: Any = Depends(get_available_predictor),
    FileManager: Any = Depends(get_file_manager_dependency)
):
    """
    Upload de arquivo para análise com Google Gemini
    
    - **file**: Arquivo CSV ou Excel para análise
    - **analysis_type**: Tipo de análise (clientes, vendas, orcamentos)
    - **ai_model**: Modelo de IA (padrão: gemini)
    """
    try:
        logger.info(f"📥 Upload: {file.filename} | Usuário: {current_user.email} | Admin: {current_user.is_admin}")
        
        # ==============================================
        # VALIDAÇÃO 1: CRÉDITOS
        # ==============================================
        credit_check = check_user_credits_before_upload(current_user, db)
        
        if not credit_check["can_proceed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": credit_check["message"],
                    "suggestion": credit_check.get("suggestion", "Adquira créditos na página de planos"),
                    "credits": current_user.credits,
                    "credits_display": get_credits_display(current_user),
                    "required": 1,
                    "redirect": "/planos"
                }
            )
        
        # ==============================================
        # VALIDAÇÃO 2: ARQUIVO
        # ==============================================
        if not file.filename:
            raise HTTPException(status_code=400, detail={"error": "invalid_filename", "message": "Nome do arquivo inválido"})
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_format",
                    "message": f"Formato {ext} não suportado. Use: {', '.join(settings.ALLOWED_EXTENSIONS)}"
                }
            )
        
        # ==============================================
        # VALIDAÇÃO 3: TAMANHO
        # ==============================================
        content = await file.read()
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"Arquivo muito grande. Máximo: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
                    "max_size_mb": settings.MAX_FILE_SIZE / 1024 / 1024
                }
            )
        
        # ==============================================
        # SALVAR ARQUIVO
        # ==============================================
        temp_path = await FileManager.save_upload(content, file.filename)
        
        # ==============================================
        # CRIAR REGISTRO NO BANCO
        # ==============================================
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
            "is_premium": current_user.plan == UserPlan.PREMIUM_MENSAL and hasattr(current_user, 'is_premium') and current_user.is_premium()
        }
        
        # ==============================================
        # TASK EM BACKGROUND
        # ==============================================
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
                predictor=predictor,
                FileManager=FileManager
            )
        
        background_tasks.add_task(process_file_background)
        
        logger.info(f"✅ Upload iniciado: {process_id[:8]} | Arquivo: {file.filename}")
        
        return {
            "success": True,
            "message": "Arquivo recebido para processamento com Google Gemini",
            "data": {
                "process_id": process_id,
                "analysis_id": db_analysis.id,
                "status": "processing",
                "ai_provider": "gemini",
                "services_available": SERVICES_STATUS,
                "estimated_time": "30-60 segundos"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro no upload: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "upload_failed",
                "message": f"Erro interno ao processar upload: {str(e)}"
            }
        )


async def _process_upload(
    process_id: str,
    temp_path: str,
    file: UploadFile,
    analysis_type: str,
    current_user: User,
    db: Session,
    preprocessor,
    gemini_service,
    predictor,
    FileManager
):
    """Processamento em background - separado para clareza"""
    credits_update_result = None
    
    try:
        update_status(process_id, "processing", 10, "Iniciando processamento...")
        
        # ==============================================
        # PRÉ-PROCESSAMENTO
        # ==============================================
        update_status(process_id, "processing", 30, "Pré-processando dados...")
        result = await preprocessor.process_file(temp_path)
        
        if result.get("status") != "success":
            raise Exception(result.get("message", "Erro no pré-processamento"))
        
        # ==============================================
        # PREVISÕES ML (opcional)
        # ==============================================
        predictions = []
        prediction_stats = {}
        ml_insights = {}
        
        if predictor and result.get("dataframe_numeric") is not None:
            df_numeric = result["dataframe_numeric"]
            if not df_numeric.empty:
                update_status(process_id, "processing", 50, "Gerando previsões com ML...")
                predictions = await predictor.predict_for_office(df_numeric)
                prediction_stats = calculate_prediction_stats(predictions)
                
                if hasattr(predictor, 'get_ml_insights_for_gemini'):
                    ml_insights = predictor.get_ml_insights_for_gemini(df_numeric, predictions)
        
        # ==============================================
        # ANÁLISE COM GEMINI
        # ==============================================
        update_status(process_id, "processing", 70, "Analisando dados com Google Gemini...")
        
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
        
        # ==============================================
        # ATUALIZAR CRÉDITOS
        # ==============================================
        update_status(process_id, "processing", 90, "Atualizando créditos...")
        
        credits_update_result = update_user_credits_after_upload(
            db, current_user, file.filename, current_user.is_admin
        )
        
        # ==============================================
        # SALVAR RESULTADO
        # ==============================================
        processing_cache[process_id].update({
            "status": "completed",
            "progress": 100,
            "completed_at": datetime.now().isoformat(),
            "ai_provider": "gemini",
            "gemini_success": ai_response.get('success', False),
            "ai_response": ai_response,
            "prediction_stats": prediction_stats,
            "ml_insights": ml_insights,
            "credits": credits_update_result
        })
        
        # Atualiza banco de dados
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
        
        logger.info(f"✅ Processamento concluído: {process_id[:8]} | Usuário: {current_user.email}")
        
    except Exception as e:
        logger.error(f"❌ Erro no processamento {process_id[:8]}: {e}")
        traceback.print_exc()
        
        update_status(process_id, "error", 0, f"Erro: {str(e)}")
        
        processing_cache[process_id].update({
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "completed_at": datetime.now().isoformat()
        })
        
        # Atualiza banco com erro
        if "analysis_id" in processing_cache.get(process_id, {}):
            crud.update_analysis(
                db=db,
                analysis_id=processing_cache[process_id]["analysis_id"],
                updates={
                    "status": "error",
                    "error_message": str(e),
                    "completed_at": datetime.now()
                }
            )
        
    finally:
        # Limpeza do arquivo temporário
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug(f"🗑️ Arquivo temporário removido: {temp_path}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao remover arquivo temporário: {e}")


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
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Processo não encontrado"}
        )
    
    process_data = processing_cache[process_id].copy()
    
    # Verificar permissão
    if process_data.get("user_id") != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado a este processo"}
        )
    
    return {
        "success": True,
        "data": process_data
    }


@router.get("/results/{analysis_id}")
async def get_results(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna resultado completo de uma análise"""
    analysis = crud.get_analysis(db, analysis_id)
    
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Análise não encontrada"}
        )
    
    if analysis.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado a esta análise"}
        )
    
    return {
        "success": True,
        "data": {
            "id": analysis.id,
            "filename": analysis.filename,
            "analysis_type": analysis.analysis_type,
            "status": analysis.status,
            "result": analysis.result,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None
        }
    }


# ==============================================
# ENDPOINTS DE RELATÓRIOS
# ==============================================

@router.get("/user/analyses")
async def get_user_analyses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """Retorna todas as análises do usuário"""
    analyses = crud.get_user_analyses(db, current_user.id, skip=skip, limit=limit)
    
    return {
        "success": True,
        "data": [
            {
                "id": a.id,
                "filename": a.filename,
                "analysis_type": a.analysis_type,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None
            }
            for a in analyses
        ],
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": len(analyses)
        }
    }


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
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
    # Contar análises por status
    analyses_stats = crud.get_analyses_stats(db)
    
    return {
        "success": True,
        "data": {
            "timestamp": datetime.now().isoformat(),
            "services": SERVICES_STATUS,
            "critical_services_ok": CRITICAL_SERVICES_OK,
            "missing_critical": service_factory.get_missing_critical_services(),
            "gemini_available": is_gemini_available(),
            "environment": {
                "python_version": os.sys.version,
                "debug_mode": settings.DEBUG if hasattr(settings, 'DEBUG') else False
            },
            "cache": {
                "size": len(processing_cache),
                "active_processes": list(processing_cache.keys())[:10]
            },
            "analyses": analyses_stats
        }
    }


print("✅ routes.py carregado com Service Factory e dependências injetadas")