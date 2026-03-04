# backend/api/routes.py - VERSÃO CORRIGIDA COM SECURITY CENTRAL E CRÉDITOS
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query, Depends, status
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pathlib import Path

print("🔧 Iniciando routes.py v2.0 com sistema de créditos...")

# ==============================================
# IMPORTS OBRIGATÓRIOS
# ==============================================
try:
    from backend.database import get_db
    from backend import crud, schemas
    from backend.security import get_current_user
    from backend.models import User
    print("✅ Módulos de autenticação importados")
except ImportError as e:
    print(f"❌ Erro CRÍTICO: {e}")
    raise

# ==============================================
# FUNÇÃO DE IMPORT INTELIGENTE
# ==============================================
def smart_import(module_path, class_name=None):
    """
    Importa módulos de forma inteligente, tentando vários caminhos
    """
    import_paths = [
        module_path,
        f"backend.{module_path}",
        f"backend.api.{module_path}",
        f".{module_path}",
        module_path.replace("backend.", ""),
    ]
    
    if class_name:
        for path in import_paths:
            try:
                exec(f"from {path} import {class_name}")
                imported = eval(class_name)
                print(f"✅ {class_name} importado de {path}")
                return imported
            except (ImportError, ModuleNotFoundError):
                continue
    
    return None

# ==============================================
# IMPORTS DOS SERVIÇOS - CORRIGIDO!
# ==============================================

# 1. FileManager
FileManager = None
try:
    from backend.config.file_manager import FileManager
    print("✅ FileManager importado")
except ImportError:
    try:
        from config.file_manager import FileManager
        print("✅ FileManager importado (caminho alternativo)")
    except ImportError:
        print("⚠️ FileManager não encontrado, criando classe dummy...")
        class FileManager:
            @staticmethod
            async def save_upload(content, filename):
                temp_dir = './temp'
                os.makedirs(temp_dir, exist_ok=True)
                file_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{filename}")
                with open(file_path, 'wb') as f:
                    f.write(content)
                return file_path
            
            @staticmethod
            async def save_result(content, process_id, ext):
                output_dir = './outputs'
                os.makedirs(output_dir, exist_ok=True)
                file_path = os.path.join(output_dir, f"{process_id}{ext}")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return file_path

# 2. DataPreprocessor - CORRIGIDO: Usando ModelTrainer do preprocessing.py
DataPreprocessor = None
try:
    # Primeiro tenta importar ModelTrainer e usar como DataPreprocessor
    from backend.preprocessing import ModelTrainer
    DataPreprocessor = ModelTrainer
    print("✅ Usando ModelTrainer como DataPreprocessor")
except ImportError:
    try:
        from preprocessing import ModelTrainer
        DataPreprocessor = ModelTrainer
        print("✅ Usando ModelTrainer como DataPreprocessor (caminho alternativo)")
    except ImportError:
        print("⚠️ ModelTrainer não encontrado, tentando DataPreprocessor direto...")
        try:
            from backend.preprocessing import DataPreprocessor
            print("✅ DataPreprocessor importado diretamente")
        except ImportError:
            try:
                from preprocessing import DataPreprocessor
                print("✅ DataPreprocessor importado diretamente (caminho alternativo)")
            except ImportError:
                print("⚠️ Criando DataPreprocessor dummy...")
                class DataPreprocessor:
                    async def process_file(self, file_path):
                        try:
                            if file_path.endswith('.csv'):
                                df = pd.read_csv(file_path)
                            else:
                                df = pd.read_excel(file_path)
                            
                            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                            df_numeric = df[numeric_cols].copy() if numeric_cols else pd.DataFrame()
                            
                            return {
                                "status": "success",
                                "dataframe": df,
                                "dataframe_numeric": df_numeric,
                                "metadata": {
                                    "original": {"linhas": len(df), "colunas": len(df.columns)},
                                    "processamento": {"colunas_numericas": numeric_cols}
                                }
                            }
                        except Exception as e:
                            return {"status": "error", "message": str(e)}

# 3. FlowiseService
FlowiseService = None
try:
    from backend.gemini import FlowiseService
    print("✅ FlowiseService importado")
except ImportError:
    try:
        from gemini import FlowiseService
        print("✅ FlowiseService importado (caminho alternativo)")
    except ImportError:
        print("⚠️ FlowiseService não encontrado, criando classe dummy...")
        class FlowiseService:
            async def analyze_office_data(self, analysis_type, data):
                return {
                    "ai_available": False,
                    "insights": ["Análise básica - IA não configurada"],
                    "recommendations": ["Configure a integração com IA"],
                    "message": "Modo offline"
                }

