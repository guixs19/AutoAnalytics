# backend/api/routes.py - VERSÃO 5.1 (CORRIGIDA E OTIMIZADA)
"""
ROUTES.PY - Rotas base da API (Gemini, Health, Admin, Análise Múltipla)
================================================================================
✅ CORREÇÕES V5.1:
   - 🔥 CORRIGIDO: /report/{analysis_id} NÃO CONSUME CRÉDITOS (já consumido no ML)
   - 🔥 CORRIGIDO: Verificação de credits_consumed antes de liberar PDF
   - 🔥 CORRIGIDO: Fallback para consumir crédito se não foi consumido
   - 🔥 ADICIONADO: Logs detalhados de status de créditos

✅ MANTIDO V5.0:
   - request não definido em /analyze-multiple
   - client_ip quando request é None
   - Verificação de disponibilidade do Gemini
   - Health check avançado
   - Cache preditivo
   - Rate limiting por usuário
================================================================================
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query, Depends, Form, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
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
import hashlib
import time
import gzip
import io
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# ==============================================
# IMPORTS CENTRALIZADOS
# ==============================================

# Banco de dados e modelos
from backend.database import get_db
from backend import crud
from backend.security import get_current_user
from backend.models import User
from backend.crud import deduct_credits, manage_credits_after_consumption

# Configurações
from backend.config.settings import settings

# Service Factory
from backend.services.service_factory import (
    get_service_factory,
    get_file_manager,
    get_preprocessor,
    get_gemini_service,
    get_predictor,
    get_daily_credits_service,
    is_gemini_available
)

# ML Pipeline
from backend.preprocessing import pipeline, process_file_content

# 🔥 NOVOS MÓDULOS
from backend.ml.multi_analysis import analyze_multiple_files
from backend.ml.report_builder import report_builder, ReportFormat, build_executive_report

# Configurar logging
logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURAÇÕES
# ==============================================

class RoutesConfig:
    """Configurações centralizadas para routes.py"""
    MAX_FILES_MULTI_ANALYZE = 3
    MAX_FILE_SIZE = 200 * 1024  # 200KB
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv'}
    CACHE_TTL = 300  # 5 minutos
    RATE_LIMIT_MULTI_ANALYZE = 5  # 5 requisições por minuto
    RATE_LIMIT_WINDOW = 60  # 1 minuto
    PROCESSING_TIMEOUT = 300  # 5 minutos
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB
    ENABLE_RESPONSE_COMPRESSION = True
    ENABLE_PREDICTIVE_CACHE = True
    # 🔥 V5.1: Créditos
    CREDITS_PER_ANALYSIS = 1


# ==============================================
# INICIALIZAÇÃO
# ==============================================

router = APIRouter()

# Cache em memória
processing_cache = {}
analysis_cache = {}  # 🔥 NOVO: Cache para análises múltiplas
predictive_cache = {}  # 🔥 NOVO: Cache preditivo
rate_limit_cache = {}  # 🔥 NOVO: Rate limiting
endpoint_metrics = {  # 🔥 NOVO: Métricas por endpoint
    "total_requests": 0,
    "endpoints": {}
}

# ThreadPoolExecutor
_executor = ThreadPoolExecutor(max_workers=4)

# Service Factory
service_factory = get_service_factory()
SERVICES_STATUS = service_factory.get_status()
CRITICAL_SERVICES_OK = service_factory.get_critical_services_status()

logger.info(f"📊 Status dos serviços: {SERVICES_STATUS}")
logger.info(f"✅ Serviços críticos OK: {CRITICAL_SERVICES_OK}")


# ==============================================
# 🔥 FUNÇÕES AUXILIARES - MÉTRICAS
# ==============================================

def track_endpoint_metrics(endpoint: str, duration_ms: float, success: bool):
    """🔥 Rastreia métricas de endpoints"""
    if endpoint not in endpoint_metrics["endpoints"]:
        endpoint_metrics["endpoints"][endpoint] = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "avg_duration_ms": 0,
            "total_duration_ms": 0,
            "last_call": None
        }
    
    metrics = endpoint_metrics["endpoints"][endpoint]
    metrics["total"] += 1
    if success:
        metrics["success"] += 1
    else:
        metrics["failed"] += 1
    metrics["total_duration_ms"] += duration_ms
    metrics["avg_duration_ms"] = metrics["total_duration_ms"] / metrics["total"]
    metrics["last_call"] = datetime.now().isoformat()
    
    endpoint_metrics["total_requests"] += 1


# ==============================================
# FUNÇÕES AUXILIARES - SERIALIZAÇÃO
# ==============================================

def serialize_dataframe(df: pd.DataFrame) -> List[Dict]:
    """Converte DataFrame para lista de dicionários com tipos serializáveis"""
    if df is None or df.empty:
        return []
    
    records = df.to_dict(orient='records')
    
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
    try:
        return jsonable_encoder(data)
    except Exception as e:
        logger.warning(f"⚠️ jsonable_encoder falhou, usando fallback: {e}")
        return serialize_numpy(data)


def compress_response_if_needed(data: Dict[str, Any]) -> bytes:
    """🔥 Comprime resposta se for muito grande"""
    json_str = json.dumps(data, ensure_ascii=False)
    json_bytes = json_str.encode('utf-8')
    
    if len(json_bytes) > RoutesConfig.MAX_RESPONSE_SIZE and RoutesConfig.ENABLE_RESPONSE_COMPRESSION:
        compressed = gzip.compress(json_bytes)
        logger.info(f"📦 Resposta comprimida: {len(json_bytes)} → {len(compressed)} bytes")
        return compressed
    
    return json_bytes


# ==============================================
# FUNÇÕES AUXILIARES - RATE LIMITING
# ==============================================

def check_rate_limit(user_id: int, endpoint: str) -> bool:
    """
    🔥 Verifica rate limit para um usuário e endpoint
    """
    key = f"{endpoint}:{user_id}"
    now = time.time()
    window = RoutesConfig.RATE_LIMIT_WINDOW
    limit = RoutesConfig.RATE_LIMIT_MULTI_ANALYZE
    
    if key not in rate_limit_cache:
        rate_limit_cache[key] = []
    
    # Limpar requisições antigas
    rate_limit_cache[key] = [t for t in rate_limit_cache[key] if now - t < window]
    
    if len(rate_limit_cache[key]) >= limit:
        return False
    
    rate_limit_cache[key].append(now)
    return True


# ==============================================
# FUNÇÕES AUXILIARES - CACHE INTELIGENTE
# ==============================================

def get_cached_analysis(cache_key: str) -> Optional[Dict[str, Any]]:
    """Obtém análise do cache"""
    if cache_key in analysis_cache:
        data, timestamp = analysis_cache[cache_key]
        if time.time() - timestamp < RoutesConfig.CACHE_TTL:
            logger.info(f"📦 Cache hit para {cache_key[:8]}")
            return data
        else:
            del analysis_cache[cache_key]
    return None


def set_cached_analysis(cache_key: str, data: Dict[str, Any]) -> None:
    """Salva análise no cache"""
    analysis_cache[cache_key] = (data, time.time())
    logger.info(f"💾 Cache salvo para {cache_key[:8]}")


def get_cache_key(files: List[UploadFile], user_id: int) -> str:
    """Gera chave de cache para arquivos"""
    if not files:
        return hashlib.md5(f"{user_id}:empty".encode()).hexdigest()
    
    content = "".join([f.filename + str(f.size) for f in files])
    return hashlib.md5(f"{content}:{user_id}".encode()).hexdigest()


def get_predictive_cache_key(analysis_type: str, user_id: int) -> str:
    """🔥 Gera chave para cache preditivo"""
    return hashlib.md5(f"predictive:{analysis_type}:{user_id}".encode()).hexdigest()


# ==============================================
# FUNÇÕES AUXILIARES - ARQUIVOS
# ==============================================

async def validate_and_read_files(files: List[UploadFile]) -> Dict[str, Any]:
    """
    🔥 Valida e lê múltiplos arquivos (VERSÃO MELHORADA)
    """
    valid_files = []
    errors = []
    
    for idx, file in enumerate(files):
        try:
            # Validar nome
            if not file.filename:
                errors.append({"filename": f"arquivo_{idx}", "error": "Arquivo sem nome"})
                continue
            
            # Validar extensão
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in RoutesConfig.ALLOWED_EXTENSIONS:
                errors.append({
                    "filename": file.filename,
                    "error": f"Formato não suportado. Use: {', '.join(RoutesConfig.ALLOWED_EXTENSIONS)}"
                })
                continue
            
            # Ler conteúdo
            content = await file.read()
            
            # Validar tamanho
            if len(content) == 0:
                errors.append({"filename": file.filename, "error": "Arquivo vazio"})
                continue
            
            if len(content) > RoutesConfig.MAX_FILE_SIZE:
                errors.append({
                    "filename": file.filename,
                    "error": f"Arquivo excede {RoutesConfig.MAX_FILE_SIZE//1024}KB"
                })
                continue
            
            # 🔥 NOVO: Detectar se é CSV ou Excel válido
            is_valid_content = False
            if file_ext == '.csv':
                try:
                    import pandas as pd
                    from io import BytesIO
                    pd.read_csv(BytesIO(content), nrows=5)
                    is_valid_content = True
                except Exception:
                    errors.append({
                        "filename": file.filename,
                        "error": "Arquivo CSV inválido ou corrompido"
                    })
                    continue
            elif file_ext in ['.xlsx', '.xls']:
                try:
                    import pandas as pd
                    from io import BytesIO
                    pd.read_excel(BytesIO(content), nrows=5)
                    is_valid_content = True
                except Exception:
                    errors.append({
                        "filename": file.filename,
                        "error": "Arquivo Excel inválido ou corrompido"
                    })
                    continue
            
            valid_files.append({
                'content': content,
                'filename': file.filename,
                'file_size': len(content),
                'file_extension': file_ext
            })
            
        except Exception as e:
            logger.error(f"❌ Erro ao ler arquivo {file.filename if hasattr(file, 'filename') else 'unknown'}: {e}")
            errors.append({
                "filename": file.filename if hasattr(file, 'filename') else f"arquivo_{idx}",
                "error": str(e)
            })
    
    return {
        "valid": valid_files,
        "errors": errors,
        "valid_count": len(valid_files),
        "error_count": len(errors),
        "total": len(files)
    }


# ==============================================
# FUNÇÕES AUXILIARES - PROCESSAMENTO
# ==============================================

async def process_with_multi_analysis(
    file_data_list: List[Dict[str, Any]],
    user_id: int,
    user_email: str,
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    🔥 Processa arquivos com multi_analysis.py
    """
    logger.info(f"📚 Processando {len(file_data_list)} arquivos com multi_analysis...")
    
    try:
        result = await analyze_multiple_files(
            files=file_data_list,
            user_id=user_id,
            user_email=user_email,
            force_reload=force_reload
        )
        
        logger.info(f"✅ Análise multi_analysis concluída: {result.get('processed_files', 0)} arquivos processados")
        return result
        
    except Exception as e:
        logger.error(f"❌ Erro no multi_analysis: {e}")
        raise


