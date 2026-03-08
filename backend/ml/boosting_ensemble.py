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
    accuracy_score, mean_squared_error
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
        
        # Pesos das amostras (inicialmente uniformes) - CORREÇÃO LINHA 98
        sample_weights = np.ones(len(X_train)) / len(X_train)
        
        # Para tracking
        y_train_pred_ensemble = np.zeros(len(X_train))
        y_test_pred_ensemble = np.zeros(len(X_test))
        
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
                        random_state=42
                    )
                else:
                    model = RandomForestRegressor(
                        n_estimators=100,
                        max_depth=10,
                        random_state=42
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
            
            # 4. CALCULAR ERROS
            if is_classification:
                # Para classificação: 0 = acertou, 1 = errou
                errors = (y_train_pred != y_train).astype(int)
                error_rate = errors.mean()
                
                # Acurácia
                train_acc = accuracy_score(y_train, y_train_pred)
                test_acc = accuracy_score(y_test, y_test_pred)
                
                if verbose:
                    print(f"\n📊 Modelo: {model_name}")
                    print(f"   Acurácia treino: {train_acc:.2%}")
                    print(f"   Acurácia teste: {test_acc:.2%}")
                    print(f"   Taxa de erro: {error_rate:.2%}")
                
                # Acumular previsões para ensemble
                y_train_pred_ensemble += y_train_pred
                y_test_pred_ensemble += y_test_pred
                
            else:
                # Para regressão: erro absoluto
                errors = np.abs(y_train - y_train_pred)
                error_rate = errors.mean() / (y_train.std() + 1e-10)
                
                # Métricas
                train_mse = mean_squared_error(y_train, y_train_pred)
                test_mse = mean_squared_error(y_test, y_test_pred)
                
                if verbose:
                    print(f"\n📊 Modelo: {model_name}")
                    print(f"   MSE treino: {train_mse:.4f}")
                    print(f"   MSE teste: {test_mse:.4f}")
                    print(f"   Erro relativo: {error_rate:.2%}")
                
                # Acumular previsões
                y_train_pred_ensemble += y_train_pred
                y_test_pred_ensemble += y_test_pred
            
            # 5. ATUALIZAR PESOS (aprender com os erros)
            # Amostras com erro recebem peso maior
            if error_rate > 0 and error_rate < 0.5:  # Evitar pesos extremos
                # Calcular novo peso baseado no erro
                model_weight = np.log((1 - error_rate) / max(error_rate, 1e-10)) / 2
                
                # Atualizar pesos das amostras
                if is_classification:
                    # Aumentar peso das amostras erradas
                    sample_weights = sample_weights * np.exp(model_weight * errors)
                else:
                    # Aumentar peso das amostras com maior erro
                    if errors.max() > 0:
                        sample_weights = sample_weights * np.exp(model_weight * (errors / errors.max()))
                
                # Normalizar
                sample_weights = sample_weights / (sample_weights.sum() + 1e-10)
                
                # Guardar peso do modelo
                self.model_weights.append(model_weight)
            else:
                self.model_weights.append(0.5)  # Peso padrão
            
            # 6. GUARDAR HISTÓRICO
            self.models.append({
                'model': model,
                'name': model_name,
                'stage': i+1,
                'error_rate': error_rate,
                'train_score': train_acc if is_classification else train_mse,
                'test_score': test_acc if is_classification else test_mse,
                'weight': self.model_weights[-1]
            })
            
            self.errors_history.append(error_rate)
            if is_classification:
                self.accuracy_history.append(test_acc)
        
        # 7. ENSEMBLE FINAL (votação ponderada)
        print(f"\n{'='*50}")
        print("🏆 RESULTADO DO ENSEMBLE FINAL")
        print(f"{'='*50}")
        
        if is_classification:
            # Votação majoritária ponderada
            ensemble_train_pred = np.round(y_train_pred_ensemble / n_models).astype(int)
            ensemble_test_pred = np.round(y_test_pred_ensemble / n_models).astype(int)
            
            ensemble_train_acc = accuracy_score(y_train, ensemble_train_pred)
            ensemble_test_acc = accuracy_score(y_test, ensemble_test_pred)
            
            print(f"\n📊 Ensemble Final ({n_models} modelos):")
            print(f"   Acurácia treino: {ensemble_train_acc:.2%}")
            print(f"   Acurácia teste: {ensemble_test_acc:.2%}")
            
            # Melhoria em relação ao primeiro modelo
            first_model_acc = self.models[0]['test_score']
            improvement = ensemble_test_acc - first_model_acc
            print(f"   Melhoria vs 1º modelo: +{improvement:.2%}")
            
            best_score = ensemble_test_acc
        else:
            # Média ponderada para regressão
            ensemble_train_pred = y_train_pred_ensemble / n_models
            ensemble_test_pred = y_test_pred_ensemble / n_models
            
            ensemble_train_mse = mean_squared_error(y_train, ensemble_train_pred)
            ensemble_test_mse = mean_squared_error(y_test, ensemble_test_pred)
            
            print(f"\n📊 Ensemble Final ({n_models} modelos):")
            print(f"   MSE treino: {ensemble_train_mse:.4f}")
            print(f"   MSE teste: {ensemble_test_mse:.4f}")
            
            best_score = -ensemble_test_mse
        
        # Guardar melhor modelo (o ensemble)
        self.best_model = {
            'models': [m['model'] for m in self.models],
            'weights': self.model_weights,
            'scaler': self.scaler,
            'is_classification': is_classification,
            'n_models': n_models
        }
        self.best_score = best_score
        
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
            'is_classification': is_classification
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
        
        for fold, (train_idx, val_idx) in enumerate(kfold.split(X), 1):
            print(f"\n📁 Fold {fold}/{n_folds}")
            
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
            
            # Treinar ensemble neste fold
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
            except Exception as e:
                print(f"   ⚠️ Erro no fold {fold}: {e}")
                continue
        
        if not fold_results:
            print("❌ Nenhum fold foi treinado com sucesso")
            return {'fold_results': [], 'mean_score': 0, 'std_score': 0, 'all_scores': []}
        
        # Resultados consolidados
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
        
        # Acumular previsões de todos os modelos
        predictions = np.zeros(len(X))
        total_weight = sum(self.best_model['weights'])
        
        if total_weight == 0:
            total_weight = 1
        
        for i, model_data in enumerate(self.best_model['models']):
            model_pred = model_data.predict(X_scaled)
            weight = self.best_model['weights'][i]
            predictions += model_pred * weight
        
        # Normalizar pelos pesos
        predictions = predictions / total_weight
        
        if self.best_model['is_classification']:
            # Arredondar para classificação
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
        
        # Acumular probabilidades
        probas = np.zeros((len(X), 2))
        total_weight = sum(self.best_model['weights'])
        
        if total_weight == 0:
            total_weight = 1
        
        for i, model_data in enumerate(self.best_model['models']):
            if hasattr(model_data, 'predict_proba'):
                model_proba = model_data.predict_proba(X_scaled)
                weight = self.best_model['weights'][i]
                probas += model_proba * weight
        
        # Normalizar
        if probas.sum() > 0:
            probas = probas / total_weight
        
        return probas
    
    def _save_results(self, is_classification: bool):
        """Salva resultados do treinamento"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Salvar modelo
        model_path = os.path.join(self.models_dir, f"ensemble_{timestamp}.pkl")
        joblib.dump({
            'best_model': self.best_model,
            'models': [(m['name'], m['stage']) for m in self.models],
            'model_weights': self.model_weights,
            'errors_history': self.errors_history,
            'accuracy_history': self.accuracy_history if is_classification else None,
            'is_classification': is_classification,
            'timestamp': timestamp
        }, model_path)
        
        print(f"\n💾 Ensemble salvo em: {model_path}")
        
        # Log
        self.training_log.append({
            'timestamp': timestamp,
            'n_models': len(self.models),
            'best_score': self.best_score,
            'is_classification': is_classification
        })
    
    def plot_learning_curve(self):
        """Plota curva de aprendizado do ensemble"""
        try:
            import matplotlib.pyplot as plt
            
            plt.figure(figsize=(12, 4))
            
            # Erros ao longo do treinamento
            plt.subplot(1, 2, 1)
            plt.plot(range(1, len(self.errors_history)+1), self.errors_history, 'bo-')
            plt.xlabel('Estágio do Modelo')
            plt.ylabel('Taxa de Erro')
            plt.title('Evolução dos Erros')
            plt.grid(True)
            
            # Acurácia (se disponível)
            if self.accuracy_history:
                plt.subplot(1, 2, 2)
                plt.plot(range(1, len(self.accuracy_history)+1), self.accuracy_history, 'go-')
                plt.xlabel('Estágio do Modelo')
                plt.ylabel('Acurácia')
                plt.title('Evolução da Acurácia')
                plt.grid(True)
            
            plt.tight_layout()
            
            # Salvar figura
            plot_path = os.path.join(self.models_dir, f"learning_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plt.savefig(plot_path)
            print(f"📈 Curva de aprendizado salva em: {plot_path}")
            
            plt.show()
            
        except Exception as e:
            print(f"⚠️ Não foi possível gerar gráfico: {e}")
    
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
                'Score Treino': f"{m['train_score']:.4f}",
                'Score Teste': f"{m['test_score']:.4f}",
                'Peso': f"{m['weight']:.4f}"
            })
        
        return pd.DataFrame(summary)
    
    def integrate_with_predictor(self):
        """Integra o melhor ensemble com o predictor existente"""
        if self.best_model is None:
            print("❌ Nenhum modelo treinado para integrar")
            return False
        
        try:
            # Salvar no formato do predictor
            model_data = {
                'ensemble': self.best_model,
                'models': self.models,
                'model_weights': self.model_weights,
                'type': 'boosting_ensemble',
                'trained_date': datetime.now().isoformat()
            }
            
            model_path = os.path.join("backend", "ml", "models", "office_model.pkl")
            joblib.dump(model_data, model_path)
            
            print(f"\n✅ Ensemble integrado com predictor em: {model_path}")
            return True
            
        except Exception as e:
            print(f"❌ Erro na integração: {e}")
            return False


# Instância global
boosting_ensemble = BoostingEnsemble()

print("\n✅ BoostingEnsemble pronto para uso!")  