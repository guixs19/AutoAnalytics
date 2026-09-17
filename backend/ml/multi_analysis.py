# backend/ml/multi_analysis.py - VERSÃO 7.0 (GEMINI DINÂMICO + FALLBACK DATA-DRIVEN)
"""
🔥 ANÁLISE MÚLTIPLA DE ARQUIVOS - V7.0
================================================================================
✅ NOVIDADES V7.0:
   - 📊 FALLBACK DATA-DRIVEN: frases geradas com números REAIS do usuário
   - 🎯 Templates condicionais por faixa (margem, risco, ticket, volume, tendência)
   - 🧠 Cada frase incorpora métricas reais + predições do ML
   - 💬 Muito mais variações: 3-6 frases por faixa/categoria
   - 🔥 Combina 3 fontes: métricas do arquivo + ML + séries temporais
   - 🎲 Determinístico por filename (resultado reprodutível)
   - 🛡️ Formatação BRL/PCT brasileira (R$ 1.234,56 | 15,2%)
   - ✅ GEMINI SEMPRE É CHAMADO PRIMEIRO — fallback só se falhar

✅ MANTIDO V6.3:
   - 🔄 GEMINI DINÂMICO (revalidação em tempo real)
   - 🛡️ CIRCUIT BREAKER (proteção contra serviço degradado)
   - 📊 TELEMETRIA completa
   - ⚡ MICRO-CACHE 10s TTL
   - 🔒 DEEPCOPY no cache
================================================================================
"""

import pandas as pd
import numpy as np
import asyncio
import logging
import json
import hashlib
import time
import re
import math
import copy
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ==============================================
# ENUMS E CONSTANTES
# ==============================================

class Priority(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class RiskLevel(str, Enum):
    BAIXO = "Baixo"
    MODERADO = "Moderado"
    ALTO = "Alto"


class TrendDirection(str, Enum):
    CRESCENTE = "crescente"
    DECRESCENTE = "decrescente"
    ESTAVEL = "estavel"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CACHED = "cached"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ==============================================
# DECORATORS
# ==============================================

def timing_decorator(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed = (time.time() - start) * 1000
            logger.debug(f"⏱️ {func.__name__} took {elapsed:.2f}ms")
            return result
        except Exception:
            elapsed = (time.time() - start) * 1000
            logger.exception(f"❌ {func.__name__} failed after {elapsed:.2f}ms")
            raise
    return wrapper


# ==============================================
# DATACLASSES
# ==============================================

@dataclass
class FileMetrics:
    filename: str
    total_rows: int
    total_revenue: float
    total_costs: float
    profit: float
    margin: float
    avg_score: float
    high_risk_percentage: float
    low_risk_percentage: float
    predictions: List[float] = field(default_factory=list)
    chart_data: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    encoding_used: Optional[str] = None
    processing_time_ms: float = 0.0
    model_used: str = "default"
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    roc_auc: float = 0.0
    normalization: str = "Z-Score"
    feature_count: int = 0


@dataclass
class MLResults:
    models_used: List[str]
    encodings_used: List[str]
    total_predictions: int
    avg_score: float
    std_score: float
    min_score: float
    max_score: float
    risk_distribution: Dict[str, float]
    avg_accuracy: float = 0.0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_f1: float = 0.0
    normalization: str = "Z-Score"


@dataclass
class ComparisonResults:
    best_revenue: str = ""
    best_profit: str = ""
    best_growth: str = ""
    best_efficiency: str = ""
    highest_risk: str = ""
    lowest_performance: str = ""
    comparison_table: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""


@dataclass
class TrendResults:
    direction: TrendDirection = TrendDirection.ESTAVEL
    strength: float = 0.5
    confidence: float = 0.7
    description: str = ""
    key_observations: List[str] = field(default_factory=list)


@dataclass
class ConsolidatedAnalysis:
    total_files: int
    processed_files: int
    failed_files: int
    user_email: str
    timestamp: str
    files: List[FileMetrics] = field(default_factory=list)
    ml_results: Optional[MLResults] = None
    comparison: Optional[ComparisonResults] = None
    trend: Optional[TrendResults] = None
    total_revenue: float = 0
    total_profit: float = 0
    avg_margin: float = 0
    avg_score_overall: float = 0
    combined_insights: List[str] = field(default_factory=list)
    combined_recommendations: List[str] = field(default_factory=list)
    chart_data: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0
    normalization: str = "Z-Score"
    total_files_analyzed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "user_email": self.user_email,
            "timestamp": self.timestamp,
            "normalization": self.normalization,
            "files": [
                {
                    "filename": f.filename,
                    "total_rows": f.total_rows,
                    "total_revenue": round(f.total_revenue, 2),
                    "total_costs": round(f.total_costs, 2),
                    "profit": round(f.profit, 2),
                    "margin": round(f.margin, 1),
                    "avg_score": round(f.avg_score, 3),
                    "high_risk_percentage": round(f.high_risk_percentage, 1),
                    "low_risk_percentage": round(f.low_risk_percentage, 1),
                    "encoding_used": f.encoding_used,
                    "model_used": f.model_used,
                    "processing_time_ms": round(f.processing_time_ms, 2),
                    "precision": round(f.precision, 3),
                    "recall": round(f.recall, 3),
                    "f1_score": round(f.f1_score, 3),
                    "feature_count": f.feature_count,
                    "normalization": f.normalization,
                }
                for f in self.files
            ],
            "ml_results": {
                "models_used": self.ml_results.models_used if self.ml_results else [],
                "encodings_used": self.ml_results.encodings_used if self.ml_results else [],
                "total_predictions": self.ml_results.total_predictions if self.ml_results else 0,
                "avg_score": round(self.ml_results.avg_score, 3) if self.ml_results else 0,
                "risk_distribution": self.ml_results.risk_distribution if self.ml_results else {},
                "avg_accuracy": round(self.ml_results.avg_accuracy, 3) if self.ml_results else 0,
                "avg_precision": round(self.ml_results.avg_precision, 3) if self.ml_results else 0,
                "avg_recall": round(self.ml_results.avg_recall, 3) if self.ml_results else 0,
                "avg_f1": round(self.ml_results.avg_f1, 3) if self.ml_results else 0,
                "normalization": self.ml_results.normalization if self.ml_results else "Z-Score",
            } if self.ml_results else {},
            "comparison": {
                "best_revenue": self.comparison.best_revenue if self.comparison else "",
                "best_profit": self.comparison.best_profit if self.comparison else "",
                "best_growth": self.comparison.best_growth if self.comparison else "",
                "best_efficiency": self.comparison.best_efficiency if self.comparison else "",
                "highest_risk": self.comparison.highest_risk if self.comparison else "",
                "lowest_performance": self.comparison.lowest_performance if self.comparison else "",
            } if self.comparison else {},
            "trend": {
                "direction": self.trend.direction.value if self.trend else "estavel",
                "strength": round(self.trend.strength, 2) if self.trend else 0.5,
                "confidence": round(self.trend.confidence, 2) if self.trend else 0.7,
                "description": self.trend.description if self.trend else "",
                "key_observations": self.trend.key_observations if self.trend else [],
            } if self.trend else {},
            "total_revenue": round(self.total_revenue, 2),
            "total_profit": round(self.total_profit, 2),
            "avg_margin": round(self.avg_margin, 1),
            "avg_score_overall": round(self.avg_score_overall, 3),
            "combined_insights": self.combined_insights[:5],
            "combined_recommendations": self.combined_recommendations[:5],
            "chart_data": self.chart_data,
            "processing_time_ms": round(self.processing_time_ms, 2),
        }


@dataclass
class MultiFileAnalysisResult:
    success: bool
    total_files: int
    processed_files: int
    failed_files: int
    executive_score: Optional[Dict[str, Any]] = None
    executive_summary: str = ""
    files: List[Dict[str, Any]] = field(default_factory=list)
    comparison: Optional[ComparisonResults] = None
    trend: Optional[TrendResults] = None
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    forecast: str = ""
    general_conclusion: str = ""
    chart_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    processing_time_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cache_hit: bool = False
    encodings_used: List[str] = field(default_factory=list)
    status: str = AnalysisStatus.PENDING.value
    progress: float = 0.0
    normalization: str = "Z-Score"
    model_version: str = "V7.0"
    feature_count_avg: int = 0
    analysis_source: str = "ml"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "progress": self.progress,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "executive_score": self.executive_score or {},
            "executive_summary": self.executive_summary,
            "files": self.files,
            "comparison": self._comparison_to_dict(),
            "trend": self._trend_to_dict(),
            "recommendations": self.recommendations,
            "forecast": self.forecast,
            "general_conclusion": self.general_conclusion,
            "chart_data": self.chart_data or {},
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp,
            "cache_hit": self.cache_hit,
            "encodings_used": list(set(self.encodings_used)) if self.encodings_used else [],
            "normalization": self.normalization,
            "model_version": self.model_version,
            "feature_count_avg": self.feature_count_avg,
            "analysis_source": self.analysis_source,
        }

    def _comparison_to_dict(self) -> Dict[str, Any]:
        if not self.comparison:
            return {}
        if isinstance(self.comparison, dict):
            return self.comparison
        if hasattr(self.comparison, 'best_revenue'):
            return {
                "best_revenue": self.comparison.best_revenue or "",
                "best_profit": self.comparison.best_profit or "",
                "best_growth": self.comparison.best_growth or "",
                "best_efficiency": self.comparison.best_efficiency or "",
                "highest_risk": self.comparison.highest_risk or "",
                "lowest_performance": self.comparison.lowest_performance or "",
                "summary": getattr(self.comparison, 'summary', ''),
            }
        return {}

    def _trend_to_dict(self) -> Dict[str, Any]:
        if not self.trend:
            return {}
        if isinstance(self.trend, dict):
            return self.trend
        if hasattr(self.trend, 'direction'):
            d = self.trend.direction
            d_val = d.value if hasattr(d, 'value') else str(d)
            return {
                "direction": d_val,
                "strength": round(self.trend.strength, 2) if hasattr(self.trend, 'strength') else 0.5,
                "confidence": round(self.trend.confidence, 2) if hasattr(self.trend, 'confidence') else 0.7,
                "description": getattr(self.trend, 'description', ''),
                "key_observations": getattr(self.trend, 'key_observations', []),
            }
        return {}


# ==============================================
# 🔥 HELPERS DE FORMATAÇÃO
# ==============================================

def _fmt_brl(v: float) -> str:
    """Formata em Real brasileiro: R$ 1.234,56"""
    try:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {v:.2f}"


def _fmt_pct(v: float, decimals: int = 1) -> str:
    try:
        return f"{v:.{decimals}f}%".replace(".", ",")
    except Exception:
        return f"{v}%"


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    try:
        return a / b if b else default
    except Exception:
        return default


def _seed_from(s: str) -> int:
    """Seed determinístico baseado no filename."""
    return abs(hash(s)) % (2 ** 31)


def _pick(pool: List[str], seed: int = 0) -> str:
    if not pool:
        return ""
    return pool[seed % len(pool)]


# ==============================================
# 🔥 FAIXAS (BUCKETS)
# ==============================================

class MarginBand:
    NEGATIVE = "negativa"
    CRITICAL = "critica"
    LOW      = "baixa"
    MODERATE = "moderada"
    HEALTHY  = "saudavel"
    EXCELLENT= "excelente"

    @staticmethod
    def of(m: float) -> str:
        if m < 0: return MarginBand.NEGATIVE
        if m < 10: return MarginBand.CRITICAL
        if m < 20: return MarginBand.LOW
        if m < 30: return MarginBand.MODERATE
        if m < 45: return MarginBand.HEALTHY
        return MarginBand.EXCELLENT


class RiskBand:
    LOW      = "baixo"
    MODERATE = "moderado"
    HIGH     = "alto"
    CRITICAL = "critico"

    @staticmethod
    def of(pct: float) -> str:
        if pct < 15: return RiskBand.LOW
        if pct < 30: return RiskBand.MODERATE
        if pct < 50: return RiskBand.HIGH
        return RiskBand.CRITICAL


class TicketBand:
    ZERO = "zero"
    LOW = "baixo"
    MEDIUM = "medio"
    HIGH = "alto"
    PREMIUM = "premium"

    @staticmethod
    def of(t: float) -> str:
        if t <= 0: return TicketBand.ZERO
        if t < 100: return TicketBand.LOW
        if t < 500: return TicketBand.MEDIUM
        if t < 2000: return TicketBand.HIGH
        return TicketBand.PREMIUM


class VolumeBand:
    LOW = "baixo"
    MEDIUM = "medio"
    HIGH = "alto"
    VERY_HIGH = "muito_alto"

    @staticmethod
    def of(n: int) -> str:
        if n < 50: return VolumeBand.LOW
        if n < 200: return VolumeBand.MEDIUM
        if n < 1000: return VolumeBand.HIGH
        return VolumeBand.VERY_HIGH


class TrendBand:
    STRONG_UP = "forte_alta"
    UP = "alta"
    STABLE = "estavel"
    DOWN = "queda"
    STRONG_DOWN = "forte_queda"

    @staticmethod
    def of(growth_pct: float) -> str:
        if growth_pct > 30: return TrendBand.STRONG_UP
        if growth_pct > 10: return TrendBand.UP
        if growth_pct > -10: return TrendBand.STABLE
        if growth_pct > -30: return TrendBand.DOWN
        return TrendBand.STRONG_DOWN


# ==============================================
# 🔥 POOLS DE FRASES DATA-DRIVEN
# ==============================================

