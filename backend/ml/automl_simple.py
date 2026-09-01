# backend/ml/automl_simple.py - VERSÃO 2.0 (INTEGRADO COM TRAIN V4.0)
"""
AutoML simplificado com integração automática ao predictor
🔥 VERSÃO 2.0: Integrado com train.py V4.0 e predict.py V7.0
🔥 USANDO Z-SCORE (StandardScaler)
🔥 DETECÇÃO AUTOMÁTICA DE FEATURES
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import os
import joblib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.model_selection import cross_val_score, KFold, train_test_split
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

print("🔧 Carregando automl_simple.py V2.0...")


class AutoMLOffice:
    """
    AutoML para dados de oficina com integração automática
    🔥 V2.0: Usa Z-Score (StandardScaler) e detecta features
    """
    
    def __init__(self):
        self.models_dir = os.path.join("backend", "ml", "models", "automl")
        os.makedirs(self.models_dir, exist_ok=True)
        
        self.best_model = None
        self.best_pipeline = None
        self.ranking = None
        self.scaler = None
        self.integrated = False
        self.feature_count = None
        self.feature_names = []
        
        print("✅ AutoMLOffice V2.0 inicializado (integrado com Train V4.0)")
    
    def comparar_modelos_classificacao(
        self,
        df: pd.DataFrame,
        target_col: str,
        n_folds: int = 10,
        test_size: float = 0.2,
        verbose: bool = True,
        integrar_apos_treino: bool = True,
        normalization: str = 'standard'  # standard, robust, minmax
    ) -> pd.DataFrame:
        """
        Compara modelos e integra automaticamente com o predictor
        🔥 Usa Z-Score (StandardScaler) por padrão
        """
        print(f"\n{'='*60}")
        print("🔬 COMPARAÇÃO DE MODELOS - OFICINA V2.0")
        print(f"{'='*60}")
        print(f"📊 Dados: {df.shape[0]} linhas, {df.shape[1]} colunas")
        print(f"🎯 Target: {target_col}")
        print(f"🔢 K-Fold: {n_folds} folds")
        print(f"📊 Normalização: {normalization} (Z-Score)")
        print(f"{'='*60}\n")
        
        # Preparar dados
        X = df.drop(columns=[target_col])
        y = df[target_col]
        
        X = X.select_dtypes(include=[np.number])
        
        if X.empty:
            print("❌ ERRO: Nenhuma coluna numérica encontrada!")
            return pd.DataFrame()
        
        self.feature_names = X.columns.tolist()
        self.feature_count = len(self.feature_names)
        print(f"   🔍 Features detectadas: {self.feature_count}")
        
        # Dividir em treino e teste
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42, stratify=y
            )
        except:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42
            )
        
        print(f"📈 Treino: {X_train.shape[0]} amostras")
        print(f"📉 Teste: {X_test.shape[0]} amostras")
        print(f"🎯 Classes: {np.unique(y)}")
        
        # Selecionar scaler (Z-Score por padrão)
        scaler_map = {
            'standard': StandardScaler(),
            'robust': RobustScaler(),
            'minmax': MinMaxScaler()
        }
        scaler = scaler_map.get(normalization, StandardScaler())
        
        # Modelos para comparar
        modelos = {
            'RANDOM FOREST (100)': RandomForestClassifier(
                n_estimators=100, random_state=42, n_jobs=-1
            ),
            'RANDOM FOREST (50)': RandomForestClassifier(
                n_estimators=50, random_state=42, n_jobs=-1
            ),
            'REGRESSÃO LOGÍSTICA': LogisticRegression(
                random_state=42, max_iter=1000, n_jobs=-1
            ),
            'RIDGE CLASSIFIER': RidgeClassifier(
                random_state=42, max_iter=1000
            )
        }
        
        resultados = []
        kfold = KFold(n_splits=n_folds, shuffle=True, random_state=42)
        
        print("\n⏳ Treinando e validando modelos...\n")
        
        for nome, modelo in modelos.items():
            pipeline = Pipeline([
                ('scaler', scaler),
                ('classifier', modelo)
            ])
            
            cv_scores = cross_val_score(
                pipeline, X_train, y_train,
                cv=kfold, scoring='accuracy', n_jobs=-1
            )
            
            pipeline.fit(X_train, y_train)
            
            y_pred = pipeline.predict(X_test)
            test_acc = accuracy_score(y_test, y_pred)
            test_f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
            test_precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
            test_recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
            
            resultados.append({
                'Modelo': nome,
                'Acurácia (CV)': cv_scores.mean(),
                'Desvio (CV)': cv_scores.std(),
                'Acurácia (Teste)': test_acc,
                'F1-Score': test_f1,
                'Precisão': test_precision,
                'Recall': test_recall,
                'Pipeline': pipeline
            })
            
            if verbose:
                print(f"{nome[:35]:<35} CV: {cv_scores.mean():.4f} (±{cv_scores.std():.4f}) | Teste: {test_acc:.4f}")
        
        # Criar ranking
        ranking_df = pd.DataFrame([
            {k: v for k, v in r.items() if k != 'Pipeline'}
            for r in resultados
        ])
        ranking_df = ranking_df.sort_values('Acurácia (CV)', ascending=False)
        ranking_df['Rank'] = range(1, len(ranking_df) + 1)
        
        print(f"\n{'='*60}")
        print("📊 RANKING FINAL:")
        print(ranking_df[['Rank', 'Modelo', 'Acurácia (CV)', 'F1-Score', 'Precisão']].to_string(index=False))
        
        # Melhor modelo
        melhor = max(resultados, key=lambda x: x['Acurácia (CV)'])
        self.best_pipeline = melhor['Pipeline']
        self.best_model = melhor['Pipeline'].named_steps['classifier']
        self.scaler = melhor['Pipeline'].named_steps['scaler']
        self.ranking = ranking_df
        
        print(f"\n✅ MELHOR MODELO: {melhor['Modelo']}")
        print(f"   Acurácia CV: {melhor['Acurácia (CV)']:.2%}")
        print(f"   Acurácia Teste: {melhor['Acurácia (Teste)']:.2%}")
        print(f"   F1-Score: {melhor['F1-Score']:.4f}")
        print(f"   Normalização: {normalization} (Z-Score)")
        
        # Salvar resultados
        self._salvar_resultados(ranking_df, melhor)
        
        # Integrar automaticamente se solicitado
        if integrar_apos_treino:
            print("\n🔄 Integrando automaticamente com o predictor V7.0...")
            self.integrar_com_predictor()
        
        return ranking_df
    
    def _salvar_resultados(self, ranking_df: pd.DataFrame, melhor_modelo: Dict):
        """Salva resultados do experimento (compatível com V7.0)"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        ranking_path = os.path.join(self.models_dir, f"ranking_{timestamp}.csv")
        ranking_df.to_csv(ranking_path, index=False)
        
        model_path = os.path.join(self.models_dir, f"melhor_modelo_{timestamp}.pkl")
        
        try:
            features = list(melhor_modelo['Pipeline'].feature_names_in_)
        except:
            features = self.feature_names
        
        model_data = {
            'pipeline': melhor_modelo['Pipeline'],
            'model': melhor_modelo['Pipeline'].named_steps['classifier'],
            'scaler': melhor_modelo['Pipeline'].named_steps['scaler'],
            'metricas': {
                'acuracia_cv': float(melhor_modelo['Acurácia (CV)']),
                'acuracia_teste': float(melhor_modelo['Acurácia (Teste)']),
                'f1_score': float(melhor_modelo['F1-Score']),
                'precision': float(melhor_modelo.get('Precisão', 0)),
                'recall': float(melhor_modelo.get('Recall', 0))
            },
            'features': features,
            'feature_count': len(features),
            'normalization': 'Z-Score (StandardScaler)',
            'version': '2.0',
            'trained_date': datetime.now().isoformat()
        }
        
        joblib.dump(model_data, model_path)
        
        print(f"\n💾 Resultados salvos em:")
        print(f"   📁 {ranking_path}")
        print(f"   📁 {model_path}")
    
    def integrar_com_predictor(self):
        """
        Integra o melhor modelo com o predictor V7.0
        ✅ Salva no formato compatível com train.py V4.0 e predict.py V7.0
        """
        if self.best_pipeline is None:
            print("❌ Nenhum modelo treinado para integrar")
            return False
        
        try:
            # Extrair componentes
            scaler = self.best_pipeline.named_steps['scaler']
            model = self.best_pipeline.named_steps['classifier']
            
            # 🔥 FORMATO COMPATÍVEL COM TRAIN.PY V4.0 E PREDICT.PY V7.0
            model_data = {
                'model': model,
                'scaler': scaler,
                'features': self.feature_names,
                'feature_count': self.feature_count,
                'model_name': 'AutoML_V2.0',
                'model_type': 'classifier',
                'metrics': {
                    'accuracy': float(self.ranking.iloc[0]['Acurácia (CV)']) if self.ranking is not None else 0,
                    'f1_score': float(self.ranking.iloc[0]['F1-Score']) if self.ranking is not None else 0
                },
                'normalization': 'Z-Score (StandardScaler)',
                'version': '2.0',
                'trained_date': datetime.now().isoformat(),
                'is_automl': True,
                'ranking': self.ranking.to_dict() if self.ranking is not None else None
            }
            
            # Salvar no formato do predictor V7.0
            model_path = os.path.join("backend", "ml", "models", "trained_model.pkl")
            joblib.dump(model_data, model_path)
            
            # Também salvar como office_model.pkl para compatibilidade
            office_path = os.path.join("backend", "ml", "models", "office_model.pkl")
            joblib.dump(model_data, office_path)
            
            print(f"\n✅ Modelo salvo em: {model_path}")
            print(f"   📊 Features: {self.feature_count}")
            print(f"   📊 Normalização: Z-Score (StandardScaler)")
            print("   🔥 Compatível com train.py V4.0 e predict.py V7.0")
            self.integrated = True
            
            return True
            
        except Exception as e:
            print(f"❌ Erro na integração: {e}")
            return False


# Instância global
automl_office = AutoMLOffice()

print("\n✅ AutoMLOffice V2.0 pronto!")
print("   📊 Usa Z-Score (StandardScaler)")
print("   🔥 Integrado com train.py V4.0 e predict.py V7.0")
print("   Exemplo: automl_office.comparar_modelos_classificacao(df, 'target')")