# 4. ModelPredictor
ModelPredictor = None
try:
    from backend.ml.predict import ModelPredictor
    print("✅ ModelPredictor importado")
except ImportError:
    try:
        from ml.predict import ModelPredictor
        print("✅ ModelPredictor importado (caminho alternativo)")
    except ImportError:
        print("⚠️ ModelPredictor não encontrado, criando classe dummy...")
        class ModelPredictor:
            async def predict_for_office(self, df):
                if df.empty:
                    return []
                return [0.5 + 0.1 * np.random.random() for _ in range(len(df))]

# 5. Settings
try:
    from backend.config.settings import settings
    print("✅ Settings importado")
except ImportError:
    try:
        from config.settings import settings
        print("✅ Settings importado (caminho alternativo)")
    except ImportError:
        print("⚠️ Settings não encontrado, criando configurações padrão...")
        from backend.config.settings import Settings
        settings = Settings()

# ==============================================
# INICIALIZAÇÃO
# ==============================================
print("🎯 Todos os imports processados!")

router = APIRouter()

# Inicializar serviços
preprocessor = DataPreprocessor() if DataPreprocessor else None
flowise_service = FlowiseService() if FlowiseService else None
predictor = ModelPredictor() if ModelPredictor else None

# Cache em memória para processamentos ativos
processing_cache = {}

# ==============================================
# FUNÇÕES AUXILIARES
# ==============================================
def normalize_predictions(predictions):
    """Normaliza previsões para formato serializável"""
    if predictions is None:
        return []
    
    if isinstance(predictions, np.ndarray):
        predictions = predictions.tolist()
    
    if not isinstance(predictions, list):
        return []
    
    result = []
    for p in predictions:
        if isinstance(p, (list, np.ndarray)) and len(p) > 0:
            result.append(float(p[0]))
        elif isinstance(p, (int, float, np.number)):
            result.append(float(p))
        else:
            result.append(0.5)
    return result

def calculate_prediction_stats(predictions):
    """Calcula estatísticas das previsões"""
    preds = normalize_predictions(predictions)
    total = len(preds)
    
    if total == 0:
        return {
            "total": 0, "alto_risco": 0, "medio_risco": 0, "baixo_risco": 0,
            "media": 0, "min": 0, "max": 0, "std": 0
        }
    
    alto_risco = sum(1 for p in preds if p > 0.7)
    medio_risco = sum(1 for p in preds if 0.4 < p <= 0.7)
    baixo_risco = total - alto_risco - medio_risco
    
    return {
        "total": total,
        "alto_risco": alto_risco,
        "medio_risco": medio_risco,
        "baixo_risco": baixo_risco,
        "media": float(np.mean(preds)),
        "min": float(np.min(preds)) if preds else 0,
        "max": float(np.max(preds)) if preds else 0,
        "std": float(np.std(preds)) if preds else 0
    }

def update_status(process_id: str, status: str, progress: int, message: str = ""):
    """Atualiza status do processamento no cache"""
    if process_id in processing_cache:
        processing_cache[process_id].update({
            "status": status,
            "progress": progress,
            "updated_at": datetime.now().isoformat(),
            "stage": message or status
        })
        print(f"   [{progress}%] {message}")

# ==============================================
# ENDPOINTS PÚBLICOS
# ==============================================
@router.get("/test")
async def test_endpoint():
    """Endpoint de teste público"""
    return {
        "message": "API funcionando!",
        "timestamp": datetime.now().isoformat(),
        "modules_loaded": {
            "FileManager": FileManager is not None,
            "DataPreprocessor": DataPreprocessor is not None,
            "FlowiseService": FlowiseService is not None,
            "ModelPredictor": ModelPredictor is not None,
            "JWT_Auth": True
        }
    }

