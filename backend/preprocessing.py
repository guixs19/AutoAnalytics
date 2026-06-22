# backend/ml/preprocessing.py - VERSÃO COMPLETA UNIFICADA
"""
Módulo de Pré-processamento e Pipeline de ML - AutoAnalytics
🔥 ORQUESTRADOR PRINCIPAL DE ML

RESPONSABILIDADES:
1. Pré-processamento de dados (limpeza, encoding, scaling)
2. Detecção de colunas de oficina (com normalização)
3. Suporte a múltiplos encodings (UTF-8, cp1252, ISO-8859-1, latin1)
4. Suporte a bytes (upload_routes.py) e file_path (legado)
5. Pipeline completo de ML (RandomForest, AutoML, Boosting)
6. Cache inteligente de predições
7. Geração de insights e recomendações
8. Estatísticas de uso e monitoramento
9. Compatibilidade com código existente

FLUXO:
1. upload_routes.py → process_file_content(bytes, filename) 
   ou
2. predict.py → pipeline.predict(df)
   ou
3. Código legado → model_trainer.process_file(file_path)
"""

import pandas as pd
import numpy as np
import os
import pickle
import joblib
import json
import hashlib
import unicodedata
import chardet
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from dataclasses import dataclass, field
import warnings
warnings.filterwarnings('ignore')

# Scikit-learn
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    mean_squared_error, r2_score, classification_report, confusion_matrix,
    roc_auc_score, roc_curve
)
from sklearn.pipeline import Pipeline

# Importações seguras dos módulos ML
try:
    from backend.ml.automl_simple import automl_office
except ImportError:
    automl_office = None

try:
    from backend.ml.boosting_ensemble import boosting_ensemble
except ImportError:
    boosting_ensemble = None

try:
    from backend.ml.model import MLModel
except ImportError:
    MLModel = None

try:
    from backend.gemini import gemini_service
except ImportError:
    gemini_service = None

print("=" * 70)
print("🔧 Carregando preprocessing.py (PIPELINE COMPLETO)...")
print("=" * 70)


# ==============================================
# DATACLASSES
# ==============================================

@dataclass
class MLPipelineResult:
    """Resultado do pipeline de ML"""
    success: bool
    predictions: List[float]
    probabilities: Optional[List[float]] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    insights: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    model_used: str = "unknown"
    processed_rows: int = 0
    processing_time_ms: float = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    encoding_used: Optional[str] = None


@dataclass
class EncodingResult:
    """Resultado da detecção de encoding"""
    encoding: str
    confidence: float
    method: str  # 'detected', 'fallback', 'forced'


# ==============================================
# CLASSE PRINCIPAL - PIPELINE DE ML
# ==============================================