MARGIN_INSIGHTS = {
    MarginBand.NEGATIVE: [
        "A margem de {margin_fmt} coloca a operação em prejuízo: cada venda de {ticket_fmt} gera perda líquida de {loss_per_sale}.",
        "Com margem negativa de {margin_fmt}, o prejuízo acumulado é de {abs_profit_fmt} — precisa ser revertido com urgência.",
        "Margem de {margin_fmt} significa que a operação paga mais do que arrecada. Ação corretiva é obrigatória.",
    ],
    MarginBand.CRITICAL: [
        "Margem crítica de {margin_fmt} — bem abaixo do piso de 10% que separa saúde de risco operacional.",
        "Com margem em {margin_fmt}, qualquer oscilação de custo pode transformar o resultado em prejuízo.",
        "A margem de {margin_fmt} é insuficiente para cobrir imprevistos: o ideal seria pelo menos 20%.",
    ],
    MarginBand.LOW: [
        "Margem de {margin_fmt} está abaixo do ideal: há espaço para ganho de {gap} até o patamar saudável (30%).",
        "Com {margin_fmt} de margem, o negócio respira mas não acumula reserva. Cada p.p. ganho vale {per_point}.",
        "Margem baixa de {margin_fmt}: pequenos ajustes de preço/custo podem elevar o lucro de {profit_fmt}.",
    ],
    MarginBand.MODERATE: [
        "Margem moderada de {margin_fmt} — aceitável, mas o teto saudável (30%) está a apenas {gap} de distância.",
        "Com {margin_fmt} de margem, o negócio é sustentável. Otimizações podem levar ao patamar 'saudável'.",
        "Margem de {margin_fmt} está dentro do aceitável. O foco agora é eficiência, não sobrevivência.",
    ],
    MarginBand.HEALTHY: [
        "Margem saudável de {margin_fmt}: a operação cobre custos com folga e gera lucro de {profit_fmt}.",
        "Com {margin_fmt} de margem, o negócio tem margem de manobra para investir ou absorver imprevistos.",
        "Margem de {margin_fmt} está dentro da zona saudável do setor — boa notícia para a sustentabilidade.",
    ],
    MarginBand.EXCELLENT: [
        "Margem excelente de {margin_fmt} — acima da média do setor. Lucro de {profit_fmt} demonstra forte controle de custos.",
        "Com {margin_fmt} de margem, a operação é referência: alta eficiência e poder de precificação.",
        "Margem de {margin_fmt} coloca o negócio no topo do setor. Considere reinvestir o lucro de {profit_fmt}.",
    ],
}

RISK_INSIGHTS = {
    RiskBand.LOW: [
        "Apenas {high_pct_fmt} dos {n} registros analisados pelo modelo de ML estão em alto risco — base sólida.",
        "O modelo aponta exposição baixa: {high_pct_fmt} em alto risco e {low_pct_fmt} em baixo risco.",
        "Risco controlado: das {n} predições, {n_low} são de baixo risco — nenhum sinal de alerta.",
    ],
    RiskBand.MODERATE: [
        "{high_pct_fmt} dos registros estão em alto risco — dentro do tolerável, mas exige monitoramento.",
        "O ML identificou {n_high} registros em alto risco de {n} totais ({high_pct_fmt}). Atenção contínua.",
        "Exposição moderada: {high_pct_fmt} em alto risco, {low_pct_fmt} em baixo. Equilíbrio razoável.",
    ],
    RiskBand.HIGH: [
        "Alerta: {high_pct_fmt} dos {n} registros são de alto risco pelo modelo preditivo. Ação preventiva recomendada.",
        "O ML detectou concentração preocupante: {n_high} casos em alto risco ({high_pct_fmt}).",
        "Com {high_pct_fmt} em alto risco, a probabilidade de evento adverso sobe — reveja processos.",
    ],
    RiskBand.CRITICAL: [
        "🚨 Situação crítica: {high_pct_fmt} dos {n} registros estão em alto risco segundo o modelo. Intervenção imediata.",
        "O ML sinaliza colapso iminente: {n_high} de {n} registros em alto risco ({high_pct_fmt}).",
        "Nível de risco insustentável: {high_pct_fmt} em alto risco. Priorize mitigação agora.",
    ],
}

TICKET_INSIGHTS = {
    TicketBand.ZERO: [
        "Nenhum valor médio foi extraído dos dados — verifique a coluna de valor/ticket.",
    ],
    TicketBand.LOW: [
        "Ticket médio de {ticket_fmt} é baixo: cada venda contribui pouco para cobrir custos fixos.",
        "Com ticket de {ticket_fmt}, são necessárias {n_for_10k} vendas para faturar R$ 10.000,00.",
        "Ticket médio de {ticket_fmt} — oportunidade clara de up-sell e cross-sell.",
    ],
    TicketBand.MEDIUM: [
        "Ticket médio de {ticket_fmt} está na faixa esperada para o setor de serviços.",
        "Com ticket de {ticket_fmt}, a receita de {revenue_fmt} vem de {n} atendimentos.",
        "Ticket médio de {ticket_fmt} — patamar saudável. Considere ofertas premium.",
    ],
    TicketBand.HIGH: [
        "Ticket médio alto de {ticket_fmt}: cada atendimento contribui significativamente para a receita.",
        "Com {ticket_fmt} por atendimento, são necessários apenas {n_for_10k} para R$ 10.000,00.",
        "Ticket médio de {ticket_fmt} — poder de precificação confirmado.",
    ],
    TicketBand.PREMIUM: [
        "Ticket premium de {ticket_fmt} — operação com foco em valor, não volume.",
        "Com {ticket_fmt} por atendimento, a base de {n} clientes já gera {revenue_fmt}.",
        "Ticket de {ticket_fmt} coloca o negócio em patamar premium — fidelização é chave.",
    ],
}

VOLUME_INSIGHTS = {
    VolumeBand.LOW: [
        "Volume de {n} registros é baixo — a análise estatística tem margem de erro maior.",
        "Com apenas {n} registros, o modelo preditivo foi treinado com dados limitados.",
        "Base de {n} registros — considere ampliar o histórico para maior precisão.",
    ],
    VolumeBand.MEDIUM: [
        "Volume de {n} registros é adequado para análises preditivas confiáveis.",
        "Com {n} registros, o modelo consegue captar padrões com razoável precisão.",
        "Base de {n} registros — dentro do esperado para análises operacionais.",
    ],
    VolumeBand.HIGH: [
        "Volume robusto de {n} registros — análises estatísticas têm alta confiabilidade.",
        "Com {n} registros, o modelo preditivo identifica padrões com boa significância.",
        "Base de {n} registros permite segmentações e análises granulares.",
    ],
    VolumeBand.VERY_HIGH: [
        "Volume muito alto de {n} registros — ideal para modelagem avançada e séries temporais.",
        "Com {n} registros, a análise tem poder estatístico comparável a benchmarks do setor.",
        "Base massiva de {n} registros — permite análise por clusters e personas.",
    ],
}

TREND_INSIGHTS = {
    TrendBand.STRONG_UP: [
        "Crescimento forte de {growth_fmt} no período — tendência clara de expansão.",
        "Receita cresceu {growth_fmt} entre os meses analisados. Ritmo acelerado de crescimento.",
        "Tendência fortemente positiva: {growth_fmt} de crescimento. Prepare a operação para escalar.",
    ],
    TrendBand.UP: [
        "Crescimento moderado de {growth_fmt} no período — direção correta.",
        "Receita avançou {growth_fmt} entre os meses — momentum positivo.",
        "Tendência de alta: {growth_fmt} de crescimento consistente.",
    ],
    TrendBand.STABLE: [
        "Receita estável: variação de apenas {growth_fmt} no período analisado.",
        "Tendência lateral com {growth_fmt} de oscilação — negócio em equilíbrio.",
        "Sem tendência clara: receita variou {growth_fmt} entre os meses.",
    ],
    TrendBand.DOWN: [
        "Queda de {abs_growth_fmt} na receita do período — atenção aos indicadores.",
        "Tendência de baixa: {abs_growth_fmt} de queda. Reveja estratégias comerciais.",
        "Receita recuou {abs_growth_fmt} — momento de cautela e revisão de custos.",
    ],
    TrendBand.STRONG_DOWN: [
        "Queda acentuada de {abs_growth_fmt} na receita — situação exige ação imediata.",
        "Retração forte: {abs_growth_fmt} de queda. Priorize retenção de clientes.",
        "Receita despencou {abs_growth_fmt} — investigar causas e reverter com urgência.",
    ],
}

WEEKLY_CONCENTRATION = {
    "alta": [
        "Concentração crítica: {peak_day} responde por {peak_pct_fmt} da receita semanal.",
        "{peak_pct_fmt} da receita semanal vem de {peak_day} — risco de dependência.",
        "Dependência de {peak_day}: {peak_pct_fmt} da receita semanal em um único dia.",
    ],
    "moderada": [
        "Concentração moderada em {peak_day} ({peak_pct_fmt} da receita semanal).",
        "{peak_day} lidera com {peak_pct_fmt} da receita semanal — distribuição razoável.",
        "Pico em {peak_day} com {peak_pct_fmt} — oportunidade de equilibrar os demais dias.",
    ],
    "equilibrada": [
        "Distribuição equilibrada: nenhum dia passa de {peak_pct_fmt} da receita semanal.",
        "Receita bem distribuída na semana — pico de apenas {peak_pct_fmt} em {peak_day}.",
        "Equilíbrio semanal confirmado: {peak_day} lidera com apenas {peak_pct_fmt}.",
    ],
}

WEEKLY_WEAK_DAY = [
    "{weak_day} contribui com apenas {weak_pct_fmt} da receita — dia subutilizado.",
    "Queda em {weak_day}: apenas {weak_pct_fmt} da receita semanal. Considere promoções.",
    "{weak_day} é o ponto fraco da semana ({weak_pct_fmt} da receita).",
]

STRENGTHS_POOL = {
    "margin": [
        "Margem de {margin_fmt} acima da média do setor",
        "Controle de custos eficaz (margem {margin_fmt})",
        "Operação lucrativa com margem de {margin_fmt}",
    ],
    "low_risk": [
        "Apenas {high_pct_fmt} em alto risco segundo o ML",
        "Base sólida: {low_pct_fmt} em baixo risco",
        "Exposição controlada: {n_low} de {n} predições em baixo risco",
    ],
    "ticket": [
        "Ticket médio de {ticket_fmt} acima da média",
        "Poder de precificação confirmado ({ticket_fmt}/atendimento)",
        "Receita por cliente elevada: {ticket_fmt}",
    ],
    "volume": [
        "Base robusta de {n} registros",
        "Volume de {n} registros permite análises confiáveis",
        "Histórico consistente de {n} registros",
    ],
    "trend": [
        "Crescimento de {growth_fmt} no período",
        "Tendência positiva consistente ({growth_fmt})",
        "Momentum de alta: {growth_fmt} de crescimento",
    ],
    "distribution": [
        "Receita bem distribuída na semana",
        "Baixa dependência de um único dia",
        "Equilíbrio semanal com pico de {peak_pct_fmt}",
    ],
}

WEAKNESSES_POOL = {
    "margin": [
        "Margem de apenas {margin_fmt}",
        "Margem {margin_band_label} ({margin_fmt})",
        "Margem abaixo do ideal: {margin_fmt}",
    ],
    "high_risk": [
        "{high_pct_fmt} em alto risco (ML)",
        "Concentração de risco: {n_high} registros críticos",
        "Exposição elevada: {high_pct_fmt} em alto risco",
    ],
    "ticket": [
        "Ticket médio baixo ({ticket_fmt})",
        "Receita por atendimento abaixo do ideal ({ticket_fmt})",
        "Ticket de {ticket_fmt} limita o crescimento",
    ],
    "trend": [
        "Queda de {abs_growth_fmt} no período",
        "Tendência de baixa ({growth_fmt})",
        "Receita em retração ({abs_growth_fmt})",
    ],
    "concentration": [
        "{peak_pct_fmt} da receita semanal concentrada em {peak_day}",
        "Dependência de {peak_day} ({peak_pct_fmt})",
        "Alta concentração semanal em {peak_day}",
    ],
    "volatility": [
        "Volatilidade mensal de {cv_fmt}",
        "Receita imprevisível (CV={cv_fmt})",
        "Alta variação mensal ({cv_fmt})",
    ],
}