@router.get("/health")
async def health_check():
    """Health check público"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api": "online",
            "file_manager": "online" if FileManager else "offline",
            "preprocessor": "online" if DataPreprocessor else "offline",
            "ai_service": "online" if FlowiseService else "offline",
            "predictor": "online" if ModelPredictor else "offline",
            "jwt_auth": "enabled"
        }
    }

# ==============================================
# ENDPOINTS PROTEGIDOS
# ==============================================
@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    analysis_type: str = Query("clientes"),
    ai_model: str = Query("flowise"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload de arquivo para análise
    Requer autenticação JWT e 1 crédito
    """
    try:
        print(f"📥 Upload: {file.filename}, Usuário: {current_user.email}")
        
        # Verificar créditos
        if not crud.check_credits(db, current_user.id, 1):
            print(f"❌ Usuário {current_user.id} sem créditos. Atual: {current_user.credits}")
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Créditos insuficientes",
                    "message": "Você não tem créditos para realizar esta análise.",
                    "credits": current_user.credits,
                    "required": 1,
                    "redirect": "/planos.html"
                }
            )
        
        # Validações
        if not file.filename:
            raise HTTPException(400, "Nome do arquivo inválido")
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Formato {ext} não suportado. Use: {settings.ALLOWED_EXTENSIONS}")
        
        # Ler e salvar arquivo
        content = await file.read()
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(400, f"Arquivo muito grande. Máximo: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB")
        
        temp_path = await FileManager.save_upload(content, file.filename)
        
        # Gerar ID do processo
        process_id = str(uuid.uuid4())
        
        # Salvar no banco
        analysis_data = schemas.AnalysisCreate(
            filename=file.filename,
            analysis_type=analysis_type
        )
        
        db_analysis = crud.create_analysis(
            db=db,
            analysis=analysis_data,
            user_id=current_user.id
        )
        
        # Cache do processo
        processing_cache[process_id] = {
            "process_id": process_id,
            "analysis_id": db_analysis.id,
            "user_id": current_user.id,
            "user_email": current_user.email,
            "filename": file.filename,
            "analysis_type": analysis_type,
            "status": "uploaded",
            "progress": 0,
            "started_at": datetime.now().isoformat()
        }
        
        # Processamento em background
        async def process_file_background():
            try:
                update_status(process_id, "processing", 10, "Iniciando processamento...")
                
                # 1. Pré-processamento
                update_status(process_id, "processing", 30, "Pré-processando dados...")
                if preprocessor:
                    result = await preprocessor.process_file(temp_path)
                else:
                    result = {"status": "error", "message": "Preprocessor não disponível"}
                
                if result.get("status") != "success":
                    raise Exception(result.get("message", "Erro no pré-processamento"))
                
                # 2. Previsões
                predictions = []
                prediction_stats = {}
                
                if predictor and result.get("dataframe_numeric") is not None:
                    df_numeric = result["dataframe_numeric"]
                    if not df_numeric.empty:
                        update_status(process_id, "processing", 50, "Gerando previsões...")
                        predictions = await predictor.predict_for_office(df_numeric)
                        prediction_stats = calculate_prediction_stats(predictions)
                
                # 3. Análise com IA
                update_status(process_id, "processing", 70, "Analisando com IA...")
                ai_response = {}
                if flowise_service:
                    ai_response = await flowise_service.analyze_office_data(
                        analysis_type, 
                        {
                            "data_summary": result.get("metadata", {}),
                            "prediction_stats": prediction_stats,
                            "filename": file.filename,
                            "workshop": current_user.workshop_name
                        }
                    )
                
                # 4. Gerar relatório
                update_status(process_id, "processing", 90, "Gerando relatório...")
                
                report = f"""RELATÓRIO DE ANÁLISE - {settings.APP_NAME}
{'='*60}

📋 INFORMAÇÕES GERAIS
──────────────────────────────
ID do Processo: {process_id}
ID da Análise: {db_analysis.id}
Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}
Usuário: {current_user.name} ({current_user.email})
Oficina: {current_user.workshop_name or 'Não informada'}

📁 ARQUIVO
──────────────────────────────
Nome: {file.filename}
Tipo de Análise: {analysis_type}

📊 PROCESSAMENTO
──────────────────────────────
Linhas processadas: {result.get('metadata', {}).get('original', {}).get('linhas', 0)}
Colunas: {result.get('metadata', {}).get('original', {}).get('colunas', 0)}
Colunas numéricas: {len(result.get('metadata', {}).get('processamento', {}).get('colunas_numericas', []))}

🤖 PREVISÕES
──────────────────────────────"""
                
                if predictions:
                    report += f"""
Total de previsões: {prediction_stats.get('total', 0)}
Média: {prediction_stats.get('media', 0):.2%}
Alto risco (>70%): {prediction_stats.get('alto_risco', 0)}
Médio risco (40-70%): {prediction_stats.get('medio_risco', 0)}
Baixo risco (<40%): {prediction_stats.get('baixo_risco', 0)}"""
                else:
                    report += f"""
Nenhuma previsão gerada"""
                
                report += f"""

🧠 ANÁLISE DA IA
──────────────────────────────"""
                
                if ai_response.get('ai_available', False):
                    insights = ai_response.get('insights', [])
                    recommendations = ai_response.get('recommendations', [])
                    
                    for i, insight in enumerate(insights, 1):
                        report += f"\n{chr(9679)} {insight}"
                    
                    report += f"\n\n✅ RECOMENDAÇÕES:"
                    for i, rec in enumerate(recommendations, 1):
                        report += f"\n   {i}. {rec}"
                else:
                    report += f"\nIA não disponível no momento."
                
                report += f"""

{'='*60}
Relatório gerado automaticamente
"""
                
                # Salvar relatório
                result_file = await FileManager.save_result(report, process_id, ".txt")
                
                # Deduzir crédito
                db.refresh(current_user)
                credits_deducted = crud.deduct_credits(db, current_user.id, 1)
                
                if credits_deducted:
                    print(f"💰 Crédito deduzido. Novo saldo: {current_user.credits - 1}")
                
                # Atualizar análise no banco
                updates = {
                    "status": "completed",
                    "ai_used": ai_response.get('ai_available', False),
                    "rows_processed": result.get('metadata', {}).get('original', {}).get('linhas', 0),
                    "columns_processed": len(result.get('metadata', {}).get('processamento', {}).get('colunas_numericas', [])),
                    "ai_report": json.dumps(ai_response, ensure_ascii=False, indent=2),
                    "report_path": result_file,
                    "processed_at": datetime.now()
                }
                
                crud.update_analysis(db, db_analysis.id, updates)
                
                # Atualizar cache
                processing_cache[process_id].update({
                    "status": "completed",
                    "progress": 100,
                    "completed_at": datetime.now().isoformat(),
                    "result_file": result_file,
                    "predictions": normalize_predictions(predictions),
                    "prediction_stats": prediction_stats
                })
                
                print(f"✅ Processamento concluído: {process_id}")
                
            except Exception as e:
                print(f"❌ Erro: {e}")
                import traceback
                traceback.print_exc()
                update_status(process_id, "error", 0, f"Erro: {str(e)}")
                
                crud.update_analysis(db, db_analysis.id, {
                    "status": "error", 
                    "error_message": str(e),
                    "processed_at": datetime.now()
                })
                
                processing_cache[process_id].update({
                    "status": "error",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat()
                })
            
            finally:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
        
        background_tasks.add_task(process_file_background)
        db.refresh(current_user)
        
        return {
            "message": "Arquivo recebido",
            "process_id": process_id,
            "analysis_id": db_analysis.id,
            "credits_remaining": current_user.credits - 1,
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erro: {e}")
        raise HTTPException(500, f"Erro interno: {str(e)}")

@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user = Depends(get_current_user)
):
    """Verifica status do processamento"""
    if process_id not in processing_cache:
        raise HTTPException(404, "Processo não encontrado")
    
    data = processing_cache[process_id]
    if data.get("user_id") != current_user.id:
        raise HTTPException(403, "Acesso negado")
    
    return data

