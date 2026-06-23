# backend/api/routes.py - VERSÃO CORRIGIDA E SINCRONIZADA
"""
ROUTES.PY - Rotas base da API (Gemini, Health, Admin)
✅ CORRIGIDO: response_model=None nas rotas problemáticas
✅ SINCRONIZADO: Com upload_routes.py e preprocessing.py
✅ REMOVIDO: Endpoint /upload duplicado (usar upload_routes.py)
✅ MANTIDO: /analyze (Gemini), /health, /test, /admin/diagnostics
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

# Banco de dados e modelos
from backend.database import get_db
from backend import crud, schemas
from backend.security import get_current_user
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

# 🔥 IMPORTANTE: Importar o pipeline ML para sincronização
from backend.preprocessing import pipeline, process_file_content

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
# ENDPOINTS PÚBLICOS (COM response_model=None)
# ==============================================

@router.get("/test", response_model=None)
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
        "ml_pipeline_available": pipeline.is_initialized,
        "version": "3.2.0"
    }


@router.get("/health", response_model=None)
async def health_check():
    """Health check com diagnóstico detalhado"""
    # Verificar pipeline ML
    ml_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    
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
            "jwt_auth": "enabled",
            "ml_pipeline": ml_status
        },
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "recommendations": [
            "Configure GEMINI_API_KEY no arquivo .env" if not SERVICES_STATUS.get("gemini_api_configured") else None,
            "Verifique a instalação dos pacotes necessários" if not SERVICES_STATUS.get("gemini") else None,
            "Execute: pip install -r requirements.txt" if not SERVICES_STATUS.get("file_manager") else None
        ]
    }


# ==============================================
# 🔥 ENDPOINT /analyze - GEMINI (COM response_model=None)
# ==============================================

@router.post("/analyze", response_model=None)
async def analyze_data(
    background_tasks: BackgroundTasks,
    analysis_type: str = Query("clientes", description="Tipo de análise: clientes, vendas, orcamentos"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini_service: Any = Depends(get_available_gemini)
):
    """
    🔥 Análise de dados com Google Gemini
    - Gera insights e recomendações em linguagem natural
    - Usa os dados do usuário para análise contextualizada
    - Consome 1 crédito por análise
    """
    try:
        logger.info(f"🤖 Análise Gemini solicitada por: {current_user.email}")
        
        # Verificar créditos
        if not current_user.is_admin and current_user.credits <= 0:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": "Créditos insuficientes para análise",
                    "credits": current_user.credits,
                    "required": 1
                }
            )
        
        # Buscar análises recentes do usuário para contexto
        user_analyses = crud.get_user_analyses(db, current_user.id, limit=5)
        
        # Preparar dados para análise
        analysis_data = {
            "user_email": current_user.email,
            "workshop_name": current_user.workshop_name or "Oficina",
            "analysis_type": analysis_type,
            "total_analyses": len(user_analyses),
            "recent_analyses": [
                {
                    "filename": a.filename,
                    "type": a.analysis_type,
                    "date": a.created_at.isoformat() if a.created_at else None
                }
                for a in user_analyses[:3]
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        # Se tiver análises, adiciona dados mais detalhados
        if user_analyses:
            latest = user_analyses[0]
            if latest.result:
                analysis_data["latest_analysis"] = {
                    "filename": latest.filename,
                    "result": latest.result
                }
        
        # 🔥 Chamar Gemini
        logger.info(f"📤 Enviando dados para Gemini: {analysis_type}")
        
        ai_response = await gemini_service.analyze_office_data(
            analysis_type,
            analysis_data
        )
        
        if not ai_response.get('success', False):
            logger.warning(f"⚠️ Gemini retornou erro: {ai_response.get('message', 'Unknown error')}")
        
        # Consumir crédito
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, f"Análise Gemini: {analysis_type}")
            if not credits_consumed:
                logger.warning(f"⚠️ Falha ao consumir crédito para {current_user.email}")
        
        db.refresh(current_user)
        
        return {
            "success": True,
            "analysis_type": analysis_type,
            "ai_response": ai_response,
            "insights": ai_response.get('insights', []),
            "recommendations": ai_response.get('recommendations', []),
            "full_analysis": ai_response.get('full_analysis', ''),
            "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
            "is_admin": current_user.is_admin,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na análise Gemini: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "analysis_failed",
                "message": f"Erro ao processar análise: {str(e)}"
            }
        )


# ==============================================
# ENDPOINT /analyze-with-data - ANÁLISE COM DADOS ENVIADOS
# ==============================================

@router.post("/analyze-with-data", response_model=None)
async def analyze_with_data(
    data: Dict[str, Any],
    analysis_type: str = Query("clientes"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini_service: Any = Depends(get_available_gemini)
):
    """
    🔥 Análise com dados enviados diretamente no body
    - Útil para análise de dados já processados
    - Usa Gemini para insights em linguagem natural
    """
    try:
        logger.info(f"🤖 Análise Gemini com dados recebidos: {current_user.email}")
        
        if not current_user.is_admin and current_user.credits <= 0:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": "Créditos insuficientes",
                    "credits": current_user.credits
                }
            )
        
        # Preparar dados para Gemini
        analysis_data = {
            "user_email": current_user.email,
            "workshop_name": current_user.workshop_name or "Oficina",
            "analysis_type": analysis_type,
            "data_summary": data.get("summary", {}),
            "predictions": data.get("predictions", []),
            "insights": data.get("insights", {}),
            "timestamp": datetime.now().isoformat()
        }
        
        # Chamar Gemini
        ai_response = await gemini_service.analyze_office_data(analysis_type, analysis_data)
        
        # Consumir crédito
        if not current_user.is_admin:
            deduct_credits(db, current_user, 1, f"Análise Gemini com dados: {analysis_type}")
            db.refresh(current_user)
        
        return {
            "success": True,
            "analysis_type": analysis_type,
            "ai_response": ai_response,
            "insights": ai_response.get('insights', []),
            "recommendations": ai_response.get('recommendations', []),
            "full_analysis": ai_response.get('full_analysis', ''),
            "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na análise: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "analysis_failed", "message": str(e)}
        )


# ==============================================
# ENDPOINTS DE STATUS (MANTIDOS)
# ==============================================

@router.get("/status/{process_id}", response_model=None)
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


@router.get("/results/{analysis_id}", response_model=None)
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


@router.get("/user/analyses", response_model=None)
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
# ADMIN DIAGNOSTICS (COM response_model=None)
# ==============================================

@router.get("/admin/diagnostics", response_model=None)
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
    
    # Status do ML Pipeline
    ml_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    encoding_stats = pipeline.get_encoding_stats() if hasattr(pipeline, 'get_encoding_stats') else {}
    
    return {
        "success": True,
        "data": {
            "timestamp": datetime.now().isoformat(),
            "services": SERVICES_STATUS,
            "critical_services_ok": CRITICAL_SERVICES_OK,
            "missing_critical": service_factory.get_missing_critical_services(),
            "gemini_available": is_gemini_available(),
            "ml_pipeline": ml_status,
            "encoding_stats": encoding_stats,
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


# ==============================================
# ENDPOINT ML PIPELINE STATUS
# ==============================================

@router.get("/ml/pipeline-status", response_model=None)
async def get_ml_pipeline_status(
    current_user: User = Depends(get_current_user)
):
    """Retorna status do ML Pipeline"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
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


