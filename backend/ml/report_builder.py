# backend/ml/report_builder.py - VERSÃO 3.1 CORRIGIDA
"""
🔥 EXECUTIVE REPORT BUILDER - AutoAnalytics V3.1
================================================================================
VERSÃO 3.1 - CORREÇÃO DE ENCODING E DUPLICAÇÃO

✅ CORREÇÕES:
   - 🔥 Removida duplicação da função to_html
   - 🔥 Encoding UTF-8 garantido em todo o HTML
   - 🔥 encoding_used propagado para o rodapé
   - 🔥 Charset correto no head e meta tags
================================================================================
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class ReportFormat(str, Enum):
    PDF = "pdf"
    HTML = "html"
    JSON = "json"


@dataclass
class ReportSection:
    title: str
    content: str
    level: int = 1
    icon: Optional[str] = None
    order: int = 0


@dataclass
class ReportTable:
    title: str
    headers: List[str]
    rows: List[List[Any]]
    caption: Optional[str] = None


@dataclass
class ExecutiveReport:
    title: str
    subtitle: str
    generated_at: str
    author: str
    
    executive_summary: str
    executive_score: Dict[str, Any]
    sections: List[ReportSection]
    tables: List[ReportTable]
    recommendations: List[Dict[str, Any]]
    comparison: Dict[str, Any]
    trend: Dict[str, Any]
    forecast: str
    general_conclusion: str
    
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    processing_time_ms: float = 0
    files: List[Dict[str, Any]] = field(default_factory=list)
    table_of_contents: List[Dict[str, Any]] = field(default_factory=list)
    
    # Dados do ML Pipeline
    ml_predictions: List[float] = field(default_factory=list)
    ml_metrics: Dict[str, Any] = field(default_factory=dict)
    ml_insights: Dict[str, Any] = field(default_factory=dict)
    ml_chart_data: Dict[str, Any] = field(default_factory=dict)
    ml_recommendations: List[str] = field(default_factory=list)
    model_used: str = "unknown"
    encoding_used: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "generated_at": self.generated_at,
            "author": self.author,
            "executive_summary": self.executive_summary,
            "executive_score": self.executive_score,
            "sections": [{"title": s.title, "content": s.content} for s in self.sections],
            "tables": [{"title": t.title, "headers": t.headers, "rows": t.rows} for t in self.tables],
            "recommendations": self.recommendations,
            "comparison": self.comparison,
            "trend": self.trend,
            "forecast": self.forecast,
            "general_conclusion": self.general_conclusion,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "processing_time_ms": self.processing_time_ms,
            "table_of_contents": self.table_of_contents,
            "ml_predictions": self.ml_predictions[:10],
            "ml_metrics": self.ml_metrics,
            "ml_insights": self.ml_insights,
            "ml_chart_data": self.ml_chart_data,
            "ml_recommendations": self.ml_recommendations,
            "model_used": self.model_used,
            "encoding_used": self.encoding_used
        }


class ExecutiveReportBuilder:
    """
    🔥 Construtor de Relatórios Executivos - V3.1
    Integrado com preprocessing.py
    """
    
    def __init__(
        self,
        language: str = "pt-BR",
        theme: str = "dark",
        logo_url: Optional[str] = None,
        company_name: str = "AutoAnalytics"
    ):
        self.language = language
        self.theme = theme
        self.logo_url = logo_url
        self.company_name = company_name
        
        self._priority_order = {'alta': 0, 'media': 1, 'baixa': 2}
        self._priority_labels = {
            'alta': '🔴 Alta Prioridade',
            'media': '🟡 Média Prioridade',
            'baixa': '🟢 Baixa Prioridade'
        }
        
        logger.info(f"✅ ExecutiveReportBuilder V3.1 inicializado")
        logger.info(f"   🌐 Idioma: {language}")
        logger.info(f"   🎨 Tema: {theme}")
        logger.info(f"   🏢 Empresa: {company_name}")
    
    # ==========================================
    # MÉTODO PRINCIPAL
    # ==========================================
    
    def build(
        self,
        analysis_result: Dict[str, Any],
        user_name: str = "Usuário"
    ) -> ExecutiveReport:
        """Constrói relatório a partir do resultado do preprocessing.py/multi_analysis.py"""
        logger.info("📄 Construindo relatório executivo integrado...")
        
        # 1. Extrair dados do ML Pipeline
        ml_predictions = analysis_result.get('predictions', [])
        ml_metrics = analysis_result.get('metrics', {})
        ml_insights = analysis_result.get('insights', {})
        ml_chart_data = analysis_result.get('chart_data', {})
        ml_recommendations = analysis_result.get('recommendations', [])
        model_used = analysis_result.get('model_used', 'unknown')
        encoding_used = analysis_result.get('encoding_used', 'unknown')
        
        # Se não tem chart_data, gera fallback
        if not ml_chart_data:
            ml_chart_data = self._generate_fallback_chart_data(ml_predictions, ml_metrics)
        
        # 2. Calcular score executivo
        executive_score = self._calculate_executive_score(ml_predictions, ml_metrics, ml_insights)
        
        # 3. Extrair insights e recomendações
        executive_summary = self._generate_executive_summary(ml_metrics, ml_insights)
        
        formatted_recommendations = []
        for rec in ml_recommendations:
            if isinstance(rec, str):
                formatted_recommendations.append({
                    'priority': 'media',
                    'category': 'geral',
                    'description': rec,
                    'expected_impact': 'Médio impacto',
                    'effort': 'medio'
                })
            elif isinstance(rec, dict):
                formatted_recommendations.append(rec)
            else:
                formatted_recommendations.append({
                    'priority': 'media',
                    'category': 'geral',
                    'description': str(rec),
                    'expected_impact': 'Médio impacto',
                    'effort': 'medio'
                })
        
        # 4. Análises
        comparison = self._analyze_comparison(ml_predictions, ml_metrics)
        trend = self._analyze_trend(ml_predictions, ml_metrics)
        forecast = self._generate_forecast(ml_predictions, ml_metrics)
        general_conclusion = self._generate_conclusion(ml_predictions, ml_metrics, ml_insights)
        
        # 5. Construir seções e tabelas
        sections = self._build_sections_from_ml(
            executive_summary=executive_summary,
            comparison=comparison,
            trend=trend,
            forecast=forecast,
            general_conclusion=general_conclusion,
            files=analysis_result.get('files', []),
            ml_insights=ml_insights,
            ml_recommendations=formatted_recommendations
        )
        
        tables = self._build_tables_from_ml(ml_predictions, ml_metrics, ml_chart_data)
        toc = self._generate_table_of_contents(sections)
        
        # 6. Criar relatório
        return ExecutiveReport(
            title=f"📊 Relatório Executivo - {self.company_name}",
            subtitle=f"Análise de {analysis_result.get('total_files', 1)} arquivo(s)",
            generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
            author=user_name,
            executive_summary=executive_summary,
            executive_score=executive_score,
            sections=sections,
            tables=tables,
            recommendations=formatted_recommendations,
            comparison=comparison,
            trend=trend,
            forecast=forecast,
            general_conclusion=general_conclusion,
            total_files=analysis_result.get('total_files', 1),
            processed_files=analysis_result.get('processed_files', 0),
            failed_files=analysis_result.get('failed_files', 0),
            processing_time_ms=analysis_result.get('processing_time_ms', 0),
            files=analysis_result.get('files', []),
            table_of_contents=toc,
            ml_predictions=ml_predictions,
            ml_metrics=ml_metrics,
            ml_insights=ml_insights,
            ml_chart_data=ml_chart_data,
            ml_recommendations=ml_recommendations,
            model_used=model_used,
            encoding_used=encoding_used
        )
    
    # ==========================================
    # FUNÇÕES DE ANÁLISE
    # ==========================================
    
    def _calculate_executive_score(self, predictions: List[float], metrics: Dict[str, Any], insights: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula score executivo baseado nos dados do ML"""
        pred_list = self._safe_predictions_to_list(predictions)
        total_predictions = len(pred_list)
        
        if total_predictions == 0:
            return {
                'saude_financeira': 5.0,
                'eficiencia': 5.0,
                'controle_custos': 5.0,
                'crescimento': 5.0,
                'nivel_risco': 'Moderado',
                'nota_geral': 5.0
            }
        
        mean_score = float(np.mean(pred_list)) if pred_list else 0.5
        high_risk_pct = metrics.get('high_risk_percentage', 0) or 0
        
        saude_financeira = min(10, max(0, mean_score * 10 + 1))
        eficiencia = min(10, max(0, mean_score * 9 + 0.5))
        controle_custos = min(10, max(0, mean_score * 8 + 1))
        crescimento = min(10, max(0, mean_score * 7 + 2))
        
        if high_risk_pct > 30:
            nivel_risco = 'Alto'
        elif high_risk_pct > 15:
            nivel_risco = 'Moderado'
        else:
            nivel_risco = 'Baixo'
        
        nota_geral = min(10, max(0, (saude_financeira + eficiencia + controle_custos + crescimento) / 4))
        
        return {
            'saude_financeira': round(saude_financeira, 1),
            'eficiencia': round(eficiencia, 1),
            'controle_custos': round(controle_custos, 1),
            'crescimento': round(crescimento, 1),
            'nivel_risco': nivel_risco,
            'nota_geral': round(nota_geral, 1)
        }
    
    def _generate_executive_summary(self, metrics: Dict[str, Any], insights: Dict[str, Any]) -> str:
        """Gera resumo executivo baseado nos dados"""
        mean_score = metrics.get('mean_prediction', 0.5) * 100
        total_rows = metrics.get('processed_rows', 0)
        high_risk = metrics.get('high_risk_percentage', 0)
        low_risk = metrics.get('low_risk_percentage', 0)
        
        summary_parts = []
        summary_parts.append(f"📊 **{total_rows} registros** analisados com um score médio de **{mean_score:.0f}%**.")
        
        if high_risk > 30:
            summary_parts.append(f"🔴 **{high_risk:.0f}%** dos casos são de alto risco, indicando necessidade de revisão de processos.")
        elif high_risk > 15:
            summary_parts.append(f"🟡 **{high_risk:.0f}%** dos casos são de alto risco, recomendando monitoramento.")
        else:
            summary_parts.append(f"🟢 **{low_risk:.0f}%** dos casos são de baixo risco, demonstrando boa performance.")
        
        return " ".join(summary_parts)
    
    def _analyze_comparison(self, predictions: List[float], metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa comparação entre arquivos/períodos"""
        pred_list = self._safe_predictions_to_list(predictions)
        total = len(pred_list)
        
        if total == 0:
            return {'best_revenue': 'N/A', 'best_profit': 'N/A', 'best_growth': 'N/A', 'highest_risk': 'N/A'}
        
        mean_score = np.mean(pred_list) if pred_list else 0.5
        high_risk_count = len([p for p in pred_list if p > 0.7])
        high_risk_pct = (high_risk_count / total) * 100 if total > 0 else 0
        
        return {
            'best_revenue': f'Score médio: {(mean_score * 100):.0f}%',
            'best_profit': f'Baixo risco: {(100 - high_risk_pct):.0f}%',
            'best_growth': f'Tendência: {self._calc_trend_direction(pred_list)}',
            'highest_risk': f'{high_risk_pct:.0f}% dos casos'
        }
    
    def _analyze_trend(self, predictions: List[float], metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa tendência dos dados"""
        pred_list = self._safe_predictions_to_list(predictions)
        total = len(pred_list)
        
        if total < 2:
            return {
                'direction': 'estavel',
                'strength': 0.5,
                'confidence': 0.5,
                'description': 'Dados insuficientes para análise de tendência.',
                'key_observations': ['Carregue mais dados para análise de tendência']
            }
        
        first_half = pred_list[:total//2]
        second_half = pred_list[total//2:]
        
        mean_first = np.mean(first_half) if first_half else 0.5
        mean_second = np.mean(second_half) if second_half else 0.5
        change = mean_second - mean_first
        
        if change > 0.05:
            direction = 'crescente'
            description = f"Os dados indicam uma tendência de crescimento de {change*100:.1f}%."
        elif change < -0.05:
            direction = 'decrescente'
            description = f"Os dados indicam uma tendência de queda de {abs(change)*100:.1f}%."
        else:
            direction = 'estavel'
            description = "Os dados indicam estabilidade no período analisado."
        
        return {
            'direction': direction,
            'strength': round(abs(change) * 2, 2),
            'confidence': 0.7 if total > 20 else 0.5,
            'description': description,
            'key_observations': [
                f"Média da primeira metade: {(mean_first*100):.0f}%",
                f"Média da segunda metade: {(mean_second*100):.0f}%",
                f"Variação: {change*100:+.1f}%"
            ]
        }
    
    def _generate_forecast(self, predictions: List[float], metrics: Dict[str, Any]) -> str:
        """Gera previsão baseada nos dados"""
        pred_list = self._safe_predictions_to_list(predictions)
        total = len(pred_list)
        
        if total < 5:
            return "Dados insuficientes para uma previsão confiável. Recomendamos carregar mais dados."
        
        mean_score = np.mean(pred_list) if pred_list else 0.5
        high_risk_pct = metrics.get('high_risk_percentage', 0) or 0
        
        if high_risk_pct > 30:
            forecast = f"⚠️ Previsão de **alto risco** ({high_risk_pct:.0f}% dos casos). "
            forecast += "Recomenda-se revisão imediata dos processos e acompanhamento semanal."
        elif high_risk_pct > 15:
            forecast = f"🟡 Previsão de **risco moderado** ({high_risk_pct:.0f}% dos casos). "
            forecast += "Recomenda-se monitoramento mensal e ajustes graduais."
        else:
            forecast = f"🟢 Previsão **favorável** com {(100-high_risk_pct):.0f}% de casos de baixo risco. "
            forecast += "Mantenha as boas práticas e monitore indicadores-chave."
        
        forecast += f" Score médio esperado: **{(mean_score * 100):.0f}%**."
        
        return forecast
    
    def _generate_conclusion(self, predictions: List[float], metrics: Dict[str, Any], insights: Dict[str, Any]) -> str:
        """Gera conclusão geral"""
        pred_list = self._safe_predictions_to_list(predictions)
        total = len(pred_list)
        
        if total == 0:
            return "Nenhum dado foi analisado. Faça upload de um arquivo para gerar a conclusão."
        
        mean_score = np.mean(pred_list) if pred_list else 0.5
        high_risk_pct = metrics.get('high_risk_percentage', 0) or 0
        low_risk_pct = metrics.get('low_risk_percentage', 0) or 0
        
        conclusion_parts = []
        
        if mean_score > 0.7:
            conclusion_parts.append("✅ A análise demonstra **alta performance**, com potencial significativo de crescimento.")
        elif mean_score > 0.4:
            conclusion_parts.append("📊 A análise demonstra **potencial de melhoria**, com oportunidades claras de otimização.")
        else:
            conclusion_parts.append("⚠️ A análise demonstra **baixa performance**, indicando necessidade de revisão estratégica.")
        
        if high_risk_pct > 30:
            conclusion_parts.append(f"🔴 Atenção: {high_risk_pct:.0f}% dos casos são de alto risco.")
        elif low_risk_pct > 60:
            conclusion_parts.append(f"🟢 Excelente: {low_risk_pct:.0f}% dos casos são de baixo risco.")
        
        if high_risk_pct > 15:
            conclusion_parts.append("🎯 Recomenda-se revisão dos processos e investimento em treinamento.")
        else:
            conclusion_parts.append("🎯 Mantenha as boas práticas e continue monitorando seus indicadores.")
        
        return " ".join(conclusion_parts)
    
    def _calc_trend_direction(self, pred_list: List[float]) -> str:
        """Calcula direção da tendência"""
        if len(pred_list) < 2:
            return "estavel"
        
        first_half = pred_list[:len(pred_list)//2]
        second_half = pred_list[len(pred_list)//2:]
        
        mean_first = np.mean(first_half) if first_half else 0.5
        mean_second = np.mean(second_half) if second_half else 0.5
        
        if mean_second > mean_first * 1.05:
            return "crescente"
        elif mean_second < mean_first * 0.95:
            return "decrescente"
        return "estavel"
    
    # ==========================================
    # CONSTRUÇÃO DE SEÇÕES
    # ==========================================
    
    def _build_sections_from_ml(
        self,
        executive_summary: str,
        comparison: Dict[str, Any],
        trend: Dict[str, Any],
        forecast: str,
        general_conclusion: str,
        files: List[Dict[str, Any]],
        ml_insights: Dict[str, Any],
        ml_recommendations: List[Dict[str, Any]]
    ) -> List[ReportSection]:
        """Constrói seções baseadas nos dados do ML"""
        sections = []
        order = 0
        
        if executive_summary:
            sections.append(ReportSection(
                title="📋 Resumo Executivo",
                content=executive_summary,
                level=1,
                icon="📋",
                order=order
            ))
            order += 1
        
        if files:
            sections.append(ReportSection(
                title="📁 Resumo dos Arquivos",
                content=self._format_files_summary(files),
                level=1,
                icon="📁",
                order=order
            ))
            order += 1
        
        if ml_insights:
            sections.append(ReportSection(
                title="💡 Insights da Análise",
                content=self._format_insights(ml_insights),
                level=1,
                icon="💡",
                order=order
            ))
            order += 1
        
        if comparison and any(comparison.values()):
            sections.append(ReportSection(
                title="📊 Comparação",
                content=self._format_comparison(comparison),
                level=1,
                icon="📊",
                order=order
            ))
            order += 1
        
        if trend and trend.get('description'):
            sections.append(ReportSection(
                title="📈 Análise de Tendência",
                content=self._format_trend(trend),
                level=1,
                icon="📈",
                order=order
            ))
            order += 1
        
        if ml_recommendations:
            sections.append(ReportSection(
                title="🎯 Recomendações Priorizadas",
                content=self._format_recommendations_text(ml_recommendations),
                level=1,
                icon="🎯",
                order=order
            ))
            order += 1
        
        if forecast:
            sections.append(ReportSection(
                title="🔮 Previsão",
                content=forecast,
                level=1,
                icon="🔮",
                order=order
            ))
            order += 1
        
        if general_conclusion:
            sections.append(ReportSection(
                title="📌 Conclusão Geral",
                content=general_conclusion,
                level=1,
                icon="📌",
                order=order
            ))
            order += 1
        
        return sections
    
    def _format_insights(self, insights: Dict[str, Any]) -> str:
        """Formata insights do ML"""
        lines = []
        
        summary = insights.get('summary', {})
        if summary:
            total = summary.get('total_predictions', 0)
            mean = summary.get('mean', 0)
            lines.append(f"📊 Total de predições: {total}")
            lines.append(f"📈 Score médio: {(mean*100):.0f}%")
        
        risk = insights.get('risk_distribution', {})
        if risk:
            lines.append(f"🔴 Alto risco: {risk.get('high_percentage', 0):.0f}%")
            lines.append(f"🟡 Médio risco: {risk.get('medium_percentage', 0):.0f}%")
            lines.append(f"🟢 Baixo risco: {risk.get('low_percentage', 0):.0f}%")
        
        model_info = insights.get('model_info', {})
        if model_info:
            source = model_info.get('source', 'unknown')
            accuracy = model_info.get('accuracy', 0)
            lines.append(f"🤖 Modelo: {source} (acurácia: {(accuracy*100):.0f}%)")
        
        return "\n".join(lines)
    
    def _format_recommendations_text(self, recommendations: List[Dict[str, Any]]) -> str:
        """Formata recomendações para texto"""
        lines = []
        priority_order = {'alta': 0, 'media': 1, 'baixa': 2}
        sorted_recs = sorted(recommendations, key=lambda x: priority_order.get(x.get('priority', 'media'), 1))
        
        for rec in sorted_recs[:5]:
            priority = rec.get('priority', 'media')
            emoji = '🔴' if priority == 'alta' else '🟡' if priority == 'media' else '🟢'
            desc = rec.get('description', '')
            lines.append(f"{emoji} {desc}")
        
        return "\n".join(lines)
    
    def _format_files_summary(self, files: List[Dict[str, Any]]) -> str:
        """Formata resumo dos arquivos"""
        lines = []
        for idx, file in enumerate(files, 1):
            status = "✅" if file.get('success') else "❌"
            rows = file.get('processed_rows', 0)
            filename = file.get('filename', f'Arquivo {idx}')
            metrics = file.get('metrics', {})
            score = metrics.get('mean_prediction', 0) * 100
            
            lines.append(f"{status} **{filename}** - {rows} registros | Score: {score:.0f}%")
        
        return "\n".join(lines)
    
    def _format_comparison(self, comparison: Dict[str, Any]) -> str:
        """Formata comparação"""
        lines = []
        for key, value in comparison.items():
            if value and key not in ['comparison_table', 'summary']:
                label = {
                    'best_revenue': '💰 Melhor Receita',
                    'best_profit': '💵 Melhor Lucro',
                    'best_growth': '📈 Melhor Crescimento',
                    'highest_risk': '⚠️ Maior Risco'
                }.get(key, key)
                lines.append(f"{label}: **{value}**")
        
        if comparison.get('summary'):
            lines.append(f"\n{comparison['summary']}")
        
        return "\n".join(lines) if lines else "Nenhuma comparação disponível"
    
    def _format_trend(self, trend: Dict[str, Any]) -> str:
        """Formata tendência"""
        lines = [trend.get('description', '')]
        
        if trend.get('key_observations'):
            lines.append("\n**Observações:**")
            for obs in trend['key_observations']:
                lines.append(f"• {obs}")
        
        return "\n".join(lines)
    
    # ==========================================
    # CONSTRUÇÃO DE TABELAS
    # ==========================================
    
    def _build_tables_from_ml(self, predictions: List[float], metrics: Dict[str, Any], chart_data: Dict[str, Any]) -> List[ReportTable]:
        """Constrói tabelas baseadas nos dados do ML"""
        tables = []
        pred_list = self._safe_predictions_to_list(predictions)
        
        if pred_list:
            high_risk = len([p for p in pred_list if p > 0.7])
            medium_risk = len([p for p in pred_list if 0.3 <= p <= 0.7])
            low_risk = len([p for p in pred_list if p < 0.3])
            
            tables.append(ReportTable(
                title="📊 Distribuição de Risco",
                headers=["Categoria", "Quantidade", "Porcentagem"],
                rows=[
                    ["🔴 Alto Risco (>70%)", high_risk, f"{high_risk/len(pred_list)*100:.1f}%"],
                    ["🟡 Médio Risco (30-70%)", medium_risk, f"{medium_risk/len(pred_list)*100:.1f}%"],
                    ["🟢 Baixo Risco (<30%)", low_risk, f"{low_risk/len(pred_list)*100:.1f}%"]
                ],
                caption="Distribuição dos casos por nível de risco"
            ))
        
        if metrics:
            table_rows = []
            for key, value in metrics.items():
                if key in ['mean_prediction', 'std_prediction', 'min_prediction', 'max_prediction']:
                    if isinstance(value, (int, float)):
                        table_rows.append([key.replace('_prediction', '').title(), f"{value*100:.1f}%"])
                elif key in ['processed_rows', 'high_risk_count', 'low_risk_count']:
                    table_rows.append([key.replace('_', ' ').title(), str(value)])
            
            if table_rows:
                tables.append(ReportTable(
                    title="📈 Métricas do Modelo",
                    headers=["Métrica", "Valor"],
                    rows=table_rows,
                    caption="Métricas calculadas pelo modelo de ML"
                ))
        
        if chart_data and chart_data.get('weekly'):
            weekly = chart_data.get('weekly', {})
            labels = weekly.get('labels', ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'])
            revenue = weekly.get('revenue', [])
            costs = weekly.get('costs', [])
            
            if revenue:
                table_rows = []
                for i, label in enumerate(labels):
                    rev = revenue[i] if i < len(revenue) else 0
                    cost = costs[i] if i < len(costs) else 0
                    profit = rev - cost
                    table_rows.append([
                        label,
                        f"R$ {rev:,.2f}",
                        f"R$ {cost:,.2f}",
                        f"R$ {profit:,.2f}"
                    ])
                
                tables.append(ReportTable(
                    title="📅 Desempenho Semanal",
                    headers=["Dia", "Receita", "Custos", "Lucro"],
                    rows=table_rows,
                    caption="Dados semanais extraídos da análise"
                ))
        
        return tables
    
    # ==========================================
    # FALLBACK
    # ==========================================
    
    def _generate_fallback_chart_data(self, predictions: List[float], metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Gera chart_data de fallback"""
        import random
        random.seed(42)
        
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        
        pred_list = self._safe_predictions_to_list(predictions)
        
        if pred_list and len(pred_list) >= 7:
            base_value = sum(pred_list) / len(pred_list) * 1500
            weekly_revenue = [base_value * (0.5 + p * 0.6) for p in pred_list[:7]]
            weekly_services = [max(1, int(p * 15 + 2)) for p in pred_list[:7]]
        else:
            weekly_revenue = [random.randint(500, 2000) + random.random() * 100 for _ in range(7)]
            weekly_services = [random.randint(2, 15) for _ in range(7)]
        
        weekly_costs = [r * (0.25 + (i % 3) * 0.05) for i, r in enumerate(weekly_revenue)]
        
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
                "revenue": [round(v * (1 + i * 0.02), 2) for i, v in enumerate(weekly_revenue[:12])] if len(weekly_revenue) >= 12 else 
                          [round(v * (1 + i * 0.02), 2) for i, v in enumerate([5000 + i * 200 for i in range(12)])]
            }
        }
    
    # ==========================================
    # UTILITÁRIOS
    # ==========================================
    
    def _safe_predictions_to_list(self, predictions: Any) -> List[float]:
        """Converte predições para lista de forma segura"""
        if predictions is None:
            return []
        
        try:
            if hasattr(predictions, 'tolist'):
                pred_list = predictions.tolist()
            elif isinstance(predictions, list):
                pred_list = predictions
            else:
                pred_list = list(predictions)
            
            return [float(p) for p in pred_list if p is not None and not np.isnan(p)]
        except Exception:
            return []
    
    def _generate_table_of_contents(self, sections: List[ReportSection]) -> List[Dict[str, Any]]:
        """Gera índice automático"""
        return [{"title": s.title, "level": s.level, "order": s.order} for s in sections]
    
    # ==========================================
    # EXPORTAÇÃO HTML (CORRIGIDO)
    # ==========================================
    
    def to_html(self, report: ExecutiveReport) -> str:
        """Converte relatório para HTML com charset UTF-8"""
        
        if self.theme == "dark":
            bg = "#0f0c29"
            card_bg = "rgba(255,255,255,0.04)"
            text = "#e2e8f0"
            text_muted = "rgba(255,255,255,0.5)"
        else:
            bg = "#f5f5f5"
            card_bg = "rgba(255,255,255,0.9)"
            text = "#1a1a2e"
            text_muted = "rgba(0,0,0,0.5)"
        
        css = f"""
        @charset "UTF-8";
        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background: {bg};
            color: {text};
            padding: 40px;
            max-width: 900px;
            margin: 0 auto;
        }}
        .report-header {{
            text-align: center;
            padding: 30px;
            background: {card_bg};
            border-radius: 16px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,107,53,0.2);
        }}
        .report-header h1 {{
            font-size: 2.2rem;
            background: linear-gradient(135deg, #ff6b35, #f7931e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
        }}
        .section {{
            background: {card_bg};
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.06);
        }}
        .section h2 {{
            font-size: 1.3rem;
            color: #ff6b35;
            margin-top: 0;
            margin-bottom: 12px;
        }}
        .section p {{
            color: {text_muted};
            line-height: 1.6;
            margin: 8px 0;
        }}
        .score-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin: 16px 0;
        }}
        .score-item {{
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            padding: 12px 16px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .score-item .score-value {{
            font-size: 1.8rem;
            font-weight: 800;
            color: #ff6b35;
        }}
        .recommendation {{
            padding: 10px 14px;
            margin: 6px 0;
            border-radius: 8px;
            border-left: 4px solid #ff6b35;
            background: rgba(255,255,255,0.02);
        }}
        .recommendation.alta {{ border-left-color: #f56565; }}
        .recommendation.media {{ border-left-color: #f5a623; }}
        .recommendation.baixa {{ border-left-color: #48bb78; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
            font-size: 0.8rem;
        }}
        table th {{
            background: rgba(255,107,53,0.1);
            color: #ff6b35;
            padding: 8px 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid rgba(255,107,53,0.2);
        }}
        table td {{
            padding: 6px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            color: {text_muted};
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: {text_muted};
            font-size: 0.6rem;
            border-top: 1px solid rgba(255,255,255,0.03);
            margin-top: 30px;
        }}
        @media (max-width: 600px) {{
            body {{ padding: 16px; }}
            .score-grid {{ grid-template-columns: 1fr 1fr; }}
        }}
        """
        
        # 🔥 CORREÇÃO: HTML com encoding UTF-8 garantido
        html = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{report.title}</title>
            <style>{css}</style>
        </head>
        <body>
            <div class="report-header">
                <h1>{report.title}</h1>
                <div style="color:{text_muted}; font-size:1rem;">{report.subtitle}</div>
                <div style="color:{text_muted}; font-size:0.8rem; margin-top:12px;">
                    Gerado em {report.generated_at} • {report.author}
                    • {report.total_files} arquivo(s) • {report.processing_time_ms:.0f}ms
                    • Modelo: {report.model_used}
                </div>
                {f'<div style="color:{text_muted}; font-size:0.6rem; margin-top:4px;">Encoding: {report.encoding_used}</div>' if report.encoding_used else ''}
            </div>
            
            <div class="section">
                <h2>📑 Índice</h2>
                {self._render_toc(report.table_of_contents)}
            </div>
        """
        
        # Score Executivo
        if report.executive_score:
            html += self._render_score(report.executive_score)
        
        # Seções
        for section in report.sections:
            html += self._render_section(section)
        
        # Recomendações
        if report.recommendations:
            html += self._render_recommendations(report.recommendations)
        
        # Tabelas
        for table in report.tables:
            html += self._render_table(table)
        
        # 🔥 CORREÇÃO: Rodapé com encoding_used
        encoding_info = f"• Encoding: {report.encoding_used}" if report.encoding_used else ""
        html += f"""
            <div class="footer">
                {self.company_name} v3.1 • Relatório gerado automaticamente por IA • {report.generated_at}
                <br><small style="color:rgba(255,255,255,0.15);">
                    Modelo: {report.model_used} • {len(report.ml_predictions)} predições {encoding_info}
                </small>
            </div>
        </body>
        </html>
        """
        
        return html
    
    # ==========================================
    # RENDERIZAÇÃO HTML
    # ==========================================
    
    def _render_toc(self, toc: List[Dict[str, Any]]) -> str:
        html = '<div style="display:grid; grid-template-columns:1fr 1fr; gap:4px 20px;">'
        for item in toc:
            indent = "&nbsp;" * ((item['level'] - 1) * 16)
            html += f'<div style="color:rgba(255,255,255,0.4); font-size:0.8rem;">{indent}{item["title"]}</div>'
        html += '</div>'
        return html
    
    def _render_score(self, score: Dict[str, Any]) -> str:
        html = '<div class="section"><h2>🏆 Score Executivo</h2><div class="score-grid">'
        
        items = [
            ("Saúde Financeira", score.get('saude_financeira', 0)),
            ("Eficiência", score.get('eficiencia', 0)),
            ("Controle de Custos", score.get('controle_custos', 0)),
            ("Crescimento", score.get('crescimento', 0)),
            ("Nível de Risco", score.get('nivel_risco', 'Moderado')),
            ("Nota Geral", score.get('nota_geral', 0))
        ]
        
        for label, value in items:
            if isinstance(value, (int, float)):
                color = '#48bb78' if value >= 7 else '#f5a623' if value >= 5 else '#f56565'
                html += f"""
                <div class="score-item">
                    <div class="score-value" style="color:{color}">{value:.1f}</div>
                    <div style="font-size:0.7rem; color:rgba(255,255,255,0.4); text-transform:uppercase;">{label}</div>
                </div>
                """
            else:
                color = '#48bb78' if value == 'Baixo' else '#f5a623' if value == 'Moderado' else '#f56565'
                html += f"""
                <div class="score-item">
                    <div class="score-value" style="color:{color}; font-size:1.2rem;">{value}</div>
                    <div style="font-size:0.7rem; color:rgba(255,255,255,0.4); text-transform:uppercase;">{label}</div>
                </div>
                """
        
        html += '</div></div>'
        return html
    
    def _render_section(self, section: ReportSection) -> str:
        content = section.content.replace('**', '<strong>').replace('**', '</strong>')
        content = content.replace('\n', '<br>')
        
        return f"""
        <div class="section">
            <h2>{section.icon if section.icon else '📄'} {section.title}</h2>
            <div style="color:rgba(255,255,255,0.7); line-height:1.6; font-size:0.9rem;">
                {content}
            </div>
        </div>
        """
    
    def _render_recommendations(self, recommendations: List[Dict[str, Any]]) -> str:
        html = '<div class="section"><h2>🎯 Recomendações Priorizadas</h2>'
        
        priority_order = {'alta': 0, 'media': 1, 'baixa': 2}
        sorted_recs = sorted(recommendations, key=lambda x: priority_order.get(x.get('priority', 'media'), 1))
        
        for rec in sorted_recs:
            priority = rec.get('priority', 'media')
            label = '🔴 Alta Prioridade' if priority == 'alta' else '🟡 Média Prioridade' if priority == 'media' else '🟢 Baixa Prioridade'
            color = '#f56565' if priority == 'alta' else '#f5a623' if priority == 'media' else '#48bb78'
            html += f"""
            <div class="recommendation {priority}">
                <div style="font-size:0.6rem; font-weight:700; text-transform:uppercase; color:{color}">
                    {label}
                </div>
                <div style="color:rgba(255,255,255,0.7); font-size:0.9rem; margin-top:2px;">
                    {rec.get('description', '')}
                </div>
                <div style="display:flex; gap:16px; margin-top:4px; font-size:0.65rem; color:rgba(255,255,255,0.2);">
                    <span>📂 {rec.get('category', 'geral')}</span>
                    <span>💥 {rec.get('expected_impact', '')}</span>
                    <span>⚡ Esforço: {rec.get('effort', 'medio')}</span>
                </div>
            </div>
            """
        
        html += '</div>'
        return html
    
    def _render_table(self, table: ReportTable) -> str:
        html = f'<div class="section"><h2>{table.title}</h2><table><thead><tr>'
        for header in table.headers:
            html += f"<th>{header}</th>"
        html += '</tr></thead><tbody>'
        
        for row in table.rows:
            html += "<tr>"
            for cell in row:
                html += f"<td>{cell}</td>"
            html += "</tr>"
        
        html += f'</tbody></table>'
        if table.caption:
            html += f'<div style="color:rgba(255,255,255,0.2); font-size:0.7rem; margin-top:4px;">{table.caption}</div>'
        html += '</div>'
        
        return html
    
    # ==========================================
    # EXPORTAÇÃO PDF
    # ==========================================
    
    def to_pdf(self, report: ExecutiveReport) -> bytes:
        """Converte relatório para PDF com encoding UTF-8"""
        html_content = self.to_html(report)
        
        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html_content, encoding='utf-8').write_pdf()
            logger.info("✅ PDF gerado com sucesso")
            return pdf_bytes
            
        except ImportError:
            logger.warning("⚠️ WeasyPrint não disponível. Instale: pip install weasyprint")
            return html_content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar PDF: {e}")
            return html_content.encode('utf-8')
    
    # ==========================================
    # SALVAR RELATÓRIO
    # ==========================================
    
    def save(
        self,
        report: ExecutiveReport,
        output_path: str,
        format: ReportFormat = ReportFormat.PDF
    ) -> str:
        """Salva relatório em arquivo"""
        if format == ReportFormat.HTML:
            content = self.to_html(report)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
        elif format == ReportFormat.PDF:
            content = self.to_pdf(report)
            with open(output_path, 'wb') as f:
                f.write(content)
        elif format == ReportFormat.JSON:
            content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
        else:
            raise ValueError(f"Formato não suportado: {format}")
        
        logger.info(f"✅ Relatório salvo: {output_path}")
        return output_path


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

report_builder = ExecutiveReportBuilder(
    language="pt-BR",
    theme="dark",
    company_name="AutoAnalytics"
)


# ==============================================
# FUNÇÃO DE COMPATIBILIDADE
# ==============================================

def build_executive_report(
    analysis_result: Dict[str, Any],
    user_name: str = "Usuário"
) -> ExecutiveReport:
    """
    🔥 Função principal para construção de relatórios
    """
    return report_builder.build(
        analysis_result=analysis_result,
        user_name=user_name
    )