RECOMMENDATIONS_POOL = {
    "margin_negative": [
        "Revisar imediatamente a precificação: cada atendimento a {ticket_fmt} gera prejuízo de {loss_per_sale}.",
        "Cortar custos operacionais em pelo menos {cut_needed_pct} para reverter a margem de {margin_fmt}.",
        "Renegociar fornecedores e reavaliar mix de serviços: margem de {margin_fmt} é insustentável.",
    ],
    "margin_critical": [
        "Aumentar preço médio em {price_increase_pct} ou reduzir custo em {cost_cut_pct} para atingir margem saudável.",
        "Revisar contrato de fornecedores: a margem de {margin_fmt} precisa subir para pelo menos 20%.",
        "Focar em serviços de maior valor agregado para elevar a margem de {margin_fmt}.",
    ],
    "margin_low": [
        "Otimizar mix de serviços: ganho de {gap} na margem adiciona {additional_profit} ao lucro.",
        "Negociar com fornecedores: cada 1% de redução de custo adiciona {per_point} ao resultado.",
        "Aumentar ticket médio em 10% via up-sell para elevar margem de {margin_fmt}.",
    ],
    "margin_moderate": [
        "Explorar serviços premium para elevar margem de {margin_fmt} ao patamar saudável (30%+).",
        "Automatizar processos para reduzir custo fixo e ganhar {gap} de margem.",
        "Fidelizar clientes atuais: aumento de 5% na retenção eleva margem em ~2 p.p.",
    ],
    "margin_excellent": [
        "Reinvestir o lucro de {profit_fmt} em expansão ou reserva estratégica.",
        "Considerar aumento de capacidade para escalar a operação de alta margem ({margin_fmt}).",
        "Documentar práticas atuais como benchmark interno para outras unidades.",
    ],
    "risk_high": [
        "Priorizar os {n_high} registros em alto risco: ação preventiva sobre os {high_pct_fmt} críticos.",
        "Criar plano de mitigação focado nos {n_high} casos sinalizados pelo ML.",
        "Revisar processo operacional: {high_pct_fmt} dos registros em alto risco indica falha sistêmica.",
    ],
    "risk_moderate": [
        "Monitorar continuamente os {n_high} registros em alto risco ({high_pct_fmt}).",
        "Criar alertas automáticos para os casos com score > 0.7.",
        "Investigar correlação entre os {n_high} casos de alto risco para achar causa raiz.",
    ],
    "risk_low": [
        "Manter monitoramento padrão: risco controlado em {high_pct_fmt}.",
        "Aproveitar a base sólida para investir em crescimento.",
        "Documentar práticas que mantêm o risco baixo para replicar.",
    ],
    "ticket_low": [
        "Oferecer combos/up-sell: elevar ticket de {ticket_fmt} em 20% aumenta receita em {ticket_gain_20pct}.",
        "Treinar equipe em técnicas de venda adicional.",
        "Criar pacotes de serviços com preço premium.",
    ],
    "ticket_medium": [
        "Introduzir serviços premium para elevar o ticket médio acima de R$ 1.000,00.",
        "Oferecer planos de manutenção recorrente para estabilizar a receita.",
        "Investir em marketing de relacionamento para aumentar frequência de visita.",
    ],
    "trend_down": [
        "Investigar causa da queda de {abs_growth_fmt}: preço, demanda ou concorrência?",
        "Reforçar marketing para reverter tendência de baixa.",
        "Reativar clientes inativos para recuperar receita.",
    ],
    "trend_up": [
        "Preparar operação para absorver crescimento de {growth_fmt} — capacidade, equipe, estoque.",
        "Documentar o que gerou o crescimento para replicar.",
        "Considerar investimento em expansão aproveitando o momentum.",
    ],
    "concentration": [
        "Diversificar receita: reduzir dependência de {peak_day} ({peak_pct_fmt} da receita).",
        "Criar promoções em {weak_day} (apenas {weak_pct_fmt} da receita).",
        "Equilibrar demanda semanal com campanhas segmentadas por dia.",
    ],
    "volatility": [
        "Reduzir volatilidade de {cv_fmt} com contratos recorrentes ou assinaturas.",
        "Criar reserva de caixa para absorver meses fracos.",
        "Estabilizar receita com serviços recorrentes (manutenção preventiva).",
    ],
}


# ==============================================
# 🔥 MOTOR DE ANÁLISE INTELIGENTE DATA-DRIVEN (V7.0)
# ==============================================

