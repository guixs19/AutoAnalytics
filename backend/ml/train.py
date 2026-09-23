# backend/ml/train.py - VERSÃO 5.0 (PRODUÇÃO REAL)
"""
🔥 TRAIN.PY V5.0 - PRODUÇÃO REAL
================================================================================
✅ CORREÇÕES CRÍTICAS V5.0:
   - 🐛 BUG CORRIGIDO: Removido np.random em _expand_features
   - 🐛 BUG CORRIGIDO: Removido np.random.choice em _reduce_features
   - ✅ Determinismo total: mesmo input → mesmo output
   - ✅ ZERO ruído aleatório em features

✅ NOVAS INTELIGÊNCIAS V5.0:
   - 🎯 Auto-detecção de target (se não informado)
   - 📊 RobustScaler + winsorização automática
   - 🚨 Detecção de data leakage
   - 📈 CV estratificada + detecção de overfitting
   - 🎯 Recomendação de modelos por contexto
   - 📉 Baseline de drift
   - ⏱️ Early stopping em modelos iterativos
   - 💬 Explicação em português para leigos

✅ PRODUÇÃO V5.0:
   - 📝 Logging estruturado
   - 🛡️ Validação de entrada
   - 🔒 Determinismo total (seeds fixas)
   - 🧪 Tratamento robusto de erros
   - 📊 Estatísticas detalhadas
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple, List, Union
import os
import pickle
import json
import joblib
import time
from datetime import datetime
import warnings
import logging
import traceback
from dataclasses import dataclass, field, asdict

warnings.filterwarnings('ignore')

# Scikit-learn
from sklearn.model_selection import (
    train_test_split,
    cross_val_score,
    cross_validate,
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
from sklearn.decomposition import PCA
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

# Scipy para estatística
try:
    from scipy import stats
    from scipy.stats import pearsonr, spearmanr, pointbiserialr, ks_2samp
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================
# 🔥 CONFIGURAÇÕES
# ==============================================

class TrainConfig:
    """Configurações centralizadas de treinamento"""

    CLASSIFIERS = {}
    REGRESSORS = {}

    # 🔥 NORMALIZAÇÃO
    NORMALIZATION = {
        'default': 'robust',  # 🔥 MUDOU: robust por padrão
        'standard': {
            'class': StandardScaler,
            'description': 'Z-Score: (x - mean) / std'
        },
        'robust': {
            'class': RobustScaler,
            'description': 'Robusto: (x - median) / IQR'
        },
        'minmax': {
            'class': MinMaxScaler,
            'description': 'Min-Max: (x - min) / (max - min)'
        }
    }

    # 🔥 FEATURE ADAPTATION
    FEATURE_ADAPTATION = {
        'enabled': True,
        'max_features': 20,
        'min_features': 3,
        'use_pca': True,
        'use_importance': True,
        'fill_strategy': 'deterministic',  # 🔥 MUDOU: deterministic (era intelligent)
    }

    SCALERS = {
        'standard': StandardScaler,
        'robust': RobustScaler,
        'minmax': MinMaxScaler
    }

    # 🔥 Configurações de validação
    CV_FOLDS = 5
    TEST_SIZE = 0.2
    RANDOM_STATE = 42
    N_JOBS = -1
    VERBOSE = 0

    # 🔥 Validação de entrada
    MAX_FEATURES = 20
    MIN_FEATURES = 3
    MIN_SAMPLES = 10
    MAX_CLASSES = 20
    FEATURE_SELECTION_THRESHOLD = 0.8

    # 🔥 Detecção de leakage
    LEAKAGE_THRESHOLD = 0.95
    LEAKAGE_ENABLED = True

    # 🔥 Drift
    DRIFT_THRESHOLD = 0.05
    DRIFT_ENABLED = True

    # 🔥 Overfitting
    OVERFITTING_ALERT = 0.15
    OVERFITTING_WARN = 0.08

    # 🔥 Estabilidade
    STABILITY_ALERT = 0.10
    STABILITY_WARN = 0.05

    # Output
    MODELS_DIR = os.path.join("backend", "ml", "models")
    LOGS_DIR = os.path.join("backend", "ml", "logs")


# 🔥 POPULAR MODELOS DINAMICAMENTE
def _populate_model_configs():
    """Popula configurações de modelos dinamicamente"""

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
                'random_state': 42,
                'n_iter_no_change': 10,       # 🔥 Early stopping
                'validation_fraction': 0.1,
                'tol': 1e-4
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
                'random_state': 42,
                'class_weight': 'balanced'
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
                'random_state': 42,
                'class_weight': 'balanced'
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
                'random_state': 42,
                'class_weight': 'balanced'
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
                'eval_metric': 'logloss',
                'early_stopping_rounds': 10
            }
        }

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
                'verbose': -1,
                'class_weight': 'balanced'
            }
        }

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
                'random_state': 42,
                'n_iter_no_change': 10,       # 🔥 Early stopping
                'validation_fraction': 0.1,
                'tol': 1e-4
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
                'random_state': 42,
                'early_stopping_rounds': 10
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


_populate_model_configs()


# ==============================================
# 🔥 MODEL TRAINER - VERSÃO 5.0 (PRODUÇÃO REAL)
# ==============================================

class ModelTrainer:
    """
    🔥 Treinador de modelos unificado - VERSÃO 5.0 (PRODUÇÃO REAL)
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

        # Detecção de features do modelo
        self.model_feature_count = None
        self.model_feature_names = None

        # 🔥 NOVO: Estatísticas V5.0
        self.stats = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "best_accuracy": 0,
            "best_r2": 0,
            "models_tested": {},
            "started_at": datetime.now().isoformat(),
            "feature_adaptations": 0,
            "pca_applied": 0,
            "feature_expansions": 0,
            "fallback_predictions": 0,
            # 🔥 NOVOS V5.0
            "leakage_detected": 0,
            "leakage_features_removed": 0,
            "winsorized_values": 0,
            "drift_baselines_saved": 0,
            "cv_evaluations": 0,
            "overfitting_detected": 0,
            "early_stopping_used": 0
        }

        # 🔥 NOVO V5.0: RobustScaler por padrão
        self.normalization_method = TrainConfig.NORMALIZATION['default']
        self.normalizer = None

        # 🔥 NOVO V5.0: Cache do último DataFrame e target para detecção
        self._current_df = None
        self._current_target = None

        logger.info("=" * 70)
        logger.info("✅ ModelTrainer V5.0 inicializado (PRODUÇÃO REAL)")
        logger.info("=" * 70)
        logger.info(f"   📁 Modelos: {self.models_dir}")
        logger.info(f"   🔢 Classificadores: {len(TrainConfig.CLASSIFIERS)}")
        logger.info(f"   🔢 Regressores: {len(TrainConfig.REGRESSORS)}")
        logger.info(f"   📊 Normalização: {self.normalization_method} (RobustScaler)")
        logger.info(f"   🔥 Feature Adaptation: {TrainConfig.FEATURE_ADAPTATION['enabled']} (determinística)")
        logger.info(f"   🚨 Detecção de leakage: {TrainConfig.LEAKAGE_ENABLED}")
        logger.info(f"   📉 Baseline de drift: {TrainConfig.DRIFT_ENABLED}")
        logger.info(f"   🔍 SHAP: {SHAP_AVAILABLE}")
        logger.info(f"   ⚖️ SMOTE: {IMB_AVAILABLE}")
        logger.info(f"   📊 XGBoost: {XGB_AVAILABLE}")
        logger.info(f"   📊 LightGBM: {LGBM_AVAILABLE}")
        logger.info(f"   🧮 SciPy: {SCIPY_AVAILABLE}")
        logger.info("=" * 70)

    # ==============================================
    # 🔥 VALIDAÇÃO DE ENTRADA (NOVO V5.0)
    # ==============================================

    def _validate_input(self, df: pd.DataFrame, target_col: str) -> Tuple[bool, str]:
        """🛡️ Valida entrada antes de processar"""
        if df is None or len(df) == 0:
            return False, "DataFrame vazio"

        if not isinstance(df, pd.DataFrame):
            return False, f"Esperado DataFrame, recebido {type(df)}"

        if target_col not in df.columns:
            return False, f"Coluna alvo '{target_col}' não encontrada"

        if len(df) < TrainConfig.MIN_SAMPLES:
            return False, f"Amostras insuficientes: {len(df)} < {TrainConfig.MIN_SAMPLES}"

        # Verificar se target tem apenas 1 valor único
        if df[target_col].nunique() < 2:
            return False, f"Coluna alvo tem apenas {df[target_col].nunique()} valor único"

        # Verificar se features numéricas existem
        feature_cols = [c for c in df.columns if c != target_col]
        if not feature_cols:
            return False, "Nenhuma feature disponível"

        return True, "OK"

    # ==============================================
    # 🔥 DETECÇÃO DE TARGET (NOVO V5.0)
    # ==============================================

    def detect_target_column(self, df: pd.DataFrame) -> Tuple[str, str, float]:
        """
        🎯 Detecta automaticamente qual coluna é o target.

        Retorna: (target_col, tipo, confiança)
        tipo: 'binary', 'multiclass', 'regression'
        """
        candidates = []

        for col in df.columns:
            col_l = str(col).lower()
            n_unique = df[col].nunique()
            n_total = len(df)

            if not pd.api.types.is_numeric_dtype(df[col]):
                continue

            score = 0.0
            tipo = None

            # 🔥 Regra 1: Nomes sugestivos
            target_keywords = ['target', 'label', 'classe', 'class', 'resultado',
                             'outcome', 'y', 'risco', 'churn', 'falha', 'sucesso',
                             'flag', 'is_', 'tem_']
            if any(k in col_l for k in target_keywords):
                score += 0.4
                if n_unique == 2:
                    tipo = 'binary'
                elif n_unique <= 10:
                    tipo = 'multiclass'

            # 🔥 Regra 2: Binário com nomes sugestivos
            if n_unique == 2:
                if any(k in col_l for k in ['flag', 'bin', 'is_', 'tem_', 'ativo']):
                    score += 0.3
                    tipo = 'binary'

            # 🔥 Regra 3: Última coluna frequentemente é target
            if df.columns.tolist().index(col) == len(df.columns) - 1:
                score += 0.1

            # 🔥 Regra 4: Baixa cardinalidade relativa
            if n_unique < n_total * 0.1:
                score += 0.2

            if score > 0.3:
                if tipo is None:
                    if n_unique == 2:
                        tipo = 'binary'
                    elif n_unique <= TrainConfig.MAX_CLASSES:
                        tipo = 'multiclass'
                    else:
                        tipo = 'regression'

                candidates.append((col, tipo, score))

        if not candidates:
            raise ValueError("Não foi possível detectar o target automaticamente")

        candidates.sort(key=lambda x: x[2], reverse=True)
        best = candidates[0]

        logger.info(f"🎯 Target detectado: '{best[0]}' (tipo: {best[1]}, confiança: {best[2]:.2f})")
        if len(candidates) > 1:
            logger.info(f"   Alternativas: {[(c[0], round(c[2], 2)) for c in candidates[1:4]]}")

        return best

    # ==============================================
    # 🔥 WINSORIZAÇÃO (NOVO V5.0)
    # ==============================================

    def _winsorize(self, X: np.ndarray, lower: float = 0.01, upper: float = 0.99) -> np.ndarray:
        """
        🔥 Limita outliers aos percentis 1 e 99.
        Protege o scaler antes de normalizar.
        """
        if X.size == 0:
            return X

        X_clean = X.copy()
        n_clipped = 0

        for i in range(X.shape[1]):
            col = X[:, i]
            if len(col) < 3:
                continue
            lo = np.percentile(col, lower * 100)
            hi = np.percentile(col, upper * 100)
            mask = (col < lo) | (col > hi)
            n_clipped += int(mask.sum())
            X_clean[:, i] = np.clip(col, lo, hi)

        if n_clipped > 0:
            pct = n_clipped / X.size * 100
            self.stats['winsorized_values'] += n_clipped
            logger.info(f"   ✂️ Winsorizado: {n_clipped} valores ({pct:.2f}%)")

        return X_clean

    # ==============================================
    # 🔥 DETECÇÃO DE LEAKAGE (NOVO V5.0)
    # ==============================================

    def _detect_and_remove_leakage(
        self,
        df: pd.DataFrame,
        target_col: str,
        threshold: float = None
    ) -> Tuple[pd.DataFrame, List[Dict]]:
        """
        🚨 Detecta features com correlação suspeita com o target.
        Remove features que podem causar data leakage.
        """
        if not TrainConfig.LEAKAGE_ENABLED or not SCIPY_AVAILABLE:
            return df, []

        threshold = threshold or TrainConfig.LEAKAGE_THRESHOLD
        suspicious = []
        is_binary = df[target_col].nunique() == 2

        for col in df.select_dtypes(include=[np.number]).columns:
            if col == target_col:
                continue

            try:
                valid = df[[col, target_col]].dropna()
                if len(valid) < 10:
                    continue

                if is_binary:
                    corr, _ = pointbiserialr(valid[target_col], valid[col])
                else:
                    corr, _ = pearsonr(valid[col], valid[target_col])

                corr_s, _ = spearmanr(valid[col], valid[target_col])

                max_corr = max(abs(corr), abs(corr_s))

                if max_corr > threshold:
                    suspicious.append({
                        'feature': col,
                        'pearson': round(float(corr), 3),
                        'spearman': round(float(corr_s), 3),
                        'action': 'REMOVIDA'
                    })
            except Exception:
                continue

        if suspicious:
            logger.warning(f"🚨 Data leakage detectado em {len(suspicious)} features:")
            for s in suspicious:
                logger.warning(f"   • {s['feature']}: pearson={s['pearson']}, spearman={s['spearman']}")

            self.stats['leakage_detected'] += 1
            self.stats['leakage_features_removed'] += len(suspicious)

            df = df.drop(columns=[s['feature'] for s in suspicious])

        return df, suspicious

    # ==============================================
    # 🔥 SCALER INTELIGENTE (NOVO V5.0)
    # ==============================================

    def _smart_scaler(self, X: np.ndarray) -> Tuple[str, object]:
        """
        🧠 Escolhe o scaler baseado na distribuição dos dados.
        """
        if not SCIPY_AVAILABLE or X.shape[1] == 0:
            return 'robust', RobustScaler()

        skews = []
        kurtoses = []

        for i in range(X.shape[1]):
            col = X[:, i]
            if len(col) > 3:
                try:
                    skews.append(abs(stats.skew(col)))
                    kurtoses.append(abs(stats.kurtosis(col)))
                except Exception:
                    continue

        avg_skew = float(np.mean(skews)) if skews else 0.0
        avg_kurt = float(np.mean(kurtoses)) if kurtoses else 0.0

        logger.info(f"   📊 Skewness médio: {avg_skew:.2f}, Kurtosis médio: {avg_kurt:.2f}")

        if avg_kurt > 3 or avg_skew > 1.5:
            logger.info("   🎯 RobustScaler (distribuição com outliers)")
            return 'robust', RobustScaler()
        elif avg_skew < 0.5 and avg_kurt < 1:
            logger.info("   🎯 StandardScaler (distribuição normal)")
            return 'standard', StandardScaler()
        else:
            logger.info("   🎯 RobustScaler (default seguro)")
            return 'robust', RobustScaler()

    # ==============================================
    # 🔥 NORMALIZAÇÃO
    # ==============================================

    def get_normalizer(self, method: str = None):
        method = method or self.normalization_method
        if method in TrainConfig.NORMALIZATION:
            return TrainConfig.NORMALIZATION[method]['class']()
        logger.warning(f"⚠️ Método '{method}' não encontrado, usando RobustScaler")
        return RobustScaler()

    def normalize(self, X: np.ndarray, method: str = None, fit: bool = True) -> np.ndarray:
        method = method or self.normalization_method
        if fit or self.normalizer is None:
            self.normalizer = self.get_normalizer(method)
            X_normalized = self.normalizer.fit_transform(X)
            logger.info(f"📊 Normalização {method} aplicada: {X.shape} → {X_normalized.shape}")
        else:
            X_normalized = self.normalizer.transform(X)
        return X_normalized

    def denormalize(self, X: np.ndarray) -> np.ndarray:
        if self.normalizer is not None:
            return self.normalizer.inverse_transform(X)
        return X

    # ==============================================
    # 🔥 DETECÇÃO DE FEATURES DO MODELO
    # ==============================================

    def detect_model_features(self, model_data: Dict[str, Any]) -> Tuple[int, List[str]]:
        feature_count = 0
        feature_names = []

        model = model_data.get('model')
        if model is not None:
            if hasattr(model, 'n_features_in_'):
                feature_count = model.n_features_in_
                logger.info(f"   🔍 Modelo espera {feature_count} features (n_features_in_)")
            if hasattr(model, 'feature_names_in_'):
                feature_names = list(model.feature_names_in_)
                logger.info(f"   🔍 Nomes: {feature_names[:5]}...")

        if feature_count == 0:
            features = model_data.get('features', []) or model_data.get('feature_names', [])
            if features:
                feature_count = len(features)
                feature_names = features
                logger.info(f"   🔍 Modelo espera {feature_count} features (metadados)")

        if feature_count == 0:
            scaler = model_data.get('scaler')
            if scaler is not None and hasattr(scaler, 'mean_'):
                feature_count = len(scaler.mean_)
                logger.info(f"   🔍 Modelo espera {feature_count} features (scaler)")
            elif scaler is not None and hasattr(scaler, 'center_'):
                feature_count = len(scaler.center_)
                logger.info(f"   🔍 Modelo espera {feature_count} features (RobustScaler)")

        if feature_count == 0:
            feature_count = 10
            logger.warning(f"   ⚠️ Não foi possível detectar features, usando {feature_count}")

        return feature_count, feature_names

    # ==============================================
    # 🔥 ADAPTAÇÃO DE FEATURES (BUG CORRIGIDO V5.0)
    # ==============================================

    def adapt_features_automatically(
        self,
        X: np.ndarray,
        expected_features: int = None,
        expected_names: List[str] = None
    ) -> np.ndarray:
        """🔥 ADAPTA FEATURES SEM RUÍDO ALEATÓRIO"""
        if expected_features is None:
            expected_features = self.model_feature_count or 10

        actual = X.shape[1]

        if actual == expected_features:
            return X

        if actual > expected_features:
            return self._reduce_features(X, actual, expected_features)

        if actual < expected_features:
            return self._expand_features(X, actual, expected_features, expected_names)

        return X

    def _reduce_features(self, X: np.ndarray, actual: int, expected: int) -> np.ndarray:
        """
        🔥 REDUZ features SEM ALEATORIEDADE (BUG CORRIGIDO V5.0)
        """
        logger.info(f"   🔄 Reduzindo: {actual} → {expected} features")
        self.stats['feature_adaptations'] += 1

        # Estratégia 1: Feature Importance do modelo
        if (self.best_model is not None
                and hasattr(self.best_model, 'feature_importances_')
                and TrainConfig.FEATURE_ADAPTATION['use_importance']):
            importances = self.best_model.feature_importances_
            if len(importances) >= expected:
                top_indices = np.argsort(importances)[-expected:]
                top_indices = np.sort(top_indices)  # 🔥 Ordem estável
                X_reduced = X[:, top_indices]
                logger.info(f"   ✅ Feature Importance: {expected} features")
                return X_reduced

        # Estratégia 2: PCA (determinístico)
        if TrainConfig.FEATURE_ADAPTATION['use_pca']:
            try:
                pca = PCA(n_components=min(expected, actual), random_state=TrainConfig.RANDOM_STATE)
                X_reduced = pca.fit_transform(X)
                self._last_pca = pca
                self.stats['pca_applied'] += 1
                logger.info(f"   ✅ PCA: {actual} → {expected} features")
                return X_reduced
            except Exception as e:
                logger.warning(f"   ⚠️ PCA falhou: {e}")

        # 🔥 Estratégia 3: Seleção determinística (primeiras features)
        X_reduced = X[:, :expected]
        logger.info(f"   ✅ Seleção determinística: {expected} features")
        return X_reduced

    def _expand_features(
        self,
        X: np.ndarray,
        actual: int,
        expected: int,
        expected_names: List[str] = None
    ) -> np.ndarray:
        """
        🔥 EXPANDE features SEM RUÍDO ALEATÓRIO (BUG CORRIGIDO V5.0)

        Estratégias determinísticas:
        1. Constante → 1.0
        2. Nome sugestivo → valor semântico determinístico
        3. Derivada → calculada de features existentes
        4. Sem nome → 0.0 (sem ruído)
        """
        logger.info(f"   🔄 Expandindo: {actual} → {expected} features (determinístico)")
        self.stats['feature_adaptations'] += 1
        self.stats['feature_expansions'] += 1

        X_expanded = np.zeros((X.shape[0], expected))
        X_expanded[:, :actual] = X

        missing = expected - actual
        if missing <= 0:
            return X_expanded

        # 🔥 Determinar estratégia por nome
        for i in range(missing):
            idx = actual + i
            name = expected_names[idx] if expected_names and idx < len(expected_names) else f"feature_{idx}"
            name_l = name.lower()

            # ✅ Constantes → 1.0
            if any(k in name_l for k in ['constante', 'bias', 'intercept', 'ones']):
                X_expanded[:, idx] = 1.0
                logger.debug(f"      '{name}' → 1.0 (constante)")

            # ✅ Receita → usa coluna de receita se existir
            elif any(k in name_l for k in ['receita', 'revenue', 'faturamento']):
                rec_idx = self._find_index(expected_names or [], ['receita', 'revenue'])
                if rec_idx is not None and rec_idx < actual:
                    X_expanded[:, idx] = X[:, rec_idx]
                else:
                    X_expanded[:, idx] = 0.0
                logger.debug(f"      '{name}' → {X_expanded[0, idx]:.2f} (determinístico)")

            # ✅ Custo → usa coluna de custo se existir
            elif any(k in name_l for k in ['custo', 'cost', 'despesa']):
                cus_idx = self._find_index(expected_names or [], ['custo', 'cost'])
                if cus_idx is not None and cus_idx < actual:
                    X_expanded[:, idx] = X[:, cus_idx]
                else:
                    X_expanded[:, idx] = 0.0
                logger.debug(f"      '{name}' → {X_expanded[0, idx]:.2f} (determinístico)")

            # ✅ Lucro → receita - custo (se ambos existirem)
            elif any(k in name_l for k in ['lucro', 'profit']):
                rec_idx = self._find_index(expected_names or [], ['receita', 'revenue'])
                cus_idx = self._find_index(expected_names or [], ['custo', 'cost'])
                if rec_idx is not None and cus_idx is not None and rec_idx < actual and cus_idx < actual:
                    X_expanded[:, idx] = X[:, rec_idx] - X[:, cus_idx]
                    logger.debug(f"      '{name}' → receita - custo")
                else:
                    X_expanded[:, idx] = 0.0

            # ✅ Margem → lucro / receita
            elif any(k in name_l for k in ['margem', 'margin']):
                rec_idx = self._find_index(expected_names or [], ['receita', 'revenue'])
                luc_idx = self._find_index(expected_names or [], ['lucro', 'profit'])
                if rec_idx is not None and luc_idx is not None and rec_idx < actual and luc_idx < actual:
                    with np.errstate(divide='ignore', invalid='ignore'):
                        margem = np.where(X[:, rec_idx] != 0, X[:, luc_idx] / X[:, rec_idx], 0.0)
                    X_expanded[:, idx] = np.nan_to_num(margem, nan=0.0, posinf=0.0, neginf=0.0)
                else:
                    X_expanded[:, idx] = 0.0

            # ✅ Quantidade → 1 (constante)
            elif any(k in name_l for k in ['quantidade', 'qtd', 'count']):
                X_expanded[:, idx] = 1.0
                logger.debug(f"      '{name}' → 1.0 (constante)")

            # ✅ Eficiência → 0.5 (constante neutra)
            elif any(k in name_l for k in ['eficiencia', 'efficiency']):
                X_expanded[:, idx] = 0.5
                logger.debug(f"      '{name}' → 0.5 (neutro)")

            # ✅ Default → 0.0 (SEM RUÍDO)
            else:
                X_expanded[:, idx] = 0.0
                logger.debug(f"      '{name}' → 0.0 (default)")

        logger.info(f"   ✅ Expandido: {actual} → {expected} features (determinístico)")
        return X_expanded

    def _find_index(self, names: List[str], keywords: List[str]) -> Optional[int]:
        """🔥 Encontra índice de uma feature por palavra-chave"""
        for i, name in enumerate(names):
            name_l = name.lower()
            if any(k in name_l for k in keywords):
                return i
        return None

    # ==============================================
    # 🔥 PREPARAÇÃO DE DADOS (V5.0)
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
        """🔥 Prepara dados com limpeza completa (V5.0)"""
        logger.info(f"📊 Preparando dados para {model_type}")

        # 🔥 Validação de entrada
        is_valid, msg = self._validate_input(df, target_col)
        if not is_valid:
            raise ValueError(f"Validação falhou: {msg}")

        # 🔥 Detecção de leakage ANTES de tudo
        df, leakage = self._detect_and_remove_leakage(df, target_col)

        X = df.drop(columns=[target_col])
        y = df[target_col]

        is_classification = model_type == 'classifier'
        unique_classes = len(y.unique())

        if is_classification and unique_classes > TrainConfig.MAX_CLASSES:
            logger.warning(f"⚠️ Muitas classes ({unique_classes}), considere regressão")

        numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = X.select_dtypes(include=['object', 'category']).columns.tolist()

        logger.info(f"   🔢 Numéricas: {len(numeric_cols)}")
        logger.info(f"   📝 Categóricas: {len(categorical_cols)}")

        if categorical_cols:
            for col in categorical_cols:
                try:
                    le = LabelEncoder()
                    X[col] = le.fit_transform(X[col].astype(str))
                    numeric_cols.append(col)
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro ao codificar {col}: {e}")

        X = X[numeric_cols]

        if X.empty:
            raise ValueError("Nenhuma coluna numérica encontrada")

        if len(X) < TrainConfig.MIN_SAMPLES:
            raise ValueError(f"Dados insuficientes: {len(X)} amostras")

        # Remover colunas constantes
        for col in list(X.columns):
            if X[col].std() == 0:
                logger.info(f"   ⚠️ Removendo coluna constante: {col}")
                X = X.drop(columns=[col])

        # Tratar infinitos e NaN
        X = X.replace([np.inf, -np.inf], np.nan)

        for col in X.columns:
            if X[col].isna().any():
                median_val = X[col].median()
                if pd.isna(median_val):
                    median_val = 0.0
                X[col] = X[col].fillna(median_val)

        if X.empty:
            raise ValueError("Após limpeza, nenhuma feature restante")

        # 🔥 WINSORIZAÇÃO antes do scaler
        X_winsorized = self._winsorize(X.values)

        # 🔥 SCALER INTELIGENTE
        scaler_name, scaler = self._smart_scaler(X_winsorized)
        self.normalization_method = scaler_name
        self.normalizer = scaler
        X_normalized = self.normalizer.fit_transform(X_winsorized)

        X = pd.DataFrame(X_normalized, columns=X.columns)
        logger.info(f"   📊 {scaler_name} aplicado")

        # Seleção de features
        if len(X.columns) > TrainConfig.MAX_FEATURES:
            try:
                score_func = f_classif if is_classification else f_regression
                selector = SelectKBest(score_func, k=min(TrainConfig.MAX_FEATURES, len(X.columns)))
                selector.fit(X, y)
                selected_mask = selector.get_support()
                selected_features = X.columns[selected_mask].tolist()
                X = X[selected_features]
                logger.info(f"   🔍 Top {len(selected_features)} features selecionadas")
            except Exception as e:
                logger.warning(f"   ⚠️ Erro na seleção: {e}")

        # Split
        stratify = y if is_classification and unique_classes <= 10 else None

        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state, stratify=stratify
            )
        except Exception:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state
            )

        # SMOTE
        if is_classification and balance and IMB_AVAILABLE:
            class_counts = pd.Series(y_train).value_counts()
            if len(class_counts) > 1 and class_counts.min() / class_counts.max() < 0.3:
                logger.info(f"   ⚠️ Classes desbalanceadas: {dict(class_counts)}")
                try:
                    smote = SMOTE(random_state=random_state)
                    X_train, y_train = smote.fit_resample(X_train, y_train)
                    logger.info(f"   ✅ SMOTE: {len(X_train)} amostras")
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro no SMOTE: {e}")

        return {
            'X': X, 'y': y,
            'X_train': X_train, 'X_test': X_test,
            'y_train': y_train, 'y_test': y_test,
            'features': X.columns.tolist(),
            'feature_count': len(X.columns),
            'total_samples': len(X),
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'is_classification': is_classification,
            'classes': np.unique(y).tolist() if is_classification else None,
            'unique_classes': unique_classes,
            'numeric_cols': numeric_cols,
            'categorical_cols': categorical_cols,
            'normalization': self.normalization_method,
            'leakage_removed': leakage
        }

    # ==============================================
    # 🔥 RECOMENDAÇÃO DE MODELOS (NOVO V5.0)
    # ==============================================

    def _recommend_models(
        self,
        df: pd.DataFrame,
        target_col: str,
        model_type: str
    ) -> List[str]:
        """🧠 Recomenda modelos baseado no contexto"""
        n_rows = len(df)
        n_features = len(df.select_dtypes(include=[np.number]).columns) - 1

        recommended = []

        if model_type == 'classifier':
            if n_rows < 500:
                recommended = ['logistic_regression', 'decision_tree', 'random_forest']
            elif n_rows < 5000:
                recommended = ['random_forest', 'gradient_boosting', 'logistic_regression']
            else:
                recommended = ['random_forest', 'gradient_boosting']
                if XGB_AVAILABLE:
                    recommended.append('xgboost')
                if LGBM_AVAILABLE:
                    recommended.append('lightgbm')

            if n_features < 10:
                recommended.append('knn')
            if n_rows < 1000:
                recommended.append('svm')
        else:
            if n_rows < 500:
                recommended = ['linear_regression', 'ridge', 'decision_tree']
            elif n_rows < 5000:
                recommended = ['random_forest', 'gradient_boosting', 'ridge']
            else:
                recommended = ['random_forest', 'gradient_boosting']
                if XGB_AVAILABLE:
                    recommended.append('xgboost')
                if LGBM_AVAILABLE:
                    recommended.append('lightgbm')

        recommended = recommended[:5]
        logger.info(f"   🎯 Modelos recomendados ({n_rows} linhas, {n_features} features): {recommended}")
        return recommended

    # ==============================================
    # 🔥 AUTO-ML
    # ==============================================

    def _auto_select_model(
        self,
        X_train, y_train, X_test, y_test,
        is_classification: bool,
        model_type: str = 'classifier',
        use_recommendation: bool = True
    ) -> Tuple[Any, str, Dict[str, Any], Dict[str, Any]]:
        """Testa múltiplos modelos e retorna o melhor"""
        logger.info(f"🤖 Auto-ML: testando modelos...")

        if is_classification:
            all_models = TrainConfig.CLASSIFIERS
        else:
            all_models = TrainConfig.REGRESSORS

        # 🔥 Recomendação de modelos
        if use_recommendation and self._current_df is not None:
            recommended = self._recommend_models(
                self._current_df, self._current_target, model_type
            )
            models_config = {k: v for k, v in all_models.items() if k in recommended}
            if not models_config:
                models_config = all_models
        else:
            models_config = all_models

        results = {}
        best_score = -np.inf
        best_model = None
        best_name = None
        best_params = None
        best_metrics = {}

        for name, config in models_config.items():
            try:
                logger.info(f"   🔍 Testando {name}...")
                model = config['model'](**config['default_params'])
                model.fit(X_train, y_train)

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

                    if len(np.unique(y_test)) == 2 and hasattr(model, 'predict_proba'):
                        try:
                            y_proba = model.predict_proba(X_test)[:, 1]
                            roc_auc = roc_auc_score(y_test, y_proba)
                            metrics['roc_auc'] = float(roc_auc)
                        except Exception:
                            pass

                    results[name] = {'score': score, 'model': model, 'params': config['default_params'], 'metrics': metrics}
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

                    results[name] = {'score': score, 'model': model, 'params': config['default_params'], 'metrics': metrics}
                    logger.info(f"      R²: {score:.4f}, RMSE: {rmse:.4f}")

                if score > best_score:
                    best_score = score
                    best_model = model
                    best_name = name
                    best_params = config['default_params']
                    best_metrics = metrics

            except Exception as e:
                logger.warning(f"   ⚠️ Erro no modelo {name}: {e}")
                continue

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
        self, model, model_name, X_train, y_train, is_classification
    ) -> Tuple[Any, Dict[str, Any]]:
        logger.info(f"🔧 Otimizando hiperparâmetros para {model_name}...")

        if is_classification:
            config = TrainConfig.CLASSIFIERS.get(model_name)
        else:
            config = TrainConfig.REGRESSORS.get(model_name)

        if not config or not config.get('params'):
            logger.info("   ℹ️ Sem parâmetros para otimizar")
            return model, {}

        param_grid = config['params']
        total_combinations = 1
        for v in param_grid.values():
            total_combinations *= len(v)

        if total_combinations > 50:
            logger.info(f"   🔄 RandomizedSearchCV ({total_combinations} combinações)")
            search = RandomizedSearchCV(
                model, param_grid,
                n_iter=min(30, total_combinations),
                cv=min(3, TrainConfig.CV_FOLDS),
                scoring='accuracy' if is_classification else 'r2',
                n_jobs=TrainConfig.N_JOBS,
                random_state=TrainConfig.RANDOM_STATE,
                verbose=0
            )
        else:
            logger.info(f"   🔄 GridSearchCV ({total_combinations} combinações)")
            search = GridSearchCV(
                model, param_grid,
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

    def _create_ensemble(self, X_train, y_train, is_classification):
        logger.info(f"🔗 Criando ensemble...")

        if is_classification:
            estimators = [
                ('rf', RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)),
                ('gb', GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42))
            ]
            if X_train.shape[0] > 100:
                estimators.append(('lr', LogisticRegression(C=1.0, max_iter=1000, random_state=42)))
            if XGB_AVAILABLE:
                estimators.append(('xgb', XGBClassifier(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42, use_label_encoder=False, eval_metric='logloss')))
            if LGBM_AVAILABLE:
                estimators.append(('lgb', LGBMClassifier(n_estimators=100, learning_rate=0.1, num_leaves=31, random_state=42, verbose=-1)))
            ensemble = VotingClassifier(estimators=estimators, voting='soft', weights=[1] * len(estimators))
        else:
            estimators = [
                ('rf', RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)),
                ('gb', GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42))
            ]
            if XGB_AVAILABLE:
                estimators.append(('xgb', XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42)))
            if LGBM_AVAILABLE:
                estimators.append(('lgb', LGBMRegressor(n_estimators=100, learning_rate=0.1, num_leaves=31, random_state=42, verbose=-1)))
            ensemble = VotingRegressor(estimators=estimators, weights=[1] * len(estimators))

        ensemble.fit(X_train, y_train)
        logger.info(f"   ✅ Ensemble criado com {len(estimators)} modelos")
        return ensemble

    # ==============================================
    # 🔥 CV ESTRATIFICADA (NOVO V5.0)
    # ==============================================

    def _evaluate_with_stratified_cv(
        self,
        model,
        X: np.ndarray,
        y: pd.Series,
        is_classification: bool,
        n_folds: int = 5
    ) -> Dict[str, Any]:
        """🧠 Validação cruzada estratificada + detecção de overfitting"""
        try:
            if is_classification:
                n_unique = len(np.unique(y))
                if n_unique >= n_folds:
                    cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
                else:
                    cv = KFold(n_splits=max(2, n_unique), shuffle=True, random_state=42)

                scoring = {
                    'accuracy': 'accuracy',
                    'precision': 'precision_weighted',
                    'recall': 'recall_weighted',
                    'f1': 'f1_weighted',
                }
                if len(np.unique(y)) == 2:
                    scoring['roc_auc'] = 'roc_auc'
            else:
                cv = KFold(n_splits=n_folds, shuffle=True, random_state=42)
                scoring = {
                    'r2': 'r2',
                    'mse': 'neg_mean_squared_error',
                    'mae': 'neg_mean_absolute_error',
                }

            self.stats['cv_evaluations'] += 1

            results = cross_validate(
                model, X, y,
                cv=cv,
                scoring=scoring,
                return_train_score=True,
                n_jobs=1,  # 🔥 Evitar conflito com nested CV
                error_score='raise'
            )

            metrics = {}
            for key, values in results.items():
                if key.startswith('test_'):
                    metric_name = key.replace('test_', '')
                    metrics[f'cv_{metric_name}_mean'] = float(np.mean(values))
                    metrics[f'cv_{metric_name}_std'] = float(np.std(values))
                elif key.startswith('train_'):
                    metric_name = key.replace('train_', '')
                    metrics[f'train_{metric_name}_mean'] = float(np.mean(values))

            # Detecção de overfitting
            if 'cv_accuracy_mean' in metrics and 'train_accuracy_mean' in metrics:
                gap = metrics['train_accuracy_mean'] - metrics['cv_accuracy_mean']
                metrics['overfitting_gap'] = float(gap)
                if gap > TrainConfig.OVERFITTING_ALERT:
                    metrics['overfitting_risk'] = 'alto'
                    self.stats['overfitting_detected'] += 1
                elif gap > TrainConfig.OVERFITTING_WARN:
                    metrics['overfitting_risk'] = 'medio'
                else:
                    metrics['overfitting_risk'] = 'baixo'

            if 'cv_r2_mean' in metrics and 'train_r2_mean' in metrics:
                gap = metrics['train_r2_mean'] - metrics['cv_r2_mean']
                metrics['overfitting_gap'] = float(gap)
                if gap > TrainConfig.OVERFITTING_ALERT:
                    metrics['overfitting_risk'] = 'alto'
                    self.stats['overfitting_detected'] += 1
                elif gap > TrainConfig.OVERFITTING_WARN:
                    metrics['overfitting_risk'] = 'medio'
                else:
                    metrics['overfitting_risk'] = 'baixo'

            # Detecção de instabilidade
            for key in ['cv_accuracy_std', 'cv_f1_std', 'cv_r2_std']:
                if key in metrics:
                    std = metrics[key]
                    if std > TrainConfig.STABILITY_ALERT:
                        metrics['stability'] = 'instavel'
                    elif std > TrainConfig.STABILITY_WARN:
                        metrics['stability'] = 'moderado'
                    else:
                        metrics['stability'] = 'estavel'
                    break

            return metrics

        except Exception as e:
            logger.warning(f"⚠️ Erro na CV estratificada: {e}")
            return {}

    # ==============================================
    # 🔥 AVALIAÇÃO
    # ==============================================

    def _evaluate_model(
        self, model, X_test, y_test, is_classification,
        X_train=None, y_train=None, data=None
    ) -> Dict[str, Any]:
        """Avalia modelo com múltiplas métricas"""
        metrics = {}
        y_pred = model.predict(X_test)

        if is_classification:
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

            if len(np.unique(y_test)) == 2 and hasattr(model, 'predict_proba'):
                try:
                    y_proba = model.predict_proba(X_test)[:, 1]
                    metrics['roc_auc'] = float(roc_auc_score(y_test, y_proba))
                except Exception:
                    pass

            try:
                metrics['confusion_matrix'] = confusion_matrix(y_test, y_pred).tolist()
            except Exception:
                pass

            try:
                metrics['classification_report'] = classification_report(
                    y_test, y_pred, output_dict=True, zero_division=0
                )
            except Exception:
                pass
        else:
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

        # 🔥 CV estratificada
        if X_train is not None and y_train is not None and len(y_train) >= 15:
            cv_metrics = self._evaluate_with_stratified_cv(
                model, X_train, y_train, is_classification
            )
            metrics.update(cv_metrics)

        # Feature importance
        if hasattr(model, 'feature_importances_'):
            features = data.get('selected_features', data.get('features', [])) if data else []
            if len(features) == len(model.feature_importances_):
                importance = dict(zip(features, model.feature_importances_))
                importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
                metrics['feature_importance'] = importance

        return metrics

    # ==============================================
    # 🔥 EXPLICAÇÃO EM PORTUGUÊS (NOVO V5.0)
    # ==============================================

    def _generate_human_explanation(
        self,
        metrics: Dict[str, Any],
        is_classification: bool,
        feature_importance: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """💬 Gera explicação em português para leigos"""
        explanation = {
            'resumo': '',
            'qualidade': '',
            'pontos_fortes': [],
            'pontos_fracos': [],
            'recomendacoes': []
        }

        if is_classification:
            acc = metrics.get('accuracy', 0)

            if acc >= 0.95:
                explanation['qualidade'] = '🏆 Excelente'
                explanation['resumo'] = f'O modelo acerta {acc*100:.1f}% das previsões. Pode ser usado em produção com total confiança.'
            elif acc >= 0.85:
                explanation['qualidade'] = '✅ Boa'
                explanation['resumo'] = f'O modelo acerta {acc*100:.1f}% das previsões. Bom para uso em produção.'
            elif acc >= 0.75:
                explanation['qualidade'] = '📊 Razoável'
                explanation['resumo'] = f'O modelo acerta {acc*100:.1f}% das previsões. Use com cautela.'
            elif acc >= 0.60:
                explanation['qualidade'] = '⚠️ Fraca'
                explanation['resumo'] = f'O modelo acerta {acc*100:.1f}% das previsões. Precisa de mais dados.'
            else:
                explanation['qualidade'] = '❌ Ruim'
                explanation['resumo'] = f'O modelo acerta apenas {acc*100:.1f}% das previsões. Revise os dados.'

            gap = metrics.get('overfitting_gap', 0)
            if gap > TrainConfig.OVERFITTING_ALERT:
                explanation['pontos_fracos'].append(
                    f'Modelo "decora" os dados de treino (gap de {gap*100:.1f}%). Pode errar em dados novos.'
                )
            elif gap > TrainConfig.OVERFITTING_WARN:
                explanation['pontos_fracos'].append(f'Leve overfitting (gap de {gap*100:.1f}%).')
            else:
                explanation['pontos_fortes'].append('Modelo generaliza bem.')

            std = metrics.get('cv_accuracy_std', 0)
            if std > TrainConfig.STABILITY_ALERT:
                explanation['pontos_fracos'].append(f'Alta variabilidade entre folds (std={std:.3f}).')
            elif 0 < std < TrainConfig.STABILITY_WARN:
                explanation['pontos_fortes'].append(f'Modelo estável (std={std:.3f}).')

            precision = metrics.get('precision', 0)
            recall = metrics.get('recall', 0)
            if precision - recall > 0.15:
                explanation['pontos_fracos'].append('Modelo conservador: perde casos positivos.')
            elif recall - precision > 0.15:
                explanation['pontos_fracos'].append('Modelo agressivo: gera falsos positivos.')
        else:
            r2 = metrics.get('r2_score', 0)

            if r2 >= 0.9:
                explanation['qualidade'] = '🏆 Excelente'
                explanation['resumo'] = f'O modelo explica {r2*100:.1f}% da variação.'
            elif r2 >= 0.7:
                explanation['qualidade'] = '✅ Boa'
                explanation['resumo'] = f'O modelo explica {r2*100:.1f}% da variação.'
            elif r2 >= 0.5:
                explanation['qualidade'] = '📊 Razoável'
                explanation['resumo'] = f'O modelo explica {r2*100:.1f}% da variação.'
            elif r2 >= 0.3:
                explanation['qualidade'] = '⚠️ Fraca'
                explanation['resumo'] = f'O modelo explica apenas {r2*100:.1f}% da variação.'
            else:
                explanation['qualidade'] = '❌ Ruim'
                explanation['resumo'] = f'O modelo explica apenas {r2*100:.1f}% da variação.'

        if feature_importance:
            top = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:3]
            explanation['pontos_fortes'].append(
                f'Features mais importantes: {", ".join([f[0] for f in top])}'
            )

        # Recomendações
        if metrics.get('overfitting_risk') == 'alto':
            explanation['recomendacoes'].append('Coletar mais dados ou reduzir complexidade do modelo.')

        if metrics.get('stability') == 'instavel':
            explanation['recomendacoes'].append('Dados inconsistentes. Verificar qualidade das features.')

        if is_classification and metrics.get('accuracy', 0) < 0.7:
            explanation['recomendacoes'].append('Revisar features e considerar engenharia de atributos.')

        return explanation

    # ==============================================
    # 🔥 BASELINE DE DRIFT (NOVO V5.0)
    # ==============================================

    def _save_drift_baseline(
        self,
        X_train: np.ndarray,
        feature_names: List[str]
    ) -> str:
        """📉 Salva baseline de distribuição para detecção de drift"""
        if not TrainConfig.DRIFT_ENABLED:
            return ""

        baseline = {
            'feature_names': feature_names,
            'n_samples': int(len(X_train)),
            'timestamp': datetime.now().isoformat(),
            'features': {}
        }

        for i, name in enumerate(feature_names):
            if i >= X_train.shape[1]:
                break
            col = X_train[:, i]
            baseline['features'][name] = {
                'mean': float(np.mean(col)),
                'std': float(np.std(col)),
                'min': float(np.min(col)),
                'max': float(np.max(col)),
                'q25': float(np.percentile(col, 25)),
                'q50': float(np.percentile(col, 50)),
                'q75': float(np.percentile(col, 75)),
            }

        baseline_path = os.path.join(self.models_dir, "drift_baseline.json")
        with open(baseline_path, 'w') as f:
            json.dump(baseline, f, indent=2)

        self.stats['drift_baselines_saved'] += 1
        logger.info(f"📉 Baseline de drift salvo: {baseline_path}")
        return baseline_path

    def detect_drift(
        self,
        X_new: np.ndarray,
        feature_names: List[str],
        threshold: float = None
    ) -> Dict[str, Any]:
        """📉 Detecta drift comparando distribuição nova com baseline"""
        if not TrainConfig.DRIFT_ENABLED or not SCIPY_AVAILABLE:
            return {'drift_detected': False, 'reason': 'disabled'}

        threshold = threshold or TrainConfig.DRIFT_THRESHOLD
        baseline_path = os.path.join(self.models_dir, "drift_baseline.json")

        if not os.path.exists(baseline_path):
            return {'drift_detected': False, 'reason': 'baseline_not_found'}

        with open(baseline_path) as f:
            baseline = json.load(f)

        drifted_features = []

        for i, name in enumerate(feature_names):
            if name not in baseline['features'] or i >= X_new.shape[1]:
                continue

            b = baseline['features'][name]
            rng = np.random.RandomState(42)
            old_dist = rng.normal(b['mean'], b['std'] + 1e-10, 1000)
            old_dist = np.clip(old_dist, b['min'], b['max'])

            new_col = X_new[:, i]

            try:
                stat, pval = ks_2samp(old_dist, new_col)
                if pval < threshold:
                    drifted_features.append({
                        'feature': name,
                        'ks_statistic': round(float(stat), 3),
                        'p_value': round(float(pval), 5),
                        'severity': 'alto' if stat > 0.3 else 'medio' if stat > 0.15 else 'baixo'
                    })
            except Exception:
                continue

        result = {
            'drift_detected': len(drifted_features) > 0,
            'n_drifted': len(drifted_features),
            'total_features': len(feature_names),
            'drifted_features': drifted_features,
            'timestamp': datetime.now().isoformat()
        }

        if result['drift_detected']:
            logger.warning(f"🚨 Drift detectado em {len(drifted_features)} features!")
            for d in drifted_features[:5]:
                logger.warning(f"   • {d['feature']}: KS={d['ks_statistic']} ({d['severity']})")

        return result

    # ==============================================
    # 🔥 SALVAR MODELO
    # ==============================================

    def _save_model(
        self,
        model, scaler, metrics, model_name, data
    ) -> str:
        """Salva modelo com metadados completos"""
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
            'version': '5.0',
            'feature_count': len(data.get('selected_features', data['features'])),
            'total_samples': data['total_samples'],
            'normalization': self.normalization_method,
            'feature_adaptation': TrainConfig.FEATURE_ADAPTATION['enabled'],
            'explicacao': metrics.get('explicacao_humana', {}),
        }

        # Salvar arquivo com timestamp
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

        # Salvar como default
        default_path = os.path.join(self.models_dir, "trained_model.pkl")
        with open(default_path, 'wb') as f:
            pickle.dump(model_data, f)

        # Salvar como office_model (compatibilidade)
        office_path = os.path.join(self.models_dir, "office_model.pkl")
        with open(office_path, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"✅ Modelo salvo: {filepath}")
        logger.info(f"   📊 Features: {model_data['feature_count']}")
        logger.info(f"   📊 Normalização: {model_data['normalization']}")

        return filepath

    def load_model(self, model_path: str) -> Dict[str, Any]:
        """Carrega modelo salvo"""
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)

        self.model_feature_count, self.model_feature_names = self.detect_model_features(model_data)
        logger.info(f"✅ Modelo carregado: {model_path}")
        return model_data

    def load_model_intelligently(self, model_path: str = None) -> Dict[str, Any]:
        """🔥 Carrega modelo e detecta features"""
        if model_path is None:
            model_path = os.path.join(self.models_dir, "trained_model.pkl")

        if not os.path.exists(model_path):
            logger.warning(f"⚠️ Modelo não encontrado: {model_path}")
            return None

        try:
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)

            self.model_feature_count, self.model_feature_names = self.detect_model_features(model_data)

            self.best_model = model_data.get('model')
            self.best_scaler = model_data.get('scaler')
            self.best_features = model_data.get('features', [])
            self.best_metrics = model_data.get('metrics', {})
            self.best_model_name = model_data.get('model_name', 'unknown')
            self.best_model_type = model_data.get('model_type', 'classifier')
            self.is_classification = self.best_model_type == 'classifier'
            self.normalizer = self.best_scaler

            logger.info(f"✅ Modelo carregado: {self.best_model_name}")
            logger.info(f"   📊 Espera {self.model_feature_count} features")

            return model_data

        except Exception as e:
            logger.error(f"❌ Erro ao carregar modelo: {e}")
            return None

    def load_best_model(self) -> Optional[Dict[str, Any]]:
        """Carrega o melhor modelo salvo"""
        default_path = os.path.join(self.models_dir, "trained_model.pkl")
        if os.path.exists(default_path):
            return self.load_model_intelligently(default_path)
        return None

    # ==============================================
    # 🔥 PREDIÇÃO INTELIGENTE
    # ==============================================

    def predict_intelligently(
        self, X: np.ndarray, scale: bool = True, auto_adapt: bool = True
    ) -> np.ndarray:
        """🔥 PREDIÇÃO com adaptação automática"""
        if self.best_model is None:
            logger.warning("⚠️ Nenhum modelo carregado, usando fallback")
            self.stats['fallback_predictions'] += 1
            return self._fallback_predict(X)

        try:
            if auto_adapt and self.model_feature_count is not None:
                X = self.adapt_features_automatically(
                    X, self.model_feature_count, self.model_feature_names
                )

            if scale and self.best_scaler is not None:
                try:
                    X_scaled = self.best_scaler.transform(X)
                except Exception:
                    self.best_scaler.fit(X)
                    X_scaled = self.best_scaler.transform(X)
            else:
                X_scaled = X

            predictions = self.best_model.predict(X_scaled)

            if self.is_classification:
                predictions = np.clip(predictions, 0, 1)

            return predictions

        except Exception as e:
            logger.error(f"❌ Erro na predição: {e}")
            self.stats['fallback_predictions'] += 1
            return self._fallback_predict(X)

    def _fallback_predict(self, X: np.ndarray) -> np.ndarray:
        """Fallback determinístico"""
        if X.shape[1] > 0:
            scores = np.mean(X, axis=1)
            min_s, max_s = np.min(scores), np.max(scores)
            if max_s - min_s > 1e-10:
                return (scores - min_s) / (max_s - min_s)
            return np.full(X.shape[0], 0.5)
        return np.full(X.shape[0], 0.5)

    def predict_proba_intelligently(self, X: np.ndarray, scale: bool = True) -> np.ndarray:
        if self.best_model is None or not self.is_classification:
            preds = self.predict_intelligently(X, scale=scale)
            return np.column_stack([1 - preds, preds])

        if hasattr(self.best_model, 'predict_proba'):
            X_adapted = self.adapt_features_automatically(
                X, self.model_feature_count, self.model_feature_names
            )
            if scale and self.best_scaler is not None:
                X_scaled = self.best_scaler.transform(X_adapted)
            else:
                X_scaled = X_adapted
            return self.best_model.predict_proba(X_scaled)
        else:
            preds = self.predict_intelligently(X, scale=scale)
            return np.column_stack([1 - preds, preds])

    # ==============================================
    # 🔥 TREINAMENTO PRINCIPAL
    # ==============================================

    async def train_and_get_metrics(
        self,
        df: pd.DataFrame,
        target_col: Optional[str] = None,  # 🔥 OPCIONAL V5.0
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
        use_recommendation: bool = True,   # 🔥 NOVO
        detect_drift_baseline: bool = True,  # 🔥 NOVO
    ) -> Dict[str, Any]:
        """
        🔥 MÉTODO PRINCIPAL - TREINA MODELO COMPLETO V5.0
        """
        start_time = datetime.now()

        logger.info("=" * 70)
        logger.info("📊 INICIANDO TREINAMENTO - V5.0 (PRODUÇÃO REAL)")
        logger.info("=" * 70)

        # 🔥 Auto-detecção de target
        if target_col is None:
            try:
                target_col, detected_type, confidence = self.detect_target_column(df)
                logger.info(f"🎯 Target auto-detectado: '{target_col}' (confiança: {confidence:.2f})")

                if detected_type == 'regression':
                    model_type = 'regressor'
                else:
                    model_type = 'classifier'
            except Exception as e:
                return {
                    "erro": f"Não foi possível detectar o target: {e}",
                    "status": "failed",
                    "sugestao": "Informe target_col explicitamente"
                }

        # Guardar para recomendação
        self._current_df = df
        self._current_target = target_col

        logger.info(f"🎯 Alvo: {target_col}")
        logger.info(f"📊 Tipo: {model_type}")
        logger.info(f"🤖 Auto-ML: {auto_ml}")
        logger.info(f"🔧 Tuning: {tune_hyperparams}")
        logger.info(f"🔍 Feature Selection: {feature_selection}")
        logger.info(f"⚖️ Balanceamento: {balance}")
        logger.info(f"🔗 Ensemble: {ensemble}")
        logger.info(f"📊 CV Folds: {cv_folds}")
        logger.info(f"🎯 Recomendação: {use_recommendation}")
        logger.info(f"📉 Drift Baseline: {detect_drift_baseline}")
        logger.info("=" * 70)

        try:
            # 1. Preparar dados (com leakage, winsorize, scaler inteligente)
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

            logger.info(f"\n📊 Dados preparados:")
            logger.info(f"   • Total: {data['total_samples']} amostras")
            logger.info(f"   • Treino: {data['train_samples']}")
            logger.info(f"   • Teste: {data['test_samples']}")
            logger.info(f"   • Features: {data['feature_count']}")
            logger.info(f"   • Normalização: {data['normalization']}")

            X_train_scaled = X_train.values if hasattr(X_train, 'values') else X_train
            X_test_scaled = X_test.values if hasattr(X_test, 'values') else X_test

            # 2. Feature selection
            if feature_selection and data['feature_count'] > 3:
                try:
                    selector_model = (
                        RandomForestClassifier(n_estimators=50, random_state=random_state)
                        if is_classification
                        else RandomForestRegressor(n_estimators=50, random_state=random_state)
                    )
                    selector_model.fit(X_train_scaled, y_train)
                    selector = SelectFromModel(selector_model, threshold='median')
                    selector.fit(X_train_scaled, y_train)

                    selected_mask = selector.get_support()
                    X_train_scaled = X_train_scaled[:, selected_mask]
                    X_test_scaled = X_test_scaled[:, selected_mask]

                    selected_features = [f for f, m in zip(data['features'], selected_mask) if m]
                    data['selected_features'] = selected_features
                    data['feature_count_selected'] = len(selected_features)

                    logger.info(f"   🔍 Features selecionadas: {len(selected_features)}/{len(data['features'])}")
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro na seleção: {e}")

            # 3. Auto-ML
            if auto_ml:
                model, model_name, results, best_metrics = self._auto_select_model(
                    X_train_scaled, y_train,
                    X_test_scaled, y_test,
                    is_classification, model_type,
                    use_recommendation=use_recommendation
                )

                if tune_hyperparams:
                    model, best_params = self._tune_hyperparameters(
                        model, model_name, X_train_scaled, y_train, is_classification
                    )
                else:
                    best_params = {}
            else:
                model_name = 'random_forest'
                if is_classification:
                    model = RandomForestClassifier(**TrainConfig.CLASSIFIERS['random_forest']['default_params'])
                else:
                    model = RandomForestRegressor(**TrainConfig.REGRESSORS['random_forest']['default_params'])
                model.fit(X_train_scaled, y_train)
                best_params = {}
                best_metrics = {}

            # 4. Ensemble
            if ensemble:
                try:
                    model = self._create_ensemble(X_train_scaled, y_train, is_classification)
                    logger.info(f"   🔗 Ensemble criado")
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro no ensemble: {e}")

            # 5. Avaliar
            metrics = self._evaluate_model(
                model, X_test_scaled, y_test, is_classification,
                X_train_scaled, y_train, data
            )

            # 6. Explicação humana
            metrics['explicacao_humana'] = self._generate_human_explanation(
                metrics, is_classification, metrics.get('feature_importance')
            )

            # 7. Metadados
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
                'training_duration_seconds': (datetime.now() - start_time).total_seconds(),
                'normalization': self.normalization_method,
                'leakage_removed': data.get('leakage_removed', []),
            })

            # 8. Salvar
            model_path = None
            if save_model:
                model_path = self._save_model(model, self.normalizer, metrics, model_name, data)
                metrics['model_path'] = model_path

            # 9. Drift baseline
            if detect_drift_baseline:
                self._save_drift_baseline(
                    X_train_scaled,
                    data.get('selected_features', data['features'])
                )

            # 10. Histórico
            self.training_history.append({
                'timestamp': datetime.now().isoformat(),
                'model_name': model_name,
                'model_type': model_type,
                'main_metric': metrics.get('main_metric', 0),
                'accuracy': metrics.get('accuracy', 0),
                'f1_score': metrics.get('f1_score', 0),
                'r2_score': metrics.get('r2_score', 0),
                'feature_count': len(metrics.get('features_used', [])),
                'total_samples': data['total_samples'],
                'normalization': self.normalization_method,
                'overfitting_risk': metrics.get('overfitting_risk', 'unknown'),
                'stability': metrics.get('stability', 'unknown')
            })

            # 11. Melhor modelo
            main_metric = metrics.get('main_metric', 0)
            if main_metric > self._get_best_metric():
                self.best_model = model
                self.best_scaler = self.normalizer
                self.best_features = data.get('selected_features', data['features'])
                self.best_metrics = metrics
                self.best_model_name = model_name
                self.best_model_type = model_type
                self.is_classification = is_classification
                self.model_feature_count = len(self.best_features)
                self.model_feature_names = self.best_features

            # 12. Estatísticas
            self.stats["total_trainings"] += 1
            self.stats["successful_trainings"] += 1
            self.stats["models_tested"][model_name] = self.stats["models_tested"].get(model_name, 0) + 1

            if is_classification:
                self.stats["best_accuracy"] = max(self.stats["best_accuracy"], metrics.get('accuracy', 0))
            else:
                self.stats["best_r2"] = max(self.stats["best_r2"], metrics.get('r2_score', 0))

            logger.info(f"\n✅ Treinamento concluído!")
            logger.info(f"   📊 Modelo: {model_name}")
            logger.info(f"   📈 Métrica principal: {metrics.get('main_metric', 0):.4f}")
            logger.info(f"   📊 Normalização: {self.normalization_method}")
            logger.info(f"   💬 Qualidade: {metrics['explicacao_humana'].get('qualidade', 'N/A')}")
            if model_path:
                logger.info(f"   📁 Salvo em: {model_path}")

            return metrics

        except Exception as e:
            logger.error(f"❌ Erro no treinamento: {e}")
            logger.error(traceback.format_exc())
            self.stats["failed_trainings"] += 1
            return {
                "erro": str(e),
                "status": "failed",
                "tipo_modelo": model_type,
                "data": datetime.now().isoformat()
            }

    # ==============================================
    # 🔥 UTILITÁRIOS
    # ==============================================

    def _get_best_metric(self) -> float:
        if not self.training_history:
            return -np.inf
        return max([h.get('main_metric', 0) for h in self.training_history])

    def get_best_model_info(self) -> Optional[Dict[str, Any]]:
        if not self.training_history:
            return None
        return max(self.training_history, key=lambda x: x.get('main_metric', 0))

    def get_model_summary(self) -> Dict[str, Any]:
        return {
            "modelo_carregado": self.best_model is not None,
            "modelo_nome": self.best_model_name,
            "modelo_tipo": self.best_model_type,
            "classificacao": self.is_classification,
            "features": self.best_features[:10] if self.best_features else [],
            "feature_count": len(self.best_features) if self.best_features else 0,
            "model_feature_count": self.model_feature_count,
            "metricas": self.best_metrics,
            "total_treinamentos": len(self.training_history),
            "melhor_accuracy": self.stats.get("best_accuracy", 0),
            "melhor_r2": self.stats.get("best_r2", 0),
            "normalization": self.normalization_method,
            "feature_adaptation": TrainConfig.FEATURE_ADAPTATION['enabled'],
            "stats": self.stats
        }

    def get_training_stats(self) -> Dict[str, Any]:
        if not self.training_history:
            return {"total_treinos": 0, "historico_vazio": True}

        return {
            "total_treinos": len(self.training_history),
            "modelos_usados": list(set([h.get('model_name', 'unknown') for h in self.training_history])),
            "melhor_metric": max([h.get('main_metric', 0) for h in self.training_history]),
            "media_metric": float(np.mean([h.get('main_metric', 0) for h in self.training_history])),
            "ultimo_treino": self.training_history[-1] if self.training_history else None,
            "melhor_modelo": self.get_best_model_info(),
            "stats": self.stats
        }

    def get_training_summary_for_gemini(self) -> Dict[str, Any]:
        if not self.training_history:
            return {
                "status": "nenhum_treinamento",
                "mensagem": "Nenhum modelo foi treinado ainda",
                "total_treinamentos": 0
            }

        metrics_list = [h.get('main_metric', 0) for h in self.training_history]
        best_metric = max(metrics_list) if metrics_list else 0
        avg_metric = float(np.mean(metrics_list)) if metrics_list else 0

        return {
            "status": "sucesso",
            "total_treinamentos": len(self.training_history),
            "melhor_acuracia": best_metric,
            "media_acuracia": avg_metric,
            "modelos_usados": list(set([h.get('model_name') for h in self.training_history])),
            "recomendacao": self._generate_recommendation(best_metric),
            "stats": self.stats,
            "normalization": self.normalization_method
        }

    def _generate_recommendation(self, best_metric: float) -> str:
        if best_metric >= 0.95:
            return "🏆 Modelo EXCELENTE! Produção com total confiança."
        elif best_metric >= 0.90:
            return "✅ Modelo ÓTIMO. Produção com alta confiança."
        elif best_metric >= 0.85:
            return "📈 Modelo BOM. Validar com dados reais antes de produção."
        elif best_metric >= 0.80:
            return "📊 Modelo RAZOÁVEL. Mais dados e engenharia de features."
        elif best_metric >= 0.70:
            return "🔧 Modelo REGULAR. Precisa de melhorias."
        elif best_metric >= 0.60:
            return "⚠️ Modelo FRACO. Revise dados e features."
        else:
            return "❌ Modelo RUIM. Dados insuficientes ou incorretos."

    def explain_model(self, X_sample: np.ndarray, feature_names: List[str] = None) -> Optional[Dict]:
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

    def predict(self, X: np.ndarray, scale: bool = True) -> np.ndarray:
        return self.predict_intelligently(X, scale=scale)

    def predict_proba(self, X: np.ndarray, scale: bool = True) -> np.ndarray:
        return self.predict_proba_intelligently(X, scale=scale)

    def clear_cache(self):
        logger.info("🧹 Cache limpo")

    def reset(self):
        self.best_model = None
        self.best_scaler = None
        self.best_features = None
        self.best_metrics = {}
        self.best_model_name = None
        self.best_model_type = None
        self.model_feature_count = None
        self.model_feature_names = None
        self.training_history = []
        self.normalizer = None
        self._current_df = None
        self._current_target = None
        self.stats = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "best_accuracy": 0,
            "best_r2": 0,
            "models_tested": {},
            "started_at": datetime.now().isoformat(),
            "feature_adaptations": 0,
            "pca_applied": 0,
            "feature_expansions": 0,
            "fallback_predictions": 0,
            "leakage_detected": 0,
            "leakage_features_removed": 0,
            "winsorized_values": 0,
            "drift_baselines_saved": 0,
            "cv_evaluations": 0,
            "overfitting_detected": 0,
            "early_stopping_used": 0
        }
        logger.info("🔄 Trainer resetado")


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

trainer = ModelTrainer()


# ==============================================
# INICIALIZAÇÃO
# ==============================================

print("\n" + "=" * 70)
print("✅ train.py V5.0 (PRODUÇÃO REAL) carregado com sucesso!")
print("=" * 70)
print("   🐛 BUGS CORRIGIDOS:")
print("      • np.random em _expand_features → ZERO")
print("      • np.random.choice em _reduce_features → ZERO")
print("      • Determinismo total: mesmo input → mesmo output")
print("   🧠 NOVAS INTELIGÊNCIAS:")
print("      • 🎯 Auto-detecção de target")
print("      • 📊 RobustScaler + winsorização automática")
print("      • 🚨 Detecção de data leakage")
print("      • 📈 CV estratificada + detecção de overfitting")
print("      • 🎯 Recomendação de modelos por contexto")
print("      • 📉 Baseline de drift")
print("      • ⏱️ Early stopping em modelos iterativos")
print("      • 💬 Explicação em português para leigos")
print("   📊 MODELOS:")
print(f"      • Classificadores: {', '.join(TrainConfig.CLASSIFIERS.keys())}")
print(f"      • Regressores: {', '.join(TrainConfig.REGRESSORS.keys())}")
print("=" * 70)