# backend/gemini.py - Serviço de integração com Google Gemini
import google.generativeai as genai
import json
import asyncio
import logging
import re
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core import exceptions as google_exceptions

# Carregar variáveis de ambiente
from dotenv import load_dotenv
from pathlib import Path

# Força o carregamento do .env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Configuração de logging
logger = logging.getLogger(__name__)


class GeminiService:
    """
    Serviço especializado em análise de dados de oficinas mecânicas
    Utiliza Gemini 2.5 Flash para processamento rápido e eficiente
    """
    
    # Constantes de configuração
    MODEL_NAME = 'gemini-2.5-flash'
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30
    MAX_TOKENS = 4096
    
    SYSTEM_INSTRUCTION = (
        "Você é um Especialista em Gestão de Oficinas Mecânicas e Análise de Dados Automotivos. "
        "Sua função é analisar dados de oficinas e fornecer insights práticos para gestão. "
        "Seja direto, objetivo e foque em ações que gerem resultados reais. "
        "Use linguagem clara, evitando jargões técnicos desnecessários."
    )
    
    def __init__(self, force_reload=False):
        """Inicializa o serviço com Gemini 2.5 Flash"""
        self.api_key = self._get_api_key(force_reload=force_reload)
        self.model = None
        
        if self.api_key:
            self._initialize_model()
        else:
            logger.error("❌ Não foi possível inicializar Gemini sem API key válida")
    
    def _get_api_key(self, force_reload=False) -> Optional[str]:
        """Obtém e valida a API key com múltiplas estratégias"""
        if force_reload:
            env_path = Path(__file__).parent.parent / '.env'
            load_dotenv(dotenv_path=env_path, override=True)
            logger.info("🔄 .env recarregado")
        
        # Estratégia 1: Tentar do settings
        try:
            from config.settings import settings
            api_key = getattr(settings, "GEMINI_API_KEY", None)
            if api_key and self._is_valid_key(api_key):
                logger.info("✅ API key encontrada no settings")
                return api_key
        except ImportError:
            pass
        
        # Estratégia 2: Tentar do os.environ
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key and self._is_valid_key(api_key):
            logger.info("✅ API key encontrada no os.environ")
            return api_key
        
        # Estratégia 3: Tentar alternativas
        api_key = os.environ.get("GEMINI_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key and self._is_valid_key(api_key):
            logger.info("✅ API key encontrada em variável alternativa")
            return api_key
        
        logger.error("❌ NENHUMA API key válida encontrada!")
        logger.error(f"   Caminho esperado do .env: {Path(__file__).parent.parent / '.env'}")
        
        return None
    
    def _is_valid_key(self, api_key: str) -> bool:
        """Valida se a chave parece ser uma API key do Google"""
        api_key = str(api_key).strip().replace('\n', '').replace('\r', '')
        
        invalid_values = [None, "", "opcional", "sua_chave_aqui", "your_api_key_here"]
        
        if api_key in invalid_values:
            return False
        
        if len(api_key) < 20:
            return False
        
        if not re.match(r'^[A-Za-z0-9\-_]+$', api_key):
            return False
        
        key_preview = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        logger.info(f"🔑 API key válida (tamanho: {len(api_key)}, preview: {key_preview})")
        return True
    
    def _initialize_model(self) -> None:
        """Inicializa o modelo Gemini"""
        if not self.api_key:
            return
        
        try:
            clean_key = self.api_key.strip().replace('\n', '').replace('\r', '')
            genai.configure(api_key=clean_key)
            
            generation_config = {
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": self.MAX_TOKENS,
            }
            
            self.model = genai.GenerativeModel(
                model_name=self.MODEL_NAME,
                system_instruction=self.SYSTEM_INSTRUCTION,
                generation_config=generation_config
            )
            
            logger.info(f"✅ Gemini inicializado - Modelo: {self.MODEL_NAME}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Gemini: {str(e)}")
            self.model = None
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _call_gemini(self, prompt: str) -> Optional[str]:
        """Faz chamada à API Gemini com retry"""
        if not self.model:
            logger.error("Modelo Gemini não disponível")
            return None
        
        try:
            loop = asyncio.get_event_loop()
            
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.model.generate_content(prompt)),
                timeout=self.TIMEOUT_SECONDS
            )
            
            if response and response.text:
                logger.debug(f"✅ Resposta recebida ({len(response.text)} caracteres)")
                return response.text
            else:
                logger.warning("⚠️ Resposta vazia")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout após {self.TIMEOUT_SECONDS} segundos")
            raise
        except Exception as e:
            logger.error(f"❌ Erro na chamada Gemini: {str(e)}")
            raise
    
    async def analyze_office_data(self, data_type: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa dados específicos de oficina"""
        if not self.model:
            return self._get_fallback_response("Gemini não configurado")
        
        if not analysis_data:
            return self._get_fallback_response("Nenhum dado fornecido")
        
        try:
            prompt = self._build_office_prompt(data_type, analysis_data)
            
            logger.info(f"🏪 Analisando dados - Tipo: {data_type}")
            response_text = await self._call_gemini(prompt)
            
            if response_text:
                return {
                    "success": True,
                    "ai_available": True,
                    "data_type": data_type,
                    "insights": self._extract_insights(response_text),
                    "recommendations": self._extract_recommendations(response_text),
                    "full_analysis": response_text,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return self._get_fallback_response("Falha na geração da análise")
                
        except Exception as e:
            logger.exception(f"Erro: {str(e)}")
            return self._get_fallback_response(f"Erro: {str(e)}")
    
    def _build_office_prompt(self, data_type: str, data: Dict[str, Any]) -> str:
        """Constrói prompt sem aspas triplas internas"""
        
        icons = {
            "clientes": "👥", "servicos": "🔧", "estoque": "📦", 
            "financeiro": "💰", "metricas": "📊", "default": "📈"
        }
        icon = icons.get(data_type, icons["default"])
        
        # Converte dados para string JSON de forma segura
        data_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        
        # Limita tamanho
        if len(data_str) > 6000:
            data_str = data_str[:6000] + "\n... (dados truncados)"
        
        # Construção segura - sem aspas triplas internas
        prompt_lines = []
        prompt_lines.append(f"{icon} ANALISE DE {data_type.upper()}")
        prompt_lines.append("")
        prompt_lines.append("Objetivo: Analisar os dados e gerar insights acionaveis.")
        prompt_lines.append("")
        prompt_lines.append("Responda em topicos:")
        prompt_lines.append("- Principais padroes identificados")
        prompt_lines.append("- Oportunidades de melhoria")
        prompt_lines.append("- Recomendacoes praticas")
        prompt_lines.append("")
        prompt_lines.append("DADOS RECEBIDOS:")
        prompt_lines.append("")
        prompt_lines.append(data_str)
        
        return "\n".join(prompt_lines)
    
    def _extract_insights(self, text: str) -> List[str]:
        """Extrai insights do texto"""
        insights = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('•') or line.startswith('*')):
                insights.append(line.lstrip('-•* ').strip())
                if len(insights) >= 5:
                    break
        
        if not insights:
            insights = ["Análise gerada com sucesso", "Consulte os detalhes completos"]
        
        return insights
    
    def _extract_recommendations(self, text: str) -> List[str]:
        """Extrai recomendações"""
        recommendations = []
        
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['recomend', 'sugest', 'acao', 'kpi', 'meta']):
                if line.strip() and len(line) < 200:
                    clean_line = line.strip().lstrip('-•* 0123456789.')
                    if clean_line and len(clean_line) > 5:
                        recommendations.append(clean_line)
                        if len(recommendations) >= 3:
                            break
        
        if not recommendations:
            recommendations = ["Monitorar KPIs mensalmente", "Revisar dados periodicamente"]
        
        return recommendations[:3]
    
    def _get_fallback_response(self, error_msg: str) -> Dict[str, Any]:
        """Resposta de fallback"""
        return {
            "success": False,
            "ai_available": False,
            "error": error_msg,
            "insights": ["Serviço de IA não disponível"],
            "recommendations": ["Verifique a configuração da API", "Tente novamente mais tarde"],
            "timestamp": datetime.now().isoformat()
        }


# ============================================================
# CRIA A INSTÂNCIA GLOBAL para ser importada por outros módulos
# ============================================================
try:
    gemini_service = GeminiService()
    logger.info("✅ GeminiService global inicializado com sucesso")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar GeminiService global: {e}")
    gemini_service = None

# Também exporta a classe para uso direto
__all__ = ['GeminiService', 'gemini_service']