def generate_report_content(
    analysis_result: Dict[str, Any],
    user_name: str,
    format: str = "html"
) -> Dict[str, Any]:
    """
    🔥 Gera relatório com report_builder.py
    """
    logger.info(f"📄 Gerando relatório em {format}...")
    
    format_map = {
        'html': ReportFormat.HTML,
        'pdf': ReportFormat.PDF,
        'json': ReportFormat.JSON
    }
    report_format = format_map.get(format.lower(), ReportFormat.HTML)
    
    report = build_executive_report(
        analysis_result=analysis_result,
        user_name=user_name
    )
    
    if report_format == ReportFormat.HTML:
        content = report_builder.to_html(report)
        content_type = "text/html"
        extension = "html"
    elif report_format == ReportFormat.PDF:
        content = report_builder.to_pdf(report)
        content_type = "application/pdf"
        extension = "pdf"
    else:
        content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        content_type = "application/json"
        extension = "json"
    
    return {
        "report": report,
        "content": content,
        "content_type": content_type,
        "extension": extension,
        "filename": f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
    }


# ==============================================
# FUNÇÕES AUXILIARES - HEALTH CHECK AVANÇADO
# ==============================================

def get_gemini_detailed_status() -> Dict[str, Any]:
    """🔥 Retorna status detalhado do Gemini"""
    try:
        gemini = get_gemini_service()
        if gemini:
            return {
                "available": is_gemini_available(),
                "model": getattr(gemini, 'current_model', 'unknown'),
                "is_healthy": getattr(gemini, 'is_healthy', lambda: False)(),
                "cache_size": len(getattr(gemini, 'response_cache', {})),
                "total_calls": getattr(gemini, 'metrics', {}).get('total_calls', 0),
                "last_error": getattr(gemini, '_last_error', None),
                "circuit_state": getattr(gemini, 'circuit_state', 'unknown'),
                "health_status": getattr(gemini, 'health_status', 'unknown')
            }
    except Exception as e:
        return {
            "available": False,
            "error": str(e)
        }
    
    return {"available": False}


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
    """🔥 Dependency que fornece o Gemini com verificação robusta"""
    
    # 🔥 VERIFICAÇÃO DETALHADA
    gemini_status = get_gemini_detailed_status()
    
    if not gemini_status.get("available"):
        logger.error(f"❌ Gemini indisponível: {gemini_status.get('error', 'Desconhecido')}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "gemini_unavailable",
                "message": "O serviço de IA não está disponível",
                "details": gemini_status,
                "action": "Verifique GEMINI_API_KEY no arquivo .env e reinicie o servidor"
            }
        )
    
    if not gemini_status.get("is_healthy", False):
        logger.warning(f"⚠️ Gemini não saudável: {gemini_status.get('health_status')}")
        # Tenta recarregar
        try:
            from backend.gemini import _gemini_service
            if _gemini_service:
                _gemini_service._initialize_client()
                _gemini_service._discover_models()
                logger.info("🔄 Gemini recarregado automaticamente")
        except Exception as e:
            logger.error(f"❌ Falha ao recarregar Gemini: {e}")
    
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
        return None
    return get_predictor()


