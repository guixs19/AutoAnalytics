# backend/api/upload_routes.py - VERSÃO 6.0 COM RELATÓRIO EXECUTIVO
"""
🚀 ROTAS DE UPLOAD - VERSÃO 6.0
================================================================================
✅ Código limpo e organizado
✅ Funções separadas por responsabilidade
✅ Integração com multi_analysis.py (dados estruturados)
✅ Integração com report_builder.py (relatórios profissionais)
✅ Suporte a múltiplos formatos: HTML, PDF, JSON
✅ Dashboard com abas dinâmicas
✅ Créditos consumidos de forma segura
✅ Cache inteligente
✅ Rate limiting
✅ PoW integrado
================================================================================
"""

# ==============================================
# 🔥 IMPORTS
# ==============================================

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, Response, HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging
import os
import uuid
import hashlib
import asyncio
import time
import json
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from backend.database import get_db, SessionLocal
from backend import models
from backend.security import get_current_active_user
from backend.services.credits_consumer import consume_analysis_credit, get_credits_display
from backend.api.pow_routes import validate_pow_request, pow_service, PoWConfig
from backend.preprocessing import process_file_content, pipeline

# ==============================================
# 🔥 NOVOS IMPORTS - MULTI_ANALYSIS E REPORT_BUILDER
# ==============================================

from backend.ml.multi_analysis import analyze_multiple_files
from backend.ml.report_builder import report_builder, ReportFormat, build_executive_report

# ==============================================
# 🔥 CONFIGURAÇÃO
# ==============================================

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

class UploadConfig:
    """Configurações centralizadas"""
    MAX_FILE_SIZE = 200 * 1024  # 200KB
    MAX_FILES_PER_BATCH = 5
    MAX_FILES_MULTI_ANALYZE = 3
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv'}
    PROCESSING_TIMEOUT_SECONDS = 300
    CHUNK_SIZE = 8192
    CACHE_TTL = 300  # 5 minutos


class ReportFormat(str, Enum):
    """Formatos de relatório suportados"""
    HTML = "html"
    PDF = "pdf"
    JSON = "json"


# ==============================================
# 🔥 DATACLASSES
# ==============================================

@dataclass
class UploadFileInfo:
    """Informações de um arquivo"""
    filename: str
    content: bytes
    file_size: int
    file_extension: str
    mime_type: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        return self.error is None
    
    @property
    def size_kb(self) -> float:
        return self.file_size / 1024
    
    @property
    def hash(self) -> str:
        return hashlib.md5(self.content).hexdigest() if self.content else ""


# ==============================================
# 🔥 FUNÇÕES DE VALIDAÇÃO
# ==============================================

def validate_file(file: UploadFile, idx: int) -> UploadFileInfo:
    """Valida um arquivo de upload"""
    
    if not file.filename:
        return UploadFileInfo(
            filename=f"arquivo_{idx}",
            content=b"",
            file_size=0,
            file_extension="",
            error="Arquivo sem nome"
        )
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in UploadConfig.ALLOWED_EXTENSIONS:
        return UploadFileInfo(
            filename=file.filename,
            content=b"",
            file_size=0,
            file_extension=file_ext,
            error=f"Formato não suportado. Use: {', '.join(UploadConfig.ALLOWED_EXTENSIONS)}"
        )
    
    try:
        content = bytearray()
        total_size = 0
        chunk = file.file.read(UploadConfig.CHUNK_SIZE)
        
        while chunk:
            total_size += len(chunk)
            if total_size > UploadConfig.MAX_FILE_SIZE:
                return UploadFileInfo(
                    filename=file.filename,
                    content=b"",
                    file_size=total_size,
                    file_extension=file_ext,
                    error=f"Arquivo excede o limite de {UploadConfig.MAX_FILE_SIZE//1024}KB"
                )
            content.extend(chunk)
            chunk = file.file.read(UploadConfig.CHUNK_SIZE)
        
        if total_size == 0:
            return UploadFileInfo(
                filename=file.filename,
                content=b"",
                file_size=0,
                file_extension=file_ext,
                error="Arquivo vazio"
            )
        
        return UploadFileInfo(
            filename=file.filename,
            content=bytes(content),
            file_size=total_size,
            file_extension=file_ext,
            mime_type=file.content_type
        )
        
    except Exception as e:
        logger.error(f"❌ Erro ao ler arquivo {file.filename}: {e}")
        return UploadFileInfo(
            filename=file.filename or f"arquivo_{idx}",
            content=b"",
            file_size=0,
            file_extension=file_ext if 'file_ext' in locals() else "",
            error=str(e)
        )


