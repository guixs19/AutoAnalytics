# backend/gemini.py - VERSÃO ATUALIZADA PARA SDK 0.8.0+

"""
Serviço de integração com Google Gemini - VERSÃO ATUALIZADA
🔥 SDK google-generativeai >= 0.8.0 com suporte a system_instruction
"""

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
    TIMEOUT_SECONDS = 60
    MAX_TOKENS = 8192
    MAX_PROMPT_SIZE = 50000
    
    SYSTEM_INSTRUCTION = (
        "Você é um Especialista em Gestão de Oficinas Mecânicas e Análise de Dados Automotivos. "
        "Sua função é analisar dados de oficinas e fornecer insights práticos para gestão. "
        "Seja direto, objetivo e foque em ações que gerem resultados reais. "
        "Use linguagem clara, evitando jargões técnicos desnecessários. "
        "Sempre use marcadores '-' para cada item em suas listas."
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
        """Inicializa o modelo Gemini com suporte a system_instruction"""
        if not self.api_key:
            return
        
        try:
            clean_key = self.api_key.strip().replace('\n', '').replace('\r', '')
            
            # 🔥 Configura a API
            genai.configure(api_key=clean_key)
            
            # 🔥 Configuração de geração
            generation_config = {
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": self.MAX_TOKENS,
            }
            
            # 🔥 NOVO: Cria o modelo com system_instruction (SDK 0.8.0+)
            # Verifica se o SDK suporta system_instruction
            import inspect
            sig = inspect.signature(genai.GenerativeModel.__init__)
            params = sig.parameters
            
            if 'system_instruction' in params:
                # Versão recente com suporte
                self.model = genai.GenerativeModel(
                    model_name=self.MODEL_NAME,
                    system_instruction=self.SYSTEM_INSTRUCTION,
                    generation_config=generation_config
                )
                logger.info(f"✅ Gemini inicializado com system_instruction (SDK 0.8.0+)")
            else:
                # Fallback para versões antigas
                logger.warning("⚠️ SDK não suporta system_instruction - usando fallback")
                self.model = genai.GenerativeModel(
                    model_name=self.MODEL_NAME,
                    generation_config=generation_config
                )
                # Armazena a instrução para ser adicionada ao prompt
                self._system_instruction_fallback = self.SYSTEM_INSTRUCTION
            
            logger.info(f"✅ Gemini inicializado - Modelo: {self.MODEL_NAME}")
            logger.info(f"   Timeout: {self.TIMEOUT_SECONDS}s | Max tokens: {self.MAX_TOKENS}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Gemini: {str(e)}")
            logger.error(f"   Tipo: {type(e).__name__}")
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
            
            logger.debug(f"📤 Enviando prompt para Gemini ({len(prompt)} caracteres)")
            
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
            logger.info(f"📏 Tamanho do prompt: {len(prompt)} caracteres")
            
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
        """Constrói prompt com formato de resposta explícito"""
        
        icons = {
            "clientes": "👥", "servicos": "🔧", "estoque": "📦", 
            "financeiro": "💰", "metricas": "📊", "default": "📈"
        }
        icon = icons.get(data_type, icons["default"])
        
        # Converte dados para string JSON de forma segura
        data_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        
        original_size = len(data_str)
        
        # Limite de 50KB
        if len(data_str) > self.MAX_PROMPT_SIZE:
            truncated_size = self.MAX_PROMPT_SIZE
            data_str = data_str[:self.MAX_PROMPT_SIZE] + "\n... (dados truncados para otimizar processamento)"
            logger.info(f"📉 Dados truncados: {original_size} → {truncated_size} caracteres")
        else:
            logger.info(f"📊 Dados enviados integralmente: {original_size} caracteres")
        
        # Extrair estatísticas principais
        stats_summary = ""
        if 'data_summary' in data:
            summary = data.get('data_summary', {})
            if isinstance(summary, dict):
                stats_summary = f"\n**Resumo dos dados:** {summary.get('diagnostico', {}).get('mensagem', '')}"
        
        # 🔥 Se o SDK não suporta system_instruction, adiciona ao prompt
        system_prefix = ""
        if hasattr(self, '_system_instruction_fallback'):
            system_prefix = f"{self._system_instruction_fallback}\n\n"
        
        prompt = f"""{system_prefix}{icon} ANALISE DE {data_type.upper()}

**Formato obrigatório da resposta (use exatamente estes cabeçalhos e marcadores '-'):**

## Principais Padrões Identificados
- [insight 1 descritivo baseado nos dados]
- [insight 2 descritivo baseado nos dados]
- [insight 3 descritivo baseado nos dados]

## Oportunidades de Melhoria
- [oportunidade 1]
- [oportunidade 2]

## Recomendações Práticas
- [recomendação 1 acionável]
- [recomendação 2 acionável]
- [recomendação 3 acionável]
{stats_summary}

**Dados para análise:**
{data_str}

Responda APENAS no formato acima, sempre usando marcadores '-' para cada item.
Seja específico e objetivo baseado nos dados fornecidos.
Se os dados foram truncados, foque nos padrões mais importantes que você consegue identificar."""

        return prompt
    
    def _extract_insights(self, text: str) -> List[str]:
        """Extrai insights do texto - VERSÃO ROBUSTA"""
        insights = []
        lines = text.split('\n')
        
        # Padrões para identificar linhas de insight
        patterns = [
            (r'^[-•*]\s*(.+)', None),
            (r'^\d+[\.\)]\s*(.+)', None),
            (r'^#{1,3}\s*(.+)', None),
            (r'^►\s*(.+)', None),
            (r'^✅\s*(.+)', None),
            (r'^→\s*(.+)', None),
            (r'^•\s*(.+)', None),
            (r'^[-\*]\s*\*\*(.+?)\*\*', None),
        ]
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            matched = False
            for pattern, _ in patterns:
                match = re.match(pattern, line)
                if match:
                    clean_text = match.group(1).strip()
                    if 10 < len(clean_text) < 300:
                        insights.append(clean_text)
                        matched = True
                        break
            
            if not matched and len(line) < 200 and not line.endswith(':'):
                insight_keywords = ['padrão', 'oportunidade', 'melhoria', 'média', 'total', 
                                   'cliente', 'serviço', 'aumento', 'redução', 'tendência',
                                   'mais', 'menos', 'maior', 'menor', 'cresceu', 'diminuiu']
                if any(keyword in line.lower() for keyword in insight_keywords):
                    insights.append(line[:150])
            
            if len(insights) >= 5:
                break
        
        if not insights:
            insights = [
                "📊 Análise concluída com sucesso",
                "📈 Consulte os detalhes completos da análise",
                "💡 Utilize os dados para tomada de decisão"
            ]
        
        return insights[:5]
    
    def _extract_recommendations(self, text: str) -> List[str]:
        """Extrai recomendações - VERSÃO ROBUSTA"""
        recommendations = []
        lines = text.split('\n')
        
        action_keywords = [
            'recomend', 'sugest', 'ação', 'implement', 'melhor', 'otimize', 'revise', 
            'monitore', 'crie', 'estabeleça', 'defina', 'invista', 'capacite', 
            'automatize', 'padronize', 'treine', 'avalie', 'kpi', 'meta',
            'priorize', 'adote', 'utilize', 'evite', 'reduza', 'aumente',
            'execute', 'planeje', 'organize', 'controle', 'verifique', 'analise'
        ]
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean or len(line_clean) < 5 or len(line_clean) > 250:
                continue
            
            line_lower = line_clean.lower()
            
            has_action = any(keyword in line_lower for keyword in action_keywords)
            has_marker = bool(re.match(r'^[-•*\d][\.\)]?\s*', line_clean))
            is_recommend_section = any(sec in line_lower for sec in ['recomend', 'sugest', 'ação', 'prática'])
            
            if (has_action or has_marker or is_recommend_section) and len(line_clean) > 15:
                clean = re.sub(r'^[-•*\d][\.\)]?\s*', '', line_clean)
                clean = re.sub(r'^\*\*(.+?)\*\*:\s*', '', clean)
                clean = re.sub(r'^#{1,3}\s*', '', clean)
                
                if len(clean) > 10 and clean not in recommendations:
                    recommendations.append(clean[:180])
                    if len(recommendations) >= 4:
                        break
        
        if not recommendations:
            recommendations = [
                "📊 Monitorar KPIs mensalmente com dashboard automatizado",
                "🔄 Revisar dados periodicamente para identificar tendências",
                "📈 Comparar resultados com metas estabelecidas",
                "💡 Utilizar insights para otimização operacional"
            ]
        
        return recommendations[:4]
    
    def _get_fallback_response(self, error_msg: str) -> Dict[str, Any]:
        """Resposta de fallback melhorada"""
        return {
            "success": False,
            "ai_available": False,
            "error": error_msg,
            "insights": [
                "⚠️ Serviço de IA temporariamente indisponível",
                "📁 Verifique a conexão com a internet",
                "🔄 Tente novamente em alguns instantes"
            ],
            "recommendations": [
                "Verificar configuração da API Gemini",
                "Validar chave de API no arquivo .env",
                "Verificar conexão com a internet",
                "Tentar novamente mais tarde"
            ],
            "timestamp": datetime.now().isoformat()
        }


# ============================================================
# CRIA A INSTÂNCIA GLOBAL
# ============================================================
try:
    gemini_service = GeminiService()
    logger.info("✅ GeminiService global inicializado com sucesso")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar GeminiService global: {e}")
    gemini_service = None

__all__ = ['GeminiService', 'gemini_service']