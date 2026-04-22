# backend/ml/boosting_ensemble.py
"""
Sistema de Ensemble Learning com Boosting
Cada modelo aprende com os erros do anterior
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import os
import joblib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Scikit-learn para boosting
from sklearn.ensemble import (
    AdaBoostClassifier, AdaBoostRegressor,
    GradientBoostingClassifier, GradientBoostingRegressor,
    RandomForestClassifier, RandomForestRegressor
)
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.model_selection import train_test_split, KFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, mean_squared_error, classification_report,
    confusion_matrix, roc_auc_score, f1_score
)

# Importar seus módulos existentes
from ml.model import MLModel
from ml.predict import predictor


class BoostingEnsemble:
    """
    Sistema de Ensemble que aprende com os erros
    Cada novo modelo foca nos erros do anterior
    """
    
    def __init__(self):
        self.models_dir = os.path.join("backend", "ml", "models", "boosting")
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Lista de modelos treinados
        self.models = []
        self.model_weights = []
        self.errors_history = []
        self.accuracy_history = []
        
        # Melhor modelo
        self.best_model = None
        self.best_score = 0
        
        # Scaler
        self.scaler = StandardScaler()
        
        # Resultados
        self.training_log = []
        
        # Métricas adicionais para Gemini
        self.last_training_metrics = None
        self.feature_importance_history = []
        
        print("✅ BoostingEnsemble inicializado")
    
    def train_sequential_boost(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_models: int = 5,
        test_size: float = 0.2,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Treina modelos sequencialmente, cada um focando nos erros do anterior
        """
        print(f"\n{'='*70}")
        print("🚀 INICIANDO BOOSTING ENSEMBLE")
        print(f"{'='*70}")
        print(f"📊 Dados: {X.shape[0]} amostras, {X.shape[1]} features")
        print(f"🎯 Target: {y.name if hasattr(y, 'name') else 'target'}")
        print(f"🔢 Modelos no ensemble: {n_models}")
        print(f"{'='*70}\n")
        
        # Preparar dados
        X = X.select_dtypes(include=[np.number])
        
        # Dividir treino e teste
        stratify = y if len(np.unique(y)) <= 10 else None
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=stratify
        )
        
        # Escalar dados
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Determinar tipo de problema
        is_classification = len(np.unique(y)) <= 20
        
        # Inicializar
        self.models = []
        self.model_weights = []
        self.errors_history = []
        self.accuracy_history = []
        self.feature_importance_history = []
        
        # Pesos das amostras (inicialmente uniformes)
        sample_weights = np.ones(len(X_train)) / len(X_train)
        
        # Para tracking
        y_train_pred_ensemble = np.zeros(len(X_train))
        y_test_pred_ensemble = np.zeros(len(X_test))
        
        # Armazenar previsões individuais
        all_train_preds = []
        all_test_preds = []
        
        for i in range(n_models):
            print(f"\n{'─'*50}")
            print(f"🌳 TREINANDO MODELO {i+1}/{n_models}")
            print(f"{'─'*50}")
            
            # 1. CRIAR MODELO APROPRIADO PARA O ESTÁGIO
            if i == 0:
                # Primeiro modelo: mais simples
                if is_classification:
                    model = DecisionTreeClassifier(max_depth=3, random_state=42)
                    model_name = "Árvore Simples (estágio 1)"
                else:
                    model = DecisionTreeRegressor(max_depth=3, random_state=42)
                    model_name = "Árvore Simples (estágio 1)"
            
            elif i == 1:
                # Segundo modelo: foca nos erros do primeiro
                if is_classification:
                    model = AdaBoostClassifier(
                        n_estimators=50,
                        learning_rate=0.8,
                        random_state=42
                    )
                    model_name = "AdaBoost (foco nos erros)"
                else:
                    model = AdaBoostRegressor(
                        n_estimators=50,
                        learning_rate=0.8,
                        random_state=42
                    )
                    model_name = "AdaBoost (foco nos erros)"
            
            elif i == 2:
                # Terceiro modelo: gradient boosting
                if is_classification:
                    model = GradientBoostingClassifier(
                        n_estimators=100,
                        learning_rate=0.1,
                        max_depth=4,
                        subsample=0.8,
                        random_state=42
                    )
                    model_name = "GradientBoosting (aprendizado profundo)"
                else:
                    model = GradientBoostingRegressor(
                        n_estimators=100,
                        learning_rate=0.1,
                        max_depth=4,
                        subsample=0.8,
                        random_state=42
                    )
                    model_name = "GradientBoosting (aprendizado profundo)"
            
            else:
                # Modelos avançados
                if is_classification:
                    model = RandomForestClassifier(
                        n_estimators=100,
                        max_depth=10,
                        random_state=42,
                        n_jobs=-1
                    )
                else:
                    model = RandomForestRegressor(
                        n_estimators=100,
                        max_depth=10,
                        random_state=42,
                        n_jobs=-1
                    )
                model_name = f"RandomForest (estágio {i+1})"
            
            # 2. TREINAR COM PESOS (foco nos erros anteriores)
            try:
                if hasattr(model, 'fit') and 'sample_weight' in model.fit.__code__.co_varnames:
                    model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
                else:
                    model.fit(X_train_scaled, y_train)
            except:
                # Se não aceitar sample_weight, treinar normalmente
                model.fit(X_train_scaled, y_train)
            
            # 3. FAZER PREVISÕES
            y_train_pred = model.predict(X_train_scaled)
            y_test_pred = model.predict(X_test_scaled)
            
            all_train_preds.append(y_train_pred)
            all_test_preds.append(y_test_pred)
            
            # 4. CALCULAR ERROS
            if is_classification:
                # Para classificação: 0 = acertou, 1 = errou
                errors = (y_train_pred != y_train).astype(int)
                error_rate = errors.mean()
                
                # Acurácia
                train_acc = accuracy_score(y_train, y_train_pred)
                test_acc = accuracy_score(y_test, y_test_pred)
                
                # F1-Score
                train_f1 = f1_score(y_train, y_train_pred, average='weighted', zero_division=0)
                test_f1 = f1_score(y_test, y_test_pred, average='weighted', zero_division=0)
                
                if verbose:
                    print(f"\n📊 Modelo: {model_name}")
                    print(f"   Acurácia treino: {train_acc:.2%}")
                    print(f"   Acurácia teste: {test_acc:.2%}")
                    print(f"   F1-Score treino: {train_f1:.3f}")
                    print(f"   F1-Score teste: {test_f1:.3f}")
                    print(f"   Taxa de erro: {error_rate:.2%}")
                
                # Acumular previsões para ensemble
                y_train_pred_ensemble += y_train_pred
                y_test_pred_ensemble += y_test_pred
                
                # Salvar métricas
                train_score = train_acc
                test_score = test_acc
                
            else:
                # Para regressão: erro absoluto
                errors = np.abs(y_train - y_train_pred)
                error_rate = errors.mean() / (y_train.std() + 1e-10)
                
                # Métricas
                train_mse = mean_squared_error(y_train, y_train_pred)
                test_mse = mean_squared_error(y_test, y_test_pred)
                train_rmse = np.sqrt(train_mse)
                test_rmse = np.sqrt(test_mse)
                
                if verbose:
                    print(f"\n📊 Modelo: {model_name}")
                    print(f"   MSE treino: {train_mse:.4f}")
                    print(f"   MSE teste: {test_mse:.4f}")
                    print(f"   RMSE treino: {train_rmse:.4f}")
                    print(f"   RMSE teste: {test_rmse:.4f}")
                    print(f"   Erro relativo: {error_rate:.2%}")
                
                # Acumular previsões
                y_train_pred_ensemble += y_train_pred
                y_test_pred_ensemble += y_test_pred
                
                train_score = -train_mse
                test_score = -test_mse
            
            # 5. ATUALIZAR PESOS (aprender com os erros)
            if error_rate > 0 and error_rate < 0.5:
                model_weight = np.log((1 - error_rate) / max(error_rate, 1e-10)) / 2
                
                if is_classification:
                    sample_weights = sample_weights * np.exp(model_weight * errors)
                else:
                    if errors.max() > 0:
                        sample_weights = sample_weights * np.exp(model_weight * (errors / errors.max()))
                
                sample_weights = sample_weights / (sample_weights.sum() + 1e-10)
                self.model_weights.append(model_weight)
            else:
                self.model_weights.append(0.5)
            
            # 6. Extrair importância das features (se disponível)
            feature_importance = None
            if hasattr(model, 'feature_importances_'):
                feature_importance = model.feature_importances_.tolist()
                self.feature_importance_history.append({
                    'stage': i+1,
                    'model': model_name,
                    'importances': feature_importance
                })
            
            # 7. GUARDAR HISTÓRICO
            self.models.append({
                'model': model,
                'name': model_name,
                'stage': i+1,
                'error_rate': error_rate,
                'train_score': train_score,
                'test_score': test_score,
                'weight': self.model_weights[-1],
                'feature_importance': feature_importance
            })
            
            self.errors_history.append(error_rate)
            if is_classification:
                self.accuracy_history.append(test_acc)
        
        # 7. ENSEMBLE FINAL
        print(f"\n{'='*50}")
        print("🏆 RESULTADO DO ENSEMBLE FINAL")
        print(f"{'='*50}")
        
        if is_classification:
            ensemble_train_pred = np.round(y_train_pred_ensemble / n_models).astype(int)
            ensemble_test_pred = np.round(y_test_pred_ensemble / n_models).astype(int)
            
            ensemble_train_acc = accuracy_score(y_train, ensemble_train_pred)
            ensemble_test_acc = accuracy_score(y_test, ensemble_test_pred)
            ensemble_f1 = f1_score(y_test, ensemble_test_pred, average='weighted', zero_division=0)
            
            print(f"\n📊 Ensemble Final ({n_models} modelos):")
            print(f"   Acurácia treino: {ensemble_train_acc:.2%}")
            print(f"   Acurácia teste: {ensemble_test_acc:.2%}")
            print(f"   F1-Score: {ensemble_f1:.3f}")
            
            first_model_acc = self.models[0]['test_score']
            improvement = ensemble_test_acc - first_model_acc
            print(f"   Melhoria vs 1º modelo: +{improvement:.2%}")
            
            best_score = ensemble_test_acc
            
            # Matriz de confusão
            conf_matrix = confusion_matrix(y_test, ensemble_test_pred).tolist()
            
        else:
            ensemble_train_pred = y_train_pred_ensemble / n_models
            ensemble_test_pred = y_test_pred_ensemble / n_models
            
            ensemble_train_mse = mean_squared_error(y_train, ensemble_train_pred)
            ensemble_test_mse = mean_squared_error(y_test, ensemble_test_pred)
            ensemble_rmse = np.sqrt(ensemble_test_mse)
            
            print(f"\n📊 Ensemble Final ({n_models} modelos):")
            print(f"   MSE treino: {ensemble_train_mse:.4f}")
            print(f"   MSE teste: {ensemble_test_mse:.4f}")
            print(f"   RMSE: {ensemble_rmse:.4f}")
            
            best_score = -ensemble_test_mse
            conf_matrix = None
        
        # Guardar melhor modelo
        self.best_model = {
            'models': [m['model'] for m in self.models],
            'weights': self.model_weights,
            'scaler': self.scaler,
            'is_classification': is_classification,
            'n_models': n_models,
            'feature_names': list(X.columns)
        }
        self.best_score = best_score
        
        # Salvar métricas para Gemini
        self.last_training_metrics = {
            'ensemble_test_score': ensemble_test_acc if is_classification else ensemble_test_mse,
            'ensemble_train_score': ensemble_train_acc if is_classification else ensemble_train_mse,
            'improvement': improvement if is_classification else None,
            'confusion_matrix': conf_matrix,
            'n_models': n_models,
            'is_classification': is_classification
        }
        
        # Salvar resultados
        self._save_results(is_classification)
        
        return {
            'models': self.models,
            'model_weights': self.model_weights,
            'errors_history': self.errors_history,
            'accuracy_history': self.accuracy_history if is_classification else None,
            'ensemble_train_score': ensemble_train_acc if is_classification else ensemble_train_mse,
            'ensemble_test_score': ensemble_test_acc if is_classification else ensemble_test_mse,
            'improvement': improvement if is_classification else None,
            'is_classification': is_classification,
            'confusion_matrix': conf_matrix,
            'feature_importance_history': self.feature_importance_history
        }
    
    def train_with_cross_validation(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_folds: int = 10,
        n_models: int = 5
    ) -> Dict[str, Any]:
        """
        Treina com validação cruzada K-Fold
        """
        print(f"\n{'='*70}")
        print(f"🔬 TREINANDO COM K-FOLD ({n_folds} FOLDS)")
        print(f"{'='*70}")
        
        X = X.select_dtypes(include=[np.number])
        kfold = KFold(n_splits=n_folds, shuffle=True, random_state=42)
        
        fold_results = []
        all_scores = []
        
        for fold, (train_idx, val_idx) in enumerate(kfold.split(X), 1):
            print(f"\n📁 Fold {fold}/{n_folds}")
            
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
            
            try:
                result = self.train_sequential_boost(
                    X_train, y_train,
                    n_models=n_models,
                    test_size=0.2,
                    verbose=False
                )
                
                fold_results.append({
                    'fold': fold,
                    'ensemble_score': result['ensemble_test_score']
                })
                all_scores.append(result['ensemble_test_score'])
                
                print(f"   ✅ Score: {result['ensemble_test_score']:.4f}")
                
            except Exception as e:
                print(f"   ⚠️ Erro no fold {fold}: {e}")
                continue
        
        if not fold_results:
            print("❌ Nenhum fold foi treinado com sucesso")
            return {'fold_results': [], 'mean_score': 0, 'std_score': 0, 'all_scores': []}
        
        scores = [r['ensemble_score'] for r in fold_results]
        print(f"\n{'='*50}")
        print("📊 RESULTADOS K-FOLD:")
        print(f"{'='*50}")
        print(f"Média: {np.mean(scores):.4f}")
        print(f"Desvio: {np.std(scores):.4f}")
        print(f"Min: {np.min(scores):.4f}")
        print(f"Max: {np.max(scores):.4f}")
        
        return {
            'fold_results': fold_results,
            'mean_score': np.mean(scores),
            'std_score': np.std(scores),
            'all_scores': scores
        }
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Faz previsões usando o ensemble
        """
        if self.best_model is None:
            raise ValueError("Nenhum modelo treinado. Execute train_sequential_boost primeiro.")
        
        X = X.select_dtypes(include=[np.number])
        X_scaled = self.best_model['scaler'].transform(X)
        
        predictions = np.zeros(len(X))
        total_weight = sum(self.best_model['weights'])
        
        if total_weight == 0:
            total_weight = 1
        
        for i, model_data in enumerate(self.best_model['models']):
            model_pred = model_data.predict(X_scaled)
            weight = self.best_model['weights'][i]
            predictions += model_pred * weight
        
        predictions = predictions / total_weight
        
        if self.best_model['is_classification']:
            predictions = np.round(predictions).astype(int)
        
        return predictions
    
    def predict_proba_ensemble(self, X: pd.DataFrame) -> np.ndarray:
        """
        Retorna probabilidades do ensemble (para classificação)
        """
        if self.best_model is None or not self.best_model['is_classification']:
            raise ValueError("Ensemble não configurado para classificação")
        
        X = X.select_dtypes(include=[np.number])
        X_scaled = self.best_model['scaler'].transform(X)
        
        probas = np.zeros((len(X), 2))
        total_weight = sum(self.best_model['weights'])
        
        if total_weight == 0:
            total_weight = 1
        
        for i, model_data in enumerate(self.best_model['models']):
            if hasattr(model_data, 'predict_proba'):
                model_proba = model_data.predict_proba(X_scaled)
                weight = self.best_model['weights'][i]
                probas += model_proba * weight
        
        if probas.sum() > 0:
            probas = probas / total_weight
        
        return probas
    
    def get_ensemble_metrics_for_gemini(self) -> Dict[str, Any]:
        """
        Retorna métricas detalhadas do ensemble para o Gemini analisar como Analista Sênior
        """
        if not self.models:
            return {
                "status": "sem_modelos", 
                "mensagem": "Nenhum ensemble foi treinado ainda",
                "recomendacao": "Execute train_sequential_boost primeiro"
            }
        
        # Calcular métricas do ensemble
        total_models = len(self.models)
        avg_error = np.mean(self.errors_history) if self.errors_history else 0
        final_error = self.errors_history[-1] if self.errors_history else 0
        initial_error = self.errors_history[0] if self.errors_history else 0
        improvement = initial_error - final_error if len(self.errors_history) > 1 else 0
        
        # Análise de convergência
        if len(self.errors_history) > 2:
            convergence_rate = abs(self.errors_history[-1] - self.errors_history[-2]) / (self.errors_history[-2] + 1e-10)
            is_converged = convergence_rate < 0.01
        else:
            convergence_rate = 1.0
            is_converged = False
        
        # Análise de overfitting
        if len(self.models) >= 2:
            train_scores = [m['train_score'] for m in self.models]
            test_scores = [m['test_score'] for m in self.models]
            
            if self.models[0].get('test_score', 0) and isinstance(self.models[0]['test_score'], (int, float)):
                overfitting_gap = train_scores[-1] - test_scores[-1]
                overfitting_risk = "Alto" if overfitting_gap > 0.15 else "Médio" if overfitting_gap > 0.08 else "Baixo"
            else:
                overfitting_risk = "Não aplicável"
        else:
            overfitting_risk = "Dados insuficientes"
        
        # Importância média das features
        feature_importance_avg = {}
        if self.feature_importance_history and self.best_model and 'feature_names' in self.best_model:
            feature_names = self.best_model['feature_names']
            all_importances = []
            
            for stage in self.feature_importance_history:
                if stage['importances']:
                    all_importances.append(stage['importances'])
            
            if all_importances and feature_names:
                avg_importances = np.mean(all_importances, axis=0)
                for i, name in enumerate(feature_names[:len(avg_importances)]):
                    feature_importance_avg[name] = float(avg_importances[i])
                
                feature_importance_avg = dict(sorted(feature_importance_avg.items(), key=lambda x: x[1], reverse=True))
        
        metrics = {
            "status": "treinado",
            "tipo_ensemble": "Boosting Sequencial",
            "total_modelos": total_models,
            "taxa_erro_inicial": float(initial_error),
            "taxa_erro_final": float(final_error),
            "melhoria_erro": float(improvement),
            "melhoria_percentual": float(improvement / (initial_error + 1e-10) * 100),
            "convergencia": {
                "atingiu_convergencia": is_converged,
                "taxa_convergencia": float(convergence_rate),
                "status": "Estável" if is_converged else "Melhorando" if convergence_rate > 0 else "Instável"
            },
            "risco_overfitting": overfitting_risk,
            "pesos_modelos": [float(w) for w in self.model_weights],
            "importancia_features": feature_importance_avg,
            "modelos_por_estagio": [
                {
                    "estagio": m['stage'],
                    "nome": m['name'],
                    "taxa_erro": float(m['error_rate']),
                    "peso": float(m['weight']),
                    "score_teste": float(m['test_score']) if isinstance(m['test_score'], (int, float)) else None
                }
                for m in self.models
            ],
            "analise_aprendizado": self._analyze_learning_curve(),
            "recomendacoes": self._generate_ensemble_recommendations(),
            "performance_ensemble": self.last_training_metrics
        }
        
        return metrics
    
    def _analyze_learning_curve(self) -> Dict[str, Any]:
        """Analisa a curva de aprendizado do ensemble"""
        if len(self.errors_history) < 3:
            return {
                "status": "dados_insuficientes", 
                "mensagem": "Mais modelos necessários para análise completa",
                "modelos_recomendados": 5 - len(self.errors_history)
            }
        
        # Verificar tendência
        errors_recent = self.errors_history[-3:]
        errors_early = self.errors_history[:3]
        
        trend = "Decrescente" if self.errors_history[-1] < self.errors_history[0] else "Estacionária" if abs(self.errors_history[-1] - self.errors_history[0]) < 0.05 else "Crescente"
        
        # Calcular taxa de aprendizado
        learning_rate = (self.errors_history[0] - self.errors_history[-1]) / len(self.errors_history)
        
        # Verificar overfitting pela curva
        if len(self.accuracy_history) >= 3:
            acc_trend = self.accuracy_history[-1] - self.accuracy_history[0]
            overfitting_from_curve = acc_trend < -0.05  # Se acurácia caiu mais que 5%
        else:
            overfitting_from_curve = False
        
        return {
            "tendencia": trend,
            "taxa_aprendizado": float(learning_rate),
            "risco_overfitting_curva": "Alto" if overfitting_from_curve else "Baixo",
            "confianca_ensemble": float(max(0, min(1, 1 - self.errors_history[-1]))),
            "modelos_restantes_recomendados": max(0, 8 - len(self.models)) if trend == "Decrescente" else 0,
            "estabilizacao_atingida": len(self.errors_history) >= 5 and abs(self.errors_history[-1] - self.errors_history[-2]) < 0.01
        }
    
    def _generate_ensemble_recommendations(self) -> List[str]:
        """Gera recomendações baseadas no desempenho do ensemble"""
        recommendations = []
        
        if not self.models:
            return ["Treine o ensemble antes de gerar recomendações"]
        
        final_error = self.errors_history[-1] if self.errors_history else 1
        initial_error = self.errors_history[0] if self.errors_history else 1
        
        # Recomendações baseadas no erro final
        if final_error < 0.05:
            recommendations.append("✅ Ensemble com performance excelente - pronto para produção")
        elif final_error < 0.10:
            recommendations.append("📊 Bom desempenho - pode ser implantado com monitoramento")
        elif final_error < 0.20:
            recommendations.append("⚠️ Desempenho moderado - considere mais iterações ou mais dados")
        else:
            recommendations.append("🔴 Desempenho abaixo do esperado - revisar features e dados")
        
        # Recomendações baseadas na melhoria
        improvement_pct = (initial_error - final_error) / (initial_error + 1e-10) * 100
        if improvement_pct > 30:
            recommendations.append(f"📈 Boa evolução ({improvement_pct:.0f}% melhoria) - ensemble eficaz")
        elif improvement_pct < 5 and len(self.models) > 3:
            recommendations.append("🔄 Ensemble estabilizado - adicionar mais modelos pode não ajudar")
        
        # Recomendações baseadas no número de modelos
        if len(self.models) < 5:
            recommendations.append(f"➕ Adicionar mais {5 - len(self.models)} modelos pode melhorar o ensemble")
        elif len(self.models) > 10:
            recommendations.append("⚖️ Ensemble grande - considerar pruning para reduzir complexidade")
        
        # Recomendações de validação
        if len(self.models) >= 3:
            recommendations.append("🔬 Recomenda-se validação cruzada para confirmar generalização")
        
        if not recommendations:
            recommendations = [
                "📊 Ensemble treinado com sucesso",
                "🔍 Monitorar performance em produção",
                "💡 Coletar mais dados para próximas iterações"
            ]
        
        return recommendations
    
    def get_model_summary(self) -> pd.DataFrame:
        """Retorna resumo dos modelos treinados"""
        if not self.models:
            return pd.DataFrame()
        
        summary = []
        for m in self.models:
            summary.append({
                'Estágio': m['stage'],
                'Modelo': m['name'],
                'Taxa Erro': f"{m['error_rate']:.2%}",
                'Score Treino': f"{m['train_score']:.4f}" if isinstance(m['train_score'], (int, float)) else "N/A",
                'Score Teste': f"{m['test_score']:.4f}" if isinstance(m['test_score'], (int, float)) else "N/A",
                'Peso': f"{m['weight']:.4f}"
            })
        
        return pd.DataFrame(summary)
    
    def integrate_with_predictor(self):
        """Integra o melhor ensemble com o predictor existente"""
        if self.best_model is None:
            print("❌ Nenhum modelo treinado para integrar")
            return False
        
        try:
            model_data = {
                'ensemble': self.best_model,
                'models': self.models,
                'model_weights': self.model_weights,
                'type': 'boosting_ensemble',
                'trained_date': datetime.now().isoformat(),
                'version': '2.0',
                'metrics': self.last_training_metrics
            }
            
            model_path = os.path.join("backend", "ml", "models", "office_model.pkl")
            joblib.dump(model_data, model_path)
            
            print(f"\n✅ Ensemble integrado com predictor em: {model_path}")
            print(f"📊 Métricas do ensemble salvas: {self.last_training_metrics}")
            return True
            
        except Exception as e:
            print(f"❌ Erro na integração: {e}")
            return False
    
    def _save_results(self, is_classification: bool):
        """Salva resultados do treinamento"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        model_path = os.path.join(self.models_dir, f"ensemble_{timestamp}.pkl")
        joblib.dump({
            'best_model': self.best_model,
            'models': [(m['name'], m['stage']) for m in self.models],
            'model_weights': self.model_weights,
            'errors_history': self.errors_history,
            'accuracy_history': self.accuracy_history if is_classification else None,
            'is_classification': is_classification,
            'timestamp': timestamp,
            'metrics': self.last_training_metrics,
            'feature_importance_history': self.feature_importance_history
        }, model_path)
        
        print(f"\n💾 Ensemble salvo em: {model_path}")
        
        self.training_log.append({
            'timestamp': timestamp,
            'n_models': len(self.models),
            'best_score': self.best_score,
            'is_classification': is_classification,
            'final_error': self.errors_history[-1] if self.errors_history else None
        })
    
    def plot_learning_curve(self):
        """Plota curva de aprendizado do ensemble"""
        try:
            import matplotlib.pyplot as plt
            
            plt.figure(figsize=(14, 5))
            
            # Erros ao longo do treinamento
            plt.subplot(1, 3, 1)
            plt.plot(range(1, len(self.errors_history)+1), self.errors_history, 'bo-', linewidth=2, markersize=8)
            plt.xlabel('Estágio do Modelo', fontsize=10)
            plt.ylabel('Taxa de Erro', fontsize=10)
            plt.title('Evolução dos Erros', fontsize=12)
            plt.grid(True, alpha=0.3)
            
            # Acurácia (se disponível)
            if self.accuracy_history:
                plt.subplot(1, 3, 2)
                plt.plot(range(1, len(self.accuracy_history)+1), self.accuracy_history, 'go-', linewidth=2, markersize=8)
                plt.xlabel('Estágio do Modelo', fontsize=10)
                plt.ylabel('Acurácia', fontsize=10)
                plt.title('Evolução da Acurácia', fontsize=12)
                plt.grid(True, alpha=0.3)
            
            # Pesos dos modelos
            plt.subplot(1, 3, 3)
            plt.bar(range(1, len(self.model_weights)+1), self.model_weights, color='purple', alpha=0.7)
            plt.xlabel('Estágio do Modelo', fontsize=10)
            plt.ylabel('Peso no Ensemble', fontsize=10)
            plt.title('Distribuição dos Pesos', fontsize=12)
            plt.grid(True, alpha=0.3, axis='y')
            
            plt.tight_layout()
            
            plot_path = os.path.join(self.models_dir, f"learning_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            print(f"📈 Curva de aprendizado salva em: {plot_path}")
            
            plt.close()
            
        except Exception as e:
            print(f"⚠️ Não foi possível gerar gráfico: {e}")


# Instância global
boosting_ensemble = BoostingEnsemble()

print("\n✅ BoostingEnsemble pronto para uso com Gemini!")
print("📊 Métodos disponíveis para Gemini: get_ensemble_metrics_for_gemini()")