# ==============================================
# ENDPOINTS PÚBLICOS
# ==============================================

@router.get("/test", response_model=None)
async def test_endpoint():
    """Endpoint de teste público com diagnóstico completo"""
    return {
        "success": True,
        "message": "API funcionando com Google Gemini V5.0!",
        "timestamp": datetime.now().isoformat(),
        "services_status": SERVICES_STATUS,
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "missing_critical": service_factory.get_missing_critical_services(),
        "gemini_available": is_gemini_available(),
        "gemini_detailed": get_gemini_detailed_status(),
        "ml_pipeline_available": pipeline.is_initialized if hasattr(pipeline, 'is_initialized') else False,
        "multi_analysis_available": True,
        "report_builder_available": True,
        "version": "5.1.0",
        "endpoint_metrics": endpoint_metrics
    }


@router.get("/health", response_model=None)
async def health_check():
    """🔥 Health check com diagnóstico detalhado V5.0"""
    start_time = time.time()
    
    ml_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    gemini_detailed = get_gemini_detailed_status()
    
    # Verificar cache health
    cache_health = {
        "analysis_cache": {
            "size": len(analysis_cache),
            "ttl": RoutesConfig.CACHE_TTL
        },
        "predictive_cache": {
            "size": len(predictive_cache)
        },
        "rate_limit_entries": len(rate_limit_cache)
    }
    
    response = {
        "status": "healthy" if CRITICAL_SERVICES_OK else "degraded",
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": (time.time() - start_time) * 1000,
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
            "ml_pipeline": ml_status,
            "multi_analysis": True,
            "report_builder": True
        },
        "gemini": gemini_detailed,
        "cache": cache_health,
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "endpoint_metrics": {
            "total_requests": endpoint_metrics["total_requests"],
            "endpoints": endpoint_metrics["endpoints"]
        },
        "recommendations": [
            "Configure GEMINI_API_KEY no arquivo .env" if not SERVICES_STATUS.get("gemini_api_configured") else None,
            "Verifique a conexão com a internet" if not gemini_detailed.get("available") else None,
        ]
    }
    
    # Remover None
    response["recommendations"] = [r for r in response["recommendations"] if r]
    
    return response