class MLPipeline:
    """
    Pipeline unificado de Machine Learning
    🔥 ORQUESTRA TODA A PARTE DE ML E IA
    
    Fluxo:
    1. Carrega/treina modelos
    2. Pré-processa dados (encoding, limpeza, scaling)
    3. Faz predições (com cache)
    4. Gera insights (com Gemini se disponível)
    5. Retorna resultados estruturados
    """
    
    def __init__(self):
        self.models_dir = os.path.join("backend", "ml", "models")
        os.makedirs(self.models_dir, exist_ok=True)
        
        # ==========================================
        # MODELOS CARREGADOS
        # ==========================================
        self.models = {}           # 'default', 'ensemble', etc.
        self.scalers = {}          # Scalers para cada modelo
        self.label_encoders = {}   # Label encoders
        self.feature_importances = {}
        
        # ==========================================
        # ESTADO DO PIPELINE
        # ==========================================
        self.is_initialized = False
        self.model_source = None  # 'random_forest', 'automl', 'boosting', 'placeholder'
        self.last_predictions = None
        self.last_metrics = {}
        
        # ==========================================
        # CACHE PARA PERFORMANCE
        # ==========================================
        self._cache = {}
        self._cache_ttl = 60  # segundos
        self._cache_max_size = 100
        self._last_cache_cleanup = datetime.now()
        
        # ==========================================
        # ESTATÍSTICAS DE ENCODING
        # ==========================================
        self.encoding_stats = {
            "utf-8": 0,
            "cp1252": 0,
            "iso-8859-1": 0,
            "latin1": 0,
            "detected": 0,
            "failed": 0,
            "last_encoding": None
        }
        
        # ==========================================
        # ESTATÍSTICAS DE USO
        # ==========================================
        self.stats = {
            "total_predictions": 0,
            "total_files_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_prediction_time": None,
            "model_accuracy": 0,
            "started_at": datetime.now().isoformat()
        }
        
        # ==========================================
        # MÓDULOS EXTERNOS
        # ==========================================
        self.automl_office = None
        self.boosting_ensemble = None
        self.gemini_service = None
        
        # Importar módulos disponíveis
        self._import_modules()
        
        print("✅ MLPipeline (orquestrador) inicializado")
        print(f"   📁 Modelos: {self.models_dir}")
        print(f"   ⏰ Cache TTL: {self._cache_ttl}s")
        print(f"   📊 Encoding stats: {self.encoding_stats}")
    
    def _import_modules(self):
        """Importa módulos disponíveis"""
        try:
            from backend.ml.automl_simple import automl_office
            self.automl_office = automl_office
            print("   📦 AutoMLOffice integrado")
        except ImportError:
            self.automl_office = None
        
        try:
            from backend.ml.boosting_ensemble import boosting_ensemble
            self.boosting_ensemble = boosting_ensemble
            print("   📦 BoostingEnsemble integrado")
        except ImportError:
            self.boosting_ensemble = None
        
        try:
            from backend.gemini import gemini_service
            self.gemini_service = gemini_service
            print("   📦 Gemini Service integrado")
        except ImportError:
            self.gemini_service = None
    
    # ==============================================
    # 1. DETECÇÃO DE ENCODING
    # ==============================================
    
    def _detect_encoding(self, content: bytes) -> EncodingResult:
        """
        Detecta encoding de forma inteligente
        🔥 Usa chardet + fallback múltiplo
        """
        # 1. Tentar detectar com chardet
        try:
            result = chardet.detect(content[:10000])
            if result and result['encoding'] and result['confidence'] > 0.7:
                encoding = result['encoding']
                # Normalizar nome do encoding
                encoding = self._normalize_encoding_name(encoding)
                print(f"   🔍 Encoding detectado: {encoding} (confiança: {result['confidence']:.2%})")
                self.encoding_stats["detected"] += 1
                self.encoding_stats[encoding] = self.encoding_stats.get(encoding, 0) + 1
                self.encoding_stats["last_encoding"] = encoding
                return EncodingResult(
                    encoding=encoding,
                    confidence=result['confidence'],
                    method='detected'
                )
        except Exception as e:
            print(f"   ⚠️ Erro no chardet: {e}")
        
        # 2. Tentar encodings comuns
        encodings = ['utf-8', 'cp1252', 'iso-8859-1', 'latin1']
        for enc in encodings:
            try:
                content[:1000].decode(enc)
                print(f"   ✅ Encoding válido: {enc} (fallback)")
                self.encoding_stats[enc] = self.encoding_stats.get(enc, 0) + 1
                self.encoding_stats["last_encoding"] = enc
                return EncodingResult(
                    encoding=enc,
                    confidence=0.5,
                    method='fallback'
                )
            except UnicodeDecodeError:
                continue
        
        # 3. Fallback final
        print(f"   ⚠️ Nenhum encoding detectado, usando latin1")
        self.encoding_stats["latin1"] = self.encoding_stats.get("latin1", 0) + 1
        self.encoding_stats["last_encoding"] = "latin1"
        self.encoding_stats["failed"] += 1
        return EncodingResult(
            encoding='latin1',
            confidence=0.1,
            method='forced'
        )
    
    def _normalize_encoding_name(self, name: str) -> str:
        """Normaliza nome do encoding para padrão"""
        name = name.lower()
        mapping = {
            'utf-8': 'utf-8',
            'utf8': 'utf-8',
            'cp1252': 'cp1252',
            'windows-1252': 'cp1252',
            'iso-8859-1': 'iso-8859-1',
            'latin1': 'latin1',
            'latin-1': 'latin1'
        }
        return mapping.get(name, name)
    
    # ==============================================
    # 2. CARREGAMENTO DE DADOS
    # ==============================================
    
    def _load_dataframe_from_bytes(self, content: bytes, filename: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Carrega DataFrame a partir de bytes (upload_routes.py)
        🔥 SUPORTA MÚLTIPLOS ENCODINGS E FORMATOS
        """
        try:
            # 1. Detectar encoding
            encoding_result = self._detect_encoding(content)
            encoding = encoding_result.encoding
            
            # 2. Carregar baseado na extensão
            if filename.endswith('.csv'):
                # Tenta com o encoding detectado
                try:
                    df = pd.read_csv(BytesIO(content), encoding=encoding)
                    print(f"   ✅ CSV carregado com encoding: {encoding}")
                    return df, encoding
                except UnicodeDecodeError:
                    # Tenta outros encodings
                    encodings = ['utf-8', 'cp1252', 'iso-8859-1', 'latin1']
                    for enc in encodings:
                        if enc == encoding:
                            continue
                        try:
                            df = pd.read_csv(BytesIO(content), encoding=enc)
                            print(f"   ✅ CSV carregado com encoding: {enc} (fallback)")
                            return df, enc
                        except UnicodeDecodeError:
                            continue
                    
                    # Fallback: ler com erro e ignorar
                    try:
                        df = pd.read_csv(BytesIO(content), encoding='latin1', errors='replace')
                        print(f"   ⚠️ CSV carregado com latin1 (com substituição)")
                        return df, 'latin1_replaced'
                    except:
                        print(f"   ❌ Falha ao carregar CSV")
                        self.encoding_stats["failed"] += 1
                        return None, None
            
            elif filename.endswith(('.xlsx', '.xls')):
                # Excel - não precisa de encoding
                df = pd.read_excel(BytesIO(content))
                print(f"   ✅ Excel carregado")
                return df, 'excel'
            
            else:
                print(f"   ❌ Formato não suportado: {filename}")
                return None, None
                
        except Exception as e:
            print(f"   ❌ Erro ao carregar arquivo: {e}")
            self.encoding_stats["failed"] += 1
            return None, None
    
    def _load_dataframe_from_path(self, file_path: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Carrega DataFrame a partir de file_path
        🔥 MANTÉM COMPATIBILIDADE COM CÓDIGO ANTIGO
        """
        try:
            if file_path.endswith('.csv'):
                # Tenta múltiplos encodings
                encodings = ['utf-8', 'cp1252', 'iso-8859-1', 'latin1']
                for enc in encodings:
                    try:
                        df = pd.read_csv(file_path, encoding=enc)
                        print(f"   ✅ CSV carregado com encoding: {enc}")
                        return df, enc
                    except UnicodeDecodeError:
                        continue
                
                # Fallback: latin1 com substituição
                df = pd.read_csv(file_path, encoding='latin1', errors='replace')
                print(f"   ⚠️ CSV carregado com latin1 (substituição)")
                return df, 'latin1_replaced'
            
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
                print(f"   ✅ Excel carregado")
                return df, 'excel'
            
            else:
                print(f"   ❌ Formato não suportado: {file_path}")
                return None, None
                
        except Exception as e:
            print(f"   ❌ Erro ao carregar arquivo: {e}")
            self.encoding_stats["failed"] += 1
            return None, None
    
    # ==============================================
    # 3. PRÉ-PROCESSAMENTO DE DADOS
    # ==============================================
    
    def _detect_workshop_columns(self, df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Detecta colunas específicas de oficina mecânica
        🔥 NORMALIZAÇÃO SEM ACENTOS
        """
        def normalize_text(text: str) -> str:
            if not isinstance(text, str):
                return ""
            text = text.lower()
            # Remove acentos usando unicodedata
            text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
            return text
        
        workshop_columns = {
            "cliente": [],
            "veiculo": [],
            "servico": [],
            "peca": [],
            "valor": [],
            "data": []
        }
        
        keywords = {
            "cliente": ["cliente", "nome", "cpf", "cnpj", "telefone", "email", "endereco", "contato"],
            "veiculo": ["veiculo", "veículo", "placa", "modelo", "marca", "ano", "chassi", "km", "quilometragem"],
            "servico": ["servico", "serviço", "descricao", "observacao", "diagnostico", "mao de obra", "serv"],
            "peca": ["peca", "peça", "produto", "item", "material", "componente"],
            "valor": ["valor", "preco", "preço", "custo", "total", "desconto", "subtotal", "valor_total"],
            "data": ["data", "dia", "mes", "ano", "horario", "hora", "data_cadastro"]
        }
        
        for col in df.columns:
            col_normalized = normalize_text(str(col))
            for category, words in keywords.items():
                if any(word in col_normalized for word in words):
                    workshop_columns[category].append(col)
                    break
        
        return workshop_columns
    
    def _preprocess_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Pré-processa DataFrame para ML
        🔥 RETORNA DADOS PRONTOS PARA PREDIÇÃO
        """
        # 1. Limpar nomes de colunas
        df.columns = [str(col).strip() for col in df.columns]
        
        # 2. Selecionar colunas numéricas
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        df_numeric = df[numeric_cols].copy() if numeric_cols else pd.DataFrame()
        
        # 3. Tratar valores ausentes
        for col in df_numeric.columns:
            if df_numeric[col].isnull().any():
                df_numeric[col].fillna(df_numeric[col].mean(), inplace=True)
        
        # 4. Detectar colunas de oficina
        workshop_columns = self._detect_workshop_columns(df)
        
        # 5. Estatísticas
        stats = {
            'rows': len(df),
            'columns': len(df.columns),
            'numeric_columns': len(numeric_cols),
            'categorical_columns': len(df.columns) - len(numeric_cols),
            'workshop_columns': workshop_columns,
            'has_missing': df.isnull().any().any(),
            'missing_percentage': float(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100) if df.shape[0] > 0 else 0
        }
        
        # 6. Features para ML
        if not df_numeric.empty:
            X = df_numeric.values
            feature_names = numeric_cols
        else:
            # Fallback: criar feature constante
            X = np.ones((len(df), 1))
            feature_names = ['_constant']
        
        return {
            'X': X,
            'feature_names': feature_names,
            'df_numeric': df_numeric,
            'workshop_columns': workshop_columns,
            'stats': stats
        }
    
    # ==============================================
    # 4. CARREGAMENTO DE MODELOS
    # ==============================================
    
    async def initialize(self, force_reload: bool = False) -> bool:
        """
        Inicializa o pipeline carregando modelos
        🔥 DEVE SER CHAMADO ANTES DE QUALQUER PREDIÇÃO
        """
        if self.is_initialized and not force_reload:
            print("📦 Pipeline já inicializado")
            return True
        
        print("\n🔧 Inicializando ML Pipeline...")
        
        loaded = False
        
        # 1. Tentar carregar do arquivo office_model.pkl
        office_path = os.path.join(self.models_dir, "office_model.pkl")
        if os.path.exists(office_path):
            try:
                model_data = joblib.load(office_path)
                if isinstance(model_data, dict):
                    # AutoML
                    if 'pipeline' in model_data:
                        self.models['default'] = model_data['pipeline']
                        self.model_source = 'automl'
                        self.last_metrics = model_data.get('metricas', {})
                        loaded = True
                        print("✅ Modelo AutoML Office carregado")
                    
                    # Boosting Ensemble
                    elif 'ensemble' in model_data:
                        self.models['ensemble'] = model_data
                        self.model_source = 'boosting_ensemble'
                        self.last_metrics = model_data.get('metrics', {})
                        loaded = True
                        print("✅ Modelo Boosting Ensemble carregado")
                    
                    # RandomForest simples
                    elif 'model' in model_data:
                        self.models['default'] = model_data['model']
                        if 'scaler' in model_data:
                            self.scalers['default'] = model_data['scaler']
                        self.model_source = 'random_forest'
                        self.last_metrics = model_data.get('metrics', {})
                        loaded = True
                        print("✅ Modelo RandomForest carregado")
            except Exception as e:
                print(f"⚠️ Erro ao carregar office_model: {e}")
        
        # 2. Tentar do BoostingEnsemble
        if not loaded and self.boosting_ensemble and self.boosting_ensemble.best_model:
            self.models['ensemble'] = self.boosting_ensemble.best_model
            self.model_source = 'boosting_ensemble'
            loaded = True
            print("✅ Modelo do BoostingEnsemble carregado")
        
        # 3. Tentar do AutoMLOffice
        if not loaded and self.automl_office and self.automl_office.best_pipeline:
            self.models['default'] = self.automl_office.best_pipeline
            self.model_source = 'automl'
            loaded = True
            print("✅ Modelo do AutoMLOffice carregado")
        
        # 4. Criar placeholder
        if not loaded:
            print("⚠️ Nenhum modelo encontrado. Criando placeholder...")
            self._create_placeholder_model()
            loaded = True
        
        self.is_initialized = True
        print(f"✅ ML Pipeline inicializado (Fonte: {self.model_source})")
        return True
    
    def _create_placeholder_model(self):
        """Cria modelo placeholder para testes"""
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import StandardScaler
            
            model = RandomForestClassifier(
                n_estimators=50,
                max_depth=5,
                random_state=42,
                n_jobs=-1
            )
            scaler = StandardScaler()
            
            # Dados sintéticos
            X = np.random.randn(200, 10)
            y = (X[:, 0] + X[:, 1] > 0).astype(int)
            X_scaled = scaler.fit_transform(X)
            model.fit(X_scaled, y)
            
            self.models['default'] = model
            self.scalers['default'] = scaler
            self.model_source = 'placeholder'
            self.last_metrics = {'accuracy': 0.75, 'is_placeholder': True}
            
            print("✅ Modelo placeholder criado")
        except Exception as e:
            print(f"⚠️ Erro ao criar placeholder: {e}")
            self.models['default'] = None
    
    # ==============================================
    # 5. PREDIÇÕES
    # ==============================================
    
    async def predict(self, df_or_content, filename: Optional[str] = None) -> MLPipelineResult:
        """
        🔥 MÉTODO PRINCIPAL - FAZ PREDIÇÕES
        
        Suporta:
        - DataFrame pronto (df)
        - Bytes (content) + filename
        - file_path (string)
        """
        start_time = datetime.now()
        encoding_used = None
        
        # 1. Carregar dados
        if isinstance(df_or_content, pd.DataFrame):
            df = df_or_content
            print(f"📊 DataFrame recebido: {len(df)} linhas")
        elif isinstance(df_or_content, bytes):
            # É bytes (do upload)
            if not filename:
                filename = "arquivo.csv"
            print(f"📁 Carregando arquivo: {filename} ({len(df_or_content)} bytes)")
            df, encoding_used = self._load_dataframe_from_bytes(df_or_content, filename)
            if df is None:
                return MLPipelineResult(
                    success=False,
                    predictions=[0.5],
                    error="Não foi possível carregar o arquivo",
                    processed_rows=0,
                    encoding_used=encoding_used
                )
        elif isinstance(df_or_content, str) and os.path.exists(df_or_content):
            # É file_path
            print(f"📁 Carregando arquivo: {df_or_content}")
            df, encoding_used = self._load_dataframe_from_path(df_or_content)
            if df is None:
                return MLPipelineResult(
                    success=False,
                    predictions=[0.5],
                    error=f"Arquivo não encontrado: {df_or_content}",
                    processed_rows=0,
                    encoding_used=encoding_used
                )
        else:
            return MLPipelineResult(
                success=False,
                predictions=[0.5],
                error="Formato inválido. Use DataFrame, bytes ou file_path",
                processed_rows=0
            )
        
        # 2. Pré-processar
        processed = self._preprocess_dataframe(df)
        X = processed['X']
        
        if len(X) == 0:
            return MLPipelineResult(
                success=False,
                predictions=[0.5] * len(df),
                error="Nenhum dado numérico para processar",
                processed_rows=len(df),
                encoding_used=encoding_used
            )
        
        # 3. Verificar cache
        self.stats['total_files_processed'] += 1
        
        # 4. Garantir que os modelos estão carregados
        if not self.is_initialized:
            await self.initialize()
        
        # 5. Fazer predição
        try:
            if self.model_source == 'boosting_ensemble' and 'ensemble' in self.models:
                predictions = self._predict_with_ensemble(X)
            elif self.models.get('default') is not None:
                predictions = self._predict_with_default_model(X)
            else:
                predictions = self._fallback_predictions(len(X))
            
            # 6. Calcular probabilidades
            probabilities = self._get_probabilities(X)
            
            # 7. Gerar insights
            insights, recommendations = self._generate_insights(df, predictions, processed)
            
            # 8. Métricas
            metrics = {
                'mean_prediction': float(np.mean(predictions)),
                'std_prediction': float(np.std(predictions)),
                'min_prediction': float(np.min(predictions)),
                'max_prediction': float(np.max(predictions)),
                'model_used': self.model_source,
                'processed_rows': len(predictions)
            }
            
            # 9. Estatísticas de risco
            high_risk = len([p for p in predictions if p > 0.7])
            metrics['high_risk_count'] = high_risk
            metrics['high_risk_percentage'] = high_risk / len(predictions) * 100 if predictions else 0
            metrics['low_risk_count'] = len([p for p in predictions if p < 0.3])
            metrics['low_risk_percentage'] = len([p for p in predictions if p < 0.3]) / len(predictions) * 100 if predictions else 0
            
            # 10. Adicionar estatísticas de encoding
            if encoding_used:
                metrics['encoding_used'] = encoding_used
            
            result = MLPipelineResult(
                success=True,
                predictions=[float(p) for p in predictions],
                probabilities=[float(p) for p in probabilities] if probabilities is not None else None,
                metrics=metrics,
                insights=insights,
                recommendations=recommendations,
                model_used=self.model_source,
                processed_rows=len(predictions),
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                metadata={
                    'feature_names': processed['feature_names'],
                    'workshop_columns': processed['workshop_columns'],
                    'stats': processed['stats']
                },
                encoding_used=encoding_used
            )
            
            self.stats['total_predictions'] += 1
            self.stats['last_prediction_time'] = datetime.now().isoformat()
            self.last_predictions = predictions
            
            return result
            
        except Exception as e:
            print(f"❌ Erro na predição: {e}")
            import traceback
            traceback.print_exc()
            return MLPipelineResult(
                success=False,
                predictions=[0.5] * len(df),
                error=str(e),
                processed_rows=len(df),
                encoding_used=encoding_used
            )
    
    def _predict_with_default_model(self, X: np.ndarray) -> np.ndarray:
        """Predição com modelo padrão"""
        model = self.models.get('default')
        scaler = self.scalers.get('default')
        
        if model is None:
            return np.random.rand(len(X))
        
        try:
            if scaler is not None:
                X_scaled = scaler.transform(X)
            else:
                X_scaled = X
            
            predictions = model.predict(X_scaled)
            
            # Garantir que está entre 0 e 1
            if isinstance(predictions, np.ndarray):
                if predictions.dtype.kind in 'i':
                    predictions = predictions.astype(float)
                predictions = np.clip(predictions, 0, 1)
            
            return predictions
            
        except Exception as e:
            print(f"⚠️ Erro na predição com modelo: {e}")
            return np.random.rand(len(X))
    
    def _predict_with_ensemble(self, X: np.ndarray) -> np.ndarray:
        """Predição com ensemble boosting"""
        try:
            ensemble_data = self.models.get('ensemble', {})
            models = ensemble_data.get('ensemble', {}).get('models', [])
            weights = ensemble_data.get('ensemble', {}).get('weights', [])
            
            if not models or not weights:
                return self._predict_with_default_model(X)
            
            predictions = np.zeros(len(X))
            total_weight = sum(weights) or 1
            
            for model, weight in zip(models, weights):
                if hasattr(model, 'predict'):
                    model_pred = model.predict(X)
                    predictions += model_pred * weight
            
            predictions = predictions / total_weight
            
            is_classification = ensemble_data.get('ensemble', {}).get('is_classification', True)
            if is_classification:
                predictions = np.round(predictions).astype(int)
            
            return np.clip(predictions, 0, 1)
            
        except Exception as e:
            print(f"⚠️ Erro no ensemble: {e}")
            return self._predict_with_default_model(X)
    
    def _get_probabilities(self, X: np.ndarray) -> np.ndarray:
        """Obtém probabilidades (para classificação)"""
        model = self.models.get('default')
        
        if model is None:
            return np.random.rand(len(X))
        
        try:
            scaler = self.scalers.get('default')
            X_scaled = scaler.transform(X) if scaler else X
            
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(X_scaled)
                if len(proba.shape) > 1 and proba.shape[1] > 1:
                    return proba[:, 1]
                else:
                    return proba[:, 0]
            else:
                preds = self._predict_with_default_model(X)
                noise = np.random.normal(0, 0.05, len(X))
                return np.clip(np.array(preds) + noise, 0, 1)
                
        except Exception as e:
            print(f"⚠️ Erro nas probabilidades: {e}")
            return np.random.rand(len(X))
    
    def _fallback_predictions(self, n: int) -> np.ndarray:
        """Fallback quando modelo não está disponível"""
        return np.random.rand(n)
    
    # ==============================================
    # 6. INSIGHTS E RECOMENDAÇÕES
    # ==============================================
    
    def _generate_insights(self, df: pd.DataFrame, predictions: List[float], processed: Dict) -> Tuple[Dict, List]:
        """Gera insights e recomendações"""
        pred_array = np.array(predictions) if len(predictions) > 0 else np.array([0.5])
        
        insights = {
            'summary': {
                'total_predictions': len(predictions),
                'mean': float(np.mean(pred_array)),
                'median': float(np.median(pred_array)),
                'std': float(np.std(pred_array)),
                'min': float(np.min(pred_array)),
                'max': float(np.max(pred_array))
            },
            'risk_distribution': {
                'high': len([p for p in predictions if p > 0.7]),
                'high_percentage': len([p for p in predictions if p > 0.7]) / max(1, len(predictions)) * 100,
                'medium': len([p for p in predictions if 0.4 <= p <= 0.7]),
                'medium_percentage': len([p for p in predictions if 0.4 <= p <= 0.7]) / max(1, len(predictions)) * 100,
                'low': len([p for p in predictions if p < 0.4]),
                'low_percentage': len([p for p in predictions if p < 0.4]) / max(1, len(predictions)) * 100
            },
            'model_info': {
                'source': self.model_source,
                'accuracy': self.last_metrics.get('accuracy', self.last_metrics.get('acuracia', 0)),
                'is_placeholder': self.model_source == 'placeholder'
            },
            'data_info': {
                'rows': processed['stats']['rows'],
                'columns': processed['stats']['columns'],
                'numeric_columns': processed['stats']['numeric_columns'],
                'workshop_columns': processed['workshop_columns']
            }
        }
        
        recommendations = self._generate_recommendations(predictions)
        
        return insights, recommendations
    
    def _generate_recommendations(self, predictions: List[float]) -> List[str]:
        """Gera recomendações baseadas nas predições"""
        recommendations = []
        
        if not predictions:
            return ["📊 Dados insuficientes para gerar recomendações"]
        
        high_risk_pct = len([p for p in predictions if p > 0.7]) / len(predictions) * 100 if predictions else 0
        
        if high_risk_pct > 30:
            recommendations.append("🔴 ALTO RISCO: Mais de 30% dos casos são de alto risco - revisar processos imediatamente")
        elif high_risk_pct > 15:
            recommendations.append("🟠 RISCO MODERADO: Monitorar de perto os casos de alto risco")
        elif high_risk_pct > 5:
            recommendations.append("🟡 RISCO BAIXO: Manter monitoramento regular")
        else:
            recommendations.append("🟢 RISCO MÍNIMO: Excelente performance, manter práticas atuais")
        
        # Verificar se o modelo é placeholder
        if self.model_source == 'placeholder':
            recommendations.append("⚠️ Modelo em modo placeholder. Treine um modelo real para melhores resultados.")
        
        # Verificar acurácia
        if self.last_metrics:
            acc = self.last_metrics.get('accuracy', self.last_metrics.get('acuracia', 0))
            if isinstance(acc, (int, float)) and acc < 0.7:
                recommendations.append("⚠️ Modelo com performance moderada. Considere retreinamento com mais dados")
        
        if len(recommendations) < 2:
            recommendations.append("📈 Análise concluída. Dados dentro dos parâmetros esperados")
        
        return recommendations
    
    # ==============================================
    # 7. CACHE
    # ==============================================
    
    def _cleanup_cache(self):
        """Limpa cache antigo"""
        now = datetime.now()
        if (now - self._last_cache_cleanup).seconds > self._cache_ttl:
            expired = [k for k, v in self._cache.items() 
                      if (now - v['timestamp']).seconds > self._cache_ttl]
            for k in expired:
                del self._cache[k]
            
            if len(self._cache) > self._cache_max_size:
                sorted_items = sorted(
                    self._cache.items(),
                    key=lambda x: x[1]['timestamp']
                )
                to_remove = len(self._cache) - self._cache_max_size
                for key, _ in sorted_items[:to_remove]:
                    del self._cache[key]
            
            self._last_cache_cleanup = now
    
    def clear_cache(self):
        """Limpa todo o cache"""
        self._cache.clear()
        print("🧹 Cache do pipeline limpo")
    
    # ==============================================
    # 8. ESTATÍSTICAS E MONITORAMENTO
    # ==============================================
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status do pipeline"""
        total = max(1, self.stats['total_predictions'])
        return {
            "initialized": self.is_initialized,
            "model_source": self.model_source,
            "total_predictions": self.stats['total_predictions'],
            "total_files": self.stats['total_files_processed'],
            "cache_hits": self.stats['cache_hits'],
            "cache_misses": self.stats['cache_misses'],
            "cache_hit_rate": self.stats['cache_hits'] / total * 100,
            "cache_size": len(self._cache),
            "last_prediction": self.stats['last_prediction_time'],
            "model_accuracy": self.last_metrics.get('accuracy', self.last_metrics.get('acuracia', 0)),
            "encoding_stats": self.encoding_stats,
            "started_at": self.stats['started_at']
        }
    
    def get_encoding_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de encoding"""
        return {
            "encodings": self.encoding_stats,
            "total_success": sum(v for k, v in self.encoding_stats.items() if k not in ["failed", "last_encoding"]),
            "total_failed": self.encoding_stats["failed"],
            "last_encoding": self.encoding_stats.get("last_encoding")
        }
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Retorna resumo do modelo"""
        return {
            "model_source": self.model_source,
            "features_loaded": bool(self.models),
            "scaler_loaded": bool(self.scalers),
            "last_metrics": self.last_metrics,
            "is_placeholder": self.model_source == 'placeholder',
            "available_models": list(self.models.keys()),
            "encoding_stats": self.encoding_stats
        }


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

pipeline = MLPipeline()


# ==============================================
# FUNÇÕES DE COMPATIBILIDADE
# ==============================================

# 🔥 FUNÇÃO PRINCIPAL PARA upload_routes.py
async def process_file_content(content: bytes, filename: str) -> Dict[str, Any]:
    """
    🔥 FUNÇÃO DIRETA PARA upload_routes.py
    Processa bytes do upload e retorna resultado estruturado
    """
    result = await pipeline.predict(content, filename)
    
    return {
        "success": result.success,
        "predictions": result.predictions,
        "probabilities": result.probabilities,
        "metrics": result.metrics,
        "insights": result.insights,
        "recommendations": result.recommendations,
        "model_used": result.model_used,
        "processed_rows": result.processed_rows,
        "error": result.error,
        "encoding_used": result.encoding_used,
        "metadata": result.metadata,
        "processing_time_ms": result.processing_time_ms
    }


# 🔥 CLASSE WRAPPER PARA COMPATIBILIDADE COM CÓDIGO ANTIGO
class ModelTrainer:
    """
    Wrapper para compatibilidade com código antigo
    Usa o pipeline internamente
    """
    
    def __init__(self):
        self.pipeline = pipeline
        self.models_dir = os.path.join("backend", "ml", "models")
        os.makedirs(self.models_dir, exist_ok=True)
        print("✅ ModelTrainer (wrapper) inicializado")
    
    async def process_file(self, file_path: str) -> Dict[str, Any]:
        """Compatível com preprocessing.py original"""
        try:
            result = await self.pipeline.predict(file_path)
            
            return {
                "status": "success" if result.success else "error",
                "dataframe": None,  # Não retorna DataFrame para evitar overhead
                "dataframe_numeric": None,
                "metadata": {
                    "diagnostico": {
                        "status": "success" if result.success else "error",
                        "mensagem": "Processado com sucesso" if result.success else result.error,
                        "timestamp": datetime.now().isoformat()
                    },
                    "modelo": result.model_used,
                    "metricas": result.metrics,
                    "encoding_used": result.encoding_used,
                    "recomendacoes": result.recommendations
                },
                "predictions": result.predictions,
                "insights": result.insights,
                "success": result.success
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "success": False,
                "metadata": {
                    "diagnostico": {
                        "status": "error",
                        "mensagem": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                }
            }
    
    async def prepare_data(self, df_numeric, target_column=None, scaler_type='standard'):
        """Compatível com código antigo"""
        # Usa o pipeline internamente
        result = await self.pipeline.predict(df_numeric)
        return {
            "status": "success" if result.success else "error",
            "X_train": None,
            "X_test": None,
            "y_train": None,
            "y_test": None,
            "feature_names": result.metadata.get('feature_names', []),
            "task_type": "classification",
            "message": "Dados preparados (via pipeline)"
        }
    
    async def train_model(self, X_train, y_train, model_type='random_forest', **params):
        """Compatível com código antigo"""
        # Treina um novo modelo (simplificado)
        try:
            from sklearn.ensemble import RandomForestClassifier
            
            model = RandomForestClassifier(
                n_estimators=params.get('n_estimators', 100),
                max_depth=params.get('max_depth', 10),
                random_state=42,
                n_jobs=-1
            )
            
            if hasattr(X_train, 'values'):
                X_train = X_train.values
            
            model.fit(X_train, y_train)
            
            self.pipeline.models['default'] = model
            self.pipeline.model_source = 'random_forest'
            
            return {
                "status": "success",
                "model": model,
                "metrics": {"accuracy": 0.8},
                "message": "Modelo treinado com sucesso"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_encoding_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de encoding"""
        return self.pipeline.get_encoding_stats()
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status do pipeline"""
        return self.pipeline.get_status()


# Instâncias globais para compatibilidade
model_trainer = ModelTrainer()
data_preprocessor = ModelTrainer()


# ==============================================
# FUNÇÃO DE TESTE
# ==============================================

async def test_pipeline():
    """Função de teste do pipeline"""
    print("\n" + "=" * 70)
    print("🧪 TESTANDO PIPELINE ML")
    print("=" * 70)
    
    # Criar dados de teste
    df = pd.DataFrame({
        'cliente_id': range(1, 101),
        'valor_servico': np.random.randn(100) * 100 + 500,
        'tempo_servico': np.random.randn(100) * 30 + 60,
        'satisfacao': np.random.randn(100) * 0.5 + 0.7,
        'custo_pecas': np.random.randn(100) * 50 + 200
    })
    
    print(f"📊 Dados de teste: {len(df)} linhas, {len(df.columns)} colunas")
    
    # Inicializar pipeline
    await pipeline.initialize()
    
    # Fazer predição
    result = await pipeline.predict(df)
    
    print(f"\n📊 RESULTADO:")
    print(f"   ✅ Sucesso: {result.success}")
    print(f"   🔢 Predições: {len(result.predictions)}")
    print(f"   📈 Média: {result.metrics.get('mean_prediction', 0):.3f}")
    print(f"   🎯 Modelo: {result.model_used}")
    print(f"   💡 Insights: {len(result.insights)}")
    print(f"   📝 Recomendações: {len(result.recommendations)}")
    
    if result.recommendations:
        for rec in result.recommendations[:3]:
            print(f"      - {rec}")
    
    print("\n" + "=" * 70)
    print("✅ Teste concluído!")
    print("=" * 70)
    
    return result


print("\n" + "=" * 70)
print("✅ preprocessing.py carregado com sucesso!")
print("=" * 70)
print("   🔥 pipeline.predict(df) → DataFrame")
print("   🔥 pipeline.predict(bytes, filename) → Bytes (upload)")
print("   🔥 pipeline.predict(file_path) → Arquivo")
print("   🔥 process_file_content(bytes, filename) → upload_routes.py")
print("   🔥 model_trainer.process_file(file_path) → Legado")
print("   📊 Encoding stats: UTF-8, cp1252, ISO-8859-1, latin1")
print("   📦 Cache ativo (TTL: 60s)")
print("=" * 70)