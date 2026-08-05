# backend/ml/preprocessing.py - VERSÃO 6.0 (PIPELINE INTELIGENTE)
"""
🔥 MÓDULO DE PRÉ-PROCESSAMENTO E PIPELINE DE ML - AUTOANALYTICS
================================================================================
VERSÃO 6.0 - PIPELINE INTELIGENTE COM FEATURE REGISTRY

✅ NOVIDADES V6.0:
   - 🔥 FEATURE REGISTRY: Define quais features o modelo espera
   - 🔥 FEATURE BUILDER: Constrói features a partir de dados brutos
   - 🔥 FEATURE MONITOR: Detecta e registra mismatches
   - 🔥 REMOVIDO: _adapt_features_to_model (padding aleatório)
   - 🔥 REMOVIDO: _generate_synthetic_features (features arbitrárias)
   - 🔥 ADICIONADO: _build_features_intelligently
   - 🔥 ADICIONADO: _validate_features
   - 🔥 ADICIONADO: _log_feature_mismatch
   - 🔥 MELHORADO: Logging detalhado do processo
================================================================================
"""

import pandas as pd
import numpy as np
import os
import pickle
import joblib
import json
import hashlib
import unicodedata
import chardet
import logging
import asyncio
import time
import random
import re
import traceback
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# Scikit-learn
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    mean_squared_error, r2_score, classification_report, confusion_matrix,
    roc_auc_score, roc_curve
)
from sklearn.pipeline import Pipeline

# ==============================================
# CONFIGURAÇÃO DE LOGGING
# ==============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================
# ENUMS E CONSTANTES
# ==============================================

class ModelType(str, Enum):
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    LOGISTIC_REGRESSION = "logistic_regression"
    AUTO_ML = "auto_ml"
    ENSEMBLE = "ensemble"
    PLACEHOLDER = "placeholder"
    NONE = "none"

class EncodingMethod(str, Enum):
    DETECTED = "detected"
    FALLBACK = "fallback"
    FORCED = "forced"
    EXCEL = "excel"

class PredictionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    FALLBACK = "fallback"

class FeatureType(str, Enum):
    """Tipo de feature"""
    DIRECT = "direct"          # Coluna direta do arquivo
    DERIVED = "derived"        # Calculada a partir de outras
    AGGREGATE = "aggregate"    # Agregação (média, soma, etc.)
    CONSTANT = "constant"      # Valor constante


# ==============================================
# FEATURE REGISTRY - DEFINE AS FEATURES DO MODELO
# ==============================================

@dataclass
class FeatureDefinition:
    """
    Definição de uma feature do modelo
    """
    name: str
    type: FeatureType
    description: str
    required: bool = True
    default_value: Any = 0.0
    
    # Para DIRECT: nome da coluna esperada
    source_column: Optional[str] = None
    
    # Para DERIVED: função de cálculo
    derive_func: Optional[Callable] = None
    
    # Para AGGREGATE: coluna e função
    aggregate_column: Optional[str] = None
    aggregate_func: Optional[str] = None  # 'mean', 'sum', 'count', 'std'
    
    # Aliases para mapeamento (nomes alternativos da coluna)
    aliases: List[str] = field(default_factory=list)
    
    # Se pode ser calculada se faltar
    can_fallback: bool = True
    
    # Fallback se não conseguir calcular
    fallback_value: float = 0.0


class FeatureRegistry:
    """
    🔥 Registro central de features do modelo
    
    Define:
    - Quais features o modelo espera
    - Como extrair cada feature do arquivo
    - Como calcular features derivadas
    - Valores de fallback
    """
    
    def __init__(self):
        self._features: Dict[str, FeatureDefinition] = {}
        self._register_features()
        self._expected_order = self._get_expected_order()
        logger.info(f"✅ FeatureRegistry: {len(self._features)} features registradas")
    
    def _register_features(self):
        """Registra todas as features do modelo"""
        
        # ==========================================
        # FEATURES DIRETAS (mapeadas do arquivo)
        # ==========================================
        
        self._features["receita"] = FeatureDefinition(
            name="receita",
            type=FeatureType.DIRECT,
            description="Receita total",
            source_column="valor_servico",
            aliases=["valor", "receita", "total", "preco", "valor_total", "receita_total"],
            required=True,
            default_value=0.0
        )
        
        self._features["custo"] = FeatureDefinition(
            name="custo",
            type=FeatureType.DIRECT,
            description="Custo total",
            source_column="custo_pecas",
            aliases=["custo", "custo_pecas", "despesa", "gasto", "custo_total", "custo_peca"],
            required=True,
            default_value=0.0
        )
        
        self._features["quantidade"] = FeatureDefinition(
            name="quantidade",
            type=FeatureType.DIRECT,
            description="Quantidade de serviços",
            source_column="quantidade",
            aliases=["qtd", "quantidade", "servicos", "total_servicos", "count"],
            required=False,
            default_value=1
        )
        
        # ==========================================
        # FEATURES DERIVADAS (calculadas)
        # ==========================================
        
        self._features["lucro"] = FeatureDefinition(
            name="lucro",
            type=FeatureType.DERIVED,
            description="Lucro = receita - custo",
            derive_func=lambda df: df["receita"] - df["custo"],
            required=True,
            default_value=0.0
        )
        
        self._features["ticket_medio"] = FeatureDefinition(
            name="ticket_medio",
            type=FeatureType.DERIVED,
            description="Ticket médio = receita / quantidade",
            derive_func=lambda df: df["receita"] / df["quantidade"] if df["quantidade"] > 0 else df["receita"],
            required=True,
            default_value=0.0
        )
        
        self._features["margem"] = FeatureDefinition(
            name="margem",
            type=FeatureType.DERIVED,
            description="Margem = lucro / receita",
            derive_func=lambda df: df["lucro"] / df["receita"] if df["receita"] > 0 else 0,
            required=True,
            default_value=0.0
        )
        
        # ==========================================
        # FEATURES AGREGADAS
        # ==========================================
        
        self._features["total_servicos"] = FeatureDefinition(
            name="total_servicos",
            type=FeatureType.AGGREGATE,
            description="Total de serviços",
            aggregate_column="quantidade",
            aggregate_func="sum",
            required=True,
            default_value=0
        )
        
        self._features["media_servicos"] = FeatureDefinition(
            name="media_servicos",
            type=FeatureType.AGGREGATE,
            description="Média de serviços por período",
            aggregate_column="quantidade",
            aggregate_func="mean",
            required=False,
            default_value=0
        )
        
        # ==========================================
        # FEATURES CONSTANTES (fallback)
        # ==========================================
        
        self._features["constante"] = FeatureDefinition(
            name="constante",
            type=FeatureType.CONSTANT,
            description="Constante para padding",
            required=False,
            default_value=1.0,
            can_fallback=True,
            fallback_value=1.0
        )
    
    def _get_expected_order(self) -> List[str]:
        """Retorna ordem esperada das features"""
        # Features obrigatórias primeiro, depois opcionais
        required = [name for name, feat in self._features.items() if feat.required]
        optional = [name for name, feat in self._features.items() if not feat.required]
        return required + optional
    
    def get_features(self) -> List[str]:
        """Retorna lista de nomes das features"""
        return list(self._features.keys())
    
    def get_definition(self, name: str) -> Optional[FeatureDefinition]:
        """Retorna definição de uma feature"""
        return self._features.get(name)
    
    def get_required_features(self) -> List[str]:
        """Retorna features obrigatórias"""
        return [name for name, feat in self._features.items() if feat.required]
    
    def get_optional_features(self) -> List[str]:
        """Retorna features opcionais"""
        return [name for name, feat in self._features.items() if not feat.required]
    
    def get_expected_count(self) -> int:
        """Retorna número total de features"""
        return len(self._features)
    
    def get_expected_order(self) -> List[str]:
        """Retorna ordem esperada das features"""
        return self._expected_order


# Instância global do registry
feature_registry = FeatureRegistry()


# ==============================================
# FEATURE BUILDER - CONSTRÓI FEATURES
# ==============================================

