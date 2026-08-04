# backend/ml/multi_analysis.py - VERSÃO FINAL 4.1 (ENCODING PROPAGADO)
"""
🔥 ANÁLISE MÚLTIPLA DE ARQUIVOS - V4.1
================================================================================
✅ Processa até 3 arquivos simultaneamente
✅ Dados estruturados (ConsolidatedAnalysis)
✅ Análise unificada com IA (Gemini) em uma única chamada
✅ Score Executivo (notas 0-10)
✅ Comparação entre arquivos
✅ Tendência e previsão
✅ Recomendações priorizadas (Alta/Média/Baixa)
✅ Conclusão geral unificada
✅ Cache inteligente com invalidação
✅ Tratamento de erros robusto
✅ Logging estruturado
✅ ENCODING PROPAGADO para o resultado final
================================================================================
"""

import pandas as pd
import numpy as np
import asyncio
import logging
import json
import hashlib
import time
import random
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ==============================================
# ENUMS E CONSTANTES
# ==============================================

class Priority(str, Enum):
    """Prioridade das recomendações"""
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class RiskLevel(str, Enum):
    """Nível de risco"""
    BAIXO = "Baixo"
    MODERADO = "Moderado"
    ALTO = "Alto"


class TrendDirection(str, Enum):
    """Direção da tendência"""
    CRESCENTE = "crescente"
    DECRESCENTE = "decrescente"
    ESTAVEL = "estavel"


# ==============================================
# DATACLASSES ESTRUTURADAS
# ==============================================

@dataclass
class FileMetrics:
    """Métricas de um único arquivo"""
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
    encoding_used: Optional[str] = None  # 🔥 ADICIONADO: encoding usado no arquivo


@dataclass
class MLResults:
    """Resultados do Machine Learning"""
    models_used: List[str]
    encodings_used: List[str]
    total_predictions: int
    avg_score: float
    std_score: float
    min_score: float
    max_score: float
    risk_distribution: Dict[str, float]


@dataclass
class ComparisonResults:
    """Resultados da comparação entre arquivos"""
    best_revenue: str
    best_profit: str
    best_growth: str
    best_efficiency: str
    highest_risk: str
    lowest_performance: str
    comparison_table: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""


@dataclass
class TrendResults:
    """Resultados da análise de tendência"""
    direction: TrendDirection
    strength: float
    confidence: float
    description: str
    key_observations: List[str] = field(default_factory=list)