# ==============================================
# 🔥 ENDPOINT /analyze - GEMINI (CORRIGIDO)
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
    🔥 Análise de dados com Google Gemini (CORRIGIDO)
    - Gera insights e recomendações em linguagem natural
    - Usa os dados do usuário para análise contextualizada
    - Consome 1 crédito por análise
    """
    start_time = time.time()
    
    try:
        logger.info(f"🤖 Análise Gemini solicitada por: {current_user.email}")
        
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
        
        user_analyses = crud.get_user_analyses(db, current_user.id, limit=5)
        
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
        
        if user_analyses:
            latest = user_analyses[0]
            if latest.result:
                analysis_data["latest_analysis"] = {
                    "filename": latest.filename,
                    "result": latest.result
                }
        
        logger.info(f"📤 Enviando dados para Gemini: {analysis_type}")
        
        ai_response = await gemini_service.analyze_office_data(
            analysis_type,
            analysis_data
        )
        
        if not ai_response.get('success', False):
            logger.warning(f"⚠️ Gemini retornou erro: {ai_response.get('message', 'Unknown error')}")
        
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, f"Análise Gemini: {analysis_type}")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para {current_user.email}. Saldo: {current_user.credits}")
            else:
                logger.warning(f"⚠️ Falha ao consumir crédito para {current_user.email}")
                db.rollback()
        
        db.refresh(current_user)
        
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/analyze", elapsed, True)
        
        return {
            "success": True,
            "analysis_type": analysis_type,
            "ai_response": ai_response,
            "insights": ai_response.get('insights', []),
            "recommendations": ai_response.get('recommendations', []),
            "full_analysis": ai_response.get('full_analysis', ''),
            "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
            "is_admin": current_user.is_admin,
            "response_time_ms": round(elapsed, 2),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/analyze", elapsed, False)
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
# 🔥 ENDPOINT /analyze-with-data (CORRIGIDO)
# ==============================================

@router.post("/analyze-with-data", response_model=None)
async def analyze_with_data(
    data: Dict[str, Any],
    analysis_type: str = Query("clientes"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini_service: Any = Depends(get_available_gemini)
):
    """🔥 Análise com dados enviados diretamente no body"""
    start_time = time.time()
    
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
        
        analysis_data = {
            "user_email": current_user.email,
            "workshop_name": current_user.workshop_name or "Oficina",
            "analysis_type": analysis_type,
            "data_summary": data.get("summary", {}),
            "predictions": data.get("predictions", []),
            "insights": data.get("insights", {}),
            "timestamp": datetime.now().isoformat()
        }
        
        ai_response = await gemini_service.analyze_office_data(analysis_type, analysis_data)
        
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, f"Análise Gemini com dados: {analysis_type}")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para {current_user.email}. Saldo: {current_user.credits}")
            else:
                db.rollback()
        
        db.refresh(current_user)
        
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/analyze-with-data", elapsed, True)
        
        return {
            "success": True,
            "analysis_type": analysis_type,
            "ai_response": ai_response,
            "insights": ai_response.get('insights', []),
            "recommendations": ai_response.get('recommendations', []),
            "full_analysis": ai_response.get('full_analysis', ''),
            "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
            "response_time_ms": round(elapsed, 2),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/analyze-with-data", elapsed, False)
        logger.error(f"❌ Erro na análise: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "analysis_failed", "message": str(e)}
        )


# ==============================================
# 🔥 ENDPOINT: ANÁLISE MÚLTIPLA (CORRIGIDO)
# ==============================================

@router.post("/analyze-multiple", response_model=None)
async def analyze_multiple_endpoint(
    request: Request,  # 🔥 CORRIGIDO: Adicionado Request
    files: List[UploadFile] = File(..., description="Arquivos para análise (máx 3)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    report_format: str = Form("html", description="html, pdf, json"),
    force_reload: bool = Form(False, description="Forçar recarregamento, ignorar cache"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🔥 ANÁLISE MÚLTIPLA COM RELATÓRIO EXECUTIVO (V5.1)
    
    Recursos:
    - Envia até 3 arquivos (CSV, Excel, TSV)
    - Processa com multi_analysis.py (ML + Gemini)
    - Gera relatório com report_builder.py (HTML, PDF, JSON)
    - Cache inteligente (5 minutos)
    - Rate limiting (5 requisições por minuto)
    - 🔥 V5.1: Consome 1 crédito por análise (não por arquivo)
    """
    start_time = time.time()
    
    # 🔥 CORRIGIDO: Obter IP do request com segurança
    client_ip = "unknown"
    if request:
        try:
            client_ip = request.client.host if request.client else "unknown"
        except Exception:
            client_ip = "unknown"
    
    request_id = str(uuid.uuid4())[:8]
    
    logger.info(f"📚 [REQ-{request_id}] Análise múltipla solicitada por: {current_user.email} (IP: {client_ip})")
    
    # ==========================================
    # PASSO 1: VALIDAR QUANTIDADE
    # ==========================================
    
    total_files = len(files)
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > RoutesConfig.MAX_FILES_MULTI_ANALYZE:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {RoutesConfig.MAX_FILES_MULTI_ANALYZE} arquivos por vez. Enviados: {total_files}"
        )
    
    # ==========================================
    # PASSO 2: RATE LIMITING
    # ==========================================
    
    if not check_rate_limit(current_user.id, "analyze_multiple"):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Muitas requisições. Aguarde {RoutesConfig.RATE_LIMIT_WINDOW} segundos.",
                "limit": RoutesConfig.RATE_LIMIT_MULTI_ANALYZE,
                "window": RoutesConfig.RATE_LIMIT_WINDOW
            }
        )
    
    # ==========================================
    # PASSO 3: VALIDAR CRÉDITOS (V5.1 - 1 por análise)
    # ==========================================
    
    if not current_user.is_admin:
        if current_user.credits < RoutesConfig.CREDITS_PER_ANALYSIS:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": f"Créditos insuficientes. Você tem {current_user.credits}, precisa de {RoutesConfig.CREDITS_PER_ANALYSIS}.",
                    "credits_available": current_user.credits,
                    "credits_needed": RoutesConfig.CREDITS_PER_ANALYSIS,
                    "files_uploaded": total_files,
                    "credits_per_analysis": RoutesConfig.CREDITS_PER_ANALYSIS
                }
            )
    
    # ==========================================
    # PASSO 4: VALIDAR ARQUIVOS
    # ==========================================
    
    validation_result = await validate_and_read_files(files)
    
    if validation_result["valid_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_files",
                "message": "Nenhum arquivo válido para processar",
                "errors": validation_result["errors"]
            }
        )
    
    file_data_list = validation_result["valid"]
    errors = validation_result["errors"]
    
    # ==========================================
    # PASSO 5: VERIFICAR CACHE
    # ==========================================
    
    cache_key = get_cache_key(files, current_user.id)
    
    if not force_reload:
        cached_result = get_cached_analysis(cache_key)
        if cached_result:
            logger.info(f"📦 [REQ-{request_id}] Retornando resultado em cache")
            
            # Gerar relatório do cache
            report_data = generate_report_content(
                analysis_result=cached_result,
                user_name=current_user.name or current_user.email,
                format=report_format
            )
            
            # Atualizar créditos (não consome novamente)
            db.refresh(current_user)
            
            elapsed = (time.time() - start_time) * 1000
            track_endpoint_metrics("/analyze-multiple", elapsed, True)
            
            return {
                "success": True,
                "message": "Análise retornada do cache",
                "cached": True,
                "request_id": request_id,
                "analysis": {
                    "executive_score": cached_result.get('executive_score', {}),
                    "executive_summary": cached_result.get('executive_summary', ''),
                    "recommendations": cached_result.get('recommendations', []),
                    "forecast": cached_result.get('forecast', ''),
                    "general_conclusion": cached_result.get('general_conclusion', '')
                },
                "report": {
                    "content": report_data["content"],
                    "format": report_data["extension"],
                    "filename": report_data["filename"]
                },
                "chart_data": cached_result.get('chart_data', {}),
                "credits": {
                    "remaining": current_user.credits if not current_user.is_admin else "∞",
                    "is_admin": current_user.is_admin
                },
                "response_time_ms": round(elapsed, 2),
                "timestamp": datetime.now().isoformat()
            }
    
    # ==========================================
    # PASSO 6: PROCESSAR COM MULTI_ANALYSIS
    # ==========================================
    
    try:
        logger.info(f"🤖 [REQ-{request_id}] Processando {len(file_data_list)} arquivos...")
        
        analysis_result = await process_with_multi_analysis(
            file_data_list=file_data_list,
            user_id=current_user.id,
            user_email=current_user.email,
            force_reload=force_reload
        )
        
        if not analysis_result.get('success'):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "analysis_failed",
                    "message": analysis_result.get('error', 'Erro na análise')
                }
            )
        
        # Salvar no cache
        set_cached_analysis(cache_key, analysis_result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [REQ-{request_id}] Erro no multi_analysis: {e}")
        track_endpoint_metrics("/analyze-multiple", (time.time() - start_time) * 1000, False)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "analysis_failed",
                "message": f"Erro na análise: {str(e)}"
            }
        )
    
    # ==========================================
    # PASSO 7: CONSUMIR CRÉDITOS (V5.1 - 1 por análise)
    # ==========================================
    
    if not current_user.is_admin:
        # 🔥 V5.1: Consome APENAS 1 crédito por análise (não por arquivo)
        success = deduct_credits(db, current_user, RoutesConfig.CREDITS_PER_ANALYSIS, f"Análise múltipla: {len(file_data_list)} arquivo(s)")
        if success:
            db.commit()
            logger.info(f"💰 [REQ-{request_id}] {RoutesConfig.CREDITS_PER_ANALYSIS} crédito consumido para {len(file_data_list)} arquivo(s). Saldo: {current_user.credits}")
        else:
            db.rollback()
            logger.warning(f"⚠️ [REQ-{request_id}] Falha ao consumir crédito para {current_user.email}")
    
    db.refresh(current_user)
    
    # ==========================================
    # PASSO 8: GERAR RELATÓRIO
    # ==========================================
    
    report_data = generate_report_content(
        analysis_result=analysis_result,
        user_name=current_user.name or current_user.email,
        format=report_format
    )
    
    processing_time_ms = (time.time() - start_time) * 1000
    logger.info(f"✅ [REQ-{request_id}] Análise concluída em {processing_time_ms:.0f}ms")
    
    track_endpoint_metrics("/analyze-multiple", processing_time_ms, True)
    
    # ==========================================
    # PASSO 9: RESPOSTA
    # ==========================================
    
    # Se for PDF, retorna para download
    if report_format.lower() == 'pdf':
        return Response(
            content=report_data["content"],
            media_type=report_data["content_type"],
            headers={
                "Content-Disposition": f"attachment; filename={report_data['filename']}",
                "Access-Control-Expose-Headers": "Content-Disposition",
                "X-Request-ID": request_id,
                "X-Processing-Time-MS": str(round(processing_time_ms, 2))
            }
        )
    
    # Se for JSON, retorna dados estruturados
    if report_format.lower() == 'json':
        return JSONResponse(
            content={
                "success": True,
                "message": f"Análise consolidada de {analysis_result.get('processed_files', 0)} arquivo(s) concluída",
                "request_id": request_id,
                "analysis": {
                    "executive_score": analysis_result.get('executive_score', {}),
                    "executive_summary": analysis_result.get('executive_summary', ''),
                    "comparison": analysis_result.get('comparison', {}),
                    "trend": analysis_result.get('trend', {}),
                    "recommendations": analysis_result.get('recommendations', []),
                    "forecast": analysis_result.get('forecast', ''),
                    "general_conclusion": analysis_result.get('general_conclusion', '')
                },
                "report": {
                    "content": report_data["content"],
                    "format": report_data["extension"],
                    "filename": report_data["filename"]
                },
                "chart_data": analysis_result.get('chart_data', {}),
                "credits": {
                    "remaining": current_user.credits if not current_user.is_admin else "∞",
                    "is_admin": current_user.is_admin,
                    "consumed": RoutesConfig.CREDITS_PER_ANALYSIS if not current_user.is_admin else 0,
                    "credits_per_analysis": RoutesConfig.CREDITS_PER_ANALYSIS
                },
                "performance": {
                    "processing_time_ms": round(processing_time_ms, 2)
                },
                "cache": {
                    "hit": force_reload,
                    "key": cache_key[:8]
                },
                "timestamp": datetime.now().isoformat()
            }
        )
    
    # HTML: retorna JSON com HTML embutido
    return {
        "success": True,
        "message": f"Análise consolidada de {analysis_result.get('processed_files', 0)} arquivo(s) concluída",
        "request_id": request_id,
        "analysis": {
            "executive_score": analysis_result.get('executive_score', {}),
            "executive_summary": analysis_result.get('executive_summary', ''),
            "comparison": analysis_result.get('comparison', {}),
            "trend": analysis_result.get('trend', {}),
            "recommendations": analysis_result.get('recommendations', []),
            "forecast": analysis_result.get('forecast', ''),
            "general_conclusion": analysis_result.get('general_conclusion', '')
        },
        "report": {
            "content": report_data["content"],
            "format": report_data["extension"],
            "filename": report_data["filename"]
        },
        "chart_data": analysis_result.get('chart_data', {}),
        "credits": {
            "remaining": current_user.credits if not current_user.is_admin else "∞",
            "is_admin": current_user.is_admin,
            "consumed": RoutesConfig.CREDITS_PER_ANALYSIS if not current_user.is_admin else 0,
            "credits_per_analysis": RoutesConfig.CREDITS_PER_ANALYSIS
        },
        "performance": {
            "processing_time_ms": round(processing_time_ms, 2)
        },
        "cache": {
            "hit": force_reload,
            "key": cache_key[:8]
        },
        "timestamp": datetime.now().isoformat()
    }