class IntelligentAnalyzer:
    """
    🔥 V7.0 DATA-DRIVEN: cada frase usa métricas REAIS do arquivo + predições do ML.
    """

    MARGIN_CRITICAL = 10.0
    MARGIN_WARNING = 20.0
    MARGIN_GOOD = 30.0
    MARGIN_EXCELLENT = 45.0
    RISK_HIGH_THRESHOLD = 0.7
    RISK_LOW_THRESHOLD = 0.3

    # -------------- API PÚBLICA --------------

    @staticmethod
    def analyze_file(file_metrics: FileMetrics) -> Dict[str, Any]:
        ctx = IntelligentAnalyzer._build_context(file_metrics)
        seed = _seed_from(file_metrics.filename)

        insights: List[str] = []
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendations: List[Dict[str, Any]] = []

        IntelligentAnalyzer._fill_margin(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzer._fill_risk(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzer._fill_ticket(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzer._fill_volume(ctx, seed, insights, strengths)
        IntelligentAnalyzer._fill_trend(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzer._fill_weekly(ctx, seed, insights, strengths, weaknesses, recommendations)
        IntelligentAnalyzer._fill_volatility(ctx, seed, insights, weaknesses, recommendations)

        summary = IntelligentAnalyzer._build_file_summary(ctx)
        score = IntelligentAnalyzer._calculate_file_score(ctx)

        return {
            "insights": insights,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "metrics_extra": ctx,
            "summary": summary,
            "score": score,
        }

    @staticmethod
    def analyze_multiple_files(consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        files = consolidated.files
        if not files:
            return IntelligentAnalyzer._empty_analysis()

        per_file = {f.filename: IntelligentAnalyzer.analyze_file(f) for f in files}

        scores = [a["score"] for a in per_file.values()]
        avg_score = sum(scores) / len(scores) if scores else 5.0

        comparison_data = (
            IntelligentAnalyzer._compare_files(files, consolidated)
            if len(files) > 1 else {}
        )
        trend_data = IntelligentAnalyzer._aggregate_trend(files, consolidated)

        all_recommendations = []
        seen = set()
        for fname, analysis in per_file.items():
            for rec in analysis["recommendations"]:
                key = rec["description"][:80]
                if key in seen:
                    continue
                seen.add(key)
                rec_copy = dict(rec)
                if len(files) > 1:
                    rec_copy["source_file"] = fname
                all_recommendations.append(rec_copy)

        priority_order = {"alta": 0, "media": 1, "baixa": 2}
        all_recommendations.sort(
            key=lambda r: priority_order.get(r.get("priority", "media"), 1)
        )
        all_recommendations = all_recommendations[:10]

        executive_score = IntelligentAnalyzer._build_executive_score(
            consolidated, per_file, avg_score
        )
        executive_summary = IntelligentAnalyzer._build_executive_summary(
            consolidated, per_file, comparison_data
        )
        forecast = IntelligentAnalyzer._build_forecast(consolidated, trend_data)
        conclusion = IntelligentAnalyzer._build_conclusion(
            consolidated, per_file, avg_score
        )

        combined_insights = []
        for fname, analysis in per_file.items():
            for ins in analysis["insights"][:3]:
                combined_insights.append(f"[{fname}] {ins}" if len(files) > 1 else ins)

        return {
            "success": True,
            "executive_score": executive_score,
            "executive_summary": executive_summary,
            "comparison": comparison_data,
            "trend": trend_data,
            "recommendations": all_recommendations,
            "forecast": forecast,
            "conclusion": conclusion,
            "combined_insights": combined_insights[:12],
            "per_file_analysis": per_file,
            "model_used": "intelligent_fallback_v7",
            "tokens_used": 0,
            "response_time_ms": 0,
            "fallback_used": True,
            "full_analysis": executive_summary + "\n\n" + conclusion,
        }

    # -------------- CONTEXTO --------------

    @staticmethod
    def _build_context(f: FileMetrics) -> Dict[str, Any]:
        predictions = list(f.predictions or [])
        n = len(predictions)

        if predictions:
            avg_score = sum(predictions) / n
            high_risk = [p for p in predictions if p > 0.7]
            low_risk = [p for p in predictions if p < 0.3]
            n_high = len(high_risk)
            n_low = len(low_risk)
            high_pct = (n_high / n) * 100
            low_pct = (n_low / n) * 100
            variance = sum((p - avg_score) ** 2 for p in predictions) / n
            std_score = math.sqrt(variance)
        else:
            avg_score = 0.5; std_score = 0.0
            n_high = n_low = 0
            high_pct = low_pct = 0.0

        revenue = float(f.total_revenue or 0)
        cost = float(f.total_costs or 0)
        profit = float(f.profit or 0)
        margin = float(f.margin or 0)
        rows = int(f.total_rows or 0)

        ticket = _safe_div(revenue, rows, 0)
        cost_per_row = _safe_div(cost, rows, 0)
        profit_per_row = _safe_div(profit, rows, 0)

        chart = f.chart_data or {}
        monthly_rev = chart.get("monthly", {}).get("revenue", [])
        valid_months = [float(v) for v in monthly_rev if v and v > 0]
        growth = 0.0
        cv = 0.0
        if len(valid_months) >= 2:
            growth = _safe_div((valid_months[-1] - valid_months[0]) * 100, valid_months[0], 0)
        if len(valid_months) >= 3:
            mean_v = sum(valid_months) / len(valid_months)
            var = sum((v - mean_v) ** 2 for v in valid_months) / len(valid_months)
            std_v = math.sqrt(var)
            cv = _safe_div(std_v * 100, mean_v, 0)

        weekly_rev = chart.get("weekly", {}).get("revenue", [])
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        peak_day = weak_day = "-"
        peak_pct = weak_pct = 0.0
        if weekly_rev and sum(weekly_rev) > 0:
            total_week = sum(weekly_rev)
            max_i = max(range(len(weekly_rev)), key=lambda i: weekly_rev[i])
            min_i = min(range(len(weekly_rev)), key=lambda i: weekly_rev[i])
            peak_day = days[max_i] if max_i < len(days) else f"Dia {max_i+1}"
            weak_day = days[min_i] if min_i < len(days) else f"Dia {min_i+1}"
            peak_pct = weekly_rev[max_i] / total_week * 100
            weak_pct = weekly_rev[min_i] / total_week * 100

        # Derivados
        margin_gap = max(0.0, 30 - margin) if margin < 30 else 0.0
        per_point_margin = revenue * 0.01 if revenue else 0
        loss_per_sale = max(0.0, cost_per_row - ticket)
        abs_profit = abs(profit)
        price_increase_pct = 0.0
        cut_needed_pct = 0.0
        if revenue > 0 and profit < 0:
            price_increase_pct = abs(profit) / revenue * 100
            cut_needed_pct = price_increase_pct
        cost_cut_pct = 0.0
        if revenue > 0:
            cost_cut_pct = max(0.0, (cost / revenue * 100) - 70)  # p/ 30% margem
        additional_profit = revenue * 0.10
        ticket_gain_20pct = ticket * 0.20 * rows
        n_for_10k = int(10000 / ticket) if ticket > 0 else 0

        # Label da banda de margem (para weakness)
        band_labels = {
            MarginBand.NEGATIVE: "negativa",
            MarginBand.CRITICAL: "crítica",
            MarginBand.LOW: "baixa",
            MarginBand.MODERATE: "moderada",
            MarginBand.HEALTHY: "saudável",
            MarginBand.EXCELLENT: "excelente",
        }

        return {
            "filename": f.filename,
            "rows": rows,
            "n": n,
            "revenue": revenue,
            "revenue_fmt": _fmt_brl(revenue),
            "cost": cost,
            "cost_fmt": _fmt_brl(cost),
            "profit": profit,
            "profit_fmt": _fmt_brl(profit),
            "abs_profit_fmt": _fmt_brl(abs_profit),
            "margin": margin,
            "margin_fmt": _fmt_pct(margin),
            "ticket": ticket,
            "ticket_fmt": _fmt_brl(ticket),
            "cost_per_row": cost_per_row,
            "profit_per_row": profit_per_row,

            "avg_score": avg_score,
            "std_score": std_score,
            "high_pct": high_pct,
            "high_pct_fmt": _fmt_pct(high_pct),
            "low_pct": low_pct,
            "low_pct_fmt": _fmt_pct(low_pct),
            "n_high": n_high,
            "n_low": n_low,

            "growth": growth,
            "growth_fmt": _fmt_pct(growth),
            "abs_growth": abs(growth),
            "abs_growth_fmt": _fmt_pct(abs(growth)),
            "cv": cv,
            "cv_fmt": _fmt_pct(cv),

            "peak_day": peak_day,
            "peak_pct": peak_pct,
            "peak_pct_fmt": _fmt_pct(peak_pct),
            "weak_day": weak_day,
            "weak_pct": weak_pct,
            "weak_pct_fmt": _fmt_pct(weak_pct),

            "gap": _fmt_pct(margin_gap, 1),
            "gap_num": margin_gap,
            "per_point": _fmt_brl(per_point_margin),
            "loss_per_sale": _fmt_brl(loss_per_sale),
            "price_increase_pct": _fmt_pct(price_increase_pct),
            "cost_cut_pct": _fmt_pct(cost_cut_pct),
            "cut_needed_pct": _fmt_pct(cut_needed_pct),
            "additional_profit": _fmt_brl(additional_profit),
            "ticket_gain_20pct": _fmt_brl(ticket_gain_20pct),
            "n_for_10k": n_for_10k,
            "margin_band_label": band_labels.get(MarginBand.of(margin), "moderada"),

            "margin_band": MarginBand.of(margin),
            "risk_band": RiskBand.of(high_pct),
            "ticket_band": TicketBand.of(ticket),
            "volume_band": VolumeBand.of(rows),
            "trend_band": TrendBand.of(growth),
        }

    # -------------- FILLERS --------------

    @staticmethod
    def _safe_format(template: str, ctx: Dict[str, Any]) -> str:
        try:
            return template.format(**ctx)
        except (KeyError, IndexError):
            return template

    @staticmethod
    def _fill_margin(ctx, seed, insights, strengths, weaknesses, recommendations):
        band = ctx["margin_band"]
        pool = MARGIN_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzer._safe_format(_pick(pool, seed), ctx))

        if band == MarginBand.NEGATIVE:
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["margin"], seed), ctx))
            recommendations.append({
                "priority": "alta", "category": "financeiro",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_negative"], seed), ctx),
                "expected_impact": "Crítico", "effort": "alto",
            })
        elif band == MarginBand.CRITICAL:
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["margin"], seed), ctx))
            recommendations.append({
                "priority": "alta", "category": "financeiro",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_critical"], seed), ctx),
                "expected_impact": "Alto", "effort": "alto",
            })
        elif band == MarginBand.LOW:
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["margin"], seed), ctx))
            recommendations.append({
                "priority": "media", "category": "financeiro",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_low"], seed), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })
        elif band == MarginBand.MODERATE:
            recommendations.append({
                "priority": "media", "category": "financeiro",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["margin_moderate"], seed), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })
        elif band in (MarginBand.HEALTHY, MarginBand.EXCELLENT):
            strengths.append(IntelligentAnalyzer._safe_format(
                _pick(STRENGTHS_POOL["margin"], seed), ctx))
            if band == MarginBand.EXCELLENT:
                recommendations.append({
                    "priority": "baixa", "category": "financeiro",
                    "description": IntelligentAnalyzer._safe_format(
                        _pick(RECOMMENDATIONS_POOL["margin_excellent"], seed), ctx),
                    "expected_impact": "Alto", "effort": "baixo",
                })

    @staticmethod
    def _fill_risk(ctx, seed, insights, strengths, weaknesses, recommendations):
        if ctx["n"] == 0:
            return
        band = ctx["risk_band"]
        pool = RISK_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzer._safe_format(_pick(pool, seed + 1), ctx))

        if band == RiskBand.LOW:
            strengths.append(IntelligentAnalyzer._safe_format(
                _pick(STRENGTHS_POOL["low_risk"], seed + 1), ctx))
            recommendations.append({
                "priority": "baixa", "category": "operacional",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["risk_low"], seed + 1), ctx),
                "expected_impact": "Baixo", "effort": "baixo",
            })
        elif band == RiskBand.MODERATE:
            recommendations.append({
                "priority": "media", "category": "operacional",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["risk_moderate"], seed + 1), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })
        elif band in (RiskBand.HIGH, RiskBand.CRITICAL):
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["high_risk"], seed + 1), ctx))
            recommendations.append({
                "priority": "alta", "category": "operacional",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["risk_high"], seed + 2), ctx),
                "expected_impact": "Alto", "effort": "alto",
            })

    @staticmethod
    def _fill_ticket(ctx, seed, insights, strengths, weaknesses, recommendations):
        band = ctx["ticket_band"]
        pool = TICKET_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzer._safe_format(_pick(pool, seed + 2), ctx))

        if band in (TicketBand.HIGH, TicketBand.PREMIUM):
            strengths.append(IntelligentAnalyzer._safe_format(
                _pick(STRENGTHS_POOL["ticket"], seed + 2), ctx))
        elif band == TicketBand.LOW:
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["ticket"], seed + 2), ctx))
            recommendations.append({
                "priority": "media", "category": "comercial",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["ticket_low"], seed + 2), ctx),
                "expected_impact": "Médio", "effort": "baixo",
            })
        elif band == TicketBand.MEDIUM:
            recommendations.append({
                "priority": "baixa", "category": "comercial",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["ticket_medium"], seed + 3), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })

    @staticmethod
    def _fill_volume(ctx, seed, insights, strengths):
        band = ctx["volume_band"]
        pool = VOLUME_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzer._safe_format(_pick(pool, seed + 3), ctx))
        if band in (VolumeBand.HIGH, VolumeBand.VERY_HIGH):
            strengths.append(IntelligentAnalyzer._safe_format(
                _pick(STRENGTHS_POOL["volume"], seed + 3), ctx))

    @staticmethod
    def _fill_trend(ctx, seed, insights, strengths, weaknesses, recommendations):
        if not ctx.get("growth"):
            return
        band = ctx["trend_band"]
        pool = TREND_INSIGHTS.get(band, [])
        if pool:
            insights.append(IntelligentAnalyzer._safe_format(_pick(pool, seed + 4), ctx))

        if band in (TrendBand.STRONG_UP, TrendBand.UP):
            strengths.append(IntelligentAnalyzer._safe_format(
                _pick(STRENGTHS_POOL["trend"], seed + 4), ctx))
            recommendations.append({
                "priority": "baixa", "category": "operacional",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["trend_up"], seed + 4), ctx),
                "expected_impact": "Alto", "effort": "medio",
            })
        elif band in (TrendBand.DOWN, TrendBand.STRONG_DOWN):
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["trend"], seed + 4), ctx))
            recommendations.append({
                "priority": "alta", "category": "operacional",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["trend_down"], seed + 5), ctx),
                "expected_impact": "Alto", "effort": "alto",
            })

    @staticmethod
    def _fill_weekly(ctx, seed, insights, strengths, weaknesses, recommendations):
        if ctx.get("peak_day") in (None, "-") or not ctx.get("peak_pct"):
            return
        peak_pct = ctx["peak_pct"]

        if peak_pct > 40:
            conc = "alta"
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["concentration"], seed + 5), ctx))
        elif peak_pct > 25:
            conc = "moderada"
        else:
            conc = "equilibrada"
            strengths.append(IntelligentAnalyzer._safe_format(
                _pick(STRENGTHS_POOL["distribution"], seed + 5), ctx))

        pool = WEEKLY_CONCENTRATION.get(conc, [])
        if pool:
            insights.append(IntelligentAnalyzer._safe_format(_pick(pool, seed + 5), ctx))

        if 0 < ctx["weak_pct"] < 5:
            insights.append(IntelligentAnalyzer._safe_format(
                _pick(WEEKLY_WEAK_DAY, seed + 6), ctx))

        if conc == "alta":
            recommendations.append({
                "priority": "media", "category": "operacional",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["concentration"], seed + 6), ctx),
                "expected_impact": "Médio", "effort": "medio",
            })

    @staticmethod
    def _fill_volatility(ctx, seed, insights, weaknesses, recommendations):
        cv = ctx.get("cv", 0)
        if cv and cv > 50:
            weaknesses.append(IntelligentAnalyzer._safe_format(
                _pick(WEAKNESSES_POOL["volatility"], seed + 7), ctx))
            recommendations.append({
                "priority": "media", "category": "financeiro",
                "description": IntelligentAnalyzer._safe_format(
                    _pick(RECOMMENDATIONS_POOL["volatility"], seed + 7), ctx),
                "expected_impact": "Médio", "effort": "alto",
            })

    # -------------- SUMÁRIO --------------

    @staticmethod
    def _build_file_summary(ctx: Dict[str, Any]) -> str:
        parts = []
        parts.append(
            f"O arquivo '{ctx['filename']}' contém {ctx['rows']} registros "
            f"com receita total de {ctx['revenue_fmt']} e lucro de {ctx['profit_fmt']}."
        )

        margin_desc = {
            MarginBand.NEGATIVE: f"A margem negativa de {ctx['margin_fmt']} exige ação corretiva imediata.",
            MarginBand.CRITICAL: f"A margem crítica de {ctx['margin_fmt']} está bem abaixo do ideal.",
            MarginBand.LOW: f"A margem de {ctx['margin_fmt']} está abaixo do esperado para o setor.",
            MarginBand.MODERATE: f"A margem de {ctx['margin_fmt']} é aceitável, com espaço para otimização.",
            MarginBand.HEALTHY: f"A margem saudável de {ctx['margin_fmt']} indica boa gestão financeira.",
            MarginBand.EXCELLENT: f"A margem excelente de {ctx['margin_fmt']} demonstra performance superior.",
        }
        parts.append(margin_desc.get(ctx["margin_band"], ""))

        vol_desc = {
            VolumeBand.LOW: "O volume de dados é baixo, o que pode limitar a precisão.",
            VolumeBand.MEDIUM: "O volume de dados é adequado para análises confiáveis.",
            VolumeBand.HIGH: "O volume de dados é robusto, permitindo análises sólidas.",
            VolumeBand.VERY_HIGH: "O volume de dados é muito alto, ideal para modelagem avançada.",
        }
        parts.append(vol_desc.get(ctx["volume_band"], ""))

        if ctx["n"] > 0:
            if ctx["high_pct"] > 50:
                parts.append(f"Preocupação: {ctx['high_pct_fmt']} dos registros são de alto risco pelo ML.")
            elif ctx["high_pct"] < 15:
                parts.append(f"Base sólida: apenas {ctx['high_pct_fmt']} em alto risco.")

        if ctx["peak_pct"] > 35 and ctx["peak_day"] != "-":
            parts.append(f"Concentração em {ctx['peak_day']} ({ctx['peak_pct_fmt']} da receita semanal).")

        if ctx["growth"] > 15:
            parts.append(f"Tendência mensal positiva (+{ctx['growth_fmt']}).")
        elif ctx["growth"] < -15:
            parts.append(f"Tendência mensal negativa ({ctx['growth_fmt']}).")

        return " ".join(p for p in parts if p)

    # -------------- SCORE --------------

    @staticmethod
    def _calculate_file_score(ctx: Dict[str, Any]) -> float:
        score = 5.0
        margin = ctx["margin"]
        if margin >= 45: score += 3.0
        elif margin >= 30: score += 2.0
        elif margin >= 20: score += 1.0
        elif margin >= 10: score += 0.0
        elif margin >= 0: score -= 1.5
        else: score -= 3.0

        high_pct = ctx["high_pct"]
        if high_pct < 15: score += 2.0
        elif high_pct < 30: score += 1.0
        elif high_pct < 50: score -= 1.0
        else: score -= 2.0

        growth = ctx["growth"]
        if growth > 20: score += 1.5
        elif growth > 5: score += 0.75
        elif growth < -20: score -= 1.5
        elif growth < -5: score -= 0.75

        cv = ctx["cv"]
        if cv and cv < 20: score += 1.0
        elif cv and cv < 40: score += 0.5
        elif cv and cv > 60: score -= 1.0

        return max(0.0, min(10.0, score))

    # -------------- COMPARAÇÃO --------------

    @staticmethod
    def _compare_files(files: List[FileMetrics], consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        if len(files) < 2:
            return {}

        by_revenue = sorted(files, key=lambda f: f.total_revenue, reverse=True)
        by_profit = sorted(files, key=lambda f: f.profit, reverse=True)
        by_margin = sorted(files, key=lambda f: f.margin, reverse=True)
        by_risk = sorted(files, key=lambda f: f.high_risk_percentage)

        parts = []
        best = by_revenue[0]; worst = by_revenue[-1]
        diff_pct = _safe_div(
            (best.total_revenue - worst.total_revenue) * 100,
            worst.total_revenue, 0,
        )
        parts.append(
            f"'{best.filename}' lidera com {_fmt_brl(best.total_revenue)} "
            f"({_fmt_pct(diff_pct)} acima de '{worst.filename}')."
        )
        riskiest = max(files, key=lambda f: f.high_risk_percentage)
        if riskiest.high_risk_percentage > 30:
            parts.append(
                f"'{riskiest.filename}' tem {_fmt_pct(riskiest.high_risk_percentage)} de alto risco."
            )
        best_margin = by_margin[0]
        parts.append(f"Melhor margem: '{best_margin.filename}' com {_fmt_pct(best_margin.margin)}.")

        return {
            "best_revenue": by_revenue[0].filename if by_revenue else "",
            "best_profit": by_profit[0].filename if by_profit else "",
            "best_growth": by_margin[0].filename if by_margin else "",
            "best_efficiency": by_margin[0].filename if by_margin else "",
            "highest_risk": riskiest.filename if riskiest else "",
            "lowest_performance": by_revenue[-1].filename if by_revenue else "",
            "summary": " ".join(parts),
            "ranking_revenue": [f.filename for f in by_revenue],
            "ranking_profit": [f.filename for f in by_profit],
            "ranking_margin": [f.filename for f in by_margin],
        }

    @staticmethod
    def _aggregate_trend(files: List[FileMetrics], consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        if len(files) < 2:
            return {
                "direction": "estavel", "strength": 0.5, "confidence": 0.5,
                "description": "Dados insuficientes para análise de tendência.",
                "key_observations": [],
            }
        sorted_files = sorted(files, key=lambda f: f.filename)
        revenues = [f.total_revenue for f in sorted_files]
        growth = _safe_div((revenues[-1] - revenues[0]) * 100, revenues[0], 0) if revenues[0] > 0 else 0

        if growth > 10:
            return {
                "direction": "crescente", "strength": round(min(1.0, growth / 50), 2),
                "confidence": 0.75,
                "description": f"Tendência de crescimento de {_fmt_pct(growth)} entre os arquivos.",
                "key_observations": [f"Receita cresceu {_fmt_pct(growth)}"],
            }
        elif growth < -10:
            return {
                "direction": "decrescente", "strength": round(min(1.0, abs(growth) / 50), 2),
                "confidence": 0.75,
                "description": f"Tendência de queda de {_fmt_pct(abs(growth))} entre os arquivos.",
                "key_observations": [f"Receita caiu {_fmt_pct(abs(growth))}"],
            }
        else:
            return {
                "direction": "estavel", "strength": 0.5, "confidence": 0.75,
                "description": f"Estabilidade no período (variação de {_fmt_pct(growth)}).",
                "key_observations": ["Receita estável"],
            }

    # -------------- EXECUTIVE --------------

    @staticmethod
    def _build_executive_score(consolidated, per_file, avg_score):
        margin = consolidated.avg_margin
        if margin < 0: saude = 1.0
        elif margin < 10: saude = 3.0
        elif margin < 20: saude = 5.0
        elif margin < 30: saude = 7.0
        elif margin < 45: saude = 8.5
        else: saude = 10.0

        eficiencia = min(10.0, avg_score)

        if consolidated.total_revenue > 0:
            cost_ratio = (consolidated.total_revenue - consolidated.total_profit) / consolidated.total_revenue
            if cost_ratio < 0.5: controle = 9.0
            elif cost_ratio < 0.65: controle = 7.0
            elif cost_ratio < 0.8: controle = 5.0
            elif cost_ratio < 0.95: controle = 3.0
            else: controle = 1.0
        else:
            controle = 5.0

        growth = 5.0
        nivel = "Moderado"
        if consolidated.ml_results and consolidated.ml_results.total_predictions > 0:
            high_risk = consolidated.ml_results.risk_distribution.get("alto", 0)
            if high_risk < 15: growth = 8.0; nivel = "Baixo"
            elif high_risk < 30: growth = 6.0; nivel = "Moderado"
            elif high_risk < 50: growth = 4.0; nivel = "Moderado"
            else: growth = 2.0; nivel = "Alto"

        nota_geral = (saude + eficiencia + controle + growth) / 4
        return {
            "saude_financeira": round(saude, 1),
            "eficiencia": round(eficiencia, 1),
            "controle_custos": round(controle, 1),
            "crescimento": round(growth, 1),
            "nivel_risco": nivel,
            "nota_geral": round(nota_geral, 1),
        }

    @staticmethod
    def _build_executive_summary(consolidated, per_file, comparison_data):
        parts = []
        n_files = consolidated.processed_files
        total_rows = sum(f.total_rows for f in consolidated.files)

        if n_files == 1:
            parts.append(f"Análise completa de '{consolidated.files[0].filename}' com {total_rows} registros.")
        else:
            parts.append(f"Análise comparativa de {n_files} arquivos com {total_rows} registros no total.")

        parts.append(
            f"Receita total de {_fmt_brl(consolidated.total_revenue)}, "
            f"lucro de {_fmt_brl(consolidated.total_profit)} "
            f"e margem média de {_fmt_pct(consolidated.avg_margin)}."
        )

        margin = consolidated.avg_margin
        if margin >= 45: parts.append("A margem está em nível excelente, acima da média do setor.")
        elif margin >= 30: parts.append("A margem é saudável e sustentável.")
        elif margin >= 20: parts.append("A margem é aceitável, mas há espaço para otimização.")
        elif margin >= 10: parts.append("A margem é baixa — atenção aos custos operacionais.")
        elif margin >= 0: parts.append("A margem é crítica — ação corretiva necessária.")
        else: parts.append("A operação está em prejuízo — intervenção imediata requerida.")

        if comparison_data and comparison_data.get("summary"):
            parts.append(comparison_data["summary"])

        if consolidated.ml_results:
            high = consolidated.ml_results.risk_distribution.get("alto", 0)
            if high > 40:
                parts.append(f"Alerta: {_fmt_pct(high)} dos registros em alto risco pelo ML.")
            elif high < 15:
                parts.append(f"Base sólida: apenas {_fmt_pct(high)} em alto risco.")

        return " ".join(parts)

    @staticmethod
    def _build_forecast(consolidated, trend):
        margin = consolidated.avg_margin
        direction = trend.get("direction", "estavel")

        if margin >= 30 and direction == "crescente":
            return ("Cenário otimista: com margem saudável e tendência de crescimento, "
                    "espera-se expansão sustentada. Prepare a estrutura para absorver aumento de demanda.")
        elif margin >= 20 and direction == "crescente":
            return ("Cenário positivo: margem aceitável combinada com crescimento. "
                    "Mantenha o foco em eficiência para consolidar a expansão.")
        elif margin >= 30 and direction == "estavel":
            return ("Cenário estável: margem saudável com receita consistente. "
                    "Boa base para investimentos em crescimento planejado.")
        elif margin < 10 and direction == "decrescente":
            return ("Cenário de atenção: margem baixa com tendência de queda. "
                    "Ação corretiva urgente para reverter o quadro.")
        elif margin < 20 and direction == "decrescente":
            return ("Cenário de cautela: margem sob pressão e receita em queda. "
                    "Revisar precificação e estrutura de custos.")
        elif margin < 10:
            return ("Cenário crítico: margem baixa exige intervenção. "
                    "Priorizar corte de custos e renegociação com fornecedores.")
        else:
            return ("Cenário neutro: indicadores estáveis. "
                    "Manter monitoramento contínuo e buscar oportunidades de otimização.")

    @staticmethod
    def _build_conclusion(consolidated, per_file, avg_score):
        parts = []
        if avg_score >= 8: parts.append(f"Desempenho geral excelente (score {avg_score:.1f}/10).")
        elif avg_score >= 6: parts.append(f"Desempenho geral bom (score {avg_score:.1f}/10).")
        elif avg_score >= 4: parts.append(f"Desempenho geral regular (score {avg_score:.1f}/10).")
        else: parts.append(f"Desempenho geral abaixo do esperado (score {avg_score:.1f}/10).")

        if len(per_file) > 1:
            scores = {name: a["score"] for name, a in per_file.items()}
            best = max(scores.items(), key=lambda x: x[1])
            worst = min(scores.items(), key=lambda x: x[1])
            parts.append(f"Melhor desempenho: '{best[0]}' ({best[1]:.1f}/10). "
                         f"Ponto de atenção: '{worst[0]}' ({worst[1]:.1f}/10).")
        elif len(per_file) == 1:
            name, analysis = list(per_file.items())[0]
            parts.append(f"Score do arquivo: {analysis['score']:.1f}/10.")
            if analysis["strengths"]:
                parts.append(f"Principais forças: {'; '.join(analysis['strengths'][:2])}.")
            if analysis["weaknesses"]:
                parts.append(f"Principais fragilidades: {'; '.join(analysis['weaknesses'][:2])}.")

        return " ".join(parts)

    @staticmethod
    def _empty_analysis():
        return {
            "success": False,
            "executive_score": {
                "saude_financeira": 5.0, "eficiencia": 5.0,
                "controle_custos": 5.0, "crescimento": 5.0,
                "nivel_risco": "Moderado", "nota_geral": 5.0,
            },
            "executive_summary": "Análise indisponível.",
            "comparison": {},
            "trend": {
                "direction": "estavel", "strength": 0.5, "confidence": 0.5,
                "description": "Sem dados.", "key_observations": [],
            },
            "recommendations": [],
            "forecast": "Sem dados suficientes para previsão.",
            "conclusion": "Análise não pôde ser concluída.",
            "combined_insights": [],
            "per_file_analysis": {},
            "model_used": "intelligent_fallback_v7",
            "tokens_used": 0, "response_time_ms": 0,
            "fallback_used": True,
            "full_analysis": "Análise indisponível.",
        }


# ==============================================
# CLASSE PRINCIPAL - ANALISADOR V7.0
# ==============================================

class MultiFileAnalyzerV6:
    """
    🔥 Analisador de múltiplos arquivos - V7.0
    Com GEMINI DINÂMICO + CIRCUIT BREAKER + FALLBACK DATA-DRIVEN.

    ⚠️ IMPORTANTE: O Gemini é SEMPRE chamado primeiro.
    O fallback só entra em ação se o Gemini falhar/estiver indisponível.
    """

    MAX_FILES = 3
    CACHE_TTL = 300
    MAX_CONCURRENT = 3
    TIMEOUT_SECONDS = 60
    NORMALIZATION = "Z-Score"

    GEMINI_CHECK_TTL = 10.0
    GEMINI_CIRCUIT_THRESHOLD = 3
    GEMINI_CIRCUIT_COOLDOWN = 30.0

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT)
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        self._cache: Dict[str, Tuple[Dict[str, Any], float, int]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        self._chart_cache: Dict[str, Dict[str, Any]] = {}
        self._chart_cache_ttl = 300

        self.gemini = None
        self.is_gemini_available = False
        self._gemini_last_check = 0.0
        self._gemini_last_result = False
        self._gemini_lock = asyncio.Lock()

        self._gemini_circuit_state = CircuitState.CLOSED
        self._gemini_failure_count = 0
        self._gemini_circuit_opened_at = 0.0
        self._gemini_last_error: Optional[str] = None

        self._stats = {
            "total_analyses": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_processing_time_ms": 0,
            "avg_processing_time_ms": 0,
            "successful_analyses": 0,
            "failed_analyses": 0,
            "started_at": datetime.now().isoformat(),
            "last_analysis_at": None,
            "files_processed_total": 0,
            "errors_total": 0,
            "feature_adaptations": 0,
            "normalizations_applied": 0,
            "gemini_errors": 0,
            "gemini_timeouts": 0,
            "fallback_used_count": 0,
            "gemini_check_calls": 0,
            "gemini_revalidations_success": 0,
            "gemini_revalidations_failed": 0,
            "gemini_circuit_opens": 0,
            "gemini_last_check_at": None,
        }

        self.pipeline = None
        self.process_file = None
        self.predictor = None

        self._progress_callback: Optional[Callable] = None
        self._db_session = None
        self._process_id = None

        self._load_dependencies()
        self._load_predictor()

        logger.info("=" * 60)
        logger.info("✅ MultiFileAnalyzerV7.0 inicializado (FALLBACK DATA-DRIVEN)")
        logger.info("=" * 60)
        logger.info(f"   📁 Máximo de arquivos: {self.MAX_FILES}")
        logger.info(f"   💾 Cache TTL: {self.CACHE_TTL}s")
        logger.info(f"   🔄 Processamento paralelo: {self.MAX_CONCURRENT}")
        logger.info(f"   📊 Normalização: {self.NORMALIZATION}")
        logger.info(f"   🔥 Predictor V7.0: {'✅' if self.predictor else '❌'}")
        logger.info(f"   🤖 Gemini: {'✅' if self.is_gemini_available else '⚠️'}")
        logger.info(f"   🎯 Fallback: DATA-DRIVEN (frases com números reais)")
        logger.info("=" * 60)

    # ==========================================
    # 🔄 GEMINI: DINÂMICO + CIRCUIT BREAKER
    # ==========================================

    def _load_dependencies(self):
        try:
            from backend.preprocessing import pipeline, process_file_content
            self.pipeline = pipeline
            self.process_file = process_file_content
            logger.info("   ✅ ML Pipeline carregado")
        except ImportError:
            logger.exception("   ⚠️ ML Pipeline não disponível")
            self.pipeline = None
            self.process_file = None

        try:
            from backend.gemini import get_gemini_service
            self.gemini = get_gemini_service()
            try:
                self.is_gemini_available = self._gemini_check_impl()
            except Exception:
                logger.exception("   ⚠️ Erro no health check inicial do Gemini")
                self.is_gemini_available = False
        except ImportError:
            logger.exception("   ⚠️ Módulo Gemini não importável (usará fallback)")
            self.gemini = None
            self.is_gemini_available = False
        except Exception:
            logger.exception("   ⚠️ Erro inesperado ao carregar Gemini")
            self.gemini = None
            self.is_gemini_available = False

    def _load_predictor(self):
        try:
            from backend.ml.predict import predictor
            self.predictor = predictor
            logger.info("   ✅ Predictor V7.0 carregado")
            if hasattr(predictor, 'load_model_intelligently'):
                predictor.load_model_intelligently()
                logger.info("   ✅ Modelo carregado pelo predictor")
        except ImportError:
            logger.exception("   ⚠️ Predictor V7.0 não disponível")
            self.predictor = None

    def _circuit_is_open(self) -> bool:
        if self._gemini_circuit_state != CircuitState.OPEN:
            return False
        if (time.time() - self._gemini_circuit_opened_at) >= self.GEMINI_CIRCUIT_COOLDOWN:
            self._gemini_circuit_state = CircuitState.HALF_OPEN
            logger.info("🛡️  Circuit breaker Gemini → HALF_OPEN (testando recuperação)")
            return False
        return True

    def _mark_gemini_failure(self, exc: Optional[Exception] = None):
        self._gemini_failure_count += 1
        self._gemini_last_error = str(exc) if exc else None
        self._stats["gemini_errors"] += 1

        if self._gemini_circuit_state == CircuitState.HALF_OPEN:
            self._gemini_circuit_state = CircuitState.OPEN
            self._gemini_circuit_opened_at = time.time()
            self._stats["gemini_circuit_opens"] += 1
            logger.warning("🛡️  Circuit breaker Gemini → OPEN (falhou em HALF_OPEN)")
        elif self._gemini_failure_count >= self.GEMINI_CIRCUIT_THRESHOLD:
            self._gemini_circuit_state = CircuitState.OPEN
            self._gemini_circuit_opened_at = time.time()
            self._stats["gemini_circuit_opens"] += 1
            logger.warning(
                f"🛡️  Circuit breaker Gemini → OPEN "
                f"({self._gemini_failure_count} falhas consecutivas)"
            )

    def _mark_gemini_success(self):
        if self._gemini_circuit_state == CircuitState.HALF_OPEN:
            logger.info("🛡️  Circuit breaker Gemini → CLOSED (recuperado)")
        self._gemini_circuit_state = CircuitState.CLOSED
        self._gemini_failure_count = 0
        self._gemini_last_error = None

    def _reset_gemini_circuit(self):
        self._gemini_circuit_state = CircuitState.CLOSED
        self._gemini_failure_count = 0
        self._gemini_circuit_opened_at = 0.0
        self._gemini_last_error = None
        self._gemini_last_check = 0.0
        self._gemini_last_result = False
        logger.info("🛡️  Circuit breaker Gemini resetado manualmente")

    def _gemini_check_impl(self) -> bool:
        try:
            from backend.gemini import get_gemini_service, is_gemini_available as gemini_available_fn

            service = get_gemini_service()
            if service is None:
                logger.debug("Gemini service indisponível (None)")
                return False

            if not gemini_available_fn():
                logger.debug("Gemini reportado como indisponível pela factory")
                return False

            if hasattr(service, 'is_healthy'):
                try:
                    if not service.is_healthy():
                        logger.debug("Gemini health check falhou")
                        return False
                except Exception:
                    logger.exception("Erro no health check do Gemini")
                    return False

            self.gemini = service
            return True

        except ImportError:
            logger.debug("Módulo Gemini não importável")
            return False
        except Exception:
            logger.exception("Erro ao verificar disponibilidade do Gemini")
            return False

    def _gemini_is_ready(self, force: bool = False) -> bool:
        self._stats["gemini_check_calls"] += 1

        if self._circuit_is_open():
            self.is_gemini_available = False
            self._gemini_last_result = False
            return False

        now = time.time()
        if not force and (now - self._gemini_last_check) < self.GEMINI_CHECK_TTL:
            return self._gemini_last_result

        result = self._gemini_check_impl()
        self._gemini_last_check = now
        self._gemini_last_result = result
        self.is_gemini_available = result
        self._stats["gemini_last_check_at"] = datetime.now().isoformat()

        if result:
            self._stats["gemini_revalidations_success"] += 1
            self._mark_gemini_success()
        else:
            self._stats["gemini_revalidations_failed"] += 1
            self._mark_gemini_failure(None)

        return result

    def invalidate_gemini_cache(self):
        self._gemini_last_check = 0.0

    # ==========================================
    # PROGRESS / SETUP
    # ==========================================

    def set_progress_callback(self, callback: Callable[[float, str], None]):
        self._progress_callback = callback

    def set_db_session(self, db_session, process_id: int):
        self._db_session = db_session
        self._process_id = process_id

    async def _update_progress(self, progress: float, status: str):
        if self._progress_callback:
            try:
                await self._progress_callback(progress, status)
            except Exception:
                logger.exception("⚠️ Erro no progress callback")

        if self._db_session and self._process_id:
            try:
                from backend import models
                analysis = self._db_session.query(models.Analysis).filter(
                    models.Analysis.id == self._process_id
                ).first()
                if analysis:
                    analysis.progress = int(progress * 100)
                    analysis.progress_message = status
                    self._db_session.commit()
            except Exception:
                logger.exception("⚠️ Erro ao salvar progresso")

    def normalize_data(self, X: np.ndarray) -> np.ndarray:
        try:
            scaler = StandardScaler()
            X_normalized = scaler.fit_transform(X)
            self._stats['normalizations_applied'] += 1
            return X_normalized
        except Exception:
            logger.exception("⚠️ Erro na normalização")
            return X

    # ==========================================
    # ANÁLISE PRINCIPAL
    # ==========================================

    @timing_decorator
    async def analyze_multiple_files(
        self,
        files: List[Dict[str, Any]],
        user_id: int = None,
        user_email: str = None,
        force_reload: bool = False,
        progress_callback: Optional[Callable] = None,
        db_session=None,
        process_id: int = None,
        normalize: bool = True,
    ) -> MultiFileAnalysisResult:
        start_time = time.time()

        if db_session and process_id:
            self.set_db_session(db_session, process_id)
        if progress_callback:
            self.set_progress_callback(progress_callback)

        await self._update_progress(0.05, "Validando arquivos...")

        if not files:
            return self._error_result("Nenhum arquivo fornecido")
        if len(files) > self.MAX_FILES:
            return self._error_result(f"Máximo de {self.MAX_FILES} arquivos por vez")

        for i, file in enumerate(files):
            if not file.get('content'):
                return self._error_result(f"Arquivo {i+1} sem conteúdo")
            if not file.get('filename'):
                return self._error_result(f"Arquivo {i+1} sem nome")

        await self._update_progress(0.10, "Verificando cache...")

        cache_key = self._get_cache_key(files, user_id)
        if not force_reload:
            cached = self._get_cached_result(cache_key)
            if cached:
                logger.info("📦 Resultado em cache")
                self._cache_hits += 1
                self._stats["cache_hits"] += 1
                cached['cache_hit'] = True
                cached['status'] = AnalysisStatus.CACHED.value
                cached['progress'] = 1.0
                await self._update_progress(1.0, "Análise retornada do cache ✅")
                return MultiFileAnalysisResult(**cached)

        self._cache_misses += 1
        self._stats["cache_misses"] += 1

        logger.info(f"📚 Iniciando análise de {len(files)} arquivos")
        await self._update_progress(0.15, f"Processando {len(files)} arquivo(s)...")

        try:
            await self._update_progress(0.20, "Processando arquivos em paralelo...")
            processed_results = await self._process_files_parallel(
                files=files, user_id=user_id, normalize=normalize
            )
            success_count = sum(1 for r in processed_results if r.get('success'))
            await self._update_progress(
                0.30 + (success_count / len(files)) * 0.40,
                f"Processados {success_count}/{len(files)} arquivos"
            )
            await self._update_progress(0.70, "Consolidando dados...")

            consolidated = await self._build_consolidated_analysis(
                processed_results=processed_results,
                user_email=user_email, user_id=user_id, normalize=normalize
            )

            await self._update_progress(0.80, "Gerando análise com IA...")
            gemini_analysis = await self._generate_gemini_analysis(consolidated)
            await self._update_progress(0.95, "Finalizando relatório...")

            result = self._build_result(
                files=files, processed_results=processed_results,
                consolidated=consolidated, gemini_analysis=gemini_analysis,
                processing_time_ms=(time.time() - start_time) * 1000,
                normalize=normalize
            )

            self._set_cache(cache_key, result.to_dict())

            self._stats["total_analyses"] += 1
            self._stats["total_processing_time_ms"] += result.processing_time_ms
            self._stats["avg_processing_time_ms"] = (
                self._stats["total_processing_time_ms"] / self._stats["total_analyses"]
            )
            self._stats["successful_analyses"] += 1 if result.success else 0
            self._stats["failed_analyses"] += 1 if not result.success else 0
            self._stats["last_analysis_at"] = datetime.now().isoformat()
            self._stats["files_processed_total"] += result.processed_files

            if result.analysis_source == 'fallback_local':
                self._stats["fallback_used_count"] += 1

            logger.info(f"✅ Análise concluída em {result.processing_time_ms:.0f}ms")
            logger.info(f"   🤖 Fonte: {result.analysis_source}")

            await self._update_progress(1.0, "Análise concluída! ✅")
            return result

        except asyncio.CancelledError:
            logger.warning("⚠️ Análise cancelada")
            await self._update_progress(0, "Análise cancelada")
            return self._error_result("Análise cancelada pelo usuário")
        except Exception as e:
            logger.exception("❌ Erro na análise")
            self._stats["errors_total"] += 1
            await self._update_progress(0, f"Erro: {str(e)[:50]}")
            return self._error_result(str(e))
        finally:
            self._db_session = None
            self._process_id = None

    async def _process_files_parallel(
        self, files: List[Dict[str, Any]], user_id: int = None, normalize: bool = True
    ) -> List[Dict[str, Any]]:
        async def process_single_with_semaphore(file_data):
            async with self._semaphore:
                return await self._process_single_file(file_data, normalize=normalize)

        tasks = [process_single_with_semaphore(f) for f in files]

        total_timeout = min(self.TIMEOUT_SECONDS * len(files), self.TIMEOUT_SECONDS * 3)
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=total_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout no processamento ({total_timeout}s)")
            return [self._error_file_result(f.get('filename', 'unknown'), "Timeout") for f in files]

        processed = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.exception(f"Erro no arquivo {files[idx].get('filename')}: {result}")
                processed.append(self._error_file_result(
                    files[idx].get('filename', 'unknown'), str(result)
                ))
            else:
                processed.append(result)
        return processed

    async def _process_single_file(
        self, file_data: Dict[str, Any], normalize: bool = True
    ) -> Dict[str, Any]:
        filename = file_data.get('filename', 'arquivo.csv')
        content = file_data.get('content')
        file_start = time.time()

        if not content:
            return self._error_file_result(filename, "Arquivo vazio")
        if not self.process_file:
            return self._error_file_result(filename, "Pipeline ML não disponível")

        try:
            result = await asyncio.wait_for(
                self.process_file(
                    content=content, filename=filename,
                    db_session=self._db_session, process_id=self._process_id
                ),
                timeout=self.TIMEOUT_SECONDS
            )

            encoding_used = result.get('encoding_used')
            if not encoding_used:
                metadata = result.get('metadata', {})
                encoding_used = metadata.get('encoding_used', 'unknown')

            elapsed = (time.time() - file_start) * 1000
            logger.info(f"   📝 '{filename}' processado em {elapsed:.0f}ms")

            chart_data = result.get('chart_data', {})
            predictions = result.get('predictions', [])
            metrics = result.get('metrics', {})

            model_info = result.get('metadata', {})
            feature_count = model_info.get('feature_count', 0)
            model_used = result.get('model_used', 'default')

            return {
                'success': result.get('success', False),
                'filename': filename,
                'predictions': predictions,
                'metrics': metrics,
                'insights': result.get('insights', {}),
                'recommendations': result.get('recommendations', []),
                'chart_data': chart_data,
                'model_used': model_used,
                'encoding_used': encoding_used,
                'processed_rows': result.get('processed_rows', 0),
                'processing_time_ms': elapsed,
                'error': result.get('error'),
                'precision': 0.0, 'recall': 0.0, 'f1_score': 0.0, 'roc_auc': 0.0,
                'feature_count': feature_count,
                'normalization': self.NORMALIZATION if normalize else "None",
            }
        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout processando {filename}")
            return self._error_file_result(filename, f"Timeout ({self.TIMEOUT_SECONDS}s)")
        except Exception:
            logger.exception(f"❌ Erro processando {filename}")
            return self._error_file_result(filename, "Erro no processamento")

    async def _build_consolidated_analysis(
        self, processed_results, user_email=None, user_id=None, normalize=True
    ) -> ConsolidatedAnalysis:
        success_results = [r for r in processed_results if r.get('success')]

        file_metrics_list, all_predictions = [], []
        models_used, encodings_used = set(), set()
        combined_insights, combined_recommendations = [], []
        all_chart_data, feature_counts = [], []

        for result in success_results:
            metrics = result.get('metrics', {})
            chart_data = result.get('chart_data', {})
            weekly = chart_data.get('weekly', {})
            revenue = weekly.get('revenue', [])
            costs = weekly.get('costs', [])
            total_revenue = sum(revenue) if revenue else 0
            total_costs = sum(costs) if costs else 0
            profit = total_revenue - total_costs

            encoding_used = result.get('encoding_used')
            if encoding_used:
                encodings_used.add(encoding_used)
            if chart_data:
                all_chart_data.append(chart_data)

            predictions = result.get('predictions', [])
            avg_score = metrics.get('mean_prediction', 0.5)
            high_risk_pct = metrics.get('high_risk_percentage', 0)
            low_risk_pct = metrics.get('low_risk_percentage', 0)

            feature_count = result.get('feature_count', 0)
            if feature_count > 0:
                feature_counts.append(feature_count)

            file_metrics = FileMetrics(
                filename=result.get('filename', 'unknown'),
                total_rows=result.get('processed_rows', 0),
                total_revenue=total_revenue, total_costs=total_costs, profit=profit,
                margin=(profit / total_revenue * 100) if total_revenue > 0 else 0,
                avg_score=avg_score, high_risk_percentage=high_risk_pct,
                low_risk_percentage=low_risk_pct, predictions=predictions,
                chart_data=chart_data, success=True, encoding_used=encoding_used,
                processing_time_ms=result.get('processing_time_ms', 0),
                model_used=result.get('model_used', 'default'),
                precision=result.get('precision', 0.0), recall=result.get('recall', 0.0),
                f1_score=result.get('f1_score', 0.0), roc_auc=result.get('roc_auc', 0.0),
                normalization=self.NORMALIZATION if normalize else "None",
                feature_count=feature_count
            )
            file_metrics_list.append(file_metrics)
            all_predictions.extend(predictions)

            if result.get('model_used'):
                models_used.add(result['model_used'])

            insights = result.get('insights', {})
            if isinstance(insights, dict):
                for value in insights.values():
                    if isinstance(value, list): combined_insights.extend(value)
                    elif isinstance(value, str): combined_insights.append(value)
            elif isinstance(insights, list):
                combined_insights.extend(insights)

            recs = result.get('recommendations', [])
            if isinstance(recs, list):
                combined_recommendations.extend(recs)

        ml_results = None
        if all_predictions:
            avg_score = sum(all_predictions) / len(all_predictions)
            std_score = float(np.std(all_predictions)) if len(all_predictions) > 1 else 0.0
            high_risk = len([p for p in all_predictions if p > 0.7])
            low_risk = len([p for p in all_predictions if p < 0.3])
            medium_risk = len(all_predictions) - high_risk - low_risk
            ml_results = MLResults(
                models_used=list(models_used), encodings_used=list(encodings_used),
                total_predictions=len(all_predictions), avg_score=avg_score,
                std_score=std_score, min_score=min(all_predictions), max_score=max(all_predictions),
                risk_distribution={
                    "alto": high_risk / len(all_predictions) * 100,
                    "medio": medium_risk / len(all_predictions) * 100,
                    "baixo": low_risk / len(all_predictions) * 100
                },
                avg_accuracy=avg_score,
                normalization=self.NORMALIZATION if normalize else "None"
            )

        comparison = None
        if len(file_metrics_list) > 1:
            comparison = ComparisonResults(
                best_revenue=max(file_metrics_list, key=lambda x: x.total_revenue).filename,
                best_profit=max(file_metrics_list, key=lambda x: x.profit).filename,
                best_growth=max(file_metrics_list, key=lambda x: x.margin).filename,
                best_efficiency=max(file_metrics_list, key=lambda x: x.avg_score).filename,
                highest_risk=max(file_metrics_list, key=lambda x: x.high_risk_percentage).filename,
                lowest_performance=min(file_metrics_list, key=lambda x: x.avg_score).filename,
                summary=self._generate_comparison_summary(file_metrics_list)
            )

        trend = self._analyze_trend(file_metrics_list) if len(file_metrics_list) > 1 else None
        chart_data = self._get_consolidated_chart_data(all_chart_data, processed_results)

        total_revenue = sum(f.total_revenue for f in file_metrics_list)
        total_profit = sum(f.profit for f in file_metrics_list)
        avg_margin = sum(f.margin for f in file_metrics_list) / len(file_metrics_list) if file_metrics_list else 0
        avg_score_overall = sum(f.avg_score for f in file_metrics_list) / len(file_metrics_list) if file_metrics_list else 0

        return ConsolidatedAnalysis(
            total_files=len(processed_results),
            processed_files=len(success_results),
            failed_files=len(processed_results) - len(success_results),
            user_email=user_email or 'anonimo',
            timestamp=datetime.now().isoformat(),
            files=file_metrics_list, ml_results=ml_results,
            comparison=comparison, trend=trend,
            total_revenue=total_revenue, total_profit=total_profit,
            avg_margin=avg_margin, avg_score_overall=avg_score_overall,
            combined_insights=combined_insights[:10],
            combined_recommendations=combined_recommendations[:5],
            chart_data=chart_data, processing_time_ms=0,
            normalization=self.NORMALIZATION if normalize else "None",
            total_files_analyzed=len(success_results)
        )

    def _generate_comparison_summary(self, files: List[FileMetrics]) -> str:
        if len(files) < 2:
            return ""
        best = max(files, key=lambda x: x.total_revenue)
        worst = min(files, key=lambda x: x.total_revenue)
        return (f"'{best.filename}' apresentou a maior receita "
                f"({_fmt_brl(best.total_revenue)}), enquanto '{worst.filename}' "
                f"teve o menor desempenho ({_fmt_brl(worst.total_revenue)}).")

    def _analyze_trend(self, files: List[FileMetrics]) -> TrendResults:
        if len(files) < 2:
            return TrendResults(direction=TrendDirection.ESTAVEL, strength=0.5,
                                confidence=0.5, description="Dados insuficientes.")
        sorted_files = sorted(files, key=lambda x: x.filename)
        revenues = [f.total_revenue for f in sorted_files]
        growth_rate = (revenues[-1] - revenues[0]) / revenues[0] if revenues[0] > 0 else 0
        if growth_rate > 0.05:
            direction = TrendDirection.CRESCENTE
            description = f"Tendência de crescimento de {_fmt_pct(growth_rate*100)}."
        elif growth_rate < -0.05:
            direction = TrendDirection.DECRESCENTE
            description = f"Tendência de queda de {_fmt_pct(abs(growth_rate)*100)}."
        else:
            direction = TrendDirection.ESTAVEL
            description = "Estabilidade no período."
        observations = []
        if abs(growth_rate) > 0.1:
            observations.append(f"Variação significativa: {_fmt_pct(growth_rate*100)}")
        if not observations:
            observations.append("Dados consistentes.")
        return TrendResults(
            direction=direction, strength=min(1, abs(growth_rate) * 2),
            confidence=0.8, description=description, key_observations=observations
        )

    def _get_consolidated_chart_data(self, chart_data_list, results) -> Dict[str, Any]:
        cache_key = hashlib.md5(
            str(len(chart_data_list)).encode() + str(len(results)).encode()
        ).hexdigest()[:16]
        if cache_key in self._chart_cache:
            cached = self._chart_cache[cache_key]
            if time.time() - cached.get('timestamp', 0) < self._chart_cache_ttl:
                return cached['data']
        chart_data = self._generate_consolidated_chart_data(results)
        self._chart_cache[cache_key] = {'data': chart_data, 'timestamp': time.time()}
        if len(self._chart_cache) > 20:
            oldest = min(self._chart_cache.items(), key=lambda x: x[1]['timestamp'])
            del self._chart_cache[oldest[0]]
        return chart_data

    def _generate_consolidated_chart_data(self, results) -> Dict[str, Any]:
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        all_chart_data = [r.get('chart_data', {}) for r in results if r.get('chart_data')]

        if all_chart_data:
            weekly_revenue = [0.0] * 7
            weekly_costs = [0.0] * 7
            weekly_services = [0.0] * 7
            count = len(all_chart_data)

            for chart in all_chart_data:
                weekly = chart.get('weekly', {})
                rev = weekly.get('revenue', [])
                costs = weekly.get('costs', [])
                perf = chart.get('performance', {})
                serv = perf.get('services', [])
                for i in range(min(7, len(rev))):
                    if rev[i]: weekly_revenue[i] += rev[i] / count
                for i in range(min(7, len(costs))):
                    if costs[i]: weekly_costs[i] += costs[i] / count
                for i in range(min(7, len(serv))):
                    if serv[i]: weekly_services[i] += serv[i] / count

            monthly_revenue = [0.0] * 12
            for chart in all_chart_data:
                monthly = chart.get('monthly', {})
                rev = monthly.get('revenue', [])
                for i in range(min(12, len(rev))):
                    if rev[i]: monthly_revenue[i] += rev[i] / count

            return {
                "weekly": {
                    "labels": days,
                    "revenue": [round(v, 2) for v in weekly_revenue],
                    "costs": [round(v, 2) for v in weekly_costs]
                },
                "performance": {"labels": days, "services": [round(v) for v in weekly_services]},
                "monthly": {"labels": months, "revenue": [round(v, 2) for v in monthly_revenue]},
                "files_merged": len(all_chart_data),
                "normalization": self.NORMALIZATION
            }

        return {
            "weekly": {"labels": days, "revenue": [0] * 7, "costs": [0] * 7},
            "performance": {"labels": days, "services": [0] * 7},
            "monthly": {"labels": months, "revenue": [0] * 12},
            "files_merged": 0,
            "normalization": self.NORMALIZATION
        }

    # ==========================================
    # 🔥 GEMINI + FALLBACK DATA-DRIVEN
    # ==========================================

    async def _generate_gemini_analysis(self, consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        """
        ⚠️ IMPORTANTE: Gemini é SEMPRE chamado PRIMEIRO.
        O fallback DATA-DRIVEN só entra em ação se o Gemini falhar.
        """
        logger.info("=" * 60)
        logger.info("🤖 INICIANDO ANÁLISE")

        # ✅ Verifica se Gemini está pronto (dinâmico)
        gemini_ok = self._gemini_is_ready()

        if not gemini_ok:
            logger.warning("⚠️ Gemini indisponível - usando FALLBACK DATA-DRIVEN")
            self._stats["fallback_used_count"] += 1
            return IntelligentAnalyzer.analyze_multiple_files(consolidated)

        # 🔥 GEMINI PRIMEIRO — só cai no fallback se falhar
        try:
            logger.info("📤 Enviando para Gemini (tentativa principal)...")
            start_time = time.time()
            analysis_data = consolidated.to_dict()
            analysis_data['analysis_type'] = 'analise_avancada'

            response = await asyncio.wait_for(
                self.gemini.analyze_office_data(
                    data_type="analise_avancada", analysis_data=analysis_data
                ),
                timeout=60.0
            )
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"⏱️ Gemini respondeu em {elapsed:.0f}ms")

            if not response or not response.get('success', False):
                logger.warning("⚠️ Gemini falhou - usando FALLBACK DATA-DRIVEN")
                self._mark_gemini_failure(RuntimeError("Resposta sem sucesso"))
                self.invalidate_gemini_cache()
                return IntelligentAnalyzer.analyze_multiple_files(consolidated)

            full_text = response.get('full_analysis', '')
            if not full_text or len(full_text) < 50:
                logger.warning("⚠️ Resposta Gemini muito curta - usando FALLBACK DATA-DRIVEN")
                self._mark_gemini_failure(RuntimeError("Resposta muito curta"))
                self.invalidate_gemini_cache()
                return IntelligentAnalyzer.analyze_multiple_files(consolidated)

            logger.info("✅ Gemini respondeu com sucesso!")
            self._mark_gemini_success()
            return {
                'success': True,
                'executive_score': self._parse_executive_score(full_text),
                'executive_summary': self._parse_summary(full_text),
                'comparison': self._parse_comparison(full_text),
                'trend': self._parse_trend(full_text),
                'recommendations': self._parse_recommendations(full_text),
                'forecast': self._parse_forecast(full_text),
                'conclusion': self._parse_conclusion(full_text),
                'full_analysis': full_text,
                'model_used': response.get('model_used', 'gemini'),
                'tokens_used': response.get('tokens_used', 0),
                'response_time_ms': elapsed,
                'fallback_used': False,
            }

        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout do Gemini - usando FALLBACK DATA-DRIVEN")
            self._stats["gemini_timeouts"] += 1
            self._mark_gemini_failure(asyncio.TimeoutError("Timeout 60s"))
            self.invalidate_gemini_cache()
            return IntelligentAnalyzer.analyze_multiple_files(consolidated)
        except Exception as e:
            logger.exception("⚠️ Erro no Gemini - usando FALLBACK DATA-DRIVEN")
            self._mark_gemini_failure(e)
            self.invalidate_gemini_cache()
            return IntelligentAnalyzer.analyze_multiple_files(consolidated)

    # ==========================================
    # PARSERS DO GEMINI
    # ==========================================

    def _parse_executive_score(self, text: str) -> Dict[str, Any]:
        scores = {
            'saude_financeira': 5.0, 'eficiencia': 5.0,
            'controle_custos': 5.0, 'crescimento': 5.0,
            'nivel_risco': 'Moderado', 'nota_geral': 5.0
        }
        patterns = {
            'saude_financeira': r'Sa[úu]de Financeira[^\d]{0,10}(\d+(?:[.,]\d+)?)',
            'eficiencia': r'Efici[êe]ncia[^\d]{0,10}(\d+(?:[.,]\d+)?)',
            'controle_custos': r'Controle de Custos[^\d]{0,10}(\d+(?:[.,]\d+)?)',
            'crescimento': r'Crescimento[^\d]{0,10}(\d+(?:[.,]\d+)?)',
            'nivel_risco': r'N[ií]vel de Risco[^\w]{0,10}([A-Za-zçãáéíóúâêô]+)',
            'nota_geral': r'Nota Geral[^\d]{0,10}(\d+(?:[.,]\d+)?)'
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).replace(',', '.')
                if key == 'nivel_risco':
                    v = value.lower()
                    if 'baix' in v: scores[key] = 'Baixo'
                    elif 'alt' in v: scores[key] = 'Alto'
                    else: scores[key] = 'Moderado'
                else:
                    try: scores[key] = float(value)
                    except ValueError: pass
        return scores

    def _parse_summary(self, text: str) -> str:
        patterns = [
            r'Resumo Executivo\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
            r'📊 Resumo\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                summary = match.group(1).strip()[:500]
                if len(summary) > 20: return summary
        return "Análise concluída."

    def _parse_comparison(self, text: str) -> ComparisonResults:
        comparison = {'best_revenue': '', 'best_profit': '', 'best_growth': '', 'highest_risk': ''}
        patterns = {
            'best_revenue': r'Melhor Receita\s*[:=]\s*([^\n]+)',
            'best_profit': r'Melhor Lucro\s*[:=]\s*([^\n]+)',
            'best_growth': r'Melhor Crescimento\s*[:=]\s*([^\n]+)',
            'highest_risk': r'Maior Risco\s*[:=]\s*([^\n]+)'
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match: comparison[key] = match.group(1).strip()
        return ComparisonResults(
            best_revenue=comparison['best_revenue'], best_profit=comparison['best_profit'],
            best_growth=comparison['best_growth'], highest_risk=comparison['highest_risk']
        )

    def _parse_trend(self, text: str) -> TrendResults:
        direction = TrendDirection.ESTAVEL
        text_lower = text.lower()
        if re.search(r'tend[eê]ncia\s*(crescent|aument|alta)', text_lower):
            direction = TrendDirection.CRESCENTE
        elif re.search(r'tend[eê]ncia\s*(decrescent|diminu|baixa)', text_lower):
            direction = TrendDirection.DECRESCENTE
        return TrendResults(direction=direction)

    def _parse_recommendations(self, text: str) -> List[Dict[str, Any]]:
        recommendations = []
        sections = re.split(r'##\s+', text)
        for section in sections:
            section_lower = section.lower()
            if any(kw in section_lower for kw in ['alta', 'urgente', 'priorit']): priority = 'alta'
            elif any(kw in section_lower for kw in ['media', 'média']): priority = 'media'
            elif any(kw in section_lower for kw in ['baixa', 'menor']): priority = 'baixa'
            else: continue
            for line in section.split('\n'):
                line = line.strip()
                if line.startswith('-') or line.startswith('•'):
                    item = line[1:].strip()
                    if len(item) > 10:
                        recommendations.append({
                            'priority': priority,
                            'category': self._guess_category(item),
                            'description': item[:180],
                            'expected_impact': self._guess_impact(item),
                            'effort': self._guess_effort(item)
                        })
        return recommendations[:6]

    def _parse_forecast(self, text: str) -> str:
        patterns = [
            r'Previsão\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
            r'Forecast\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match: return match.group(1).strip()[:300]
        return "Espera-se estabilidade com leve crescimento."

    def _parse_conclusion(self, text: str) -> str:
        patterns = [
            r'Conclusão Geral\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
            r'📌 Conclusão\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match: return match.group(1).strip()[:500]
        return "A análise demonstra potencial de melhoria."

    def _guess_category(self, text: str) -> str:
        text_lower = text.lower()
        categories = {
            'financeiro': ['custo', 'gasto', 'despesa', 'lucro', 'receita', 'margem'],
            'operacional': ['processo', 'eficiência', 'tempo', 'produtividade', 'fluxo'],
            'comercial': ['cliente', 'venda', 'marketing', 'atendimento'],
            'estoque': ['estoque', 'inventário', 'suprimento', 'material']
        }
        for category, keywords in categories.items():
            if any(kw in text_lower for kw in keywords): return category
        return 'geral'

    def _guess_impact(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ['alto', 'grande', 'significativo']): return 'Alto impacto'
        if any(w in t for w in ['médio', 'moderado']): return 'Médio impacto'
        return 'Baixo impacto'

    def _guess_effort(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ['imediato', 'rápido', 'simples', 'fácil']): return 'baixo'
        if any(w in t for w in ['complexo', 'longo', 'estrutural']): return 'alto'
        return 'medio'

    # ==========================================
    # BUILD RESULT
    # ==========================================

    def _build_result(
        self, files, processed_results, consolidated, gemini_analysis,
        processing_time_ms, normalize=True
    ) -> MultiFileAnalysisResult:
        success_count = sum(1 for r in processed_results if r.get('success'))

        if not gemini_analysis or not gemini_analysis.get('success', False):
            logger.warning("⚠️ gemini_analysis inválido — aplicando fallback DATA-DRIVEN")
            gemini_analysis = IntelligentAnalyzer.analyze_multiple_files(consolidated)

        encodings_used = [r['encoding_used'] for r in processed_results if r.get('encoding_used')]
        if not encodings_used:
            encodings_used = ['unknown']

        comparison = self._ensure_comparison_object(
            gemini_analysis.get('comparison'), consolidated.comparison
        )
        trend = self._ensure_trend_object(
            gemini_analysis.get('trend'), consolidated.trend
        )

        feature_counts = [f.feature_count for f in consolidated.files if f.feature_count > 0]
        avg_feature_count = sum(feature_counts) / len(feature_counts) if feature_counts else 0

        analysis_source = 'gemini' if not gemini_analysis.get('fallback_used', False) else 'fallback_local'

        return MultiFileAnalysisResult(
            success=success_count > 0,
            status=AnalysisStatus.COMPLETED.value if success_count > 0 else AnalysisStatus.FAILED.value,
            progress=1.0, total_files=len(files), processed_files=success_count,
            failed_files=len(files) - success_count,
            files=processed_results,
            executive_score=gemini_analysis.get('executive_score', {}),
            executive_summary=gemini_analysis.get('executive_summary', ''),
            comparison=comparison, trend=trend,
            recommendations=gemini_analysis.get('recommendations', []),
            forecast=gemini_analysis.get('forecast', ''),
            general_conclusion=gemini_analysis.get('conclusion', ''),
            chart_data=consolidated.chart_data,
            processing_time_ms=processing_time_ms, cache_hit=False,
            encodings_used=list(set(encodings_used)),
            normalization=self.NORMALIZATION if normalize else "None",
            model_version="V7.0", feature_count_avg=int(avg_feature_count),
            analysis_source=analysis_source
        )

    def _ensure_comparison_object(self, comparison_data, fallback_comparison):
        if comparison_data is None: return fallback_comparison
        if isinstance(comparison_data, ComparisonResults): return comparison_data
        if isinstance(comparison_data, dict):
            return ComparisonResults(
                best_revenue=comparison_data.get('best_revenue', ''),
                best_profit=comparison_data.get('best_profit', ''),
                best_growth=comparison_data.get('best_growth', ''),
                best_efficiency=comparison_data.get('best_efficiency', ''),
                highest_risk=comparison_data.get('highest_risk', ''),
                lowest_performance=comparison_data.get('lowest_performance', ''),
                comparison_table=comparison_data.get('comparison_table', {}),
                summary=comparison_data.get('summary', '')
            )
        return fallback_comparison

    def _ensure_trend_object(self, trend_data, fallback_trend):
        if trend_data is None: return fallback_trend
        if isinstance(trend_data, TrendResults): return trend_data
        if isinstance(trend_data, dict):
            direction_str = str(trend_data.get('direction', 'estavel')).lower()
            try:
                direction = TrendDirection(direction_str)
            except ValueError:
                direction = TrendDirection.ESTAVEL
            return TrendResults(
                direction=direction,
                strength=float(trend_data.get('strength', 0.5)),
                confidence=float(trend_data.get('confidence', 0.7)),
                description=trend_data.get('description', ''),
                key_observations=trend_data.get('key_observations', [])
            )
        return fallback_trend

    # ==========================================
    # CACHE
    # ==========================================

    def _get_cache_key(self, files, user_id=None) -> str:
        content_parts = []
        for f in files:
            name = f.get('filename', '')
            size = f.get('file_size', 0)
            content_hash = hashlib.md5(f.get('content', b'')).hexdigest()[:8]
            content_parts.append(f"{name}:{size}:{content_hash}")
        base = "|".join(content_parts)
        if user_id: base += f":user_{user_id}"
        return hashlib.md5(base.encode()).hexdigest()

    def _get_cached_result(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._cache:
            data, timestamp, hits = self._cache[key]
            if time.time() - timestamp < self.CACHE_TTL:
                self._cache[key] = (data, timestamp, hits + 1)
                self._cache_hits += 1
                self._stats["cache_hits"] += 1
                return copy.deepcopy(data)
            else:
                del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Dict[str, Any]) -> None:
        self._cache[key] = (copy.deepcopy(data), time.time(), 0)
        if len(self._cache) > 100:
            self._clean_cache()

    def _clean_cache(self):
        if len(self._cache) <= 100: return
        items = sorted(self._cache.items(), key=lambda x: (x[1][1], x[1][2]))
        to_remove = len(self._cache) - 80
        for i in range(to_remove):
            del self._cache[items[i][0]]

    def clear_cache(self):
        size = len(self._cache)
        self._cache.clear()
        self._chart_cache.clear()
        logger.info(f"🧹 Cache cleared: {size} entries")

    def _error_result(self, error: str) -> MultiFileAnalysisResult:
        return MultiFileAnalysisResult(
            success=False, status=AnalysisStatus.FAILED.value,
            progress=1.0, total_files=0, processed_files=0,
            failed_files=0, error=error,
            timestamp=datetime.now().isoformat(),
            model_version="V7.0"
        )

    def _error_file_result(self, filename: str, error: str) -> Dict[str, Any]:
        return {
            'success': False, 'filename': filename, 'error': error,
            'predictions': [], 'metrics': {}, 'chart_data': {},
            'encoding_used': None, 'processing_time_ms': 0, 'model_used': 'error',
            'precision': 0.0, 'recall': 0.0, 'f1_score': 0.0,
            'roc_auc': 0.0, 'feature_count': 0
        }

    # ==========================================
    # STATS / HEALTH
    # ==========================================

    def get_stats(self) -> Dict[str, Any]:
        uptime = (datetime.now() - datetime.fromisoformat(self._stats["started_at"])).total_seconds()
        gemini_ok = self._gemini_is_ready(force=False)
        return {
            **self._stats,
            "cache_size": len(self._cache),
            "chart_cache_size": len(self._chart_cache),
            "cache_hit_rate": (
                self._cache_hits / (self._cache_hits + self._cache_misses) * 100
                if (self._cache_hits + self._cache_misses) > 0 else 0
            ),
            "uptime_seconds": uptime,
            "gemini_available": gemini_ok,
            "gemini_circuit_state": self._gemini_circuit_state.value,
            "gemini_failure_count": self._gemini_failure_count,
            "gemini_last_error": self._gemini_last_error,
            "predictor_available": self.predictor is not None,
            "max_concurrent": self.MAX_CONCURRENT,
            "cache_ttl": self.CACHE_TTL,
            "normalization": self.NORMALIZATION,
            "fallback_engine": "intelligent_fallback_v7_data_driven",
            "model_version": "V7.0"
        }

    def get_health_status(self) -> Dict[str, Any]:
        gemini_ok = self._gemini_is_ready(force=True)
        return {
            "status": "healthy" if self.pipeline else "degraded",
            "gemini": "available" if gemini_ok else "unavailable",
            "gemini_circuit_state": self._gemini_circuit_state.value,
            "gemini_failure_count": self._gemini_failure_count,
            "gemini_last_error": self._gemini_last_error,
            "gemini_last_check_at": self._stats.get("gemini_last_check_at"),
            "predictor": "available" if self.predictor else "unavailable",
            "pipeline": "available" if self.pipeline else "unavailable",
            "cache_size": len(self._cache),
            "total_analyses": self._stats["total_analyses"],
            "success_rate": (
                self._stats["successful_analyses"] / self._stats["total_analyses"] * 100
                if self._stats["total_analyses"] > 0 else 0
            ),
            "gemini_errors": self._stats["gemini_errors"],
            "gemini_revalidations_success": self._stats["gemini_revalidations_success"],
            "gemini_revalidations_failed": self._stats["gemini_revalidations_failed"],
            "gemini_circuit_opens": self._stats["gemini_circuit_opens"],
            "fallback_used_count": self._stats["fallback_used_count"],
            "normalization": self.NORMALIZATION,
            "model_version": "V7.0",
            "fallback_engine": "intelligent_fallback_v7_data_driven",
            "timestamp": datetime.now().isoformat()
        }


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

_multi_analyzer = None


def get_multi_analyzer() -> MultiFileAnalyzerV6:
    global _multi_analyzer
    if _multi_analyzer is None:
        _multi_analyzer = MultiFileAnalyzerV6()
    return _multi_analyzer


async def analyze_multiple_files(
    files: List[Dict[str, Any]],
    user_id: int = None,
    user_email: str = None,
    force_reload: bool = False,
    progress_callback: Optional[Callable] = None,
    db_session=None,
    process_id: int = None,
    normalize: bool = True
) -> Dict[str, Any]:
    analyzer = get_multi_analyzer()
    result = await analyzer.analyze_multiple_files(
        files=files, user_id=user_id, user_email=user_email,
        force_reload=force_reload, progress_callback=progress_callback,
        db_session=db_session, process_id=process_id, normalize=normalize
    )
    return result.to_dict()


# ==============================================
# TESTES
# ==============================================

async def test_multi_analysis():
    print("\n" + "=" * 70)
    print("🧪 TESTANDO ANÁLISE MÚLTIPLA V7.0 (FALLBACK DATA-DRIVEN)")
    print("=" * 70)

    from io import BytesIO

    def create_test_file(i: int, seed: int = 42):
        np.random.seed(seed + i)
        df = pd.DataFrame({
            'cliente_id': range(1, 101),
            'valor_servico': np.random.randn(100) * 100 + 500 + i * 50,
            'custo_pecas': np.random.randn(100) * 50 + 200 + i * 30,
            'data': pd.date_range('2024-01-01', periods=100, freq='D')
        })
        buffer = BytesIO()
        df.to_csv(buffer, index=False)
        return buffer.getvalue()

    files = []
    for i in range(3):
        content = create_test_file(i)
        files.append({
            'content': content,
            'filename': f'teste_arquivo_{i+1}.csv',
            'file_size': len(content)
        })

    def print_progress(progress: float, status: str):
        bar = "█" * int(progress * 40)
        spaces = " " * (40 - int(progress * 40))
        print(f"\r   [{bar}{spaces}] {progress*100:.0f}% - {status}", end="")
        if progress >= 1.0: print()

    try:
        result = await analyze_multiple_files(
            files=files, user_email='teste@email.com', user_id=1,
            progress_callback=print_progress, normalize=True
        )
        print(f"\n📊 RESULTADO:")
        print(f"   ✅ Sucesso: {result['success']}")
        print(f"   🤖 Fonte: {result.get('analysis_source', 'N/A')}")
        print(f"   📁 Total: {result['total_files']}")
        print(f"   ✅ Processados: {result['processed_files']}")
        print(f"   ⏱️ Tempo: {result['processing_time_ms']:.0f}ms")
        print(f"\n📝 RESUMO: {result.get('executive_summary', '')[:300]}")
        print("\n✅ Teste concluído!")
        return result
    except Exception as e:
        print(f"\n❌ TESTE FALHOU: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_gemini_revalidation():
    print("\n" + "=" * 70)
    print("🧪 TESTANDO REVALIDAÇÃO DINÂMICA DO GEMINI")
    print("=" * 70)
    analyzer = get_multi_analyzer()

    print(f"\n1️⃣ Estado inicial: is_gemini_available={analyzer.is_gemini_available}")

    analyzer.is_gemini_available = False
    analyzer.invalidate_gemini_cache()
    print(f"2️⃣ Após forçar False: is_gemini_available={analyzer.is_gemini_available}")

    ready = analyzer._gemini_is_ready(force=True)
    print(f"3️⃣ Após revalidação: ready={ready}, is_gemini_available={analyzer.is_gemini_available}")

    health = analyzer.get_health_status()
    print(f"4️⃣ Health status: gemini={health['gemini']}, circuit={health['gemini_circuit_state']}")

    print("\n5️⃣ Testando circuit breaker (3 falhas simuladas)...")
    for i in range(3):
        analyzer._mark_gemini_failure(RuntimeError(f"falha_simulada_{i}"))
    print(f"   Estado do circuit: {analyzer._gemini_circuit_state.value}")
    print(f"   Deve bloquear: {analyzer._gemini_is_ready(force=True)}")

    print("\n6️⃣ Reset manual do circuit...")
    analyzer._reset_gemini_circuit()
    print(f"   Estado após reset: {analyzer._gemini_circuit_state.value}")

    print("\n✅ Teste de revalidação concluído!")


if __name__ == "__main__":
    asyncio.run(test_multi_analysis())
    asyncio.run(test_gemini_revalidation())