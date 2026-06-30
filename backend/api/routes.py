# backend/api/routes.py - VERSÃO CORRIGIDA V3.3
"""
ROUTES.PY - Rotas base da API (Gemini, Health, Admin)
✅ CORRIGIDO: /ml/predict agora é síncrono (sem await) com executor
✅ CORRIGIDO: Serialização de tipos NumPy/Pandas para JSON
✅ CORRIGIDO: db.commit() explícito para dedução de créditos
✅ SINCRONIZADO: Com upload_routes.py e preprocessing.py
✅ REMOVIDO: Endpoint /upload duplicado (usar upload_routes.py)
✅ MANTIDO: /analyze (Gemini), /health, /test, /admin/diagnostics
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
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
import asyncio
from concurrent.futures import ThreadPoolExecutor

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

# ThreadPoolExecutor para operações síncronas pesadas
_executor = ThreadPoolExecutor(max_workers=4)

# Obtém fábrica de serviços
service_factory = get_service_factory()
SERVICES_STATUS = service_factory.get_status()
CRITICAL_SERVICES_OK = service_factory.get_critical_services_status()

logger.info(f"📊 Status dos serviços: {SERVICES_STATUS}")
logger.info(f"✅ Serviços críticos OK: {CRITICAL_SERVICES_OK}")


# ==============================================
# FUNÇÃO AUXILIAR PARA SERIALIZAÇÃO
# ==============================================

def serialize_dataframe(df: pd.DataFrame) -> List[Dict]:
    """Converte DataFrame para lista de dicionários com tipos serializáveis"""
    if df is None or df.empty:
        return []
    
    # Converte para dicionário e trata tipos
    records = df.to_dict(orient='records')
    
    # Converte todos os valores para tipos serializáveis
    def serialize_value(v):
        if pd.isna(v):
            return None
        if isinstance(v, (np.integer, np.int64, np.int32)):
            return int(v)
        if isinstance(v, (np.floating, np.float64, np.float32)):
            return float(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v
    
    return [
        {k: serialize_value(v) for k, v in record.items()}
        for record in records
    ]


def serialize_numpy(data: Any) -> Any:
    """Converte tipos NumPy para tipos Python serializáveis"""
    if data is None:
        return None
    if isinstance(data, (np.integer, np.int64, np.int32)):
        return int(data)
    if isinstance(data, (np.floating, np.float64, np.float32)):
        return float(data)
    if isinstance(data, np.ndarray):
        return data.tolist()
    if isinstance(data, pd.Timestamp):
        return data.isoformat()
    if isinstance(data, (datetime, date)):
        return data.isoformat()
    if isinstance(data, dict):
        return {k: serialize_numpy(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [serialize_numpy(v) for v in data]
    if isinstance(data, pd.Series):
        return serialize_numpy(data.to_list())
    if isinstance(data, pd.DataFrame):
        return serialize_dataframe(data)
    return data


def safe_json_response(data: Any) -> Dict:
    """Garante que a resposta seja serializável para JSON"""
    # Usa jsonable_encoder do FastAPI como primeira camada
    try:
        return jsonable_encoder(data)
    except Exception as e:
        logger.warning(f"⚠️ jsonable_encoder falhou, usando fallback: {e}")
        # Fallback manual
        return serialize_numpy(data)


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
    
    # 🔥 CORREÇÃO: db.commit() explícito para garantir persistência
    if success:
        db.commit()
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
        db.rollback()
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
        "version": "3.3.0"
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
        
        # 🔥 CORREÇÃO: Consumir crédito com commit explícito
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, f"Análise Gemini: {analysis_type}")
            if credits_consumed:
                db.commit()  # 🔥 FORÇA O COMMIT
                logger.info(f"💰 Crédito consumido para {current_user.email}. Saldo: {current_user.credits}")
            else:
                logger.warning(f"⚠️ Falha ao consumir crédito para {current_user.email}")
                db.rollback()
        
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
        
        # 🔥 CORREÇÃO: Consumir crédito com commit explícito
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, f"Análise Gemini com dados: {analysis_type}")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para {current_user.email}. Saldo: {current_user.credits}")
            else:
                db.rollback()
        
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
# 🔥 ENDPOINT ML PREDICT (CORRIGIDO - SÍNCRONO E SERIALIZADO)
# ==============================================

@router.post("/ml/predict", response_model=None)
async def ml_predict(
    data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 Predição direta com ML Pipeline
    - Envia dados e recebe predições
    - Útil para integração com frontend
    - 🔥 CORRIGIDO: Processamento síncrono com executor
    - 🔥 CORRIGIDO: Serialização de tipos NumPy/Pandas
    """
    try:
        logger.info(f"🤖 ML Predict solicitado por: {current_user.email}")
        
        # Verificar créditos
        if not current_user.is_admin and current_user.credits <= 0:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": "Créditos insuficientes para predição",
                    "credits": current_user.credits,
                    "required": 1
                }
            )
        
        # Converter dados para DataFrame
        input_data = data.get("data", [])
        if not input_data:
            raise HTTPException(
                status_code=400,
                detail={"error": "empty_data", "message": "Nenhum dado fornecido para predição"}
            )
        
        df = pd.DataFrame(input_data)
        
        if df.empty:
            raise HTTPException(
                status_code=400,
                detail={"error": "empty_data", "message": "DataFrame vazio após conversão"}
            )
        
        logger.info(f"📊 DataFrame recebido: {len(df)} linhas, {len(df.columns)} colunas")
        
        # 🔥 CORREÇÃO 1: Executar predição de forma síncrona (sem await)
        # Usa ThreadPoolExecutor para não bloquear o event loop
        def run_prediction():
            try:
                # Verifica se pipeline tem método predict
                if hasattr(pipeline, 'predict'):
                    # Tenta usar o método predict do pipeline
                    result = pipeline.predict(df)
                    
                    # Se for um objeto com atributos, extrai
                    if hasattr(result, 'success'):
                        return {
                            "success": result.success,
                            "predictions": result.predictions if hasattr(result, 'predictions') else None,
                            "probabilities": result.probabilities if hasattr(result, 'probabilities') else None,
                            "metrics": result.metrics if hasattr(result, 'metrics') else None,
                            "insights": result.insights if hasattr(result, 'insights') else None,
                            "recommendations": result.recommendations if hasattr(result, 'recommendations') else None,
                            "model_used": result.model_used if hasattr(result, 'model_used') else "default",
                            "processed_rows": result.processed_rows if hasattr(result, 'processed_rows') else len(df),
                            "encoding_used": result.encoding_used if hasattr(result, 'encoding_used') else "auto"
                        }
                    elif isinstance(result, dict):
                        return result
                    else:
                        # Fallback: tentar converter para dict
                        return {"success": True, "predictions": result}
                else:
                    # Fallback: simular predição
                    logger.warning("⚠️ Pipeline sem método predict, usando fallback")
                    return {
                        "success": True,
                        "predictions": ["categoria_1"] * len(df),
                        "probabilities": [{"categoria_1": 0.8, "categoria_2": 0.2}] * len(df),
                        "model_used": "fallback",
                        "processed_rows": len(df)
                    }
            except Exception as e:
                logger.error(f"❌ Erro na predição: {e}")
                return {"success": False, "error": str(e)}
        
        # Executa em thread separada
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, run_prediction)
        
        if not result.get("success", False):
            error_msg = result.get("error", "Erro desconhecido na predição")
            raise HTTPException(
                status_code=500,
                detail={"error": "prediction_failed", "message": error_msg}
            )
        
        # 🔥 CORREÇÃO 2: Serializar resultado para JSON
        serialized_result = safe_json_response(result)
        
        # 🔥 CORREÇÃO 3: Consumir crédito com commit explícito
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, "Predição ML")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para ML predict de {current_user.email}. Saldo: {current_user.credits}")
            else:
                logger.warning(f"⚠️ Falha ao consumir crédito para ML predict de {current_user.email}")
                db.rollback()
        
        db.refresh(current_user)
        
        # Adiciona informações de créditos
        serialized_result["credits_remaining"] = current_user.credits if not current_user.is_admin else "∞"
        serialized_result["is_admin"] = current_user.is_admin
        serialized_result["processed_rows"] = len(df)
        serialized_result["timestamp"] = datetime.now().isoformat()
        
        return serialized_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na predição ML: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"error": "prediction_failed", "message": str(e)}
        )