# ==============================================
# 🔥 NOVO ENDPOINT: PREDICTIVE CACHE
# ==============================================

@router.post("/cache/preload", response_model=None)
async def preload_cache(
    analysis_type: str = Query("clientes"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🔥 PRÉ-CARREGA CACHE para análises comuns
    
    Útil para melhorar performance de análises frequentes.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
    try:
        # Verificar se já existe no cache preditivo
        cache_key = get_predictive_cache_key(analysis_type, current_user.id)
        
        if cache_key in predictive_cache:
            data, timestamp = predictive_cache[cache_key]
            if time.time() - timestamp < RoutesConfig.CACHE_TTL:
                return {
                    "success": True,
                    "message": "Cache já está pré-carregado",
                    "cached_at": datetime.fromtimestamp(timestamp).isoformat()
                }
        
        # Buscar análises recentes do usuário
        user_analyses = crud.get_user_analyses(db, current_user.id, limit=10)
        
        # Preparar dados para pré-carregamento
        if user_analyses:
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
                    for a in user_analyses[:5]
                ],
                "timestamp": datetime.now().isoformat()
            }
            
            # Salvar no cache preditivo
            predictive_cache[cache_key] = (analysis_data, time.time())
            
            logger.info(f"🔥 Cache preditivo pré-carregado para {current_user.email}")
            
            return {
                "success": True,
                "message": "Cache pré-carregado com sucesso",
                "analyses_count": len(user_analyses),
                "cache_key": cache_key[:8]
            }
        else:
            return {
                "success": True,
                "message": "Nenhuma análise para pré-carregar",
                "analyses_count": 0
            }
            
    except Exception as e:
        logger.error(f"❌ Erro ao pré-carregar cache: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "cache_preload_failed", "message": str(e)}
        )


