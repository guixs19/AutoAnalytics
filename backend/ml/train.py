# backend/ml/train.py - VERSÃO CORRIGIDA COM PADRONIZAÇÃO DE CHAVES
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
            
            # 🔥 CORREÇÃO: Padronizar nomes das chaves (português consistente)
            metrics = {
                "tipo_modelo": "RandomForest Classifier",
                "acuracia": float(accuracy),           # 🔥 Padrão: "acuracia" (sem acento? com acento?)
                "acuracia_cv_media": float(cv_scores.mean()),
                "acuracia_cv_desvio": float(cv_scores.std()),
                "relatorio_classificacao": class_report,
                "matriz_confusao": conf_matrix,
                "features_importantes": feature_importance,
                "total_amostras": len(X),
                "amostras_treino": len(X_train),
                "amostras_teste": len(X_test),
                "classes_encontradas": sorted(map(int, np.unique(y))),
                "balanceamento_classes": {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))},
                # 🔥 Campos adicionais para compatibilidade (inglês e português)
                "accuracy": float(accuracy),           # Compatibilidade com inglês
                "acurácia": float(accuracy)            # Compatibilidade com acento
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
            
            # 🔥 CORREÇÃO: Padronizar nomes das chaves
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
                },
                # 🔥 Campos adicionais para compatibilidade
                "r2": float(r2)
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
        
        # 🔥 CORREÇÃO: Adicionar ao histórico com chaves consistentes
        # Extrair métrica principal de forma robusta
        main_metric = metrics.get('acuracia', metrics.get('accuracy', metrics.get('r2_score', metrics.get('r2', 0))))
        
        self.training_history.append({
            'timestamp': datetime.now().isoformat(),
            'model_type': model_type,
            'main_metric': main_metric,      # 🔥 Padrão: "main_metric"
            'acuracia': main_metric,          # 🔥 Compatibilidade com português
            'accuracy': main_metric,          # 🔥 Compatibilidade com inglês
            'r2_score': main_metric if model_type == 'regressor' else None,
            'model_path': model_path,
            'total_amostras': len(X),
            'features_count': len(X.columns)
        })
        
        print(f"\n✅ Modelo treinado e salvo em: {model_path}")
        print(f"📊 Métrica principal: {main_metric:.3f}")
        
        return metrics
    
    def get_training_summary_for_gemini(self) -> Dict[str, Any]:
        """
        Retorna resumo do histórico de treinamentos para o Gemini
        🔥 CORREÇÃO: Estrutura padronizada para o Gemini consumir
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
        
        # 🔥 Extrair métricas de forma robusta
        accuracies = []
        for h in self.training_history:
            # Tentar várias chaves possíveis
            metric = h.get('main_metric', h.get('acuracia', h.get('accuracy', 0)))
            accuracies.append(metric)
        
        best_metric = max(accuracies) if accuracies else 0
        avg_metric = np.mean(accuracies) if accuracies else 0
        
        # 🔥 Identificar o melhor treinamento
        best_index = accuracies.index(best_metric) if accuracies else -1
        best_training = self.training_history[best_index] if best_index >= 0 else None
        
        # 🔥 Criar resumo enriquecido para o Gemini
        summary = {
            "status": "sucesso",
            "total_treinamentos": len(self.training_history),
            "historico": self.training_history[-5:],  # Últimos 5
            "melhor_acuracia": best_metric,
            "melhor_accuracy": best_metric,  # Compatibilidade inglês
            "media_acuracia": avg_metric,
            "media_accuracy": avg_metric,    # Compatibilidade inglês
            "melhor_treinamento": best_training,
            "tipos_modelos": list(set([h.get('model_type') for h in self.training_history])),
            "recomendacao": self._generate_recommendation(best_metric, avg_metric, len(self.training_history))
        }
        
        return summary
    
    def _generate_recommendation(self, best_metric: float, avg_metric: float, total_count: int) -> str:
        """
        Gera recomendação baseada nas métricas
        """
        if best_metric >= 0.9:
            return "✅ Modelo excelente! Pode ser utilizado em produção com confiança."
        elif best_metric >= 0.8:
            return "📈 Bom modelo. Considere aumentar a quantidade de dados para melhorar ainda mais."
        elif best_metric >= 0.7:
            return "⚠️ Modelo razoável. Recomenda-se mais engenharia de features e validação cruzada."
        elif best_metric >= 0.6:
            return "🔧 Modelo precisa de melhorias. Tente diferentes algoritmos ou mais dados de treino."
        else:
            return "❌ Modelo com baixa performance. Revise a qualidade dos dados e seleção de features."
    
    def get_best_model_info(self) -> Optional[Dict[str, Any]]:
        """
        Retorna informações do melhor modelo treinado
        """
        if not self.training_history:
            return None
        
        # Encontrar melhor pelo main_metric
        best = max(self.training_history, key=lambda x: x.get('main_metric', 0))
        return best


# Instância global
trainer = ModelTrainer()

print("✅ ModelTrainer pronto para treinamento com extração de métricas")
print("   📊 Chaves padronizadas: 'acuracia', 'main_metric', 'accuracy'")