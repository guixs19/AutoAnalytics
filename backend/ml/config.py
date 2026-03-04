# backend/ml/config.py
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.svm import SVC, SVR
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression
import numpy as np

class ModelConfig:
    """Configurações dos modelos para scikit-learn"""
    
    # Configurações gerais
    DEFAULT_INPUT_SHAPE = (10,)  # Mantido para compatibilidade
    DEFAULT_EPOCHS = 50  # Renomeado para n_estimators/iter no sklearn
    DEFAULT_BATCH_SIZE = 32  # Não aplicável diretamente no sklearn
    DEFAULT_LEARNING_RATE = 0.001  # Para modelos que suportam
    
    # Configurações por tipo de análise
    OFFICE_MODELS = {
        'clientes': {
            'type': 'binary',
            'model': 'random_forest',  # ou 'svm', 'mlp', 'logistic'
            'n_estimators': 100,
            'max_depth': 20,
            'min_samples_split': 5,
            'min_samples_leaf': 2,
            'random_state': 42
        },
        'servicos': {
            'type': 'multiclass',
            'model': 'mlp',
            'hidden_layer_sizes': (96, 48, 24),  # 3 layers com 96, 48, 24 unidades
            'activation': 'relu',
            'solver': 'adam',
            'alpha': 0.0001,
            'batch_size': 32,
            'learning_rate_init': 0.001,
            'max_iter': 80,
            'random_state': 42
        },
        'estoque': {
            'type': 'regression',
            'model': 'random_forest',
            'n_estimators': 120,
            'max_depth': 15,
            'min_samples_split': 4,
            'min_samples_leaf': 1,
            'random_state': 42
        },
        'financeiro': {
            'type': 'binary',
            'model': 'mlp',
            'hidden_layer_sizes': (256, 128, 64, 32, 16),  # 5 layers
            'activation': 'relu',
            'solver': 'adam',
            'alpha': 0.0001,
            'batch_size': 32,
            'learning_rate_init': 0.001,
            'max_iter': 150,
            'random_state': 42
        }
    }
    
    # Factory methods para criar modelos
    @staticmethod
    def get_model(model_type, task_type, config=None):
        """Factory method para criar modelos sklearn"""
        if task_type == 'binary':
            if model_type == 'random_forest':
                return RandomForestClassifier(**config if config else {})
            elif model_type == 'svm':
                return SVC(**config if config else {})
            elif model_type == 'mlp':
                return MLPClassifier(**config if config else {})
            elif model_type == 'logistic':
                return LogisticRegression(**config if config else {})
                
        elif task_type == 'multiclass':
            if model_type == 'random_forest':
                return RandomForestClassifier(**config if config else {})
            elif model_type == 'svm':
                return SVC(**config if config else {})
            elif model_type == 'mlp':
                return MLPClassifier(**config if config else {})
                
        elif task_type == 'regression':
            if model_type == 'random_forest':
                return RandomForestRegressor(**config if config else {})
            elif model_type == 'svm':
                return SVR(**config if config else {})
            elif model_type == 'mlp':
                return MLPRegressor(**config if config else {})
            elif model_type == 'linear':
                return LinearRegression(**config if config else {})
        
        raise ValueError(f"Unsupported model_type: {model_type} for task_type: {task_type}")
    
    # Callbacks adaptados para sklearn (usando funcionalidades similares)
    @staticmethod
    def get_callbacks(monitor='val_loss', patience=10):
        """
        Retorna configurações de callback adaptadas para sklearn.
        Em vez de callbacks reais, retorna configurações para validação e parada antecipada.
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
    
    # Método para obter configurações do modelo para um departamento específico
    @classmethod
    def get_office_model_config(cls, office_type):
        """Retorna configuração do modelo para um tipo de departamento"""
        return cls.OFFICE_MODELS.get(office_type, {})
    
    # Método para criar modelo específico do escritório
    @classmethod
    def create_office_model(cls, office_type):
        """Cria uma instância do modelo para um departamento específico"""
        config = cls.get_office_model_config(office_type)
        if not config:
            raise ValueError(f"Invalid office type: {office_type}")
        
        model_config = config.copy()
        model_config.pop('type', None)
        model_type = model_config.pop('model', 'random_forest')
        
        return cls.get_model(
            model_type=model_type,
            task_type=config['type'],
            config=model_config
        )