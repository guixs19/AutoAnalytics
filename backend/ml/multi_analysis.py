# backend/ml/multi_analysis.py - VERSÃO 6.3 (GEMINI DINÂMICO + CIRCUIT BREAKER)
"""
🔥 ANÁLISE MÚLTIPLA DE ARQUIVOS - V6.3
================================================================================
✅ NOVIDADES V6.3:
   - 🔄 GEMINI DINÂMICO: revalidação em tempo real (sem estado congelado)
   - 🛡️ CIRCUIT BREAKER: proteção contra serviço degradado
   - 📊 TELEMETRIA: métricas de revalidação e falhas
   - 🐛 13 BUGS CORRIGIDOS
   - ⚡ MICRO-CACHE: 10s TTL para evitar overhead
   - 🎯 LOGGER.EXCEPTION: tracebacks preservados
   - 🔒 DEEPCOPY no cache: sem mutação acidental

✅ MANTIDO V6.2:
   - 🔥 FALLBACK INTELIGENTE (análise rica sem Gemini)
   - 🔥 ANÁLISE POR ARQUIVO + COMPARAÇÃO + TENDÊNCIA
   - 🔥 ZERO DADOS INVENTADOS
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
    CLOSED = "closed"        # operacional
    OPEN = "open"            # bloqueado
    HALF_OPEN = "half_open"  # testando recuperação


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
# DATACLASSES (mantidas, com pequenos ajustes)
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
                    "normalization": f.normalization
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
                "normalization": self.ml_results.normalization if self.ml_results else "Z-Score"
            } if self.ml_results else {},
            "comparison": {
                "best_revenue": self.comparison.best_revenue if self.comparison else "",
                "best_profit": self.comparison.best_profit if self.comparison else "",
                "best_growth": self.comparison.best_growth if self.comparison else "",
                "best_efficiency": self.comparison.best_efficiency if self.comparison else "",
                "highest_risk": self.comparison.highest_risk if self.comparison else "",
                "lowest_performance": self.comparison.lowest_performance if self.comparison else ""
            } if self.comparison else {},
            "trend": {
                "direction": self.trend.direction.value if self.trend else "estavel",
                "strength": round(self.trend.strength, 2) if self.trend else 0.5,
                "confidence": round(self.trend.confidence, 2) if self.trend else 0.7,
                "description": self.trend.description if self.trend else "",
                "key_observations": self.trend.key_observations if self.trend else []
            } if self.trend else {},
            "total_revenue": round(self.total_revenue, 2),
            "total_profit": round(self.total_profit, 2),
            "avg_margin": round(self.avg_margin, 1),
            "avg_score_overall": round(self.avg_score_overall, 3),
            "combined_insights": self.combined_insights[:5],
            "combined_recommendations": self.combined_recommendations[:5],
            "chart_data": self.chart_data,
            "processing_time_ms": round(self.processing_time_ms, 2)
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
    model_version: str = "V6.3"
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
            "analysis_source": self.analysis_source
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
                "summary": getattr(self.comparison, 'summary', '')
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
                "key_observations": getattr(self.trend, 'key_observations', [])
            }
        return {}


# ==============================================
# 🔥 MOTOR DE ANÁLISE INTELIGENTE (FALLBACK)
# ==============================================
# (Mantido integralmente da V6.2 — nenhuma alteração aqui,
#  para preservar comportamento e evitar regressões)

class IntelligentAnalyzer:
    MARGIN_CRITICAL = 10.0
    MARGIN_WARNING = 20.0
    MARGIN_GOOD = 30.0
    MARGIN_EXCELLENT = 45.0
    RISK_HIGH_THRESHOLD = 0.7
    RISK_LOW_THRESHOLD = 0.3
    CONCENTRATION_THRESHOLD = 0.4

    @staticmethod
    def analyze_file(file_metrics: FileMetrics) -> Dict[str, Any]:
        insights, strengths, weaknesses, recommendations = [], [], [], []
        metrics_extra: Dict[str, Any] = {}

        margin = file_metrics.margin
        revenue = file_metrics.total_revenue
        profit = file_metrics.profit

        metrics_extra['margin_class'] = IntelligentAnalyzer._classify_margin(margin)
        metrics_extra['revenue_class'] = IntelligentAnalyzer._classify_revenue(revenue)
        metrics_extra['profit_class'] = 'positivo' if profit > 0 else 'negativo' if profit < 0 else 'neutro'

        if margin < 0:
            insights.append(f"⚠️ Margem negativa ({margin:.1f}%): operação está no prejuízo.")
            weaknesses.append(f"Margem negativa de {margin:.1f}%")
            recommendations.append({
                'priority': 'alta', 'category': 'financeiro',
                'description': f'Margem de {margin:.1f}% indica prejuízo. Ação imediata: revisar precificação, cortar custos ou renegociar fornecedores.',
                'expected_impact': 'Crítico', 'effort': 'alto'
            })
        elif margin < IntelligentAnalyzer.MARGIN_CRITICAL:
            insights.append(f"🔴 Margem crítica ({margin:.1f}%): abaixo do mínimo saudável de {IntelligentAnalyzer.MARGIN_CRITICAL}%.")
            weaknesses.append(f"Margem crítica de {margin:.1f}%")
            recommendations.append({
                'priority': 'alta', 'category': 'financeiro',
                'description': f'Margem de {margin:.1f}% está abaixo do ideal. Reveja estrutura de custos e considere ajuste de preços.',
                'expected_impact': 'Alto', 'effort': 'medio'
            })
        elif margin < IntelligentAnalyzer.MARGIN_WARNING:
            insights.append(f"🟡 Margem moderada ({margin:.1f}%): há espaço para otimização.")
            recommendations.append({
                'priority': 'media', 'category': 'financeiro',
                'description': f'Margem de {margin:.1f}% é aceitável, mas pode chegar a {IntelligentAnalyzer.MARGIN_GOOD}% com ajustes.',
                'expected_impact': 'Médio', 'effort': 'medio'
            })
        elif margin < IntelligentAnalyzer.MARGIN_GOOD:
            insights.append(f"🟢 Margem saudável ({margin:.1f}%): dentro do esperado para o setor.")
            strengths.append(f"Margem saudável de {margin:.1f}%")
        else:
            insights.append(f"💎 Margem excelente ({margin:.1f}%): performance acima da média do setor.")
            strengths.append(f"Margem excelente de {margin:.1f}%")
            recommendations.append({
                'priority': 'baixa', 'category': 'financeiro',
                'description': f'Margem de {margin:.1f}% é excelente. Considere reinvestir em expansão ou reserva estratégica.',
                'expected_impact': 'Alto', 'effort': 'baixo'
            })

        predictions = file_metrics.predictions or []
        if predictions:
            high_risk_count = sum(1 for p in predictions if p > IntelligentAnalyzer.RISK_HIGH_THRESHOLD)
            low_risk_count = sum(1 for p in predictions if p < IntelligentAnalyzer.RISK_LOW_THRESHOLD)
            total = len(predictions)

            metrics_extra['high_risk_count'] = high_risk_count
            metrics_extra['low_risk_count'] = low_risk_count
            metrics_extra['predictions_count'] = total

            high_pct = (high_risk_count / total) * 100 if total > 0 else 0
            low_pct = (low_risk_count / total) * 100 if total > 0 else 0

            metrics_extra['high_risk_pct'] = high_pct
            metrics_extra['low_risk_pct'] = low_pct

            if high_pct > 50:
                insights.append(f"🚨 Alta concentração de risco: {high_pct:.1f}% dos registros são de alto risco.")
                weaknesses.append(f"{high_pct:.1f}% em alto risco")
                recommendations.append({
                    'priority': 'alta', 'category': 'operacional',
                    'description': f'{high_pct:.1f}% dos registros são de alto risco. Ação preventiva urgente.',
                    'expected_impact': 'Alto', 'effort': 'alto'
                })
            elif high_pct > 25:
                insights.append(f"⚠️ {high_pct:.1f}% dos registros são de alto risco — monitorar de perto.")
                recommendations.append({
                    'priority': 'media', 'category': 'operacional',
                    'description': f'{high_pct:.1f}% em alto risco requer monitoramento contínuo.',
                    'expected_impact': 'Médio', 'effort': 'medio'
                })
            else:
                insights.append(f"✅ Baixa exposição a risco: apenas {high_pct:.1f}% em alto risco.")
                strengths.append(f"Baixa exposição a risco ({high_pct:.1f}%)")

            if low_pct > 60:
                strengths.append(f"{low_pct:.1f}% em baixo risco — base sólida")

        rows = file_metrics.total_rows
        metrics_extra['rows_class'] = IntelligentAnalyzer._classify_volume(rows)

        if rows > 0:
            revenue_per_row = revenue / rows
            metrics_extra['revenue_per_row'] = revenue_per_row

            if revenue_per_row < 50:
                insights.append(f"📉 Ticket médio baixo (R$ {revenue_per_row:.2f} por registro).")
                recommendations.append({
                    'priority': 'media', 'category': 'comercial',
                    'description': f'Ticket médio de R$ {revenue_per_row:.2f} pode ser aumentado com up-sell e cross-sell.',
                    'expected_impact': 'Médio', 'effort': 'baixo'
                })
            elif revenue_per_row > 500:
                strengths.append(f"Ticket médio alto (R$ {revenue_per_row:.2f})")
            else:
                insights.append(f"💰 Ticket médio de R$ {revenue_per_row:.2f} — dentro do esperado.")

        chart_data = file_metrics.chart_data or {}
        weekly = chart_data.get('weekly', {})
        weekly_revenue = weekly.get('revenue', [])

        if weekly_revenue and len(weekly_revenue) >= 3:
            total_week = sum(weekly_revenue)
            if total_week > 0:
                max_day_idx = weekly_revenue.index(max(weekly_revenue))
                min_day_idx = weekly_revenue.index(min(weekly_revenue))
                days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

                max_pct = (weekly_revenue[max_day_idx] / total_week) * 100
                min_pct = (weekly_revenue[min_day_idx] / total_week) * 100

                metrics_extra['peak_day'] = days[max_day_idx]
                metrics_extra['peak_day_pct'] = max_pct
                metrics_extra['weak_day'] = days[min_day_idx]
                metrics_extra['weak_day_pct'] = min_pct

                if max_pct > 40:
                    insights.append(f"📊 Concentração em {days[max_day_idx]}: {max_pct:.1f}% da receita semanal.")
                    recommendations.append({
                        'priority': 'media', 'category': 'operacional',
                        'description': f'{max_pct:.1f}% da receita vem de {days[max_day_idx]}. Diversifique.',
                        'expected_impact': 'Médio', 'effort': 'medio'
                    })
                elif max_pct < 20:
                    insights.append(f"✅ Distribuição equilibrada: nenhum dia passa de {max_pct:.1f}% da receita.")
                    strengths.append("Distribuição equilibrada na semana")

                if min_pct < 5:
                    insights.append(f"⚠️ {days[min_day_idx]} tem apenas {min_pct:.1f}% da receita — dia subutilizado.")
                    recommendations.append({
                        'priority': 'baixa', 'category': 'comercial',
                        'description': f'{days[min_day_idx]} tem baixo movimento ({min_pct:.1f}%). Considere promoções.',
                        'expected_impact': 'Baixo', 'effort': 'baixo'
                    })

                sazonalidade = max_pct - min_pct
                metrics_extra['sazonalidade_weekly'] = sazonalidade
                if sazonalidade > 50:
                    weaknesses.append(f"Alta variação semanal ({sazonalidade:.1f} p.p.)")

        monthly = chart_data.get('monthly', {})
        monthly_revenue = monthly.get('revenue', [])

        if monthly_revenue and len(monthly_revenue) >= 3:
            valid_months = [(i, v) for i, v in enumerate(monthly_revenue) if v > 0]
            if len(valid_months) >= 3:
                values = [v for _, v in valid_months]
                n = len(values)
                x = list(range(n))
                x_mean = sum(x) / n
                y_mean = sum(values) / n
                numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
                denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
                slope = numerator / denominator if denominator != 0 else 0

                growth = ((values[-1] - values[0]) / values[0] * 100) if values[0] > 0 else 0
                metrics_extra['monthly_growth_pct'] = growth

                if growth > 20:
                    insights.append(f"📈 Crescimento mensal de {growth:.1f}% no período analisado.")
                    strengths.append(f"Crescimento de {growth:.1f}%")
                elif growth > 5:
                    insights.append(f"📈 Crescimento moderado de {growth:.1f}%.")
                elif growth < -20:
                    insights.append(f"📉 Queda de {abs(growth):.1f}% — atenção aos indicadores.")
                    weaknesses.append(f"Queda de {abs(growth):.1f}%")
                    recommendations.append({
                        'priority': 'alta', 'category': 'operacional',
                        'description': f'Queda de {abs(growth):.1f}% na receita mensal. Analise causas.',
                        'expected_impact': 'Alto', 'effort': 'alto'
                    })
                elif growth < -5:
                    insights.append(f"📉 Leve queda de {abs(growth):.1f}% — monitorar.")
                else:
                    insights.append(f"➡️ Estabilidade mensal (variação de {growth:.1f}%).")

                mean_v = sum(values) / n
                variance = sum((v - mean_v) ** 2 for v in values) / n
                std_v = variance ** 0.5
                cv = (std_v / mean_v * 100) if mean_v > 0 else 0
                metrics_extra['monthly_cv'] = cv

                if cv > 50:
                    weaknesses.append(f"Alta volatilidade mensal (CV={cv:.1f}%)")
                    insights.append(f"⚠️ Volatilidade alta ({cv:.1f}%) — receita imprevisível.")

        file_summary = IntelligentAnalyzer._generate_file_summary(
            file_metrics, metrics_extra, strengths, weaknesses
        )
        file_score = IntelligentAnalyzer._calculate_file_score(file_metrics, metrics_extra)

        return {
            'insights': insights, 'strengths': strengths, 'weaknesses': weaknesses,
            'recommendations': recommendations, 'metrics_extra': metrics_extra,
            'summary': file_summary, 'score': file_score
        }

    @staticmethod
    def _classify_margin(margin: float) -> str:
        if margin < 0: return 'negativa'
        if margin < 10: return 'critica'
        if margin < 20: return 'baixa'
        if margin < 30: return 'moderada'
        if margin < 45: return 'saudavel'
        return 'excelente'

    @staticmethod
    def _classify_revenue(revenue: float) -> str:
        if revenue <= 0: return 'sem_receita'
        if revenue < 5000: return 'baixa'
        if revenue < 20000: return 'media'
        if revenue < 100000: return 'alta'
        return 'muito_alta'

    @staticmethod
    def _classify_volume(rows: int) -> str:
        if rows < 50: return 'baixo'
        if rows < 200: return 'medio'
        if rows < 1000: return 'alto'
        return 'muito_alto'

    @staticmethod
    def _generate_file_summary(file_metrics, metrics_extra, strengths, weaknesses) -> str:
        parts = []
        parts.append(
            f"O arquivo '{file_metrics.filename}' contém {file_metrics.total_rows} registros "
            f"com receita total de R$ {file_metrics.total_revenue:,.2f} e lucro de R$ {file_metrics.profit:,.2f}."
        )
        margin = file_metrics.margin
        margin_class = metrics_extra.get('margin_class', 'moderada')
        margin_descriptions = {
            'negativa': f"A margem negativa de {margin:.1f}% exige ação corretiva imediata.",
            'critica': f"A margem crítica de {margin:.1f}% está bem abaixo do ideal.",
            'baixa': f"A margem de {margin:.1f}% está abaixo do esperado para o setor.",
            'moderada': f"A margem de {margin:.1f}% é aceitável, com espaço para otimização.",
            'saudavel': f"A margem saudável de {margin:.1f}% indica boa gestão financeira.",
            'excelente': f"A margem excelente de {margin:.1f}% demonstra performance superior."
        }
        parts.append(margin_descriptions.get(margin_class, ""))
        rows_class = metrics_extra.get('rows_class', 'medio')
        volume_desc = {
            'baixo': "O volume de dados é baixo, o que pode limitar a precisão.",
            'medio': "O volume de dados é adequado para análises confiáveis.",
            'alto': "O volume de dados é robusto, permitindo análises sólidas.",
            'muito_alto': "O volume de dados é muito alto, ideal para modelagem avançada."
        }
        parts.append(volume_desc.get(rows_class, ""))
        high_pct = metrics_extra.get('high_risk_pct', 0)
        if high_pct > 50:
            parts.append(f"Preocupação: {high_pct:.1f}% dos registros são de alto risco.")
        elif high_pct < 15:
            parts.append(f"Base sólida: apenas {high_pct:.1f}% em alto risco.")
        peak_day = metrics_extra.get('peak_day')
        peak_pct = metrics_extra.get('peak_day_pct', 0)
        if peak_day and peak_pct > 35:
            parts.append(f"Há concentração em {peak_day} ({peak_pct:.1f}% da receita semanal).")
        growth = metrics_extra.get('monthly_growth_pct', 0)
        if growth > 15:
            parts.append(f"Tendência mensal positiva (+{growth:.1f}%).")
        elif growth < -15:
            parts.append(f"Tendência mensal negativa ({growth:.1f}%).")
        if strengths:
            parts.append(f"Pontos fortes: {'; '.join(strengths[:3])}.")
        if weaknesses:
            parts.append(f"Pontos de atenção: {'; '.join(weaknesses[:3])}.")
        return " ".join(p for p in parts if p)

    @staticmethod
    def _calculate_file_score(file_metrics, metrics_extra) -> float:
        score = 5.0
        margin = file_metrics.margin
        if margin >= 45: score += 3.0
        elif margin >= 30: score += 2.0
        elif margin >= 20: score += 1.0
        elif margin >= 10: score += 0.0
        elif margin >= 0: score -= 1.5
        else: score -= 3.0
        high_pct = metrics_extra.get('high_risk_pct', 0)
        if high_pct < 15: score += 2.0
        elif high_pct < 30: score += 1.0
        elif high_pct < 50: score -= 1.0
        else: score -= 2.0
        growth = metrics_extra.get('monthly_growth_pct', 0)
        if growth > 20: score += 1.5
        elif growth > 5: score += 0.75
        elif growth < -20: score -= 1.5
        elif growth < -5: score -= 0.75
        cv = metrics_extra.get('monthly_cv', 0)
        if cv < 20: score += 1.0
        elif cv < 40: score += 0.5
        elif cv > 60: score -= 1.0
        return max(0, min(10, score))

    @staticmethod
    def analyze_multiple_files(consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        files = consolidated.files
        if not files:
            return IntelligentAnalyzer._empty_analysis()

        per_file_analysis = {f.filename: IntelligentAnalyzer.analyze_file(f) for f in files}

        file_scores = [a['score'] for a in per_file_analysis.values()]
        avg_score = sum(file_scores) / len(file_scores) if file_scores else 5.0

        comparison_data = {}
        if len(files) > 1:
            comparison_data = IntelligentAnalyzer._compare_files(files)

        trend_data = IntelligentAnalyzer._analyze_aggregate_trend(files)

        all_recommendations = []
        seen_descriptions = set()
        for filename, analysis in per_file_analysis.items():
            for rec in analysis['recommendations']:
                desc_key = rec['description'][:80]
                if desc_key not in seen_descriptions:
                    seen_descriptions.add(desc_key)
                    if len(files) > 1:
                        rec_copy = rec.copy()
                        rec_copy['source_file'] = filename
                        all_recommendations.append(rec_copy)
                    else:
                        all_recommendations.append(rec)

        priority_order = {'alta': 0, 'media': 1, 'baixa': 2}
        all_recommendations.sort(key=lambda r: priority_order.get(r.get('priority', 'media'), 1))
        all_recommendations = all_recommendations[:8]

        executive_score = IntelligentAnalyzer._build_executive_score(consolidated, per_file_analysis, avg_score)
        executive_summary = IntelligentAnalyzer._build_executive_summary(consolidated, per_file_analysis, comparison_data)
        forecast = IntelligentAnalyzer._build_forecast(consolidated, per_file_analysis, trend_data)
        conclusion = IntelligentAnalyzer._build_conclusion(consolidated, per_file_analysis, avg_score)

        combined_insights = []
        for filename, analysis in per_file_analysis.items():
            for insight in analysis['insights'][:3]:
                if len(files) > 1:
                    combined_insights.append(f"[{filename}] {insight}")
                else:
                    combined_insights.append(insight)

        return {
            'success': True,
            'executive_score': executive_score,
            'executive_summary': executive_summary,
            'comparison': comparison_data,
            'trend': trend_data,
            'recommendations': all_recommendations,
            'forecast': forecast,
            'conclusion': conclusion,
            'combined_insights': combined_insights[:10],
            'per_file_analysis': per_file_analysis,
            'model_used': 'intelligent_fallback',
            'tokens_used': 0,
            'response_time_ms': 0,
            'fallback_used': True,
            'full_analysis': executive_summary + "\n\n" + conclusion
        }

    @staticmethod
    def _compare_files(files):
        if len(files) < 2:
            return {}
        by_revenue = sorted(files, key=lambda f: f.total_revenue, reverse=True)
        by_profit = sorted(files, key=lambda f: f.profit, reverse=True)
        by_margin = sorted(files, key=lambda f: f.margin, reverse=True)
        by_risk = sorted(files, key=lambda f: f.high_risk_percentage)
        summary_parts = []
        if len(files) >= 2:
            best = by_revenue[0]
            worst = by_revenue[-1]
            diff_pct = ((best.total_revenue - worst.total_revenue) / worst.total_revenue * 100) if worst.total_revenue > 0 else 0
            summary_parts.append(
                f"'{best.filename}' lidera com R$ {best.total_revenue:,.2f} "
                f"({diff_pct:.1f}% acima de '{worst.filename}')."
            )
        riskiest = max(files, key=lambda f: f.high_risk_percentage)
        if riskiest.high_risk_percentage > 30:
            summary_parts.append(f"'{riskiest.filename}' tem {riskiest.high_risk_percentage:.1f}% de alto risco.")
        best_margin = by_margin[0]
        summary_parts.append(f"Melhor margem: '{best_margin.filename}' com {best_margin.margin:.1f}%.")
        return {
            'best_revenue': by_revenue[0].filename if by_revenue else '',
            'best_profit': by_profit[0].filename if by_profit else '',
            'best_growth': by_margin[0].filename if by_margin else '',
            'best_efficiency': by_margin[0].filename if by_margin else '',
            'highest_risk': riskiest.filename if riskiest else '',
            'lowest_performance': by_revenue[-1].filename if by_revenue else '',
            'summary': ' '.join(summary_parts),
            'ranking_revenue': [f.filename for f in by_revenue],
            'ranking_profit': [f.filename for f in by_profit],
            'ranking_margin': [f.filename for f in by_margin]
        }

    @staticmethod
    def _analyze_aggregate_trend(files):
        if len(files) < 2:
            return {
                'direction': 'estavel', 'strength': 0.5, 'confidence': 0.5,
                'description': 'Dados insuficientes para análise de tendência.',
                'key_observations': []
            }
        sorted_files = sorted(files, key=lambda f: f.filename)
        revenues = [f.total_revenue for f in sorted_files]
        if len(revenues) >= 2 and revenues[0] > 0:
            growth = (revenues[-1] - revenues[0]) / revenues[0] * 100
        else:
            growth = 0
        if growth > 10:
            direction = 'crescente'
            description = f"Tendência de crescimento de {growth:.1f}% entre os arquivos."
            strength = min(1.0, growth / 50)
            observations = [f"Receita cresceu {growth:.1f}%"]
        elif growth < -10:
            direction = 'decrescente'
            description = f"Tendência de queda de {abs(growth):.1f}% entre os arquivos."
            strength = min(1.0, abs(growth) / 50)
            observations = [f"Receita caiu {abs(growth):.1f}%"]
        else:
            direction = 'estavel'
            description = f"Estabilidade no período (variação de {growth:.1f}%)."
            strength = 0.5
            observations = ["Receita estável"]
        return {
            'direction': direction, 'strength': round(strength, 2),
            'confidence': 0.75, 'description': description,
            'key_observations': observations
        }

    @staticmethod
    def _build_executive_score(consolidated, per_file_analysis, avg_score):
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
        if consolidated.ml_results and consolidated.ml_results.total_predictions > 0:
            high_risk = consolidated.ml_results.risk_distribution.get('alto', 0)
            if high_risk < 15: growth = 8.0
            elif high_risk < 30: growth = 6.0
            elif high_risk < 50: growth = 4.0
            else: growth = 2.0
        if consolidated.ml_results:
            high_risk = consolidated.ml_results.risk_distribution.get('alto', 0)
            if high_risk < 15: nivel = 'Baixo'
            elif high_risk < 35: nivel = 'Moderado'
            else: nivel = 'Alto'
        else:
            nivel = 'Moderado'
        nota_geral = (saude + eficiencia + controle + growth) / 4
        return {
            'saude_financeira': round(saude, 1), 'eficiencia': round(eficiencia, 1),
            'controle_custos': round(controle, 1), 'crescimento': round(growth, 1),
            'nivel_risco': nivel, 'nota_geral': round(nota_geral, 1)
        }

    @staticmethod
    def _build_executive_summary(consolidated, per_file_analysis, comparison_data):
        parts = []
        n_files = consolidated.processed_files
        total_rows = sum(f.total_rows for f in consolidated.files)
        if n_files == 1:
            f = consolidated.files[0]
            parts.append(f"Análise completa de '{f.filename}' com {total_rows} registros processados.")
        else:
            parts.append(f"Análise comparativa de {n_files} arquivos com {total_rows} registros no total.")
        parts.append(
            f"Receita total de R$ {consolidated.total_revenue:,.2f}, "
            f"lucro de R$ {consolidated.total_profit:,.2f} "
            f"e margem média de {consolidated.avg_margin:.1f}%."
        )
        margin = consolidated.avg_margin
        if margin >= 45: parts.append("A margem está em nível excelente, acima da média do setor.")
        elif margin >= 30: parts.append("A margem é saudável e sustentável.")
        elif margin >= 20: parts.append("A margem é aceitável, mas há espaço para otimização.")
        elif margin >= 10: parts.append("A margem é baixa — atenção aos custos operacionais.")
        elif margin >= 0: parts.append("A margem é crítica — ação corretiva necessária.")
        else: parts.append("A operação está em prejuízo — intervenção imediata requerida.")
        if comparison_data and comparison_data.get('summary'):
            parts.append(comparison_data['summary'])
        if consolidated.ml_results:
            high_risk = consolidated.ml_results.risk_distribution.get('alto', 0)
            if high_risk > 40:
                parts.append(f"Alerta: {high_risk:.1f}% dos registros em alto risco.")
            elif high_risk < 15:
                parts.append(f"Base sólida: apenas {high_risk:.1f}% em alto risco.")
        return " ".join(parts)

    @staticmethod
    def _build_forecast(consolidated, per_file_analysis, trend_data):
        margin = consolidated.avg_margin
        direction = trend_data.get('direction', 'estavel')
        if margin >= 30 and direction == 'crescente':
            return ("Cenário otimista: com margem saudável e tendência de crescimento, "
                    "espera-se expansão sustentada nos próximos períodos. "
                    "Recomenda-se preparar estrutura para absorver aumento de demanda.")
        elif margin >= 20 and direction == 'crescente':
            return ("Cenário positivo: margem aceitável combinada com crescimento. "
                    "Mantenha o foco em eficiência operacional para consolidar a expansão.")
        elif margin >= 30 and direction == 'estavel':
            return ("Cenário estável: margem saudável com receita consistente. "
                    "Boa base para investimentos em crescimento planejado.")
        elif margin < 10 and direction == 'decrescente':
            return ("Cenário de atenção: margem baixa com tendência de queda. "
                    "Ação corretiva urgente necessária para reverter o quadro.")
        elif margin < 20 and direction == 'decrescente':
            return ("Cenário de cautela: margem sob pressão e receita em queda. "
                    "Revisar precificação e estrutura de custos.")
        elif margin < 10:
            return ("Cenário crítico: margem baixa exige intervenção. "
                    "Priorizar corte de custos e renegociação com fornecedores.")
        else:
            return ("Cenário neutro: indicadores estáveis. "
                    "Manter monitoramento contínuo e buscar oportunidades de otimização.")

    @staticmethod
    def _build_conclusion(consolidated, per_file_analysis, avg_score):
        parts = []
        if avg_score >= 8: parts.append(f"Desempenho geral excelente (score {avg_score:.1f}/10).")
        elif avg_score >= 6: parts.append(f"Desempenho geral bom (score {avg_score:.1f}/10).")
        elif avg_score >= 4: parts.append(f"Desempenho geral regular (score {avg_score:.1f}/10).")
        else: parts.append(f"Desempenho geral abaixo do esperado (score {avg_score:.1f}/10).")
        if len(per_file_analysis) > 1:
            scores = {name: a['score'] for name, a in per_file_analysis.items()}
            best = max(scores.items(), key=lambda x: x[1])
            worst = min(scores.items(), key=lambda x: x[1])
            parts.append(
                f"Melhor desempenho: '{best[0]}' ({best[1]:.1f}/10). "
                f"Ponto de atenção: '{worst[0]}' ({worst[1]:.1f}/10)."
            )
        elif len(per_file_analysis) == 1:
            name, analysis = list(per_file_analysis.items())[0]
            parts.append(f"Score do arquivo: {analysis['score']:.1f}/10.")
            if analysis['strengths']:
                parts.append(f"Principais forças: {'; '.join(analysis['strengths'][:2])}.")
            if analysis['weaknesses']:
                parts.append(f"Principais fragilidades: {'; '.join(analysis['weaknesses'][:2])}.")
        return " ".join(parts)

    @staticmethod
    def _empty_analysis():
        return {
            'success': False,
            'executive_score': {
                'saude_financeira': 5.0, 'eficiencia': 5.0,
                'controle_custos': 5.0, 'crescimento': 5.0,
                'nivel_risco': 'Moderado', 'nota_geral': 5.0
            },
            'executive_summary': 'Análise indisponível.',
            'comparison': {},
            'trend': {'direction': 'estavel', 'strength': 0.5, 'confidence': 0.5,
                     'description': 'Sem dados.', 'key_observations': []},
            'recommendations': [],
            'forecast': 'Sem dados suficientes para previsão.',
            'conclusion': 'Análise não pôde ser concluída.',
            'combined_insights': [],
            'per_file_analysis': {},
            'model_used': 'intelligent_fallback',
            'tokens_used': 0,
            'response_time_ms': 0,
            'fallback_used': True,
            'full_analysis': 'Análise indisponível.'
        }


# ==============================================
# CLASSE PRINCIPAL - ANALISADOR V6.3
# ==============================================

class MultiFileAnalyzerV6:
    """
    🔥 Analisador de múltiplos arquivos - V6.3
    Com GEMINI DINÂMICO + CIRCUIT BREAKER + FALLBACK INTELIGENTE.
    """

    MAX_FILES = 3
    CACHE_TTL = 300
    MAX_CONCURRENT = 3
    TIMEOUT_SECONDS = 60
    NORMALIZATION = "Z-Score"

    # Configuração do circuit breaker do Gemini
    GEMINI_CHECK_TTL = 10.0           # micro-cache da checagem
    GEMINI_CIRCUIT_THRESHOLD = 3      # falhas consecutivas p/ abrir
    GEMINI_CIRCUIT_COOLDOWN = 30.0    # segundos em OPEN antes de HALF_OPEN

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT)
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        self._cache: Dict[str, Tuple[Dict[str, Any], float, int]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        self._chart_cache: Dict[str, Dict[str, Any]] = {}
        self._chart_cache_ttl = 300

        # ==========================================
        # Estado do Gemini (NÃO CONGELADO)
        # ==========================================
        self.gemini = None
        self.is_gemini_available = False          # hint atualizado dinamicamente
        self._gemini_last_check = 0.0
        self._gemini_last_result = False
        self._gemini_lock = asyncio.Lock()

        # Circuit breaker
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
        logger.info("✅ MultiFileAnalyzerV6.3 inicializado (GEMINI DINÂMICO)")
        logger.info("=" * 60)
        logger.info(f"   📁 Máximo de arquivos: {self.MAX_FILES}")
        logger.info(f"   💾 Cache TTL: {self.CACHE_TTL}s")
        logger.info(f"   🔄 Processamento paralelo: {self.MAX_CONCURRENT}")
        logger.info(f"   📊 Normalização: {self.NORMALIZATION}")
        logger.info(f"   🔥 Predictor V7.0: {'✅' if self.predictor else '❌'}")
        logger.info(f"   🤖 Gemini (estado inicial): {'✅' if self.is_gemini_available else '⚠️'}")
        logger.info(f"   🛡️  Circuit breaker: threshold={self.GEMINI_CIRCUIT_THRESHOLD}, cooldown={self.GEMINI_CIRCUIT_COOLDOWN}s")
        logger.info("=" * 60)

    # ==========================================
    # 🔄 GEMINI: REVALIDAÇÃO DINÂMICA + CIRCUIT BREAKER
    # ==========================================

    def _load_dependencies(self):
        """Carrega pipeline ML. Gemini NÃO é congelado — só dica inicial."""
        try:
            from backend.preprocessing import pipeline, process_file_content
            self.pipeline = pipeline
            self.process_file = process_file_content
            logger.info("   ✅ ML Pipeline carregado")
        except ImportError:
            logger.exception("   ⚠️ ML Pipeline não disponível")
            self.pipeline = None
            self.process_file = None

        # Gemini: apenas hint — revalidação acontece sob demanda
        try:
            from backend.gemini import get_gemini_service
            self.gemini = get_gemini_service()
            # Checagem única, mas NÃO congelante
            try:
                self.is_gemini_available = self._gemini_check_impl()
            except Exception:
                logger.exception("   ⚠️ Erro no health check inicial do Gemini "
                                 "(será revalidado dinamicamente)")
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

    # ---------- Circuit breaker ----------

    def _circuit_is_open(self) -> bool:
        if self._gemini_circuit_state != CircuitState.OPEN:
            return False
        # Cooldown expirado? Transiciona para HALF_OPEN
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
            # Falhou no teste → reabre
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
        """Reset manual (útil para /admin/health/reset)."""
        self._gemini_circuit_state = CircuitState.CLOSED
        self._gemini_failure_count = 0
        self._gemini_circuit_opened_at = 0.0
        self._gemini_last_error = None
        self._gemini_last_check = 0.0
        self._gemini_last_result = False
        logger.info("🛡️  Circuit breaker Gemini resetado manualmente")

    # ---------- Checagem dinâmica ----------

    def _gemini_check_impl(self) -> bool:
        """
        Implementação pura da checagem. Não usa micro-cache.
        Levanta exceções? Não — sempre retorna bool e loga com exception.
        """
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
        """
        Verifica dinamicamente se o Gemini está disponível.
        - Usa micro-cache de GEMINI_CHECK_TTL segundos (evita overhead em bursts)
        - Respeita o circuit breaker (bloqueia se OPEN)
        - `force=True` ignora micro-cache (usado em /health e chamadas críticas)
        """
        self._stats["gemini_check_calls"] += 1

        # Circuit breaker aberto? Bloqueia
        if self._circuit_is_open():
            self.is_gemini_available = False
            self._gemini_last_result = False
            return False

        now = time.time()

        # Micro-cache
        if not force and (now - self._gemini_last_check) < self.GEMINI_CHECK_TTL:
            return self._gemini_last_result

        # Revalida
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
        """Força revalidação na próxima chamada."""
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
        normalize: bool = True
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

        # BUGFIX #9: clamp de timeout
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
                'normalization': self.NORMALIZATION if normalize else "None"
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
        if len(files) < 2: return ""
        best = max(files, key=lambda x: x.total_revenue)
        worst = min(files, key=lambda x: x.total_revenue)
        return (f"'{best.filename}' apresentou a maior receita "
                f"(R$ {best.total_revenue:,.2f}), enquanto '{worst.filename}' "
                f"teve o menor desempenho (R$ {worst.total_revenue:,.2f}).")

    def _analyze_trend(self, files: List[FileMetrics]) -> TrendResults:
        if len(files) < 2:
            return TrendResults(direction=TrendDirection.ESTAVEL, strength=0.5,
                                confidence=0.5, description="Dados insuficientes.")
        sorted_files = sorted(files, key=lambda x: x.filename)
        revenues = [f.total_revenue for f in sorted_files]
        growth_rate = (revenues[-1] - revenues[0]) / revenues[0] if revenues[0] > 0 else 0
        if growth_rate > 0.05:
            direction = TrendDirection.CRESCENTE
            description = f"Tendência de crescimento de {growth_rate*100:.1f}%."
        elif growth_rate < -0.05:
            direction = TrendDirection.DECRESCENTE
            description = f"Tendência de queda de {abs(growth_rate)*100:.1f}%."
        else:
            direction = TrendDirection.ESTAVEL
            description = "Estabilidade no período."
        observations = []
        if abs(growth_rate) > 0.1:
            observations.append(f"Variação significativa: {growth_rate*100:.1f}%")
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
    # 🔥 GEMINI + FALLBACK (AGORA DINÂMICO)
    # ==========================================

    async def _generate_gemini_analysis(self, consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info("🤖 INICIANDO ANÁLISE")

        # ✅ ÚNICA VERIFICAÇÃO (não mais triple-check)
        gemini_ok = self._gemini_is_ready()

        if not gemini_ok:
            logger.warning("⚠️ Gemini indisponível - usando FALLBACK INTELIGENTE")
            self._stats["fallback_used_count"] += 1
            return IntelligentAnalyzer.analyze_multiple_files(consolidated)

        # Tentar Gemini
        try:
            logger.info("📤 Enviando para Gemini...")
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
                logger.warning("⚠️ Gemini falhou - usando FALLBACK")
                self._mark_gemini_failure(RuntimeError("Resposta sem sucesso"))
                self.invalidate_gemini_cache()
                return IntelligentAnalyzer.analyze_multiple_files(consolidated)

            full_text = response.get('full_analysis', '')
            if not full_text or len(full_text) < 50:
                logger.warning("⚠️ Resposta Gemini muito curta - usando FALLBACK")
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
                'fallback_used': False
            }

        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout do Gemini - usando FALLBACK")
            self._stats["gemini_timeouts"] += 1
            self._mark_gemini_failure(asyncio.TimeoutError("Timeout 60s"))
            self.invalidate_gemini_cache()
            return IntelligentAnalyzer.analyze_multiple_files(consolidated)
        except Exception as e:
            logger.exception("⚠️ Erro no Gemini - usando FALLBACK")
            self._mark_gemini_failure(e)
            self.invalidate_gemini_cache()
            return IntelligentAnalyzer.analyze_multiple_files(consolidated)

    # ==========================================
    # PARSERS DO GEMINI (com regex melhoradas)
    # ==========================================

    def _parse_executive_score(self, text: str) -> Dict[str, Any]:
        scores = {
            'saude_financeira': 5.0, 'eficiencia': 5.0,
            'controle_custos': 5.0, 'crescimento': 5.0,
            'nivel_risco': 'Moderado', 'nota_geral': 5.0
        }
        # BUGFIX #5: regex mais tolerante (aceita "/10", "de 10", etc.)
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
    # BUILD RESULT (com fallback em vez de RuntimeError)
    # ==========================================

    def _build_result(
        self, files, processed_results, consolidated, gemini_analysis,
        processing_time_ms, normalize=True
    ) -> MultiFileAnalysisResult:
        success_count = sum(1 for r in processed_results if r.get('success'))

        # BUGFIX #8: não crashar se gemini_analysis inválido — usa fallback
        if not gemini_analysis or not gemini_analysis.get('success', False):
            logger.warning("⚠️ gemini_analysis inválido — aplicando fallback local")
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
            model_version="V6.3", feature_count_avg=int(avg_feature_count),
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
            # BUGFIX #6: validação robusta
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
    # CACHE (com deepcopy)
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
                # BUGFIX #7: deepcopy evita mutação acidental
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
        # BUGFIX #10: campos preenchidos
        return MultiFileAnalysisResult(
            success=False, status=AnalysisStatus.FAILED.value,
            progress=1.0, total_files=0, processed_files=0,
            failed_files=0, error=error,
            timestamp=datetime.now().isoformat(),
            model_version="V6.3"
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
        # Usa micro-cache para não forçar revalidação a cada chamada
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
            "normalization": self.NORMALIZATION
        }

    def get_health_status(self) -> Dict[str, Any]:
        # Force=True: sempre revalida (endpoint de health)
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
            "model_version": "V6.3",
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
# TESTE (com teste específico de revalidação)
# ==============================================

async def test_multi_analysis():
    print("\n" + "=" * 70)
    print("🧪 TESTANDO ANÁLISE MÚLTIPLA V6.3 (GEMINI DINÂMICO)")
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
        print(f"\n📝 RESUMO: {result.get('executive_summary', '')[:200]}")
        print("\n✅ Teste concluído!")
        return result
    except Exception as e:
        print(f"\n❌ TESTE FALHOU: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_gemini_revalidation():
    """Testa especificamente a revalidação dinâmica do Gemini."""
    print("\n" + "=" * 70)
    print("🧪 TESTANDO REVALIDAÇÃO DINÂMICA DO GEMINI")
    print("=" * 70)
    analyzer = get_multi_analyzer()

    # Estado inicial
    print(f"\n1️⃣ Estado inicial: is_gemini_available={analyzer.is_gemini_available}")

    # Força estado "congelado" (simula V6.2)
    analyzer.is_gemini_available = False
    analyzer.invalidate_gemini_cache()
    print(f"2️⃣ Após forçar False: is_gemini_available={analyzer.is_gemini_available}")

    # Revalida
    ready = analyzer._gemini_is_ready(force=True)
    print(f"3️⃣ Após revalidação: ready={ready}, is_gemini_available={analyzer.is_gemini_available}")

    # Health
    health = analyzer.get_health_status()
    print(f"4️⃣ Health status: gemini={health['gemini']}, circuit={health['gemini_circuit_state']}")

    # Testa circuit breaker
    print("\n5️⃣ Testando circuit breaker (3 falhas simuladas)...")
    for i in range(3):
        analyzer._mark_gemini_failure(RuntimeError(f"falha_simulada_{i}"))
    print(f"   Estado do circuit: {analyzer._gemini_circuit_state.value}")
    print(f"   Deve bloquear: {analyzer._gemini_is_ready(force=True)}")

    # Reset manual
    print("\n6️⃣ Reset manual do circuit...")
    analyzer._reset_gemini_circuit()
    print(f"   Estado após reset: {analyzer._gemini_circuit_state.value}")

    print("\n✅ Teste de revalidação concluído!")


if __name__ == "__main__":
    asyncio.run(test_multi_analysis())
    asyncio.run(test_gemini_revalidation())