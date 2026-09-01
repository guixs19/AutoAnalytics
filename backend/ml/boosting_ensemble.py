# backend/ml/boosting_ensemble.py - VERSÃO 3.0 (INTEGRADO COM TRAIN V4.0)
"""
Sistema de Ensemble Learning com Boosting
Cada modelo aprende com os erros do anterior
🔥 VERSÃO 3.0: Integrado com train.py V4.0 e predict.py V7.0
🔥 USANDO Z-SCORE (StandardScaler)
🔥 DETECÇÃO AUTOMÁTICA DE FEATURES
🔥 ADAPTAÇÃO AUTOMÁTICA A QUALQUER NÚMERO DE FEATURES
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional, Union
import os
import joblib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Scikit-learn para boosting
from sklearn.ensemble import (
    AdaBoostClassifier, AdaBoostRegressor,
    GradientBoostingClassifier, GradientBoostingRegressor,
    RandomForestClassifier, RandomForestRegressor,
    VotingClassifier, VotingRegressor
)
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler
from sklearn.metrics import (
    accuracy_score, mean_squared_error, classification_report,
    confusion_matrix, roc_auc_score, f1_score, precision_score, recall_score,
    r2_score, mean_absolute_error
)
from sklearn.decomposition import PCA

print("🔧 Carregando boosting_ensemble.py V3.0...")


class BoostingEnsemble:
    """
    Sistema de Ensemble que aprende com os erros
    🔥 V3.0: Integrado com train.py V4.0 e predict.py V7.0
    🔥 Normalização Z-Score (StandardScaler)
    🔥 Adaptação automática a qualquer número de features
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
        
        # Scaler (Z-Score)
        self.scaler = StandardScaler()
        self.scaler_type = "standard"
        self.scaler_fitted = False
        
        # 🔥 NOVO: Detecção de features
        self.feature_count = None
        self.feature_names = []
        self.model_feature_count = None
        
        # 🔥 NOVO: PCA para redução de features
        self._pca = None
        self._pca_fitted = False
        
        # Resultados
        self.training_log = []
        
        # Métricas adicionais para Gemini
        self.last_training_metrics = None
        self.feature_importance_history = []
        
        # 🔥 NOVO: Estatísticas
        self.stats = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "feature_adaptations": 0,
            "pca_applied": 0,
            "feature_expansions": 0,
            "best_accuracy": 0,
            "best_f1": 0
        }
        
        print("✅ BoostingEnsemble V3.0 inicializado (integrado com Train V4.0)")
        print(f"   📊 Normalização: Z-Score (StandardScaler)")
        print(f"   🔥 Feature Adaptation: Ativada")
    
    # ==============================================
    # 🔥 NORMALIZAÇÃO (Z-SCORE)
    # ==============================================
    
    def get_scaler(self, scaler_type: str = "standard"):
        """Retorna o scaler apropriado (Z-Score por padrão)"""
        scalers = {
            "standard": StandardScaler(),
            "robust": RobustScaler(),
            "minmax": MinMaxScaler()
        }
        return scalers.get(scaler_type, StandardScaler())
    
    def normalize(self, X: np.ndarray, fit: bool = True) -> np.ndarray:
        """Normaliza dados usando Z-Score (StandardScaler)"""
        if fit or not self.scaler_fitted:
            self.scaler = self.get_scaler(self.scaler_type)
            X_normalized = self.scaler.fit_transform(X)
            self.scaler_fitted = True
        else:
            X_normalized = self.scaler.transform(X)
        return X_normalized
    
    # ==============================================
    # 🔥 ADAPTAÇÃO AUTOMÁTICA DE FEATURES
    # ==============================================
    
    def adapt_features_automatically(
        self, 
        X: np.ndarray,
        expected_features: int = None
    ) -> np.ndarray:
        """
        🔥 ADAPTA QUALQUER NÚMERO DE FEATURES AUTOMATICAMENTE
        """
        if expected_features is None:
            expected_features = self.feature_count or 10
        
        actual = X.shape[1]
        
        # CASO 1: Já tem o número certo
        if actual == expected_features:
            return X
        
        # CASO 2: Mais features → Reduzir
        if actual > expected_features:
            return self._reduce_features(X, actual, expected_features)
        
        # CASO 3: Menos features → Expandir
        if actual < expected_features:
            return self._expand_features(X, actual, expected_features)
        
        return X
    
    def _reduce_features(self, X: np.ndarray, actual: int, expected: int) -> np.ndarray:
        """Reduz número de features"""
        self.stats['feature_adaptations'] += 1
        
        # Estratégia 1: PCA
        try:
            if not self._pca_fitted:
                self._pca = PCA(n_components=min(expected, actual))
                X_reduced = self._pca.fit_transform(X)
                self._pca_fitted = True
            else:
                X_reduced = self._pca.transform(X)
            self.stats['pca_applied'] += 1
            print(f"   ✅ PCA: {actual} → {expected} features")
            return X_reduced
        except Exception as e:
            print(f"   ⚠️ PCA falhou: {e}")
        
        # Estratégia 2: Selecionar primeiras
        X_reduced = X[:, :expected]
        print(f"   ✅ Truncado: {actual} → {expected} features")
        return X_reduced
    
    def _expand_features(self, X: np.ndarray, actual: int, expected: int) -> np.ndarray:
        """Expande número de features"""
        self.stats['feature_adaptations'] += 1
        self.stats['feature_expansions'] += 1
        
        X_expanded = np.zeros((X.shape[0], expected))
        
        # Copiar features existentes
        for i in range(min(actual, expected)):
            X_expanded[:, i] = X[:, i]
        
        # Preencher faltantes
        missing = expected - actual
        if missing > 0:
            col_means = np.mean(X, axis=0)
            col_stds = np.std(X, axis=0) + 1e-10
            mean_all = np.mean(col_means)
            std_all = np.mean(col_stds)
            
            for i in range(missing):
                idx = actual + i
                # Usar média + ruído
                X_expanded[:, idx] = mean_all + std_all * np.random.randn(X.shape[0])
        
        print(f"   ✅ Expandido: {actual} → {expected} features")
        return X_expanded
    
    # ==============================================
    # 🔥 MÉTODO PRINCIPAL - TREINAMENTO
    # ==============================================
    
    def train_sequential_boost(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_models: int = 5,
        test_size: float = 0.2,
        verbose: bool = True,
        normalize: bool = True,
        scaler_type: str = "standard",
        auto_adapt: bool = True
    ) -> Dict[str, Any]:
        """
        Treina modelos sequencialmente, cada um focando nos erros do anterior
        🔥 Usa Z-Score (StandardScaler) para normalização
        🔥 Adaptação automática de features
        """
        print(f"\n{'='*70}")
        print("🚀 INICIANDO BOOSTING ENSEMBLE V3.0")
        print(f"{'='*70}")
        print(f"📊 Dados: {X.shape[0]} amostras, {X.shape[1]} features")
        print(f"🎯 Target: {y.name if hasattr(y, 'name') else 'target'}")
        print(f"🔢 Modelos no ensemble: {n_models}")
        print(f"📊 Normalização: {scaler_type} (Z-Score)")
        print(f"🔥 Auto-Adapt: {auto_adapt}")
        print(f"{'='*70}\n")
        
        # Preparar dados
        X_original = X.copy()
        X = X.select_dtypes(include=[np.number])
        self.feature_names = X.columns.tolist()
        self.feature_count = len(self.feature_names)
        self.scaler_type = scaler_type
        
        print(f"   🔍 Features detectadas: {self.feature_count}")
        
        # 🔥 ADAPTAÇÃO AUTOMÁTICA (se necessário)
        if auto_adapt and hasattr(self, 'model_feature_count') and self.model_feature_count:
            X_values = self.adapt_features_automatically(X.values, self.model_feature_count)
            X = pd.DataFrame(X_values, columns=[f"feature_{i}" for i in range(X_values.shape[1])])
            self.feature_count = X.shape[1]
            print(f"   🔄 Features adaptadas: {self.feature_count}")
        
        # Dividir treino e teste
        stratify = y if len(np.unique(y)) <= 10 else None
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42, stratify=stratify
            )
        except:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42
            )
        
        print(f"📈 Treino: {X_train.shape[0]} amostras")
        print(f"📉 Teste: {X_test.shape[0]} amostras")
        
        # 🔥 NORMALIZAÇÃO Z-SCORE
        if normalize:
            self.scaler = self.get_scaler(scaler_type)
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            self.scaler_fitted = True
            print(f"📊 Z-Score aplicado: média ≈ 0, std ≈ 1")
        else:
            X_train_scaled = X_train.values
            X_test_scaled = X_test.values
        
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
        
        all_train_preds = []
        all_test_preds = []
        
        for i in range(n_models):
            print(f"\n{'─'*50}")
            print(f"🌳 TREINANDO MODELO {i+1}/{n_models}")
            print(f"{'─'*50}")
            
            # CRIAR MODELO APROPRIADO PARA O ESTÁGIO
            if i == 0:
                if is_classification:
                    model = DecisionTreeClassifier(max_depth=3, random_state=42)
                    model_name = "Árvore Simples (estágio 1)"
                else:
                    model = DecisionTreeRegressor(max_depth=3, random_state=42)
                    model_name = "Árvore Simples (estágio 1)"
            
            elif i == 1:
                if is_classification:
                    model = AdaBoostClassifier(n_estimators=50, learning_rate=0.8, random_state=42)
                    model_name = "AdaBoost (foco nos erros)"
                else:
                    model = AdaBoostRegressor(n_estimators=50, learning_rate=0.8, random_state=42)
                    model_name = "AdaBoost (foco nos erros)"
            
            elif i == 2:
                if is_classification:
                    model = GradientBoostingClassifier(
                        n_estimators=100, learning_rate=0.1, max_depth=4, 
                        subsample=0.8, random_state=42
                    )
                    model_name = "GradientBoosting (aprendizado profundo)"
                else:
                    model = GradientBoostingRegressor(
                        n_estimators=100, learning_rate=0.1, max_depth=4,
                        subsample=0.8, random_state=42
                    )
                    model_name = "GradientBoosting (aprendizado profundo)"
            
            else:
                if is_classification:
                    model = RandomForestClassifier(
                        n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
                    )
                else:
                    model = RandomForestRegressor(
                        n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
                    )
                model_name = f"RandomForest (estágio {i+1})"
            
            # TREINAR COM PESOS (foco nos erros anteriores)
            try:
                if hasattr(model, 'fit') and 'sample_weight' in model.fit.__code__.co_varnames:
                    model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
                else:
                    model.fit(X_train_scaled, y_train)
            except:
                model.fit(X_train_scaled, y_train)
            
            # FAZER PREVISÕES
            y_train_pred = model.predict(X_train_scaled)
            y_test_pred = model.predict(X_test_scaled)
            
            all_train_preds.append(y_train_pred)
            all_test_preds.append(y_test_pred)
            
            # CALCULAR ERROS
            if is_classification:
                errors = (y_train_pred != y_train).astype(int)
                error_rate = errors.mean()
                train_acc = accuracy_score(y_train, y_train_pred)
                test_acc = accuracy_score(y_test, y_test_pred)
                train_f1 = f1_score(y_train, y_train_pred, average='weighted', zero_division=0)
                test_f1 = f1_score(y_test, y_test_pred, average='weighted', zero_division=0)
                train_precision = precision_score(y_train, y_train_pred, average='weighted', zero_division=0)
                test_precision = precision_score(y_test, y_test_pred, average='weighted', zero_division=0)
                
                if verbose:
                    print(f"\n📊 Modelo: {model_name}")
                    print(f"   Acurácia treino: {train_acc:.2%}")
                    print(f"   Acurácia teste: {test_acc:.2%}")
                    print(f"   F1-Score: {test_f1:.3f}")
                    print(f"   Precisão: {test_precision:.3f}")
                    print(f"   Taxa de erro: {error_rate:.2%}")
                
                y_train_pred_ensemble += y_train_pred
                y_test_pred_ensemble += y_test_pred
                train_score = train_acc
                test_score = test_acc
                
            else:
                errors = np.abs(y_train - y_train_pred)
                error_rate = errors.mean() / (y_train.std() + 1e-10)
                train_mse = mean_squared_error(y_train, y_train_pred)
                test_mse = mean_squared_error(y_test, y_test_pred)
                train_rmse = np.sqrt(train_mse)
                test_rmse = np.sqrt(test_mse)
                train_r2 = r2_score(y_train, y_train_pred)
                test_r2 = r2_score(y_test, y_test_pred)
                
                if verbose:
                    print(f"\n📊 Modelo: {model_name}")
                    print(f"   MSE treino: {train_mse:.4f}")
                    print(f"   MSE teste: {test_mse:.4f}")
                    print(f"   RMSE: {test_rmse:.4f}")
                    print(f"   R²: {test_r2:.4f}")
                    print(f"   Erro relativo: {error_rate:.2%}")
                
                y_train_pred_ensemble += y_train_pred
                y_test_pred_ensemble += y_test_pred
                train_score = -train_mse
                test_score = -test_mse
            
            # ATUALIZAR PESOS (aprender com os erros)
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
            
            # Extrair importância das features (se disponível)
            if hasattr(model, 'feature_importances_'):
                feature_importance = model.feature_importances_.tolist()
                self.feature_importance_history.append({
                    'stage': i+1,
                    'model': model_name,
                    'importances': feature_importance
                })
            
            # GUARDAR HISTÓRICO
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
        
        # ENSEMBLE FINAL
        print(f"\n{'='*50}")
        print("🏆 RESULTADO DO ENSEMBLE FINAL")
        print(f"{'='*50}")
        
        if is_classification:
            ensemble_train_pred = np.round(y_train_pred_ensemble / n_models).astype(int)
            ensemble_test_pred = np.round(y_test_pred_ensemble / n_models).astype(int)
            
            ensemble_train_acc = accuracy_score(y_train, ensemble_train_pred)
            ensemble_test_acc = accuracy_score(y_test, ensemble_test_pred)
            ensemble_f1 = f1_score(y_test, ensemble_test_pred, average='weighted', zero_division=0)
            ensemble_precision = precision_score(y_test, ensemble_test_pred, average='weighted', zero_division=0)
            ensemble_recall = recall_score(y_test, ensemble_test_pred, average='weighted', zero_division=0)
            
            print(f"\n📊 Ensemble Final ({n_models} modelos):")
            print(f"   Acurácia treino: {ensemble_train_acc:.2%}")
            print(f"   Acurácia teste: {ensemble_test_acc:.2%}")
            print(f"   F1-Score: {ensemble_f1:.3f}")
            print(f"   Precisão: {ensemble_precision:.3f}")
            print(f"   Recall: {ensemble_recall:.3f}")
            
            first_model_acc = self.models[0]['test_score']
            improvement = ensemble_test_acc - first_model_acc
            print(f"   Melhoria vs 1º modelo: +{improvement:.2%}")
            
            best_score = ensemble_test_acc
            conf_matrix = confusion_matrix(y_test, ensemble_test_pred).tolist()
            
            metrics = {
                'accuracy': float(ensemble_test_acc),
                'f1_score': float(ensemble_f1),
                'precision': float(ensemble_precision),
                'recall': float(ensemble_recall),
                'improvement': float(improvement),
                'confusion_matrix': conf_matrix,
                'is_classification': True
            }
            
            self.stats['best_accuracy'] = max(self.stats['best_accuracy'], ensemble_test_acc)
            self.stats['best_f1'] = max(self.stats['best_f1'], ensemble_f1)
            
        else:
            ensemble_train_pred = y_train_pred_ensemble / n_models
            ensemble_test_pred = y_test_pred_ensemble / n_models
            
            ensemble_train_mse = mean_squared_error(y_train, ensemble_train_pred)
            ensemble_test_mse = mean_squared_error(y_test, ensemble_test_pred)
            ensemble_rmse = np.sqrt(ensemble_test_mse)
            ensemble_r2 = r2_score(y_test, ensemble_test_pred)
            ensemble_mae = mean_absolute_error(y_test, ensemble_test_pred)
            
            print(f"\n📊 Ensemble Final ({n_models} modelos):")
            print(f"   MSE treino: {ensemble_train_mse:.4f}")
            print(f"   MSE teste: {ensemble_test_mse:.4f}")
            print(f"   RMSE: {ensemble_rmse:.4f}")
            print(f"   R²: {ensemble_r2:.4f}")
            print(f"   MAE: {ensemble_mae:.4f}")
            
            best_score = -ensemble_test_mse
            conf_matrix = None
            
            metrics = {
                'mse': float(ensemble_test_mse),
                'rmse': float(ensemble_rmse),
                'r2_score': float(ensemble_r2),
                'mae': float(ensemble_mae),
                'is_classification': False
            }
        
        # Guardar melhor modelo
        self.best_model = {
            'models': [m['model'] for m in self.models],
            'weights': self.model_weights,
            'scaler': self.scaler,
            'scaler_type': self.scaler_type,
            'is_classification': is_classification,
            'n_models': n_models,
            'feature_names': self.feature_names,
            'feature_count': self.feature_count,
            'normalization': f'{scaler_type} (Z-Score)',
            'version': '3.0'
        }
        self.best_score = best_score
        self.model_feature_count = self.feature_count
        
        # Salvar métricas
        self.last_training_metrics = {
            **metrics,
            'n_models': n_models,
            'normalization': f'{scaler_type} (Z-Score)',
            'feature_count': self.feature_count
        }
        
        # Salvar resultados
        self._save_results(is_classification)
        
        self.stats['total_trainings'] += 1
        self.stats['successful_trainings'] += 1
        
        print(f"\n✅ Ensemble treinado com sucesso!")
        print(f"   📊 Features: {self.feature_count}")
        print(f"   📊 Normalização: {scaler_type} (Z-Score)")
        print(f"   🔥 Auto-Adapt: {auto_adapt}")
        
        return {
            'models': self.models,
            'model_weights': self.model_weights,
            'errors_history': self.errors_history,
            'accuracy_history': self.accuracy_history if is_classification else None,
            'ensemble_test_score': ensemble_test_acc if is_classification else ensemble_test_mse,
            'improvement': improvement if is_classification else None,
            'is_classification': is_classification,
            'confusion_matrix': conf_matrix,
            'feature_importance_history': self.feature_importance_history,
            'metrics': metrics,
            'normalization': f'{scaler_type} (Z-Score)',
            'feature_count': self.feature_count
        }
    
    # ==============================================
    # 🔥 VALIDAÇÃO CRUZADA
    # ==============================================
    
    def train_with_cross_validation(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_folds: int = 10,
        n_models: int = 5,
        normalize: bool = True,
        scaler_type: str = "standard"
    ) -> Dict[str, Any]:
        """
        Treina com validação cruzada K-Fold
        🔥 Usa Z-Score (StandardScaler)
        """
        print(f"\n{'='*70}")
        print(f"🔬 TREINANDO COM K-FOLD ({n_folds} FOLDS)")
        print(f"{'='*70}")
        print(f"📊 Normalização: {scaler_type} (Z-Score)")
        
        X = X.select_dtypes(include=[np.number])
        self.feature_names = X.columns.tolist()
        self.feature_count = len(self.feature_names)
        
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
                    verbose=False,
                    normalize=normalize,
                    scaler_type=scaler_type
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
    
    # ==============================================
    # 🔥 PREDIÇÃO (COM ADAPTAÇÃO AUTOMÁTICA)
    # ==============================================
    
    def predict(self, X: pd.DataFrame, auto_adapt: bool = True) -> np.ndarray:
        """
        Faz previsões usando o ensemble
        🔥 Com adaptação automática de features
        """
        if self.best_model is None:
            raise ValueError("Nenhum modelo treinado. Execute train_sequential_boost primeiro.")
        
        X = X.select_dtypes(include=[np.number])
        
        # 🔥 ADAPTAÇÃO AUTOMÁTICA
        if auto_adapt and self.best_model.get('feature_count'):
            X_values = self.adapt_features_automatically(X.values, self.best_model['feature_count'])
            X = pd.DataFrame(X_values, columns=[f"feature_{i}" for i in range(X_values.shape[1])])
        
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
            predictions = np.clip(predictions, 0, 1)
        
        return predictions
    
    def predict_proba_ensemble(self, X: pd.DataFrame, auto_adapt: bool = True) -> np.ndarray:
        """
        Retorna probabilidades do ensemble (para classificação)
        🔥 Com adaptação automática de features
        """
        if self.best_model is None or not self.best_model['is_classification']:
            raise ValueError("Ensemble não configurado para classificação")
        
        X = X.select_dtypes(include=[np.number])
        
        # 🔥 ADAPTAÇÃO AUTOMÁTICA
        if auto_adapt and self.best_model.get('feature_count'):
            X_values = self.adapt_features_automatically(X.values, self.best_model['feature_count'])
            X = pd.DataFrame(X_values, columns=[f"feature_{i}" for i in range(X_values.shape[1])])
        
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
    
    # ==============================================
    # 🔥 MÉTRICAS PARA GEMINI
    # ==============================================
    
    def get_ensemble_metrics_for_gemini(self) -> Dict[str, Any]:
        """
        Retorna métricas detalhadas do ensemble para o Gemini
        🔥 Versão aprimorada com mais métricas
        """
        if not self.models:
            return {
                "status": "sem_modelos", 
                "mensagem": "Nenhum ensemble foi treinado ainda",
                "recomendacao": "Execute train_sequential_boost primeiro"
            }
        
        # Calcular métricas do ensemble
        total_models = len(self.models)
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
                overfitting_gap = train_scores[-1] - test_scores[-1] if train_scores and test_scores else 0
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
                min_len = min(len(feature_names), len(all_importances[0]) if all_importances else 0)
                if min_len > 0:
                    avg_importances = np.mean([imp[:min_len] for imp in all_importances], axis=0)
                    for i, name in enumerate(feature_names[:min_len]):
                        feature_importance_avg[name] = float(avg_importances[i])
                    
                    feature_importance_avg = dict(sorted(feature_importance_avg.items(), key=lambda x: x[1], reverse=True))
        
        # Métricas principais
        is_classification = self.best_model.get('is_classification', True)
        main_metric = self.last_training_metrics.get('accuracy', 0) if is_classification else self.last_training_metrics.get('r2_score', 0)
        
        metrics = {
            "status": "treinado",
            "tipo_ensemble": "Boosting Sequencial",
            "total_modelos": total_models,
            "taxa_erro_inicial": float(initial_error),
            "taxa_erro_final": float(final_error),
            "melhoria_erro": float(improvement),
            "melhoria_percentual": float(improvement / (initial_error + 1e-10) * 100) if initial_error > 0 else 0,
            "convergencia": {
                "atingiu_convergencia": is_converged,
                "taxa_convergencia": float(convergence_rate),
                "status": "Estável" if is_converged else "Melhorando" if convergence_rate > 0 else "Instável"
            },
            "risco_overfitting": overfitting_risk,
            "pesos_modelos": [float(w) for w in self.model_weights],
            "importancia_features": feature_importance_avg,
            "feature_count": self.best_model.get('feature_count', 0),
            "normalization": self.best_model.get('normalization', 'Z-Score'),
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
            "performance_ensemble": self.last_training_metrics,
            "metrica_principal": float(main_metric),
            "is_classification": is_classification
        }
        
        return metrics
    
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
    
    # ==============================================
    # 🔥 INTEGRAÇÃO COM PREDICTOR V7.0
    # ==============================================
    
    def integrate_with_predictor(self):
        """
        Integra o melhor ensemble com o predictor V7.0
        ✅ Salva no formato compatível com train.py V4.0 e predict.py V7.0
        """
        if self.best_model is None:
            print("❌ Nenhum modelo treinado para integrar")
            return False
        
        try:
            is_classification = self.best_model['is_classification']
            metrics = self.last_training_metrics or {}
            
            # 🔥 FORMATO COMPATÍVEL COM TRAIN.PY V4.0 E PREDICT.PY V7.0
            model_data = {
                'ensemble': self.best_model,
                'models': self.models,
                'model_weights': self.model_weights,
                'type': 'boosting_ensemble',
                'model_name': 'BoostingEnsemble_V3.0',
                'model_type': 'classifier' if is_classification else 'regressor',
                'trained_date': datetime.now().isoformat(),
                'version': '3.0',
                'metrics': metrics,
                'features': self.feature_names,
                'feature_count': self.feature_count,
                'normalization': self.best_model.get('normalization', 'Z-Score (StandardScaler)'),
                'scaler': self.scaler,
                'scaler_type': self.scaler_type,
                'is_classification': is_classification,
                'n_models': len(self.models),
                'best_score': self.best_score
            }
            
            # Salvar no formato do predictor V7.0
            model_path = os.path.join("backend", "ml", "models", "trained_model.pkl")
            joblib.dump(model_data, model_path)
            
            # Também salvar como office_model.pkl para compatibilidade
            office_path = os.path.join("backend", "ml", "models", "office_model.pkl")
            joblib.dump(model_data, office_path)
            
            print(f"\n✅ Ensemble salvo em: {model_path}")
            print(f"   📊 Features: {self.feature_count}")
            print(f"   📊 Normalização: {self.best_model.get('normalization', 'Z-Score')}")
            print(f"   🔥 Compatível com train.py V4.0 e predict.py V7.0")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro na integração: {e}")
            return False
    
    # ==============================================
    # 🔥 SALVAR RESULTADOS
    # ==============================================
    
    def _save_results(self, is_classification: bool):
        """Salva resultados do treinamento (compatível com V7.0)"""
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
            'feature_importance_history': self.feature_importance_history,
            'feature_count': self.feature_count,
            'feature_names': self.feature_names,
            'normalization': self.best_model.get('normalization', 'Z-Score (StandardScaler)'),
            'version': '3.0',
            'stats': self.stats
        }, model_path)
        
        print(f"\n💾 Ensemble salvo em: {model_path}")
        
        self.training_log.append({
            'timestamp': timestamp,
            'n_models': len(self.models),
            'best_score': self.best_score,
            'is_classification': is_classification,
            'final_error': self.errors_history[-1] if self.errors_history else None,
            'feature_count': self.feature_count
        })
    
    # ==============================================
    # 🔥 GRÁFICO DE APRENDIZADO
    # ==============================================
    
    def plot_learning_curve(self):
        """Plota curva de aprendizado do ensemble"""
        try:
            import matplotlib.pyplot as plt
            
            plt.figure(figsize=(15, 5))
            
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
    
    # ==============================================
    # 🔥 UTILITÁRIOS
    # ==============================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do ensemble"""
        return {
            **self.stats,
            "total_models": len(self.models),
            "feature_count": self.feature_count,
            "normalization": self.scaler_type,
            "best_score": self.best_score,
            "is_trained": self.best_model is not None,
            "is_classification": self.best_model.get('is_classification') if self.best_model else None
        }
    
    def reset(self):
        """Reseta o ensemble"""
        self.models = []
        self.model_weights = []
        self.errors_history = []
        self.accuracy_history = []
        self.best_model = None
        self.best_score = 0
        self.scaler = StandardScaler()
        self.scaler_fitted = False
        self._pca = None
        self._pca_fitted = False
        self.training_log = []
        self.last_training_metrics = None
        self.feature_importance_history = []
        print("🔄 Ensemble resetado")


# Instância global
boosting_ensemble = BoostingEnsemble()

print("\n✅ BoostingEnsemble V3.0 pronto!")
print("   📊 Usa Z-Score (StandardScaler)")
print("   🔥 Feature Adaptation: Ativada")
print("   🔥 Integrado com train.py V4.0 e predict.py V7.0")
print("   📊 Métodos disponíveis:")
print("      • train_sequential_boost(X, y, n_models=5)")
print("      • predict(X, auto_adapt=True)")
print("      • predict_proba_ensemble(X)")
print("      • integrate_with_predictor()")
print("      • get_ensemble_metrics_for_gemini()")