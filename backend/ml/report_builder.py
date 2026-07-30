# backend/ml/report_builder.py - CONSTRUTOR DE RELATÓRIOS
"""
🔥 EXECUTIVE REPORT BUILDER - AutoAnalytics
================================================================================
VERSÃO 2.0 - CONSTRUTOR DE RELATÓRIOS COM CONFIGURAÇÕES

RESPONSABILIDADES:
✅ Recebe dados do multi_analysis.py
✅ Monta PDF com layout profissional
✅ Organiza seções do relatório
✅ Ordena prioridades (Alta → Média → Baixa)
✅ Gera índice automático
✅ Aplica estilos e formatação
✅ Gera versão HTML para preview

USO:
    builder = ExecutiveReportBuilder()
    report = builder.build(analysis_result, user_name="João")
    pdf = builder.to_pdf(report)
    html = builder.to_html(report)
================================================================================
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

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
            "table_of_contents": self.table_of_contents
        }


class ExecutiveReportBuilder:
    """
    🔥 Construtor de Relatórios Executivos
    
    Com configurações para:
    - Idioma
    - Tema
    - Logo
    - Templates
    """
    
    def __init__(
        self,
        language: str = "pt-BR",
        theme: str = "dark",
        logo_url: Optional[str] = None,
        company_name: str = "AutoAnalytics"
    ):
        """
        Args:
            language: Idioma do relatório ("pt-BR", "en-US")
            theme: Tema ("dark", "light")
            logo_url: URL da logo da empresa
            company_name: Nome da empresa
        """
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
        
        logger.info(f"✅ ExecutiveReportBuilder inicializado")
        logger.info(f"   🌐 Idioma: {language}")
        logger.info(f"   🎨 Tema: {theme}")
        logger.info(f"   🏢 Empresa: {company_name}")
    
    # ==========================================
    # MÉTODO PRINCIPAL
    # ==========================================
    
    def build(
        self,
        analysis_result: Dict[str, Any],  # ← Resultado do multi_analysis.py
        user_name: str = "Usuário"
    ) -> ExecutiveReport:
        """
        🔥 Constrói relatório executivo a partir do resultado REAL da análise
        """
        logger.info("📄 Construindo relatório executivo...")
        
        # Extrair dados
        executive_score = analysis_result.get('executive_score', {})
        executive_summary = analysis_result.get('executive_summary', '')
        comparison = analysis_result.get('comparison', {})
        trend = analysis_result.get('trend', {})
        recommendations = analysis_result.get('recommendations', [])
        forecast = analysis_result.get('forecast', '')
        general_conclusion = analysis_result.get('general_conclusion', '')
        files = analysis_result.get('files', [])
        
        # Ordenar recomendações
        ordered_recommendations = sorted(
            recommendations,
            key=lambda x: self._priority_order.get(x.get('priority', 'media'), 1)
        )
        
        # Construir seções
        sections = self._build_sections(
            executive_summary=executive_summary,
            comparison=comparison,
            trend=trend,
            forecast=forecast,
            general_conclusion=general_conclusion,
            files=files
        )
        
        # Construir tabelas
        tables = self._build_tables(comparison, files)
        
        # Gerar índice
        toc = self._generate_table_of_contents(sections)
        
        return ExecutiveReport(
            title=f"📊 Relatório Executivo - {self.company_name}",
            subtitle=f"Análise de {analysis_result.get('total_files', 0)} arquivo(s)",
            generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
            author=user_name,
            executive_summary=executive_summary,
            executive_score=executive_score,
            sections=sections,
            tables=tables,
            recommendations=ordered_recommendations,
            comparison=comparison,
            trend=trend,
            forecast=forecast,
            general_conclusion=general_conclusion,
            total_files=analysis_result.get('total_files', 0),
            processed_files=analysis_result.get('processed_files', 0),
            failed_files=analysis_result.get('failed_files', 0),
            processing_time_ms=analysis_result.get('processing_time_ms', 0),
            files=files,
            table_of_contents=toc
        )
    
    # ==========================================
    # CONSTRUIR SEÇÕES
    # ==========================================
    
    def _build_sections(
        self,
        executive_summary: str,
        comparison: Dict[str, Any],
        trend: Dict[str, Any],
        forecast: str,
        general_conclusion: str,
        files: List[Dict[str, Any]]
    ) -> List[ReportSection]:
        """Constrói seções do relatório"""
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
        
        if comparison and any([comparison.get('best_revenue'), comparison.get('best_profit')]):
            sections.append(ReportSection(
                title="📊 Comparação entre Períodos",
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
        
        if comparison.get('best_revenue'):
            lines.append(f"💰 Melhor Receita: **{comparison['best_revenue']}**")
        if comparison.get('best_profit'):
            lines.append(f"💵 Melhor Lucro: **{comparison['best_profit']}**")
        if comparison.get('highest_risk'):
            lines.append(f"⚠️ Maior Risco: **{comparison['highest_risk']}**")
        
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
    # CONSTRUIR TABELAS
    # ==========================================
    
    def _build_tables(
        self,
        comparison: Dict[str, Any],
        files: List[Dict[str, Any]]
    ) -> List[ReportTable]:
        """Constrói tabelas do relatório"""
        tables = []
        
        if files:
            headers = ["Arquivo", "Registros", "Score Médio", "Alto Risco", "Baixo Risco"]
            rows = []
            for file in files:
                if file.get('success'):
                    metrics = file.get('metrics', {})
                    rows.append([
                        file.get('filename', ''),
                        file.get('processed_rows', 0),
                        f"{metrics.get('mean_prediction', 0)*100:.0f}%",
                        f"{metrics.get('high_risk_percentage', 0):.0f}%",
                        f"{metrics.get('low_risk_percentage', 0):.0f}%"
                    ])
            
            if rows:
                tables.append(ReportTable(
                    title="📋 Métricas por Arquivo",
                    headers=headers,
                    rows=rows,
                    caption="Resumo das métricas de cada arquivo analisado"
                ))
        
        return tables
    
    # ==========================================
    # GERAR ÍNDICE
    # ==========================================
    
    def _generate_table_of_contents(self, sections: List[ReportSection]) -> List[Dict[str, Any]]:
        """Gera índice automático"""
        return [{"title": s.title, "level": s.level, "order": s.order} for s in sections]
    
    # ==========================================
    # EXPORTAR PARA HTML
    # ==========================================
    
    def to_html(self, report: ExecutiveReport) -> str:
        """Converte relatório para HTML com tema configurado"""
        
        # Escolher tema
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
        <style>
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
        </style>
        """
        
        # Montar HTML (mesmo da versão anterior)
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{report.title}</title>
            {css}
        </head>
        <body>
            <div class="report-header">
                <h1>{report.title}</h1>
                <div style="color:{text_muted}; font-size:1rem;">{report.subtitle}</div>
                <div style="color:{text_muted}; font-size:0.8rem; margin-top:12px;">
                    Gerado em {report.generated_at} • {report.author}
                    • {report.total_files} arquivo(s) • {report.processing_time_ms:.0f}ms
                </div>
            </div>
            
            <div class="section">
                <h2>📑 Índice</h2>
                {self._render_toc(report.table_of_contents)}
            </div>
        """
        
        # Score
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
        
        html += f"""
            <div class="footer">
                {self.company_name} v3.0 • Relatório gerado automaticamente por IA • {report.generated_at}
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _render_toc(self, toc: List[Dict[str, Any]]) -> str:
        """Renderiza índice"""
        html = '<div style="display:grid; grid-template-columns:1fr 1fr; gap:4px 20px;">'
        for item in toc:
            indent = "&nbsp;" * ((item['level'] - 1) * 16)
            html += f'<div style="color:rgba(255,255,255,0.4); font-size:0.8rem;">{indent}{item["title"]}</div>'
        html += '</div>'
        return html
    
    def _render_score(self, score: Dict[str, Any]) -> str:
        """Renderiza score executivo"""
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
        """Renderiza uma seção"""
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
        """Renderiza recomendações"""
        html = '<div class="section"><h2>🎯 Recomendações Priorizadas</h2>'
        
        for rec in recommendations:
            priority = rec.get('priority', 'media')
            label = self._priority_labels.get(priority, '📌')
            html += f"""
            <div class="recommendation {priority}">
                <div style="font-size:0.6rem; font-weight:700; text-transform:uppercase; color:{'#f56565' if priority=='alta' else '#f5a623' if priority=='media' else '#48bb78'}">
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
        """Renderiza uma tabela"""
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
    # EXPORTAR PARA PDF
    # ==========================================
    
    def to_pdf(self, report: ExecutiveReport) -> bytes:
        """Converte relatório para PDF"""
        html_content = self.to_html(report)
        
        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html_content).write_pdf()
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
            content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
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