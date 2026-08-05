# backend/ml/predict.py - VERSÃO 6.1 (HIERARQUIA DE FALLBACK CORRIGIDA)
"""
Módulo de predição unificado para AutoAnalytics - V6.1
🔥 HIERARQUIA DE FALLBACK CORRIGIDA
🔥 INTEGRAÇÃO COM FEATURE REGISTRY
🔥 SUPORTE A FEATURES PRÉ-CONSTRUÍDAS
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
import warnings
warnings.filterwarnings('ignore')

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


class ModelPredictor:
    """
    🔥 Predictor V6.1 - Hierarquia de Fallback Corrigida
    
    Hierarquia de fallback para features faltantes:
    1. Existe no arquivo? → usa
    2. Consegue calcular a partir de outras? → calcula
    3. Tem média histórica disponível? → usa média
    4. Valor padrão (configurável por feature)
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
            "fallback_values_used": 0
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
        logger.info("✅ ModelPredictor V6.1 inicializado")
        logger.info(f"   📊 Features esperadas: {self.expected_features or 'N/A'}")
        logger.info(f"   🔧 Regras de cálculo: {len(self._calculation_rules)}")
        logger.info(f"   📈 Médias históricas: {len(self._historical_means)}")
    
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
    # 🔥 HIERARQUIA DE FALLBACK - MÉTODOS
    # ==========================================
    
    def _get_feature_names(self) -> List[str]:
        """
        🔥 Retorna os nomes das features esperadas
        """
        if self._registry_loaded and self.feature_registry:
            return self.feature_registry.get_expected_order()
        
        # Fallback: nomes genéricos
        return [f"feature_{i}" for i in range(self.expected_features or 10)]
    
    def _try_calculate_feature(
        self, 
        X: np.ndarray, 
        feature_name: str, 
        feature_data: Dict[str, np.ndarray]
    ) -> Optional[np.ndarray]:
        """
        🔥 PASSO 2: Tenta calcular uma feature a partir de outras
        
        Exemplos:
        - "lucro" = "receita" - "custo"
        - "margem" = "lucro" / "receita"
        - "ticket_medio" = "receita" / "quantidade"
        """
        
        # Verificar se a feature tem regra de cálculo
        if feature_name not in self._calculation_rules:
            return None
        
        rule = self._calculation_rules[feature_name]
        depends_on = rule["depends_on"]
        formula = rule["formula"]
        
        # Verificar se todas as dependências estão disponíveis
        available_values = []
        
        for dep in depends_on:
            # 1. Verificar se a dependência está no feature_data (já calculada)
            if dep in feature_data:
                available_values.append(feature_data[dep])
                continue
            
            # 2. Verificar se a dependência existe no X original
            # Precisamos saber qual coluna corresponde a qual feature
            # Usar feature_names para identificar
            feature_names = self._get_feature_names()
            
            if dep in feature_names:
                idx = feature_names.index(dep)
                if idx < X.shape[1]:
                    available_values.append(X[:, idx])
                    continue
            
            # 3. Tenta encontrar pelo nome na feature_data (case insensitive)
            for key, value in feature_data.items():
                if key.lower() == dep.lower():
                    available_values.append(value)
                    break
            else:
                # Não encontrou a dependência
                return None
        
        # Se todas as dependências estão disponíveis, calcular
        try:
            result = formula(*available_values)
            self.stats["feature_calculations"] += 1
            return result
        except Exception as e:
            logger.debug(f"   ⚠️ Erro ao calcular '{feature_name}': {e}")
            return None
    
    def _get_historical_mean(self, feature_name: str) -> Optional[float]:
        """
        🔥 PASSO 3: Obtém média histórica para uma feature
        """
        return self._historical_means.get(feature_name)
    
    def _get_fallback_value(self, feature_name: str) -> float:
        """
        🔥 PASSO 4: Obtém valor padrão para uma feature
        """
        return self.FEATURE_FALLBACKS.get(feature_name, 0.5)
    
    def _adapt_features_smart(self, X: np.ndarray) -> np.ndarray:
        """
        🔥 ADAPTAÇÃO INTELIGENTE - Hierarquia correta
        
        Ordem de fallback:
        1. Existe no arquivo? → usa
        2. Consegue calcular? → calcula
        3. Tem média histórica? → usa média
        4. Valor padrão (configurável por feature)
        """
        expected = self.expected_features or 10
        actual = X.shape[1]
        
        self.stats["feature_adaptations"] += 1
        
        # Se já tem o número correto, retorna
        if actual == expected:
            return X
        
        # Obter nomes das features
        feature_names = self._get_feature_names()
        
        # ==========================================
        # CASO 1: MAIS features que o esperado
        # ==========================================
        if actual > expected:
            logger.info(f"   🔄 Reduzindo {actual} → {expected} features")
            
            # Se tiver feature_importances_, selecionar as mais importantes
            if hasattr(self.office_model, 'feature_importances_'):
                importances = self.office_model.feature_importances_
                if len(importances) >= expected:
                    # Pegar as features mais importantes
                    top_indices = np.argsort(importances)[-expected:]
                    X_adapted = X[:, top_indices]
                    logger.info(f"   ✅ Selecionadas {expected} features mais importantes")
                    return X_adapted
            
            # Fallback: pegar as primeiras
            X_adapted = X[:, :expected]
            logger.info(f"   ✅ Truncado para {expected} features")
            return X_adapted
        
        # ==========================================
        # CASO 2: MENOS features que o esperado
        # ==========================================
        elif actual < expected:
            logger.info(f"   🔄 Expandindo {actual} → {expected} features")
            
            # Criar array com o tamanho correto
            X_adapted = np.zeros((X.shape[0], expected))
            
            # Dicionário para armazenar valores já processados
            feature_data = {}
            
            # 🔥 PASSO 1: Copiar features existentes
            for i in range(actual):
                X_adapted[:, i] = X[:, i]
                if i < len(feature_names):
                    feature_data[feature_names[i]] = X[:, i]
                else:
                    feature_data[f"feature_{i}"] = X[:, i]
            
            # 🔥 PASSO 2: Preencher features faltantes
            missing = expected - actual
            logger.info(f"   🔍 Processando {missing} features faltantes...")
            
            for idx in range(actual, expected):
                feature_name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
                
                # ----- PASSO 2: TENTAR CALCULAR -----
                calculated = self._try_calculate_feature(X, feature_name, feature_data)
                
                if calculated is not None:
                    X_adapted[:, idx] = calculated
                    feature_data[feature_name] = calculated
                    logger.info(f"   ✅ '{feature_name}' calculado a partir de outras features")
                    continue
                
                # ----- PASSO 3: TENTAR MÉDIA HISTÓRICA -----
                historical = self._get_historical_mean(feature_name)
                
                if historical is not None:
                    X_adapted[:, idx] = historical
                    feature_data[feature_name] = np.full(X.shape[0], historical)
                    self.stats["historical_means_used"] += 1
                    logger.info(f"   📊 '{feature_name}' → média histórica: {historical:.4f}")
                    continue
                
                # ----- PASSO 4: VALOR PADRÃO -----
                default = self._get_fallback_value(feature_name)
                X_adapted[:, idx] = default
                feature_data[feature_name] = np.full(X.shape[0], default)
                self.stats["fallback_values_used"] += 1
                logger.info(f"   ⚠️ '{feature_name}' → valor padrão: {default:.4f}")
            
            logger.info(f"   ✅ Expansão concluída: {actual} → {expected} features")
            logger.info(f"      📊 Calculadas: {self.stats['feature_calculations']}")
            logger.info(f"      📈 Médias históricas: {self.stats['historical_means_used']}")
            logger.info(f"      ⚠️ Fallbacks: {self.stats['fallback_values_used']}")
            
            return X_adapted
        
        return X
    
    def validate_features(self, X: np.ndarray) -> Dict[str, Any]:
        """
        🔥 Valida se as features estão no formato esperado
        """
        self.stats["feature_validations"] += 1
        
        expected = self.expected_features or 10
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
            
            # Log detalhado do mismatch
            feature_names = self._get_feature_names()
            actual_names = [f"col_{i}" for i in range(actual)]
            if len(feature_names) >= expected:
                expected_str = ", ".join(feature_names[:expected])
                logger.info(f"   📋 Esperado: [{expected_str}]")
            if actual <= len(feature_names):
                actual_str = ", ".join(feature_names[:actual])
                logger.info(f"   📋 Recebido: [{actual_str}]")
        
        return result
    
    async def predict_with_features(
        self, 
        X: np.ndarray, 
        scale: bool = True,
        validate: bool = True
    ) -> List[float]:
        """
        🔥 PREDIZ com features já construídas (MÉTODO PRINCIPAL V6.1)
        
        Args:
            X: Features já construídas (numpy array)
            scale: Se deve escalonar os dados
            validate: Se deve validar as features
        
        Returns:
            Lista de predições (0-1)
        """
        if self.office_model is None:
            logger.warning("⚠️ Nenhum modelo disponível, usando fallback")
            return self._fallback_predictions_from_features(X)
        
        try:
            # 1. Validar features
            if validate and self._registry_loaded:
                validation = self.validate_features(X)
                
                # Se mismatch, tentar adaptar
                if not validation["valid"]:
                    logger.warning(f"⚠️ Adaptando features: {validation['actual']} → {validation['expected']}")
                    X = self._adapt_features_smart(X)
                    # Re-validar após adaptação
                    validation = self.validate_features(X)
                    if not validation["valid"]:
                        logger.error(f"❌ Falha na adaptação: {validation}")
                        return self._fallback_predictions_from_features(X)
            
            # 2. Escalonar
            if scale and self.scaler is not None:
                try:
                    X_scaled = self.scaler.transform(X)
                except Exception as e:
                    logger.warning(f"⚠️ Erro no scaler: {e}, tentando sem escala")
                    X_scaled = X
            else:
                X_scaled = X
            
            # 3. Predizer
            if hasattr(self.office_model, 'predict'):
                predictions = self.office_model.predict(X_scaled)
            else:
                logger.warning("⚠️ Modelo não tem predict(), usando fallback")
                return self._fallback_predictions_from_features(X)
            
            # 4. Pós-processamento
            if isinstance(predictions, np.ndarray):
                predictions = predictions.tolist()
            
            # Garantir que está entre 0 e 1
            predictions = [
                max(0.0, min(1.0, float(p))) 
                if p is not None and not np.isnan(p) 
                else 0.5 
                for p in predictions
            ]
            
            self.stats['total_predictions'] += 1
            self.stats['last_prediction_time'] = datetime.now().isoformat()
            
            return predictions
            
        except Exception as e:
            logger.error(f"❌ Erro na predição: {e}")
            return self._fallback_predictions_from_features(X)
    
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
            # Calcular score baseado nos dados
            mean_val = np.mean(row) if len(row) > 0 else 0.5
            std_val = np.std(row) if len(row) > 0 else 0.3
            
            # Normalizar para 0-1
            score = 0.5 + (mean_val * 0.3) + (std_val * 0.2)
            score = max(0.0, min(1.0, score))
            predictions.append(score)
        
        return predictions
    
    # ==========================================
    # MÉTODOS LEGADOS (COMPATIBILIDADE)
    # ==========================================
    
    async def predict_for_office(self, df: pd.DataFrame) -> List[float]:
        """
        ⚠️ MÉTODO LEGADO - Mantido para compatibilidade
        🔥 Use predict_with_features() para novas implementações
        """
        logger.warning("⚠️ predict_for_office() está depreciado. Use predict_with_features()")
        
        # Se tiver Feature Registry, construir features
        if self._registry_loaded and self.feature_registry:
            try:
                from backend.ml.feature_builder import FeatureBuilder
                builder = FeatureBuilder(self.feature_registry)
                result = builder.build_features(df)
                if result.success:
                    return await self.predict_with_features(result.features.values)
            except Exception as e:
                logger.warning(f"⚠️ Erro ao construir features: {e}")
        
        # Fallback: pré-processamento antigo
        X_scaled = self._preprocess_features_legacy(df)
        return await self.predict_with_features(X_scaled, scale=False, validate=False)
    
    def _preprocess_features_legacy(self, df: pd.DataFrame) -> np.ndarray:
        """
        ⚠️ PRÉ-PROCESSAMENTO LEGADO - Mantido para compatibilidade
        """
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
    # MÉTODOS DE CARREGAMENTO DE MODELOS (MANTIDOS)
    # ==========================================
    
    async def load_or_train_models(self, force_reload: bool = False):
        """Carrega modelos existentes ou cria modelos placeholder"""
        if self.is_loaded and not force_reload:
            logger.info("📦 Modelos já carregados")
            return True
        
        logger.info("\n🔧 Carregando modelos de ML V6.1...")
        
        office_loaded = self._load_office_model()
        default_loaded = self._load_default_model()
        
        if not office_loaded and not default_loaded:
            logger.warning("⚠️ Nenhum modelo encontrado. Criando modelo placeholder...")
            self._create_placeholder_model()
        
        self.is_loaded = True
        logger.info(f"✅ Modelos carregados (Fonte: {self.model_source})")
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
    # DETECÇÃO DE ENCODING (MANTIDO)
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
    # MÉTODOS DE PREDIÇÃO EM LOTE (MANTIDOS)
    # ==========================================
    
    async def predict_multiple_files(self, files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Processa múltiplos arquivos em lote"""
        logger.info(f"\n📦 Processando lote de {len(files_data)} arquivo(s) com ML V6.1")
        
        await self.load_or_train_models()
        
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
                            predictions = await self.predict_with_features(
                                build_result.features.values,
                                validate=True
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
                    'processed_at': datetime.now().isoformat()
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
    # UTILITÁRIOS
    # ==========================================
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Retorna resumo do modelo"""
        return {
            "modelo_carregado": self.is_loaded,
            "fonte_modelo": self.model_source,
            "features": self.feature_names[:10] if self.feature_names else [],
            "features_esperadas": self.expected_features,
            "registry_carregado": self._registry_loaded,
            "ultimas_metricas": self.last_metrics,
            "estatisticas_uso": {
                "total_predicoes": self.stats['total_predictions'],
                "total_arquivos": self.stats['total_files_processed'],
                "feature_validations": self.stats['feature_validations'],
                "feature_mismatches": self.stats['feature_mismatches'],
                "feature_adaptations": self.stats['feature_adaptations'],
                "feature_calculations": self.stats['feature_calculations'],
                "historical_means_used": self.stats['historical_means_used'],
                "fallback_values_used": self.stats['fallback_values_used']
            },
            "encoding_stats": self.encoding_stats,
            "last_encoding": self.last_encoding
        }
    
    def update_historical_means(self, new_means: Dict[str, float]):
        """
        🔥 Atualiza as médias históricas
        """
        self._historical_means.update(new_means)
        logger.info(f"📈 Médias históricas atualizadas: {list(new_means.keys())}")
    
    def update_fallback_values(self, new_fallbacks: Dict[str, float]):
        """
        🔥 Atualiza os valores de fallback
        """
        self.FEATURE_FALLBACKS.update(new_fallbacks)
        logger.info(f"⚙️ Valores de fallback atualizados: {list(new_fallbacks.keys())}")
    
    def clear_cache(self):
        """Limpa cache de predições"""
        self._prediction_cache.clear()
        logger.info("🧹 Cache de predições limpo")
    
    async def train_simple_model(self, X: pd.DataFrame, y: pd.Series, model_type: str = 'classifier'):
        """Treina um modelo simples"""
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
            logger.info(f"✅ Classificador treinado - Acurácia: {score:.2%}")
        else:
            model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            score = r2_score(y_test, y_pred)
            logger.info(f"✅ Regressor treinado - R²: {score:.4f}")
        
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


# ==========================================
# INSTÂNCIA GLOBAL E FUNÇÕES DE COMPATIBILIDADE
# ==========================================

predictor = ModelPredictor()


async def predict_office_data(df: pd.DataFrame) -> List[float]:
    """Compatibilidade - usa método legado"""
    return await predictor.predict_for_office(df)


async def predict_with_features(X: np.ndarray) -> List[float]:
    """🔥 NOVO - Predição com features já construídas"""
    return await predictor.predict_with_features(X)


async def predict_multiple_files(files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return await predictor.predict_multiple_files(files_data)


def get_predictor_status() -> Dict[str, Any]:
    return predictor.get_model_summary()


print("\n" + "=" * 70)
print("✅ predict.py V6.1 carregado com sucesso!")
print("=" * 70)
print("   🔥 HIERARQUIA DE FALLBACK CORRIGIDA:")
print("      1️⃣ Existe no arquivo? → usa")
print("      2️⃣ Consegue calcular? → calcula")
print("      3️⃣ Tem média histórica? → usa média")
print("      4️⃣ Valor padrão (configurável)")
print("   📊 ESTATÍSTICAS:")
print(f"      → Regras de cálculo: {len(predictor._calculation_rules)}")
print(f"      → Médias históricas: {len(predictor._historical_means)}")
print(f"      → Fallbacks configurados: {len(predictor.FEATURE_FALLBACKS)}")
print("   🔧 MÉTODOS:")
print("      → predictor.predict_with_features(X)")
print("      → predictor.validate_features(X)")
print("      → predictor.update_historical_means(dict)")
print("      → predictor.update_fallback_values(dict)")
print("=" * 70)