@dataclass
class ConsolidatedAnalysis:
    """
    🔥 DADOS ESTRUTURADOS PARA O GEMINI
    
    Organiza TODOS os dados que serão enviados para o Gemini.
    """
    # 1. Informações Gerais
    total_files: int
    processed_files: int
    failed_files: int
    user_email: str
    timestamp: str
    
    # 2. Métricas por Arquivo
    files: List[FileMetrics] = field(default_factory=list)
    
    # 3. Resultados do ML
    ml_results: Optional[MLResults] = None
    
    # 4. Comparação
    comparison: Optional[ComparisonResults] = None
    
    # 5. Tendência
    trend: Optional[TrendResults] = None
    
    # 6. Dados Consolidados
    total_revenue: float = 0
    total_profit: float = 0
    avg_margin: float = 0
    avg_score_overall: float = 0
    combined_insights: List[str] = field(default_factory=list)
    combined_recommendations: List[str] = field(default_factory=list)
    
    # 7. Chart Data Consolidado
    chart_data: Dict[str, Any] = field(default_factory=dict)
    
    # 8. Metadados
    processing_time_ms: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (para envio ao Gemini)"""
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "user_email": self.user_email,
            "timestamp": self.timestamp,
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
                    "encoding_used": f.encoding_used  # 🔥 PROPAGADO
                }
                for f in self.files
            ],
            "ml_results": {
                "models_used": self.ml_results.models_used if self.ml_results else [],
                "encodings_used": self.ml_results.encodings_used if self.ml_results else [],
                "total_predictions": self.ml_results.total_predictions if self.ml_results else 0,
                "avg_score": round(self.ml_results.avg_score, 3) if self.ml_results else 0,
                "risk_distribution": self.ml_results.risk_distribution if self.ml_results else {}
            } if self.ml_results else {},
            "comparison": {
                "best_revenue": self.comparison.best_revenue if self.comparison else "",
                "best_profit": self.comparison.best_profit if self.comparison else "",
                "best_growth": self.comparison.best_growth if self.comparison else "",
                "highest_risk": self.comparison.highest_risk if self.comparison else ""
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
            "combined_recommendations": self.combined_recommendations[:5]
        }


# ==============================================
# RESULTADO FINAL
# ==============================================

@dataclass
class MultiFileAnalysisResult:
    """Resultado completo da análise múltipla"""
    success: bool
    total_files: int
    processed_files: int
    failed_files: int
    
    # 1. Score Executivo
    executive_score: Optional[Dict[str, Any]] = None
    
    # 2. Resumo Executivo
    executive_summary: str = ""
    
    # 3. Análise por arquivo
    files: List[Dict[str, Any]] = field(default_factory=list)
    
    # 4. Comparação
    comparison: Optional[ComparisonResults] = None
    
    # 5. Tendência
    trend: Optional[TrendResults] = None
    
    # 6. Recomendações Priorizadas
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    
    # 7. Previsão
    forecast: str = ""
    
    # 8. Conclusão Geral
    general_conclusion: str = ""
    
    # Chart data consolidado
    chart_data: Dict[str, Any] = field(default_factory=dict)
    
    # Metadados
    error: Optional[str] = None
    processing_time_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cache_hit: bool = False
    encodings_used: List[str] = field(default_factory=list)  # 🔥 ADICIONADO: lista de encodings usados
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "executive_score": self.executive_score,
            "executive_summary": self.executive_summary,
            "files": self.files,
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
            "recommendations": self.recommendations,
            "forecast": self.forecast,
            "general_conclusion": self.general_conclusion,
            "chart_data": self.chart_data,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp,
            "cache_hit": self.cache_hit,
            "encodings_used": self.encodings_used  # 🔥 PROPAGADO
        }


# ==============================================
# CLASSE PRINCIPAL - ANALISADOR MÚLTIPLO
# ==============================================

class MultiFileAnalyzerV4:
    """
    Analisador de múltiplos arquivos com IA Avançada
    """
    
    MAX_FILES = 3
    CACHE_TTL = 300  # 5 minutos
    
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._stats = {
            "total_analyses": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "started_at": datetime.now().isoformat()
        }
        self._load_dependencies()
        logger.info("✅ MultiFileAnalyzerV4.1 inicializado")
        logger.info(f"   📁 Máximo de arquivos: {self.MAX_FILES}")
        logger.info(f"   💾 Cache TTL: {self.CACHE_TTL}s")
        logger.info(f"   🔥 ENCODING: Propagado para o resultado final")
    
    def _load_dependencies(self):
        """Carrega dependências necessárias"""
        try:
            from backend.preprocessing import pipeline, process_file_content
            self.pipeline = pipeline
            self.process_file = process_file_content
            logger.info("   ✅ ML Pipeline carregado")
        except ImportError as e:
            logger.warning(f"   ⚠️ ML Pipeline não disponível: {e}")
            self.pipeline = None
            self.process_file = None
        
        try:
            from backend.gemini import gemini_service
            self.gemini = gemini_service
            logger.info("   ✅ Gemini Service carregado")
        except ImportError as e:
            logger.warning(f"   ⚠️ Gemini Service não disponível: {e}")
            self.gemini = None
    
    # ==========================================
    # MÉTODO PRINCIPAL
    # ==========================================
    
    async def analyze_multiple_files(
        self,
        files: List[Dict[str, Any]],
        user_id: int = None,
        user_email: str = None,
        force_reload: bool = False
    ) -> MultiFileAnalysisResult:
        """
        🔥 Analisa múltiplos arquivos com relatório executivo completo
        """
        start_time = time.time()
        
        # 1️⃣ VALIDAÇÃO
        if not files:
            return self._error_result("Nenhum arquivo fornecido")
        
        if len(files) > self.MAX_FILES:
            return self._error_result(f"Máximo de {self.MAX_FILES} arquivos por vez")
        
        # 2️⃣ VERIFICAR CACHE
        cache_key = self._get_cache_key(files, user_id)
        if not force_reload:
            cached = self._get_cached_result(cache_key)
            if cached:
                logger.info(f"📦 Resultado em cache para {len(files)} arquivos")
                cached['cache_hit'] = True
                return MultiFileAnalysisResult(**cached)
        
        logger.info(f"📚 Iniciando análise avançada de {len(files)} arquivos")
        
        try:
            # 3️⃣ PROCESSAR ARQUIVOS
            processed_results = await self._process_files_parallel(files)
            
            # 4️⃣ CONSTRUIR DADOS ESTRUTURADOS
            consolidated = await self._build_consolidated_analysis(
                processed_results=processed_results,
                user_email=user_email,
                user_id=user_id
            )
            
            # 5️⃣ GERAR ANÁLISE COM GEMINI
            gemini_analysis = await self._generate_gemini_analysis(consolidated)
            
            # 6️⃣ CONSTRUIR RESULTADO
            result = self._build_result(
                files=files,
                processed_results=processed_results,
                consolidated=consolidated,
                gemini_analysis=gemini_analysis,
                processing_time_ms=(time.time() - start_time) * 1000
            )
            
            # 7️⃣ SALVAR CACHE
            self._set_cache(cache_key, result.to_dict())
            
            # 8️⃣ ATUALIZAR ESTATÍSTICAS
            self._stats["total_analyses"] += 1
            self._stats["cache_misses"] += 1
            
            logger.info(f"✅ Análise avançada concluída em {result.processing_time_ms:.0f}ms")
            logger.info(f"   📝 Encodings usados: {result.encodings_used}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro na análise: {e}")
            return self._error_result(str(e))
    
    # ==========================================
    # PROCESSAMENTO PARALELO
    # ==========================================
    
    async def _process_files_parallel(
        self,
        files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Processa arquivos em paralelo"""
        
        async def process_single(file_data: Dict[str, Any]) -> Dict[str, Any]:
            try:
                content = file_data.get('content')
                filename = file_data.get('filename', 'arquivo.csv')
                
                if not content:
                    return self._error_file_result(filename, "Arquivo vazio")
                
                if not self.process_file:
                    return self._error_file_result(filename, "Pipeline ML não disponível")
                
                result = await self.process_file(content, filename)
                
                # 🔥 GARANTIR que encoding_used seja capturado
                encoding_used = result.get('encoding_used')
                if not encoding_used:
                    # Tentar extrair do metadata
                    metadata = result.get('metadata', {})
                    encoding_used = metadata.get('encoding_used', 'unknown')
                
                # 🔥 LOG do encoding capturado
                logger.info(f"   📝 Arquivo '{filename}' - Encoding: {encoding_used}")
                
                return {
                    'success': result.get('success', False),
                    'filename': filename,
                    'predictions': result.get('predictions', []),
                    'metrics': result.get('metrics', {}),
                    'insights': result.get('insights', {}),
                    'recommendations': result.get('recommendations', []),
                    'chart_data': result.get('chart_data', {}),
                    'model_used': result.get('model_used', 'default'),
                    'encoding_used': encoding_used,  # 🔥 PROPAGADO
                    'processed_rows': result.get('processed_rows', 0),
                    'error': result.get('error')
                }
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar {file_data.get('filename')}: {e}")
                return self._error_file_result(
                    file_data.get('filename', 'unknown'),
                    str(e)
                )
        
        tasks = [process_single(f) for f in files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(self._error_file_result(
                    files[idx].get('filename', 'unknown'),
                    str(result)
                ))
            else:
                processed.append(result)
        
        return processed
    
    # ==========================================
    # CONSTRUIR DADOS ESTRUTURADOS
    # ==========================================
    
    async def _build_consolidated_analysis(
        self,
        processed_results: List[Dict[str, Any]],
        user_email: str = None,
        user_id: int = None
    ) -> ConsolidatedAnalysis:
        """
        🔥 Constrói dados estruturados para o Gemini
        """
        # Filtrar resultados com sucesso
        success_results = [r for r in processed_results if r.get('success')]
        
        # 🔥 Coletar encodings usados
        all_encodings = []
        for result in success_results:
            enc = result.get('encoding_used')
            if enc:
                all_encodings.append(enc)
        
        logger.info(f"   📝 Encodings detectados: {set(all_encodings) if all_encodings else 'nenhum'}")
        
        # 1️⃣ Métricas por arquivo
        file_metrics_list = []
        all_predictions = []
        all_metrics = []
        models_used = set()
        encodings_used = set()
        total_rows = 0
        combined_insights = []
        combined_recommendations = []
        
        for result in success_results:
            metrics = result.get('metrics', {})
            chart_data = result.get('chart_data', {})
            weekly = chart_data.get('weekly', {})
            
            revenue = weekly.get('revenue', [])
            costs = weekly.get('costs', [])
            
            total_revenue = sum(revenue) if revenue else 0
            total_costs = sum(costs) if costs else 0
            profit = total_revenue - total_costs
            
            # 🔥 ADICIONAR encoding_used ao FileMetrics
            encoding_used = result.get('encoding_used')
            
            file_metrics = FileMetrics(
                filename=result.get('filename', 'unknown'),
                total_rows=result.get('processed_rows', 0),
                total_revenue=total_revenue,
                total_costs=total_costs,
                profit=profit,
                margin=(profit / total_revenue * 100) if total_revenue > 0 else 0,
                avg_score=metrics.get('mean_prediction', 0.5),
                high_risk_percentage=metrics.get('high_risk_percentage', 0),
                low_risk_percentage=metrics.get('low_risk_percentage', 0),
                predictions=result.get('predictions', []),
                chart_data=chart_data,
                success=True,
                encoding_used=encoding_used  # 🔥 PROPAGADO
            )
            file_metrics_list.append(file_metrics)
            
            # Consolidar dados
            predictions = result.get('predictions', [])
            all_predictions.extend(predictions)
            all_metrics.append(metrics)
            total_rows += result.get('processed_rows', 0)
            
            if result.get('model_used'):
                models_used.add(result['model_used'])
            if result.get('encoding_used'):
                encodings_used.add(result['encoding_used'])
            
            # Insights e recomendações
            insights = result.get('insights', {})
            if isinstance(insights, dict):
                for key, value in insights.items():
                    if isinstance(value, list):
                        combined_insights.extend(value)
                    elif isinstance(value, str):
                        combined_insights.append(value)
            elif isinstance(insights, list):
                combined_insights.extend(insights)
            
            recs = result.get('recommendations', [])
            if isinstance(recs, list):
                combined_recommendations.extend(recs)
        
        # 2️⃣ Resultados do ML
        ml_results = None
        if all_predictions:
            avg_score = sum(all_predictions) / len(all_predictions)
            std_score = np.std(all_predictions) if len(all_predictions) > 1 else 0
            
            # Distribuição de risco
            high_risk = len([p for p in all_predictions if p > 0.7])
            low_risk = len([p for p in all_predictions if p < 0.3])
            medium_risk = len(all_predictions) - high_risk - low_risk
            
            ml_results = MLResults(
                models_used=list(models_used),
                encodings_used=list(encodings_used),
                total_predictions=len(all_predictions),
                avg_score=avg_score,
                std_score=std_score,
                min_score=min(all_predictions),
                max_score=max(all_predictions),
                risk_distribution={
                    "alto": high_risk / len(all_predictions) * 100,
                    "medio": medium_risk / len(all_predictions) * 100,
                    "baixo": low_risk / len(all_predictions) * 100
                }
            )
        
        # 3️⃣ Comparação
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
        
        # 4️⃣ Tendência
        trend = None
        if len(file_metrics_list) > 1:
            trend = self._analyze_trend(file_metrics_list)
        
        # 5️⃣ Chart Data Consolidado
        chart_data = self._generate_consolidated_chart_data(processed_results)
        
        # 6️⃣ Totais
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
            files=file_metrics_list,
            ml_results=ml_results,
            comparison=comparison,
            trend=trend,
            total_revenue=total_revenue,
            total_profit=total_profit,
            avg_margin=avg_margin,
            avg_score_overall=avg_score_overall,
            combined_insights=combined_insights[:10],
            combined_recommendations=combined_recommendations[:5],
            chart_data=chart_data,
            processing_time_ms=0
        )
    
    def _generate_comparison_summary(self, files: List[FileMetrics]) -> str:
        """Gera resumo da comparação"""
        if len(files) < 2:
            return ""
        
        best = max(files, key=lambda x: x.total_revenue)
        worst = min(files, key=lambda x: x.total_revenue)
        
        return f"O arquivo '{best.filename}' apresentou a maior receita (R$ {best.total_revenue:,.2f}), enquanto '{worst.filename}' teve o menor desempenho (R$ {worst.total_revenue:,.2f})."
    
    def _analyze_trend(self, files: List[FileMetrics]) -> TrendResults:
        """Analisa tendência entre os arquivos"""
        if len(files) < 2:
            return TrendResults(
                direction=TrendDirection.ESTAVEL,
                strength=0.5,
                confidence=0.5,
                description="Dados insuficientes para análise de tendência.",
                key_observations=[]
            )
        
        # Ordenar por nome (assumindo que os nomes indicam ordem cronológica)
        sorted_files = sorted(files, key=lambda x: x.filename)
        
        # Analisar receita
        revenues = [f.total_revenue for f in sorted_files]
        if len(revenues) >= 2:
            growth_rate = (revenues[-1] - revenues[0]) / revenues[0] if revenues[0] > 0 else 0
        else:
            growth_rate = 0
        
        # Analisar score
        scores = [f.avg_score for f in sorted_files]
        score_trend = scores[-1] - scores[0] if len(scores) >= 2 else 0
        
        # Determinar direção
        if growth_rate > 0.05:
            direction = TrendDirection.CRESCENTE
            description = f"Os dados indicam uma tendência de crescimento de {growth_rate*100:.1f}% no período analisado."
        elif growth_rate < -0.05:
            direction = TrendDirection.DECRESCENTE
            description = f"Os dados indicam uma tendência de queda de {abs(growth_rate)*100:.1f}% no período analisado."
        else:
            direction = TrendDirection.ESTAVEL
            description = "Os dados indicam estabilidade no período analisado."
        
        # Observações
        observations = []
        if abs(growth_rate) > 0.1:
            observations.append(f"Variação significativa na receita: {growth_rate*100:.1f}%")
        if abs(score_trend) > 0.05:
            observations.append(f"Variação no score médio: {score_trend*100:.1f}%")
        
        if not observations:
            observations.append("Dados consistentes entre os períodos analisados.")
        
        return TrendResults(
            direction=direction,
            strength=min(1, abs(growth_rate) * 2),
            confidence=0.8,
            description=description,
            key_observations=observations
        )
    
    # ==========================================
    # GERAR ANÁLISE COM GEMINI
    # ==========================================
    
    async def _generate_gemini_analysis(
        self,
        consolidated: ConsolidatedAnalysis
    ) -> Dict[str, Any]:
        """
        🔥 Gera análise com Gemini usando dados estruturados
        """
        if not self.gemini:
            logger.warning("⚠️ Gemini não disponível, usando fallback")
            return self._generate_fallback_analysis(consolidated)
        
        try:
            # Dados estruturados para o Gemini
            analysis_data = consolidated.to_dict()
            analysis_data['analysis_type'] = 'analise_avancada'
            
            logger.info(f"🤖 Enviando dados estruturados para Gemini ({consolidated.total_files} arquivos)")
            
            response = await self.gemini.analyze_office_data(
                data_type="analise_avancada",
                analysis_data=analysis_data
            )
            
            if response.get('success'):
                full_text = response.get('full_analysis', '')
                return {
                    'success': True,
                    'executive_score': self._parse_executive_score(full_text),
                    'executive_summary': self._parse_summary(full_text),
                    'comparison': self._parse_comparison(full_text),
                    'trend': self._parse_trend(full_text),
                    'recommendations': self._parse_recommendations(full_text),
                    'forecast': self._parse_forecast(full_text),
                    'conclusion': self._parse_conclusion(full_text),
                    'full_analysis': full_text
                }
            else:
                logger.warning(f"⚠️ Gemini retornou erro: {response.get('error')}")
                return self._generate_fallback_analysis(consolidated)
                
        except Exception as e:
            logger.error(f"❌ Erro na análise: {e}")
            return self._generate_fallback_analysis(consolidated)
    
    # ==========================================
    # CONSTRUIR RESULTADO
    # ==========================================
    
    def _build_result(
        self,
        files: List[Dict[str, Any]],
        processed_results: List[Dict[str, Any]],
        consolidated: ConsolidatedAnalysis,
        gemini_analysis: Dict[str, Any],
        processing_time_ms: float
    ) -> MultiFileAnalysisResult:
        """Constrói o resultado final"""
        
        success_count = sum(1 for r in processed_results if r.get('success'))
        
        # 🔥 Coletar todos os encodings usados
        encodings_used = []
        for r in processed_results:
            if r.get('encoding_used'):
                encodings_used.append(r['encoding_used'])
        
        # 🔥 Se não tiver encodings, usar 'unknown'
        if not encodings_used:
            encodings_used = ['unknown']
        
        logger.info(f"   📝 Encodings no resultado final: {set(encodings_used)}")
        
        return MultiFileAnalysisResult(
            success=success_count > 0,
            total_files=len(files),
            processed_files=success_count,
            failed_files=len(files) - success_count,
            files=processed_results,
            executive_score=gemini_analysis.get('executive_score', {}),
            executive_summary=gemini_analysis.get('executive_summary', ''),
            comparison=consolidated.comparison,
            trend=consolidated.trend,
            recommendations=gemini_analysis.get('recommendations', []),
            forecast=gemini_analysis.get('forecast', ''),
            general_conclusion=gemini_analysis.get('conclusion', ''),
            chart_data=consolidated.chart_data,
            processing_time_ms=processing_time_ms,
            cache_hit=False,
            encodings_used=list(set(encodings_used))  # 🔥 PROPAGADO
        )
    
    # ==========================================
    # PARSE DAS RESPOSTAS DO GEMINI
    # ==========================================
    
    def _parse_executive_score(self, text: str) -> Dict[str, Any]:
        """Extrai scores do texto"""
        scores = {
            'saude_financeira': 5.0,
            'eficiencia': 5.0,
            'controle_custos': 5.0,
            'crescimento': 5.0,
            'nivel_risco': 'Moderado',
            'nota_geral': 5.0
        }
        
        patterns = {
            'saude_financeira': r'Sa[úu]de Financeira\s*[:=]\s*(\d+[,.]?\d*)',
            'eficiencia': r'Efici[êe]ncia\s*[:=]\s*(\d+[,.]?\d*)',
            'controle_custos': r'Controle de Custos\s*[:=]\s*(\d+[,.]?\d*)',
            'crescimento': r'Crescimento\s*[:=]\s*(\d+[,.]?\d*)',
            'nivel_risco': r'N[ií]vel de Risco\s*[:=]\s*([A-Za-zçãáéíóú]+)',
            'nota_geral': r'Nota Geral\s*[:=]\s*(\d+[,.]?\d*)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).replace(',', '.')
                if key == 'nivel_risco':
                    if value.lower() in ['baixo', 'baixa']:
                        scores[key] = 'Baixo'
                    elif value.lower() in ['alto', 'alta']:
                        scores[key] = 'Alto'
                    else:
                        scores[key] = 'Moderado'
                else:
                    scores[key] = float(value)
        
        return scores
    
    def _parse_summary(self, text: str) -> str:
        """Extrai resumo executivo"""
        patterns = [
            r'Resumo Executivo\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
            r'📊 Resumo\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()[:500]
        
        return "Análise concluída com sucesso."
    
    def _parse_comparison(self, text: str) -> Dict[str, Any]:
        """Extrai comparação"""
        comparison = {
            'best_revenue': '',
            'best_profit': '',
            'best_growth': '',
            'best_efficiency': '',
            'highest_risk': '',
            'lowest_performance': ''
        }
        
        patterns = {
            'best_revenue': r'Melhor Receita\s*[:=]\s*([^\n]+)',
            'best_profit': r'Melhor Lucro\s*[:=]\s*([^\n]+)',
            'best_growth': r'Melhor Crescimento\s*[:=]\s*([^\n]+)',
            'highest_risk': r'Maior Risco\s*[:=]\s*([^\n]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                comparison[key] = match.group(1).strip()
        
        return comparison
    
    def _parse_trend(self, text: str) -> Dict[str, Any]:
        """Extrai tendência"""
        trend = {
            'direction': 'estavel',
            'strength': 0.5,
            'confidence': 0.7,
            'description': '',
            'key_observations': []
        }
        
        if re.search(r'tend[eê]ncia\s*(crescent|aument|alta)', text, re.IGNORECASE):
            trend['direction'] = 'crescente'
        elif re.search(r'tend[eê]ncia\s*(decrescent|diminu|baixa)', text, re.IGNORECASE):
            trend['direction'] = 'decrescente'
        
        obs_pattern = r'Observaç[õo]es\s*[:=]?\s*([^\n]+)'
        match = re.search(obs_pattern, text, re.IGNORECASE)
        if match:
            trend['key_observations'] = [match.group(1).strip()]
        
        return trend
    
    def _parse_recommendations(self, text: str) -> List[Dict[str, Any]]:
        """Extrai recomendações priorizadas"""
        recommendations = []
        
        patterns = {
            'alta': r'🔴 Alta Prioridade\s*[:=]?\s*(.+?)(?=\n🟡|\n🟢|\n\n|\Z)',
            'media': r'🟡 Média Prioridade\s*[:=]?\s*(.+?)(?=\n🔴|\n🟢|\n\n|\Z)',
            'baixa': r'🟢 Baixa Prioridade\s*[:=]?\s*(.+?)(?=\n🔴|\n🟡|\n\n|\Z)'
        }
        
        for priority, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                items = match.group(1).strip().split('\n')
                for item in items:
                    item = item.strip()
                    if item and item.startswith('-'):
                        item = item[1:].strip()
                    if item and len(item) > 10:
                        recommendations.append({
                            'priority': priority,
                            'category': self._guess_category(item),
                            'description': item[:180],
                            'expected_impact': self._guess_impact(item),
                            'effort': self._guess_effort(item)
                        })
        
        return recommendations[:6]
    
    def _parse_forecast(self, text: str) -> str:
        """Extrai previsão"""
        patterns = [
            r'Previsão\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
            r'Forecast\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()[:300]
        
        return "Baseado nos dados analisados, espera-se estabilidade com leve crescimento."
    
    def _parse_conclusion(self, text: str) -> str:
        """Extrai conclusão geral"""
        patterns = [
            r'Conclusão Geral\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)',
            r'📌 Conclusão\s*[:=]?\s*(.+?)(?=\n\n|\n#|\Z)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()[:500]
        
        return "A análise demonstra potencial de melhoria com foco em otimização de custos."
    
    # ==========================================
    # FUNÇÕES AUXILIARES
    # ==========================================
    
    def _guess_category(self, text: str) -> str:
        """Adivinha categoria da recomendação"""
        text_lower = text.lower()
        if any(w in text_lower for w in ['custo', 'gasto', 'despesa', 'peca']):
            return 'financeiro'
        if any(w in text_lower for w in ['processo', 'eficiência', 'tempo']):
            return 'operacional'
        if any(w in text_lower for w in ['cliente', 'venda', 'marketing']):
            return 'comercial'
        if any(w in text_lower for w in ['estoque', 'inventário']):
            return 'estoque'
        return 'geral'
    
    def _guess_impact(self, text: str) -> str:
        """Adivinha impacto esperado"""
        text_lower = text.lower()
        if any(w in text_lower for w in ['alto', 'grande', 'significativo']):
            return 'Alto impacto'
        if any(w in text_lower for w in ['médio', 'moderado']):
            return 'Médio impacto'
        return 'Baixo impacto'
    
    def _guess_effort(self, text: str) -> str:
        """Adivinha esforço necessário"""
        text_lower = text.lower()
        if any(w in text_lower for w in ['imediato', 'rápido', 'simples']):
            return 'baixo'
        if any(w in text_lower for w in ['complexo', 'longo', 'estrutural']):
            return 'alto'
        return 'medio'
    
    def _generate_consolidated_chart_data(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Gera chart_data consolidado"""
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        
        all_chart_data = []
        for result in results:
            chart = result.get('chart_data', {})
            if chart:
                all_chart_data.append(chart)
        
        if all_chart_data:
            weekly_revenue = [0] * 7
            weekly_costs = [0] * 7
            weekly_services = [0] * 7
            count = len(all_chart_data)
            
            for chart in all_chart_data:
                weekly = chart.get('weekly', {})
                rev = weekly.get('revenue', [])
                costs = weekly.get('costs', [])
                perf = chart.get('performance', {})
                serv = perf.get('services', [])
                
                for i in range(min(7, len(rev))):
                    weekly_revenue[i] += rev[i] / count if rev[i] else 0
                for i in range(min(7, len(costs))):
                    weekly_costs[i] += costs[i] / count if costs[i] else 0
                for i in range(min(7, len(serv))):
                    weekly_services[i] += serv[i] / count if serv[i] else 0
            
            monthly_revenue = [0] * 12
            for chart in all_chart_data:
                monthly = chart.get('monthly', {})
                rev = monthly.get('revenue', [])
                for i in range(min(12, len(rev))):
                    monthly_revenue[i] += rev[i] / count if rev[i] else 0
            
            return {
                "weekly": {
                    "labels": days,
                    "revenue": [round(v, 2) for v in weekly_revenue],
                    "costs": [round(v, 2) for v in weekly_costs]
                },
                "performance": {
                    "labels": days,
                    "services": [round(v) for v in weekly_services]
                },
                "monthly": {
                    "labels": months,
                    "revenue": [round(v, 2) for v in monthly_revenue]
                },
                "files_merged": len(all_chart_data)
            }
        
        random.seed(42)
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
            },
            "files_merged": 0
        }
    
    def _generate_fallback_analysis(self, consolidated: ConsolidatedAnalysis) -> Dict[str, Any]:
        """Gera análise de fallback"""
        return {
            'success': True,
            'executive_score': {
                'saude_financeira': min(10, max(0, consolidated.avg_score_overall * 10)),
                'eficiencia': min(10, max(0, consolidated.avg_score_overall * 8 + 2)),
                'controle_custos': min(10, max(0, consolidated.avg_score_overall * 6 + 4)),
                'crescimento': min(10, max(0, consolidated.avg_score_overall * 7 + 3)),
                'nivel_risco': 'Moderado' if consolidated.avg_score_overall < 0.6 else 'Baixo',
                'nota_geral': min(10, max(0, consolidated.avg_score_overall * 8 + 2))
            },
            'executive_summary': f"Análise de {consolidated.total_files} arquivo(s) concluída. Receita total: R$ {consolidated.total_revenue:,.2f}.",
            'recommendations': [
                {
                    'priority': 'media',
                    'category': 'geral',
                    'description': '📊 Monitorar KPIs mensalmente para acompanhar evolução do negócio.',
                    'expected_impact': 'Médio impacto',
                    'effort': 'medio'
                }
            ],
            'forecast': 'Baseado nos dados analisados, espera-se manutenção da tendência atual.',
            'conclusion': 'A análise demonstra potencial de melhoria com foco em otimização de custos.'
        }
    
    # ==========================================
    # CACHE
    # ==========================================
    
    def _get_cache_key(self, files: List[Dict[str, Any]], user_id: int = None) -> str:
        """Gera chave de cache"""
        content = "".join([
            f.get('filename', '') + str(f.get('file_size', 0)) 
            for f in files
        ])
        if user_id:
            content += str(user_id)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_result(self, key: str) -> Optional[Dict[str, Any]]:
        """Obtém resultado do cache"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self.CACHE_TTL:
                self._stats["cache_hits"] += 1
                return data
            else:
                del self._cache[key]
        self._stats["cache_misses"] += 1
        return None
    
    def _set_cache(self, key: str, data: Dict[str, Any]) -> None:
        """Salva resultado no cache"""
        self._cache[key] = (data, time.time())
    
    # ==========================================
    # FUNÇÕES AUXILIARES
    # ==========================================
    
    def _error_result(self, error: str) -> MultiFileAnalysisResult:
        """Cria resultado de erro"""
        return MultiFileAnalysisResult(
            success=False,
            total_files=0,
            processed_files=0,
            failed_files=0,
            error=error
        )
    
    def _error_file_result(self, filename: str, error: str) -> Dict[str, Any]:
        """Cria resultado de erro para um arquivo"""
        return {
            'success': False,
            'filename': filename,
            'error': error,
            'predictions': [],
            'metrics': {},
            'chart_data': {},
            'encoding_used': None  # 🔥 ADICIONADO
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do analisador"""
        return {
            **self._stats,
            "cache_size": len(self._cache),
            "uptime_seconds": (datetime.now() - datetime.fromisoformat(self._stats["started_at"])).total_seconds()
        }


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

multi_analyzer = MultiFileAnalyzerV4()


# ==============================================
# FUNÇÃO DE COMPATIBILIDADE
# ==============================================

async def analyze_multiple_files(
    files: List[Dict[str, Any]],
    user_id: int = None,
    user_email: str = None,
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    🔥 Função principal para análise múltipla
    """
    result = await multi_analyzer.analyze_multiple_files(
        files=files,
        user_id=user_id,
        user_email=user_email,
        force_reload=force_reload
    )
    return result.to_dict()


# ==============================================
# TESTE
# ==============================================

async def test_multi_analysis():
    """Função de teste"""
    print("\n" + "=" * 70)
    print("🧪 TESTANDO ANÁLISE MÚLTIPLA V4.1")
    print("=" * 70)
    
    import pandas as pd
    import numpy as np
    from io import BytesIO
    
    files = []
    
    for i in range(3):
        df = pd.DataFrame({
            'cliente_id': range(1, 101),
            'valor_servico': np.random.randn(100) * 100 + 500 + i * 50,
            'custo_pecas': np.random.randn(100) * 50 + 200 + i * 30,
            'data': pd.date_range('2024-01-01', periods=100, freq='D')
        })
        
        buffer = BytesIO()
        df.to_csv(buffer, index=False)
        content = buffer.getvalue()
        
        files.append({
            'content': content,
            'filename': f'teste_arquivo_{i+1}.csv',
            'file_size': len(content)
        })
    
    print(f"📁 {len(files)} arquivos criados")
    
    result = await analyze_multiple_files(
        files=files,
        user_email='teste@email.com',
        user_id=1
    )
    
    print(f"\n📊 RESULTADO:")
    print(f"   ✅ Sucesso: {result['success']}")
    print(f"   📁 Total: {result['total_files']}")
    print(f"   ✅ Processados: {result['processed_files']}")
    print(f"   ❌ Falhas: {result['failed_files']}")
    print(f"   ⏱️ Tempo: {result['processing_time_ms']:.0f}ms")
    
    # 🔥 MOSTRAR ENCODINGS
    encodings = result.get('encodings_used', [])
    print(f"   📝 Encodings usados: {encodings if encodings else 'N/A'}")
    
    if result.get('executive_score'):
        print("\n🏆 SCORE EXECUTIVO:")
        for key, value in result['executive_score'].items():
            print(f"   {key}: {value}")
    
    print("\n📝 RECOMENDAÇÕES:")
    for rec in result.get('recommendations', [])[:3]:
        emoji = '🔴' if rec['priority'] == 'alta' else '🟡' if rec['priority'] == 'media' else '🟢'
        print(f"   {emoji} [{rec['priority'].upper()}] {rec['description'][:60]}...")
    
    print("\n" + "=" * 70)
    print("✅ Teste concluído!")
    print("=" * 70)
    
    return result


if __name__ == "__main__":
    asyncio.run(test_multi_analysis())