# backend/ml/train.py
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, mean_squared_error, r2_score
import joblib
import os
import asyncio
import warnings
warnings.filterwarnings('ignore')

from ml.model import MLModel
from config.settings import settings

class ModelTrainer:
    def __init__(self):
        self.model_manager = MLModel()
    
    async def prepare_office_data(self, file_path: str, analysis_type: str = 'clientes'):
        """
        Prepara dados específicos de oficina para treinamento
        """
        print(f"📊 Preparando dados de {analysis_type} para treinamento...")
        
        # Carregar dados
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, encoding='utf-8', errors='ignore')
        else:
            df = pd.read_excel(file_path)
        
        # Converter nomes para maiúsculas
        df.columns = [str(col).upper().strip() for col in df.columns]
        
        print(f"   Dados carregados: {df.shape[0]} linhas x {df.shape[1]} colunas")
        
        # Processar baseado no tipo de análise
        if analysis_type == 'clientes':
            X, y = self._prepare_client_data(df)
        elif analysis_type == 'servicos':
            X, y = self._prepare_service_data(df)
        elif analysis_type == 'financeiro':
            X, y = self._prepare_financial_data(df)
        else:
            X, y = self._prepare_general_data(df)
        
        print(f"   Features: {X.shape[1]}, Amostras: {X.shape[0]}")
        return X, y
    
    def _prepare_client_data(self, df: pd.DataFrame):
        """Prepara dados de clientes"""
        feature_columns = []
        
        numeric_candidates = ['VALOR', 'TOTAL', 'GASTO', 'COMPRA', 'FREQUENCIA', 
                             'TICKET_MEDIO', 'ULTIMA_COMPRA', 'DIAS_ATRASO']
        
        for col in df.columns:
            col_upper = str(col).upper()
            if any(candidate in col_upper for candidate in numeric_candidates):
                if pd.api.types.is_numeric_dtype(df[col]):
                    feature_columns.append(col)
        
        if not feature_columns:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
        
        feature_columns = feature_columns[:10]
        
        X = df[feature_columns].copy()
        X = X.fillna(X.mean())
        
        # Criar target fictício
        if len(X) > 0:
            y = (X.mean(axis=1) > X.mean(axis=1).median()).astype(int)
        else:
            y = np.zeros(len(X))
        
        return X.values, y.values
    
    def _prepare_service_data(self, df: pd.DataFrame):
        """Prepara dados de serviços"""
        feature_columns = []
        
        numeric_candidates = ['TEMPO', 'HORAS', 'MINUTOS', 'VALOR', 'CUSTO', 
                             'QUANTIDADE', 'PEÇAS', 'PECAS', 'DIFICULDADE']
        
        for col in df.columns:
            col_upper = str(col).upper()
            if any(candidate in col_upper for candidate in numeric_candidates):
                if pd.api.types.is_numeric_dtype(df[col]):
                    feature_columns.append(col)
        
        if not feature_columns:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
        
        feature_columns = feature_columns[:10]
        
        X = df[feature_columns].copy()
        X = X.fillna(X.mean())
        
        if len(X) > 0:
            y = (X.std(axis=1) > X.std(axis=1).median()).astype(int)
        else:
            y = np.zeros(len(X))
        
        return X.values, y.values
    
    def _prepare_financial_data(self, df: pd.DataFrame):
        """Prepara dados financeiros"""
        feature_columns = []
        
        numeric_candidates = ['LUCRO', 'RECEITA', 'DESPESA', 'CUSTO', 'INVESTIMENTO',
                             'MARGEM', 'RETORNO', 'FLUXO', 'CAIXA', 'FATURAMENTO']
        
        for col in df.columns:
            col_upper = str(col).upper()
            if any(candidate in col_upper for candidate in numeric_candidates):
                if pd.api.types.is_numeric_dtype(df[col]):
                    feature_columns.append(col)
        
        if not feature_columns:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
        
        feature_columns = feature_columns[:10]
        
        X = df[feature_columns].copy()
        X = X.fillna(X.mean())
        
        if len(X) > 0:
            y = (X.sum(axis=1) > X.sum(axis=1).median()).astype(int)
        else:
            y = np.zeros(len(X))
        
        return X.values, y.values
    
    def _prepare_general_data(self, df: pd.DataFrame):
        """Prepara dados gerais"""
        X = df.select_dtypes(include=[np.number])
        
        if X.empty:
            X = pd.DataFrame(np.random.randn(len(df), 10))
        
        X = X.fillna(X.mean())
        
        y = np.random.randint(0, 2, len(X))
        
        return X.values, y
    
    async def train_model(self, X: np.ndarray, y: np.ndarray, 
                         model_type: str = 'binary', 
                         analysis_type: str = 'clientes',
                         epochs: int = 50) -> dict:  # epochs mantido para compatibilidade
        """
        Treina o modelo sklearn com os dados fornecidos
        """
        print(f"🏁 Iniciando treinamento sklearn para {analysis_type}...")
        
        if len(X) < 20:
            print(f"⚠️  Poucos dados ({len(X)} amostras). Usando configuração simplificada.")
        
        # Dividir dados
        if len(X) > 10:
            test_size = 0.2 if len(X) > 50 else 0.3
            stratify = y if len(np.unique(y)) > 1 else None
            
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42, stratify=stratify
            )
        else:
            X_train, y_train = X, y
            X_test, y_test = X, y
        
        # Normalizar
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test) if len(X_test) > 0 else X_train_scaled
        
        # Salvar scaler
        scaler_path = os.path.join(settings.MODELS_DIR, f"scaler_{analysis_type}.pkl")
        os.makedirs(settings.MODELS_DIR, exist_ok=True)
        joblib.dump(scaler, scaler_path)
        
        # Definir input shape (mantido para compatibilidade)
        input_shape = (X_train.shape[1],)
        self.model_manager.input_shape = input_shape
        
        print(f"   Input shape: {input_shape}")
        print(f"   Treino: {X_train.shape}, Teste: {X_test.shape}")
        
        # Criar modelo sklearn apropriado
        model = self.model_manager.create_sklearn_model(
            task_type=model_type,
            module_name=analysis_type
        )
        
        # Treinar modelo sklearn
        print(f"   Treinando modelo: {type(model).__name__}...")
        
        # Hiperparâmetros específicos baseados no tipo de análise
        if analysis_type == 'clientes':
            model.n_estimators = 100
            model.max_depth = 20
        elif analysis_type == 'financeiro':
            if hasattr(model, 'max_iter'):
                model.max_iter = 150
            if hasattr(model, 'hidden_layer_sizes'):
                model.hidden_layer_sizes = (256, 128, 64, 32, 16)
        elif analysis_type == 'servicos':
            if hasattr(model, 'max_iter'):
                model.max_iter = 80
            if hasattr(model, 'hidden_layer_sizes'):
                model.hidden_layer_sizes = (96, 48, 24)
        
        # Treinar
        model.fit(X_train_scaled, y_train)
        
        # Avaliar
        metrics = {}
        if len(X_test) > 0:
            y_pred = model.predict(X_test_scaled)
            
            if model_type in ['binary', 'multiclass']:
                metrics = {
                    'accuracy': accuracy_score(y_test, y_pred),
                    'precision': precision_score(y_test, y_pred, average='weighted', zero_division=0),
                    'recall': recall_score(y_test, y_pred, average='weighted', zero_division=0),
                    'f1_score': f1_score(y_test, y_pred, average='weighted', zero_division=0)
                }
            else:  # regression
                metrics = {
                    'mse': mean_squared_error(y_test, y_pred),
                    'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
                    'r2': r2_score(y_test, y_pred)
                }
        else:
            metrics = {'accuracy': 0.5}  # Valor dummy
        
        # Salvar modelo
        model_path = os.path.join(settings.MODELS_DIR, f"model_{analysis_type}.pkl")
        joblib.dump(model, model_path)
        
        print(f"✅ Modelo treinado e salvo em: {model_path}")
        print(f"📊 Métricas finais: {metrics}")
        
        return {
            'history': {'loss': [], 'val_loss': []},  # Mantido para compatibilidade
            'metrics': metrics,
            'model_path': model_path,
            'scaler_path': scaler_path,
            'input_shape': input_shape,
            'model_type': type(model).__name__
        }
    
    async def train_with_cross_validation(self, X: np.ndarray, y: np.ndarray,
                                         model_type: str = 'binary',
                                         analysis_type: str = 'clientes'):
        """
        Treina modelo com validação cruzada (específico sklearn)
        """
        print(f"🏁 Iniciando treinamento com validação cruzada para {analysis_type}...")
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = self.model_manager.create_sklearn_model(
            task_type=model_type,
            module_name=analysis_type
        )
        
        # Validação cruzada
        cv_scores = cross_val_score(model, X_scaled, y, cv=min(5, len(X)), scoring='accuracy')
        
        # Treinar modelo final
        model.fit(X_scaled, y)
        
        # Salvar
        os.makedirs(settings.MODELS_DIR, exist_ok=True)
        model_path = os.path.join(settings.MODELS_DIR, f"model_{analysis_type}_cv.pkl")
        scaler_path = os.path.join(settings.MODELS_DIR, f"scaler_{analysis_type}.pkl")
        
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)
        
        print(f"✅ Modelo treinado com validação cruzada")
        print(f"📊 CV Scores: {cv_scores}")
        print(f"   Média CV: {cv_scores.mean():.4f} (+/- {cv_scores.std() * 2:.4f})")
        
        return {
            'model_path': model_path,
            'scaler_path': scaler_path,
            'cv_scores': cv_scores,
            'mean_cv_score': cv_scores.mean()
        }
    
    async def train_office_model_with_placeholder(self, analysis_type: str = 'clientes'):
        """
        Treina um modelo placeholder quando não há dados suficientes
        """
        print(f"🎭 Treinando modelo placeholder sklearn para {analysis_type}...")
        
        # Definir shape padrão baseado no tipo
        if analysis_type == 'financeiro':
            input_shape = (8,)
        elif analysis_type == 'servicos':
            input_shape = (6,)
        elif analysis_type == 'estoque':
            input_shape = (5,)
        else:  # clientes
            input_shape = (10,)
        
        self.model_manager.input_shape = input_shape
        
        # Criar modelo placeholder
        model = self.model_manager.create_sklearn_placeholder_model(
            task_type='binary',
            module_name=analysis_type
        )
        
        # Criar dados dummy para treinar placeholder
        X_dummy = np.random.randn(100, input_shape[0])
        
        if analysis_type == 'estoque':
            y_dummy = np.random.randn(100)  # regressão
        else:
            y_dummy = np.random.randint(0, 2, 100)  # classificação
        
        # Treinar placeholder
        model.fit(X_dummy, y_dummy)
        
        # Salvar modelo
        model_path = os.path.join(settings.MODELS_DIR, f"model_{analysis_type}.pkl")
        scaler_path = os.path.join(settings.MODELS_DIR, f"scaler_{analysis_type}.pkl")
        
        os.makedirs(settings.MODELS_DIR, exist_ok=True)
        joblib.dump(model, model_path)
        
        # Criar scaler placeholder
        dummy_scaler = StandardScaler()
        dummy_scaler.fit(X_dummy)
        joblib.dump(dummy_scaler, scaler_path)
        
        print(f"✅ Modelo placeholder treinado e salvo")
        print(f"   Modelo: {model_path}")
        print(f"   Scaler: {scaler_path}")
        
        return {
            'model_path': model_path,
            'scaler_path': scaler_path,
            'input_shape': input_shape,
            'is_placeholder': True,
            'model_type': type(model).__name__
        }
    
    async def ensure_trained_model(self, analysis_type: str = 'clientes', 
                                  data_file: str = None) -> dict:
        """
        Garante que existe um modelo treinado para o tipo de análise
        """
        model_path = os.path.join(settings.MODELS_DIR, f"model_{analysis_type}.pkl")
        
        # Verificar se modelo já existe
        if os.path.exists(model_path):
            print(f"✅ Modelo sklearn {analysis_type} já existe: {model_path}")
            return {
                'model_path': model_path,
                'scaler_path': os.path.join(settings.MODELS_DIR, f"scaler_{analysis_type}.pkl"),
                'exists': True,
                'is_placeholder': False
            }
        
        # Se tem arquivo de dados, tentar treinar com dados reais
        if data_file and os.path.exists(data_file):
            try:
                X, y = await self.prepare_office_data(data_file, analysis_type)
                
                if len(X) > 10:
                    result = await self.train_model(
                        X, y, 
                        model_type='binary',
                        analysis_type=analysis_type,
                        epochs=30
                    )
                    return {**result, 'exists': False, 'is_placeholder': False}
                
            except Exception as e:
                print(f"⚠️  Erro ao treinar com dados reais: {e}")
        
        # Se não conseguiu treinar com dados reais, criar placeholder
        print(f"📝 Criando modelo placeholder sklearn para {analysis_type}...")
        return await self.train_office_model_with_placeholder(analysis_type)