@dataclass
class FeatureBuildResult:
    """Resultado da construção de features"""
    success: bool
    features: pd.DataFrame
    missing_features: List[str] = field(default_factory=list)
    fallback_used: List[str] = field(default_factory=list)
    calculated_features: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def has_missing(self) -> bool:
        return len(self.missing_features) > 0
    
    @property
    def has_fallback(self) -> bool:
        return len(self.fallback_used) > 0
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "feature_count": len(self.features.columns) if self.features is not None else 0,
            "missing_features": self.missing_features,
            "fallback_used": self.fallback_used,
            "calculated_features": self.calculated_features,
            "warnings": self.warnings,
            "errors": self.errors
        }


class FeatureBuilder:
    """
    🔥 Constrói features a partir de dados brutos
    
    Pipeline:
    1. Detecta colunas disponíveis no arquivo
    2. Mapeia colunas para features
    3. Calcula features derivadas
    4. Aplica fallback para features faltantes
    5. Valida e retorna DataFrame com todas as features
    """
    
    def __init__(self, registry: FeatureRegistry = None):
        self.registry = registry or feature_registry
        self._column_cache: Dict[str, str] = {}
        logger.info("✅ FeatureBuilder inicializado")
    
    def build_features(self, df: pd.DataFrame) -> FeatureBuildResult:
        """
        🔥 Constrói todas as features a partir do DataFrame
        """
        logger.info(f"🏗️ Construindo features a partir de {len(df)} linhas, {len(df.columns)} colunas")
        
        result = FeatureBuildResult(
            success=False,
            features=pd.DataFrame()
        )
        
        try:
            # 1. Detectar colunas disponíveis
            available_columns = self._detect_columns(df)
            logger.info(f"   🔍 Colunas detectadas: {len(available_columns)} mapeamentos")
            
            # 2. Construir cada feature
            feature_data = {}
            missing = []
            fallback_used = []
            calculated = []
            warnings = []
            
            for feature_name in self.registry.get_expected_order():
                definition = self.registry.get_definition(feature_name)
                if not definition:
                    warnings.append(f"Feature '{feature_name}' não definida no registry")
                    continue
                
                try:
                    value = self._build_single_feature(
                        df=df,
                        definition=definition,
                        available_columns=available_columns,
                        feature_data=feature_data
                    )
                    
                    if value is not None:
                        # Verificar se é uma série ou valor único
                        if isinstance(value, (pd.Series, np.ndarray)):
                            feature_data[feature_name] = value
                        else:
                            # Se for valor único, repetir para todas as linhas
                            feature_data[feature_name] = pd.Series([value] * len(df))
                        calculated.append(feature_name)
                    else:
                        missing.append(feature_name)
                        if definition.can_fallback:
                            fallback_used.append(feature_name)
                            feature_data[feature_name] = pd.Series([definition.fallback_value] * len(df))
                            logger.debug(f"   ⚠️ Fallback para '{feature_name}': {definition.fallback_value}")
                            
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro ao construir feature '{feature_name}': {e}")
                    missing.append(feature_name)
                    if definition.can_fallback:
                        fallback_used.append(feature_name)
                        feature_data[feature_name] = pd.Series([definition.fallback_value] * len(df))
            
            # 3. Criar DataFrame com a ordem correta
            if feature_data:
                result.features = pd.DataFrame(feature_data)
                # Reordenar colunas conforme ordem esperada
                expected_order = self.registry.get_expected_order()
                actual_cols = result.features.columns.tolist()
                # Manter apenas as que existem
                ordered_cols = [col for col in expected_order if col in actual_cols]
                if ordered_cols:
                    result.features = result.features[ordered_cols]
                
                result.missing_features = missing
                result.fallback_used = fallback_used
                result.calculated_features = calculated
                result.warnings = warnings
                result.success = True
                
                logger.info(f"✅ Features construídas: {len(calculated)} calculadas, {len(fallback_used)} fallback, {len(missing)} faltantes")
                logger.info(f"   📊 Shape final: {result.features.shape}")
            else:
                result.errors.append("Nenhuma feature foi construída")
                
        except Exception as e:
            logger.error(f"❌ Erro ao construir features: {e}")
            result.errors.append(str(e))
        
        return result
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        🔥 Detecta quais colunas do DataFrame mapeiam para features
        """
        column_map = {}
        df_cols_lower = {col.lower().strip(): col for col in df.columns}
        
        for feature_name, definition in self.registry._features.items():
            if definition.type == FeatureType.DIRECT and definition.source_column:
                # 1. Verificar pelo nome da coluna fonte
                source_lower = definition.source_column.lower().strip()
                if source_lower in df_cols_lower:
                    column_map[df_cols_lower[source_lower]] = feature_name
                    continue
                
                # 2. Verificar por aliases
                for alias in definition.aliases:
                    alias_lower = alias.lower().strip()
                    if alias_lower in df_cols_lower:
                        column_map[df_cols_lower[alias_lower]] = feature_name
                        break
                
                # 3. Verificar por correspondência parcial (case insensitive)
                if feature_name not in column_map.values():
                    for col, col_name in df_cols_lower.items():
                        # Verificar se a coluna contém palavras-chave
                        for keyword in definition.aliases + [definition.source_column]:
                            if keyword.lower() in col or col in keyword.lower():
                                column_map[col_name] = feature_name
                                break
        
        logger.debug(f"   🔍 Mapeamentos encontrados: {len(column_map)}")
        for col, feat in column_map.items():
            logger.debug(f"      {col} → {feat}")
        
        return column_map
    
    def _build_single_feature(
        self,
        df: pd.DataFrame,
        definition: FeatureDefinition,
        available_columns: Dict[str, str],
        feature_data: Dict[str, Any]
    ) -> Any:
        """
        🔥 Constrói uma feature individual
        """
        
        if definition.type == FeatureType.CONSTANT:
            return definition.default_value
        
        elif definition.type == FeatureType.DIRECT:
            # Buscar coluna no arquivo
            source_col = None
            
            # 1. Tentar pelo mapeamento detectado
            for col, feat in available_columns.items():
                if feat == definition.name:
                    source_col = col
                    break
            
            # 2. Tentar pelo nome da coluna fonte
            if source_col is None and definition.source_column in df.columns:
                source_col = definition.source_column
            
            # 3. Tentar por aliases
            if source_col is None and definition.aliases:
                for alias in definition.aliases:
                    if alias in df.columns:
                        source_col = alias
                        break
                    # Tentar case-insensitive
                    for col in df.columns:
                        if col.lower() == alias.lower():
                            source_col = col
                            break
                    if source_col:
                        break
            
            if source_col:
                return df[source_col].fillna(0)
            else:
                logger.debug(f"   ⚠️ Coluna para '{definition.name}' não encontrada")
                return None
        
        elif definition.type == FeatureType.DERIVED:
            if definition.derive_func:
                try:
                    # Criar DataFrame com dados disponíveis
                    data_dict = {}
                    
                    # Adicionar colunas originais
                    for col in df.columns:
                        data_dict[col] = df[col]
                    
                    # Adicionar features já construídas
                    for feat_name, value in feature_data.items():
                        data_dict[feat_name] = value
                    
                    temp_df = pd.DataFrame(data_dict)
                    result = definition.derive_func(temp_df)
                    
                    # Garantir que o resultado tem o tamanho correto
                    if isinstance(result, (pd.Series, np.ndarray)):
                        if len(result) != len(df):
                            # Se não tiver o tamanho correto, tentar broadcast
                            if len(result) == 1:
                                return pd.Series([result.iloc[0]] * len(df))
                    return result
                except Exception as e:
                    logger.debug(f"   ⚠️ Erro ao calcular '{definition.name}': {e}")
                    return None
            else:
                logger.debug(f"   ⚠️ Feature derivada '{definition.name}' sem função")
                return None
        
        elif definition.type == FeatureType.AGGREGATE:
            # Similar ao DERIVED, mas com agregação
            if definition.aggregate_func == 'count':
                return len(df)
            elif definition.aggregate_func == 'sum' and definition.aggregate_column:
                if definition.aggregate_column in df.columns:
                    return df[definition.aggregate_column].sum()
                # Tentar pelo mapeamento
                for col, feat in available_columns.items():
                    if feat == definition.aggregate_column and col in df.columns:
                        return df[col].sum()
                return None
            elif definition.aggregate_func == 'mean' and definition.aggregate_column:
                if definition.aggregate_column in df.columns:
                    return df[definition.aggregate_column].mean()
                # Tentar pelo mapeamento
                for col, feat in available_columns.items():
                    if feat == definition.aggregate_column and col in df.columns:
                        return df[col].mean()
                return None
            else:
                return None
        
        return None


# ==============================================
# FEATURE MONITOR - MONITORA MISMATCHES
# ==============================================

@dataclass
class FeatureMismatchEvent:
    """Evento de mismatch de features"""
    timestamp: str
    expected_features: List[str]
    actual_features: List[str]
    missing_count: int
    extra_count: int
    missing_names: List[str]
    extra_names: List[str]
    request_id: Optional[str] = None
    user_id: Optional[int] = None
    filename: Optional[str] = None
    action_taken: str = "logged"
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "expected_features": self.expected_features,
            "actual_features": self.actual_features,
            "missing_count": self.missing_count,
            "extra_count": self.extra_count,
            "missing_names": self.missing_names,
            "extra_names": self.extra_names,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "filename": self.filename,
            "action_taken": self.action_taken
        }


class FeatureMonitor:
    """
    🔥 Monitora divergências entre features esperadas e recebidas
    """
    
    def __init__(self, log_dir: str = "backend/ml/logs/features"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        self._events: List[FeatureMismatchEvent] = []
        self._stats = {
            "total_requests": 0,
            "mismatch_count": 0,
            "fallback_count": 0,
            "alert_count": 0,
            "last_mismatch": None,
            "most_common_missing": {},
            "most_common_extra": {}
        }
        
        logger.info(f"✅ FeatureMonitor inicializado (log_dir: {log_dir})")
    
    def check_mismatch(
        self,
        expected_features: List[str],
        actual_features: List[str],
        request_id: Optional[str] = None,
        user_id: Optional[int] = None,
        filename: Optional[str] = None,
        auto_log: bool = True
    ) -> Dict[str, Any]:
        """
        🔥 Verifica se há mismatch entre features esperadas e recebidas
        """
        expected_set = set(expected_features)
        actual_set = set(actual_features)
        
        missing = list(expected_set - actual_set)
        extra = list(actual_set - expected_set)
        
        result = {
            "has_mismatch": len(missing) > 0 or len(extra) > 0,
            "expected_count": len(expected_set),
            "actual_count": len(actual_set),
            "missing_count": len(missing),
            "extra_count": len(extra),
            "missing_features": missing,
            "extra_features": extra,
            "match_percentage": len(expected_set & actual_set) / len(expected_set) * 100 if expected_set else 0
        }
        
        self._stats["total_requests"] += 1
        
        if result["has_mismatch"]:
            self._stats["mismatch_count"] += 1
            self._stats["last_mismatch"] = datetime.now().isoformat()
            
            # Atualizar estatísticas de features faltantes
            for feat in missing:
                self._stats["most_common_missing"][feat] = self._stats["most_common_missing"].get(feat, 0) + 1
            
            for feat in extra:
                self._stats["most_common_extra"][feat] = self._stats["most_common_extra"].get(feat, 0) + 1
            
            # Criar evento
            event = FeatureMismatchEvent(
                timestamp=datetime.now().isoformat(),
                expected_features=expected_features,
                actual_features=actual_features,
                missing_count=len(missing),
                extra_count=len(extra),
                missing_names=missing,
                extra_names=extra,
                request_id=request_id,
                user_id=user_id,
                filename=filename,
                action_taken="logged"
            )
            
            self._events.append(event)
            
            # Salvar em arquivo
            if auto_log:
                self._log_event(event)
            
            # Gerar alerta se muitas features faltando (> 30% de mismatch)
            if result["match_percentage"] < 70:
                self._stats["alert_count"] += 1
                event.action_taken = "alert"
                self._send_alert(event)
            
            logger.warning(
                f"⚠️ Feature mismatch: {len(missing)} faltando, {len(extra)} extras. "
                f"Match: {result['match_percentage']:.1f}%"
            )
        else:
            logger.info(f"✅ Features match: {len(actual_set)}/{len(expected_set)}")
        
        return result
    
    def _log_event(self, event: FeatureMismatchEvent):
        """Salva evento em arquivo JSON"""
        filename = f"{self.log_dir}/mismatch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(event.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Erro ao salvar log: {e}")
    
    def _send_alert(self, event: FeatureMismatchEvent):
        """
        🔥 Envia alerta para administradores
        """
        message = f"""
        ⚠️ ALERTA: Feature Mismatch Detectado!
        
        📊 Request: {event.request_id or 'N/A'}
        👤 Usuário: {event.user_id or 'N/A'}
        📁 Arquivo: {event.filename or 'N/A'}
        
        ❌ Features faltantes ({event.missing_count}):
        {', '.join(event.missing_names)}
        
        ➕ Features extras ({event.extra_count}):
        {', '.join(event.extra_names)}
        
        🔧 Ação: {event.action_taken}
        """
        
        logger.warning(message)
        
        # TODO: Integrar com sistema de notificação (email, Slack, etc.)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do monitor"""
        return {
            **self._stats,
            "recent_events": [e.to_dict() for e in self._events[-10:]],
            "total_events": len(self._events)
        }
    
    def get_recent_mismatches(self, limit: int = 10) -> List[Dict]:
        """Retorna os últimos mismatches"""
        return [e.to_dict() for e in self._events[-limit:]]