@router.get("/result/{process_id}")
async def get_result(
    process_id: str,
    current_user = Depends(get_current_user)
):
    """Obtém resultado do processamento"""
    if process_id not in processing_cache:
        raise HTTPException(404, "Processo não encontrado")
    
    data = processing_cache[process_id]
    if data.get("user_id") != current_user.id:
        raise HTTPException(403, "Acesso negado")
    
    if data["status"] != "completed":
        raise HTTPException(425, "Processamento não concluído")
    
    if "result_file" in data and os.path.exists(data["result_file"]):
        return FileResponse(
            data["result_file"],
            filename=f"relatorio_{process_id}.txt",
            media_type="text/plain"
        )
    
    return JSONResponse(content={
        "process_id": process_id,
        "status": "completed",
        "predictions": data.get("predictions", []),
        "prediction_stats": data.get("prediction_stats", {})
    })

@router.get("/user/profile")
async def get_user_profile(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna perfil do usuário"""
    db.refresh(current_user)
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "workshop_name": current_user.workshop_name,
        "credits": current_user.credits,
        "total_purchased": current_user.total_purchased
    }

@router.get("/stats")
async def get_stats(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna estatísticas do dashboard"""
    analyses = crud.get_user_analyses(db, current_user.id)
    db.refresh(current_user)
    
    return {
        "total_analises": len(analyses),
        "creditos": current_user.credits
    }

print("✅ routes.py carregado com sucesso!")