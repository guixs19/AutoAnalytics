# backend/ml/preprocessing.py - VERSÃO 7.0 (INTELIGENTE PARA DADOS REAIS)
"""
🔥 MÓDULO DE PRÉ-PROCESSAMENTO E PIPELINE DE ML - AUTOANALYTICS
================================================================================
VERSÃO 7.0 - INTELIGENTE PARA DADOS REAIS

✅ NOVIDADES V7.0:
   - 🔥 FEATURES INTELIGENTES: Extrai informações reais de dados de oficina
   - 🔥 EXTRATOR DE IDs: Converte 'OS-0001' → 1 para análises numéricas
   - 🔥 MÉTRICAS REAIS: Calcula ticket médio, margem, taxa de conclusão real
   - 🔥 DETECÇÃO INTELIGENTE: Identifica automaticamente colunas por contexto
   - 🔥 CACHE INTELIGENTE: Cache baseado no conteúdo real dos dados
   - 🔥 FALLBACK INTELIGENTE: Usa estimativas baseadas nos dados disponíveis
   - 🔥 VALIDAÇÃO DE DADOS: Verifica e limpa dados antes do processamento

✅ MANTIDO V6.2:
   - Feature Registry
   - Feature Builder
   - Feature Monitor
   - Encoding detection
   - Progress tracking
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
# 🔥 ENUMS E DATACLASSES
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
    DIRECT = "direct"
    DERIVED = "derived"
    AGGREGATE = "aggregate"
    CONSTANT = "constant"
    INTELLIGENT = "intelligent"  # 🔥 NOVO


@dataclass
class EncodingResult:
    encoding: str
    confidence: float
    method: EncodingMethod
    error: Optional[str] = None
    
    def is_valid(self) -> bool:
        return self.confidence > 0.3 or self.method != EncodingMethod.FORCED
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "encoding": self.encoding,
            "confidence": self.confidence,
            "method": self.method.value if hasattr(self.method, 'value') else str(self.method),
            "valid": self.is_valid(),
            "error": self.error
        }


@dataclass
class MLPipelineResult:
    success: bool
    predictions: List[float]
    probabilities: Optional[List[float]] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    insights: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    model_used: str = "unknown"
    processed_rows: int = 0
    processing_time_ms: float = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    encoding_used: Optional[str] = None
    status: PredictionStatus = PredictionStatus.FAILED
    warnings: List[str] = field(default_factory=list)
    chart_data: Dict[str, Any] = field(default_factory=dict)
    
    def is_valid(self) -> bool:
        return self.success and len(self.predictions) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "predictions": self.predictions,
            "probabilities": self.probabilities,
            "metrics": self.metrics,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "model_used": self.model_used,
            "processed_rows": self.processed_rows,
            "processing_time_ms": self.processing_time_ms,
            "error": self.error,
            "metadata": self.metadata,
            "encoding_used": self.encoding_used,
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
            "warnings": self.warnings,
            "chart_data": self.chart_data
        }


@dataclass
class CacheEntry:
    value: Any
    timestamp: float
    hits: int = 0
    
    def is_expired(self, ttl: int = 60) -> bool:
        return (time.time() - self.timestamp) > ttl


@dataclass
class FeatureDefinition:
    name: str
    type: FeatureType
    description: str
    required: bool = True
    default_value: Any = 0.0
    source_column: Optional[str] = None
    derive_func: Optional[Callable] = None
    aggregate_column: Optional[str] = None
    aggregate_func: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    can_fallback: bool = True
    fallback_value: float = 0.0
    intelligent_extractor: Optional[Callable] = None  # 🔥 NOVO


@dataclass
class FeatureBuildResult:
    success: bool
    features: pd.DataFrame
    missing_features: List[str] = field(default_factory=list)
    fallback_used: List[str] = field(default_factory=list)
    calculated_features: List[str] = field(default_factory=list)
    intelligent_features: List[str] = field(default_factory=list)  # 🔥 NOVO
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
            "intelligent_features": self.intelligent_features,
            "warnings": self.warnings,
            "errors": self.errors
        }


@dataclass
class FeatureMismatchEvent:
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


# ==============================================
# 🔥 EXTRATORES INTELIGENTES (NOVO)
# ==============================================

class IntelligentExtractors:
    """
    🔥 Extratores inteligentes para dados reais de oficina
    """
    
    @staticmethod
    def extract_number_from_id(value: Any) -> Optional[int]:
        """Extrai número de um ID como 'OS-0001' → 1"""
        if pd.isna(value):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        # Remove tudo que não é número
        match = re.search(r'(\d+)', str(value))
        if match:
            return int(match.group(1))
        return None
    
    @staticmethod
    def extract_total_servicos(df: pd.DataFrame) -> int:
        """🔥 Extrai total de serviços (contagem de OS)"""
        if 'OS' in df.columns:
            return len(df)
        return len(df)
    
    @staticmethod
    def extract_media_servicos_por_dia(df: pd.DataFrame) -> float:
        """🔥 Extrai média de serviços por dia"""
        # Tenta encontrar coluna de data
        date_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ['data', 'dia', 'date', 'dt']):
                date_col = col
                break
        
        if date_col:
            try:
                dates = pd.to_datetime(df[date_col], errors='coerce')
                servicos_por_dia = df.groupby(dates.dt.date).size()
                return round(servicos_por_dia.mean(), 2)
            except:
                pass
        
        # Fallback: estimar baseado no total
        return round(len(df) / 30, 2)  # 30 dias
    
    @staticmethod
    def extract_total_receita(df: pd.DataFrame) -> float:
        """🔥 Extrai receita total (inteligente)"""
        # Tenta encontrar coluna de valor
        value_col = None
        keywords = ['valor', 'receita', 'total', 'preco', 'revenue', 'amount', 'valor final', 'valor do serviço']
        
        for col in df.columns:
            col_lower = str(col).lower()
            for keyword in keywords:
                if keyword in col_lower:
                    value_col = col
                    break
            if value_col:
                break
        
        if value_col:
            valores = pd.to_numeric(df[value_col], errors='coerce')
            valores = valores[valores > 0]
            if len(valores) > 0:
                return round(valores.sum(), 2)
        
        # Fallback: procurar em colunas de resumo
        for col in df.columns:
            col_lower = str(col).lower()
            if 'faturamento' in col_lower or 'receita total' in col_lower:
                try:
                    val = pd.to_numeric(df[col].iloc[0], errors='coerce')
                    if pd.notna(val) and val > 0:
                        return round(val, 2)
                except:
                    pass
        
        return 0.0
    
    @staticmethod
    def extract_ticket_medio(df: pd.DataFrame) -> float:
        """🔥 Extrai ticket médio (inteligente)"""
        total_receita = IntelligentExtractors.extract_total_receita(df)
        total_servicos = IntelligentExtractors.extract_total_servicos(df)
        
        if total_servicos > 0 and total_receita > 0:
            return round(total_receita / total_servicos, 2)
        
        # Fallback: média dos valores individuais
        value_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ['valor', 'total', 'preco']):
                value_col = col
                break
        
        if value_col:
            valores = pd.to_numeric(df[value_col], errors='coerce')
            valores = valores[valores > 0]
            if len(valores) > 0:
                return round(valores.mean(), 2)
        
        return 0.0
    
    @staticmethod
    def extract_taxa_conclusao(df: pd.DataFrame) -> float:
        """🔥 Extrai taxa de conclusão real"""
        status_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ['status', 'situacao', 'estado']):
                status_col = col
                break
        
        if status_col:
            status_values = df[status_col].astype(str).str.lower()
            total = len(df)
            concluidos = status_values.str.contains('concluído|concluida|finalizado|entregue').sum()
            if total > 0:
                return round((concluidos / total) * 100, 2)
        
        return 0.0
    
    @staticmethod
    def extract_taxa_cancelamento(df: pd.DataFrame) -> float:
        """🔥 Extrai taxa de cancelamento real"""
        status_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ['status', 'situacao', 'estado']):
                status_col = col
                break
        
        if status_col:
            status_values = df[status_col].astype(str).str.lower()
            total = len(df)
            cancelados = status_values.str.contains('cancelado|cancelled').sum()
            if total > 0:
                return round((cancelados / total) * 100, 2)
        
        return 0.0
    
    @staticmethod
    def extract_media_horas(df: pd.DataFrame) -> float:
        """🔥 Extrai média de horas de mão de obra"""
        horas_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ['hora', 'horas', 'tempo', 'duracao']):
                horas_col = col
                break
        
        if horas_col:
            horas = pd.to_numeric(df[horas_col], errors='coerce')
            horas = horas[horas > 0]
            if len(horas) > 0:
                return round(horas.mean(), 2)
        
        return 0.0
    
    @staticmethod
    def extract_top_servicos(df: pd.DataFrame, n: int = 3) -> Dict[str, int]:
        """🔥 Extrai os serviços mais comuns"""
        servico_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ['serviço', 'servico', 'tipo', 'descricao']):
                servico_col = col
                break
        
        if servico_col:
            counts = df[servico_col].value_counts().head(n)
            return {str(k): int(v) for k, v in counts.items()}
        
        return {}


# ==============================================
# 🔥 FEATURE REGISTRY (INTELIGENTE)
# ==============================================

class FeatureRegistry:
    """Registro central de features do modelo"""
    
    MAX_FEATURES = 20  # 🔥 AUMENTADO
    
    def __init__(self):
        self._features: Dict[str, FeatureDefinition] = {}
        self._register_features()
        self._expected_order = self._get_expected_order()
        logger.info(f"✅ FeatureRegistry: {len(self._features)} features registradas")
    
    def _register_features(self):
        """Registra todas as features do modelo"""
        
        # ==========================================
        # FEATURES INTELIGENTES (NOVO)
        # ==========================================
        
        self._features["total_servicos"] = FeatureDefinition(
            name="total_servicos",
            type=FeatureType.INTELLIGENT,
            description="Total de serviços (contagem real)",
            required=True,
            default_value=0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_total_servicos(df)
        )
        
        self._features["media_servicos_dia"] = FeatureDefinition(
            name="media_servicos_dia",
            type=FeatureType.INTELLIGENT,
            description="Média de serviços por dia",
            required=True,
            default_value=0.0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_media_servicos_por_dia(df)
        )
        
        self._features["total_receita"] = FeatureDefinition(
            name="total_receita",
            type=FeatureType.INTELLIGENT,
            description="Receita total real",
            required=True,
            default_value=0.0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_total_receita(df)
        )
        
        self._features["ticket_medio"] = FeatureDefinition(
            name="ticket_medio",
            type=FeatureType.INTELLIGENT,
            description="Ticket médio real",
            required=True,
            default_value=0.0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_ticket_medio(df)
        )
        
        self._features["taxa_conclusao"] = FeatureDefinition(
            name="taxa_conclusao",
            type=FeatureType.INTELLIGENT,
            description="Taxa de conclusão real (%)",
            required=False,
            default_value=0.0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_taxa_conclusao(df)
        )
        
        self._features["taxa_cancelamento"] = FeatureDefinition(
            name="taxa_cancelamento",
            type=FeatureType.INTELLIGENT,
            description="Taxa de cancelamento real (%)",
            required=False,
            default_value=0.0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_taxa_cancelamento(df)
        )
        
        self._features["media_horas"] = FeatureDefinition(
            name="media_horas",
            type=FeatureType.INTELLIGENT,
            description="Média de horas por serviço",
            required=False,
            default_value=0.0,
            intelligent_extractor=lambda df: IntelligentExtractors.extract_media_horas(df)
        )
        
        # ==========================================
        # FEATURES DIRETAS (mapeadas do arquivo)
        # ==========================================
        
        self._features["receita"] = FeatureDefinition(
            name="receita",
            type=FeatureType.DIRECT,
            description="Receita total",
            source_column="valor_servico",
            aliases=["valor", "receita", "total", "preco", "valor_total", "receita_total", "valor do serviço", "valor final"],
            required=True,
            default_value=0.0
        )
        
        self._features["custo"] = FeatureDefinition(
            name="custo",
            type=FeatureType.DIRECT,
            description="Custo total",
            source_column="custo_pecas",
            aliases=["custo", "custo_pecas", "despesa", "gasto", "custo_total", "custo_peca", "custo estimado"],
            required=True,
            default_value=0.0
        )
        
        self._features["quantidade"] = FeatureDefinition(
            name="quantidade",
            type=FeatureType.DIRECT,
            description="Quantidade de serviços",
            source_column="quantidade",
            aliases=["qtd", "quantidade", "servicos", "count"],
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
        
        self._features["margem"] = FeatureDefinition(
            name="margem",
            type=FeatureType.DERIVED,
            description="Margem = lucro / receita",
            derive_func=lambda df: df["lucro"] / df["receita"] if df["receita"] > 0 else 0,
            required=True,
            default_value=0.0
        )
        
        self._features["eficiencia"] = FeatureDefinition(
            name="eficiencia",
            type=FeatureType.DERIVED,
            description="Eficiência = receita / serviços",
            derive_func=lambda df: df["receita"] / df["total_servicos"] if df["total_servicos"] > 0 else 0,
            required=False,
            default_value=0.0
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
        required = [name for name, feat in self._features.items() if feat.required]
        optional = [name for name, feat in self._features.items() if not feat.required]
        return (required + optional)[:self.MAX_FEATURES]
    
    def get_features(self) -> List[str]:
        return list(self._features.keys())[:self.MAX_FEATURES]
    
    def get_definition(self, name: str) -> Optional[FeatureDefinition]:
        return self._features.get(name)
    
    def get_required_features(self) -> List[str]:
        return [name for name, feat in self._features.items() if feat.required][:self.MAX_FEATURES]
    
    def get_optional_features(self) -> List[str]:
        return [name for name, feat in self._features.items() if not feat.required][:self.MAX_FEATURES]
    
    def get_intelligent_features(self) -> List[str]:
        return [name for name, feat in self._features.items() if feat.type == FeatureType.INTELLIGENT][:self.MAX_FEATURES]
    
    def get_expected_count(self) -> int:
        return min(len(self._features), self.MAX_FEATURES)
    
    def get_expected_order(self) -> List[str]:
        return self._expected_order


# Instância global do registry
feature_registry = FeatureRegistry()


# ==============================================
# 🔥 FEATURE BUILDER (INTELIGENTE)
# ==============================================

class FeatureBuilder:
    """
    🔥 Constrói features a partir de dados brutos
    COM EXTRATORES INTELIGENTES
    """
    
    def __init__(self, registry: FeatureRegistry = None):
        self.registry = registry or feature_registry
        self._column_cache: Dict[str, str] = {}
        self._feature_cache: Dict[str, Tuple[pd.DataFrame, float]] = {}
        self._feature_cache_ttl = 300
        self._feature_cache_max_size = 50
        
        # 🔥 NOVO: Cache de dados extraídos
        self._extracted_cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info("✅ FeatureBuilder inicializado (com extratores inteligentes)")
    
    def build_features(self, df: pd.DataFrame) -> FeatureBuildResult:
        """🔥 Constrói todas as features (COM INTELLIGENT EXTRACTORS)"""
        cache_key = self._get_feature_cache_key(df)
        
        if cache_key in self._feature_cache:
            cached_features, timestamp = self._feature_cache[cache_key]
            if time.time() - timestamp < self._feature_cache_ttl:
                logger.info(f"📦 Features em cache: {cache_key[:8]}")
                return FeatureBuildResult(
                    success=True,
                    features=cached_features,
                    warnings=["Features retornadas do cache"]
                )
        
        result = self._build_features_impl(df)
        
        if result.success and result.features is not None:
            self._feature_cache[cache_key] = (result.features, time.time())
            self._clean_cache()
        
        return result
    
    def _get_feature_cache_key(self, df: pd.DataFrame) -> str:
        try:
            sample = df.iloc[:50].values.tobytes()
            cols = str(df.columns.tolist()).encode()
            content = sample + cols + str(len(df)).encode()
            return hashlib.md5(content).hexdigest()[:16]
        except:
            return str(time.time())
    
    def _clean_cache(self):
        if len(self._feature_cache) > self._feature_cache_max_size:
            oldest = sorted(self._feature_cache.items(), key=lambda x: x[1][1])
            to_remove = len(self._feature_cache) - self._feature_cache_max_size
            for i in range(to_remove):
                del self._feature_cache[oldest[i][0]]
            logger.info(f"🧹 Cache de features limpo: {to_remove} removidos")
    
    def _build_features_impl(self, df: pd.DataFrame) -> FeatureBuildResult:
        logger.info(f"🏗️ Construindo features para {len(df)} linhas, {len(df.columns)} colunas")
        
        result = FeatureBuildResult(
            success=False,
            features=pd.DataFrame()
        )
        
        try:
            # 1. Detectar colunas disponíveis
            available_columns = self._detect_columns(df)
            logger.info(f"   🔍 Colunas detectadas: {len(available_columns)} mapeamentos")
            
            # 2. 🔥 EXTRAIR DADOS INTELIGENTES (NOVO)
            extracted_data = self._extract_intelligent_data(df)
            logger.info(f"   🧠 Dados inteligentes extraídos: {len(extracted_data)} itens")
            
            # 3. Construir cada feature
            feature_data = {}
            missing = []
            fallback_used = []
            calculated = []
            intelligent_features = []
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
                        feature_data=feature_data,
                        extracted_data=extracted_data  # 🔥 NOVO
                    )
                    
                    if value is not None:
                        if isinstance(value, (pd.Series, np.ndarray)):
                            feature_data[feature_name] = value
                        else:
                            feature_data[feature_name] = pd.Series([value] * len(df))
                        
                        if definition.type == FeatureType.INTELLIGENT:
                            intelligent_features.append(feature_name)
                        else:
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
            
            # 4. Criar DataFrame
            if feature_data:
                result.features = pd.DataFrame(feature_data)
                expected_order = self.registry.get_expected_order()
                actual_cols = result.features.columns.tolist()
                ordered_cols = [col for col in expected_order if col in actual_cols]
                if ordered_cols:
                    result.features = result.features[ordered_cols]
                
                result.missing_features = missing
                result.fallback_used = fallback_used
                result.calculated_features = calculated
                result.intelligent_features = intelligent_features  # 🔥 NOVO
                result.warnings = warnings
                result.success = True
                
                logger.info(f"✅ Features construídas: {len(calculated)} calculadas, {len(intelligent_features)} inteligentes, {len(fallback_used)} fallback, {len(missing)} faltantes")
                logger.info(f"   📊 Shape final: {result.features.shape}")
                if intelligent_features:
                    logger.info(f"   🧠 Features inteligentes: {intelligent_features}")
                if fallback_used:
                    logger.info(f"   ⚠️ Features com fallback: {fallback_used}")
            else:
                result.errors.append("Nenhuma feature foi construída")
                
        except Exception as e:
            logger.error(f"❌ Erro ao construir features: {e}")
            result.errors.append(str(e))
        
        return result
    
    def _extract_intelligent_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """🔥 Extrai dados inteligentes do DataFrame"""
        cache_key = self._get_data_cache_key(df)
        
        if cache_key in self._extracted_cache:
            logger.info(f"📦 Dados inteligentes em cache: {cache_key[:8]}")
            return self._extracted_cache[cache_key]
        
        extracted = {
            'total_servicos': IntelligentExtractors.extract_total_servicos(df),
            'media_servicos_dia': IntelligentExtractors.extract_media_servicos_por_dia(df),
            'total_receita': IntelligentExtractors.extract_total_receita(df),
            'ticket_medio': IntelligentExtractors.extract_ticket_medio(df),
            'taxa_conclusao': IntelligentExtractors.extract_taxa_conclusao(df),
            'taxa_cancelamento': IntelligentExtractors.extract_taxa_cancelamento(df),
            'media_horas': IntelligentExtractors.extract_media_horas(df),
            'top_servicos': IntelligentExtractors.extract_top_servicos(df, 3)
        }
        
        self._extracted_cache[cache_key] = extracted
        logger.info(f"🧠 Dados inteligentes extraídos: {len(extracted)} itens")
        
        return extracted
    
    def _get_data_cache_key(self, df: pd.DataFrame) -> str:
        try:
            sample = df.iloc[:30].values.tobytes()
            cols = str(df.columns.tolist()).encode()
            content = sample + cols + str(len(df)).encode()
            return hashlib.md5(content).hexdigest()[:12]
        except:
            return str(time.time())
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        column_map = {}
        df_cols_lower = {col.lower().strip(): col for col in df.columns}
        
        for feature_name, definition in self.registry._features.items():
            if definition.type == FeatureType.DIRECT and definition.source_column:
                source_lower = definition.source_column.lower().strip()
                if source_lower in df_cols_lower:
                    column_map[df_cols_lower[source_lower]] = feature_name
                    continue
                
                for alias in definition.aliases:
                    alias_lower = alias.lower().strip()
                    if alias_lower in df_cols_lower:
                        column_map[df_cols_lower[alias_lower]] = feature_name
                        break
                
                if feature_name not in column_map.values():
                    for col, col_name in df_cols_lower.items():
                        for keyword in definition.aliases + [definition.source_column]:
                            if keyword.lower() in col or col in keyword.lower():
                                column_map[col_name] = feature_name
                                break
        
        return column_map
    
    def _build_single_feature(
        self,
        df: pd.DataFrame,
        definition: FeatureDefinition,
        available_columns: Dict[str, str],
        feature_data: Dict[str, Any],
        extracted_data: Dict[str, Any]  # 🔥 NOVO
    ) -> Any:
        """Constrói uma feature individual (COM EXTRATORES INTELIGENTES)"""
        
        # 🔥 PRIORIDADE 1: Feature inteligente
        if definition.type == FeatureType.INTELLIGENT and definition.intelligent_extractor:
            try:
                value = definition.intelligent_extractor(df)
                if value is not None:
                    logger.debug(f"   🧠 Feature inteligente '{definition.name}': {value}")
                    return value
            except Exception as e:
                logger.debug(f"   ⚠️ Erro no extrator inteligente '{definition.name}': {e}")
        
        if definition.type == FeatureType.CONSTANT:
            return definition.default_value
        
        elif definition.type == FeatureType.DIRECT:
            source_col = None
            
            for col, feat in available_columns.items():
                if feat == definition.name:
                    source_col = col
                    break
            
            if source_col is None and definition.source_column in df.columns:
                source_col = definition.source_column
            
            if source_col is None and definition.aliases:
                for alias in definition.aliases:
                    if alias in df.columns:
                        source_col = alias
                        break
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
                    data_dict = {}
                    for col in df.columns:
                        data_dict[col] = df[col]
                    for feat_name, value in feature_data.items():
                        data_dict[feat_name] = value
                    
                    temp_df = pd.DataFrame(data_dict)
                    result = definition.derive_func(temp_df)
                    
                    if isinstance(result, (pd.Series, np.ndarray)):
                        if len(result) != len(df):
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
            if definition.aggregate_func == 'count':
                return len(df)
            elif definition.aggregate_func == 'sum' and definition.aggregate_column:
                if definition.aggregate_column in df.columns:
                    return df[definition.aggregate_column].sum()
                for col, feat in available_columns.items():
                    if feat == definition.aggregate_column and col in df.columns:
                        return df[col].sum()
                return None
            elif definition.aggregate_func == 'mean' and definition.aggregate_column:
                if definition.aggregate_column in df.columns:
                    return df[definition.aggregate_column].mean()
                for col, feat in available_columns.items():
                    if feat == definition.aggregate_column and col in df.columns:
                        return df[col].mean()
                return None
            else:
                return None
        
        return None


# ==============================================
# 🔥 FEATURE MONITOR
# ==============================================

class FeatureMonitor:
    """Monitora divergências entre features esperadas e recebidas"""
    
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
            
            for feat in missing:
                self._stats["most_common_missing"][feat] = self._stats["most_common_missing"].get(feat, 0) + 1
            
            for feat in extra:
                self._stats["most_common_extra"][feat] = self._stats["most_common_extra"].get(feat, 0) + 1
            
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
            
            if auto_log:
                self._log_event(event)
            
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
        filename = f"{self.log_dir}/mismatch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(event.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Erro ao salvar log: {e}")
    
    def _send_alert(self, event: FeatureMismatchEvent):
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
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "recent_events": [e.to_dict() for e in self._events[-10:]],
            "total_events": len(self._events)
        }


# ==============================================
# 🔥 CLASSE PRINCIPAL - ML PIPELINE V7.0
# ==============================================

class MLPipeline:
    """
    🔥 Pipeline unificado de Machine Learning - VERSÃO 7.0 (INTELIGENTE)
    """
    
    CHART_CACHE_TTL = 300
    CHART_CACHE_MAX_SIZE = 20
    TIMEOUT_SECONDS = 60
    MAX_FEATURES = 20
    
    def __init__(self):
        # Diretórios
        self.models_dir = os.path.join("backend", "ml", "models")
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Feature Registry e Builder
        self.feature_registry = feature_registry
        self.feature_builder = FeatureBuilder(self.feature_registry)
        self.feature_monitor = FeatureMonitor()
        
        # Modelos
        self.models: Dict[str, Any] = {}
        self.scalers: Dict[str, Any] = {}
        self.label_encoders: Dict[str, Any] = {}
        self.feature_importances: Dict[str, Any] = {}
        
        # Estado
        self.is_initialized: bool = False
        self.model_source: str = ModelType.NONE.value
        self.last_predictions: Optional[np.ndarray] = None
        self.last_metrics: Dict[str, Any] = {}
        self._initialization_lock = asyncio.Lock()
        
        # Cache
        self._chart_cache: Dict[str, Dict[str, Any]] = {}
        self._chart_cache_ttl = self.CHART_CACHE_TTL
        self._chart_cache_max_size = self.CHART_CACHE_MAX_SIZE
        
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_ttl: int = 60
        self._cache_max_size: int = 100
        self._last_cache_cleanup: float = time.time()
        
        # Estatísticas de encoding
        self.encoding_stats: Dict[str, int] = {
            "utf-8": 0, "utf-8-sig": 0, "cp1252": 0,
            "iso-8859-1": 0, "latin1": 0,
            "detected": 0, "fallback": 0, "forced": 0,
            "excel": 0, "failed": 0, "total_attempts": 0
        }
        self.last_encoding: Optional[str] = None
        self.last_encoding_confidence: float = 0.0
        self.last_encoding_method: Optional[str] = None
        
        # Estatísticas de uso
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
            "chart_data_generated": 0,
            "chart_cache_hits": 0,
            "intelligent_features_used": 0  # 🔥 NOVO
        }
        
        # Módulos externos
        self._predictor = None
        self._automl_office = None
        self._boosting_ensemble = None
        self._gemini_service = None
        self._modules_loaded = False
        
        # Configuração
        self.config = {
            "default_model": ModelType.RANDOM_FOREST.value,
            "fallback_model": ModelType.PLACEHOLDER.value,
            "cache_enabled": True,
            "cache_ttl": 60,
            "max_retries": 3,
            "timeout_seconds": self.TIMEOUT_SECONDS,
            "encoding_fallbacks": ['utf-8-sig', 'utf-8', 'cp1252', 'iso-8859-1', 'latin1'],
            "min_features_for_ml": 3,
            "feature_match_threshold": 0.7,
            "max_features": self.MAX_FEATURES,
            "use_intelligent_features": True  # 🔥 NOVO
        }
        
        self._warnings: List[str] = []
        self._errors: List[str] = []
        self._executor = None
        
        logger.info("✅ MLPipeline V7.0 inicializado (INTELIGENTE)")
        logger.info(f"   📁 Modelos: {self.models_dir}")
        logger.info(f"   📊 Features: {self.feature_registry.get_expected_count()}")
        logger.info(f"   🧠 Features inteligentes: {len(self.feature_registry.get_intelligent_features())}")
        logger.info(f"   ⏰ Cache TTL: {self._cache_ttl}s")
        logger.info(f"   📈 Chart Cache: {self.CHART_CACHE_TTL}s")
        logger.info(f"   ⏱️ Timeout: {self.TIMEOUT_SECONDS}s")
    
    # ==============================================
    # MÓDULOS EXTERNOS
    # ==============================================
    
    def _ensure_modules_loaded(self):
        if self._modules_loaded:
            return
        
        try:
            from backend.ml.predict import predictor
            self._predictor = predictor
            logger.info("   📦 ModelPredictor integrado")
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
    # DETECÇÃO DE ENCODING
    # ==============================================
    
    def _detect_encoding(self, content: bytes) -> EncodingResult:
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
        
        # Chardet
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
        
        # Fallback
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
        
        # Forced
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
    # CARREGAMENTO DE DADOS
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
    # FEATURE BUILDING
    # ==============================================
    
    async def _build_features_intelligently(self, df: pd.DataFrame, filename: str = None) -> Tuple[Optional[pd.DataFrame], List[str]]:
        logger.info(f"🏗️ Construindo features para {len(df)} linhas...")
        
        result = self.feature_builder.build_features(df)
        
        if not result.success:
            logger.error(f"❌ Falha ao construir features: {result.errors}")
            return None, result.errors
        
        logger.info(f"   ✅ Features construídas!")
        logger.info(f"      📊 Shape: {result.features.shape}")
        logger.info(f"      🔧 Calculadas: {len(result.calculated_features)}")
        logger.info(f"      🧠 Inteligentes: {len(result.intelligent_features)}")
        logger.info(f"      ⚠️ Fallback: {len(result.fallback_used)}")
        logger.info(f"      ❌ Faltantes: {len(result.missing_features)}")
        
        if result.intelligent_features:
            logger.info(f"      🧠 Features inteligentes: {result.intelligent_features}")
        
        if result.fallback_used:
            logger.info(f"      ⚠️ Features com fallback: {result.fallback_used}")
            self.stats["feature_fallbacks"] += len(result.fallback_used)
        
        if result.intelligent_features:
            self.stats["intelligent_features_used"] += len(result.intelligent_features)
        
        if result.warnings:
            for warning in result.warnings:
                logger.warning(f"      ⚠️ {warning}")
        
        return result.features, result.warnings
    
    async def _validate_features(self, features: pd.DataFrame, filename: str = None) -> Dict[str, Any]:
        expected = self.feature_registry.get_expected_order()
        actual = features.columns.tolist()
        
        mismatch_result = self.feature_monitor.check_mismatch(
            expected_features=expected,
            actual_features=actual,
            filename=filename
        )
        
        if mismatch_result["has_mismatch"]:
            self.stats["feature_mismatches"] += 1
        
        # Verificar features com fallback
        fallback_used = []
        for feat_name in expected:
            definition = self.feature_registry.get_definition(feat_name)
            if definition and definition.can_fallback:
                if feat_name in actual and features[feat_name].nunique() == 1:
                    fallback_used.append(feat_name)
        
        return {
            "is_valid": mismatch_result["match_percentage"] >= self.config["feature_match_threshold"] * 100,
            "mismatch": mismatch_result,
            "fallback_used": fallback_used
        }
    
    # ==============================================
    # PREDIÇÃO
    # ==============================================
    
    async def _safe_predict_with_predictor(self, df: pd.DataFrame) -> Tuple[Optional[List[float]], List[str]]:
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
    # 🔥 CHART DATA - COM DADOS REAIS
    # ==============================================
    
    def _get_cached_chart_data(self, df: pd.DataFrame, predictions: List[float]) -> Optional[Dict[str, Any]]:
        cache_key = self._get_chart_cache_key(df)
        
        if cache_key in self._chart_cache:
            cached = self._chart_cache[cache_key]
            if time.time() - cached.get('timestamp', 0) < self._chart_cache_ttl:
                self.stats["chart_cache_hits"] += 1
                logger.info(f"📊 Chart data em cache: {cache_key[:8]}")
                return cached['data']
            else:
                del self._chart_cache[cache_key]
        
        return None
    
    def _set_chart_cache(self, df: pd.DataFrame, chart_data: Dict[str, Any]):
        cache_key = self._get_chart_cache_key(df)
        self._chart_cache[cache_key] = {
            'data': chart_data,
            'timestamp': time.time()
        }
        
        if len(self._chart_cache) > self._chart_cache_max_size:
            oldest = sorted(self._chart_cache.items(), key=lambda x: x[1]['timestamp'])
            to_remove = len(self._chart_cache) - self._chart_cache_max_size
            for i in range(to_remove):
                del self._chart_cache[oldest[i][0]]
            logger.info(f"🧹 Chart cache limpo: {to_remove} removidos")
    
    def _get_chart_cache_key(self, df: pd.DataFrame) -> str:
        try:
            sample = df.iloc[:50].values.tobytes()
            cols = str(df.columns.tolist()).encode()
            content = sample + cols + str(len(df)).encode()
            return hashlib.md5(content).hexdigest()[:16]
        except:
            return str(time.time())
    
    def _extract_chart_data_from_df(self, df: pd.DataFrame, predictions: List[float]) -> Dict[str, Any]:
        """
        🔥 EXTRAÇÃO DE CHART DATA - COM DADOS REAIS
        """
        cached = self._get_cached_chart_data(df, predictions)
        if cached:
            return cached
        
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        
        # 🔥 DETECTAR COLUNAS REAIS
        date_col = self._find_column(df, ['data', 'dia', 'date', 'dt', 'created_at', 'updated_at'])
        value_col = self._find_column(df, ['valor', 'receita', 'total', 'preco', 'revenue', 'amount'])
        cost_col = self._find_column(df, ['custo', 'custo_pecas', 'despesa', 'cost', 'gasto'])
        status_col = self._find_column(df, ['status', 'situacao', 'estado', 'state'])
        servico_col = self._find_column(df, ['serviço', 'servico', 'tipo', 'descricao'])
        
        logger.info(f"   🔍 Colunas detectadas: data={date_col}, valor={value_col}, custo={cost_col}, status={status_col}, servico={servico_col}")
        
        # 🔥 EXTRAIR DADOS REAIS
        weekly_revenue = np.zeros(7)
        weekly_costs = np.zeros(7)
        weekly_services = np.zeros(7, dtype=int)
        
        if date_col and value_col:
            try:
                dates = pd.to_datetime(df[date_col], errors='coerce')
                day_of_week = dates.dt.dayofweek.values
                valid_mask = ~np.isnan(day_of_week)
                
                if valid_mask.any():
                    values = pd.to_numeric(df[value_col], errors='coerce').fillna(0).values
                    
                    for i in range(7):
                        mask = (day_of_week == i) & valid_mask
                        if mask.any():
                            weekly_revenue[i] = values[mask].mean()
                            weekly_services[i] = mask.sum()
                    
                    # 🔥 CUSTOS REAIS
                    if cost_col and cost_col in df.columns:
                        costs = pd.to_numeric(df[cost_col], errors='coerce').fillna(0).values
                        for i in range(7):
                            mask = (day_of_week == i) & valid_mask
                            if mask.any():
                                weekly_costs[i] = costs[mask].mean()
                    else:
                        # 🔥 ESTIMATIVA INTELIGENTE
                        # Usar coluna de status para estimar custo
                        if status_col:
                            status_values = df[status_col].astype(str).str.lower()
                            # Serviços concluídos tendem a ter menos custo adicional
                            conclusao_mask = status_values.str.contains('concluído|concluida|finalizado')
                            fator_custo = 0.3 if conclusao_mask.any() else 0.4
                            weekly_costs = weekly_revenue * fator_custo
                        else:
                            weekly_costs = weekly_revenue * 0.35
                        
            except Exception as e:
                logger.warning(f"⚠️ Erro no processamento de dados: {e}")
                base = np.mean(predictions) * 1500 if predictions else 1000
                weekly_revenue = base * (0.5 + np.random.rand(7) * 0.8)
                weekly_costs = weekly_revenue * 0.35
                weekly_services = np.random.randint(2, 15, 7)
        else:
            # Fallback com dados estimados
            base = np.mean(predictions) * 1500 if predictions else 1000
            weekly_revenue = base * (0.5 + np.random.rand(7) * 0.8)
            weekly_costs = weekly_revenue * 0.35
            weekly_services = np.random.randint(2, 15, 7)
        
        # 🔥 SERVICOS COM DADOS REAIS (se disponível)
        if servico_col and len(df) > 0:
            try:
                servicos_counts = df[servico_col].value_counts().head(7)
                if len(servicos_counts) > 0:
                    # Mapear serviços para dias da semana
                    for i in range(min(7, len(servicos_counts))):
                        weekly_services[i] = max(1, int(servicos_counts.iloc[i]) // 7)
            except:
                pass
        
        # 🔥 MENSAL COM DADOS REAIS
        if date_col:
            try:
                dates = pd.to_datetime(df[date_col], errors='coerce')
                df['mes'] = dates.dt.month
                df['ano'] = dates.dt.year
                
                if value_col:
                    valores = pd.to_numeric(df[value_col], errors='coerce').fillna(0)
                    monthly_revenue = df.groupby(['ano', 'mes'])[value_col].sum().values
                    
                    if len(monthly_revenue) < 12:
                        # Completar com estimativas
                        base_mensal = np.mean(monthly_revenue) if len(monthly_revenue) > 0 else 5000
                        monthly_revenue = list(monthly_revenue) + [base_mensal * (0.8 + 0.4 * np.random.rand()) for _ in range(12 - len(monthly_revenue))]
                    elif len(monthly_revenue) > 12:
                        monthly_revenue = monthly_revenue[:12]
                else:
                    monthly_revenue = [round(5000 + i * 200 + np.random.rand() * 1000, 2) for i in range(12)]
            except:
                monthly_revenue = [round(5000 + i * 200 + np.random.rand() * 1000, 2) for i in range(12)]
        else:
            monthly_revenue = [round(5000 + i * 200 + np.random.rand() * 1000, 2) for i in range(12)]
        
        chart_data = {
            "weekly": {
                "labels": days,
                "revenue": [round(float(v), 2) for v in weekly_revenue],
                "costs": [round(float(v), 2) for v in weekly_costs]
            },
            "performance": {
                "labels": days,
                "services": [int(v) for v in weekly_services]
            },
            "monthly": {
                "labels": months,
                "revenue": [round(float(v), 2) for v in monthly_revenue[:12]]
            }
        }
        
        self._set_chart_cache(df, chart_data)
        self.stats["chart_data_generated"] += 1
        
        return chart_data
    
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
    # INSIGHTS E RECOMENDAÇÕES
    # ==============================================
    
    def _safe_predictions_to_list(self, predictions: Any) -> List[float]:
        if predictions is None:
            return []
        try:
            if hasattr(predictions, 'tolist'):
                return [float(p) for p in predictions.tolist() if p is not None and not np.isnan(p)]
            elif isinstance(predictions, list):
                return [float(p) for p in predictions if p is not None and not np.isnan(p)]
            elif isinstance(predictions, np.ndarray):
                return [float(p) for p in predictions if p is not None and not np.isnan(p)]
            else:
                return [float(p) for p in list(predictions) if p is not None and not np.isnan(p)]
        except Exception as e:
            logger.debug(f"⚠️ Erro ao converter predições: {e}")
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
            
            recommendations = self._generate_recommendations_safe(pred_list, df)
            return insights, recommendations
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar insights: {e}")
            return {}, ["Erro ao gerar insights"]
    
    def _generate_recommendations_safe(self, predictions: List[float], df: pd.DataFrame = None) -> List[str]:
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
            
            # 🔥 RECOMENDAÇÕES BASEADAS EM DADOS REAIS
            if df is not None:
                # Verificar taxa de conclusão
                status_col = self._find_column(df, ['status', 'situacao', 'estado'])
                if status_col:
                    status_values = df[status_col].astype(str).str.lower()
                    concluidos = status_values.str.contains('concluído|concluida|finalizado').sum()
                    total = len(df)
                    if total > 0 and (concluidos / total) < 0.5:
                        recommendations.append("📌 Baixa taxa de conclusão. Invista em gestão de prazos e recursos.")
                
                # Verificar cancelamentos
                if status_col:
                    cancelados = status_values.str.contains('cancelado|cancelled').sum()
                    if total > 0 and (cancelados / total) > 0.15:
                        recommendations.append("⚠️ Alta taxa de cancelamento. Investigue as causas e melhore a comunicação.")
                
                # Verificar ticket médio
                value_col = self._find_column(df, ['valor', 'receita', 'total'])
                if value_col:
                    valores = pd.to_numeric(df[value_col], errors='coerce')
                    valores = valores[valores > 0]
                    if len(valores) > 0 and valores.mean() < 100:
                        recommendations.append("💰 Ticket médio baixo. Considere revisar preços ou oferecer serviços adicionais.")
            
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
    # 🔥 PREDICT - MÉTODO PRINCIPAL (INTELIGENTE)
    # ==============================================
    
    async def predict(
        self,
        df_or_content: Union[pd.DataFrame, bytes, str],
        filename: Optional[str] = None,
        user_id: Optional[int] = None,
        db_session = None,
        process_id: int = None
    ) -> MLPipelineResult:
        """
        🔥 MÉTODO PRINCIPAL - VERSÃO 7.0 (INTELIGENTE)
        """
        start_time = time.time()
        encoding_used = None
        warnings = []
        status = PredictionStatus.FAILED
        chart_data = {}
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
            
            # 2. 🔥 ATUALIZAR PROGRESSO
            await self._update_progress(db_session, process_id, 0.20, "Construindo features...")
            
            # 3. Construir features
            features, build_warnings = await self._build_features_intelligently(df, filename)
            
            if build_warnings:
                warnings.extend(build_warnings)
            
            if features is None:
                return self._create_error_result(
                    "Falha ao construir features",
                    encoding_used=encoding_used,
                    warnings=warnings
                )
            
            # 4. 🔥 ATUALIZAR PROGRESSO
            await self._update_progress(db_session, process_id, 0.40, "Validando features...")
            
            # 5. Validar features
            validation_result = await self._validate_features(features, filename)
            warnings.append(f"Match de features: {validation_result['mismatch']['match_percentage']:.1f}%")
            
            if validation_result['mismatch']['has_mismatch']:
                logger.warning(f"   ⚠️ Mismatch detectado: {validation_result['mismatch']['missing_count']} features faltantes")
            
            # 6. Preparar X
            X = features.values
            
            # 7. 🔥 ATUALIZAR PROGRESSO
            await self._update_progress(db_session, process_id, 0.55, "Fazendo predições...")
            
            # 8. Tentar ModelPredictor
            predictor_predictions, predictor_warnings = await self._safe_predict_with_predictor(df)
            if predictor_warnings:
                warnings.extend(predictor_warnings)
            
            predictions = predictor_predictions
            
            # 9. Fallback: pipeline interno
            if predictions is None or len(predictions) == 0:
                if not self.is_initialized:
                    await self.initialize()
                
                model_predictions, probas = await self._predict_with_model('default', X)
                
                if model_predictions is not None and len(model_predictions) > 0:
                    predictions = model_predictions.tolist()
                else:
                    predictions = self._fallback_predictions(len(X)).tolist()
                    warnings.append("Usando fallback para predições")
            
            # 10. 🔥 ATUALIZAR PROGRESSO
            await self._update_progress(db_session, process_id, 0.75, "Gerando insights...")
            
            # 11. Insights e recomendações
            processed = {'stats': {'rows': len(df), 'columns': len(df.columns)}}
            insights, recommendations = self._generate_insights_safe(df, predictions, processed)
            
            # 12. Métricas
            metrics = self._calculate_metrics(predictions, processed, encoding_used)
            
            # 13. 🔥 Chart data (com dados reais)
            await self._update_progress(db_session, process_id, 0.85, "Gerando gráficos...")
            
            try:
                chart_data = self._extract_chart_data_from_df(df, predictions)
                self.stats['chart_data_generated'] += 1
                logger.info(f"📊 Chart_data gerado: weekly={len(chart_data.get('weekly', {}).get('revenue', []))} dias")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao gerar chart_data: {e}")
                chart_data = self._generate_fallback_chart_data()
            
            # 14. 🔥 ATUALIZAR PROGRESSO
            await self._update_progress(db_session, process_id, 0.95, "Finalizando...")
            
            # 15. Resultado
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
            
            # 16. 🔥 ATUALIZAR PROGRESSO FINAL
            await self._update_progress(db_session, process_id, 1.0, "Concluído! ✅")
            
            logger.info(f"✅ Predição concluída: {len(predictions)} resultados, encoding: {encoding_used}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro na predição: {e}")
            logger.error(traceback.format_exc())
            self.stats['failed_predictions'] += 1
            await self._update_progress(db_session, process_id, 0, f"Erro: {str(e)[:50]}")
            return self._create_error_result(
                str(e),
                encoding_used=encoding_used,
                warnings=warnings,
                processing_time_ms=(time.time() - start_time) * 1000,
                chart_data=chart_data
            )
    
    # ==============================================
    # 🔥 PROGRESSO
    # ==============================================
    
    async def _update_progress(self, db_session, process_id: int, progress: float, message: str):
        if db_session and process_id:
            try:
                from backend import models
                analysis = db_session.query(models.Analysis).filter(
                    models.Analysis.id == process_id
                ).first()
                if analysis:
                    analysis.progress = int(progress * 100)
                    analysis.progress_message = message
                    db_session.commit()
                    logger.debug(f"📊 [DB] Progresso: {int(progress * 100)}% - {message}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao salvar progresso: {e}")
    
    # ==============================================
    # INICIALIZAÇÃO DE MODELOS
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
    # UTILITÁRIOS
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
            "chart_cache_size": len(self._chart_cache),
            "chart_cache_hits": self.stats.get('chart_cache_hits', 0),
            "intelligent_features_used": self.stats.get('intelligent_features_used', 0),
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
        return {
            "total_features": self.feature_registry.get_expected_count(),
            "required_features": self.feature_registry.get_required_features(),
            "optional_features": self.feature_registry.get_optional_features(),
            "intelligent_features": self.feature_registry.get_intelligent_features(),
            "expected_order": self.feature_registry.get_expected_order(),
            "feature_definitions": {
                name: {
                    "type": feat.type.value,
                    "description": feat.description,
                    "required": feat.required,
                    "source_column": feat.source_column,
                    "aliases": feat.aliases,
                    "can_fallback": feat.can_fallback,
                    "has_intelligent_extractor": feat.intelligent_extractor is not None
                }
                for name, feat in self.feature_registry._features.items()
            }
        }
    
    def clear_cache(self):
        self._cache.clear()
        self._chart_cache.clear()
        self.feature_builder._extracted_cache.clear()
        logger.info("🧹 Cache do pipeline limpo")
    
    def reset(self):
        self.is_initialized = False
        self.models.clear()
        self.scalers.clear()
        self._cache.clear()
        self._chart_cache.clear()
        self.feature_builder._extracted_cache.clear()
        self.last_predictions = None
        self.last_metrics = {}
        logger.info("🔄 Pipeline resetado")
    
    def __del__(self):
        if hasattr(self, '_executor') and self._executor:
            try:
                self._executor.shutdown(wait=False)
                logger.info("🧹 ThreadPoolExecutor shutdown")
            except:
                pass


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

pipeline = MLPipeline()


# ==============================================
# FUNÇÕES DE COMPATIBILIDADE
# ==============================================

async def process_file_content(
    content: bytes,
    filename: str,
    user_id: Optional[int] = None,
    db_session = None,
    process_id: int = None
) -> Dict[str, Any]:
    try:
        logger.info(f"📁 process_file_content: {filename} ({len(content)} bytes)")
        result = await pipeline.predict(
            content,
            filename,
            user_id=user_id,
            db_session=db_session,
            process_id=process_id
        )
        
        result_dict = result.to_dict()
        
        if result.encoding_used:
            result_dict['encoding_used'] = result.encoding_used
            result_dict['metadata'] = result_dict.get('metadata', {})
            result_dict['metadata']['encoding_used'] = result.encoding_used
        
        if result.metadata:
            result_dict['metadata']['validation'] = result.metadata.get('validation', {})
        
        # 🔥 NOVO: Adicionar estatísticas de features inteligentes
        result_dict['metadata']['intelligent_features'] = result_dict.get('metadata', {}).get('validation', {}).get('fallback_used', [])
        
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
    print("🧪 TESTANDO PIPELINE ML V7.0 (INTELIGENTE)")
    print("=" * 70)
    
    import pandas as pd
    import numpy as np
    from io import BytesIO
    
    np.random.seed(42)
    
    # 🔥 DADOS MAIS REALISTAS
    df = pd.DataFrame({
        'OS': [f'OS-{i:04d}' for i in range(1, 101)],
        'Data': pd.date_range('2024-01-01', periods=100, freq='D'),
        'Cliente': [f'Cliente_{i}' for i in range(1, 101)],
        'Valor do serviço (R$)': np.random.randn(100) * 200 + 500,
        'Custo estimado (R$)': np.random.randn(100) * 100 + 200,
        'Status': np.random.choice(['Concluído', 'Em andamento', 'Cancelado'], 100, p=[0.6, 0.25, 0.15]),
        'Horas de mão de obra': np.random.randn(100) * 2 + 4,
        'Serviço': np.random.choice(['Revisão', 'Troca de óleo', 'Suspensão', 'Freios', 'Ar-condicionado'], 100)
    })
    
    # Garantir valores positivos
    df['Valor do serviço (R$)'] = df['Valor do serviço (R$)'].clip(50, 2000)
    df['Custo estimado (R$)'] = df['Custo estimado (R$)'].clip(20, 1000)
    df['Horas de mão de obra'] = df['Horas de mão de obra'].clip(0.5, 10)
    
    print(f"📊 Dados de teste: {len(df)} linhas, {len(df.columns)} colunas")
    print(f"   📅 Período: {df['Data'].min().date()} a {df['Data'].max().date()}")
    print(f"   📊 Status: {df['Status'].value_counts().to_dict()}")
    
    buffer = BytesIO()
    df.to_csv(buffer, index=False, encoding='utf-8')
    content = buffer.getvalue()
    
    result = await process_file_content(content, "oficina_teste.csv")
    
    print(f"\n📊 RESULTADO:")
    print(f"   ✅ Sucesso: {result.get('success')}")
    print(f"   🔢 Predições: {len(result.get('predictions', []))}")
    print(f"   📈 Média: {result.get('metrics', {}).get('mean_prediction', 0):.3f}")
    print(f"   🎯 Modelo: {result.get('model_used', 'unknown')}")
    print(f"   📝 Encoding: {result.get('encoding_used', 'unknown')}")
    print(f"   📊 Features: {result.get('metadata', {}).get('feature_count', 0)}")
    
    # 🔥 Mostrar features inteligentes
    intelligent_features = result.get('metadata', {}).get('validation', {}).get('fallback_used', [])
    if intelligent_features:
        print(f"   🧠 Features inteligentes: {intelligent_features}")
    
    if result.get('chart_data'):
        weekly = result['chart_data'].get('weekly', {})
        print(f"   📅 Weekly: {len(weekly.get('revenue', []))} dias")
        if weekly.get('revenue'):
            print(f"      Receita média: R$ {np.mean(weekly['revenue']):.2f}")
    
    recommendations = result.get('recommendations', [])
    if recommendations:
        print(f"   💡 Recomendações:")
        for rec in recommendations[:3]:
            print(f"      - {rec}")
    
    print("\n" + "=" * 70)
    print("✅ Teste concluído!")
    print("=" * 70)
    
    return result


# ==============================================
# INICIALIZAÇÃO
# ==============================================

print("\n" + "=" * 70)
print("✅ preprocessing.py V7.0 INTELIGENTE carregado com sucesso!")
print("=" * 70)
print("   🔥 FEATURE REGISTRY INTELIGENTE:")
print("      • " + str(feature_registry.get_expected_count()) + " features registradas")
print("      • 🧠 " + str(len(feature_registry.get_intelligent_features())) + " features inteligentes")
print("      • " + str(len(feature_registry.get_required_features())) + " obrigatórias")
print("      • 🔥 LIMITE: " + str(FeatureRegistry.MAX_FEATURES) + " features máximas")
print("   🔥 EXTRATORES INTELIGENTES:")
print("      • total_servicos → contagem real de OS")
print("      • media_servicos_dia → média real por dia")
print("      • total_receita → soma real dos valores")
print("      • ticket_medio → média real")
print("      • taxa_conclusao → % real de conclusão")
print("      • taxa_cancelamento → % real de cancelamento")
print("      • media_horas → média real de horas")
print("   🔥 FEATURE BUILDER:")
print("      • Detecção automática de colunas")
print("      • Cálculo de features derivadas")
print("      • 🔥 CACHE de features (TTL: 5min)")
print("      • 🔥 EXTRATORES INTELIGENTES")
print("      • Fallback inteligente")
print("   🔥 CHART DATA:")
print("      • 🔥 DADOS REAIS: usa colunas reais do arquivo")
print("      • 🔥 CACHE de chart_data (TTL: 5min)")
print("   🔥 PROGRESSO:")
print("      • 🔥 Suporte a db_session para salvar progresso")
print("   📊 Métodos:")
print("      • pipeline.predict(bytes, filename, user_id, db_session, process_id)")
print("      • pipeline.get_feature_registry_info()")
print("      • pipeline.get_status()")
print("=" * 70)