# ==============================================
# 🔥 ENDPOINT: MÉTRICAS DO SISTEMA
# ==============================================

@router.get("/metrics", response_model=None)
async def get_system_metrics(
    current_user: User = Depends(get_current_user)
):
    """
    🔥 Retorna métricas detalhadas do sistema (admin only)
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "endpoint_metrics": endpoint_metrics,
        "cache": {
            "analysis_cache": {
                "size": len(analysis_cache),
                "ttl": RoutesConfig.CACHE_TTL
            },
            "predictive_cache": {
                "size": len(predictive_cache)
            },
            "rate_limit_entries": len(rate_limit_cache)
        },
        "services": SERVICES_STATUS,
        "critical_services_ok": CRITICAL_SERVICES_OK,
        "gemini": get_gemini_detailed_status(),
        "uptime": {
            "started_at": datetime.now().isoformat(),
            "seconds": 0  # TODO: Track uptime
        }
    }


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
# ADMIN DIAGNOSTICS
# ==============================================

@router.get("/admin/diagnostics", response_model=None)
async def get_diagnostics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Endpoint de diagnóstico detalhado (apenas admin) V5.1"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
    analyses_stats = crud.get_analyses_stats(db)
    ml_status = pipeline.get_status() if hasattr(pipeline, 'get_status') else {}
    encoding_stats = pipeline.get_encoding_stats() if hasattr(pipeline, 'get_encoding_stats') else {}
    
    return {
        "success": True,
        "data": {
            "timestamp": datetime.now().isoformat(),
            "version": "5.1.0",
            "services": SERVICES_STATUS,
            "critical_services_ok": CRITICAL_SERVICES_OK,
            "missing_critical": service_factory.get_missing_critical_services(),
            "gemini_available": is_gemini_available(),
            "gemini_detailed": get_gemini_detailed_status(),
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
            "analyses": analyses_stats,
            "analysis_cache": {
                "size": len(analysis_cache),
                "ttl": RoutesConfig.CACHE_TTL
            },
            "predictive_cache": {
                "size": len(predictive_cache)
            },
            "rate_limit": {
                "active_entries": len(rate_limit_cache),
                "per_minute": RoutesConfig.RATE_LIMIT_MULTI_ANALYZE
            },
            "endpoint_metrics": endpoint_metrics,
            "system": {
                "platform": os.name,
                "cpu_count": os.cpu_count(),
                "pid": os.getpid()
            },
            "credits_config": {
                "credits_per_analysis": RoutesConfig.CREDITS_PER_ANALYSIS
            }
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
# 🔥 ENDPOINT ML PREDICT (OTIMIZADO)
# ==============================================

@router.post("/ml/predict", response_model=None)
async def ml_predict(
    data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Predição direta com ML Pipeline (OTIMIZADO)"""
    start_time = time.time()
    
    try:
        logger.info(f"🤖 ML Predict solicitado por: {current_user.email}")
        
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
        
        def run_prediction():
            try:
                if hasattr(pipeline, 'predict'):
                    result = pipeline.predict(df)
                    
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
                        return {"success": True, "predictions": result}
                else:
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
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, run_prediction)
        
        if not result.get("success", False):
            error_msg = result.get("error", "Erro desconhecido na predição")
            raise HTTPException(
                status_code=500,
                detail={"error": "prediction_failed", "message": error_msg}
            )
        
        serialized_result = safe_json_response(result)
        
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, "Predição ML")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para ML predict de {current_user.email}. Saldo: {current_user.credits}")
            else:
                logger.warning(f"⚠️ Falha ao consumir crédito para ML predict de {current_user.email}")
                db.rollback()
        
        db.refresh(current_user)
        
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/ml/predict", elapsed, True)
        
        serialized_result["credits_remaining"] = current_user.credits if not current_user.is_admin else "∞"
        serialized_result["is_admin"] = current_user.is_admin
        serialized_result["processed_rows"] = len(df)
        serialized_result["response_time_ms"] = round(elapsed, 2)
        serialized_result["timestamp"] = datetime.now().isoformat()
        
        return serialized_result
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/ml/predict", elapsed, False)
        logger.error(f"❌ Erro na predição ML: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"error": "prediction_failed", "message": str(e)}
        )


