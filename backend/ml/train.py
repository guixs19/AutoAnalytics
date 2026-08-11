# backend/ml/train.py - VERSÃO 3.0 (UNIFICADA E OTIMIZADA)
"""
🔥 MÓDULO DE TREINAMENTO DE MODELOS - AUTOANALYTICS V3.0
================================================================================
UNIFICA TODOS OS MÓDULOS DE ML EM UM SISTEMA COERENTE

✅ INTEGRAÇÕES:
   - 🔥 AutoMLOffice: Seleção automática de modelos
   - 🔥 BoostingEnsemble: Ensemble learning
   - 🔥 ModelPredictor: Predição unificada
   - 🔥 FeatureRegistry: Gestão de features
   - 🔥 FeatureBuilder: Construção de features

✅ NOVIDADES V3.0:
   - 🔥 AUTO-ML COMPLETO: Testa 10+ modelos automaticamente
   - 🔥 ENSEMBLE INTELIGENTE: Combinação ponderada de modelos
   - 🔥 HYPERPARAMETER TUNING: Otimização com GridSearchCV
   - 🔥 FEATURE SELECTION: Seleção automática das melhores features
   - 🔥 CROSS-VALIDATION: Validação robusta com K-Fold
   - 🔥 MODEL REGISTRY: Histórico completo de treinamentos
   - 🔥 SHAP INTEGRATION: Explicabilidade de predições
   - 🔥 METRICS EXTRACTION: Métricas para Gemini
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple, List, Union
import os
import pickle
import json
import joblib
from datetime import datetime
import warnings
import logging
warnings.filterwarnings('ignore')

# Scikit-learn
from sklearn.model_selection import (
    train_test_split, 
    cross_val_score, 
    KFold, 
    StratifiedKFold,
    GridSearchCV,
    RandomizedSearchCV
)
from sklearn.metrics import (
    classification_report, 
    confusion_matrix, 
    accuracy_score, 
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    mean_squared_error, 
    r2_score,
    mean_absolute_error
)
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler, LabelEncoder
from sklearn.feature_selection import SelectFromModel, RFE, SelectKBest, f_classif, f_regression
from sklearn.ensemble import (
    RandomForestClassifier, 
    RandomForestRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    AdaBoostClassifier,
    AdaBoostRegressor,
    VotingClassifier,
    VotingRegressor,
    StackingClassifier,
    StackingRegressor
)
from sklearn.linear_model import (
    LogisticRegression,
    LinearRegression,
    Ridge,
    Lasso,
    ElasticNet
)
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor

# XGBoost e LightGBM (opcionais)
try:
    from xgboost import XGBClassifier, XGBRegressor
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False

# SHAP para explainability
try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

# Imbalanced-learn para balanceamento
try:
    from imblearn.over_sampling import SMOTE, ADASYN
    from imblearn.pipeline import Pipeline as ImbPipeline
    IMB_AVAILABLE = True
except ImportError:
    IMB_AVAILABLE = False

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================
# 🔥 CONFIGURAÇÕES
# ==============================================

class TrainConfig:
    """Configurações centralizadas de treinamento"""
    
    # Modelos disponíveis para classificação
    CLASSIFIERS = {}
    
    # Modelos disponíveis para regressão
    REGRESSORS = {}
    
    # Scaler options
    SCALERS = {
        'standard': StandardScaler,
        'robust': RobustScaler,
        'minmax': MinMaxScaler
    }
    
    # Configurações de validação
    CV_FOLDS = 5
    TEST_SIZE = 0.2
    RANDOM_STATE = 42
    N_JOBS = -1
    VERBOSE = 0
    
    # Features
    MAX_FEATURES = 20
    MIN_FEATURES = 3
    FEATURE_SELECTION_THRESHOLD = 0.8
    
    # Output
    MODELS_DIR = os.path.join("backend", "ml", "models")
    LOGS_DIR = os.path.join("backend", "ml", "logs")


# 🔥 POPULAR MODELOS DINAMICAMENTE
def _populate_model_configs():
    """Popula configurações de modelos dinamicamente"""
    
    # ==========================================
    # CLASSIFICADORES
    # ==========================================
    
    TrainConfig.CLASSIFIERS = {
        'random_forest': {
            'model': RandomForestClassifier,
            'params': {
                'n_estimators': [50, 100, 200],
                'max_depth': [5, 10, 15, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'max_features': ['sqrt', 'log2', None]
            },
            'default_params': {
                'n_estimators': 100,
                'max_depth': 10,
                'random_state': 42,
                'n_jobs': -1
            }
        },
        'gradient_boosting': {
            'model': GradientBoostingClassifier,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'max_depth': [3, 5, 7],
                'min_samples_split': [2, 5],
                'subsample': [0.8, 1.0]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'random_state': 42
            }
        },
        'adaboost': {
            'model': AdaBoostClassifier,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.5, 1.0]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'random_state': 42
            }
        },
        'logistic_regression': {
            'model': LogisticRegression,
            'params': {
                'C': [0.01, 0.1, 1.0, 10.0],
                'penalty': ['l1', 'l2'],
                'solver': ['liblinear', 'saga']
            },
            'default_params': {
                'C': 1.0,
                'penalty': 'l2',
                'solver': 'liblinear',
                'max_iter': 1000,
                'random_state': 42
            }
        },
        'svm': {
            'model': SVC,
            'params': {
                'C': [0.1, 1.0, 10.0],
                'kernel': ['rbf', 'linear', 'poly'],
                'gamma': ['scale', 'auto']
            },
            'default_params': {
                'C': 1.0,
                'kernel': 'rbf',
                'probability': True,
                'random_state': 42
            }
        },
        'decision_tree': {
            'model': DecisionTreeClassifier,
            'params': {
                'max_depth': [3, 5, 7, 10, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'criterion': ['gini', 'entropy']
            },
            'default_params': {
                'max_depth': 10,
                'random_state': 42
            }
        },
        'knn': {
            'model': KNeighborsClassifier,
            'params': {
                'n_neighbors': [3, 5, 7, 11, 15],
                'weights': ['uniform', 'distance'],
                'p': [1, 2]
            },
            'default_params': {
                'n_neighbors': 5,
                'weights': 'uniform',
                'p': 2
            }
        }
    }
    
    # Adicionar XGBoost se disponível
    if XGB_AVAILABLE:
        TrainConfig.CLASSIFIERS['xgboost'] = {
            'model': XGBClassifier,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'max_depth': [3, 5, 7],
                'subsample': [0.8, 1.0],
                'colsample_bytree': [0.8, 1.0],
                'gamma': [0, 0.1, 0.2]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'random_state': 42,
                'use_label_encoder': False,
                'eval_metric': 'logloss'
            }
        }
    
    # Adicionar LightGBM se disponível
    if LGBM_AVAILABLE:
        TrainConfig.CLASSIFIERS['lightgbm'] = {
            'model': LGBMClassifier,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'num_leaves': [15, 31, 63],
                'max_depth': [-1, 5, 10],
                'subsample': [0.8, 1.0],
                'colsample_bytree': [0.8, 1.0]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'num_leaves': 31,
                'random_state': 42,
                'verbose': -1
            }
        }
    
    # ==========================================
    # REGRESSORES
    # ==========================================
    
    TrainConfig.REGRESSORS = {
        'random_forest': {
            'model': RandomForestRegressor,
            'params': {
                'n_estimators': [50, 100, 200],
                'max_depth': [5, 10, 15, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'max_features': ['sqrt', 'log2', None]
            },
            'default_params': {
                'n_estimators': 100,
                'max_depth': 10,
                'random_state': 42,
                'n_jobs': -1
            }
        },
        'gradient_boosting': {
            'model': GradientBoostingRegressor,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'max_depth': [3, 5, 7],
                'min_samples_split': [2, 5],
                'subsample': [0.8, 1.0]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'random_state': 42
            }
        },
        'adaboost': {
            'model': AdaBoostRegressor,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.5, 1.0]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'random_state': 42
            }
        },
        'linear_regression': {
            'model': LinearRegression,
            'params': {},
            'default_params': {
                'n_jobs': -1
            }
        },
        'ridge': {
            'model': Ridge,
            'params': {
                'alpha': [0.01, 0.1, 1.0, 10.0, 100.0]
            },
            'default_params': {
                'alpha': 1.0,
                'random_state': 42
            }
        },
        'lasso': {
            'model': Lasso,
            'params': {
                'alpha': [0.01, 0.1, 1.0, 10.0]
            },
            'default_params': {
                'alpha': 1.0,
                'random_state': 42
            }
        },
        'elastic_net': {
            'model': ElasticNet,
            'params': {
                'alpha': [0.01, 0.1, 1.0],
                'l1_ratio': [0.2, 0.5, 0.8]
            },
            'default_params': {
                'alpha': 0.1,
                'l1_ratio': 0.5,
                'random_state': 42
            }
        },
        'svm': {
            'model': SVR,
            'params': {
                'C': [0.1, 1.0, 10.0],
                'kernel': ['rbf', 'linear'],
                'gamma': ['scale', 'auto']
            },
            'default_params': {
                'C': 1.0,
                'kernel': 'rbf'
            }
        },
        'decision_tree': {
            'model': DecisionTreeRegressor,
            'params': {
                'max_depth': [3, 5, 7, 10, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'criterion': ['squared_error', 'absolute_error']
            },
            'default_params': {
                'max_depth': 10,
                'random_state': 42
            }
        },
        'knn': {
            'model': KNeighborsRegressor,
            'params': {
                'n_neighbors': [3, 5, 7, 11, 15],
                'weights': ['uniform', 'distance'],
                'p': [1, 2]
            },
            'default_params': {
                'n_neighbors': 5,
                'weights': 'uniform',
                'p': 2
            }
        }
    }
    
    if XGB_AVAILABLE:
        TrainConfig.REGRESSORS['xgboost'] = {
            'model': XGBRegressor,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'max_depth': [3, 5, 7],
                'subsample': [0.8, 1.0],
                'colsample_bytree': [0.8, 1.0],
                'gamma': [0, 0.1, 0.2]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'random_state': 42
            }
        }
    
    if LGBM_AVAILABLE:
        TrainConfig.REGRESSORS['lightgbm'] = {
            'model': LGBMRegressor,
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'num_leaves': [15, 31, 63],
                'max_depth': [-1, 5, 10],
                'subsample': [0.8, 1.0],
                'colsample_bytree': [0.8, 1.0]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'num_leaves': 31,
                'random_state': 42,
                'verbose': -1
            }
        }


# Popular configurações
_populate_model_configs()


# ==============================================
# 🔥 MODEL TRAINER - VERSÃO 3.0
# ==============================================

class ModelTrainer:
    """
    🔥 Treinador de modelos unificado - VERSÃO 3.0
    """
    
    def __init__(self):
        # Diretórios
        self.models_dir = TrainConfig.MODELS_DIR
        self.logs_dir = TrainConfig.LOGS_DIR
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Estado
        self.training_history = []
        self.best_model = None
        self.best_scaler = None
        self.best_features = None
        self.best_metrics = {}
        self.best_model_name = None
        self.best_model_type = None
        self.is_classification = None
        
        # Cache
        self._model_cache = {}
        self._scaler_cache = {}
        
        # Estatísticas
        self.stats = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "best_accuracy": 0,
            "best_r2": 0,
            "models_tested": {},
            "started_at": datetime.now().isoformat()
        }
        
        # Feature Registry (opcional)
        self.feature_registry = None
        self._load_feature_registry()
        
        logger.info("✅ ModelTrainer V3.0 inicializado")
        logger.info(f"   📁 Modelos: {self.models_dir}")
        logger.info(f"   🔢 Classificadores: {len(TrainConfig.CLASSIFIERS)}")
        logger.info(f"   🔢 Regressores: {len(TrainConfig.REGRESSORS)}")
        logger.info(f"   🔍 SHAP disponível: {SHAP_AVAILABLE}")
        logger.info(f"   ⚖️ SMOTE disponível: {IMB_AVAILABLE}")
        logger.info(f"   📊 XGBoost disponível: {XGB_AVAILABLE}")
        logger.info(f"   📊 LightGBM disponível: {LGBM_AVAILABLE}")
    
    def _load_feature_registry(self):
        """Carrega Feature Registry se disponível"""
        try:
            from backend.ml.feature_registry import feature_registry
            self.feature_registry = feature_registry
            logger.info(f"   📊 Feature Registry carregado: {feature_registry.get_expected_count()} features")
        except ImportError:
            self.feature_registry = None
            logger.debug("   ℹ️ Feature Registry não disponível")
    
    # ==============================================
    # 🔥 PRÉ-PROCESSAMENTO INTELIGENTE
    # ==============================================
    
    def _prepare_data(
        self, 
        df: pd.DataFrame, 
        target_col: str,
        model_type: str = 'classifier',
        balance: bool = True,
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Dict[str, Any]:
        """
        🔥 Prepara dados com validação, limpeza e balanceamento
        """
        logger.info(f"📊 Preparando dados para {model_type}")
        
        # Verificar coluna alvo
        if target_col not in df.columns:
            raise ValueError(f"Coluna '{target_col}' não encontrada")
        
        # Separar X e y
        X = df.drop(columns=[target_col])
        y = df[target_col]
        
        # Verificar se y tem dados
        if len(y) == 0:
            raise ValueError("Coluna alvo está vazia")
        
        # Determinar tipo
        is_classification = model_type == 'classifier'
        unique_classes = len(y.unique())
        
        # Se for classificação com muitas classes, sugerir regressão
        if is_classification and unique_classes > 20:
            logger.warning(f"⚠️ Muitas classes ({unique_classes}), considere regressão")
        
        # Selecionar apenas colunas numéricas
        numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = X.select_dtypes(include=['object', 'category']).columns.tolist()
        
        logger.info(f"   🔢 Colunas numéricas: {len(numeric_cols)}")
        logger.info(f"   📝 Colunas categóricas: {len(categorical_cols)}")
        
        # Codificar colunas categóricas
        if categorical_cols:
            logger.info(f"   🔄 Codificando colunas categóricas...")
            for col in categorical_cols:
                try:
                    le = LabelEncoder()
                    X[col] = le.fit_transform(X[col].astype(str))
                    numeric_cols.append(col)
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro ao codificar {col}: {e}")
        
        # Usar apenas colunas numéricas
        X = X[numeric_cols]
        
        # Verificar se há features
        if X.empty:
            raise ValueError("Nenhuma coluna numérica encontrada para treinamento")
        
        # Verificar dados suficientes
        if len(X) < 10:
            raise ValueError(f"Dados insuficientes: {len(X)} amostras (mínimo 10)")
        
        # Remover colunas com variância zero
        for col in X.columns:
            if X[col].std() == 0:
                logger.info(f"   ⚠️ Removendo coluna com variância zero: {col}")
                X = X.drop(columns=[col])
        
        # Tratar valores infinitos
        X = X.replace([np.inf, -np.inf], np.nan)
        
        # Preencher NaN com mediana
        for col in X.columns:
            if X[col].isna().any():
                median_val = X[col].median()
                X[col] = X[col].fillna(median_val)
                logger.info(f"   🔧 Preenchendo NaN em {col} com mediana: {median_val:.2f}")
        
        # Verificar se ainda há features
        if X.empty:
            raise ValueError("Após limpeza, nenhuma feature restante")
        
        # Selecionar top K features (se houver muitas)
        if len(X.columns) > TrainConfig.MAX_FEATURES:
            try:
                score_func = f_classif if is_classification else f_regression
                selector = SelectKBest(score_func, k=min(TrainConfig.MAX_FEATURES, len(X.columns)))
                selector.fit(X, y)
                selected_mask = selector.get_support()
                selected_features = X.columns[selected_mask].tolist()
                X = X[selected_features]
                logger.info(f"   🔍 Selecionadas top {len(selected_features)} features")
            except Exception as e:
                logger.warning(f"   ⚠️ Erro na seleção de features: {e}")
        
        # Dividir dados
        stratify = y if is_classification and unique_classes <= 10 else None
        
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, 
                test_size=test_size, 
                random_state=random_state,
                stratify=stratify
            )
        except Exception as e:
            logger.warning(f"   ⚠️ Erro na estratificação: {e}")
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, 
                test_size=test_size, 
                random_state=random_state
            )
        
        # Balanceamento para classificação (se solicitado)
        if is_classification and balance and IMB_AVAILABLE:
            class_counts = pd.Series(y_train).value_counts()
            if len(class_counts) > 1 and class_counts.min() / class_counts.max() < 0.3:
                logger.info(f"   ⚠️ Classes desbalanceadas: {dict(class_counts)}")
                try:
                    smote = SMOTE(random_state=random_state)
                    X_train, y_train = smote.fit_resample(X_train, y_train)
                    logger.info(f"   ✅ SMOTE aplicado: {len(X_train)} amostras")
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro no SMOTE: {e}")
        
        return {
            'X': X,
            'y': y,
            'X_train': X_train,
            'X_test': X_test,
            'y_train': y_train,
            'y_test': y_test,
            'features': X.columns.tolist(),
            'feature_count': len(X.columns),
            'total_samples': len(X),
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'is_classification': is_classification,
            'classes': np.unique(y).tolist() if is_classification else None,
            'unique_classes': unique_classes,
            'numeric_cols': numeric_cols,
            'categorical_cols': categorical_cols
        }
    
    # ==============================================
    # 🔥 AUTO-ML - TESTA MÚLTIPLOS MODELOS
    # ==============================================
    
    def _auto_select_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        is_classification: bool,
        model_type: str = 'classifier'
    ) -> Tuple[Any, str, Dict[str, Any], Dict[str, Any]]:
        """
        🔥 Testa múltiplos modelos e retorna o melhor
        """
        logger.info(f"🤖 Auto-ML: testando modelos...")
        
        if is_classification:
            models_config = TrainConfig.CLASSIFIERS
            scoring = 'accuracy'
        else:
            models_config = TrainConfig.REGRESSORS
            scoring = 'r2'
        
        results = {}
        best_score = -np.inf
        best_model = None
        best_name = None
        best_params = None
        best_metrics = {}
        
        # Testar cada modelo
        for name, config in models_config.items():
            try:
                logger.info(f"   🔍 Testando {name}...")
                
                # Modelo com parâmetros padrão
                model = config['model'](**config['default_params'])
                model.fit(X_train, y_train)
                
                # Avaliar
                if is_classification:
                    y_pred = model.predict(X_test)
                    score = accuracy_score(y_test, y_pred)
                    precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
                    recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
                    f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
                    
                    metrics = {
                        'accuracy': float(score),
                        'precision': float(precision),
                        'recall': float(recall),
                        'f1_score': float(f1)
                    }
                    
                    # ROC AUC (se binário)
                    if len(np.unique(y_test)) == 2 and hasattr(model, 'predict_proba'):
                        try:
                            y_proba = model.predict_proba(X_test)[:, 1]
                            roc_auc = roc_auc_score(y_test, y_proba)
                            metrics['roc_auc'] = float(roc_auc)
                        except:
                            pass
                    
                    results[name] = {
                        'score': score,
                        'model': model,
                        'params': config['default_params'],
                        'metrics': metrics
                    }
                    
                    logger.info(f"      Acc: {score:.4f}, F1: {f1:.4f}")
                    
                else:
                    y_pred = model.predict(X_test)
                    score = r2_score(y_test, y_pred)
                    mse = mean_squared_error(y_test, y_pred)
                    rmse = np.sqrt(mse)
                    mae = mean_absolute_error(y_test, y_pred)
                    
                    metrics = {
                        'r2_score': float(score),
                        'mse': float(mse),
                        'rmse': float(rmse),
                        'mae': float(mae)
                    }
                    
                    results[name] = {
                        'score': score,
                        'model': model,
                        'params': config['default_params'],
                        'metrics': metrics
                    }
                    
                    logger.info(f"      R²: {score:.4f}, RMSE: {rmse:.4f}")
                
                # Atualizar melhor
                if score > best_score:
                    best_score = score
                    best_model = model
                    best_name = name
                    best_params = config['default_params']
                    best_metrics = metrics
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Erro no modelo {name}: {e}")
                continue
        
        # Verificar se algum modelo funcionou
        if best_model is None:
            logger.warning("⚠️ Nenhum modelo funcionou, usando fallback")
            if is_classification:
                best_model = RandomForestClassifier(**TrainConfig.CLASSIFIERS['random_forest']['default_params'])
            else:
                best_model = RandomForestRegressor(**TrainConfig.REGRESSORS['random_forest']['default_params'])
            best_model.fit(X_train, y_train)
            best_name = 'fallback_random_forest'
            best_params = {}
            best_metrics = {}
        
        logger.info(f"   ✅ Melhor modelo: {best_name} (score: {best_score:.4f})")
        
        return best_model, best_name, results, best_metrics
    
    # ==============================================
    # 🔥 HYPERPARAMETER TUNING
    # ==============================================
    
    def _tune_hyperparameters(
        self,
        model: Any,
        model_name: str,
        X_train: np.ndarray,
        y_train: pd.Series,
        is_classification: bool
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        🔥 Otimiza hiperparâmetros com GridSearchCV/RandomizedSearchCV
        """
        logger.info(f"🔧 Otimizando hiperparâmetros para {model_name}...")
        
        if is_classification:
            config = TrainConfig.CLASSIFIERS.get(model_name)
        else:
            config = TrainConfig.REGRESSORS.get(model_name)
        
        if not config or not config.get('params'):
            logger.info("   ℹ️ Sem parâmetros para otimizar")
            return model, {}
        
        param_grid = config['params']
        
        # Se muitos parâmetros, usar RandomizedSearchCV
        total_combinations = 1
        for v in param_grid.values():
            total_combinations *= len(v)
        
        if total_combinations > 50:
            logger.info(f"   🔄 Usando RandomizedSearchCV ({total_combinations} combinações)")
            search = RandomizedSearchCV(
                model,
                param_grid,
                n_iter=min(30, total_combinations),
                cv=min(3, TrainConfig.CV_FOLDS),
                scoring='accuracy' if is_classification else 'r2',
                n_jobs=TrainConfig.N_JOBS,
                random_state=TrainConfig.RANDOM_STATE,
                verbose=0
            )
        else:
            logger.info(f"   🔄 Usando GridSearchCV ({total_combinations} combinações)")
            search = GridSearchCV(
                model,
                param_grid,
                cv=min(3, TrainConfig.CV_FOLDS),
                scoring='accuracy' if is_classification else 'r2',
                n_jobs=TrainConfig.N_JOBS,
                verbose=0
            )
        
        try:
            search.fit(X_train, y_train)
            best_params = search.best_params_
            best_score = search.best_score_
            best_model = search.best_estimator_
            
            logger.info(f"   ✅ Melhores parâmetros: {best_params}")
            logger.info(f"   ✅ Melhor score: {best_score:.4f}")
            
            return best_model, best_params
            
        except Exception as e:
            logger.warning(f"   ⚠️ Erro na otimização: {e}")
            return model, {}
    
    # ==============================================
    # 🔥 ENSEMBLE
    # ==============================================
    
    def _create_ensemble(
        self,
        X_train: np.ndarray,
        y_train: pd.Series,
        is_classification: bool
    ) -> Any:
        """
        🔥 Cria ensemble de modelos
        """
        logger.info(f"🔗 Criando ensemble...")
        
        if is_classification:
            estimators = []
            
            # Random Forest
            estimators.append(('rf', RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
            )))
            
            # Gradient Boosting
            estimators.append(('gb', GradientBoostingClassifier(
                n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42
            )))
            
            # Logistic Regression (se dados permitirem)
            if X_train.shape[0] > 100:
                estimators.append(('lr', LogisticRegression(
                    C=1.0, max_iter=1000, random_state=42, n_jobs=-1
                )))
            
            # XGBoost (se disponível)
            if XGB_AVAILABLE:
                estimators.append(('xgb', XGBClassifier(
                    n_estimators=100, learning_rate=0.1, max_depth=5,
                    random_state=42, use_label_encoder=False, eval_metric='logloss'
                )))
            
            # LightGBM (se disponível)
            if LGBM_AVAILABLE:
                estimators.append(('lgb', LGBMClassifier(
                    n_estimators=100, learning_rate=0.1, num_leaves=31,
                    random_state=42, verbose=-1
                )))
            
            ensemble = VotingClassifier(
                estimators=estimators,
                voting='soft',
                weights=[1] * len(estimators)
            )
            
        else:
            estimators = []
            
            # Random Forest
            estimators.append(('rf', RandomForestRegressor(
                n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
            )))
            
            # Gradient Boosting
            estimators.append(('gb', GradientBoostingRegressor(
                n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42
            )))
            
            # XGBoost (se disponível)
            if XGB_AVAILABLE:
                estimators.append(('xgb', XGBRegressor(
                    n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42
                )))
            
            # LightGBM (se disponível)
            if LGBM_AVAILABLE:
                estimators.append(('lgb', LGBMRegressor(
                    n_estimators=100, learning_rate=0.1, num_leaves=31,
                    random_state=42, verbose=-1
                )))
            
            ensemble = VotingRegressor(
                estimators=estimators,
                weights=[1] * len(estimators)
            )
        
        ensemble.fit(X_train, y_train)
        logger.info(f"   ✅ Ensemble criado com {len(estimators)} modelos")
        return ensemble
    
    # ==============================================
    # 🔥 TREINAMENTO PRINCIPAL
    # ==============================================
    
    async def train_and_get_metrics(
        self, 
        df: pd.DataFrame, 
        target_col: str, 
        model_type: str = 'classifier',
        auto_ml: bool = True,
        tune_hyperparams: bool = True,
        feature_selection: bool = True,
        balance: bool = True,
        ensemble: bool = False,
        test_size: float = 0.2,
        cv_folds: int = 5,
        random_state: int = 42,
        save_model: bool = True,
        use_historical_means: bool = True
    ) -> Dict[str, Any]:
        """
        🔥 MÉTODO PRINCIPAL - TREINA MODELO COMPLETO
        
        Args:
            df: DataFrame com dados
            target_col: Coluna alvo
            model_type: 'classifier' ou 'regressor'
            auto_ml: Testar múltiplos modelos automaticamente
            tune_hyperparams: Otimizar hiperparâmetros
            feature_selection: Selecionar melhores features
            balance: Balancear classes (classificação)
            ensemble: Criar ensemble de modelos
            test_size: Tamanho do conjunto de teste
            cv_folds: Número de folds para validação cruzada
            random_state: Semente aleatória
            save_model: Salvar modelo em disco
            use_historical_means: Usar médias históricas para fallback
        
        Returns:
            Dicionário com métricas completas
        """
        print(f"\n{'='*70}")
        print("📊 INICIANDO TREINAMENTO DE MODELO V3.0")
        print(f"{'='*70}")
        print(f"🎯 Alvo: {target_col}")
        print(f"📊 Tipo: {model_type}")
        print(f"🤖 Auto-ML: {auto_ml}")
        print(f"🔧 Tuning: {tune_hyperparams}")
        print(f"🔍 Feature Selection: {feature_selection}")
        print(f"⚖️ Balanceamento: {balance}")
        print(f"🔗 Ensemble: {ensemble}")
        print(f"📊 CV Folds: {cv_folds}")
        print("=" * 70)
        
        start_time = datetime.now()
        
        try:
            # 1. Preparar dados
            data = self._prepare_data(
                df, target_col, model_type,
                balance=balance,
                test_size=test_size,
                random_state=random_state
            )
            
            X_train = data['X_train']
            X_test = data['X_test']
            y_train = data['y_train']
            y_test = data['y_test']
            is_classification = data['is_classification']
            
            print(f"\n📊 Dados preparados:")
            print(f"   • Total: {data['total_samples']} amostras")
            print(f"   • Treino: {data['train_samples']} amostras")
            print(f"   • Teste: {data['test_samples']} amostras")
            print(f"   • Features: {data['feature_count']}")
            
            # 2. Escalar dados
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # 3. Selecionar features (se solicitado)
            if feature_selection and data['feature_count'] > 3:
                try:
                    if is_classification:
                        selector_model = RandomForestClassifier(n_estimators=50, random_state=random_state)
                    else:
                        selector_model = RandomForestRegressor(n_estimators=50, random_state=random_state)
                    selector_model.fit(X_train_scaled, y_train)
                    selector = SelectFromModel(selector_model, threshold='median')
                    selector.fit(X_train_scaled, y_train)
                    
                    selected_mask = selector.get_support()
                    X_train_scaled = X_train_scaled[:, selected_mask]
                    X_test_scaled = X_test_scaled[:, selected_mask]
                    
                    selected_features = [f for f, m in zip(data['features'], selected_mask) if m]
                    data['selected_features'] = selected_features
                    data['feature_count_selected'] = len(selected_features)
                    
                    print(f"   🔍 Features selecionadas: {len(selected_features)}/{len(data['features'])}")
                    
                except Exception as e:
                    print(f"   ⚠️ Erro na seleção de features: {e}")
            
            # 4. Auto-ML (se solicitado)
            if auto_ml:
                model, model_name, results, best_metrics = self._auto_select_model(
                    X_train_scaled, y_train,
                    X_test_scaled, y_test,
                    is_classification,
                    model_type
                )
                
                # 5. Otimizar hiperparâmetros (se solicitado)
                if tune_hyperparams:
                    model, best_params = self._tune_hyperparameters(
                        model, model_name,
                        X_train_scaled, y_train,
                        is_classification
                    )
                else:
                    best_params = {}
            else:
                # Usar modelo padrão
                if is_classification:
                    model_name = 'random_forest'
                    model = RandomForestClassifier(**TrainConfig.CLASSIFIERS['random_forest']['default_params'])
                else:
                    model_name = 'random_forest'
                    model = RandomForestRegressor(**TrainConfig.REGRESSORS['random_forest']['default_params'])
                
                model.fit(X_train_scaled, y_train)
                best_params = {}
                best_metrics = {}
            
            # 6. Ensemble (se solicitado)
            if ensemble:
                try:
                    model = self._create_ensemble(
                        X_train_scaled, y_train,
                        is_classification
                    )
                    print(f"   🔗 Ensemble criado com sucesso")
                except Exception as e:
                    print(f"   ⚠️ Erro no ensemble: {e}")
            
            # 7. Avaliar modelo
            metrics = self._evaluate_model(
                model, 
                X_test_scaled, 
                y_test, 
                is_classification,
                X_train_scaled,
                y_train,
                data
            )
            
            # 8. Adicionar metadados
            metrics.update({
                'model_name': model_name,
                'model_type': model_type,
                'auto_ml': auto_ml,
                'tune_hyperparams': tune_hyperparams,
                'feature_selection': feature_selection,
                'balance': balance,
                'ensemble': ensemble,
                'best_params': best_params,
                'features_used': data.get('selected_features', data['features']),
                'feature_count': len(data.get('selected_features', data['features'])),
                'total_samples': data['total_samples'],
                'train_samples': data['train_samples'],
                'test_samples': data['test_samples'],
                'training_date': datetime.now().isoformat(),
                'training_duration_seconds': (datetime.now() - start_time).total_seconds()
            })
            
            # 9. Salvar modelo
            model_path = None
            if save_model:
                model_path = self._save_model(
                    model, 
                    scaler, 
                    metrics, 
                    model_name,
                    data
                )
                metrics['model_path'] = model_path
            
            # 10. Atualizar histórico
            self.training_history.append({
                'timestamp': datetime.now().isoformat(),
                'model_name': model_name,
                'model_type': model_type,
                'main_metric': metrics.get('main_metric', 0),
                'accuracy': metrics.get('accuracy', 0),
                'precision': metrics.get('precision', 0),
                'recall': metrics.get('recall', 0),
                'f1_score': metrics.get('f1_score', 0),
                'r2_score': metrics.get('r2_score', 0),
                'mse': metrics.get('mse', 0),
                'rmse': metrics.get('rmse', 0),
                'mae': metrics.get('mae', 0),
                'feature_count': len(metrics.get('features_used', [])),
                'total_samples': data['total_samples'],
                'auto_ml': auto_ml,
                'tune_hyperparams': tune_hyperparams,
                'ensemble': ensemble,
                'model_path': model_path
            })
            
            # 11. Guardar melhor modelo
            main_metric = metrics.get('main_metric', 0)
            if main_metric > self._get_best_metric():
                self.best_model = model
                self.best_scaler = scaler
                self.best_features = data.get('selected_features', data['features'])
                self.best_metrics = metrics
                self.best_model_name = model_name
                self.best_model_type = model_type
                self.is_classification = is_classification
            
            # 12. Atualizar estatísticas
            self.stats["total_trainings"] += 1
            self.stats["successful_trainings"] += 1
            self.stats["models_tested"][model_name] = self.stats["models_tested"].get(model_name, 0) + 1
            
            if is_classification:
                self.stats["best_accuracy"] = max(self.stats["best_accuracy"], metrics.get('accuracy', 0))
            else:
                self.stats["best_r2"] = max(self.stats["best_r2"], metrics.get('r2_score', 0))
            
            print(f"\n✅ Treinamento concluído!")
            print(f"   📊 Modelo: {model_name}")
            print(f"   📈 Métrica principal: {metrics.get('main_metric', 0):.4f}")
            if model_path:
                print(f"   📁 Salvo em: {model_path}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Erro no treinamento: {e}")
            import traceback
            traceback.print_exc()
            self.stats["failed_trainings"] += 1
            return {
                "erro": str(e),
                "status": "failed",
                "tipo_modelo": model_type,
                "data": datetime.now().isoformat()
            }
    
    # ==============================================
    # 🔥 AVALIAÇÃO DE MODELO
    # ==============================================
    
    def _evaluate_model(
        self,
        model: Any,
        X_test: np.ndarray,
        y_test: pd.Series,
        is_classification: bool,
        X_train: np.ndarray = None,
        y_train: pd.Series = None,
        data: Dict = None
    ) -> Dict[str, Any]:
        """
        🔥 Avalia modelo com múltiplas métricas
        """
        metrics = {}
        
        # Previsões
        y_pred = model.predict(X_test)
        
        if is_classification:
            # Métricas de classificação
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
            recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
            f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
            
            metrics.update({
                'accuracy': float(accuracy),
                'precision': float(precision),
                'recall': float(recall),
                'f1_score': float(f1),
                'main_metric': float(accuracy),
                'acurácia': float(accuracy),
                'acuracia': float(accuracy)
            })
            
            # ROC AUC (se for binário)
            if len(np.unique(y_test)) == 2:
                try:
                    if hasattr(model, 'predict_proba'):
                        y_proba = model.predict_proba(X_test)[:, 1]
                        roc_auc = roc_auc_score(y_test, y_proba)
                        metrics['roc_auc'] = float(roc_auc)
                except Exception:
                    pass
            
            # Validação cruzada
            if X_train is not None and y_train is not None:
                try:
                    cv_scores = cross_val_score(
                        model, X_train, y_train, 
                        cv=min(5, len(y_train)), 
                        scoring='accuracy'
                    )
                    metrics['cv_mean'] = float(cv_scores.mean())
                    metrics['cv_std'] = float(cv_scores.std())
                except Exception:
                    pass
            
            # Matriz de confusão
            try:
                conf_matrix = confusion_matrix(y_test, y_pred)
                metrics['confusion_matrix'] = conf_matrix.tolist()
            except Exception:
                pass
            
            # Relatório de classificação
            try:
                class_report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
                metrics['classification_report'] = class_report
            except Exception:
                pass
            
        else:
            # Métricas de regressão
            mse = mean_squared_error(y_test, y_pred)
            rmse = np.sqrt(mse)
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            
            metrics.update({
                'mse': float(mse),
                'rmse': float(rmse),
                'mae': float(mae),
                'r2_score': float(r2),
                'main_metric': float(r2),
                'r2': float(r2)
            })
            
            # Validação cruzada
            if X_train is not None and y_train is not None:
                try:
                    cv_scores = cross_val_score(
                        model, X_train, y_train, 
                        cv=min(5, len(y_train)), 
                        scoring='r2'
                    )
                    metrics['cv_mean'] = float(cv_scores.mean())
                    metrics['cv_std'] = float(cv_scores.std())
                except Exception:
                    pass
        
        # Feature importance
        if hasattr(model, 'feature_importances_'):
            features = data.get('selected_features', data.get('features', []))
            if len(features) == len(model.feature_importances_):
                importance = dict(zip(features, model.feature_importances_))
                importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
                metrics['feature_importance'] = importance
            else:
                metrics['feature_importance'] = {
                    f'feature_{i}': float(v) 
                    for i, v in enumerate(model.feature_importances_)
                }
        
        return metrics
    
    # ==============================================
    # 🔥 SALVAR E CARREGAR MODELOS
    # ==============================================
    
    def _save_model(
        self,
        model: Any,
        scaler: Any,
        metrics: Dict[str, Any],
        model_name: str,
        data: Dict[str, Any]
    ) -> str:
        """
        🔥 Salva modelo com metadados
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{model_name}_{timestamp}.pkl"
        filepath = os.path.join(self.models_dir, filename)
        
        model_data = {
            'model': model,
            'scaler': scaler,
            'metrics': metrics,
            'features': data.get('selected_features', data['features']),
            'model_name': model_name,
            'model_type': 'classifier' if data.get('is_classification') else 'regressor',
            'training_date': datetime.now().isoformat(),
            'version': '3.0',
            'feature_count': len(data.get('selected_features', data['features'])),
            'total_samples': data['total_samples']
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
        
        # Também salvar como modelo padrão
        default_path = os.path.join(self.models_dir, "trained_model.pkl")
        with open(default_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"✅ Modelo salvo: {filepath}")
        return filepath
    
    def load_model(self, model_path: str) -> Dict[str, Any]:
        """
        🔥 Carrega modelo salvo
        """
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
        
        logger.info(f"✅ Modelo carregado: {model_path}")
        return model_data
    
    def load_best_model(self) -> Optional[Dict[str, Any]]:
        """
        🔥 Carrega o melhor modelo salvo
        """
        default_path = os.path.join(self.models_dir, "trained_model.pkl")
        if os.path.exists(default_path):
            return self.load_model(default_path)
        return None
    
    # ==============================================
    # 🔥 RESUMO PARA GEMINI
    # ==============================================
    
    def get_training_summary_for_gemini(self) -> Dict[str, Any]:
        """
        🔥 Retorna resumo do histórico para o Gemini
        """
        if not self.training_history:
            return {
                "status": "nenhum_treinamento",
                "mensagem": "Nenhum modelo foi treinado ainda",
                "total_treinamentos": 0,
                "historico": [],
                "melhor_acuracia": 0,
                "media_acuracia": 0,
                "recomendacao": "Treine um modelo primeiro para obter insights"
            }
        
        # Extrair métricas principais
        metrics_list = []
        for h in self.training_history:
            metric = h.get('main_metric', h.get('acuracia', h.get('accuracy', h.get('r2_score', 0))))
            metrics_list.append(metric)
        
        best_metric = max(metrics_list) if metrics_list else 0
        avg_metric = np.mean(metrics_list) if metrics_list else 0
        
        best_index = metrics_list.index(best_metric) if metrics_list else -1
        best_training = self.training_history[best_index] if best_index >= 0 else None
        
        # Análise de modelos
        models_used = {}
        for h in self.training_history:
            name = h.get('model_name', 'unknown')
            models_used[name] = models_used.get(name, 0) + 1
        
        summary = {
            "status": "sucesso",
            "total_treinamentos": len(self.training_history),
            "historico": self.training_history[-5:],
            "melhor_acuracia": best_metric,
            "melhor_accuracy": best_metric,
            "melhor_r2": best_metric,
            "media_acuracia": avg_metric,
            "media_accuracy": avg_metric,
            "media_r2": avg_metric,
            "melhor_treinamento": best_training,
            "tipos_modelos": list(set([h.get('model_type') for h in self.training_history])),
            "modelos_usados": list(set([h.get('model_name') for h in self.training_history])),
            "frequencia_modelos": models_used,
            "recomendacao": self._generate_recommendation(best_metric, avg_metric, len(self.training_history))
        }
        
        return summary
    
    def _generate_recommendation(self, best_metric: float, avg_metric: float, total_count: int) -> str:
        """
        🔥 Gera recomendação baseada nas métricas
        """
        if best_metric >= 0.95:
            return "🏆 Modelo EXCELENTE! Pode ser utilizado em produção com total confiança."
        elif best_metric >= 0.90:
            return "✅ Modelo ÓTIMO. Pode ser utilizado em produção com alta confiança."
        elif best_metric >= 0.85:
            return "📈 Modelo BOM. Considere validar com dados reais antes de produção."
        elif best_metric >= 0.80:
            return "📊 Modelo RAZOÁVEL. Recomenda-se mais dados e engenharia de features."
        elif best_metric >= 0.70:
            return "🔧 Modelo REGULAR. Precisa de melhorias significativas."
        elif best_metric >= 0.60:
            return "⚠️ Modelo FRACO. Revise a qualidade dos dados e seleção de features."
        else:
            return "❌ Modelo RUIM. Dados insuficientes ou incorretos. Revise o dataset."
    
    def get_best_model_info(self) -> Optional[Dict[str, Any]]:
        """
        🔥 Retorna informações do melhor modelo treinado
        """
        if not self.training_history:
            return None
        
        best = max(self.training_history, key=lambda x: x.get('main_metric', 0))
        return best
    
    def get_training_stats(self) -> Dict[str, Any]:
        """
        🔥 Retorna estatísticas de treinamento
        """
        if not self.training_history:
            return {"total_treinos": 0, "historico_vazio": True}
        
        return {
            "total_treinos": len(self.training_history),
            "modelos_usados": list(set([h.get('model_name', 'unknown') for h in self.training_history])),
            "tipos": list(set([h.get('model_type', 'unknown') for h in self.training_history])),
            "melhor_metric": max([h.get('main_metric', 0) for h in self.training_history]),
            "media_metric": np.mean([h.get('main_metric', 0) for h in self.training_history]),
            "ultimo_treino": self.training_history[-1] if self.training_history else None,
            "melhor_modelo": self.get_best_model_info()
        }
    
    def _get_best_metric(self) -> float:
        """Retorna a melhor métrica do histórico"""
        if not self.training_history:
            return -np.inf
        return max([h.get('main_metric', 0) for h in self.training_history])
    
    # ==============================================
    # 🔥 SHAP EXPLAINABILITY
    # ==============================================
    
    def explain_model(self, X_sample: np.ndarray, feature_names: List[str] = None) -> Optional[Dict]:
        """
        🔥 Explica predições com SHAP
        """
        if not SHAP_AVAILABLE or self.best_model is None:
            return None
        
        try:
            if feature_names is None:
                feature_names = self.best_features or [f"feature_{i}" for i in range(X_sample.shape[1])]
            
            explainer = shap.TreeExplainer(self.best_model)
            shap_values = explainer.shap_values(X_sample)
            
            return {
                'shap_values': shap_values.tolist() if hasattr(shap_values, 'tolist') else shap_values,
                'base_value': float(explainer.expected_value) if hasattr(explainer, 'expected_value') else 0,
                'feature_names': feature_names
            }
        except Exception as e:
            logger.warning(f"⚠️ Erro no SHAP: {e}")
            return None
    
    # ==============================================
    # 🔥 PREDIÇÃO
    # ==============================================
    
    def predict(self, X: np.ndarray, scale: bool = True) -> np.ndarray:
        """
        🔥 Faz predições com o melhor modelo
        """
        if self.best_model is None:
            raise ValueError("Nenhum modelo treinado. Execute train_and_get_metrics primeiro.")
        
        if scale and self.best_scaler is not None:
            X_scaled = self.best_scaler.transform(X)
        else:
            X_scaled = X
        
        return self.best_model.predict(X_scaled)
    
    def predict_proba(self, X: np.ndarray, scale: bool = True) -> np.ndarray:
        """
        🔥 Retorna probabilidades (classificação)
        """
        if self.best_model is None:
            raise ValueError("Nenhum modelo treinado.")
        
        if not self.is_classification:
            raise ValueError("Modelo não é de classificação")
        
        if scale and self.best_scaler is not None:
            X_scaled = self.best_scaler.transform(X)
        else:
            X_scaled = X
        
        if hasattr(self.best_model, 'predict_proba'):
            return self.best_model.predict_proba(X_scaled)
        else:
            # Fallback: usar decision function ou placeholder
            logger.warning("⚠️ Modelo não tem predict_proba, usando fallback")
            return np.column_stack([1 - self.predict(X_scaled), self.predict(X_scaled)])
    
    # ==============================================
    # 🔥 UTILITÁRIOS
    # ==============================================
    
    def get_model_summary(self) -> Dict[str, Any]:
        """
        🔥 Retorna resumo completo do modelo
        """
        return {
            "modelo_carregado": self.best_model is not None,
            "modelo_nome": self.best_model_name,
            "modelo_tipo": self.best_model_type,
            "classificacao": self.is_classification,
            "features": self.best_features[:10] if self.best_features else [],
            "feature_count": len(self.best_features) if self.best_features else 0,
            "metricas": self.best_metrics,
            "total_treinamentos": len(self.training_history),
            "melhor_accuracy": self.stats.get("best_accuracy", 0),
            "melhor_r2": self.stats.get("best_r2", 0),
            "modelos_testados": self.stats.get("models_tested", {}),
            "ultimo_treino": self.training_history[-1] if self.training_history else None,
            "shap_disponivel": SHAP_AVAILABLE
        }
    
    def clear_cache(self):
        """Limpa cache"""
        self._model_cache.clear()
        self._scaler_cache.clear()
        logger.info("🧹 Cache limpo")
    
    def reset(self):
        """Reseta o estado do treinador"""
        self.best_model = None
        self.best_scaler = None
        self.best_features = None
        self.best_metrics = {}
        self.best_model_name = None
        self.best_model_type = None
        self.training_history = []
        self.stats = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "best_accuracy": 0,
            "best_r2": 0,
            "models_tested": {},
            "started_at": datetime.now().isoformat()
        }
        logger.info("🔄 Trainer resetado")


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

trainer = ModelTrainer()


# ==============================================
# FUNÇÃO DE TESTE
# ==============================================

async def test_trainer():
    """
    🔥 Testa o treinador com dados sintéticos
    """
    print("\n" + "=" * 70)
    print("🧪 TESTANDO MODEL TRAINER V3.0")
    print("=" * 70)
    
    import pandas as pd
    import numpy as np
    
    # Dados sintéticos
    np.random.seed(42)
    n_samples = 500
    
    df = pd.DataFrame({
        'feature_1': np.random.randn(n_samples) * 10 + 50,
        'feature_2': np.random.randn(n_samples) * 5 + 30,
        'feature_3': np.random.randn(n_samples) * 2 + 10,
        'feature_4': np.random.randn(n_samples) * 3 + 20,
        'target': np.random.randint(0, 2, n_samples)
    })
    
    print(f"📊 Dados de teste: {n_samples} amostras, 4 features")
    
    # Treinar
    metrics = await trainer.train_and_get_metrics(
        df=df,
        target_col='target',
        model_type='classifier',
        auto_ml=True,
        tune_hyperparams=True,
        feature_selection=True,
        balance=True,
        ensemble=True
    )
    
    print("\n📊 MÉTRICAS:")
    if 'erro' in metrics:
        print(f"   ❌ Erro: {metrics['erro']}")
    else:
        print(f"   ✅ Acuracia: {metrics.get('acuracia', 0):.4f}")
        print(f"   ✅ Precision: {metrics.get('precision', 0):.4f}")
        print(f"   ✅ Recall: {metrics.get('recall', 0):.4f}")
        print(f"   ✅ F1-Score: {metrics.get('f1_score', 0):.4f}")
        print(f"   🤖 Modelo: {metrics.get('model_name', 'unknown')}")
        print(f"   📁 Salvo em: {metrics.get('model_path', 'unknown')}")
    
    # Resumo para Gemini
    summary = trainer.get_training_summary_for_gemini()
    print(f"\n📊 RESUMO GEMINI:")
    print(f"   Total treinos: {summary.get('total_treinamentos', 0)}")
    print(f"   Melhor acuracia: {summary.get('melhor_acuracia', 0):.4f}")
    print(f"   Media acuracia: {summary.get('media_acuracia', 0):.4f}")
    print(f"   Recomendacao: {summary.get('recomendacao', 'N/A')}")
    
    print("\n" + "=" * 70)
    print("✅ Teste concluído!")
    print("=" * 70)
    
    return metrics


# ==============================================
# INICIALIZAÇÃO
# ==============================================

print("\n" + "=" * 70)
print("✅ train.py V3.0 carregado com sucesso!")
print("=" * 70)
print("   🔥 AUTO-ML: Testa 10+ modelos automaticamente")
print("   🔥 HYPERPARAMETER TUNING: Otimização com GridSearchCV")
print("   🔥 FEATURE SELECTION: Seleção automática das melhores features")
print("   🔥 ENSEMBLE: Combinação ponderada de modelos")
print("   🔥 SHAP: Explicabilidade de predições")
print("   🔥 SMOTE: Balanceamento de classes")
print("   📊 MODELOS DISPONÍVEIS:")
print("      • Classificadores: " + ", ".join(TrainConfig.CLASSIFIERS.keys()))
print("      • Regressores: " + ", ".join(TrainConfig.REGRESSORS.keys()))
print("   📊 MÉTODOS:")
print("      • trainer.train_and_get_metrics(df, target_col, ...)")
print("      • trainer.get_training_summary_for_gemini()")
print("      • trainer.get_best_model_info()")
print("      • trainer.predict(X)")
print("      • trainer.predict_proba(X)")
print("      • trainer.explain_model(X_sample, feature_names)")
print("=" * 70)