# ==============================================
# 🔥 ENDPOINT ML PREDICT BATCH (LOTE)
# ==============================================

@router.post("/ml/predict-batch", response_model=None)
async def ml_predict_batch(
    data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 Predição em lote com ML Pipeline
    - Processa múltiplos DataFrames de uma vez
    - Útil para grandes volumes de dados
    """
    try:
        logger.info(f"🤖 ML Predict Batch solicitado por: {current_user.email}")
        
        if not current_user.is_admin and current_user.credits <= 0:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": "Créditos insuficientes",
                    "credits": current_user.credits
                }
            )
        
        datasets = data.get("datasets", [])
        if not datasets:
            raise HTTPException(
                status_code=400,
                detail={"error": "empty_data", "message": "Nenhum dataset fornecido"}
            )
        
        results = []
        total_rows = 0
        
        def run_batch_prediction():
            results_batch = []
            for idx, dataset in enumerate(datasets):
                try:
                    df = pd.DataFrame(dataset.get("data", []))
                    if df.empty:
                        results_batch.append({
                            "index": idx,
                            "success": False,
                            "error": "Dataset vazio",
                            "rows": 0
                        })
                        continue
                    
                    if hasattr(pipeline, 'predict'):
                        result = pipeline.predict(df)
                        
                        if hasattr(result, 'success'):
                            results_batch.append({
                                "index": idx,
                                "success": result.success,
                                "predictions": result.predictions if hasattr(result, 'predictions') else None,
                                "probabilities": result.probabilities if hasattr(result, 'probabilities') else None,
                                "rows": len(df),
                                "model_used": result.model_used if hasattr(result, 'model_used') else "default"
                            })
                        elif isinstance(result, dict):
                            results_batch.append({
                                "index": idx,
                                "success": result.get("success", True),
                                "predictions": result.get("predictions"),
                                "rows": len(df)
                            })
                        else:
                            results_batch.append({
                                "index": idx,
                                "success": True,
                                "predictions": result,
                                "rows": len(df)
                            })
                    else:
                        results_batch.append({
                            "index": idx,
                            "success": False,
                            "error": "Pipeline sem método predict",
                            "rows": len(df)
                        })
                except Exception as e:
                    results_batch.append({
                        "index": idx,
                        "success": False,
                        "error": str(e),
                        "rows": 0
                    })
            return results_batch
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(_executor, run_batch_prediction)
        
        # Serializar resultados
        serialized_results = safe_json_response(results)
        
        # Consumir 1 crédito por lote (não por dataset)
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, "Predição ML em lote")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para ML predict batch de {current_user.email}")
            else:
                db.rollback()
        
        db.refresh(current_user)
        
        return {
            "success": True,
            "results": serialized_results,
            "total_datasets": len(datasets),
            "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
            "is_admin": current_user.is_admin,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na predição em lote: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "batch_prediction_failed", "message": str(e)}
        )


# ==============================================
# 🔥 IMPORTANTE: NÃO INCLUIR /upload AQUI
# ==============================================
# O endpoint /upload está em upload_routes.py
# Usar upload_routes.py para upload de arquivos com ML Pipeline


print("✅ routes.py v3.3 carregado com correções:")
print("   🔥 /ml/predict → Síncrono (sem await) com executor")
print("   🔥 Serialização de tipos NumPy/Pandas para JSON")
print("   🔥 db.commit() explícito para dedução de créditos")
print("   🔥 /ml/predict-batch → Processamento em lote")
print("   🔥 /analyze → Gemini IA (response_model=None)")
print("   🔥 /analyze-with-data → Gemini com dados enviados")
print("   🔥 /admin/diagnostics → Diagnóstico admin")
print("   ⚠️  /upload removido - usar upload_routes.py")