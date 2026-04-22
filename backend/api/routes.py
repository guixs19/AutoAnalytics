# backend/api/routes.py - VERSÃO COMPLETA COM GEMINI
"""
ROUTES.PY - VERSÃO COM GEMINI
----------------------
✅ Usuários comuns: começam com 3 créditos
⭐ Plano Premium: ganham 1 crédito por dia
👑 Admin: créditos ilimitados
💰 Upload: CONSome créditos (NÃO ganham)
🤖 IA: Google Gemini (substituiu Flowise)
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query, Depends, Form
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import uuid
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pathlib import Path

print("🔧 Iniciando routes.py v6.0 - Com Google Gemini")

# ==============================================
# IMPORTS OBRIGATÓRIOS
# ==============================================
try:
    from backend.database import get_db
    from backend import crud, schemas
    from backend.security import get_current_user
    from backend.models import User, UserPlan
    from backend.crud import get_credits_display, check_credits, deduct_credits
    from backend.services.daily_credits_service import DailyCreditsService
    print("✅ Módulos de autenticação importados")
except ImportError as e:
    print(f"❌ Erro CRÍTICO: {e}")
    raise

# ==============================================
# IMPORTS DOS SERVIÇOS
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

# 2. DataPreprocessor
DataPreprocessor = None
try:
    from backend.preprocessing import ModelTrainer
    DataPreprocessor = ModelTrainer
    print("✅ ModelTrainer como DataPreprocessor")
except ImportError:
    try:
        from preprocessing import ModelTrainer
        DataPreprocessor = ModelTrainer
        print("✅ ModelTrainer (caminho alternativo)")
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

# 3. GeminiService (substituiu Flowise)
GeminiService = None
try:
    from backend.services.gemini_service import GeminiService
    print("✅ GeminiService importado")
except ImportError:
    try:
        from backend.GeminiService import GeminiService
        print("✅ GeminiService importado de gemini.py")
    except ImportError:
        try:
            from backend.GeminiService import GeminiService
            print("✅ GeminiService importado (caminho alternativo)")
        except ImportError:
            print("⚠️ GeminiService não encontrado, criando classe dummy...")
            class GeminiService:
                def __init__(self):
                    self.model = None
                    print("⚠️ GeminiService dummy inicializado")
                
                async def analyze_office_data(self, data_type: str, data: Dict) -> Dict:
                    return {
                        "success": False,
                        "ai_available": False,
                        "insights": ["⚠️ IA não configurada. Configure a chave API do Gemini."],
                        "recommendations": ["✅ Adicione GEMINI_API_KEY ao arquivo .env"],
                        "message": "Modo offline - Gemini não disponível"
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
            
            def get_ml_insights_for_gemini(self, df, predictions=None):
                return {"status": "dummy", "message": "Modelo não configurado"}

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

# 6. AutoML
try:
    from backend.ml.automl_simple import automl_office
    print("✅ AutoML importado")
except ImportError:
    try:
        from ml.automl_simple import automl_office
        print("✅ AutoML importado (caminho alternativo)")
    except ImportError:
        print("⚠️ AutoML não disponível")
        automl_office = None

# 7. DailyCreditsService
try:
    daily_credits_service = DailyCreditsService()
    print("✅ DailyCreditsService inicializado")
except Exception as e:
    print(f"⚠️ Erro ao inicializar DailyCreditsService: {e}")
    daily_credits_service = None

# 8. BoostingEnsemble (opcional)
try:
    from backend.ml.boosting_ensemble import boosting_ensemble
    print("✅ BoostingEnsemble importado")
except ImportError:
    print("⚠️ BoostingEnsemble não disponível")
    boosting_ensemble = None

# ==============================================
# INICIALIZAÇÃO
# ==============================================
print("🎯 Todos os imports processados!")

router = APIRouter()

# Inicializar serviços
preprocessor = DataPreprocessor() if DataPreprocessor else None
gemini_service = GeminiService() if GeminiService else None
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

async def auto_detect_target(df):
    """Detecta automaticamente a melhor coluna para ser target"""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    
    if len(numeric_cols) == 0:
        return None, "error", "Nenhuma coluna numérica encontrada"
    
    if len(numeric_cols) == 1:
        return numeric_cols[0], "regression", "Única coluna numérica"
    
    candidates = []
    for col in numeric_cols:
        unique_count = df[col].nunique()
        if 2 <= unique_count <= 10:
            candidates.append((col, unique_count, "classificação"))
    
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0], "classification", f"Coluna categórica com {candidates[0][1]} classes"
    
    suggestive_names = ['target', 'alvo', 'classe', 'resultado', 'retorno', 'risco']
    for col in numeric_cols:
        col_lower = col.lower()
        if any(name in col_lower for name in suggestive_names):
            return col, "classification", f"Coluna com nome sugestivo: {col}"
    
    return numeric_cols[-1], "regression", "Última coluna numérica (padrão)"

def check_user_credits_before_upload(user: User, db: Session) -> Dict:
    """Verifica créditos antes do upload"""
    if user.is_admin:
        return {
            "can_proceed": True,
            "credits_display": "∞",
            "message": "Admin - créditos ilimitados"
        }
    
    if user.credits <= 0:
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        if is_premium:
            return {
                "can_proceed": False,
                "credits_display": "0",
                "message": "Você usou todos seus créditos. Amanhã você ganha mais 1 do plano premium!",
                "suggestion": "Volte amanhã ou compre mais créditos"
            }
        else:
            return {
                "can_proceed": False,
                "credits_display": "0",
                "message": "Você não tem créditos suficientes",
                "suggestion": "Compre créditos na página de planos"
            }
    
    return {
        "can_proceed": True,
        "credits_display": str(user.credits),
        "credits_remaining": user.credits - 1,
        "message": f"Você tem {user.credits} créditos. Esta análise consumirá 1 crédito."
    }

# ==============================================
# ENDPOINTS PÚBLICOS
# ==============================================
@router.get("/test")
async def test_endpoint():
    """Endpoint de teste público"""
    return {
        "message": "API funcionando com Google Gemini!",
        "timestamp": datetime.now().isoformat(),
        "modules_loaded": {
            "FileManager": FileManager is not None,
            "DataPreprocessor": DataPreprocessor is not None,
            "GeminiService": GeminiService is not None,
            "ModelPredictor": ModelPredictor is not None,
            "AutoML": automl_office is not None,
            "BoostingEnsemble": boosting_ensemble is not None,
            "DailyCreditsService": daily_credits_service is not None,
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
            "ai_service": "online" if gemini_service else "offline",
            "ai_provider": "Google Gemini",
            "predictor": "online" if ModelPredictor else "offline",
            "automl": "online" if automl_office else "offline",
            "boosting_ensemble": "online" if boosting_ensemble else "offline",
            "daily_credits": "online" if daily_credits_service else "offline",
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
    ai_model: str = Query("gemini"),  # Agora padrão é gemini
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload de arquivo para análise com Google Gemini
    ✅ Admin: não consome créditos
    ⭐ Premium: consome 1 crédito
    👤 Comum: consome 1 crédito
    🤖 IA: Google Gemini
    """
    try:
        print(f"📥 Upload: {file.filename}, Usuário: {current_user.email}, IA: Gemini")
        
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
        
        if not file.filename:
            raise HTTPException(400, "Nome do arquivo inválido")
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Formato {ext} não suportado. Use: {settings.ALLOWED_EXTENSIONS}")
        
        content = await file.read()
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(400, f"Arquivo muito grande. Máximo: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB")
        
        temp_path = await FileManager.save_upload(content, file.filename)
        
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
        
        async def process_file_background():
            try:
                update_status(process_id, "processing", 10, "Iniciando processamento...")
                
                update_status(process_id, "processing", 30, "Pré-processando dados...")
                if preprocessor:
                    result = await preprocessor.process_file(temp_path)
                else:
                    result = {"status": "error", "message": "Preprocessor não disponível"}
                
                if result.get("status") != "success":
                    raise Exception(result.get("message", "Erro no pré-processamento"))
                
                predictions = []
                prediction_stats = {}
                
                if predictor and result.get("dataframe_numeric") is not None:
                    df_numeric = result["dataframe_numeric"]
                    if not df_numeric.empty:
                        update_status(process_id, "processing", 50, "Gerando previsões...")
                        predictions = await predictor.predict_for_office(df_numeric)
                        prediction_stats = calculate_prediction_stats(predictions)
                        
                        # Extrair insights do ML para o Gemini
                        ml_insights = predictor.get_ml_insights_for_gemini(df_numeric, predictions)
                
                update_status(process_id, "processing", 70, "Analisando com Google Gemini...")
                ai_response = {}
                if gemini_service:
                    ai_response = await gemini_service.analyze_office_data(
                        analysis_type, 
                        {
                            "data_summary": result.get("metadata", {}),
                            "prediction_stats": prediction_stats,
                            "ml_insights": ml_insights if 'ml_insights' in dir() else {},
                            "filename": file.filename,
                            "workshop": current_user.workshop_name,
                            "total_records": len(result.get("dataframe", [])),
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                
                update_status(process_id, "processing", 90, "Gerando relatório...")
                
                admin_tag = " [ADMIN]" if current_user.is_admin else ""
                premium_tag = " ⭐[PREMIUM]" if (current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()) else ""
                
                credits_before = current_user.credits
                credits_after = credits_before
                
                if not current_user.is_admin:
                    success = deduct_credits(db, current_user.id, 1, f"Análise Gemini: {file.filename}")
                    if success:
                        db.refresh(current_user)
                        credits_after = current_user.credits
                        print(f"💰 Crédito deduzido: {credits_before} → {credits_after}")
                
                premium_info = None
                if daily_credits_service and current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium():
                    premium_info = await daily_credits_service.check_premium_daily_credit(db, current_user.id)
                
                # Gerar relatório com análise do Gemini
                report = f"""RELATÓRIO DE ANÁLISE COM GOOGLE GEMINI - {settings.APP_NAME}{admin_tag}{premium_tag}
{'='*70}

📋 INFORMAÇÕES GERAIS
──────────────────────────────
ID do Processo: {process_id}
ID da Análise: {db_analysis.id}
Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}
Usuário: {current_user.name} ({current_user.email})
Oficina: {current_user.workshop_name or 'Não informada'}
Tipo: {'👑 ADMIN' if current_user.is_admin else '⭐ PREMIUM' if (current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()) else '👤 USUÁRIO COMUM'}
IA Utilizada: 🤖 Google Gemini

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

🧠 ANÁLISE DO GOOGLE GEMINI
──────────────────────────────"""
                
                if ai_response.get('success', False):
                    insights = ai_response.get('insights', [])
                    recommendations = ai_response.get('recommendations', [])
                    
                    report += f"\n\n📊 INSIGHTS IDENTIFICADOS:"
                    for i, insight in enumerate(insights, 1):
                        report += f"\n   {i}. {insight}"
                    
                    report += f"\n\n✅ RECOMENDAÇÕES ESTRATÉGICAS:"
                    for i, rec in enumerate(recommendations, 1):
                        report += f"\n   {i}. {rec}"
                    
                    if ai_response.get('full_analysis'):
                        report += f"\n\n📝 ANÁLISE COMPLETA:\n{ai_response.get('full_analysis')}"
                else:
                    report += f"\n⚠️ Gemini não disponível: {ai_response.get('message', 'Configure a chave API')}"
                
                report += f"""

💰 CRÉDITOS
──────────────────────────────
Créditos antes: {'∞' if current_user.is_admin else credits_before}
Créditos depois: {'∞' if current_user.is_admin else credits_after}
Status: {'👑 ADMIN (não consome)' if current_user.is_admin else '✅ 1 crédito consumido'}

"""
                
                if premium_info and premium_info.get('is_premium'):
                    report += f"""
⭐ PLANO PREMIUM
──────────────────────────────
Recebeu hoje: {'✅ Sim' if premium_info.get('received_today') else '❌ Não'}
Dias restantes: {premium_info.get('days_left', 0)}
Próximo crédito: {premium_info.get('next_credit_date', 'Amanhã')}
"""
                
                report += f"""
{'='*70}
Relatório gerado automaticamente pelo AutoAnalytics com Google Gemini
"""
                
                result_file = await FileManager.save_result(report, process_id, ".txt")
                
                updates = {
                    "status": "completed",
                    "ai_used": ai_response.get('success', False),
                    "rows_processed": result.get('metadata', {}).get('original', {}).get('linhas', 0),
                    "columns_processed": len(result.get('metadata', {}).get('processamento', {}).get('colunas_numericas', [])),
                    "ai_report": json.dumps(ai_response, ensure_ascii=False, indent=2),
                    "report_path": result_file,
                    "processed_at": datetime.now()
                }
                
                crud.update_analysis(db, db_analysis.id, updates)
                
                processing_cache[process_id].update({
                    "status": "completed",
                    "progress": 100,
                    "completed_at": datetime.now().isoformat(),
                    "result_file": result_file,
                    "predictions": normalize_predictions(predictions),
                    "prediction_stats": prediction_stats,
                    "credits_before": credits_before,
                    "credits_after": credits_after,
                    "credits_display": "∞" if current_user.is_admin else str(credits_after),
                    "premium_info": premium_info,
                    "ai_provider": "gemini"
                })
                
                print(f"✅ Processamento concluído com Gemini: {process_id}")
                
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
        
        return {
            "message": "Arquivo recebido para processamento com Google Gemini",
            "process_id": process_id,
            "analysis_id": db_analysis.id,
            "credits_before": current_user.credits,
            "credits_after": current_user.credits - 1 if not current_user.is_admin and current_user.credits > 0 else current_user.credits,
            "credits_display": get_credits_display(current_user),
            "is_admin": current_user.is_admin,
            "is_premium": current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium(),
            "status": "processing",
            "ai_provider": "gemini",
            "note": "Esta análise consumirá 1 crédito e usará Google Gemini" if not current_user.is_admin else "Admin não consome créditos"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erro: {e}")
        raise HTTPException(500, f"Erro interno: {str(e)}")

# ==============================================
# UPLOAD AUTOMÁTICO
# ==============================================

@router.post("/upload-auto")
async def upload_auto(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    algorithm: str = Form("auto"),
    auto_detect: bool = Form(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🚀 UPLOAD AUTOMÁTICO com Google Gemini - Detecta tudo sozinho"""
    try:
        print(f"📥 Upload automático: {file.filename}, Usuário: {current_user.email}, IA: Gemini")
        
        credit_check = check_user_credits_before_upload(current_user, db)
        
        if not credit_check["can_proceed"]:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Créditos insuficientes",
                    "message": credit_check["message"],
                    "suggestion": credit_check.get("suggestion", "Compre mais créditos"),
                    "credits": current_user.credits,
                    "required": 1
                }
            )
        
        if not file.filename:
            raise HTTPException(400, "Nome do arquivo inválido")
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Formato {ext} não suportado. Use: {settings.ALLOWED_EXTENSIONS}")
        
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(400, f"Arquivo muito grande. Máximo: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB")
        
        temp_path = await FileManager.save_upload(content, file.filename)
        
        process_id = str(uuid.uuid4())
        
        analysis_data = schemas.AnalysisCreate(
            filename=file.filename,
            analysis_type="auto"
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
            "algorithm": algorithm,
            "auto_detect": auto_detect,
            "status": "uploaded",
            "progress": 0,
            "started_at": datetime.now().isoformat(),
            "is_admin": current_user.is_admin,
            "is_premium": current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
        }
        
        async def process_auto_background():
            try:
                update_status(process_id, "detecting", 10, "Detectando padrões nos dados...")
                
                if not preprocessor:
                    raise Exception("Preprocessor não disponível")
                
                result = await preprocessor.process_file(temp_path)
                
                if result.get("status") != "success":
                    raise Exception(result.get("message", "Erro no pré-processamento"))
                
                df = result["dataframe"]
                df_numeric = result["dataframe_numeric"]
                
                update_status(process_id, "detecting", 30, "Identificando coluna alvo...")
                
                target_column, problem_type, detection_reason = await auto_detect_target(df)
                
                if target_column is None:
                    raise Exception("Não foi possível detectar uma coluna alvo adequada")
                
                print(f"✅ Target detectado: {target_column} ({problem_type}) - {detection_reason}")
                
                update_status(process_id, "analyzing", 50, f"Target: {target_column} ({problem_type})...")
                
                model_info = {
                    "best_model": algorithm if algorithm != "auto" else "AutoML",
                    "accuracy": 0.85
                }
                
                if automl_office and algorithm == "auto":
                    update_status(process_id, "training", 60, "Executando AutoML...")
                    try:
                        ranking = automl_office.comparar_modelos_classificacao(
                            df_numeric,
                            target_column,
                            integrar_apos_treino=True,
                            verbose=False
                        )
                        if ranking is not None and not ranking.empty:
                            model_info["best_model"] = ranking.iloc[0]['Modelo']
                            model_info["accuracy"] = float(ranking.iloc[0]['Acurácia (CV)'])
                    except Exception as e:
                        print(f"⚠️ AutoML erro: {e}")
                
                update_status(process_id, "predicting", 80, "Gerando previsões e analisando com Gemini...")
                
                predictions = []
                if predictor:
                    pred_results = await predictor.predict_for_office(df_numeric)
                    predictions = normalize_predictions(pred_results)
                
                stats = calculate_prediction_stats(predictions) if predictions else {}
                
                # Análise com Google Gemini
                ai_analysis = {}
                if gemini_service:
                    ml_insights = predictor.get_ml_insights_for_gemini(df_numeric, predictions) if predictor else {}
                    
                    ai_analysis = await gemini_service.analyze_office_data(
                        "auto",
                        {
                            "target_detected": target_column,
                            "problem_type": problem_type,
                            "detection_reason": detection_reason,
                            "prediction_stats": stats,
                            "ml_insights": ml_insights,
                            "model_info": model_info,
                            "total_rows": len(df),
                            "total_columns": len(df.columns),
                            "numeric_columns": len(df_numeric.columns),
                            "filename": file.filename
                        }
                    )
                
                analysis_info = {
                    "detected_columns": len(df.columns),
                    "numeric_columns": len(df_numeric.columns),
                    "target_column": target_column,
                    "problem_type": "classificação" if problem_type == "classification" else "regressão",
                    "detection_reason": detection_reason,
                    "features_count": len(df_numeric.columns) - 1,
                    "model_used": model_info.get("best_model", "AutoML"),
                    "accuracy": model_info.get("accuracy", 0.85),
                    "ai_analysis": ai_analysis.get('full_analysis', '')[:500] if ai_analysis else ''
                }
                
                credits_before = current_user.credits
                credits_after = credits_before
                
                if not current_user.is_admin:
                    success = deduct_credits(db, current_user.id, 1, f"Auto análise Gemini: {file.filename}")
                    if success:
                        db.refresh(current_user)
                        credits_after = current_user.credits
                
                premium_info = None
                if daily_credits_service and current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium():
                    premium_info = await daily_credits_service.check_premium_daily_credit(db, current_user.id)
                
                processing_cache[process_id].update({
                    "status": "completed",
                    "progress": 100,
                    "completed_at": datetime.now().isoformat(),
                    "predictions": predictions,
                    "prediction_stats": stats,
                    "target_detected": target_column,
                    "problem_type": problem_type,
                    "analysis_info": analysis_info,
                    "ai_analysis": ai_analysis,
                    "rows_processed": len(df),
                    "credits_before": credits_before,
                    "credits_after": credits_after,
                    "credits_display": "∞" if current_user.is_admin else str(credits_after),
                    "premium_info": premium_info,
                    "ai_provider": "gemini"
                })
                
                crud.update_analysis(db, db_analysis.id, {
                    "status": "completed",
                    "rows_processed": len(df),
                    "columns_processed": len(df_numeric.columns),
                    "ai_used": ai_analysis.get('success', False),
                    "ai_report": json.dumps(ai_analysis, ensure_ascii=False, indent=2)[:5000],
                    "processed_at": datetime.now()
                })
                
                print(f"✅ Análise automática com Gemini concluída: {process_id}")
                
            except Exception as e:
                print(f"❌ Erro na análise automática: {e}")
                import traceback
                traceback.print_exc()
                
                processing_cache[process_id].update({
                    "status": "error",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat()
                })
                
                crud.update_analysis(db, db_analysis.id, {
                    "status": "error", 
                    "error_message": str(e),
                    "processed_at": datetime.now()
                })
            
            finally:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
        
        background_tasks.add_task(process_auto_background)
        
        return {
            "message": "Análise automática com Google Gemini iniciada com sucesso!",
            "process_id": process_id,
            "analysis_id": db_analysis.id,
            "credits_before": current_user.credits,
            "credits_after": current_user.credits - 1 if not current_user.is_admin and current_user.credits > 0 else current_user.credits,
            "credits_display": get_credits_display(current_user),
            "is_admin": current_user.is_admin,
            "is_premium": current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium(),
            "status": "processing",
            "ai_provider": "gemini",
            "info": "O sistema irá detectar automaticamente os padrões nos dados e analisar com Google Gemini"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erro no upload automático: {e}")
        raise HTTPException(500, f"Erro interno: {str(e)}")

# ==============================================
# ROTAS DE STATUS E RESULTADO
# ==============================================

@router.get("/status/{process_id}")
async def get_status(
    process_id: str,
    current_user = Depends(get_current_user)
):
    """Verifica status do processamento"""
    if process_id not in processing_cache:
        raise HTTPException(404, "Processo não encontrado")
    
    data = processing_cache[process_id]
    if data.get("user_id") != current_user.id and not current_user.is_admin:
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
    if data.get("user_id") != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Acesso negado")
    
    if data["status"] != "completed":
        raise HTTPException(425, "Processamento não concluído")
    
    if "target_detected" in data:
        return JSONResponse(content={
            "process_id": process_id,
            "status": "completed",
            "predictions": data.get("predictions", []),
            "prediction_stats": data.get("prediction_stats", {}),
            "target_detected": data.get("target_detected"),
            "problem_type": data.get("problem_type"),
            "analysis_info": data.get("analysis_info", {}),
            "ai_analysis": data.get("ai_analysis", {}),
            "rows_processed": data.get("rows_processed", 0),
            "credits_remaining": data.get("credits_display", "0"),
            "ai_provider": data.get("ai_provider", "gemini")
        })
    
    if "result_file" in data and os.path.exists(data["result_file"]):
        return FileResponse(
            data["result_file"],
            filename=f"relatorio_gemini_{process_id}.txt",
            media_type="text/plain"
        )
    
    return JSONResponse(content={
        "process_id": process_id,
        "status": "completed",
        "predictions": data.get("predictions", []),
        "prediction_stats": data.get("prediction_stats", {}),
        "credits_remaining": data.get("credits_display", "0"),
        "ai_provider": data.get("ai_provider", "gemini")
    })

# ==============================================
# ROTAS DE USUÁRIO
# ==============================================

@router.get("/user/profile")
async def get_user_profile(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna perfil do usuário"""
    db.refresh(current_user)
    
    is_premium = current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
    
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "workshop_name": current_user.workshop_name,
        "credits": current_user.credits,
        "credits_display": get_credits_display(current_user),
        "total_purchased": current_user.total_purchased,
        "is_admin": current_user.is_admin,
        "is_premium": is_premium,
        "role": current_user.role.value if hasattr(current_user.role, 'value') else current_user.role,
        "plan": current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan,
        "premium_expires_at": current_user.premium_expires_at.isoformat() if current_user.premium_expires_at else None,
        "premium_days_left": current_user.get_premium_days_left() if is_premium else 0
    }

@router.get("/stats")
async def get_stats(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna estatísticas do dashboard"""
    try:
        print(f"📊 Buscando estatísticas para usuário: {current_user.email}")
        
        analyses = crud.get_user_analyses(db, current_user.id)
        
        hoje = date.today()
        analises_hoje = sum(1 for a in analyses if a.uploaded_at.date() == hoje)
        
        is_premium = current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
        
        premium_info = None
        if daily_credits_service and is_premium:
            premium_info = await daily_credits_service.check_premium_daily_credit(db, current_user.id)
        
        return {
            "total_analises": len(analyses),
            "analises_hoje": analises_hoje,
            "creditos": "∞" if current_user.is_admin else current_user.credits,
            "creditos_numeric": 999999 if current_user.is_admin else current_user.credits,
            "creditos_display": get_credits_display(current_user),
            "nome": current_user.name,
            "email": current_user.email,
            "workshop": current_user.workshop_name,
            "is_admin": current_user.is_admin,
            "is_premium": is_premium,
            "premium_info": premium_info,
            "initial_credits": 3,
            "ai_provider": "Google Gemini",
            "status": "success"
        }
        
    except Exception as e:
        print(f"❌ Erro em get_stats: {e}")
        return {
            "total_analises": 0,
            "analises_hoje": 0,
            "creditos": "∞" if current_user.is_admin else (current_user.credits if current_user else 0),
            "creditos_display": get_credits_display(current_user) if current_user else "0",
            "nome": current_user.name if current_user else "Usuário",
            "email": current_user.email if current_user else "",
            "is_admin": current_user.is_admin if current_user else False,
            "is_premium": False,
            "ai_provider": "Google Gemini",
            "status": "error",
            "mensagem": "Erro ao carregar estatísticas completas"
        }

# ==============================================
# HISTÓRICO DE ANÁLISES
# ==============================================

@router.get("/analyses/history")
async def get_analysis_history(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Retorna histórico de análises do usuário"""
    try:
        print(f"📜 Buscando histórico para usuário: {current_user.email}")
        
        analyses = crud.get_user_analyses(db, current_user.id, limit=limit)
        
        return [
            {
                "id": a.id,
                "filename": a.filename,
                "status": a.status,
                "created_at": a.uploaded_at.isoformat(),
                "analysis_type": a.analysis_type,
                "ai_used": a.ai_used,
                "ai_provider": "gemini" if a.ai_used else None,
                "rows_processed": a.rows_processed,
                "columns_processed": a.columns_processed
            }
            for a in analyses
        ]
    except Exception as e:
        print(f"❌ Erro ao buscar histórico: {e}")
        return []

# ==============================================
# ROTAS DE CRÉDITOS E PREMIUM
# ==============================================

@router.get("/credits/status")
async def get_credits_status(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna status detalhado dos créditos do usuário"""
    db.refresh(current_user)
    
    is_premium = current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
    
    premium_info = None
    if daily_credits_service and is_premium:
        premium_info = await daily_credits_service.get_premium_summary(db, current_user.id)
    
    if current_user.is_admin:
        return {
            "success": True,
            "credits": "∞",
            "credits_numeric": 999999,
            "credits_display": "∞",
            "is_admin": True,
            "is_premium": False,
            "message": "Admin tem créditos ilimitados"
        }
    
    return {
        "success": True,
        "credits": current_user.credits,
        "credits_numeric": current_user.credits,
        "credits_display": str(current_user.credits),
        "is_admin": False,
        "is_premium": is_premium,
        "premium_info": premium_info,
        "message": f"Você tem {current_user.credits} crédito(s) disponível(is)",
        "initial_credits": 3,
        "note": "Você começou com 3 créditos. Assine o plano premium para ganhar 1 crédito por dia!",
        "ai_provider": "Google Gemini"
    }

@router.get("/premium/status")
async def get_premium_status(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna status específico do plano premium"""
    if not daily_credits_service:
        raise HTTPException(503, "Serviço de créditos premium indisponível")
    
    return await daily_credits_service.get_premium_summary(db, current_user.id)

@router.post("/premium/check-daily")
async def check_premium_daily(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """⭐ Verifica e adiciona crédito diário do premium"""
    if not daily_credits_service:
        raise HTTPException(503, "Serviço de créditos premium indisponível")
    
    is_premium = current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
    
    if not is_premium:
        raise HTTPException(403, "Usuário não possui plano premium ativo")
    
    result = await daily_credits_service.check_and_add_daily_credit(db, current_user.id)
    
    return result

# ==============================================
# DASHBOARD
# ==============================================

@router.get("/dashboard")
async def dashboard(
    request: Request,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Rota do dashboard"""
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates
    
    templates = Jinja2Templates(directory="frontend")
    
    is_premium = current_user.plan == UserPlan.PREMIUM_MENSAL and current_user.is_premium()
    
    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request, 
            "user": current_user,
            "credits": "∞" if current_user.is_admin else current_user.credits,
            "credits_display": get_credits_display(current_user),
            "name": current_user.name,
            "is_admin": current_user.is_admin,
            "is_premium": is_premium,
            "ai_provider": "Google Gemini"
        }
    )

# ==============================================
# ROTAS DE ADMIN
# ==============================================

@router.get("/admin/check")
async def check_admin_status(
    current_user = Depends(get_current_user)
):
    """Verifica se usuário é admin"""
    return {
        "is_admin": current_user.is_admin,
        "credits_display": get_credits_display(current_user),
        "email": current_user.email
    }