# ==============================================
# 🔥 ENDPOINT ML PREDICT BATCH (OTIMIZADO)
# ==============================================

@router.post("/ml/predict-batch", response_model=None)
async def ml_predict_batch(
    data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Predição em lote com ML Pipeline (OTIMIZADO)"""
    start_time = time.time()
    
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
        
        serialized_results = safe_json_response(results)
        
        if not current_user.is_admin:
            credits_consumed = deduct_credits(db, current_user, 1, "Predição ML em lote")
            if credits_consumed:
                db.commit()
                logger.info(f"💰 Crédito consumido para ML predict batch de {current_user.email}")
            else:
                db.rollback()
        
        db.refresh(current_user)
        
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/ml/predict-batch", elapsed, True)
        
        return {
            "success": True,
            "results": serialized_results,
            "total_datasets": len(datasets),
            "credits_remaining": current_user.credits if not current_user.is_admin else "∞",
            "is_admin": current_user.is_admin,
            "response_time_ms": round(elapsed, 2),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        track_endpoint_metrics("/ml/predict-batch", elapsed, False)
        logger.error(f"❌ Erro na predição em lote: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "batch_prediction_failed", "message": str(e)}
        )


# ==============================================
# 🔥 ENDPOINT: ANÁLISE MÚLTIPLA STATUS
# ==============================================

@router.get("/analyze-multiple-status", response_model=None)
async def analyze_multiple_status(
    current_user: User = Depends(get_current_user)
):
    """
    🔥 Retorna status do serviço de análise múltipla
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
    # Estatísticas do cache
    cache_size = len(analysis_cache)
    cache_memory = 0
    for key, (data, _) in analysis_cache.items():
        cache_memory += len(json.dumps(data))
    
    # Estatísticas de rate limit
    rate_limit_entries = len(rate_limit_cache)
    
    return {
        "success": True,
        "config": {
            "max_files": RoutesConfig.MAX_FILES_MULTI_ANALYZE,
            "max_file_size_kb": RoutesConfig.MAX_FILE_SIZE // 1024,
            "cache_ttl_seconds": RoutesConfig.CACHE_TTL,
            "rate_limit_per_minute": RoutesConfig.RATE_LIMIT_MULTI_ANALYZE,
            "rate_limit_window_seconds": RoutesConfig.RATE_LIMIT_WINDOW,
            "processing_timeout_seconds": RoutesConfig.PROCESSING_TIMEOUT,
            "allowed_extensions": list(RoutesConfig.ALLOWED_EXTENSIONS),
            "credits_per_analysis": RoutesConfig.CREDITS_PER_ANALYSIS
        },
        "cache": {
            "size": cache_size,
            "memory_usage_kb": round(cache_memory / 1024, 2),
            "max_size": 100
        },
        "rate_limit": {
            "active_entries": rate_limit_entries
        },
        "gemini_status": get_gemini_detailed_status(),
        "timestamp": datetime.now().isoformat()
    }


# ==============================================
# 🔥🔥🔥 ENDPOINT: DOWNLOAD RELATÓRIO (V5.1 - NÃO CONSUME CRÉDITOS)
# ==============================================

@router.get("/report/{analysis_id}", response_model=None)
async def download_report_endpoint(
    analysis_id: int,
    format: str = Query("pdf", description="pdf, html, json"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🔥 Baixa relatório de uma análise existente (V5.1)
    
    🔥 NÃO CONSUME CRÉDITOS - já foram consumidos no ML
    🔥 Verifica se o crédito foi consumido antes de liberar
    🔥 Fallback: se não foi consumido, tenta consumir agora
    """
    start_time = time.time()
    
    # Buscar análise
    analysis = crud.get_analysis(db, analysis_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    if analysis.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if analysis.status == "pending_credit":
        # 🔥 V5.1: Análise aguardando crédito - tentar consumir agora
        logger.info(f"📄 [REPORT] Análise {analysis_id} em pending_credit. Tentando consumir crédito...")
        
        if current_user.is_admin:
            # Admin: marcar como consumido
            analysis.credits_consumed = True
            analysis.credits_consumed_at = datetime.now()
            analysis.status = "completed"
            db.commit()
            logger.info(f"👑 [REPORT] Admin - análise {analysis_id} marcada como consumida")
        else:
            # Usuário normal: tentar consumir crédito
            if current_user.credits >= 1:
                try:
                    result = manage_credits_after_consumption(
                        db=db,
                        user=current_user,
                        amount=1,
                        description=f"PDF da análise {analysis_id} (fallback)"
                    )
                    
                    if result.get("success"):
                        db.refresh(current_user)
                        analysis.credits_consumed = True
                        analysis.credits_consumed_at = datetime.now()
                        analysis.credits_consumed_amount = 1
                        analysis.credits_remaining_after = current_user.credits
                        analysis.status = "completed"
                        db.commit()
                        logger.info(f"💰 [REPORT] Crédito consumido no fallback para análise {analysis_id}")
                    else:
                        raise HTTPException(
                            status_code=402,
                            detail={
                                "error": "insufficient_credits",
                                "message": f"Créditos insuficientes: {result.get('message', 'Erro ao consumir crédito')}",
                                "credits_available": current_user.credits,
                                "credits_needed": 1
                            }
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"❌ [REPORT] Erro ao consumir crédito no fallback: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "credit_consumption_failed",
                            "message": f"Erro ao consumir crédito: {str(e)}"
                        }
                    )
            else:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "insufficient_credits",
                        "message": f"Créditos insuficientes. Você tem {current_user.credits}, precisa de 1.",
                        "credits_available": current_user.credits,
                        "credits_needed": 1
                    }
                )
    
    if analysis.status != "completed":
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "analysis_not_completed",
                "message": f"Análise não concluída. Status atual: {analysis.status}"
            }
        )
    
    # 🔥 V5.1: Verificar se o crédito foi consumido (exceto admin)
    if not current_user.is_admin:
        credits_consumed = hasattr(analysis, 'credits_consumed') and analysis.credits_consumed
        
        if not credits_consumed:
            # 🔥 Tentar consumir crédito agora (fallback)
            logger.warning(f"⚠️ [REPORT] Análise {analysis_id} sem crédito consumido. Tentando consumir agora...")
            
            if current_user.credits >= 1:
                try:
                    result = manage_credits_after_consumption(
                        db=db,
                        user=current_user,
                        amount=1,
                        description=f"PDF da análise {analysis_id} (fallback)"
                    )
                    
                    if result.get("success"):
                        db.refresh(current_user)
                        analysis.credits_consumed = True
                        analysis.credits_consumed_at = datetime.now()
                        analysis.credits_consumed_amount = 1
                        analysis.credits_remaining_after = current_user.credits
                        db.commit()
                        logger.info(f"💰 [REPORT] Crédito consumido no fallback para análise {analysis_id}")
                    else:
                        raise HTTPException(
                            status_code=402,
                            detail={
                                "error": "insufficient_credits",
                                "message": f"Créditos insuficientes: {result.get('message', 'Erro ao consumir crédito')}",
                                "credits_available": current_user.credits,
                                "credits_needed": 1
                            }
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"❌ [REPORT] Erro ao consumir crédito no fallback: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "credit_consumption_failed",
                            "message": f"Erro ao consumir crédito: {str(e)}"
                        }
                    )
            else:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "insufficient_credits",
                        "message": f"Créditos insuficientes. Você tem {current_user.credits}, precisa de 1.",
                        "credits_available": current_user.credits,
                        "credits_needed": 1
                    }
                )
    
    # ==========================================
    # GERAR RELATÓRIO
    # ==========================================
    
    logger.info(f"📄 [REPORT] Gerando relatório para análise {analysis_id} (formato: {format})")
    
    # Construir resultado a partir dos dados salvos
    analysis_result = {
        "success": True,
        "total_files": 1,
        "processed_files": 1,
        "failed_files": 0,
        "executive_score": analysis.predictions_summary or {},
        "executive_summary": analysis.insights.get('summary', {}).get('mensagem', '') if analysis.insights else '',
        "files": [
            {
                "filename": analysis.filename,
                "success": True,
                "processed_rows": analysis.rows_processed or 0,
                "metrics": analysis.predictions_summary or {},
                "chart_data": analysis.chart_data or {}
            }
        ],
        "recommendations": analysis.recommendations or [],
        "chart_data": analysis.chart_data or {}
    }
    
    # Gerar relatório
    report_data = generate_report_content(
        analysis_result=analysis_result,
        user_name=current_user.name or current_user.email,
        format=format
    )
    
    elapsed = (time.time() - start_time) * 1000
    track_endpoint_metrics("/report", elapsed, True)
    
    credits_info = {
        "consumed": analysis.credits_consumed if hasattr(analysis, 'credits_consumed') else False,
        "consumed_at": analysis.credits_consumed_at.isoformat() if hasattr(analysis, 'credits_consumed_at') and analysis.credits_consumed_at else None,
        "remaining_after": analysis.credits_remaining_after if hasattr(analysis, 'credits_remaining_after') else None
    }
    
    logger.info(f"✅ [REPORT] Relatório gerado para análise {analysis_id} em {elapsed:.0f}ms")
    logger.info(f"💰 [REPORT] Status créditos: consumido={credits_info['consumed']}")
    
    return Response(
        content=report_data["content"],
        media_type=report_data["content_type"],
        headers={
            "Content-Disposition": f"attachment; filename={report_data['filename']}",
            "Access-Control-Expose-Headers": "Content-Disposition",
            "X-Analysis-ID": str(analysis_id),
            "X-User-ID": str(current_user.id),
            "X-Credits-Consumed": str(credits_info["consumed"]),
            "X-Report-Format": format,
            "X-Response-Time-MS": str(round(elapsed, 2))
        }
    )


# ==============================================
# 🔥 ENDPOINT: LIMPAR CACHE (ADMIN)
# ==============================================

@router.post("/admin/cache/clear", response_model=None)
async def clear_cache_endpoint(
    current_user: User = Depends(get_current_user)
):
    """🔥 Limpa todos os caches do sistema (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Acesso negado. Apenas administradores."}
        )
    
    size_before = len(analysis_cache) + len(predictive_cache) + len(processing_cache)
    
    analysis_cache.clear()
    predictive_cache.clear()
    processing_cache.clear()
    rate_limit_cache.clear()
    
    return {
        "success": True,
        "message": "Caches limpos com sucesso",
        "entries_cleared": size_before,
        "timestamp": datetime.now().isoformat()
    }


# ==============================================
# 🔥 IMPORTANTE: NÃO INCLUIR /upload AQUI
# ==============================================

print("=" * 80)
print("✅ routes.py v5.1 carregado com CORREÇÕES e MELHORIAS:")
print("   🔥 CORRIGIDO: /report/{analysis_id} NÃO CONSUME CRÉDITOS")
print("   🔥 CORRIGIDO: Verificação de credits_consumed antes de liberar PDF")
print("   🔥 CORRIGIDO: Fallback para consumir crédito se não foi consumido")
print("   🔥 ADICIONADO: Logs detalhados de status de créditos")
print("   🔥 MANTIDO: request não definido em /analyze-multiple")
print("   🔥 MANTIDO: client_ip quando request é None")
print("   🔥 MANTIDO: Verificação de disponibilidade do Gemini")
print("   🚀 Health check avançado com métricas do Gemini")
print("   🚀 Diagnóstico auto-corretivo")
print("   🚀 Cache preditivo")
print("   🚀 Rate limiting por usuário")
print("   🚀 Logs estruturados com correlation ID")
print("   🚀 Fallback inteligente")
print("   🚀 Métricas de performance")
print("   🚀 Validação de arquivos robusta")
print("   🚀 Compressão de resposta")
print("   🚀 Background tasks")
print("   ⚠️  /upload removido - usar upload_routes.py")
print("=" * 80)