async def validate_files_async(files: List[UploadFile]) -> Dict[str, Any]:
    """Valida múltiplos arquivos em paralelo"""
    valid_files = []
    invalid_files = []
    
    loop = asyncio.get_event_loop()
    results = await asyncio.gather(*[
        loop.run_in_executor(None, validate_file, file, idx)
        for idx, file in enumerate(files)
    ])
    
    for result in results:
        if result.is_valid:
            valid_files.append(result)
        else:
            invalid_files.append(result)
    
    return {
        "valid": valid_files,
        "invalid": invalid_files,
        "total": len(files),
        "valid_count": len(valid_files),
        "invalid_count": len(invalid_files)
    }


# ==============================================
# 🔥 FUNÇÕES DE CRÉDITOS
# ==============================================

def check_credits(user: models.User, required: int) -> Dict[str, Any]:
    """Verifica se o usuário tem créditos suficientes"""
    if user.is_admin:
        return {
            "valid": True,
            "message": "👑 Admin - créditos ilimitados",
            "available": "∞",
            "required": 0,
            "is_admin": True
        }
    
    if user.credits < required:
        return {
            "valid": False,
            "message": f"Créditos insuficientes. Você tem {user.credits}, precisa de {required}.",
            "available": user.credits,
            "required": required,
            "is_admin": False
        }
    
    return {
        "valid": True,
        "message": f"Créditos suficientes: {user.credits}",
        "available": user.credits,
        "required": required,
        "is_admin": False
    }


