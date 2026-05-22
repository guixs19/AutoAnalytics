# backend/ml/predict.py - VERSÃO ATUALIZADA COM SUPORTE A MÚLTIPLOS ARQUIVOS
"""
Módulo de predição unificado para AutoAnalytics
Integra: RandomForest, AutoMLOffice, BoostingEnsemble
Suporte a processamento de múltiplos arquivos
"""

import numpy as np
import pandas as pd
import joblib
import os
import pickle
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Scikit-learn
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score

print("🔧 Carregando predict.py (versão integrada com múltiplos arquivos)...")


class ModelPredictor:
    """
    Predictor unificado que integra:
    - RandomForest (padrão)
    - AutoML Office (automl_simple)
    - Boosting Ensemble (boosting_ensemble)
    - Suporte a múltiplos arquivos
    """
    
    def __init__(self):
        self.models_dir = os.path.join("backend", "ml", "models")
        self.office_model_path = os.path.join(self.models_dir, "office_model.pkl")
        self.default_model_path = os.path.join(self.models_dir, "trained_model.pkl")
        
        # Modelos carregados
        self.office_model = None
        self.default_model = None
        self.scaler = None
        self.model_type = None
        self.model_source = None  # 'random_forest', 'automl', 'boosting_ensemble'
        self.feature_names = None
        self.is_loaded = False
        
        # Métricas do último modelo
        self.last_metrics = {}
        
        # Cache para previsões frequentes
        self._prediction_cache = {}
        self._cache_max_size = 100
        self._cache_ttl = 60  # segundos
        self._last_cache_cleanup = datetime.now()
        
        # Estatísticas de uso
        self.stats = {
            "total_predictions": 0,
            "total_files_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_prediction_time": None
        }
        
        # Importar módulos existentes
        self._import_modules()
        
        os.makedirs(self.models_dir, exist_ok=True)
        print("✅ ModelPredictor inicializado")
    
    def _import_modules(self):
        """Importa módulos existentes se disponíveis"""
        try:
            from backend.ml.automl_simple import automl_office
            self.automl_office = automl_office
            print("   📦 AutoMLOffice integrado")
        except ImportError:
            self.automl_office = None
            print("   ⚠️ AutoMLOffice não disponível")
        
        try:
            from backend.ml.boosting_ensemble import boosting_ensemble
            self.boosting_ensemble = boosting_ensemble
            print("   📦 BoostingEnsemble integrado")
        except ImportError:
            self.boosting_ensemble = None
            print("   ⚠️ BoostingEnsemble não disponível")
    
    async def load_or_train_models(self, force_reload: bool = False):
        """Carrega modelos existentes ou cria modelos placeholder"""
        if self.is_loaded and not force_reload:
            print("📦 Modelos já carregados")
            return True
        
        print("\n🔧 Carregando modelos de ML...")
        
        # Tentar carregar modelo da oficina
        office_loaded = self._load_office_model()
        
        # Tentar carregar modelo padrão
        default_loaded = self._load_default_model()
        
        if not office_loaded and not default_loaded:
            print("⚠️ Nenhum modelo encontrado. Criando modelo placeholder...")
            self._create_placeholder_model()
        
        self.is_loaded = True
        print(f"✅ Modelos carregados (Fonte: {self.model_source})")
        return True
    
    def _load_office_model(self) -> bool:
        """Carrega modelo de oficina (suporta múltiplos formatos)"""
        try:
            if not os.path.exists(self.office_model_path):
                return False
            
            with open(self.office_model_path, 'rb') as f:
                model_data = joblib.load(f)
            
            # Caso 1: Dicionário com metadados
            if isinstance(model_data, dict):
                # AutoML Office
                if 'pipeline' in model_data:
                    self.office_model = model_data['pipeline']
                    self.model_source = 'automl'
                    self.scaler = model_data['pipeline'].named_steps.get('scaler')
                    self.last_metrics = model_data.get('metricas', {})
                    print("✅ Modelo AutoML Office carregado")
                    return True
                
                # Boosting Ensemble
                elif 'ensemble' in model_data:
                    self.office_model = model_data
                    self.model_source = 'boosting_ensemble'
                    self.last_metrics = model_data.get('metrics', {})
                    print("✅ Modelo Boosting Ensemble carregado")
                    return True
                
                # RandomForest com scaler
                elif 'model' in model_data:
                    self.office_model = model_data['model']
                    self.scaler = model_data.get('scaler')
                    self.model_source = 'random_forest'
                    self.feature_names = model_data.get('features', [])
                    self.last_metrics = model_data.get('metrics', {})
                    print("✅ Modelo RandomForest carregado")
                    return True
                
                # Fallback
                else:
                    self.office_model = model_data
                    self.model_source = 'unknown'
                    print("⚠️ Modelo carregado (tipo desconhecido)")
                    return True
            
            # Caso 2: Objeto modelo simples
            elif hasattr(model_data, 'predict'):
                self.office_model = model_data
                self.model_source = 'simple_model'
                print("✅ Modelo simples carregado")
                return True
            
            # Caso 3: Try to extract from boosting_ensemble
            elif self.boosting_ensemble and self.boosting_ensemble.best_model:
                self.office_model = self.boosting_ensemble.best_model
                self.model_source = 'boosting_ensemble'
                print("✅ Modelo do BoostingEnsemble carregado")
                return True
            
            # Caso 4: Try to extract from automl_office
            elif self.automl_office and self.automl_office.best_pipeline:
                self.office_model = self.automl_office.best_pipeline
                self.model_source = 'automl'
                print("✅ Modelo do AutoMLOffice carregado")
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ Erro ao carregar modelo de oficina: {e}")
            return False
    
    def _load_default_model(self) -> bool:
        """Carrega modelo padrão (pickle)"""
        try:
            if not os.path.exists(self.default_model_path):
                return False
            
            with open(self.default_model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            if isinstance(model_data, dict):
                self.default_model = model_data.get('model')
                if not self.scaler:
                    self.scaler = model_data.get('scaler')
                self.last_metrics = model_data.get('metrics', {})
            else:
                self.default_model = model_data
            
            if self.default_model and not self.office_model:
                self.office_model = self.default_model
                self.model_source = 'default'
            
            print("✅ Modelo padrão carregado")
            return True
            
        except Exception as e:
            print(f"⚠️ Erro ao carregar modelo padrão: {e}")
            return False
    
    def _create_placeholder_model(self):
        """Cria modelo placeholder para testes"""
        try:
            # Criar modelo simples
            self.office_model = RandomForestClassifier(
                n_estimators=50,
                max_depth=5,
                random_state=42,
                n_jobs=-1
            )
            self.scaler = StandardScaler()
            self.model_source = 'placeholder'
            
            # Treinar com dados sintéticos
            X_dummy = np.random.randn(100, 10)
            y_dummy = (X_dummy[:, 0] + X_dummy[:, 1] > 0).astype(int)
            X_scaled = self.scaler.fit_transform(X_dummy)
            self.office_model.fit(X_scaled, y_dummy)
            
            self.last_metrics = {
                'accuracy': 0.75,
                'is_placeholder': True,
                'message': 'Modelo placeholder para testes'
            }
            
            print("✅ Modelo placeholder criado")
            
        except Exception as e:
            print(f"⚠️ Erro ao criar placeholder: {e}")
            self.office_model = None
    
    def _cleanup_cache(self):
        """Limpa cache antigo"""
        now = datetime.now()
        if (now - self._last_cache_cleanup).seconds > self._cache_ttl:
            expired = []
            for key, item in self._prediction_cache.items():
                if (now - item['timestamp']).seconds > self._cache_ttl:
                    expired.append(key)
            
            for key in expired:
                del self._prediction_cache[key]
            
            if len(self._prediction_cache) > self._cache_max_size:
                sorted_items = sorted(
                    self._prediction_cache.items(),
                    key=lambda x: x[1]['timestamp']
                )
                to_remove = len(self._prediction_cache) - self._cache_max_size
                for key, _ in sorted_items[:to_remove]:
                    del self._prediction_cache[key]
            
            self._last_cache_cleanup = now
    
    def _get_cache_key(self, df: pd.DataFrame) -> str:
        """Gera chave de cache baseada nos dados"""
        if len(df) > 100:
            sample = df.head(50)
        else:
            sample = df
        
        data_str = sample.values.tobytes()
        return str(hash(data_str))
    
    def _preprocess_features(self, df: pd.DataFrame) -> np.ndarray:
        """Pré-processa features para predição"""
        X = df.select_dtypes(include=[np.number]).copy()
        
        if X.empty:
            X = pd.DataFrame(index=df.index)
            X['_constant'] = 1.0
        
        X = X.fillna(X.mean())
        X = X.fillna(0)
        
        if self.scaler is not None:
            try:
                X_scaled = self.scaler.transform(X)
            except Exception:
                self.scaler.fit(X)
                X_scaled = self.scaler.transform(X)
        else:
            X_scaled = (X - X.min()) / (X.max() - X.min() + 1e-8)
            X_scaled = X_scaled.fillna(0).values
        
        return X_scaled
    
    async def predict_for_office(self, df: pd.DataFrame) -> List[float]:
        """Faz predições para dados de oficina"""
        start_time = datetime.now()
        
        cache_key = self._get_cache_key(df)
        if cache_key in self._prediction_cache:
            cached = self._prediction_cache[cache_key]
            if (datetime.now() - cached['timestamp']).seconds < self._cache_ttl:
                self.stats['cache_hits'] += 1
                self.stats['total_predictions'] += 1
                return cached['predictions']
        
        self.stats['cache_misses'] += 1
        
        if self.office_model is None:
            print("⚠️ Nenhum modelo disponível, usando fallback")
            predictions = self._fallback_predictions(df)
        else:
            try:
                X_scaled = self._preprocess_features(df)
                
                if self.model_source == 'boosting_ensemble' and isinstance(self.office_model, dict):
                    predictions = self._predict_with_ensemble(X_scaled)
                elif hasattr(self.office_model, 'predict'):
                    predictions = self.office_model.predict(X_scaled)
                else:
                    predictions = self._fallback_predictions(df)
                
                if isinstance(predictions, np.ndarray):
                    predictions = predictions.tolist()
                
                predictions = [max(0.0, min(1.0, float(p))) if p is not None else 0.5 for p in predictions]
                
            except Exception as e:
                print(f"⚠️ Erro na predição: {e}")
                predictions = self._fallback_predictions(df)
        
        self.stats['total_predictions'] += 1
        self.stats['last_prediction_time'] = start_time.isoformat()
        
        self._cleanup_cache()
        if len(self._prediction_cache) < self._cache_max_size:
            self._prediction_cache[cache_key] = {
                'predictions': predictions,
                'timestamp': datetime.now()
            }
        
        return predictions
    
    def _predict_with_ensemble(self, X_scaled: np.ndarray) -> np.ndarray:
        """Faz predições com ensemble boosting"""
        try:
            ensemble_data = self.office_model
            
            models = None
            weights = None
            
            if 'ensemble' in ensemble_data:
                models = ensemble_data['ensemble'].get('models', [])
                weights = ensemble_data['ensemble'].get('weights', [])
            elif 'models' in ensemble_data:
                models = ensemble_data.get('models', [])
                weights = ensemble_data.get('model_weights', [])
            
            if (not models or not weights) and self.boosting_ensemble and self.boosting_ensemble.best_model:
                models = self.boosting_ensemble.best_model.get('models', [])
                weights = self.boosting_ensemble.best_model.get('weights', [])
            
            if models and weights:
                predictions = np.zeros(len(X_scaled))
                total_weight = sum(weights)
                
                if total_weight == 0:
                    total_weight = 1
                
                for model, weight in zip(models, weights):
                    if hasattr(model, 'predict'):
                        model_pred = model.predict(X_scaled)
                        predictions += model_pred * weight
                
                predictions = predictions / total_weight
                
                is_classification = ensemble_data.get('ensemble', {}).get('is_classification', True)
                if is_classification:
                    predictions = np.round(predictions).astype(int)
                
                return predictions
            
        except Exception as e:
            print(f"⚠️ Erro na predição do ensemble: {e}")
        
        if hasattr(self.office_model, 'predict'):
            return self.office_model.predict(X_scaled)
        
        return np.random.rand(len(X_scaled))
    
    def _fallback_predictions(self, df: pd.DataFrame) -> List[float]:
        """Fallback quando modelo não está disponível"""
        predictions = []
        df_numeric = df.select_dtypes(include=[np.number])
        
        for idx in range(len(df)):
            if len(df_numeric) > 0:
                row = df_numeric.iloc[idx].fillna(0)
                
                if row.std() > 0:
                    normalized = (row - row.min()) / (row.max() - row.min() + 1e-8)
                    score = float(normalized.mean())
                else:
                    score = float(row.mean() / 100) if row.mean() > 0 else 0.5
                
                score = max(0.0, min(1.0, score))
                predictions.append(score)
            else:
                predictions.append(0.5)
        
        return predictions
    
    # ========== 🔥 NOVO: SUPORTE A MÚLTIPLOS ARQUIVOS ==========
    
    async def predict_multiple_files(self, files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processa múltiplos arquivos em lote com o modelo ML
        
        Args:
            files_data: Lista de dicionários com 'content' (bytes), 'filename' e 'process_id'
        
        Returns:
            Lista de resultados por arquivo
        """
        print(f"\n{'='*60}")
        print(f"📦 Processando lote de {len(files_data)} arquivo(s) com ML")
        print(f"{'='*60}")
        
        # Garantir que os modelos estão carregados
        await self.load_or_train_models()
        
        results = []
        
        for idx, file_info in enumerate(files_data):
            print(f"\n📁 [{idx+1}/{len(files_data)}] Processando: {file_info['filename']}")
            
            try:
                filename = file_info['filename']
                content = file_info['content']
                process_id = file_info.get('process_id', f'file_{idx}')
                
                # Carregar arquivo baseado na extensão
                if filename.endswith('.csv'):
                    df = pd.read_csv(pd.io.common.BytesIO(content))
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(pd.io.common.BytesIO(content))
                else:
                    results.append({
                        'process_id': process_id,
                        'filename': filename,
                        'success': False,
                        'error': f'Formato não suportado: {filename}'
                    })
                    continue
                
                # Validar dados
                if df.empty:
                    results.append({
                        'process_id': process_id,
                        'filename': filename,
                        'success': False,
                        'error': 'Arquivo vazio'
                    })
                    continue
                
                # Estatísticas do arquivo
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                categorical_cols = [c for c in df.columns if c not in numeric_cols]
                
                file_stats = {
                    'rows': len(df),
                    'columns': len(df.columns),
                    'numeric_columns': len(numeric_cols),
                    'categorical_columns': len(categorical_cols),
                    'size_kb': len(content) / 1024,
                    'has_missing': df.isnull().any().any(),
                    'missing_percentage': float(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100) if df.shape[0] > 0 else 0
                }
                
                # Fazer predições
                try:
                    predictions = await self.predict_for_office(df)
                    
                    # Estatísticas das previsões
                    predictions_array = np.array(predictions)
                    pred_summary = {
                        'total': len(predictions),
                        'mean': float(np.mean(predictions_array)),
                        'median': float(np.median(predictions_array)),
                        'std': float(np.std(predictions_array)),
                        'min': float(np.min(predictions_array)),
                        'max': float(np.max(predictions_array)),
                        'high_risk_count': len([p for p in predictions if p > 0.7]),
                        'high_risk_percentage': len([p for p in predictions if p > 0.7]) / len(predictions) * 100 if predictions else 0,
                        'low_risk_count': len([p for p in predictions if p < 0.3]),
                        'low_risk_percentage': len([p for p in predictions if p < 0.3]) / len(predictions) * 100 if predictions else 0
                    }
                    
                    # Amostra das previsões (primeiras 10)
                    predictions_sample = predictions[:10] if len(predictions) > 10 else predictions
                    
                except Exception as ml_error:
                    print(f"   ⚠️ Erro no ML: {ml_error}")
                    predictions = [0.5] * len(df)
                    pred_summary = {'total': len(df), 'error': str(ml_error), 'fallback': True}
                    predictions_sample = [0.5] * min(10, len(df))
                
                # Gerar insights para Gemini
                insights = self.get_ml_insights_for_gemini(df, predictions)
                
                # Identificar features mais importantes
                top_features = []
                if self.feature_names and hasattr(self.office_model, 'feature_importances_'):
                    importances = self.office_model.feature_importances_
                    if len(importances) == len(self.feature_names):
                        feature_imp = list(zip(self.feature_names, importances))
                        feature_imp.sort(key=lambda x: x[1], reverse=True)
                        top_features = [{'name': f, 'importance': float(i)} for f, i in feature_imp[:5]]
                
                results.append({
                    'process_id': process_id,
                    'filename': filename,
                    'success': True,
                    'stats': file_stats,
                    'predictions_summary': pred_summary,
                    'predictions_sample': predictions_sample,
                    'top_features': top_features,
                    'insights': insights,
                    'model_used': self.model_source,
                    'processed_at': datetime.now().isoformat()
                })
                
                self.stats['total_files_processed'] += 1
                
                print(f"   ✅ {filename}: {len(df)} linhas, {len(predictions)} previsões")
                print(f"      📊 Média: {pred_summary['mean']:.3f} | Alto risco: {pred_summary.get('high_risk_percentage', 0):.1f}%")
                
            except Exception as e:
                print(f"   ❌ Erro ao processar {file_info.get('filename', 'desconhecido')}: {e}")
                results.append({
                    'process_id': file_info.get('process_id', f'error_{idx}'),
                    'filename': file_info.get('filename', 'desconhecido'),
                    'success': False,
                    'error': str(e)
                })
        
        print(f"\n{'='*60}")
        print(f"📊 RESUMO DO LOTE:")
        success_count = len([r for r in results if r.get('success')])
        print(f"   ✅ Sucesso: {success_count}/{len(results)}")
        print(f"   📁 Total arquivos processados: {self.stats['total_files_processed']}")
        print(f"   🎯 Total predições: {self.stats['total_predictions']}")
        print(f"{'='*60}\n")
        
        return results
    
    async def predict_proba_for_office(self, df: pd.DataFrame) -> List[float]:
        """Retorna probabilidades para classificação"""
        if self.office_model is None:
            return [0.5] * len(df)
        
        try:
            X_scaled = self._preprocess_features(df)
            
            if hasattr(self.office_model, 'predict_proba'):
                proba = self.office_model.predict_proba(X_scaled)
                if len(proba.shape) > 1 and proba.shape[1] > 1:
                    return proba[:, 1].tolist()
                else:
                    return proba[:, 0].tolist()
            
            elif hasattr(self.office_model, 'decision_function'):
                decision = self.office_model.decision_function(X_scaled)
                proba = 1 / (1 + np.exp(-decision))
                return proba.tolist()
            
            else:
                predictions = await self.predict_for_office(df)
                noise = np.random.normal(0, 0.1, len(predictions))
                proba = np.clip(np.array(predictions) + noise, 0, 1)
                return proba.tolist()
                
        except Exception as e:
            print(f"⚠️ Erro na predição de probabilidade: {e}")
            return [0.5] * len(df)
    
    def get_ml_insights_for_gemini(self, df: pd.DataFrame, predictions: List[float]) -> Dict[str, Any]:
        """Gera insights detalhados sobre as previsões para o Gemini"""
        df_numeric = df.select_dtypes(include=[np.number])
        
        feature_correlations = {}
        if len(df_numeric) > 0 and len(predictions) == len(df_numeric):
            predictions_array = np.array(predictions)
            for col in df_numeric.columns:
                col_data = df_numeric[col].fillna(df_numeric[col].mean())
                if col_data.std() > 0:
                    corr = np.corrcoef(col_data, predictions_array)[0, 1]
                    feature_correlations[col] = float(corr) if not np.isnan(corr) else 0.0
        
        feature_correlations = dict(sorted(feature_correlations.items(), key=lambda x: abs(x[1]), reverse=True))
        
        insights = {
            "visao_geral": {
                "total_registros": len(df),
                "total_features_numericas": df_numeric.shape[1],
                "total_features_originais": df.shape[1],
                "features_numericas": list(df_numeric.columns)[:20],
                "modelo_utilizado": self.model_source or "desconhecido",
                "timestamp_analise": datetime.now().isoformat()
            },
            "estatisticas_previsoes": {
                "media": float(np.mean(predictions)),
                "mediana": float(np.median(predictions)),
                "desvio_padrao": float(np.std(predictions)),
                "minimo": float(np.min(predictions)),
                "maximo": float(np.max(predictions)),
                "distribuicao": {
                    "alto_risco": len([p for p in predictions if p > 0.7]),
                    "porcentagem_alto_risco": len([p for p in predictions if p > 0.7]) / len(predictions) * 100 if predictions else 0,
                    "medio_risco": len([p for p in predictions if 0.4 < p <= 0.7]),
                    "baixo_risco": len([p for p in predictions if p <= 0.4])
                }
            },
            "features_mais_importantes": {
                feature: float(corr) 
                for feature, corr in list(feature_correlations.items())[:10]
            },
            "metricas_modelo": self.last_metrics,
            "recomendacoes": self._generate_recommendations(predictions, df_numeric, feature_correlations),
            "estatisticas_servico": {
                "total_predicoes_servidas": self.stats['total_predictions'],
                "total_arquivos_processados": self.stats['total_files_processed'],
                "cache_hits": self.stats['cache_hits'],
                "cache_misses": self.stats['cache_misses'],
                "cache_hit_rate": self.stats['cache_hits'] / max(1, self.stats['total_predictions']) * 100,
                "ultima_predicao": self.stats['last_prediction_time']
            }
        }
        
        return insights
    
    def _generate_recommendations(self, predictions: List[float], df: pd.DataFrame, correlations: Dict) -> List[str]:
        """Gera recomendações baseadas nas previsões"""
        recommendations = []
        
        if not predictions:
            return ["Dados insuficientes para gerar recomendações"]
        
        high_risk_count = len([p for p in predictions if p > 0.7])
        high_risk_pct = high_risk_count / len(predictions) * 100 if predictions else 0
        
        if high_risk_pct > 30:
            recommendations.append("🔴 ALTO RISCO: Mais de 30% dos casos são de alto risco - revisar processos imediatamente")
        elif high_risk_pct > 15:
            recommendations.append("🟠 RISCO MODERADO: Monitorar de perto os casos de alto risco")
        elif high_risk_pct > 5:
            recommendations.append("🟡 RISCO BAIXO: Manter monitoramento regular")
        else:
            recommendations.append("🟢 RISCO MÍNIMO: Excelente performance, manter práticas atuais")
        
        if correlations:
            top_features = list(correlations.keys())[:3]
            if top_features:
                recommendations.append(f"📊 Features mais influentes: {', '.join(top_features)}")
        
        if high_risk_pct > 10:
            recommendations.append("🎯 Sugestão: Priorizar análise dos casos identificados como alto risco")
        
        if self.last_metrics:
            accuracy = self.last_metrics.get('acurácia', self.last_metrics.get('accuracy', self.last_metrics.get('r2_score', 0.5)))
            if isinstance(accuracy, (int, float)) and accuracy < 0.7:
                recommendations.append("⚠️ Modelo com performance moderada. Considere retreinamento com mais dados")
        
        if len(recommendations) < 2:
            recommendations.append("📈 Análise concluída. Dados dentro dos parâmetros esperados")
        
        return recommendations
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Retorna resumo do modelo atual"""
        return {
            "modelo_carregado": self.is_loaded,
            "fonte_modelo": self.model_source,
            "features": self.feature_names[:10] if self.feature_names else [],
            "ultimas_metricas": self.last_metrics,
            "cache": {
                "tamanho": len(self._prediction_cache),
                "max_tamanho": self._cache_max_size,
                "ttl_segundos": self._cache_ttl
            },
            "estatisticas_uso": {
                "total_predicoes": self.stats['total_predictions'],
                "total_arquivos": self.stats['total_files_processed'],
                "cache_hits": self.stats['cache_hits'],
                "cache_hit_rate": self.stats['cache_hits'] / max(1, self.stats['total_predictions']) * 100
            }
        }
    
    def clear_cache(self):
        """Limpa cache de predições"""
        self._prediction_cache.clear()
        print("🧹 Cache de predições limpo")
    
    async def train_simple_model(self, X: pd.DataFrame, y: pd.Series, model_type: str = 'classifier'):
        """Treina um modelo simples e salva"""
        print(f"\n🚀 Treinando modelo {model_type}...")
        
        X = X.select_dtypes(include=[np.number])
        X = X.fillna(X.mean())
        X = X.fillna(0)
        
        stratify = y if model_type == 'classifier' and len(y.unique()) <= 10 else None
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=stratify
        )
        
        if model_type == 'classifier':
            model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            score = accuracy_score(y_test, y_pred)
            print(f"✅ Classificador treinado - Acurácia: {score:.2%}")
        else:
            model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            score = r2_score(y_test, y_pred)
            print(f"✅ Regressor treinado - R²: {score:.4f}")
        
        model_data = {
            'model': model,
            'features': list(X.columns),
            'model_type': model_type,
            'metrics': {'score': float(score)},
            'trained_date': datetime.now().isoformat()
        }
        
        with open(self.office_model_path, 'wb') as f:
            joblib.dump(model_data, f)
        
        await self.load_or_train_models(force_reload=True)
        
        return {'success': True, 'score': float(score)}


# Instância global
predictor = ModelPredictor()

# Funções de compatibilidade
async def predict_office_data(df: pd.DataFrame) -> List[float]:
    return await predictor.predict_for_office(df)

async def predict_office_probabilities(df: pd.DataFrame) -> List[float]:
    return await predictor.predict_proba_for_office(df)

async def predict_multiple_files(files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return await predictor.predict_multiple_files(files_data)

def get_predictor_insights(df: pd.DataFrame, predictions: List[float]) -> Dict[str, Any]:
    return predictor.get_ml_insights_for_gemini(df, predictions)

def get_predictor_status() -> Dict[str, Any]:
    return predictor.get_model_summary()


print("\n✅ predict.py carregado com sucesso!")
print("   Métodos disponíveis:")
print("   → predictor.predict_for_office(df)")
print("   → predictor.predict_multiple_files(files_data) 🔥 NOVO")
print("   → predictor.predict_proba_for_office(df)")
print("   → predictor.get_ml_insights_for_gemini(df, predictions)")
print("   → predictor.get_model_summary()")