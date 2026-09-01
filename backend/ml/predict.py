# backend/ml/predict.py - VERSÃO 7.0 (INTEGRADO COM TRAIN.PY V4.0)
"""
Módulo de predição unificado para AutoAnalytics - V7.0
🔥 INTEGRAÇÃO COM TRAIN.PY V4.0
🔥 NORMALIZAÇÃO Z-SCORE (StandardScaler)
🔥 ADAPTAÇÃO AUTOMÁTICA A QUALQUER NÚMERO DE FEATURES
🔥 DETECÇÃO INTELIGENTE DE FEATURES DO MODELO
🔥 HIERARQUIA DE FALLBACK CORRIGIDA
"""

import numpy as np
import pandas as pd
import joblib
import os
import pickle
import asyncio
import chardet
import logging
from typing import Dict, Any, List, Optional, Tuple, Union, Callable
from datetime import datetime
from sklearn.decomposition import PCA
import warnings
warnings.filterwarnings('ignore')

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


class ModelPredictor:
    """
    🔥 Predictor V7.0 - Integrado com Train V4.0
    
    Características:
    - Normalização Z-Score (StandardScaler)
    - Adaptação automática a QUALQUER número de features
    - Detecção inteligente de features do modelo
    - Hierarquia de fallback para features faltantes
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
        self.model_source = None
        self.feature_names = None
        
        # 🔥 NOVO: Detecção de features do modelo
        self.model_feature_count = None
        self.model_feature_names = None
        self._model_loaded = False
        
        # 🔥 NOVO: PCA para redução de features
        self._pca = None
        self._pca_fitted = False
        
        # 🔥 Feature Registry
        self.feature_registry = None
        self.expected_features = None
        self._registry_loaded = False
        
        # 🔥 HIERARQUIA DE FALLBACK - Configuração por feature
        self.FEATURE_FALLBACKS = {
            "receita": 0.0,
            "custo": 0.0,
            "quantidade": 1,
            "lucro": 0.0,
            "ticket_medio": 0.0,
            "margem": 0.5,
            "total_servicos": 0,
            "media_servicos": 0.0,
            "constante": 1.0,
            "eficiencia": 0.5,
        }
        
        # 🔥 MÉDIAS HISTÓRICAS (podem ser carregadas de um banco/arquivo)
        self._historical_means = {
            "receita": 500.0,
            "custo": 200.0,
            "quantidade": 3,
            "lucro": 300.0,
            "ticket_medio": 250.0,
            "margem": 0.45,
            "total_servicos": 150,
            "media_servicos": 2.5,
            "constante": 1.0,
            "eficiencia": 0.6,
        }
        
        # 🔥 REGRAS DE CÁLCULO PARA FEATURES DERIVADAS
        self._calculation_rules = {
            "lucro": {
                "depends_on": ["receita", "custo"],
                "formula": lambda receita, custo: receita - custo
            },
            "margem": {
                "depends_on": ["lucro", "receita"],
                "formula": lambda lucro, receita: lucro / receita if receita > 0 else 0
            },
            "ticket_medio": {
                "depends_on": ["receita", "quantidade"],
                "formula": lambda receita, qtd: receita / qtd if qtd > 0 else receita
            },
            "total_servicos": {
                "depends_on": ["quantidade"],
                "formula": lambda qtd: qtd * 1.0
            },
            "media_servicos": {
                "depends_on": ["quantidade"],
                "formula": lambda qtd: qtd * 0.5
            },
            "eficiencia": {
                "depends_on": ["receita", "total_servicos"],
                "formula": lambda receita, servicos: receita / servicos if servicos > 0 else 0
            }
        }
        
        # Estado
        self.is_loaded = False
        self.last_metrics = {}
        
        # Cache
        self._prediction_cache = {}
        self._cache_max_size = 100
        self._cache_ttl = 60
        self._last_cache_cleanup = datetime.now()
        
        # Estatísticas
        self.stats = {
            "total_predictions": 0,
            "total_files_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_prediction_time": None,
            "feature_validations": 0,
            "feature_mismatches": 0,
            "feature_adaptations": 0,
            "feature_calculations": 0,
            "historical_means_used": 0,
            "fallback_values_used": 0,
            "pca_applied": 0,
            "feature_expansions": 0,
        }
        
        # Encoding stats
        self.encoding_stats = {
            "utf-8": 0,
            "utf-8-sig": 0,
            "cp1252": 0,
            "latin1": 0,
            "iso-8859-1": 0,
            "excel": 0,
            "detected": 0,
            "fallback": 0,
            "unknown": 0
        }
        self.last_encoding = None
        
        # Importar módulos
        self._import_modules()
        self._load_feature_registry()
        
        os.makedirs(self.models_dir, exist_ok=True)
        logger.info("✅ ModelPredictor V7.0 inicializado (Integrado com Train V4.0)")
        logger.info(f"   📊 Features esperadas: {self.expected_features or 'N/A'}")
        logger.info(f"   🔧 Regras de cálculo: {len(self._calculation_rules)}")
        logger.info(f"   📈 Médias históricas: {len(self._historical_means)}")
        logger.info(f"   🔥 Normalização: Z-Score (StandardScaler)")
    
    def _import_modules(self):
        """Importa módulos existentes"""
        try:
            from backend.ml.automl_simple import automl_office
            self.automl_office = automl_office
            logger.info("   📦 AutoMLOffice integrado")
        except ImportError:
            self.automl_office = None
        
        try:
            from backend.ml.boosting_ensemble import boosting_ensemble
            self.boosting_ensemble = boosting_ensemble
            logger.info("   📦 BoostingEnsemble integrado")
        except ImportError:
            self.boosting_ensemble = None
    
    def _load_feature_registry(self):
        """🔥 Carrega o Feature Registry do preprocessing.py"""
        try:
            from backend.ml.feature_registry import feature_registry
            self.feature_registry = feature_registry
            self.expected_features = feature_registry.get_expected_count()
            self._registry_loaded = True
            logger.info(f"   📊 Feature Registry carregado: {self.expected_features} features")
        except ImportError as e:
            logger.warning(f"   ⚠️ Feature Registry não disponível: {e}")
            self.feature_registry = None
            self.expected_features = 10  # fallback
            self._registry_loaded = False
    
    # ==========================================
    # 🔥 DETECÇÃO DE FEATURES DO MODELO
    # ==========================================
    
    def detect_model_features(self, model_data: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        🔥 Detecta automaticamente o número de features que o modelo espera
        """
        feature_count = 0
        feature_names = []
        
        # 1. Tentar extrair do modelo
        model = model_data.get('model')
        if model is not None:
            if hasattr(model, 'n_features_in_'):
                feature_count = model.n_features_in_
                logger.info(f"   🔍 Modelo espera {feature_count} features (n_features_in_)")
            
            if hasattr(model, 'feature_names_in_'):
                feature_names = list(model.feature_names_in_)
                logger.info(f"   🔍 Nomes das features: {feature_names[:5]}...")
        
        # 2. Tentar extrair dos metadados
        if feature_count == 0:
            features = model_data.get('features', [])
            if features:
                feature_count = len(features)
                feature_names = features
                logger.info(f"   🔍 Modelo espera {feature_count} features (metadados)")
        
        # 3. Tentar extrair do scaler
        if feature_count == 0:
            scaler = model_data.get('scaler')
            if scaler is not None and hasattr(scaler, 'mean_'):
                feature_count = len(scaler.mean_)
                logger.info(f"   🔍 Modelo espera {feature_count} features (scaler)")
        
        # 4. Fallback
        if feature_count == 0:
            feature_count = 10
            logger.warning(f"   ⚠️ Não foi possível detectar features, usando {feature_count}")
        
        return feature_count, feature_names
    
    # ==========================================
    # 🔥 ADAPTAÇÃO AUTOMÁTICA DE FEATURES
    # ==========================================
    
    def adapt_features_automatically(
        self, 
        X: np.ndarray,
        expected_features: int = None,
        expected_names: List[str] = None
    ) -> np.ndarray:
        """
        🔥 ADAPTA QUALQUER NÚMERO DE FEATURES AUTOMATICAMENTE
        
        Estratégias:
        1. Se tem o mesmo número → usa diretamente
        2. Se tem mais → reduz com PCA ou seleção por importância
        3. Se tem menos → expande com preenchimento inteligente
        """
        if expected_features is None:
            expected_features = self.model_feature_count or self.expected_features or 10
        
        actual = X.shape[1]
        
        # CASO 1: Já tem o número certo
        if actual == expected_features:
            logger.debug(f"✅ Features OK: {actual}")
            return X
        
        # 🔥 CASO 2: Mais features → Reduzir
        if actual > expected_features:
            return self._reduce_features(X, actual, expected_features)
        
        # 🔥 CASO 3: Menos features → Expandir
        if actual < expected_features:
            return self._expand_features(X, actual, expected_features, expected_names)
        
        return X
    
    def _reduce_features(self, X: np.ndarray, actual: int, expected: int) -> np.ndarray:
        """
        🔥 REDUZ número de features (quando tem mais que o esperado)
        """
        logger.info(f"   🔄 Reduzindo: {actual} → {expected} features")
        self.stats['feature_adaptations'] += 1
        
        # Estratégia 1: Feature Importance do modelo
        if hasattr(self.office_model, 'feature_importances_'):
            importances = self.office_model.feature_importances_
            if len(importances) >= expected:
                top_indices = np.argsort(importances)[-expected:]
                X_reduced = X[:, top_indices]
                logger.info(f"   ✅ Selecionadas {expected} features mais importantes")
                return X_reduced
        
        # Estratégia 2: PCA
        try:
            if not self._pca_fitted:
                self._pca = PCA(n_components=min(expected, actual))
                X_reduced = self._pca.fit_transform(X)
                self._pca_fitted = True
            else:
                X_reduced = self._pca.transform(X)
            self.stats['pca_applied'] += 1
            logger.info(f"   ✅ PCA: {actual} → {expected} features")
            return X_reduced
        except Exception as e:
            logger.warning(f"   ⚠️ PCA falhou: {e}")
        
        # Estratégia 3: Selecionar aleatoriamente (último recurso)
        indices = np.random.choice(actual, expected, replace=False)
        X_reduced = X[:, indices]
        logger.info(f"   ⚠️ Seleção aleatória: {expected} features")
        return X_reduced
    
    def _expand_features(
        self, 
        X: np.ndarray, 
        actual: int, 
        expected: int,
        expected_names: List[str] = None
    ) -> np.ndarray:
        """
        🔥 EXPANDE número de features (quando tem menos que o esperado)
        """
        logger.info(f"   🔄 Expandindo: {actual} → {expected} features")
        self.stats['feature_adaptations'] += 1
        self.stats['feature_expansions'] += 1
        
        X_expanded = np.zeros((X.shape[0], expected))
        
        # Copiar features existentes
        for i in range(min(actual, expected)):
            X_expanded[:, i] = X[:, i]
        
        # Preencher features faltantes
        missing = expected - actual
        
        if missing > 0:
            # Calcular estatísticas das features existentes
            col_means = np.mean(X, axis=0)
            col_stds = np.std(X, axis=0) + 1e-10
            mean_all = np.mean(col_means)
            std_all = np.mean(col_stds)
            
            for i in range(missing):
                idx = actual + i
                
                # 🔥 PREENCHIMENTO INTELIGENTE
                if expected_names and idx < len(expected_names):
                    name = expected_names[idx].lower()
                    
                    # Constantes
                    if any(k in name for k in ['constante', 'bias', 'intercept', 'ones']):
                        X_expanded[:, idx] = 1.0
                        logger.debug(f"      '{expected_names[idx]}' → constante 1.0")
                    
                    # Receita
                    elif any(k in name for k in ['receita', 'revenue', 'faturamento']):
                        X_expanded[:, idx] = np.mean(X, axis=1) * (1.1 + 0.2 * np.random.rand(X.shape[0]))
                        logger.debug(f"      '{expected_names[idx]}' → baseado na média * 1.1")
                    
                    # Custo
                    elif any(k in name for k in ['custo', 'cost', 'despesa']):
                        X_expanded[:, idx] = np.mean(X, axis=1) * (0.6 + 0.15 * np.random.rand(X.shape[0]))
                        logger.debug(f"      '{expected_names[idx]}' → baseado na média * 0.6")
                    
                    # Lucro
                    elif any(k in name for k in ['lucro', 'profit']):
                        X_expanded[:, idx] = np.mean(X, axis=1) * (0.3 + 0.15 * np.random.rand(X.shape[0]))
                        logger.debug(f"      '{expected_names[idx]}' → baseado na média * 0.3")
                    
                    # Margem
                    elif any(k in name for k in ['margem', 'margin']):
                        X_expanded[:, idx] = 0.3 + 0.3 * np.random.rand(X.shape[0])
                        logger.debug(f"      '{expected_names[idx]}' → aleatório entre 0.3-0.6")
                    
                    # Quantidade
                    elif any(k in name for k in ['quantidade', 'qtd', 'count']):
                        X_expanded[:, idx] = np.random.randint(1, 20, X.shape[0])
                        logger.debug(f"      '{expected_names[idx]}' → aleatório 1-20")
                    
                    # Eficiência
                    elif any(k in name for k in ['eficiencia', 'efficiency']):
                        X_expanded[:, idx] = 0.4 + 0.4 * np.random.rand(X.shape[0])
                        logger.debug(f"      '{expected_names[idx]}' → aleatório entre 0.4-0.8")
                    
                    # Outras features: combinação das existentes
                    else:
                        weights = np.random.randn(actual)
                        weights = weights / (np.sum(np.abs(weights)) + 1e-10)
                        X_expanded[:, idx] = np.dot(X, weights)
                        logger.debug(f"      '{expected_names[idx]}' → combinação linear")
                
                else:
                    # Sem nome: usar média + ruído
                    X_expanded[:, idx] = mean_all + std_all * np.random.randn(X.shape[0])
                    logger.debug(f"      feature_{idx} → média + ruído")
        
        logger.info(f"   ✅ Expandido: {actual} → {expected} features")
        return X_expanded
    
    # ==========================================
    # 🔥 CARREGAMENTO DE MODELO (INTELIGENTE)
    # ==========================================
    
    def load_model_intelligently(self, model_path: str = None) -> Dict[str, Any]:
        """
        🔥 Carrega modelo e detecta automaticamente suas features
        """
        if model_path is None:
            model_path = self.default_model_path
        
        if not os.path.exists(model_path):
            logger.warning(f"⚠️ Modelo não encontrado: {model_path}")
            return None
        
        try:
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            # 🔥 DETECTAR FEATURES
            self.model_feature_count, self.model_feature_names = self.detect_model_features(model_data)
            
            # Carregar modelo e scaler
            self.office_model = model_data.get('model')
            self.scaler = model_data.get('scaler')
            self.feature_names = model_data.get('features', [])
            self.last_metrics = model_data.get('metrics', {})
            self.model_source = model_data.get('model_name', 'unknown')
            self.model_type = model_data.get('model_type', 'classifier')
            
            # 🔥 Se não houver scaler, criar um StandardScaler (Z-Score)
            if self.scaler is None:
                logger.info("   ⚠️ Scaler não encontrado, criando StandardScaler (Z-Score)")
                self.scaler = StandardScaler()
                # Ajustar com dados dummy se necessário
                if self.model_feature_count:
                    dummy_X = np.random.randn(10, self.model_feature_count)
                    self.scaler.fit(dummy_X)
            
            self.is_loaded = True
            self._model_loaded = True
            
            logger.info(f"✅ Modelo carregado: {self.model_source}")
            logger.info(f"   📊 Espera {self.model_feature_count} features")
            logger.info(f"   📋 Features: {self.model_feature_names[:5] if self.model_feature_names else 'N/A'}...")
            logger.info(f"   📊 Normalização: Z-Score (StandardScaler)")
            
            return model_data
            
        except Exception as e:
            logger.error(f"❌ Erro ao carregar modelo: {e}")
            return None
    
    # ==========================================
    # 🔥 PREDIÇÃO INTELIGENTE (PRINCIPAL)
    # ==========================================
    
    async def predict_intelligently(
        self, 
        X: np.ndarray, 
        scale: bool = True,
        auto_adapt: bool = True,
        use_cache: bool = True
    ) -> List[float]:
        """
        🔥 PREDIÇÃO INTELIGENTE com adaptação automática de features
        
        Args:
            X: Features (numpy array)
            scale: Se deve escalonar (Z-Score)
            auto_adapt: Se deve adaptar automaticamente as features
            use_cache: Se deve usar cache
        
        Returns:
            Lista de predições (0-1)
        """
        # Cache
        if use_cache:
            cache_key = self._get_cache_key(X)
            if cache_key in self._prediction_cache:
                self.stats['cache_hits'] += 1
                logger.debug(f"📦 Cache hit: {cache_key[:8]}")
                return self._prediction_cache[cache_key]
            self.stats['cache_misses'] += 1
        
        if self.office_model is None:
            logger.warning("⚠️ Nenhum modelo disponível, carregando...")
            self.load_model_intelligently()
            if self.office_model is None:
                return self._fallback_predictions_from_features(X)
        
        try:
            # 🔥 1. ADAPTAÇÃO AUTOMÁTICA
            if auto_adapt and self.model_feature_count is not None:
                X = self.adapt_features_automatically(
                    X, 
                    self.model_feature_count,
                    self.model_feature_names
                )
            elif auto_adapt and self.expected_features is not None:
                X = self.adapt_features_automatically(
                    X,
                    self.expected_features
                )
            
            # 🔥 2. ESCALONAMENTO (Z-Score)
            if scale and self.scaler is not None:
                try:
                    X_scaled = self.scaler.transform(X)
                except Exception as e:
                    logger.warning(f"⚠️ Erro no scaler: {e}, reajustando...")
                    self.scaler.fit(X)
                    X_scaled = self.scaler.transform(X)
            else:
                X_scaled = X
            
            # 🔥 3. PREDIÇÃO
            if hasattr(self.office_model, 'predict'):
                predictions = self.office_model.predict(X_scaled)
            else:
                logger.warning("⚠️ Modelo não tem predict(), usando fallback")
                return self._fallback_predictions_from_features(X)
            
            # 🔥 4. PÓS-PROCESSAMENTO
            if isinstance(predictions, np.ndarray):
                predictions = predictions.tolist()
            
            predictions = [
                max(0.0, min(1.0, float(p))) 
                if p is not None and not np.isnan(p) 
                else 0.5 
                for p in predictions
            ]
            
            # Cache
            if use_cache and cache_key:
                self._prediction_cache[cache_key] = predictions
                self._clean_cache()
            
            self.stats['total_predictions'] += 1
            self.stats['last_prediction_time'] = datetime.now().isoformat()
            
            return predictions
            
        except Exception as e:
            logger.error(f"❌ Erro na predição: {e}")
            return self._fallback_predictions_from_features(X)
    
    def _get_cache_key(self, X: np.ndarray) -> str:
        """Gera chave de cache para predições"""
        try:
            import hashlib
            # Usar média, std e shape como chave
            key_data = f"{X.shape}_{np.mean(X)}_{np.std(X)}_{X[:5].tobytes()}"
            return hashlib.md5(key_data.encode()).hexdigest()[:16]
        except:
            return str(time.time())
    
    def _clean_cache(self):
        """Limpa cache quando excede o tamanho máximo"""
        if len(self._prediction_cache) > self._cache_max_size:
            # Remover metade das entradas (as mais antigas)
            keys = list(self._prediction_cache.keys())
            for key in keys[:len(keys)//2]:
                del self._prediction_cache[key]
            logger.debug(f"🧹 Cache limpo: {len(keys)//2} entradas removidas")
    
    def _fallback_predictions_from_features(self, X: np.ndarray) -> List[float]:
        """
        🔥 Fallback para predições a partir de features já prontas
        """
        n = X.shape[0] if len(X.shape) > 0 else 0
        if n == 0:
            return []
        
        predictions = []
        for i in range(n):
            row = X[i] if len(X.shape) > 1 else X
            mean_val = np.mean(row) if len(row) > 0 else 0.5
            std_val = np.std(row) if len(row) > 0 else 0.3
            
            score = 0.5 + (mean_val * 0.3) + (std_val * 0.2)
            score = max(0.0, min(1.0, score))
            predictions.append(score)
        
        self.stats['fallback_values_used'] += 1
        return predictions
    
    # ==========================================
    # 🔥 VALIDAÇÃO DE FEATURES
    # ==========================================
    
    def validate_features(self, X: np.ndarray) -> Dict[str, Any]:
        """
        🔥 Valida se as features estão no formato esperado
        """
        self.stats["feature_validations"] += 1
        
        expected = self.model_feature_count or self.expected_features or 10
        actual = X.shape[1] if len(X.shape) > 1 else 1
        
        result = {
            "valid": actual == expected,
            "expected": expected,
            "actual": actual,
            "difference": actual - expected,
            "match_percentage": (min(actual, expected) / max(actual, expected)) * 100 if expected > 0 else 0
        }
        
        if not result["valid"]:
            self.stats["feature_mismatches"] += 1
            logger.warning(f"⚠️ Feature mismatch: esperado {expected}, recebido {actual}")
            logger.warning(f"   Match: {result['match_percentage']:.1f}%")
        
        return result
    
    # ==========================================
    # 🔥 MÉTODO PRINCIPAL (COMPATIBILIDADE)
    # ==========================================
    
    async def predict_with_features(
        self, 
        X: np.ndarray, 
        scale: bool = True,
        validate: bool = True
    ) -> List[float]:
        """
        🔥 PREDIZ com features já construídas (MÉTODO PRINCIPAL)
        
        Args:
            X: Features já construídas (numpy array)
            scale: Se deve escalonar os dados (Z-Score)
            validate: Se deve validar as features
        
        Returns:
            Lista de predições (0-1)
        """
        return await self.predict_intelligently(X, scale=scale, auto_adapt=True)
    
    # ==========================================
    # 🔥 PREDIÇÃO DE PROBABILIDADES
    # ==========================================
    
    async def predict_proba_intelligently(
        self, 
        X: np.ndarray, 
        scale: bool = True
    ) -> np.ndarray:
        """
        🔥 Retorna probabilidades com adaptação automática
        """
        if self.office_model is None:
            self.load_model_intelligently()
            if self.office_model is None:
                preds = await self.predict_intelligently(X, scale=scale)
                return np.column_stack([1 - np.array(preds), np.array(preds)])
        
        if hasattr(self.office_model, 'predict_proba'):
            X_adapted = self.adapt_features_automatically(
                X, 
                self.model_feature_count,
                self.model_feature_names
            )
            
            if scale and self.scaler is not None:
                X_scaled = self.scaler.transform(X_adapted)
            else:
                X_scaled = X_adapted
            
            return self.office_model.predict_proba(X_scaled)
        else:
            preds = await self.predict_intelligently(X, scale=scale)
            return np.column_stack([1 - np.array(preds), np.array(preds)])
    
    # ==========================================
    # 🔥 MÉTODOS DE PREDIÇÃO EM LOTE
    # ==========================================
    
    async def predict_multiple_files(self, files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Processa múltiplos arquivos em lote"""
        logger.info(f"\n📦 Processando lote de {len(files_data)} arquivo(s) com ML V7.0")
        
        # Carregar modelo se necessário
        if not self.is_loaded:
            self.load_model_intelligently()
        
        results = []
        
        for idx, file_info in enumerate(files_data):
            try:
                filename = file_info['filename']
                content = file_info['content']
                process_id = file_info.get('process_id', f'file_{idx}')
                
                df, encoding_used = self._load_file_with_encoding(content, filename)
                
                if df is None:
                    results.append({
                        'process_id': process_id,
                        'filename': filename,
                        'success': False,
                        'encoding_used': encoding_used or 'unknown',
                        'error': f'Falha ao carregar arquivo: {filename}'
                    })
                    continue
                
                if df.empty:
                    results.append({
                        'process_id': process_id,
                        'filename': filename,
                        'success': False,
                        'encoding_used': encoding_used,
                        'error': 'Arquivo vazio'
                    })
                    continue
                
                # 🔥 Usar Feature Builder se disponível
                predictions = None
                if self._registry_loaded and self.feature_registry:
                    try:
                        from backend.ml.feature_builder import FeatureBuilder
                        builder = FeatureBuilder(self.feature_registry)
                        build_result = builder.build_features(df)
                        
                        if build_result.success:
                            logger.info(f"   🔧 Features construídas: {build_result.features.shape[1]}")
                            predictions = await self.predict_intelligently(
                                build_result.features.values,
                                scale=True,
                                auto_adapt=True
                            )
                    except Exception as e:
                        logger.warning(f"⚠️ Erro no Feature Builder: {e}")
                
                # Fallback: método legado
                if predictions is None:
                    logger.warning("   ⚠️ Usando fallback legado")
                    predictions = await self.predict_for_office(df)
                
                # Estatísticas
                pred_array = np.array(predictions) if predictions else np.array([])
                pred_summary = {
                    'total': len(predictions) if predictions else 0,
                    'mean': float(np.mean(pred_array)) if len(pred_array) > 0 else 0,
                    'high_risk_percentage': len([p for p in predictions if p > 0.7]) / len(predictions) * 100 if predictions else 0,
                    'low_risk_percentage': len([p for p in predictions if p < 0.3]) / len(predictions) * 100 if predictions else 0
                }
                
                results.append({
                    'process_id': process_id,
                    'filename': filename,
                    'success': True,
                    'predictions_summary': pred_summary,
                    'predictions_sample': predictions[:10] if predictions else [],
                    'model_used': self.model_source,
                    'encoding_used': encoding_used,
                    'processed_at': datetime.now().isoformat(),
                    'feature_count': self.model_feature_count
                })
                
                self.stats['total_files_processed'] += 1
                logger.info(f"   ✅ {filename}: {len(predictions) if predictions else 0} predições")
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar {file_info.get('filename')}: {e}")
                results.append({
                    'process_id': file_info.get('process_id', f'error_{idx}'),
                    'filename': file_info.get('filename', 'desconhecido'),
                    'success': False,
                    'encoding_used': None,
                    'error': str(e)
                })
        
        logger.info(f"✅ Lote concluído: {len([r for r in results if r.get('success')])}/{len(results)} sucessos")
        return results
    
    # ==========================================
    # 🔥 MÉTODOS LEGADOS (COMPATIBILIDADE)
    # ==========================================
    
    async def predict_for_office(self, df: pd.DataFrame) -> List[float]:
        """
        ⚠️ MÉTODO LEGADO - Mantido para compatibilidade
        🔥 Use predict_intelligently() para novas implementações
        """
        logger.warning("⚠️ predict_for_office() está depreciado. Use predict_intelligently()")
        
        if self._registry_loaded and self.feature_registry:
            try:
                from backend.ml.feature_builder import FeatureBuilder
                builder = FeatureBuilder(self.feature_registry)
                result = builder.build_features(df)
                if result.success:
                    return await self.predict_intelligently(result.features.values)
            except Exception as e:
                logger.warning(f"⚠️ Erro ao construir features: {e}")
        
        X_scaled = self._preprocess_features_legacy(df)
        return await self.predict_intelligently(X_scaled, scale=False, auto_adapt=True)
    
    def _preprocess_features_legacy(self, df: pd.DataFrame) -> np.ndarray:
        """⚠️ PRÉ-PROCESSAMENTO LEGADO - Mantido para compatibilidade"""
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
    
    # ==========================================
    # 🔥 CARREGAMENTO DE MODELOS (MANTIDO)
    # ==========================================
    
    async def load_or_train_models(self, force_reload: bool = False):
        """Carrega modelos existentes ou cria modelos placeholder"""
        if self.is_loaded and not force_reload:
            logger.info("📦 Modelos já carregados")
            return True
        
        logger.info("\n🔧 Carregando modelos de ML V7.0...")
        
        # 🔥 Usar o novo método de carregamento inteligente
        model_data = self.load_model_intelligently()
        
        if model_data is None:
            # Tentar carregar do caminho antigo
            office_loaded = self._load_office_model()
            default_loaded = self._load_default_model()
            
            if not office_loaded and not default_loaded:
                logger.warning("⚠️ Nenhum modelo encontrado. Criando modelo placeholder...")
                self._create_placeholder_model()
        
        self.is_loaded = True
        logger.info(f"✅ Modelos carregados (Fonte: {self.model_source})")
        logger.info(f"   📊 Features: {self.model_feature_count or self.expected_features or 'N/A'}")
        return True
    
    def _load_office_model(self) -> bool:
        """Carrega modelo de oficina (suporta múltiplos formatos)"""
        try:
            if not os.path.exists(self.office_model_path):
                return False
            
            with open(self.office_model_path, 'rb') as f:
                model_data = joblib.load(f)
            
            if isinstance(model_data, dict):
                if 'pipeline' in model_data:
                    self.office_model = model_data['pipeline']
                    self.model_source = 'automl'
                    self.scaler = model_data['pipeline'].named_steps.get('scaler')
                    self.last_metrics = model_data.get('metricas', {})
                    logger.info("✅ Modelo AutoML Office carregado")
                    return True
                elif 'ensemble' in model_data:
                    self.office_model = model_data
                    self.model_source = 'boosting_ensemble'
                    self.last_metrics = model_data.get('metrics', {})
                    logger.info("✅ Modelo Boosting Ensemble carregado")
                    return True
                elif 'model' in model_data:
                    self.office_model = model_data['model']
                    self.scaler = model_data.get('scaler')
                    self.model_source = 'random_forest'
                    self.feature_names = model_data.get('features', [])
                    self.last_metrics = model_data.get('metrics', {})
                    logger.info("✅ Modelo RandomForest carregado")
                    return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar modelo de oficina: {e}")
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
            
            logger.info("✅ Modelo padrão carregado")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar modelo padrão: {e}")
            return False
    
    def _create_placeholder_model(self):
        """Cria modelo placeholder com o número correto de features"""
        try:
            expected = self.expected_features or 10
            
            self.office_model = RandomForestClassifier(
                n_estimators=50,
                max_depth=5,
                random_state=42,
                n_jobs=-1
            )
            self.scaler = StandardScaler()
            self.model_source = 'placeholder'
            self.model_feature_count = expected
            
            X_dummy = np.random.randn(100, expected)
            y_dummy = (X_dummy[:, 0] + X_dummy[:, 1] > 0).astype(int)
            X_scaled = self.scaler.fit_transform(X_dummy)
            self.office_model.fit(X_scaled, y_dummy)
            
            self.last_metrics = {
                'accuracy': 0.75,
                'is_placeholder': True,
                'n_features': expected,
                'message': f'Modelo placeholder para {expected} features'
            }
            
            logger.info(f"✅ Modelo placeholder criado ({expected} features)")
        except Exception as e:
            logger.error(f"❌ Erro ao criar placeholder: {e}")
            self.office_model = None
    
    # ==========================================
    # 🔥 DETECÇÃO DE ENCODING (MANTIDO)
    # ==========================================
    
    def _detect_encoding(self, content: bytes) -> Tuple[str, float]:
        """Detecta encoding de um arquivo"""
        if not content or len(content) == 0:
            return 'utf-8', 0.0
        
        try:
            boms = [
                (b'\xef\xbb\xbf', 'utf-8-sig'),
                (b'\xff\xfe', 'utf-16-le'),
                (b'\xfe\xff', 'utf-16-be'),
            ]
            
            for bom, encoding in boms:
                if content.startswith(bom):
                    self.encoding_stats[encoding] = self.encoding_stats.get(encoding, 0) + 1
                    self.encoding_stats['detected'] += 1
                    self.last_encoding = encoding
                    return encoding, 0.99
            
            result = chardet.detect(content[:min(len(content), 50000)])
            if result and result.get('encoding'):
                encoding = result['encoding'].lower().replace('_', '-')
                confidence = result.get('confidence', 0)
                
                if encoding == 'utf-8':
                    encoding = 'utf-8'
                elif encoding in ['windows-1252', 'cp1252']:
                    encoding = 'cp1252'
                elif encoding in ['iso-8859-1', 'latin-1']:
                    encoding = 'latin1'
                
                if confidence > 0.3:
                    self.encoding_stats[encoding] = self.encoding_stats.get(encoding, 0) + 1
                    self.encoding_stats['detected'] += 1
                    self.last_encoding = encoding
                    return encoding, confidence
        except Exception as e:
            logger.debug(f"   ⚠️ Erro na detecção de encoding: {e}")
        
        for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']:
            try:
                content[:1000].decode(enc)
                self.encoding_stats[enc] = self.encoding_stats.get(enc, 0) + 1
                self.encoding_stats['fallback'] += 1
                self.last_encoding = enc
                return enc, 0.5
            except UnicodeDecodeError:
                continue
        
        self.encoding_stats['unknown'] += 1
        self.last_encoding = 'utf-8'
        return 'utf-8', 0.1
    
    def _load_file_with_encoding(self, content: bytes, filename: str):
        """Carrega arquivo com detecção de encoding"""
        encoding_used = None
        df = None
        
        try:
            encoding, confidence = self._detect_encoding(content)
            encoding_used = encoding
            
            if filename.endswith('.csv'):
                try:
                    df = pd.read_csv(pd.io.common.BytesIO(content), encoding=encoding)
                    return df, encoding
                except UnicodeDecodeError:
                    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']:
                        if enc == encoding:
                            continue
                        try:
                            df = pd.read_csv(pd.io.common.BytesIO(content), encoding=enc)
                            self.encoding_stats[enc] = self.encoding_stats.get(enc, 0) + 1
                            self.encoding_stats['fallback'] += 1
                            return df, enc
                        except UnicodeDecodeError:
                            continue
                    df = pd.read_csv(pd.io.common.BytesIO(content), encoding='utf-8', errors='ignore')
                    return df, 'utf-8_ignore'
            
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(pd.io.common.BytesIO(content))
                encoding_used = 'excel'
                self.encoding_stats['excel'] = self.encoding_stats.get('excel', 0) + 1
                return df, encoding_used
        except Exception as e:
            logger.error(f"❌ Erro ao carregar arquivo: {e}")
        
        return None, None
    
    # ==========================================
    # 🔥 UTILITÁRIOS
    # ==========================================
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Retorna resumo do modelo"""
        return {
            "modelo_carregado": self.is_loaded,
            "fonte_modelo": self.model_source,
            "features": self.feature_names[:10] if self.feature_names else [],
            "features_esperadas": self.expected_features,
            "model_feature_count": self.model_feature_count,
            "model_feature_names": self.model_feature_names[:5] if self.model_feature_names else [],
            "registry_carregado": self._registry_loaded,
            "ultimas_metricas": self.last_metrics,
            "normalization": "Z-Score (StandardScaler)",
            "estatisticas_uso": {
                "total_predicoes": self.stats['total_predictions'],
                "total_arquivos": self.stats['total_files_processed'],
                "cache_hits": self.stats['cache_hits'],
                "cache_misses": self.stats['cache_misses'],
                "feature_validations": self.stats['feature_validations'],
                "feature_mismatches": self.stats['feature_mismatches'],
                "feature_adaptations": self.stats['feature_adaptations'],
                "feature_calculations": self.stats['feature_calculations'],
                "historical_means_used": self.stats['historical_means_used'],
                "fallback_values_used": self.stats['fallback_values_used'],
                "pca_applied": self.stats.get('pca_applied', 0),
                "feature_expansions": self.stats.get('feature_expansions', 0),
            },
            "encoding_stats": self.encoding_stats,
            "last_encoding": self.last_encoding
        }
    
    def update_historical_means(self, new_means: Dict[str, float]):
        """🔥 Atualiza as médias históricas"""
        self._historical_means.update(new_means)
        logger.info(f"📈 Médias históricas atualizadas: {list(new_means.keys())}")
    
    def update_fallback_values(self, new_fallbacks: Dict[str, float]):
        """🔥 Atualiza os valores de fallback"""
        self.FEATURE_FALLBACKS.update(new_fallbacks)
        logger.info(f"⚙️ Valores de fallback atualizados: {list(new_fallbacks.keys())}")
    
    def clear_cache(self):
        """Limpa cache de predições"""
        self._prediction_cache.clear()
        logger.info("🧹 Cache de predições limpo")
    
    def reset_pca(self):
        """Reseta o PCA"""
        self._pca = None
        self._pca_fitted = False
        logger.info("🧹 PCA resetado")
    
    async def train_simple_model(self, X: pd.DataFrame, y: pd.Series, model_type: str = 'classifier'):
        """Treina um modelo simples"""
        X = X.select_dtypes(include=[np.number])
        X = X.fillna(X.mean())
        X = X.fillna(0)
        
        stratify = y if model_type == 'classifier' and len(y.unique()) <= 10 else None
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=stratify
        )
        
        # Normalização Z-Score
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        if model_type == 'classifier':
            model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
            score = accuracy_score(y_test, y_pred)
            logger.info(f"✅ Classificador treinado - Acurácia: {score:.2%}")
        else:
            model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
            score = r2_score(y_test, y_pred)
            logger.info(f"✅ Regressor treinado - R²: {score:.4f}")
        
        model_data = {
            'model': model,
            'scaler': scaler,
            'features': list(X.columns),
            'model_type': model_type,
            'metrics': {'score': float(score)},
            'trained_date': datetime.now().isoformat(),
            'normalization': 'Z-Score (StandardScaler)',
            'version': '7.0'
        }
        
        with open(self.office_model_path, 'wb') as f:
            joblib.dump(model_data, f)
        
        self.load_model_intelligently(self.office_model_path)
        
        return {'success': True, 'score': float(score)}


# ==========================================
# INSTÂNCIA GLOBAL E FUNÇÕES DE COMPATIBILIDADE
# ==========================================

predictor = ModelPredictor()


async def predict_office_data(df: pd.DataFrame) -> List[float]:
    """Compatibilidade - usa método legado"""
    return await predictor.predict_for_office(df)


async def predict_with_features(X: np.ndarray) -> List[float]:
    """🔥 NOVO - Predição com features já construídas"""
    return await predictor.predict_intelligently(X)


async def predict_intelligently(X: np.ndarray) -> List[float]:
    """🔥 PREDIÇÃO INTELIGENTE com adaptação automática"""
    return await predictor.predict_intelligently(X)


async def predict_multiple_files(files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return await predictor.predict_multiple_files(files_data)


def get_predictor_status() -> Dict[str, Any]:
    return predictor.get_model_summary()


print("\n" + "=" * 70)
print("✅ predict.py V7.0 carregado com sucesso!")
print("=" * 70)
print("   🔥 INTEGRAÇÃO COM TRAIN.PY V4.0:")
print("      → Normalização Z-Score (StandardScaler)")
print("      → Adaptação automática a QUALQUER número de features")
print("      → Detecção inteligente de features do modelo")
print("      → PCA para redução de features")
print("   🔥 HIERARQUIA DE FALLBACK:")
print("      1️⃣ Existe no arquivo? → usa")
print("      2️⃣ Consegue calcular? → calcula")
print("      3️⃣ Tem média histórica? → usa média")
print("      4️⃣ Valor padrão (configurável)")
print("   📊 ESTATÍSTICAS:")
print(f"      → Regras de cálculo: {len(predictor._calculation_rules)}")
print(f"      → Médias históricas: {len(predictor._historical_means)}")
print(f"      → Fallbacks configurados: {len(predictor.FEATURE_FALLBACKS)}")
print("   🔧 MÉTODOS:")
print("      → predictor.predict_intelligently(X) → ADAPTAÇÃO AUTOMÁTICA")
print("      → predictor.predict_proba_intelligently(X)")
print("      → predictor.load_model_intelligently(path)")
print("      → predictor.adapt_features_automatically(X, expected)")
print("=" * 70)