# backend/preprocessing.py
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import (
    recall_score, 
    confusion_matrix, 
    classification_report,
    accuracy_score,
    precision_score,
    f1_score,
    roc_auc_score,
    roc_curve
)
import matplotlib
matplotlib.use('Agg')  # Para ambientes sem GUI
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
import warnings
import os
from datetime import datetime

warnings.filterwarnings('ignore')

class ModelTrainer:
    """
    Classe para treinamento de modelos de machine learning
    """
    def __init__(self):
        self.model = None
        self.scaler = None
        self.label_encoder = None
        self.scaler_type = 'standard'
        self.model_type = 'random_forest'
        self.metrics = {}
        self.feature_names = []
        self.class_names = []
        print("✅ ModelTrainer inicializado")
    
    # ========== MÉTODO PARA PROCESSAR ARQUIVOS (USADO PELO ROUTES.PY) ==========
    async def process_file(self, file_path: str) -> Dict[str, Any]:
        """
        Processa arquivo de dados (CSV/Excel) e retorna dados para análise
        Este método é usado pelo routes.py
        """
        try:
            print(f"📊 Processando arquivo: {file_path}")
            
            # Verificar se arquivo existe
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "message": "Arquivo não encontrado",
                    "metadata": {
                        "diagnostico": {
                            "status": "error",
                            "mensagem": "Arquivo não encontrado"
                        }
                    }
                }
            
            # Carregar dados
            if file_path.endswith('.csv'):
                try:
                    df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    df = pd.read_csv(file_path, encoding='latin1')
            else:
                df = pd.read_excel(file_path)
            
            # Informações básicas
            total_rows = len(df)
            total_cols = len(df.columns)
            
            # Separar colunas numéricas
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            df_numeric = df[numeric_cols].copy() if numeric_cols else pd.DataFrame()
            
            # Preencher valores nulos
            for col in df_numeric.columns:
                if df_numeric[col].isnull().any():
                    df_numeric[col].fillna(df_numeric[col].mean(), inplace=True)
            
            # Detectar colunas de oficina
            workshop_columns = self._detect_workshop_columns(df)
            
            # Metadados
            metadata = {
                "original": {
                    "linhas": total_rows,
                    "colunas": total_cols,
                    "colunas_nomes": df.columns.tolist()
                },
                "processamento": {
                    "colunas_numericas": numeric_cols,
                    "total_numericas": len(numeric_cols),
                    "colunas_oficina": workshop_columns
                },
                "diagnostico": {
                    "status": "success",
                    "mensagem": f"Processado: {total_rows} registros, {total_cols} colunas",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            print(f"✅ Arquivo processado: {total_rows} linhas, {len(numeric_cols)} colunas numéricas")
            
            return {
                "status": "success",
                "dataframe": df,
                "dataframe_numeric": df_numeric,
                "metadata": metadata
            }
            
        except Exception as e:
            print(f"❌ Erro no processamento: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": str(e),
                "metadata": {
                    "diagnostico": {
                        "status": "error",
                        "mensagem": str(e)
                    }
                }
            }
    
    def _detect_workshop_columns(self, df: pd.DataFrame) -> Dict[str, List[str]]:
        """Detecta colunas específicas de oficina mecânica"""
        workshop_columns = {
            "cliente": [],
            "veiculo": [],
            "servico": [],
            "peca": [],
            "valor": [],
            "data": []
        }
        
        keywords = {
            "cliente": ["cliente", "nome", "cpf", "cnpj", "telefone", "email", "endereço"],
            "veiculo": ["veiculo", "placa", "modelo", "marca", "ano", "chassi", "km", "quilometragem"],
            "servico": ["serviço", "servico", "descrição", "descricao", "observação", "observacao"],
            "peca": ["peça", "peca", "produto", "item", "material"],
            "valor": ["valor", "preço", "preco", "custo", "total", "desconto"],
            "data": ["data", "dia", "mês", "mes", "ano", "horário", "horario"]
        }
        
        for col in df.columns:
            col_lower = col.lower()
            for category, words in keywords.items():
                if any(word in col_lower for word in words):
                    workshop_columns[category].append(col)
                    break
        
        return workshop_columns
    
    # ========== MÉTODOS DE TREINAMENTO ==========
    async def prepare_data(self, 
                          df_numeric: pd.DataFrame,
                          target_column: Optional[str] = None,
                          test_size: float = 0.2,
                          scaler_type: str = 'standard',
                          random_state: int = 42) -> Dict[str, Any]:
        """
        Prepara dados para treinamento com scaling
        """
        print("\n📊 PREPARANDO DADOS PARA TREINAMENTO...")
        
        if df_numeric.empty:
            return {"error": "DataFrame numérico vazio"}
        
        result = {
            "status": "success",
            "message": "",
            "X_train": None,
            "X_test": None,
            "y_train": None,
            "y_test": None,
            "feature_names": [],
            "class_names": [],
            "scaler_info": {}
        }
        
        try:
            # Separar features e target
            if target_column and target_column in df_numeric.columns:
                X = df_numeric.drop(columns=[target_column])
                y = df_numeric[target_column]
                print(f"✅ Usando '{target_column}' como coluna alvo")
            else:
                print("⚠️  Nenhuma coluna alvo especificada. Usando última coluna...")
                X = df_numeric.iloc[:, :-1]
                y = df_numeric.iloc[:, -1]
                target_column = df_numeric.columns[-1]
                print(f"✅ Usando '{target_column}' como coluna alvo")
            
            # Guardar nomes das features
            self.feature_names = X.columns.tolist()
            result["feature_names"] = self.feature_names
            
            # Verificar e tratar valores ausentes
            if X.isnull().sum().sum() > 0:
                print("⚠️  Valores ausentes encontrados. Preenchendo com mediana...")
                X = X.fillna(X.median())
            
            # Verificar tipo do target
            unique_values = y.nunique()
            if unique_values < 20:
                print(f"✅ Target é categórico com {unique_values} classes")
                
                if y.dtype == 'object':
                    self.label_encoder = LabelEncoder()
                    y = self.label_encoder.fit_transform(y)
                    self.class_names = self.label_encoder.classes_.tolist()
                else:
                    self.class_names = [str(i) for i in sorted(y.unique())]
                
                result["class_names"] = self.class_names
                result["task_type"] = "classification"
            else:
                print(f"✅ Target é contínuo (regressão)")
                result["task_type"] = "regression"
            
            # Aplicar scaling
            print(f"\n⚖️ APLICANDO SCALING ({scaler_type})...")
            
            if scaler_type == 'standard':
                self.scaler = StandardScaler()
            elif scaler_type == 'minmax':
                self.scaler = MinMaxScaler()
            elif scaler_type == 'robust':
                self.scaler = RobustScaler()
            else:
                self.scaler = StandardScaler()
            
            self.scaler_type = scaler_type
            X_scaled = self.scaler.fit_transform(X)
            X_scaled = pd.DataFrame(X_scaled, columns=self.feature_names)
            
            # Dividir em treino e teste
            stratify = y if unique_values < 20 else None
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=test_size, random_state=random_state, stratify=stratify
            )
            
            print(f"\n📊 DIVISÃO DOS DADOS:")
            print(f"   Treino: {X_train.shape[0]} amostras")
            print(f"   Teste: {X_test.shape[0]} amostras")
            
            result["X_train"] = X_train
            result["X_test"] = X_test
            result["y_train"] = y_train
            result["y_test"] = y_test
            result["status"] = "success"
            result["message"] = f"Dados preparados com {scaler_type} scaling"
            
        except Exception as e:
            print(f"❌ Erro na preparação: {str(e)}")
            result["status"] = "error"
            result["message"] = str(e)
        
        return result
    
    async def train_model(self,
                         X_train: pd.DataFrame,
                         y_train: pd.Series,
                         X_test: Optional[pd.DataFrame] = None,
                         y_test: Optional[pd.Series] = None,
                         model_type: str = 'random_forest',
                         **model_params) -> Dict[str, Any]:
        """
        Treina modelo e calcula métricas
        """
        print(f"\n🤖 TREINANDO MODELO: {model_type}")
        
        result = {
            "status": "success",
            "model": None,
            "metrics": {},
            "confusion_matrix": None,
            "confusion_matrix_image": None,
            "classification_report": None,
            "feature_importance": None,
            "predictions": None,
            "message": ""
        }
        
        try:
            # Selecionar modelo
            if model_type == 'random_forest':
                self.model = RandomForestClassifier(
                    n_estimators=model_params.get('n_estimators', 100),
                    max_depth=model_params.get('max_depth', None),
                    random_state=42
                )
            elif model_type == 'gradient_boosting':
                self.model = GradientBoostingClassifier(
                    n_estimators=model_params.get('n_estimators', 100),
                    learning_rate=model_params.get('learning_rate', 0.1),
                    max_depth=model_params.get('max_depth', 3),
                    random_state=42
                )
            elif model_type == 'logistic_regression':
                self.model = LogisticRegression(
                    C=model_params.get('C', 1.0),
                    max_iter=model_params.get('max_iter', 1000),
                    random_state=42
                )
            else:
                self.model = RandomForestClassifier(n_estimators=100, random_state=42)
            
            self.model_type = model_type
            
            # Treinar
            print("   Treinando...")
            self.model.fit(X_train, y_train)
            
            # Avaliar se temos dados de teste
            if X_test is not None and y_test is not None:
                y_pred = self.model.predict(X_test)
                
                # Calcular métricas
                accuracy = accuracy_score(y_test, y_pred)
                recall = recall_score(y_test, y_pred, average='macro') if len(np.unique(y_test)) > 2 else recall_score(y_test, y_pred)
                precision = precision_score(y_test, y_pred, average='macro') if len(np.unique(y_test)) > 2 else precision_score(y_test, y_pred)
                f1 = f1_score(y_test, y_pred, average='macro') if len(np.unique(y_test)) > 2 else f1_score(y_test, y_pred)
                
                self.metrics = {
                    "accuracy": accuracy,
                    "recall": recall,
                    "precision": precision,
                    "f1_score": f1,
                    "model_type": model_type
                }
                
                result["metrics"] = self.metrics
                result["predictions"] = y_pred.tolist()
                
                # Matriz de confusão
                cm = confusion_matrix(y_test, y_pred)
                result["confusion_matrix"] = cm.tolist()
                
                print(f"\n📊 MÉTRICAS:")
                print(f"   Accuracy:  {accuracy:.4f}")
                print(f"   Recall:    {recall:.4f}")
                print(f"   Precision: {precision:.4f}")
                print(f"   F1-Score:  {f1:.4f}")
            
            result["model"] = self.model
            result["status"] = "success"
            
        except Exception as e:
            print(f"❌ Erro no treinamento: {str(e)}")
            result["status"] = "error"
            result["message"] = str(e)
        
        return result
    
    async def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Faz previsões com o modelo treinado"""
        if self.model is None:
            raise ValueError("Modelo não treinado")
        
        if self.scaler is not None:
            X_scaled = self.scaler.transform(X)
        else:
            X_scaled = X
        
        predictions = self.model.predict(X_scaled)
        
        if self.label_encoder is not None:
            predictions = self.label_encoder.inverse_transform(predictions)
        
        return predictions

class DataPreprocessor(ModelTrainer):
    """
    Classe para pré-processamento de dados - compatível com routes.py
    Herda de ModelTrainer para manter todas as funcionalidades
    """
    def __init__(self):
        super().__init__()
        print("✅ DataPreprocessor inicializado (wrapper para ModelTrainer)")
    
    # O método process_file já existe na classe pai (ModelTrainer)
    # Então não precisa reimplementar