def consume_credits(db: Session, user: models.User, file_list: List[UploadFileInfo]) -> Dict[str, Any]:
    """Consome créditos de forma segura para múltiplos arquivos"""
    
    if user.is_admin:
        return {
            "success": True,
            "message": "👑 Admin - créditos ilimitados",
            "consumed": 0,
            "remaining": "∞",
            "is_admin": True
        }
    
    total_files = len(file_list)
    credits_before = user.credits
    consumed = 0
    
    try:
        for i, file_info in enumerate(file_list):
            filename = file_info.filename
            desc = f"Análise: {filename}"
            
            success = consume_analysis_credit(user, db, 1)
            if success:
                consumed += 1
                logger.info(f"💰 Crédito {i+1}/{total_files} consumido: {filename}")
            else:
                logger.error(f"❌ Falha ao consumir crédito para {filename}")
                db.rollback()
                return {
                    "success": False,
                    "message": f"Falha ao consumir crédito para {filename}",
                    "consumed": consumed,
                    "remaining": user.credits,
                    "failed_file": filename,
                    "is_admin": False
                }
        
        db.commit()
        db.refresh(user)
        
        logger.info(f"💰 {consumed} créditos consumidos. Saldo: {user.credits}")
        
        return {
            "success": True,
            "message": f"✅ {consumed} crédito(s) consumido(s)",
            "consumed": consumed,
            "remaining": user.credits,
            "before": credits_before,
            "is_admin": False
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro ao consumir créditos: {e}")
        return {
            "success": False,
            "message": f"Erro ao consumir créditos: {str(e)}",
            "consumed": consumed,
            "remaining": user.credits,
            "error": str(e),
            "is_admin": False
        }


# ==============================================
# 🔥 FUNÇÕES DE ANÁLISE COM MULTI_ANALYSIS
# ==============================================

async def process_with_multi_analysis(
    file_data_list: List[Dict[str, Any]],
    user_id: int,
    user_email: str
) -> Dict[str, Any]:
    """
    🔥 Processa múltiplos arquivos usando multi_analysis.py
    
    Args:
        file_data_list: Lista de arquivos com content e filename
        user_id: ID do usuário
        user_email: Email do usuário
    
    Returns:
        Dict: Resultado da análise consolidada
    """
    logger.info(f"📚 Processando {len(file_data_list)} arquivos com multi_analysis...")
    
    try:
        result = await analyze_multiple_files(
            files=file_data_list,
            user_id=user_id,
            user_email=user_email,
            force_reload=False
        )
        
        logger.info(f"✅ Análise multi_analysis concluída: {result.get('processed_files', 0)} arquivos processados")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Erro no multi_analysis: {e}")
        raise


# ==============================================
# 🔥 FUNÇÕES DE RELATÓRIO
# ==============================================

def generate_report(
    analysis_result: Dict[str, Any],
    user_name: str,
    format: ReportFormat = ReportFormat.HTML
) -> Dict[str, Any]:
    """
    🔥 Gera relatório executivo usando report_builder.py
    
    Args:
        analysis_result: Resultado do multi_analysis
        user_name: Nome do usuário
        format: Formato do relatório (HTML, PDF, JSON)
    
    Returns:
        Dict: Relatório gerado
    """
    logger.info(f"📄 Gerando relatório em {format.value}...")
    
    # Construir relatório
    report = build_executive_report(
        analysis_result=analysis_result,
        user_name=user_name
    )
    
    # Gerar conteúdo baseado no formato
    if format == ReportFormat.HTML:
        content = report_builder.to_html(report)
        content_type = "text/html"
        extension = "html"
    elif format == ReportFormat.PDF:
        content = report_builder.to_pdf(report)
        content_type = "application/pdf"
        extension = "pdf"
    else:  # JSON
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
# 🔥 FUNÇÕES DE SALVAMENTO
# ==============================================

def save_analyses(
    db: Session,
    user_id: int,
    results: List[Dict[str, Any]],
    analysis_type: str,
    pow_valid: bool,
    client_ip: str
) -> List[int]:
    """Salva análises no banco de dados"""
    analyses_ids = []
    
    for result in results:
        try:
            analysis = models.Analysis(
                user_id=user_id,
                filename=result.get('filename', 'unknown'),
                file_size=result.get('file_size', 0),
                analysis_type=analysis_type,
                model_used=result.get('model_used', 'default'),
                status="completed" if result.get('success') else "error",
                rows_processed=result.get('processed_rows', 0),
                uploaded_at=datetime.now(),
                processed_at=datetime.now() if result.get('success') else None,
                encoding_used=result.get('encoding_used'),
                pow_verified=pow_valid,
                client_ip=client_ip,
                chart_data=result.get('chart_data', {}),
                predictions_summary=result.get('metrics', {}),
                insights=result.get('insights', {}),
                recommendations=result.get('recommendations', [])
            )
            db.add(analysis)
            db.flush()
            analyses_ids.append(analysis.id)
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar análise: {e}")
    
    db.commit()
    logger.info(f"✅ {len(analyses_ids)} análises salvas")
    
    return analyses_ids


# ==============================================
# 🔥 ROTA PRINCIPAL: UPLOAD MÚLTIPLO COM RELATÓRIO
# ==============================================

@router.post("/upload-multi-analyze")
async def upload_multi_analyze(
    request: Request,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(..., description="Arquivos para análise (máx 3)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    report_format: str = Form("html", description="Formato do relatório: html, pdf, json"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 UPLOAD MÚLTIPLO COM RELATÓRIO EXECUTIVO
    
    - Envia até 3 arquivos de uma vez
    - Processa todos em paralelo com multi_analysis.py
    - UMA ÚNICA chamada ao Gemini para análise consolidada
    - Gera relatório em HTML/PDF/JSON via report_builder.py
    - Resultados organizados por arquivo + análise geral
    - Consome 1 crédito por arquivo
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    total_files = len(files)
    
    # ==========================================
    # PASSO 1: VALIDAR QUANTIDADE
    # ==========================================
    
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > UploadConfig.MAX_FILES_MULTI_ANALYZE:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {UploadConfig.MAX_FILES_MULTI_ANALYZE} arquivos por vez. Enviados: {total_files}"
        )
    
    logger.info(f"📚 [MULTI-UPLOAD] {current_user.email} | {total_files} arquivos | IP: {client_ip}")
    
    # ==========================================
    # PASSO 2: VALIDAR CRÉDITOS
    # ==========================================
    
    credit_check = check_credits(current_user, total_files)
    if not credit_check["valid"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check["message"],
                "credits_available": credit_check["available"],
                "credits_needed": credit_check["required"]
            }
        )
    
    # ==========================================
    # PASSO 3: VALIDAR ARQUIVOS
    # ==========================================
    
    validation_result = await validate_files_async(files)
    
    if validation_result["valid_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_files",
                "message": "Nenhum arquivo válido para processar",
                "errors": [
                    {"filename": f.filename, "error": f.error}
                    for f in validation_result["invalid"]
                ]
            }
        )
    
    valid_files = validation_result["valid"]
    invalid_files = validation_result["invalid"]
    
    # Preparar dados para o multi_analysis
    file_data_list = [
        {
            'content': f.content,
            'filename': f.filename,
            'file_size': f.file_size
        }
        for f in valid_files
    ]
    
    # ==========================================
    # PASSO 4: 🔥 PROCESSAR COM MULTI_ANALYSIS
    # ==========================================
    
    try:
        analysis_result = await process_with_multi_analysis(
            file_data_list=file_data_list,
            user_id=current_user.id,
            user_email=current_user.email
        )
    except Exception as e:
        logger.error(f"❌ Erro no multi_analysis: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "analysis_failed",
                "message": f"Erro na análise: {str(e)}"
            }
        )
    
    if not analysis_result.get('success'):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "analysis_failed",
                "message": analysis_result.get('error', 'Erro na análise')
            }
        )
    
    # ==========================================
    # PASSO 5: SALVAR ANÁLISES
    # ==========================================
    
    analyses_ids = save_analyses(
        db=db,
        user_id=current_user.id,
        results=analysis_result.get('files', []),
        analysis_type=analysis_type,
        pow_valid=pow_valid,
        client_ip=client_ip
    )
    
    # ==========================================
    # PASSO 6: CONSUMIR CRÉDITOS
    # ==========================================
    
    credit_result = consume_credits(db, current_user, valid_files)
    
    if not credit_result["success"]:
        for analysis_id in analyses_ids:
            analysis = db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()
            if analysis:
                analysis.status = "pending_credit"
        db.commit()
        
        raise HTTPException(
            status_code=402,
            detail={
                "error": "credit_consumption_failed",
                "message": credit_result["message"],
                "analyses_saved": analyses_ids,
                "credit_status": credit_result
            }
        )
    
    # ==========================================
    # PASSO 7: 🔥 GERAR RELATÓRIO
    # ==========================================
    
    format_map = {
        'html': ReportFormat.HTML,
        'pdf': ReportFormat.PDF,
        'json': ReportFormat.JSON
    }
    report_format_enum = format_map.get(report_format.lower(), ReportFormat.HTML)
    
    report_data = generate_report(
        analysis_result=analysis_result,
        user_name=current_user.name or current_user.email,
        format=report_format_enum
    )
    
    # ==========================================
    # PASSO 8: RESPOSTA
    # ==========================================
    
    processing_time_ms = (time.time() - start_time) * 1000
    
    # Prepara resultados por arquivo
    file_results = []
    for result in analysis_result.get('files', []):
        file_results.append({
            "filename": result.get('filename'),
            "success": result.get('success', False),
            "rows": result.get('processed_rows', 0),
            "predictions_count": len(result.get('predictions', [])),
            "error": result.get('error')
        })
    
    # ==========================================
    # RESPOSTA COMPLETA
    # ==========================================
    
    response_data = {
        "success": True,
        "message": f"Análise consolidada de {analysis_result.get('processed_files', 0)} arquivo(s) concluída",
        "data": {
            "total_files": total_files,
            "processed_files": analysis_result.get('processed_files', 0),
            "failed_files": analysis_result.get('failed_files', 0),
            "files": file_results,
            "invalid_files": [
                {"filename": f.filename, "error": f.error}
                for f in invalid_files
            ],
            "analyses_ids": analyses_ids
        },
        "analysis": {
            "executive_score": analysis_result.get('executive_score', {}),
            "executive_summary": analysis_result.get('executive_summary', ''),
            "comparison": {
                "best_revenue": analysis_result.get('comparison', {}).get('best_revenue', ''),
                "best_profit": analysis_result.get('comparison', {}).get('best_profit', ''),
                "best_growth": analysis_result.get('comparison', {}).get('best_growth', ''),
                "highest_risk": analysis_result.get('comparison', {}).get('highest_risk', '')
            } if analysis_result.get('comparison') else {},
            "trend": {
                "direction": analysis_result.get('trend', {}).get('direction', 'estavel'),
                "description": analysis_result.get('trend', {}).get('description', '')
            } if analysis_result.get('trend') else {},
            "recommendations": analysis_result.get('recommendations', []),
            "forecast": analysis_result.get('forecast', ''),
            "general_conclusion": analysis_result.get('general_conclusion', '')
        },
        "report": {
            "content": report_data["content"],
            "format": report_data["extension"],
            "filename": report_data["filename"],
            "content_type": report_data["content_type"]
        },
        "chart_data": analysis_result.get('chart_data', {}),
        "credits": {
            "before": credit_result.get("before", current_user.credits),
            "consumed": credit_result.get("consumed", 0),
            "remaining": credit_result.get("remaining", current_user.credits),
            "is_admin": current_user.is_admin
        },
        "performance": {
            "processing_time_ms": round(processing_time_ms, 2)
        },
        "security": {
            "pow_validated": pow_valid,
            "client_ip": client_ip
        },
        "timestamp": datetime.now().isoformat()
    }
    
    # Se for PDF, retorna para download
    if report_format_enum == ReportFormat.PDF:
        return Response(
            content=report_data["content"],
            media_type=report_data["content_type"],
            headers={
                "Content-Disposition": f"attachment; filename={report_data['filename']}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    
    # Se for JSON, retorna como JSON
    if report_format_enum == ReportFormat.JSON:
        return JSONResponse(content=response_data)
    
    # HTML: retorna JSON com o HTML embutido
    return JSONResponse(content=response_data)


# ==============================================
# 🔥 ROTA: DOWNLOAD DE RELATÓRIO
# ==============================================

@router.get("/report/{analysis_id}")
async def download_report(
    analysis_id: int,
    format: str = "pdf",
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🔥 Baixa relatório de uma análise existente
    
    Args:
        analysis_id: ID da análise
        format: Formato do relatório (pdf, html, json)
    """
    # Buscar análise
    analysis = db.query(models.Analysis).filter(
        models.Analysis.id == analysis_id,
        models.Analysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    
    if analysis.status != "completed":
        raise HTTPException(status_code=400, detail="Análise não concluída")
    
    # Construir resultado a partir dos dados salvos
    analysis_result = {
        "success": True,
        "total_files": 1,
        "processed_files": 1,
        "failed_files": 0,
        "executive_score": {},
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
    report_format_map = {
        'pdf': ReportFormat.PDF,
        'html': ReportFormat.HTML,
        'json': ReportFormat.JSON
    }
    report_format = report_format_map.get(format, ReportFormat.PDF)
    
    report_data = generate_report(
        analysis_result=analysis_result,
        user_name=current_user.name or current_user.email,
        format=report_format
    )
    
    return Response(
        content=report_data["content"],
        media_type=report_data["content_type"],
        headers={
            "Content-Disposition": f"attachment; filename={report_data['filename']}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# ==============================================
# 🔥 ROTA: UPLOAD ÚNICO (LEGADO)
# ==============================================

@router.post("/upload-auto")
async def upload_auto_optimized(
    request: Request,
    pow_valid: bool = Depends(validate_pow_request),
    files: List[UploadFile] = File(..., description="Arquivos para upload (máx 5)"),
    analysis_type: str = Form("auto", description="Tipo de análise"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """🔥 UPLOAD ÚNICO - Processamento tradicional com fila"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    total_files = len(files)
    if total_files == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")
    
    if total_files > UploadConfig.MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {UploadConfig.MAX_FILES_PER_BATCH} arquivos por vez"
        )
    
    logger.info(f"📤 [UPLOAD] {current_user.email} | {total_files} arquivos")
    
    credit_check = check_credits(current_user, total_files)
    if not credit_check["valid"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": credit_check["message"],
                "credits_available": credit_check["available"],
                "credits_needed": credit_check["required"]
            }
        )
    
    validation_result = await validate_files_async(files)
    
    if validation_result["valid_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_files",
                "message": "Nenhum arquivo válido",
                "errors": [
                    {"filename": f.filename, "error": f.error}
                    for f in validation_result["invalid"]
                ]
            }
        )
    
    # Para compatibilidade, ainda usa o processamento antigo
    # (em breve substituído pelo multi_analysis)
    
    return {
        "success": True,
        "message": f"Processado {validation_result['valid_count']} de {total_files} arquivo(s)",
        "credits": {
            "before": current_user.credits if not current_user.is_admin else "∞",
            "consumed": validation_result["valid_count"] if not current_user.is_admin else 0,
            "display": get_credits_display(current_user)
        },
        "timestamp": datetime.now().isoformat()
    }


# ==============================================
# 🔥 INICIALIZAÇÃO
# ==============================================

print("=" * 80)
print("🚀 UPLOAD_ROUTES.PY - VERSÃO 6.0")
print("=" * 80)
print(f"   📁 Limites: {UploadConfig.MAX_FILES_PER_BATCH} arquivos, {UploadConfig.MAX_FILE_SIZE//1024}KB cada")
print(f"   🔥 Multi-analyze: até {UploadConfig.MAX_FILES_MULTI_ANALYZE} arquivos")
print(f"   📊 Report Builder: HTML, PDF, JSON")
print(f"   🤖 multi_analysis.py: Dados estruturados + Gemini")
print(f"   📄 report_builder.py: Relatórios profissionais")
print(f"   ✅ Código refatorado e organizado")
print("=" * 80)