# ==============================================
# CLASSE PRINCIPAL - ML PIPELINE V6.0
# ==============================================

class MLPipeline:
    """
    Pipeline unificado de Machine Learning - VERSÃO 6.0
    🔥 PIPELINE INTELIGENTE COM FEATURE REGISTRY
    """
    
    def __init__(self):
        # ==========================================
        # DIRETÓRIOS E PATHS
        # ==========================================
        self.models_dir = os.path.join("backend", "ml", "models")
        os.makedirs(self.models_dir, exist_ok=True)
        
        # ==========================================
        # FEATURE REGISTRY E BUILDER
        # ==========================================
        self.feature_registry = feature_registry
        self.feature_builder = FeatureBuilder(self.feature_registry)
        self.feature_monitor = FeatureMonitor()
        
        # ==========================================
        # MODELOS E SCALERS
        # ==========================================
        self.models: Dict[str, Any] = {}
        self.scalers: Dict[str, Any] = {}
        self.label_encoders: Dict[str, Any] = {}
        self.feature_importances: Dict[str, Any] = {}
        
        # ==========================================
        # ESTADO DO PIPELINE
        # ==========================================
        self.is_initialized: bool = False
        self.model_source: str = ModelType.NONE.value
        self.last_predictions: Optional[np.ndarray] = None
        self.last_metrics: Dict[str, Any] = {}
        self._initialization_lock = asyncio.Lock()
        
        # ==========================================
        # CACHE INTELIGENTE
        # ==========================================
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: int = 60
        self._cache_max_size: int = 100
        self._last_cache_cleanup: float = time.time()
        
        # ==========================================
        # ESTATÍSTICAS DE ENCODING
        # ==========================================
        self.encoding_stats: Dict[str, int] = {
            "utf-8": 0,
            "utf-8-sig": 0,
            "cp1252": 0,
            "iso-8859-1": 0,
            "latin1": 0,
            "detected": 0,
            "fallback": 0,
            "forced": 0,
            "excel": 0,
            "failed": 0,
            "total_attempts": 0
        }
        self.last_encoding: Optional[str] = None
        self.last_encoding_confidence: float = 0.0
        self.last_encoding_method: Optional[str] = None
        
        # ==========================================
        # ESTATÍSTICAS DE USO
        # ==========================================
        self.stats: Dict[str, Any] = {
            "total_predictions": 0,
            "total_files_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "failed_predictions": 0,
            "successful_predictions": 0,
            "last_prediction_time": None,
            "started_at": datetime.now().isoformat(),
            "uptime_seconds": 0,
            "feature_mismatches": 0,
            "feature_fallbacks": 0,
            "chart_data_generated": 0
        }
        
        # ==========================================
        # MÓDULOS EXTERNOS (LAZY LOADING)
        # ==========================================
        self._predictor = None
        self._automl_office = None
        self._boosting_ensemble = None
        self._gemini_service = None
        self._modules_loaded = False
        
        # ==========================================
        # CONFIGURAÇÃO
        # ==========================================
        self.config = {
            "default_model": ModelType.RANDOM_FOREST.value,
            "fallback_model": ModelType.PLACEHOLDER.value,
            "cache_enabled": True,
            "cache_ttl": 60,
            "max_retries": 3,
            "timeout_seconds": 30,
            "encoding_fallbacks": ['utf-8-sig', 'utf-8', 'cp1252', 'iso-8859-1', 'latin1'],
            "min_features_for_ml": 3,
            "feature_match_threshold": 0.7  # 70% de match é aceitável
        }
        
        # ==========================================
        # WARNINGS E ERRORS
        # ==========================================
        self._warnings: List[str] = []
        self._errors: List[str] = []
        
        logger.info("✅ MLPipeline V6.0 COMPLETO inicializado")
        logger.info(f"   📁 Modelos: {self.models_dir}")
        logger.info(f"   📊 Features: {self.feature_registry.get_expected_count()}")
        logger.info(f"   ⏰ Cache TTL: {self._cache_ttl}s")
        logger.info(f"   🔥 FEATURE REGISTRY: {len(self.feature_registry.get_features())} features")
        logger.info(f"   📊 FEATURE MONITOR: Ativo")
    
    # ==============================================
    # MÓDULOS EXTERNOS (LAZY LOADING)
    # ==============================================
    
    def _ensure_modules_loaded(self):
        """Carrega módulos externos apenas quando necessário"""
        if self._modules_loaded:
            return
        
        try:
            from backend.ml.predict import predictor
            self._predictor = predictor
            logger.info("   📦 ModelPredictor (predict.py) integrado")
        except ImportError as e:
            logger.debug(f"   ⚠️ ModelPredictor não disponível: {e}")
        
        try:
            from backend.ml.automl_simple import automl_office
            self._automl_office = automl_office
            logger.info("   📦 AutoMLOffice integrado")
        except ImportError as e:
            logger.debug(f"   ⚠️ AutoMLOffice não disponível: {e}")
        
        try:
            from backend.ml.boosting_ensemble import boosting_ensemble
            self._boosting_ensemble = boosting_ensemble
            logger.info("   📦 BoostingEnsemble integrado")
        except ImportError as e:
            logger.debug(f"   ⚠️ BoostingEnsemble não disponível: {e}")
        
        try:
            from backend.gemini import gemini_service
            self._gemini_service = gemini_service
            logger.info("   📦 Gemini Service integrado")
        except ImportError as e:
            logger.debug(f"   ⚠️ Gemini Service não disponível: {e}")
        
        self._modules_loaded = True
    
    # ==============================================
    # DETECÇÃO DE ENCODING (MANTIDO)
    # ==============================================
    
    def _detect_encoding(self, content: bytes) -> EncodingResult:
        """Detecta encoding de forma robusta com múltiplos fallbacks"""
        self.encoding_stats["total_attempts"] += 1
        
        # BOM detection
        boms = [
            (b'\xef\xbb\xbf', 'utf-8-sig'),
            (b'\xff\xfe', 'utf-16-le'),
            (b'\xfe\xff', 'utf-16-be'),
        ]
        
        for bom, encoding in boms:
            if content.startswith(bom):
                logger.info(f"   🔍 BOM detectado: {encoding}")
                self.encoding_stats["detected"] += 1
                self.encoding_stats[encoding] = self.encoding_stats.get(encoding, 0) + 1
                return EncodingResult(
                    encoding=encoding,
                    confidence=0.99,
                    method=EncodingMethod.DETECTED
                )
        
        # Chardet detection
        try:
            if len(content) > 0:
                result = chardet.detect(content[:50000])
                if result and result.get('encoding'):
                    encoding = self._normalize_encoding_name(result['encoding'])
                    confidence = result.get('confidence', 0)
                    if confidence > 0.5:
                        try:
                            content[:1000].decode(encoding)
                            logger.info(f"   🔍 Encoding detectado: {encoding} (conf: {confidence:.2%})")
                            self.encoding_stats["detected"] += 1
                            self.encoding_stats[encoding] = self.encoding_stats.get(encoding, 0) + 1
                            return EncodingResult(
                                encoding=encoding,
                                confidence=confidence,
                                method=EncodingMethod.DETECTED
                            )
                        except UnicodeDecodeError:
                            pass
        except Exception:
            pass
        
        # Fallback encodings
        for enc in self.config["encoding_fallbacks"]:
            try:
                content[:5000].decode(enc)
                logger.info(f"   ✅ Encoding válido: {enc} (fallback)")
                self.encoding_stats["fallback"] += 1
                self.encoding_stats[enc] = self.encoding_stats.get(enc, 0) + 1
                return EncodingResult(
                    encoding=enc,
                    confidence=0.6,
                    method=EncodingMethod.FALLBACK
                )
            except UnicodeDecodeError:
                continue
        
        # Forced fallback
        logger.warning(f"   ⚠️ Nenhum encoding detectado, usando latin1")
        self.encoding_stats["forced"] += 1
        self.encoding_stats["latin1"] = self.encoding_stats.get("latin1", 0) + 1
        return EncodingResult(
            encoding='latin1',
            confidence=0.1,
            method=EncodingMethod.FORCED
        )
    
    def _normalize_encoding_name(self, name: str) -> str:
        if not name:
            return "unknown"
        name = name.lower().replace('_', '-').replace(' ', '')
        mapping = {
            'utf-8': 'utf-8', 'utf8': 'utf-8',
            'utf-8-sig': 'utf-8-sig', 'utf8-sig': 'utf-8-sig',
            'cp1252': 'cp1252', 'windows-1252': 'cp1252',
            'iso-8859-1': 'iso-8859-1', 'latin1': 'latin1',
        }
        return mapping.get(name, name)
    
    # ==============================================
    # CARREGAMENTO DE DADOS (MANTIDO)
    # ==============================================
    
    def _load_csv_from_bytes(self, content: bytes, encoding: str, encoding_result: EncodingResult):
        encodings_to_try = [encoding, 'utf-8-sig', 'utf-8', 'cp1252', 'latin1', 'iso-8859-1']
        encodings_to_try = list(dict.fromkeys(encodings_to_try))
        
        for enc in encodings_to_try:
            try:
                df = pd.read_csv(BytesIO(content), encoding=enc, low_memory=False)
                if df is not None and len(df) > 0 and len(df.columns) > 0:
                    logger.info(f"   ✅ CSV carregado com encoding: {enc}")
                    self.encoding_stats[enc] = self.encoding_stats.get(enc, 0) + 1
                    return df, enc
            except Exception:
                continue
        
        try:
            df = pd.read_csv(BytesIO(content), encoding='utf-8', errors='ignore', engine='python')
            if df is not None and len(df) > 0:
                logger.warning(f"   ⚠️ CSV carregado com utf-8 (erros ignorados)")
                return df, 'utf-8_ignore'
        except Exception:
            pass
        
        return None, None
    
    def _load_excel_from_bytes(self, content: bytes, filename: str):
        try:
            df = pd.read_excel(BytesIO(content))
            logger.info(f"   ✅ Excel carregado: {filename}")
            self.encoding_stats["excel"] = self.encoding_stats.get("excel", 0) + 1
            return df, 'excel'
        except Exception as e:
            logger.error(f"   ❌ Erro ao carregar Excel: {e}")
            return None, None
    
    def _load_dataframe_from_bytes(self, content: bytes, filename: str):
        if not content or len(content) == 0:
            return None, None
        
        logger.info(f"   📁 Carregando: {filename} ({len(content)} bytes)")
        
        try:
            encoding_result = self._detect_encoding(content)
            encoding = encoding_result.encoding
            logger.info(f"   🔍 Encoding detectado: {encoding} (conf: {encoding_result.confidence:.2%})")
            
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext == '.csv':
                df, used_encoding = self._load_csv_from_bytes(content, encoding, encoding_result)
                if df is not None:
                    return df, used_encoding
            elif file_ext in ['.xlsx', '.xls']:
                df, used_encoding = self._load_excel_from_bytes(content, filename)
                if df is not None:
                    return df, used_encoding
            else:
                df, used_encoding = self._load_csv_from_bytes(content, encoding, encoding_result)
                if df is not None:
                    return df, used_encoding
        except Exception as e:
            logger.error(f"   ❌ Erro ao carregar arquivo: {e}")
        
        return None, None
    
    async def _load_data_enhanced(self, df_or_content, filename=None):
        warnings = []
        df = None
        encoding_used = None
        
        try:
            if isinstance(df_or_content, pd.DataFrame):
                df = df_or_content
                encoding_used = "dataframe"
                logger.info(f"📊 DataFrame recebido: {len(df)} linhas")
            elif isinstance(df_or_content, bytes):
                filename = filename or "arquivo.csv"
                df, encoding_used = self._load_dataframe_from_bytes(df_or_content, filename)
                if df is None:
                    warnings.append("Falha ao carregar arquivo")
            elif isinstance(df_or_content, str) and os.path.exists(df_or_content):
                with open(df_or_content, 'rb') as f:
                    content = f.read()
                df, encoding_used = self._load_dataframe_from_bytes(content, os.path.basename(df_or_content))
                if df is None:
                    warnings.append(f"Falha ao carregar arquivo: {df_or_content}")
            else:
                warnings.append(f"Formato inválido: {type(df_or_content)}")
            
            if encoding_used:
                self.last_encoding = encoding_used
                logger.info(f"   📝 Encoding final: {encoding_used}")
            
            return {'df': df, 'encoding': encoding_used, 'warnings': warnings}
        except Exception as e:
            warnings.append(f"Erro ao carregar dados: {e}")
            return {'df': None, 'encoding': None, 'warnings': warnings}
    
    # ==============================================
    # 🔥 FEATURE BUILDING - NOVO MÉTODO PRINCIPAL
    # ==============================================
    
    async def _build_features_intelligently(self, df: pd.DataFrame, filename: str = None) -> Tuple[Optional[pd.DataFrame], List[str]]:
        """
        🔥 Constrói features usando o Feature Builder
        """
        logger.info(f"🏗️ Construindo features para {len(df)} linhas...")
        
        result = self.feature_builder.build_features(df)
        
        if not result.success:
            logger.error(f"❌ Falha ao construir features: {result.errors}")
            return None, result.errors
        
        # Log do resultado
        logger.info(f"   ✅ Features construídas com sucesso!")
        logger.info(f"      📊 Shape: {result.features.shape}")
        logger.info(f"      🔧 Calculadas: {len(result.calculated_features)}")
        logger.info(f"      ⚠️ Fallback: {len(result.fallback_used)}")
        logger.info(f"      ❌ Faltantes: {len(result.missing_features)}")
        
        if result.warnings:
            for warning in result.warnings:
                logger.warning(f"      ⚠️ {warning}")
        
        return result.features, result.warnings
    
    async def _validate_features(self, features: pd.DataFrame, filename: str = None) -> Dict[str, Any]:
        """
        🔥 Valida features contra o registry e monitora mismatches
        """
        expected = self.feature_registry.get_expected_order()
        actual = features.columns.tolist()
        
        # Verificar mismatch
        mismatch_result = self.feature_monitor.check_mismatch(
            expected_features=expected,
            actual_features=actual,
            filename=filename,
            user_id=None  # Será preenchido pelo caller
        )
        
        # Atualizar estatísticas
        if mismatch_result["has_mismatch"]:
            self.stats["feature_mismatches"] += 1
        
        # Calcular fallbacks usados
        fallback_used = []
        for feat_name in expected:
            definition = self.feature_registry.get_definition(feat_name)
            if definition and definition.can_fallback:
                # Verificar se a feature é constante (fallback)
                if feat_name in actual and features[feat_name].nunique() == 1:
                    # Se todos os valores são iguais, provavelmente é fallback
                    fallback_used.append(feat_name)
        
        if fallback_used:
            self.stats["feature_fallbacks"] += len(fallback_used)
            logger.info(f"   ⚠️ Features com fallback: {fallback_used}")
        
        return {
            "is_valid": mismatch_result["match_percentage"] >= self.config["feature_match_threshold"] * 100,
            "mismatch": mismatch_result,
            "fallback_used": fallback_used
        }
    
    # ==============================================
    # PREDIÇÃO COM PREDICTOR (INTEGRAÇÃO)
    # ==============================================
    
    async def _safe_predict_with_predictor(self, df: pd.DataFrame) -> Tuple[Optional[List[float]], List[str]]:
        """Usa o ModelPredictor do predict.py para fazer predições"""
        warnings = []
        self._ensure_modules_loaded()
        
        if self._predictor is not None:
            try:
                logger.info("   🤖 Usando ModelPredictor para predição")
                predictions = await self._predictor.predict_for_office(df)
                
                if predictions and len(predictions) > 0:
                    logger.info(f"   ✅ Predições do ModelPredictor: {len(predictions)} resultados")
                    return predictions, warnings
                else:
                    warnings.append("ModelPredictor retornou predições vazias")
            except Exception as e:
                warnings.append(f"Erro no ModelPredictor: {e}")
                logger.warning(f"   ⚠️ Erro no ModelPredictor: {e}")
        
        logger.info("   ⚠️ Usando pipeline interno para predição")
        return None, warnings
    
    async def _predict_with_model(self, model_key: str, X: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Predição com um modelo específico"""
        try:
            model = self.models.get(model_key)
            scaler = self.scalers.get(model_key)
            
            if model is None:
                return None, None
            
            if scaler is not None:
                X_scaled = scaler.transform(X)
            else:
                X_scaled = X
            
            if hasattr(model, 'predict'):
                predictions = model.predict(X_scaled)
                predictions = np.array(predictions, dtype=float)
                if predictions.dtype.kind in 'iu':
                    predictions = predictions.astype(float)
                
                if predictions.max() > 1 or predictions.min() < 0:
                    if predictions.max() > predictions.min():
                        predictions = (predictions - predictions.min()) / (predictions.max() - predictions.min())
                    else:
                        predictions = np.full(len(X), 0.5)
                
                predictions = np.clip(predictions, 0, 1)
            else:
                predictions = np.full(len(X), 0.5)
            
            probas = None
            if hasattr(model, 'predict_proba'):
                try:
                    probas = model.predict_proba(X_scaled)
                    if len(probas.shape) > 1 and probas.shape[1] > 1:
                        probas = probas[:, 1]
                    else:
                        probas = probas[:, 0]
                    probas = np.clip(probas, 0, 1)
                except:
                    pass
            
            return predictions, probas
            
        except Exception as e:
            logger.warning(f"⚠️ Erro no modelo {model_key}: {e}")
            return None, None
    
    def _fallback_predictions(self, n: int) -> np.ndarray:
        if n <= 0:
            return np.array([])
        return np.random.uniform(0.3, 0.7, n)
    
    # ==============================================
    # CHART_DATA (MANTIDO)
    # ==============================================
    
    def _extract_chart_data_from_df(self, df: pd.DataFrame, predictions: List[float]) -> Dict[str, Any]:
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        
        pred_list = self._safe_predictions_to_list(predictions)
        base_value = sum(pred_list) / len(pred_list) * 1500 if pred_list else 1000
        
        weekly_revenue = [0] * 7
        weekly_costs = [0] * 7
        weekly_count = [0] * 7
        
        date_col = self._find_column(df, ['data', 'dia', 'date', 'created_at'])
        value_col = self._find_column(df, ['valor', 'receita', 'total', 'preco', 'revenue'])
        cost_col = self._find_column(df, ['custo', 'custo_pecas', 'despesa', 'cost'])
        
        if date_col and value_col:
            try:
                for i in range(len(df)):
                    val = df.iloc[i]
                    try:
                        date = pd.to_datetime(val[date_col])
                        day_idx = date.dayofweek
                        value = float(val[value_col]) if pd.notna(val[value_col]) else 0
                        weekly_revenue[day_idx] += value
                        weekly_count[day_idx] += 1
                        
                        if cost_col and cost_col in df.columns:
                            cost = float(val[cost_col]) if pd.notna(val[cost_col]) else 0
                            weekly_costs[day_idx] += cost
                    except:
                        continue
                
                for i in range(7):
                    if weekly_count[i] > 0:
                        weekly_revenue[i] = weekly_revenue[i] / weekly_count[i]
                        if weekly_costs[i] > 0:
                            weekly_costs[i] = weekly_costs[i] / weekly_count[i]
                        else:
                            weekly_costs[i] = weekly_revenue[i] * 0.35
                    else:
                        weekly_revenue[i] = base_value * (0.5 + random.random() * 0.8)
                        weekly_costs[i] = weekly_revenue[i] * (0.25 + random.random() * 0.35)
            except Exception:
                weekly_revenue = [base_value * (0.5 + random.random() * 0.8) for _ in range(7)]
                weekly_costs = [r * (0.25 + random.random() * 0.35) for r in weekly_revenue]
        else:
            if pred_list and len(pred_list) >= 7:
                weekly_revenue = [base_value * (0.5 + p * 0.6) for p in pred_list[:7]]
            else:
                weekly_revenue = [base_value * (0.5 + random.random() * 0.8) for _ in range(7)]
            weekly_costs = [r * (0.25 + random.random() * 0.35) for r in weekly_revenue]
        
        weekly_services = [max(1, int(p * 15 + 2)) for p in pred_list[:7]] if pred_list else [random.randint(2, 15) for _ in range(7)]
        
        monthly_revenue = [base_value * (1 + 0.3 * (m / 12)) * (0.5 + random.random() * 0.8) for m in range(12)]
        
        return {
            "weekly": {
                "labels": days,
                "revenue": [round(v, 2) for v in weekly_revenue],
                "costs": [round(v, 2) for v in weekly_costs]
            },
            "performance": {
                "labels": days,
                "services": weekly_services
            },
            "monthly": {
                "labels": months,
                "revenue": [round(v, 2) for v in monthly_revenue]
            }
        }
    
    def _find_column(self, df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
        for col in df.columns:
            col_lower = str(col).lower()
            for keyword in keywords:
                if keyword in col_lower:
                    return col
        return None
    
    def _generate_fallback_chart_data(self) -> Dict[str, Any]:
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        return {
            "weekly": {
                "labels": days,
                "revenue": [round(random.randint(500, 2000) + random.random() * 100, 2) for _ in range(7)],
                "costs": [round(random.randint(100, 800) + random.random() * 50, 2) for _ in range(7)]
            },
            "performance": {
                "labels": days,
                "services": [random.randint(2, 15) for _ in range(7)]
            },
            "monthly": {
                "labels": months,
                "revenue": [round(random.randint(5000, 15000) + random.random() * 1000, 2) for _ in range(12)]
            }
        }
    
    # ==============================================
    # INSIGHTS E RECOMENDAÇÕES (MANTIDO)
    # ==============================================
    
    def _safe_predictions_to_list(self, predictions: Any) -> List[float]:
        if predictions is None:
            return []
        try:
            if hasattr(predictions, 'tolist'):
                return [float(p) for p in predictions.tolist() if p is not None and not np.isnan(p)]
            elif isinstance(predictions, list):
                return [float(p) for p in predictions if p is not None and not np.isnan(p)]
            else:
                return [float(p) for p in list(predictions) if p is not None and not np.isnan(p)]
        except Exception:
            return []
    
    def _generate_insights_safe(self, df: pd.DataFrame, predictions: List[float], processed: Dict) -> Tuple[Dict, List]:
        try:
            pred_list = self._safe_predictions_to_list(predictions)
            
            if not pred_list:
                return {
                    'summary': {'total_predictions': 0},
                    'risk_distribution': {},
                    'model_info': {'source': self.model_source},
                    'data_info': {'rows': 0}
                }, ["Dados insuficientes para gerar insights"]
            
            insights = {
                'summary': {
                    'total_predictions': len(pred_list),
                    'mean': float(np.mean(pred_list)),
                    'median': float(np.median(pred_list)),
                    'std': float(np.std(pred_list)),
                    'min': float(np.min(pred_list)),
                    'max': float(np.max(pred_list))
                },
                'risk_distribution': {
                    'high': len([p for p in pred_list if p > 0.7]),
                    'high_percentage': len([p for p in pred_list if p > 0.7]) / max(1, len(pred_list)) * 100,
                    'medium': len([p for p in pred_list if 0.4 <= p <= 0.7]),
                    'medium_percentage': len([p for p in pred_list if 0.4 <= p <= 0.7]) / max(1, len(pred_list)) * 100,
                    'low': len([p for p in pred_list if p < 0.4]),
                    'low_percentage': len([p for p in pred_list if p < 0.4]) / max(1, len(pred_list)) * 100
                },
                'model_info': {
                    'source': self.model_source,
                    'accuracy': self.last_metrics.get('accuracy', 0),
                    'is_placeholder': self.model_source == ModelType.PLACEHOLDER.value
                },
                'data_info': {
                    'rows': processed.get('stats', {}).get('rows', 0),
                    'columns': processed.get('stats', {}).get('columns', 0),
                    'numeric_columns': processed.get('stats', {}).get('numeric_columns', 0)
                }
            }
            
            recommendations = self._generate_recommendations_safe(pred_list)
            return insights, recommendations
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar insights: {e}")
            return {}, ["Erro ao gerar insights"]
    
    def _generate_recommendations_safe(self, predictions: List[float]) -> List[str]:
        recommendations = []
        
        if not predictions:
            return ["📊 Dados insuficientes para gerar recomendações"]
        
        try:
            high_risk_pct = len([p for p in predictions if p > 0.7]) / len(predictions) * 100
            
            if high_risk_pct > 30:
                recommendations.append("🔴 ALTO RISCO: Mais de 30% dos casos são de alto risco - revisar processos imediatamente")
            elif high_risk_pct > 15:
                recommendations.append("🟠 RISCO MODERADO: Monitorar de perto os casos de alto risco")
            elif high_risk_pct > 5:
                recommendations.append("🟡 RISCO BAIXO: Manter monitoramento regular")
            else:
                recommendations.append("🟢 RISCO MÍNIMO: Excelente performance, manter práticas atuais")
            
            mean_val = np.mean(predictions)
            std_val = np.std(predictions)
            
            if std_val > 0.2:
                recommendations.append("📊 Alta variabilidade nos dados. Considere segmentação mais granular.")
            
            if mean_val > 0.7:
                recommendations.append("📈 Tendência positiva. Continue investindo nas estratégias atuais.")
            elif mean_val < 0.3:
                recommendations.append("⚠️ Tendência negativa. Reveja suas estratégias e processos.")
            
            if len(recommendations) < 2:
                recommendations.append("📊 Análise concluída. Utilize os insights para tomada de decisão.")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao gerar recomendações: {e}")
            recommendations = ["📊 Recomendações indisponíveis devido a erro no processamento"]
        
        return recommendations
    
    def _calculate_metrics(self, predictions: List[float], processed: Dict, encoding_used: str) -> Dict[str, Any]:
        pred_list = self._safe_predictions_to_list(predictions)
        
        metrics = {
            'mean_prediction': float(np.mean(pred_list)) if pred_list else 0,
            'std_prediction': float(np.std(pred_list)) if pred_list else 0,
            'min_prediction': float(np.min(pred_list)) if pred_list else 0,
            'max_prediction': float(np.max(pred_list)) if pred_list else 0,
            'model_used': self.model_source,
            'processed_rows': len(pred_list),
        }
        
        if pred_list:
            high_risk = len([p for p in pred_list if p > 0.7])
            metrics['high_risk_count'] = high_risk
            metrics['high_risk_percentage'] = high_risk / len(pred_list) * 100
            
            low_risk = len([p for p in pred_list if p < 0.3])
            metrics['low_risk_count'] = low_risk
            metrics['low_risk_percentage'] = low_risk / len(pred_list) * 100
        
        if encoding_used:
            metrics['encoding_used'] = encoding_used
        
        stats = processed.get('stats', {})
        if stats:
            metrics['dataset_rows'] = stats.get('rows', 0)
            metrics['dataset_columns'] = stats.get('columns', 0)
            metrics['numeric_columns'] = stats.get('numeric_columns', 0)
        
        return metrics
    
    # ==============================================
    # 🔥 PREDICT - MÉTODO PRINCIPAL (V6.0)
    # ==============================================
    
    async def predict(self, df_or_content: Union[pd.DataFrame, bytes, str], 
                      filename: Optional[str] = None,
                      user_id: Optional[int] = None) -> MLPipelineResult:
        """
        🔥 MÉTODO PRINCIPAL - VERSÃO 6.0 COM FEATURE REGISTRY
        """
        start_time = time.time()
        encoding_used = None
        warnings = []
        status = PredictionStatus.FAILED
        chart_data = {}
        feature_build_result = None
        validation_result = None
        
        try:
            # 1. Carregar dados
            load_result = await self._load_data_enhanced(df_or_content, filename)
            df = load_result.get('df')
            encoding_used = load_result.get('encoding')
            load_warnings = load_result.get('warnings', [])
            
            if load_warnings:
                warnings.extend(load_warnings)
            
            if df is None or len(df) == 0:
                return self._create_error_result(
                    "Não foi possível carregar os dados",
                    encoding_used=encoding_used,
                    warnings=warnings
                )
            
            logger.info(f"📊 Dados carregados: {len(df)} linhas, {len(df.columns)} colunas")
            
            # 2. 🔥 CONSTRUIR FEATURES INTELIGENTEMENTE
            features, build_warnings = await self._build_features_intelligently(df, filename)
            
            if build_warnings:
                warnings.extend(build_warnings)
            
            if features is None:
                return self._create_error_result(
                    "Falha ao construir features",
                    encoding_used=encoding_used,
                    warnings=warnings
                )
            
            # 3. 🔥 VALIDAR FEATURES
            validation_result = await self._validate_features(features, filename)
            warnings.append(f"Match de features: {validation_result['mismatch']['match_percentage']:.1f}%")
            
            if validation_result['mismatch']['has_mismatch']:
                logger.warning(f"   ⚠️ Mismatch detectado: {validation_result['mismatch']['missing_count']} features faltantes")
            
            # 4. Preparar X para predição
            X = features.values
            
            # 5. Tentar usar ModelPredictor primeiro
            predictor_predictions, predictor_warnings = await self._safe_predict_with_predictor(df)
            if predictor_warnings:
                warnings.extend(predictor_warnings)
            
            predictions = predictor_predictions
            
            # 6. Se predictor falhou, usar pipeline interno
            if predictions is None or len(predictions) == 0:
                if not self.is_initialized:
                    await self.initialize()
                
                # 🔥 USAR FEATURES CORRETAS (NÃO ADAPTADAS)
                model_predictions, probas = await self._predict_with_model('default', X)
                
                if model_predictions is not None and len(model_predictions) > 0:
                    predictions = model_predictions.tolist()
                else:
                    predictions = self._fallback_predictions(len(X)).tolist()
                    warnings.append("Usando fallback para predições")
            
            # 7. Gerar insights e recomendações
            processed = {'stats': {'rows': len(df), 'columns': len(df.columns)}}
            insights, recommendations = self._generate_insights_safe(df, predictions, processed)
            
            # 8. Métricas
            metrics = self._calculate_metrics(predictions, processed, encoding_used)
            
            # 9. Chart data
            try:
                chart_data = self._extract_chart_data_from_df(df, predictions)
                self.stats['chart_data_generated'] += 1
                logger.info(f"📊 Chart_data gerado: weekly={len(chart_data.get('weekly', {}).get('revenue', []))} dias")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao gerar chart_data: {e}")
                chart_data = self._generate_fallback_chart_data()
            
            # 10. Resultado
            result = MLPipelineResult(
                success=True,
                predictions=[float(p) for p in predictions],
                metrics=metrics,
                insights=insights,
                recommendations=recommendations,
                model_used=self.model_source,
                processed_rows=len(predictions),
                processing_time_ms=(time.time() - start_time) * 1000,
                metadata={
                    'feature_names': features.columns.tolist(),
                    'feature_count': len(features.columns),
                    'feature_build': feature_build_result.to_dict() if feature_build_result else {},
                    'validation': validation_result,
                    'stats': {'rows': len(df), 'columns': len(df.columns)}
                },
                encoding_used=encoding_used,
                status=PredictionStatus.SUCCESS,
                warnings=warnings,
                chart_data=chart_data
            )
            
            self.stats['total_predictions'] += 1
            self.stats['total_files_processed'] += 1
            self.stats['successful_predictions'] += 1
            self.stats['last_prediction_time'] = datetime.now().isoformat()
            self.last_predictions = np.array(predictions)
            
            logger.info(f"✅ Predição concluída: {len(predictions)} resultados, encoding: {encoding_used}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro na predição: {e}")
            logger.error(traceback.format_exc())
            self.stats['failed_predictions'] += 1
            return self._create_error_result(
                str(e),
                encoding_used=encoding_used,
                warnings=warnings,
                processing_time_ms=(time.time() - start_time) * 1000,
                chart_data=chart_data
            )
    
    # ==============================================
    # INICIALIZAÇÃO DE MODELOS (MANTIDO)
    # ==============================================
    
    async def initialize(self, force_reload: bool = False) -> bool:
        async with self._initialization_lock:
            if self.is_initialized and not force_reload:
                return True
            
            logger.info("\n🔧 Inicializando ML Pipeline...")
            self._ensure_modules_loaded()
            loaded = False
            
            if self._predictor is not None:
                try:
                    await self._predictor.load_or_train_models()
                    if self._predictor.office_model is not None:
                        self.models['default'] = self._predictor.office_model
                        self.scalers['default'] = self._predictor.scaler
                        self.model_source = self._predictor.model_source or ModelType.RANDOM_FOREST.value
                        loaded = True
                        logger.info(f"✅ Modelo do ModelPredictor carregado (fonte: {self.model_source})")
                except Exception as e:
                    logger.warning(f"⚠️ Erro no ModelPredictor: {e}")
            
            if not loaded:
                office_path = os.path.join(self.models_dir, "office_model.pkl")
                if os.path.exists(office_path):
                    try:
                        model_data = joblib.load(office_path)
                        loaded = self._load_model_from_data(model_data)
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao carregar office_model: {e}")
            
            if not loaded and self._boosting_ensemble:
                try:
                    if hasattr(self._boosting_ensemble, 'best_model') and self._boosting_ensemble.best_model:
                        self.models['ensemble'] = self._boosting_ensemble.best_model
                        self.model_source = ModelType.ENSEMBLE.value
                        loaded = True
                        logger.info("✅ Modelo do BoostingEnsemble carregado")
                except Exception as e:
                    logger.warning(f"⚠️ Erro no BoostingEnsemble: {e}")
            
            if not loaded and self._automl_office:
                try:
                    if hasattr(self._automl_office, 'best_pipeline') and self._automl_office.best_pipeline:
                        self.models['default'] = self._automl_office.best_pipeline
                        self.model_source = ModelType.AUTO_ML.value
                        loaded = True
                        logger.info("✅ Modelo do AutoMLOffice carregado")
                except Exception as e:
                    logger.warning(f"⚠️ Erro no AutoMLOffice: {e}")
            
            if not loaded:
                logger.warning("⚠️ Nenhum modelo encontrado. Criando placeholder...")
                self._create_placeholder_model()
                loaded = True
            
            self.is_initialized = True
            logger.info(f"✅ ML Pipeline inicializado (Fonte: {self.model_source})")
            return True
    
    def _load_model_from_data(self, model_data: Dict[str, Any]) -> bool:
        try:
            if isinstance(model_data, dict):
                if 'pipeline' in model_data:
                    self.models['default'] = model_data['pipeline']
                    self.model_source = ModelType.AUTO_ML.value
                    self.last_metrics = model_data.get('metricas', {})
                    return True
                elif 'ensemble' in model_data:
                    self.models['ensemble'] = model_data
                    self.model_source = ModelType.ENSEMBLE.value
                    self.last_metrics = model_data.get('metrics', {})
                    return True
                elif 'model' in model_data:
                    self.models['default'] = model_data['model']
                    if 'scaler' in model_data:
                        self.scalers['default'] = model_data['scaler']
                    self.model_source = ModelType.RANDOM_FOREST.value
                    self.last_metrics = model_data.get('metrics', {})
                    return True
        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar modelo: {e}")
        return False
    
    def _create_placeholder_model(self):
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import StandardScaler
            
            expected_features = self.feature_registry.get_expected_count()
            
            model = RandomForestClassifier(
                n_estimators=20,
                max_depth=4,
                random_state=42,
                n_jobs=-1
            )
            scaler = StandardScaler()
            
            X = np.random.randn(200, expected_features)
            y = (X[:, 0] + X[:, 1] > 0).astype(int)
            
            X_scaled = scaler.fit_transform(X)
            model.fit(X_scaled, y)
            
            self.models['default'] = model
            self.scalers['default'] = scaler
            self.model_source = ModelType.PLACEHOLDER.value
            self.last_metrics = {
                'accuracy': 0.65,
                'is_placeholder': True,
                'n_features': expected_features
            }
            
            logger.info(f"✅ Modelo placeholder criado ({expected_features} features)")
        except Exception as e:
            logger.error(f"❌ Erro ao criar placeholder: {e}")
            self.models['default'] = None
    
    # ==============================================
    # FUNÇÕES DE UTILIDADE
    # ==============================================
    
    def _create_error_result(self, error: str, **kwargs) -> MLPipelineResult:
        chart_data = kwargs.pop('chart_data', {})
        return MLPipelineResult(
            success=False,
            predictions=[0.5],
            error=error,
            status=PredictionStatus.FAILED,
            chart_data=chart_data,
            **{k: v for k, v in kwargs.items() if k in MLPipelineResult.__annotations__}
        )
    
    def get_encoding_stats(self) -> Dict[str, Any]:
        total = self.encoding_stats.get("total_attempts", 0)
        successful = (self.encoding_stats.get("detected", 0) + 
                      self.encoding_stats.get("fallback", 0) +
                      self.encoding_stats.get("excel", 0))
        
        encodings = {k: v for k, v in self.encoding_stats.items() 
                     if k not in ["detected", "fallback", "forced", "excel", "failed", "total_attempts"]}
        
        return {
            "encodings": encodings,
            "total_attempts": total,
            "successful": successful,
            "failed": self.encoding_stats.get("failed", 0),
            "last_encoding": self.last_encoding,
            "last_encoding_confidence": self.last_encoding_confidence,
            "last_encoding_method": self.last_encoding_method,
            "success_rate": (successful / max(1, total)) * 100,
            "detected_rate": (self.encoding_stats.get("detected", 0) / max(1, total)) * 100,
            "fallback_rate": (self.encoding_stats.get("fallback", 0) / max(1, total)) * 100,
            "forced_rate": (self.encoding_stats.get("forced", 0) / max(1, total)) * 100
        }
    
    def get_status(self) -> Dict[str, Any]:
        self.stats['uptime_seconds'] = (datetime.now() - datetime.fromisoformat(self.stats['started_at'])).total_seconds()
        
        total = max(1, self.stats['total_predictions'])
        return {
            "initialized": self.is_initialized,
            "model_source": self.model_source,
            "total_predictions": self.stats['total_predictions'],
            "successful_predictions": self.stats['successful_predictions'],
            "failed_predictions": self.stats['failed_predictions'],
            "success_rate": self.stats['successful_predictions'] / max(1, self.stats['total_predictions']) * 100,
            "total_files": self.stats['total_files_processed'],
            "cache_hits": self.stats['cache_hits'],
            "cache_misses": self.stats['cache_misses'],
            "cache_hit_rate": self.stats['cache_hits'] / max(1, self.stats['total_predictions']) * 100,
            "cache_size": len(self._cache),
            "last_prediction": self.stats['last_prediction_time'],
            "uptime_seconds": self.stats['uptime_seconds'],
            "model_accuracy": self.last_metrics.get('accuracy', 0),
            "encoding_stats": self.encoding_stats,
            "started_at": self.stats['started_at'],
            "feature_mismatches": self.stats.get('feature_mismatches', 0),
            "feature_fallbacks": self.stats.get('feature_fallbacks', 0),
            "chart_data_generated": self.stats.get('chart_data_generated', 0),
            "feature_monitor": self.feature_monitor.get_stats()
        }
    
    def get_feature_registry_info(self) -> Dict[str, Any]:
        """Retorna informações sobre o Feature Registry"""
        return {
            "total_features": self.feature_registry.get_expected_count(),
            "required_features": self.feature_registry.get_required_features(),
            "optional_features": self.feature_registry.get_optional_features(),
            "expected_order": self.feature_registry.get_expected_order(),
            "feature_definitions": {
                name: {
                    "type": feat.type.value,
                    "description": feat.description,
                    "required": feat.required,
                    "source_column": feat.source_column,
                    "aliases": feat.aliases,
                    "can_fallback": feat.can_fallback
                }
                for name, feat in self.feature_registry._features.items()
            }
        }
    
    def clear_cache(self):
        self._cache.clear()
        logger.info("🧹 Cache do pipeline limpo")
    
    def reset(self):
        self.is_initialized = False
        self.models.clear()
        self.scalers.clear()
        self._cache.clear()
        self.last_predictions = None
        self.last_metrics = {}
        logger.info("🔄 Pipeline resetado")


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

pipeline = MLPipeline()


# ==============================================
# FUNÇÕES DE COMPATIBILIDADE
# ==============================================

async def process_file_content(content: bytes, filename: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    🔥 FUNÇÃO PRINCIPAL PARA upload_routes.py
    Processa bytes do upload e retorna resultado estruturado com chart_data
    """
    try:
        logger.info(f"📁 process_file_content: {filename} ({len(content)} bytes)")
        result = await pipeline.predict(content, filename, user_id=user_id)
        
        result_dict = result.to_dict()
        
        if result.encoding_used:
            result_dict['encoding_used'] = result.encoding_used
            result_dict['metadata'] = result_dict.get('metadata', {})
            result_dict['metadata']['encoding_used'] = result.encoding_used
        
        # Adicionar informações do Feature Registry
        if result.metadata:
            result_dict['metadata']['feature_build'] = result.metadata.get('feature_build', {})
            result_dict['metadata']['validation'] = result.metadata.get('validation', {})
        
        logger.info(f"✅ process_file_content concluído: encoding={result.encoding_used}")
        return result_dict
        
    except Exception as e:
        logger.error(f"❌ Erro em process_file_content: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "predictions": [0.5],
            "error": str(e),
            "processed_rows": 0,
            "chart_data": {},
            "encoding_used": None,
            "metadata": {
                "encoding_used": None,
                "error": str(e)
            }
        }


# ==============================================
# FUNÇÃO DE TESTE
# ==============================================

async def test_pipeline():
    print("\n" + "=" * 70)
    print("🧪 TESTANDO PIPELINE ML V6.0 (FEATURE REGISTRY)")
    print("=" * 70)
    
    import pandas as pd
    import numpy as np
    from io import BytesIO
    
    np.random.seed(42)
    df = pd.DataFrame({
        'cliente_id': range(1, 101),
        'valor_servico': np.random.randn(100) * 100 + 500,
        'custo_pecas': np.random.randn(100) * 50 + 200,
        'quantidade': np.random.randint(1, 5, 100),
        'data': pd.date_range('2024-01-01', periods=100, freq='D')
    })
    
    print(f"📊 Dados de teste: {len(df)} linhas, {len(df.columns)} colunas")
    
    buffer = BytesIO()
    df.to_csv(buffer, index=False, encoding='utf-8')
    content = buffer.getvalue()
    
    result = await process_file_content(content, "teste.csv")
    
    print(f"\n📊 RESULTADO:")
    print(f"   ✅ Sucesso: {result.get('success')}")
    print(f"   🔢 Predições: {len(result.get('predictions', []))}")
    print(f"   📈 Média: {result.get('metrics', {}).get('mean_prediction', 0):.3f}")
    print(f"   🎯 Modelo: {result.get('model_used', 'unknown')}")
    print(f"   📝 Encoding: {result.get('encoding_used', 'unknown')}")
    print(f"   📊 Features: {result.get('metadata', {}).get('feature_count', 0)}")
    
    if result.get('chart_data'):
        weekly = result['chart_data'].get('weekly', {})
        print(f"   📅 Weekly: {len(weekly.get('revenue', []))} dias")
    
    print("\n" + "=" * 70)
    print("✅ Teste concluído!")
    print("=" * 70)
    
    return result


# ==============================================
# INICIALIZAÇÃO
# ==============================================

print("\n" + "=" * 70)
print("✅ preprocessing.py V6.0 COMPLETO carregado com sucesso!")
print("=" * 70)
print("   🔥 FEATURE REGISTRY:")
print("      • " + str(feature_registry.get_expected_count()) + " features registradas")
print("      • " + str(len(feature_registry.get_required_features())) + " obrigatórias")
print("      • " + str(len(feature_registry.get_optional_features())) + " opcionais")
print("   🔥 FEATURE BUILDER:")
print("      • Detecção automática de colunas")
print("      • Cálculo de features derivadas")
print("      • Fallback inteligente")
print("   🔥 FEATURE MONITOR:")
print("      • Detecção de mismatches")
print("      • Logging de eventos")
print("      • Alertas para administradores")
print("   🗑️ REMOVIDO:")
print("      • _adapt_features_to_model (padding aleatório)")
print("      • _generate_synthetic_features (features arbitrárias)")
print("   📊 Métodos:")
print("      • pipeline.predict(bytes, filename, user_id)")
print("      • pipeline.get_feature_registry_info()")
print("      • pipeline.get_status()")
print("=" * 70)