# ==============================================
# ENDPOINT ML PREDICT (DIRETO)
# ==============================================

@router.post("/ml/predict", response_model=None)
async def ml_predict(
    data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    🔥 Predição direta com ML Pipeline
    - Envia dados e recebe predições
    - Útil para integração com frontend
    """
    try:
        if not current_user.is_admin and current_user.credits <= 0:
            raise HTTPException(
                status_code=402,
                detail={"error": "insufficient_credits", "message": "Créditos insuficientes"}
            )
        
        # Converter dados para DataFrame
        df = pd.DataFrame(data.get("data", []))
        
        if df.empty:
            raise HTTPException(
                status_code=400,
                detail={"error": "empty_data", "message": "Nenhum dado fornecido para predição"}
            )
        
        # Fazer predição
        result = await pipeline.predict(df)
        
        return {
            "success": result.success,
            "predictions": result.predictions,
            "probabilities": result.probabilities,
            "metrics": result.metrics,
            "insights": result.insights,
            "recommendations": result.recommendations,
            "model_used": result.model_used,
            "processed_rows": result.processed_rows,
            "encoding_used": result.encoding_used
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na predição ML: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "prediction_failed", "message": str(e)}
        )


# ==============================================
# 🔥 IMPORTANTE: NÃO INCLUIR /upload AQUI
# ==============================================
# O endpoint /upload está em upload_routes.py
# Usar upload_routes.py para upload de arquivos com ML Pipeline


print("✅ routes.py carregado com Service Factory e dependências injetadas")
print("   🔥 /analyze → Gemini IA (response_model=None)")
print("   🔥 /analyze-with-data → Gemini com dados enviados")
print("   🔥 /ml/predict → ML Pipeline direto")
print("   🔥 /admin/diagnostics → Diagnóstico admin")
print("   ⚠️  /upload removido - usar upload_routes.py")