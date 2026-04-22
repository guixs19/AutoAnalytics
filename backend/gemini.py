# backend/gemini.py - Serviço de integração com Google Gemini
import google.generativeai as genai
import json
import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core import exceptions as google_exceptions
from config.settings import settings

# Configuração de logging
logger = logging.getLogger(__name__)


class GeminiService:
    """
    Serviço especializado em análise de dados de oficinas mecânicas
    
    Utiliza Gemini 2.5 Flash para processamento rápido e eficiente de:
    - Clientes e fidelização
    - Serviços realizados
    - Estoque e peças
    - Financeiro e faturamento
    - Métricas operacionais
    """
    
    # Constantes de configuração
    MODEL_NAME = 'gemini-2.5-flash'  # Versão mais recente e rápida
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30
    MAX_TOKENS = 4096
    
    # Instrução de sistema especializada para oficinas
    SYSTEM_INSTRUCTION = (
        "Você é um Especialista em Gestão de Oficinas Mecânicas e Análise de Dados Automotivos. "
        "Sua função é analisar dados de oficinas e fornecer insights práticos para gestão. "
        "Seja direto, objetivo e foque em ações que gerem resultados reais. "
        "Use linguagem clara, evitando jargões técnicos desnecessários. "
        "Sempre que possível, sugira métricas de KPIs e benchmarks do setor automotivo."
    )
    
    def __init__(self):
        """Inicializa o serviço com Gemini 2.5 Flash"""
        self.api_key = self._get_api_key()
        self.model = None
        self._initialize_model()
    
    def _get_api_key(self) -> Optional[str]:
        """Obtém e valida a API key do settings"""
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        
        # Verifica se é uma chave válida
        invalid_keys = [None, "", "opcional", "sua_chave_aqui", "your_api_key_here"]
        
        if api_key in invalid_keys:
            logger.warning("⚠️ GEMINI_API_KEY não encontrada ou inválida!")
            return None
        
        key_preview = api_key[:8] + "..." if len(api_key) > 8 else "***"
        logger.info(f"🔑 API key configurada: {key_preview}")
        
        return api_key
    
    def _initialize_model(self) -> None:
        """Inicializa o modelo Gemini 2.5 Flash com configurações otimizadas"""
        if not self.api_key:
            return
        
        try:
            genai.configure(api_key=self.api_key)
            
            # Configuração otimizada para análise rápida de dados de oficina
            generation_config = {
                "temperature": 0.3,  # Baixo para respostas consistentes
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": self.MAX_TOKENS,
                "candidate_count": 1,
            }
            
            # Configuração de segurança (moderada para análises legítimas)
            safety_settings = {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE",
            }
            
            # Modelo principal - Gemini 2.5 Flash
            self.model = genai.GenerativeModel(
                model_name=self.MODEL_NAME,
                system_instruction=self.SYSTEM_INSTRUCTION,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            logger.info(f"✅ Gemini inicializado com sucesso - Modelo: {self.MODEL_NAME}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Gemini: {str(e)}")
            self.model = None
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (google_exceptions.ServiceUnavailable, 
             google_exceptions.ResourceExhausted,
             ConnectionError,
             asyncio.TimeoutError)
        )
    )
    async def _call_gemini(self, prompt: str) -> Optional[str]:
        """
        Faz chamada à API Gemini com retry automático
        
        Args:
            prompt: Prompt para o modelo
            
        Returns:
            Resposta do modelo ou None
        """
        if not self.model:
            logger.error("Modelo Gemini não disponível")
            return None
        
        try:
            loop = asyncio.get_event_loop()
            
            # Chamada com timeout
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.model.generate_content(prompt)),
                timeout=self.TIMEOUT_SECONDS
            )
            
            if response and response.text:
                logger.debug(f"✅ Resposta recebida ({len(response.text)} caracteres)")
                return response.text
            else:
                logger.warning("⚠️ Resposta vazia do Gemini")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout após {self.TIMEOUT_SECONDS} segundos")
            raise
            
        except google_exceptions.ResourceExhausted as e:
            logger.error(f"🚫 Cota da API esgotada: {str(e)}")
            raise
            
        except Exception as e:
            logger.error(f"❌ Erro na chamada Gemini: {str(e)}")
            raise
    
    async def analyze_office_data(self, data_type: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analisa dados específicos de oficina mecânica
        
        Args:
            data_type: Tipo de dados (clientes, servicos, estoque, financeiro, metricas)
            analysis_data: Dados a serem analisados
            
        Returns:
            Dicionário com insights e recomendações
        """
        if not self.model:
            return self._get_fallback_response("Gemini não configurado. Verifique sua API key.")
        
        if not analysis_data:
            logger.warning(f"Dados vazios para análise do tipo: {data_type}")
            return self._get_fallback_response("Nenhum dado fornecido para análise.")
        
        try:
            # Prepara prompt específico para o tipo de dado
            prompt = self._build_office_prompt(data_type, analysis_data)
            
            logger.info(f"🏪 Analisando dados de oficina - Tipo: {data_type}")
            response_text = await self._call_gemini(prompt)
            
            if response_text:
                return {
                    "success": True,
                    "ai_available": True,
                    "data_type": data_type,
                    "insights": self._extract_insights(response_text, data_type),
                    "recommendations": self._extract_recommendations(response_text, data_type),
                    "full_analysis": response_text,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return self._get_fallback_response("Falha na geração da análise.")
                
        except google_exceptions.ResourceExhausted:
            return self._get_fallback_response("Cota da API esgotada. Tente novamente mais tarde.")
        except Exception as e:
            logger.exception(f"Erro em analyze_office_data: {str(e)}")
            return self._get_fallback_response(f"Erro na análise: {str(e)}")
    
    def _build_office_prompt(self, data_type: str, data: Dict[str, Any]) -> str:
        """
        Constrói prompt especializado para análise de oficina com tratamento inteligente de dados
        """
        
        # Mapeamento de emojis e ícones por tipo de análise
        icons = {
            "clientes": "👥", "servicos": "🔧", "estoque": "📦", 
            "financeiro": "💰", "metricas": "📊", "default": "📈",
            "auto": "🤖"
        }
        icon = icons.get(data_type, icons["default"])
        
        # Truncamento inteligente - preserva estrutura JSON
        data_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        max_length = 8000
        
        if len(data_str) > max_length:
            truncated = data_str[:max_length]
            last_comma = truncated.rfind(',')
            if last_comma > max_length - 500:
                data_str = truncated[:last_comma] + '\n  ... (dados truncados para análise)\n}'
            else:
                data_str = truncated + '\n... (dados truncados para análise)'
            
            logger.info(f"Dados truncados: {len(json.dumps(data, default=str))} -> {len(data_str)} caracteres")
        
        # Prompts especializados por tipo de dado
        prompts = {
            "clientes": f"""
{icon} **ANÁLISE DE CLIENTES**

**Objetivo:** Identificar padrões de comportamento, fidelização e oportunidades.

**Responda em tópicos:**
• Perfil dos clientes (recorrência, ticket médio, top 20%)
• Taxa de retenção e padrões de churn
• Oportunidades de cross-selling e fidelização
• KPIs sugeridos para acompanhamento
""",
            
            "servicos": f"""
{icon} **ANÁLISE DE SERVIÇOS**

**Objetivo:** Otimizar operação, precificação e produtividade.

**Responda em tópicos:**
• Serviços mais comuns e mais lucrativos
• Tempo médio de execução vs. padrão
• Gargalos e oportunidades de agilização
• Sugestões de precificação e pacotes
""",
            
            "estoque": f"""
{icon} **ANÁLISE DE ESTOQUE**

**Objetivo:** Otimizar giro de peças e reduzir custos.

**Responda em tópicos:**
• Giro de estoque (rápido/lento) e peças paradas
• Risco de ruptura e itens críticos
• Sugestões para peças de giro lento
• Ponto de pedido ideal e fornecedores estratégicos
""",
            
            "financeiro": f"""
{icon} **ANÁLISE FINANCEIRA**

**Objetivo:** Avaliar saúde financeira e identificar oportunidades.

**Responda em tópicos:**
• Tendência de faturamento e margem líquida
• Principais custos e oportunidades de redução
• Ponto de equilíbrio e sazonalidade
• Metas financeiras realistas
""",
            
            "metricas": f"""
{icon} **ANÁLISE DE MÉTRICAS**

**Objetivo:** Avaliar desempenho geral e definir KPIs.

**Responda em tópicos:**
• KPIs que estão bons vs. precisam atenção
• Pontos fortes e principais gargalos
• Sugestão de metas para próximos 3 meses
• Ações prioritárias e responsáveis
""",
            
            "auto": f"""
{icon} **ANÁLISE AUTOMÁTICA**

**Objetivo:** Analisar dados detectados automaticamente.

**Responda em tópicos:**
• Principais padrões identificados
• Anomalias ou pontos de atenção
• Oportunidades de melhoria
• Recomendações práticas
"""
        }
        
        specific_prompt = prompts.get(data_type, prompts.get("auto", f"""
{icon} **ANÁLISE DE {data_type.upper()}**

**Objetivo:** Analisar os dados e gerar insights acionáveis.

**Responda em tópicos:**
• Principais padrões identificados
• Oportunidades de melhoria
• Recomendações práticas
"""))
        
        full_prompt = f"""{specific_prompt}**DADOS RECEBIDOS:**```json{data_str}"""