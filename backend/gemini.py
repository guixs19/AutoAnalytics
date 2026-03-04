import httpx
import json
import aiofiles
import asyncio
import pandas as pd
from typing import Dict, Any, Optional
import uuid
import os
from datetime import datetime

from config.settings import settings

class FlowiseService:
    """Serviço de integração com Flowise Cloud"""
    
    def __init__(self):
        self.flowise_url = settings.FLOWISE_URL
        self.api_key = settings.FLOWISE_API_KEY
        self.headers = {
            "Content-Type": "application/json"
        }
        
        # Adicionar API key se existir
        if self.api_key and self.api_key != "opcional" and self.api_key != "sua_chave_aqui":
            self.headers["Authorization"] = f"Bearer {self.api_key}"
    
    async def send_to_flowise(self, question: str, data: Dict, context: str = "oficina") -> Dict:
        """
        Envia dados para sua instância do Flowise Cloud
        
        Args:
            question: Pergunta/contexto para a IA
            data: Dados para análise
            context: Contexto da análise (oficina, clientes, etc.)
            
        Returns:
            Resposta da IA
        """
        try:
            # Preparar payload para sua URL específica
            payload = {
                "question": question,
                "context": context,
                "data": data,
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "source": "autoanalytics",
                    "version": "1.0"
                }
            }
            
            print(f"🌐 Enviando para Flowise: {self.flowise_url}")
            
            # Configurar timeout maior para processamento da IA
            timeout = httpx.Timeout(60.0, connect=10.0)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.flowise_url,
                    json=payload,
                    headers=self.headers
                )
                
                print(f"📥 Resposta Flowise: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ Flowise respondeu com sucesso")
                    return self._process_flowise_response(result)
                else:
                    error_msg = f"Erro {response.status_code}"
                    if response.text:
                        try:
                            error_data = response.json()
                            error_msg = error_data.get('message', error_msg)
                        except:
                            error_msg = response.text[:200]
                    
                    print(f"❌ Erro Flowise: {error_msg}")
                    return self._get_fallback_response(question, data)
                    
        except httpx.TimeoutException:
            print("⏰ Timeout ao conectar com Flowise")
            return self._get_fallback_response(question, data)
            
        except Exception as e:
            print(f"❌ Erro na comunicação: {str(e)}")
            return self._get_fallback_response(question, data)
    
    def _process_flowise_response(self, response: Dict) -> Dict:
        """Processa resposta do Flowise"""
        # Sua resposta do Flowise pode ter diferentes formatos
        # Ajuste conforme o que seu flow retorna
        
        # Tenta diferentes formatos comuns do Flowise
        if isinstance(response, dict):
            # Formato 1: Resposta direta
            if "text" in response:
                return {
                    "success": True,
                    "insights": [response["text"]],
                    "recommendations": [],
                    "analysis": "Análise completa pela IA"
                }
            
            # Formato 2: Com estrutura de resposta
            elif "response" in response:
                text = response["response"]
                return {
                    "success": True,
                    "insights": self._extract_insights(text),
                    "recommendations": self._extract_recommendations(text),
                    "raw_response": text
                }
            
            # Formato 3: Retorno direto do chatflow
            else:
                # Pega a primeira chave string que pareça ser a resposta
                for key, value in response.items():
                    if isinstance(value, str) and len(value) > 10:
                        return {
                            "success": True,
                            "insights": self._extract_insights(value),
                            "recommendations": self._extract_recommendations(value),
                            "raw_response": value
                        }
        
        # Se não reconhecer o formato, retorna fallback
        return self._get_fallback_response("Análise", {})
    
    def _extract_insights(self, text: str) -> list:
        """Extrai insights do texto da IA"""
        insights = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and len(line) > 20:
                # Identifica insights com marcadores comuns
                if line.startswith(('•', '-', '*', '→', '📊', '🔍', '💡')):
                    insights.append(line)
                elif any(word in line.lower() for word in ['importante', 'recomendo', 'sugiro', 'atenção', 'destaque']):
                    insights.append(f"💡 {line}")
        
        return insights[:5] if insights else ["Análise realizada com sucesso."]
    
    def _extract_recommendations(self, text: str) -> list:
        """Extrai recomendações do texto da IA"""
        recommendations = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip().lower()
            if any(word in line for word in ['sugestão', 'recomendação', 'ação', 'faça', 'melhore', 'otimize']):
                rec = line.capitalize()
                if not rec.startswith(('•', '-', '*')):
                    rec = f"✅ {rec}"
                recommendations.append(rec)
        
        return recommendations[:3] if recommendations else [
            "Revise regularmente os dados",
            "Compare com períodos anteriores",
            "Identifique oportunidades de melhoria"
        ]
    
    def _get_fallback_response(self, question: str, data: Dict) -> Dict:
        """Resposta fallback quando o Flowise não está disponível"""
        print("🔄 Usando resposta fallback (IA offline)")
        
        insights = []
        
        # Gera insights básicos baseados nos dados
        if "analysis" in data:
            analysis = data["analysis"]
            
            # Insights baseados em análise estatística
            if "sumario" in analysis:
                summary = analysis["sumario"]
                
                if "media_valores_numericos" in summary:
                    medias = summary["media_valores_numericos"]
                    if medias:
                        avg = sum(medias.values()) / len(medias)
                        insights.append(f"📊 Média geral dos valores: R$ {avg:.2f}")
                
                if "contagem_categorias" in summary:
                    categorias = summary["contagem_categorias"]
                    if categorias:
                        insights.append(f"📈 {len(categorias)} categorias analisadas")
        
        # Adiciona insights padrão
        if not insights:
            insights = [
                "📋 Análise básica concluída",
                f"🔍 {len(data.get('sample_data', []))} registros analisados",
                "💼 Dados preparados para tomada de decisão"
            ]
        
        return {
            "success": False,
            "insights": insights,
            "recommendations": [
                "✅ Mantenha os dados atualizados",
                "✅ Compare com períodos anteriores",
                "✅ Identifique padrões recorrentes"
            ],
            "ai_available": False,
            "message": "IA offline - Análise básica concluída"
        }
    
    async def analyze_office_data(self, data_type: str, analysis_data: Dict) -> Dict:
        """
        Análise específica para dados de oficina
        
        Args:
            data_type: Tipo de dados (clientes, servicos, estoque, financeiro)
            analysis_data: Dados da análise
            
        Returns:
            Insights da IA
        """
        questions_map = {
            "clientes": "Analise este conjunto de dados de clientes de oficina mecânica. Identifique padrões de fidelização, clientes mais valiosos, oportunidades de retenção e sugestões para melhorar o relacionamento.",
            "servicos": "Analise estes dados de serviços realizados em uma oficina. Identifique os serviços mais comuns, tempo médio por serviço, sazonalidade, e sugira otimizações no fluxo de trabalho.",
            "estoque": "Analise estes dados de estoque de peças de oficina. Identifique peças com alta/baixa rotatividade, sugira ajustes no inventário, e aponte oportunidades de economia.",
            "financeiro": "Analise estes dados financeiros da oficina. Identifique tendências de faturamento, despesas principais, margens de lucro, e sugira ações para melhorar a saúde financeira."
        }
        
        question = questions_map.get(data_type, "Analise estes dados de oficina mecânica e forneça insights úteis.")
        
        return await self.send_to_flowise(question, analysis_data, data_type)
    
    async def generate_report(self, process_id: str, analysis_type: str, 
                            insights: Dict, analysis: Dict, ai_response: Dict) -> str:
        """Gera relatório completo"""
        report = []
        report.append("=" * 70)
        report.append(f"RELATÓRIO AUTOANALYTICS - OFICINA MECÂNICA")
        report.append("=" * 70)
        report.append(f"📋 ID: {process_id}")
        report.append(f"🔧 Tipo: {analysis_type}")
        report.append(f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        report.append("=" * 70)
        report.append("")
        
        # Resumo da análise
        report.append("📊 RESUMO DA ANÁLISE")
        report.append(f"  • Arquivo processado com sucesso")
        report.append(f"  • Tipo de análise: {analysis_type}")
        
        if "total_linhas" in insights:
            report.append(f"  • Total de registros: {insights['total_linhas']}")
        if "total_colunas" in insights:
            report.append(f"  • Colunas analisadas: {insights['total_colunas']}")
        
        report.append("")
        
        # Insights da IA
        report.append("🤖 INSIGHTS DA INTELIGÊNCIA ARTIFICIAL")
        report.append("-" * 50)
        
        if ai_response.get("success", False) or ai_response.get("ai_available", False):
            for insight in ai_response.get("insights", []):
                report.append(f"  • {insight}")
            
            report.append("")
            report.append("💡 RECOMENDAÇÕES")
            for rec in ai_response.get("recommendations", []):
                report.append(f"  • {rec}")
        else:
            report.append("  ⚠️  IA temporariamente indisponível")
            report.append("  📋 Análise estatística básica concluída:")
            for insight in ai_response.get("insights", []):
                report.append(f"    {insight}")
        
        report.append("")
        
        # Métricas principais
        report.append("📈 MÉTRICAS PRINCIPAIS")
        if "sumario" in analysis:
            summary = analysis["sumario"]
            
            if "media_valores_numericos" in summary and summary["media_valores_numericos"]:
                report.append(f"  • Valores médios calculados")
            
            if "contagem_categorias" in summary and summary["contagem_categorias"]:
                total_cats = sum(len(v) if isinstance(v, dict) else 1 for v in summary["contagem_categorias"].values())
                report.append(f"  • {total_cats} categorias analisadas")
        
        report.append("")
        
        # Ações recomendadas
        report.append("🎯 AÇÕES RECOMENDADAS")
        report.append("  1. Revise este relatório com sua equipe")
        report.append("  2. Implemente as recomendações prioritárias")
        report.append("  3. Agende próxima análise para acompanhamento")
        report.append("  4. Documente os resultados alcançados")
        
        report.append("")
        report.append("=" * 70)
        report.append("AutoAnalytics 🤖 + Flowise IA")
        report.append("Transformando dados em resultados para sua oficina")
        report.append("=" * 70)
        
        return "\n".join(report)
    
    async def save_report_to_file(self, report_content: str, process_id: str) -> str:
        """Salva relatório em arquivo"""
        await self._ensure_output_dir()
        
        filename = f"relatorio_oficina_{process_id}.txt"
        filepath = os.path.join(settings.OUTPUT_DIR, filename)
        
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(report_content)
        
        print(f"💾 Relatório salvo: {filepath}")
        return filepath
    
    async def _ensure_output_dir(self):
        """Garante que o diretório de saída existe"""
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

# Alias para compatibilidade
GeminiService = FlowiseService