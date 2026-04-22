# backend/ml/train.py - VERSÃO ATUALIZADA
"""
Módulo de treinamento de modelos com extração de métricas para Gemini
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
import os
import pickle
from datetime import datetime
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, mean_squared_error, r2_score

class ModelTrainer:
    """Treinador de modelos com extração de métricas para análise sênior"""
    
    def __init__(self):
        self.models_dir = os.path.join("backend", "ml", "models")
        os.makedirs(self.models_dir, exist_ok=True)
        self.training_history = []
    
    async def train_and_get_metrics(self, df: pd.DataFrame, target_col: str, model_type: str = 'classifier') -> Dict[str, Any]:
        """
        Treina modelo e retorna métricas detalhadas para o Gemini
        
        Args:
            df: DataFrame com dados
            target_col: Coluna alvo
            model_type: 'classifier' ou 'regressor'
        
        Returns:
            Dicionário com métricas completas
        """
        print(f"\n{'='*60}")
        print("📊 INICIANDO TREINAMENTO DE MODELO")
        print(f"{'='*60}")
        
        # Preparar dados
        X = df.drop(columns=[target_col])
        y = df[target_col]
        
        # Selecionar apenas colunas numéricas
        X = X.select_dtypes(include=[np.number])
        
        if X.empty:
            return {"erro": "Nenhuma coluna numérica encontrada para treinamento"}
        
        # Dividir dados
        stratify = y if model_type == 'classifier' and len(np.unique(y)) <= 10 else None
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=stratify
        )
        
        # Importar modelos
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.preprocessing import StandardScaler
        
        # Escalar dados
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Treinar modelo
        if model_type == 'classifier':
            model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train_scaled, y_train)
            
            # Previsões
            y_pred = model.predict(X_test_scaled)
            y_pred_proba = model.predict_proba(X_test_scaled)
            
            # Métricas
            accuracy = accuracy_score(y_test, y_pred)
            
            # Validação cruzada
            cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring='accuracy')
            
            # Relatório de classificação
            class_report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
            
            # Matriz de confusão
            conf_matrix = confusion_matrix(y_test, y_pred).tolist()
            
            # Importância das features
            feature_importance = dict(zip(X.columns, model.feature_importances_))
            feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
            
            metrics = {
                "tipo_modelo": "RandomForest Classifier",
                "acuraciA": float(accuracy),
                "acuraciA_cv_media": float(cv_scores.mean()),
                "acuraciA_cv_desvio": float(cv_scores.std()),
                "relatorio_classificacao": class_report,
                "matriz_confusao": conf_matrix,
                "features_importantes": feature_importance,
                "total_amostras": len(X),
                "amostras_treino": len(X_train),
                "amostras_teste": len(X_test),
                "classes_encontradas": sorted(map(int, np.unique(y))),
                "balanceamento_classes": {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
            }
            
        else:  # Regressor
            model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train_scaled, y_train)
            
            # Previsões
            y_pred = model.predict(X_test_scaled)
            
            # Métricas
            mse = mean_squared_error(y_test, y_pred)
            rmse = np.sqrt(mse)
            r2 = r2_score(y_test, y_pred)
            
            # Validação cruzada
            cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring='r2')
            
            # Importância das features
            feature_importance = dict(zip(X.columns, model.feature_importances_))
            feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
            
            metrics = {
                "tipo_modelo": "RandomForest Regressor",
                "mse": float(mse),
                "rmse": float(rmse),
                "r2_score": float(r2),
                "r2_cv_media": float(cv_scores.mean()),
                "r2_cv_desvio": float(cv_scores.std()),
                "features_importantes": feature_importance,
                "total_amostras": len(X),
                "amostras_treino": len(X_train),
                "amostras_teste": len(X_test),
                "range_valores": {
                    "min": float(y.min()),
                    "max": float(y.max()),
                    "media": float(y.mean()),
                    "mediana": float(y.median())
                }
            }
        
        # Salvar modelo
        model_path = os.path.join(self.models_dir, f"trained_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl")
        model_data = {
            'model': model,
            'scaler': scaler,
            'metrics': metrics,
            'features': list(X.columns),
            'trained_date': datetime.now().isoformat()
        }
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        # Adicionar ao histórico
        self.training_history.append({
            'timestamp': datetime.now().isoformat(),
            'model_type': model_type,
            'accuracy': metrics.get('acurácia', metrics.get('r2_score', 0)),
            'model_path': model_path
        })
        
        print(f"\n✅ Modelo treinado e salvo em: {model_path}")
        print(f"📊 Métricas principais: {metrics.get('acurácia', metrics.get('r2_score', 0)):.3f}")
        
        return metrics
    
    def get_training_summary_for_gemini(self) -> Dict[str, Any]:
        """Retorna resumo do histórico de treinamentos para o Gemini"""
        if not self.training_history:
            return {"status": "nenhum_treinamento", "mensagem": "Nenhum modelo foi treinado ainda"}
        
        return {
            "total_treinamentos": len(self.training_history),
            "historico": self.training_history[-5:],  # Últimos 5
            "melhor_acuracia": max([h.get('accuracy', 0) for h in self.training_history]),
            "media_acuracia": np.mean([h.get('accuracy', 0) for h in self.training_history])
        }


# Instância global
trainer = ModelTrainer()

print("✅ ModelTrainer pronto para treinamento com extração de métricas")