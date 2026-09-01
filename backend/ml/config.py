# backend/ml/config.py - VERSÃO 2.0 (INTEGRADO COM TRAIN V4.0 E PREDICT V7.0)
"""
Configurações dos modelos para scikit-learn
🔥 VERSÃO 2.0: Integrado com train.py V4.0 e predict.py V7.0
🔥 NORMALIZAÇÃO Z-SCORE (StandardScaler)
🔥 CONFIGURAÇÕES EXPANDIDAS
🔥 SUPORTE A ENSEMBLE E BOOSTING
"""

from sklearn.ensemble import (
    RandomForestClassifier, RandomForestRegressor,
    GradientBoostingClassifier, GradientBoostingRegressor,
    AdaBoostClassifier, AdaBoostRegressor,
    VotingClassifier, VotingRegressor,
    StackingClassifier, StackingRegressor
)
from sklearn.svm import SVC, SVR
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge, Lasso
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler
import numpy as np

print("🔧 Carregando config.py V2.0...")


class ModelConfig:
    """
    Configurações dos modelos para scikit-learn
    🔥 V2.0: Integrado com train.py V4.0 e predict.py V7.0
    """
    
    # ==============================================
    # CONFIGURAÇÕES GERAIS
    # ==============================================
    
    DEFAULT_INPUT_SHAPE = (10,)
    DEFAULT_EPOCHS = 50
    DEFAULT_BATCH_SIZE = 32
    DEFAULT_LEARNING_RATE = 0.001
    RANDOM_STATE = 42
    N_JOBS = -1
    
    # ==============================================
    # 🔥 NORMALIZAÇÃO (Z-SCORE)
    # ==============================================
    
    NORMALIZATION = {
        'default': 'standard',
        'standard': {
            'class': StandardScaler,
            'description': 'Z-Score: (x - mean) / std',
            'params': {}
        },
        'robust': {
            'class': RobustScaler,
            'description': 'Robusto: (x - median) / IQR',
            'params': {}
        },
        'minmax': {
            'class': MinMaxScaler,
            'description': 'Min-Max: (x - min) / (max - min)',
            'params': {'feature_range': (0, 1)}
        }
    }
    
    # ==============================================
    # 🔥 FEATURE ADAPTATION
    # ==============================================
    
    FEATURE_ADAPTATION = {
        'enabled': True,
        'max_features': 20,
        'min_features': 3,
        'use_pca': True,
        'use_importance': True,
        'fill_strategy': 'intelligent',  # intelligent, mean, zero, random
        'pca_variance': 0.95
    }
    
    # ==============================================
    # 🔥 MODELOS PARA CLASSIFICAÇÃO
    # ==============================================
    
    CLASSIFIERS = {
        'random_forest': {
            'model': RandomForestClassifier,
            'description': 'Random Forest com Z-Score',
            'params': {
                'n_estimators': [50, 100, 200, 300],
                'max_depth': [5, 10, 15, 20, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'max_features': ['sqrt', 'log2', None],
                'class_weight': ['balanced', 'balanced_subsample', None]
            },
            'default_params': {
                'n_estimators': 100,
                'max_depth': 10,
                'min_samples_split': 2,
                'min_samples_leaf': 1,
                'max_features': 'sqrt',
                'class_weight': 'balanced',
                'random_state': RANDOM_STATE,
                'n_jobs': N_JOBS
            }
        },
        'gradient_boosting': {
            'model': GradientBoostingClassifier,
            'description': 'Gradient Boosting com Z-Score',
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'max_depth': [3, 5, 7, 9],
                'min_samples_split': [2, 5],
                'subsample': [0.8, 0.9, 1.0],
                'max_features': ['sqrt', 'log2', None]
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'min_samples_split': 2,
                'subsample': 0.8,
                'max_features': 'sqrt',
                'random_state': RANDOM_STATE
            }
        },
        'adaboost': {
            'model': AdaBoostClassifier,
            'description': 'AdaBoost com Z-Score',
            'params': {
                'n_estimators': [50, 100, 200, 300],
                'learning_rate': [0.01, 0.05, 0.1, 0.5, 1.0],
                'algorithm': ['SAMME', 'SAMME.R']
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'algorithm': 'SAMME.R',
                'random_state': RANDOM_STATE
            }
        },
        'logistic_regression': {
            'model': LogisticRegression,
            'description': 'Regressão Logística com Z-Score',
            'params': {
                'C': [0.01, 0.1, 1.0, 10.0, 100.0],
                'penalty': ['l1', 'l2', 'elasticnet'],
                'solver': ['liblinear', 'saga'],
                'class_weight': ['balanced', None]
            },
            'default_params': {
                'C': 1.0,
                'penalty': 'l2',
                'solver': 'liblinear',
                'class_weight': 'balanced',
                'max_iter': 1000,
                'random_state': RANDOM_STATE,
                'n_jobs': N_JOBS
            }
        },
        'svm': {
            'model': SVC,
            'description': 'SVM com Z-Score',
            'params': {
                'C': [0.1, 1.0, 10.0, 100.0],
                'kernel': ['rbf', 'linear', 'poly', 'sigmoid'],
                'gamma': ['scale', 'auto'],
                'degree': [2, 3, 4],
                'class_weight': ['balanced', None]
            },
            'default_params': {
                'C': 1.0,
                'kernel': 'rbf',
                'gamma': 'scale',
                'class_weight': 'balanced',
                'probability': True,
                'random_state': RANDOM_STATE
            }
        },
        'decision_tree': {
            'model': DecisionTreeClassifier,
            'description': 'Árvore de Decisão com Z-Score',
            'params': {
                'max_depth': [3, 5, 7, 10, 15, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'criterion': ['gini', 'entropy', 'log_loss'],
                'class_weight': ['balanced', None]
            },
            'default_params': {
                'max_depth': 10,
                'min_samples_split': 2,
                'min_samples_leaf': 1,
                'criterion': 'gini',
                'class_weight': 'balanced',
                'random_state': RANDOM_STATE
            }
        },
        'knn': {
            'model': KNeighborsClassifier,
            'description': 'K-Nearest Neighbors com Z-Score',
            'params': {
                'n_neighbors': [3, 5, 7, 11, 15, 21],
                'weights': ['uniform', 'distance'],
                'p': [1, 2],
                'metric': ['euclidean', 'manhattan', 'minkowski']
            },
            'default_params': {
                'n_neighbors': 5,
                'weights': 'uniform',
                'p': 2,
                'metric': 'minkowski',
                'n_jobs': N_JOBS
            }
        }
    }
    
    # ==============================================
    # 🔥 MODELOS PARA REGRESSÃO
    # ==============================================
    
    REGRESSORS = {
        'random_forest': {
            'model': RandomForestRegressor,
            'description': 'Random Forest Regressor com Z-Score',
            'params': {
                'n_estimators': [50, 100, 200, 300],
                'max_depth': [5, 10, 15, 20, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'max_features': ['sqrt', 'log2', None]
            },
            'default_params': {
                'n_estimators': 100,
                'max_depth': 10,
                'min_samples_split': 2,
                'min_samples_leaf': 1,
                'max_features': 'sqrt',
                'random_state': RANDOM_STATE,
                'n_jobs': N_JOBS
            }
        },
        'gradient_boosting': {
            'model': GradientBoostingRegressor,
            'description': 'Gradient Boosting Regressor com Z-Score',
            'params': {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.05, 0.1, 0.2],
                'max_depth': [3, 5, 7, 9],
                'min_samples_split': [2, 5],
                'subsample': [0.8, 0.9, 1.0],
                'max_features': ['sqrt', 'log2', None],
                'loss': ['squared_error', 'absolute_error', 'huber']
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'min_samples_split': 2,
                'subsample': 0.8,
                'max_features': 'sqrt',
                'loss': 'squared_error',
                'random_state': RANDOM_STATE
            }
        },
        'adaboost': {
            'model': AdaBoostRegressor,
            'description': 'AdaBoost Regressor com Z-Score',
            'params': {
                'n_estimators': [50, 100, 200, 300],
                'learning_rate': [0.01, 0.05, 0.1, 0.5, 1.0],
                'loss': ['linear', 'square', 'exponential']
            },
            'default_params': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'loss': 'linear',
                'random_state': RANDOM_STATE
            }
        },
        'linear_regression': {
            'model': LinearRegression,
            'description': 'Regressão Linear com Z-Score',
            'params': {},
            'default_params': {
                'n_jobs': N_JOBS
            }
        },
        'ridge': {
            'model': Ridge,
            'description': 'Ridge Regression com Z-Score',
            'params': {
                'alpha': [0.01, 0.1, 1.0, 10.0, 100.0],
                'solver': ['auto', 'svd', 'cholesky', 'lsqr', 'sparse_cg', 'sag', 'saga']
            },
            'default_params': {
                'alpha': 1.0,
                'solver': 'auto',
                'random_state': RANDOM_STATE
            }
        },
        'lasso': {
            'model': Lasso,
            'description': 'Lasso Regression com Z-Score',
            'params': {
                'alpha': [0.01, 0.1, 1.0, 10.0],
                'selection': ['cyclic', 'random']
            },
            'default_params': {
                'alpha': 1.0,
                'selection': 'cyclic',
                'random_state': RANDOM_STATE,
                'max_iter': 1000
            }
        },
        'svm': {
            'model': SVR,
            'description': 'SVM Regressor com Z-Score',
            'params': {
                'C': [0.1, 1.0, 10.0, 100.0],
                'kernel': ['rbf', 'linear', 'poly', 'sigmoid'],
                'gamma': ['scale', 'auto'],
                'degree': [2, 3, 4],
                'epsilon': [0.01, 0.1, 0.5, 1.0]
            },
            'default_params': {
                'C': 1.0,
                'kernel': 'rbf',
                'gamma': 'scale',
                'epsilon': 0.1
            }
        },
        'decision_tree': {
            'model': DecisionTreeRegressor,
            'description': 'Árvore de Decisão Regressor com Z-Score',
            'params': {
                'max_depth': [3, 5, 7, 10, 15, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'criterion': ['squared_error', 'friedman_mse', 'absolute_error', 'poisson']
            },
            'default_params': {
                'max_depth': 10,
                'min_samples_split': 2,
                'min_samples_leaf': 1,
                'criterion': 'squared_error',
                'random_state': RANDOM_STATE
            }
        },
        'knn': {
            'model': KNeighborsRegressor,
            'description': 'K-Nearest Neighbors Regressor com Z-Score',
            'params': {
                'n_neighbors': [3, 5, 7, 11, 15, 21],
                'weights': ['uniform', 'distance'],
                'p': [1, 2],
                'metric': ['euclidean', 'manhattan', 'minkowski']
            },
            'default_params': {
                'n_neighbors': 5,
                'weights': 'uniform',
                'p': 2,
                'metric': 'minkowski',
                'n_jobs': N_JOBS
            }
        }
    }
    
    # ==============================================
    # 🔥 CONFIGURAÇÕES POR TIPO DE ANÁLISE
    # ==============================================
    
    OFFICE_MODELS = {
        'clientes': {
            'type': 'binary',
            'model': 'random_forest',
            'description': 'Análise de clientes (classificação binária)',
            'n_estimators': 100,
            'max_depth': 20,
            'min_samples_split': 5,
            'min_samples_leaf': 2,
            'class_weight': 'balanced',
            'random_state': RANDOM_STATE,
            'normalization': 'standard'
        },
        'servicos': {
            'type': 'multiclass',
            'model': 'gradient_boosting',
            'description': 'Análise de serviços (multiclasse)',
            'n_estimators': 100,
            'learning_rate': 0.1,
            'max_depth': 5,
            'subsample': 0.8,
            'random_state': RANDOM_STATE,
            'normalization': 'standard'
        },
        'estoque': {
            'type': 'regression',
            'model': 'random_forest',
            'description': 'Análise de estoque (regressão)',
            'n_estimators': 120,
            'max_depth': 15,
            'min_samples_split': 4,
            'min_samples_leaf': 1,
            'random_state': RANDOM_STATE,
            'normalization': 'standard'
        },
        'financeiro': {
            'type': 'binary',
            'model': 'gradient_boosting',
            'description': 'Análise financeira (classificação binária)',
            'n_estimators': 150,
            'learning_rate': 0.05,
            'max_depth': 7,
            'subsample': 0.8,
            'class_weight': 'balanced',
            'random_state': RANDOM_STATE,
            'normalization': 'standard'
        },
        'geral': {
            'type': 'binary',
            'model': 'random_forest',
            'description': 'Análise geral (classificação binária)',
            'n_estimators': 100,
            'max_depth': 10,
            'min_samples_split': 2,
            'min_samples_leaf': 1,
            'class_weight': 'balanced',
            'random_state': RANDOM_STATE,
            'normalization': 'standard'
        }
    }
    
    # ==============================================
    # 🔥 MÉTRICAS E AVALIAÇÃO
    # ==============================================
    
    METRICS = {
        'classification': {
            'primary': 'accuracy',
            'secondary': ['precision', 'recall', 'f1_score', 'roc_auc'],
            'scoring': 'accuracy'
        },
        'regression': {
            'primary': 'r2_score',
            'secondary': ['mse', 'rmse', 'mae'],
            'scoring': 'r2'
        }
    }
    
    # ==============================================
    # 🔥 VALIDAÇÃO CRUZADA
    # ==============================================
    
    CV = {
        'folds': 5,
        'shuffle': True,
        'random_state': RANDOM_STATE,
        'stratify': True
    }
    
    # ==============================================
    # 🔥 FACTORY METHODS
    # ==============================================
    
    @staticmethod
    def get_model(model_type: str, task_type: str, config: dict = None) -> object:
        """
        Factory method para criar modelos sklearn
        🔥 Versão expandida com mais modelos
        """
        config = config or {}
        
        # Classificação binária
        if task_type == 'binary':
            if model_type == 'random_forest':
                return RandomForestClassifier(**config)
            elif model_type == 'gradient_boosting':
                return GradientBoostingClassifier(**config)
            elif model_type == 'adaboost':
                return AdaBoostClassifier(**config)
            elif model_type == 'svm':
                return SVC(**config)
            elif model_type == 'logistic':
                return LogisticRegression(**config)
            elif model_type == 'decision_tree':
                return DecisionTreeClassifier(**config)
            elif model_type == 'knn':
                return KNeighborsClassifier(**config)
            elif model_type == 'mlp':
                return MLPClassifier(**config)
        
        # Multiclasse
        elif task_type == 'multiclass':
            if model_type == 'random_forest':
                return RandomForestClassifier(**config)
            elif model_type == 'gradient_boosting':
                return GradientBoostingClassifier(**config)
            elif model_type == 'adaboost':
                return AdaBoostClassifier(**config)
            elif model_type == 'svm':
                return SVC(**config)
            elif model_type == 'logistic':
                return LogisticRegression(**config, multi_class='multinomial')
            elif model_type == 'mlp':
                return MLPClassifier(**config)
        
        # Regressão
        elif task_type == 'regression':
            if model_type == 'random_forest':
                return RandomForestRegressor(**config)
            elif model_type == 'gradient_boosting':
                return GradientBoostingRegressor(**config)
            elif model_type == 'adaboost':
                return AdaBoostRegressor(**config)
            elif model_type == 'svm':
                return SVR(**config)
            elif model_type == 'linear':
                return LinearRegression(**config)
            elif model_type == 'ridge':
                return Ridge(**config)
            elif model_type == 'lasso':
                return Lasso(**config)
            elif model_type == 'decision_tree':
                return DecisionTreeRegressor(**config)
            elif model_type == 'knn':
                return KNeighborsRegressor(**config)
            elif model_type == 'mlp':
                return MLPRegressor(**config)
        
        raise ValueError(f"Unsupported model_type: {model_type} for task_type: {task_type}")
    
    @staticmethod
    def get_ensemble_model(
        estimators: list,
        task_type: str = 'binary',
        voting: str = 'soft',
        weights: list = None
    ) -> object:
        """
        Cria modelo ensemble (VotingClassifier/Regressor)
        🔥 Suporte a ensembles com Z-Score
        """
        if task_type in ['binary', 'multiclass']:
            return VotingClassifier(
                estimators=estimators,
                voting=voting,
                weights=weights,
                n_jobs=ModelConfig.N_JOBS
            )
        elif task_type == 'regression':
            return VotingRegressor(
                estimators=estimators,
                weights=weights,
                n_jobs=ModelConfig.N_JOBS
            )
        else:
            raise ValueError(f"Unsupported task_type: {task_type}")
    
    @staticmethod
    def get_stacking_model(
        estimators: list,
        final_estimator: object = None,
        task_type: str = 'binary',
        cv: int = 5
    ) -> object:
        """
        Cria modelo Stacking (StackingClassifier/Regressor)
        🔥 Suporte a stacking com Z-Score
        """
        if final_estimator is None:
            if task_type in ['binary', 'multiclass']:
                final_estimator = LogisticRegression(
                    max_iter=1000,
                    random_state=ModelConfig.RANDOM_STATE,
                    n_jobs=ModelConfig.N_JOBS
                )
            else:
                final_estimator = Ridge(
                    random_state=ModelConfig.RANDOM_STATE
                )
        
        if task_type in ['binary', 'multiclass']:
            return StackingClassifier(
                estimators=estimators,
                final_estimator=final_estimator,
                cv=cv,
                n_jobs=ModelConfig.N_JOBS
            )
        elif task_type == 'regression':
            return StackingRegressor(
                estimators=estimators,
                final_estimator=final_estimator,
                cv=cv,
                n_jobs=ModelConfig.N_JOBS
            )
        else:
            raise ValueError(f"Unsupported task_type: {task_type}")
    
    @staticmethod
    def get_scaler(scaler_type: str = 'standard') -> object:
        """
        Retorna o scaler apropriado (Z-Score por padrão)
        """
        scaler_config = ModelConfig.NORMALIZATION.get(scaler_type, ModelConfig.NORMALIZATION['standard'])
        scaler_class = scaler_config['class']
        scaler_params = scaler_config.get('params', {})
        return scaler_class(**scaler_params)
    
    # ==============================================
    # 🔥 CALLBACKS (SKLEARN COMPATÍVEL)
    # ==============================================
    
    @staticmethod
    def get_callbacks(monitor: str = 'val_loss', patience: int = 10) -> dict:
        """
        Retorna configurações de callback adaptadas para sklearn
        """
        return {
            'early_stopping': {
                'enabled': True,
                'patience': patience,
                'monitor': monitor,
                'restore_best_weights': True
            },
            'model_checkpoint': {
                'enabled': True,
                'filepath': 'models/best_model.pkl',
                'monitor': monitor,
                'save_best_only': True
            },
            'learning_rate_schedule': {
                'enabled': True,
                'factor': 0.5,
                'patience': 5,
                'min_learning_rate': 0.00001
            }
        }
    
    # ==============================================
    # 🔥 MÉTODOS DE CONVENIÊNCIA
    # ==============================================
    
    @classmethod
    def get_office_model_config(cls, office_type: str) -> dict:
        """
        Retorna configuração do modelo para um tipo de departamento
        """
        return cls.OFFICE_MODELS.get(office_type, cls.OFFICE_MODELS['geral'])
    
    @classmethod
    def create_office_model(cls, office_type: str, **kwargs) -> object:
        """
        Cria uma instância do modelo para um departamento específico
        🔥 Com normalização Z-Score integrada
        """
        config = cls.get_office_model_config(office_type)
        if not config:
            raise ValueError(f"Invalid office type: {office_type}")
        
        # Extrair configurações
        model_config = config.copy()
        task_type = model_config.pop('type', 'binary')
        model_type = model_config.pop('model', 'random_forest')
        normalization = model_config.pop('normalization', 'standard')
        
        # Combinar com kwargs
        final_config = {**model_config, **kwargs}
        
        # Criar modelo
        model = cls.get_model(
            model_type=model_type,
            task_type=task_type,
            config=final_config
        )
        
        return {
            'model': model,
            'task_type': task_type,
            'model_type': model_type,
            'normalization': normalization,
            'config': final_config
        }
    
    @classmethod
    def get_classifier_list(cls) -> List[str]:
        """Retorna lista de classificadores disponíveis"""
        return list(cls.CLASSIFIERS.keys())
    
    @classmethod
    def get_regressor_list(cls) -> List[str]:
        """Retorna lista de regressores disponíveis"""
        return list(cls.REGRESSORS.keys())
    
    @classmethod
    def get_office_types(cls) -> List[str]:
        """Retorna lista de tipos de análise de oficina"""
        return list(cls.OFFICE_MODELS.keys())
    
    @classmethod
    def get_normalization_list(cls) -> List[str]:
        """Retorna lista de métodos de normalização disponíveis"""
        return list(cls.NORMALIZATION.keys())


# ==============================================
# 🔥 INSTÂNCIA GLOBAL PARA COMPATIBILIDADE
# ==============================================

config = ModelConfig()

print("\n" + "=" * 70)
print("✅ config.py V2.0 carregado com sucesso!")
print("=" * 70)
print("   📊 NORMALIZAÇÃO: Z-Score (StandardScaler)")
print("   🔥 INTEGRADO COM TRAIN.PY V4.0 E PREDICT.PY V7.0")
print("   📊 CLASSIFICADORES DISPONÍVEIS:")
print(f"      • {', '.join(ModelConfig.get_classifier_list())}")
print("   📊 REGRESSORES DISPONÍVEIS:")
print(f"      • {', '.join(ModelConfig.get_regressor_list())}")
print("   📊 TIPOS DE ANÁLISE:")
print(f"      • {', '.join(ModelConfig.get_office_types())}")
print("   📊 NORMALIZAÇÃO DISPONÍVEL:")
print(f"      • {', '.join(ModelConfig.get_normalization_list())}")
print("   🔧 MÉTODOS:")
print("      • config.get_model(model_type, task_type, config)")
print("      • config.create_office_model(office_type)")
print("      • config.get_ensemble_model(estimators, task_type)")
print("      • config.get_stacking_model(estimators, task_type)")
print("      • config.get_scaler(scaler_type)")
print("=" * 70)