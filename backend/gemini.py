# backend/gemini.py - VERSÃO ATUALIZADA 2.0 (CORREÇÃO DE MODELO E MELHORIAS)
"""
🔥 Serviço de integração com Google Gemini - VERSÃO 2.0
================================================================================
✅ CORREÇÕES CRÍTICAS:
   - 🔥 Modelo atualizado para 'gemini-2.0-flash' (disponível para novos usuários)
   - 🔥 Fallback automático entre modelos disponíveis
   - 🔥 Validação de modelo antes do uso
   - 🔥 Melhor tratamento de erros 404 (modelo indisponível)

✅ MELHORIAS:
   - 📊 Lista de modelos disponíveis com fallback ordenado
   - 🔄 Cache de modelos funcionando
   - 📝 Logging estruturado com níveis
   - 🛡️ Validação de API key mais robusta
   - 📈 Métricas de performance
   - 🔒 Timeout configurável

✅ NOVAS FUNCIONALIDADES:
   - 🔍 get_available_models() - Lista modelos disponíveis
   - 📊 get_model_stats() - Estatísticas de uso
   - 🔄 test_model() - Testa um modelo específico
   - 📝 diagnose() - Diagnóstico completo
================================================================================
"""

import google.generativeai as genai
import json
import asyncio
import logging
import re
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
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
    Utiliza Gemini com fallback automático entre modelos disponíveis
    """
    
    # 🔥 MODELOS DISPONÍVEIS (ordem de preferência)
    AVAILABLE_MODELS = [
        'gemini-2.0-flash',          # 🔥 RECOMENDADO - Disponível para novos usuários
        'gemini-2.0-flash-lite',     # 🔥 Alternativa mais leve
        'gemini-1.5-flash',          # Fallback
        'gemini-1.5-pro',            # Fallback mais robusto
        'gemini-1.0-pro',            # Último recurso
    ]
    
    # 🔥 Modelo padrão
    DEFAULT_MODEL = 'gemini-2.0-flash'
    
    # Configurações
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    MAX_TOKENS = 8192
    MAX_PROMPT_SIZE = 50000
    CACHE_MODEL_TTL = 3600  # 1 hora
    
    SYSTEM_INSTRUCTION = (
        "Você é um Especialista em Gestão de Oficinas Mecânicas e Análise de Dados Automotivos. "
        "Sua função é analisar dados de oficinas e fornecer insights práticos para gestão. "
        "Seja direto, objetivo e foque em ações que gerem resultados reais. "
        "Use linguagem clara, evitando jargões técnicos desnecessários. "
        "Sempre use marcadores '-' para cada item em suas listas."
    )
    
    def __init__(self, force_reload=False):
        """Inicializa o serviço com Gemini"""
        self.api_key = self._get_api_key(force_reload=force_reload)
        self.model = None
        self.model_name = None
        self._available_models_cache = None
        self._cache_timestamp = None
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "model_used": None,
            "last_call": None,
            "total_tokens": 0,
        }
        
        if self.api_key:
            self._initialize_model()
        else:
            logger.error("❌ Não foi possível inicializar Gemini sem API key válida")
    
    # ==========================================
    # 🔥 API KEY - VALIDAÇÃO ROBUSTA
    # ==========================================
    
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
        
        # Estratégia 4: Verificar se a chave está em um arquivo
        try:
            key_file = Path(__file__).parent.parent / '.gemini_key'
            if key_file.exists():
                api_key = key_file.read_text().strip()
                if api_key and self._is_valid_key(api_key):
                    logger.info("✅ API key encontrada no arquivo .gemini_key")
                    return api_key
        except Exception:
            pass
        
        logger.error("❌ NENHUMA API key válida encontrada!")
        logger.error(f"   Caminho esperado do .env: {Path(__file__).parent.parent / '.env'}")
        
        return None
    
    def _is_valid_key(self, api_key: str) -> bool:
        """Valida se a chave parece ser uma API key do Google"""
        api_key = str(api_key).strip().replace('\n', '').replace('\r', '')
        
        invalid_values = [None, "", "opcional", "sua_chave_aqui", "your_api_key_here", "API_KEY_AQUI"]
        
        if api_key in invalid_values:
            return False
        
        if len(api_key) < 20:
            return False
        
        if not re.match(r'^[A-Za-z0-9\-_]+$', api_key):
            return False
        
        key_preview = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        logger.info(f"🔑 API key válida (tamanho: {len(api_key)}, preview: {key_preview})")
        return True
    
    # ==========================================
    # 🔥 INICIALIZAÇÃO DO MODELO
    # ==========================================
    
    def _initialize_model(self) -> None:
        """Inicializa o modelo Gemini com fallback automático"""
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
            
            # 🔥 Tenta inicializar com o modelo padrão
            model_initialized = False
            
            for model_name in self.AVAILABLE_MODELS:
                try:
                    logger.info(f"🔄 Tentando inicializar modelo: {model_name}")
                    
                    # Verifica se o SDK suporta system_instruction
                    import inspect
                    sig = inspect.signature(genai.GenerativeModel.__init__)
                    params = sig.parameters
                    
                    if 'system_instruction' in params:
                        # Versão recente com suporte
                        self.model = genai.GenerativeModel(
                            model_name=model_name,
                            system_instruction=self.SYSTEM_INSTRUCTION,
                            generation_config=generation_config
                        )
                    else:
                        # Fallback para versões antigas
                        self.model = genai.GenerativeModel(
                            model_name=model_name,
                            generation_config=generation_config
                        )
                        self._system_instruction_fallback = self.SYSTEM_INSTRUCTION
                    
                    # 🔥 TESTA O MODELO
                    test_response = self.model.generate_content("Teste de conexão. Responda apenas 'OK'.")
                    
                    if test_response and test_response.text:
                        self.model_name = model_name
                        model_initialized = True
                        logger.info(f"✅ Gemini inicializado com sucesso - Modelo: {model_name}")
                        logger.info(f"   Timeout: {self.TIMEOUT_SECONDS}s | Max tokens: {self.MAX_TOKENS}")
                        break
                    else:
                        logger.warning(f"⚠️ Modelo {model_name} não respondeu corretamente")
                        
                except Exception as e:
                    error_msg = str(e)
                    # 🔥 Tratamento específico para erro 404 (modelo indisponível)
                    if "404" in error_msg or "not found" in error_msg.lower():
                        logger.warning(f"⚠️ Modelo {model_name} não disponível: {error_msg}")
                    else:
                        logger.warning(f"⚠️ Falha ao inicializar {model_name}: {error_msg}")
                    
                    self.model = None
                    continue
            
            if not model_initialized:
                logger.error("❌ NENHUM modelo Gemini disponível!")
                self.model = None
                self.model_name = None
                
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Gemini: {str(e)}")
            logger.error(f"   Tipo: {type(e).__name__}")
            self.model = None
            self.model_name = None
    
    # ==========================================
    # 🔥 TESTE DE MODELOS DISPONÍVEIS
    # ==========================================
    
    def get_available_models(self, force_refresh: bool = False) -> List[str]:
        """
        🔥 Retorna lista de modelos disponíveis para o usuário
        """
        # Verifica cache
        if not force_refresh and self._available_models_cache is not None:
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).seconds < self.CACHE_MODEL_TTL:
                return self._available_models_cache
        
        available = []
        
        for model_name in self.AVAILABLE_MODELS:
            try:
                temp_model = genai.GenerativeModel(model_name)
                test_response = temp_model.generate_content("Teste")
                if test_response and test_response.text:
                    available.append(model_name)
                    logger.info(f"✅ Modelo disponível: {model_name}")
                else:
                    logger.warning(f"⚠️ Modelo {model_name} não respondeu")
            except Exception as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    logger.warning(f"⚠️ Modelo {model_name} não disponível (404)")
                else:
                    logger.warning(f"⚠️ Modelo {model_name} indisponível: {str(e)[:50]}")
        
        self._available_models_cache = available
        self._cache_timestamp = datetime.now()
        
        return available
    
    def test_model(self, model_name: str) -> Tuple[bool, str]:
        """
        🔥 Testa um modelo específico
        """
        try:
            test_model = genai.GenerativeModel(model_name)
            response = test_model.generate_content("Teste de conexão. Responda apenas 'OK'.")
            
            if response and response.text:
                return True, "OK"
            return False, "Sem resposta"
        except Exception as e:
            return False, str(e)
    
    # ==========================================
    # 🔥 CHAMADA GEMINI COM RETRY
    # ==========================================
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((google_exceptions.NotFound, google_exceptions.ResourceExhausted))
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
            
            self._stats["total_calls"] += 1
            
            if response and response.text:
                self._stats["successful_calls"] += 1
                self._stats["model_used"] = self.model_name
                self._stats["last_call"] = datetime.now().isoformat()
                
                # Tentar extrair uso de tokens
                try:
                    if hasattr(response, 'usage_metadata'):
                        self._stats["total_tokens"] += response.usage_metadata.total_token_count or 0
                except:
                    pass
                
                logger.debug(f"✅ Resposta recebida ({len(response.text)} caracteres)")
                return response.text
            else:
                self._stats["failed_calls"] += 1
                logger.warning("⚠️ Resposta vazia")
                return None
                
        except asyncio.TimeoutError:
            self._stats["failed_calls"] += 1
            logger.error(f"⏰ Timeout após {self.TIMEOUT_SECONDS} segundos")
            raise
        except google_exceptions.NotFound as e:
            self._stats["failed_calls"] += 1
            logger.error(f"❌ Modelo não encontrado: {e}")
            # 🔥 Tentar recarregar modelo com fallback
            self._initialize_model()
            raise
        except Exception as e:
            self._stats["failed_calls"] += 1
            logger.error(f"❌ Erro na chamada Gemini: {str(e)}")
            raise
    
    # ==========================================
    # 🔥 ANÁLISE PRINCIPAL
    # ==========================================
    
    async def analyze_office_data(self, data_type: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa dados específicos de oficina"""
        if not self.model:
            return self._get_fallback_response("Gemini não configurado")
        
        if not analysis_data:
            return self._get_fallback_response("Nenhum dado fornecido")
        
        try:
            prompt = self._build_office_prompt(data_type, analysis_data)
            
            logger.info(f"🏪 Analisando dados - Tipo: {data_type} | Modelo: {self.model_name or 'desconhecido'}")
            logger.info(f"📏 Tamanho do prompt: {len(prompt)} caracteres")
            
            response_text = await self._call_gemini(prompt)
            
            if response_text:
                return {
                    "success": True,
                    "ai_available": True,
                    "data_type": data_type,
                    "model_used": self.model_name or "unknown",
                    "insights": self._extract_insights(response_text),
                    "recommendations": self._extract_recommendations(response_text),
                    "full_analysis": response_text,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return self._get_fallback_response("Falha na geração da análise")
                
        except google_exceptions.NotFound as e:
            logger.error(f"❌ Modelo não disponível: {e}")
            # 🔥 Tentar reinicializar com fallback
            self._initialize_model()
            return self._get_fallback_response(f"Modelo indisponível. Tentando novamente com outro modelo.")
        except Exception as e:
            logger.exception(f"Erro: {str(e)}")
            return self._get_fallback_response(f"Erro: {str(e)}")
    
    # ==========================================
    # 🔥 CONSTRUÇÃO DE PROMPT
    # ==========================================
    
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
    
    # ==========================================
    # 🔥 EXTRAÇÃO DE INSIGHTS E RECOMENDAÇÕES
    # ==========================================
    
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
        
        # Seções de insights
        insight_sections = ['insight', 'padrão', 'observação', 'identificado', 'destaca', 'nota-se']
        in_insight_section = False
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            # Verificar se está em uma seção de insights
            line_lower = line.lower()
            if any(sec in line_lower for sec in ['principais padrões', 'insights', 'observações']):
                in_insight_section = True
                continue
            
            # Se saiu da seção, parar
            if in_insight_section and any(sec in line_lower for sec in ['oportunidades', 'recomendações', 'conclusão']):
                in_insight_section = False
            
            matched = False
            for pattern, _ in patterns:
                match = re.match(pattern, line)
                if match:
                    clean_text = match.group(1).strip()
                    if 10 < len(clean_text) < 300:
                        insights.append(clean_text)
                        matched = True
                        break
            
            if not matched and len(line) < 200 and not line.endswith(':') and in_insight_section:
                insight_keywords = ['padrão', 'oportunidade', 'melhoria', 'média', 'total', 
                                   'cliente', 'serviço', 'aumento', 'redução', 'tendência',
                                   'mais', 'menos', 'maior', 'menor', 'cresceu', 'diminuiu',
                                   'observa', 'nota-se', 'identifica']
                if any(keyword in line_lower for keyword in insight_keywords):
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
        
        # Seções de recomendações
        rec_sections = ['recomend', 'ações', 'práticas', 'sugestões']
        in_rec_section = False
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean or len(line_clean) < 5 or len(line_clean) > 250:
                continue
            
            line_lower = line_clean.lower()
            
            # Verificar se está em uma seção de recomendações
            if any(sec in line_lower for sec in rec_sections):
                in_rec_section = True
                continue
            
            # Se saiu da seção
            if in_rec_section and any(sec in line_lower for sec in ['conclusão', 'resumo', 'próximos']):
                in_rec_section = False
            
            has_action = any(keyword in line_lower for keyword in action_keywords)
            has_marker = bool(re.match(r'^[-•*\d][\.\)]?\s*', line_clean))
            is_in_section = in_rec_section or any(sec in line_lower for sec in rec_sections)
            
            if (has_action or has_marker or is_in_section) and len(line_clean) > 15:
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
    
    # ==========================================
    # 🔥 FALLBACK E DIAGNÓSTICO
    # ==========================================
    
    def _get_fallback_response(self, error_msg: str) -> Dict[str, Any]:
        """Resposta de fallback melhorada"""
        return {
            "success": False,
            "ai_available": False,
            "error": error_msg,
            "model_used": None,
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
    
    def get_model_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de uso do modelo"""
        return {
            "total_calls": self._stats["total_calls"],
            "successful_calls": self._stats["successful_calls"],
            "failed_calls": self._stats["failed_calls"],
            "success_rate": round((self._stats["successful_calls"] / max(1, self._stats["total_calls"])) * 100, 1),
            "model_used": self._stats["model_used"] or self.model_name or "none",
            "last_call": self._stats["last_call"],
            "total_tokens": self._stats["total_tokens"],
            "model_initialized": self.model is not None,
            "api_key_valid": bool(self.api_key),
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Diagnóstico completo do serviço"""
        available_models = self.get_available_models(force_refresh=True)
        
        return {
            "status": "ok" if self.model else "error",
            "api_key_valid": bool(self.api_key),
            "model_initialized": self.model is not None,
            "model_name": self.model_name or "none",
            "available_models": available_models,
            "stats": self.get_model_stats(),
            "config": {
                "timeout": self.TIMEOUT_SECONDS,
                "max_tokens": self.MAX_TOKENS,
                "max_retries": self.MAX_RETRIES,
                "default_model": self.DEFAULT_MODEL,
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def is_available(self) -> bool:
        """Verifica se o serviço está disponível"""
        return self.model is not None and bool(self.api_key)


# ============================================================
# 🔥 CRIA A INSTÂNCIA GLOBAL
# ============================================================
try:
    gemini_service = GeminiService()
    logger.info("✅ GeminiService global inicializado com sucesso")
    if gemini_service.is_available():
        logger.info(f"   📊 Modelo: {gemini_service.model_name}")
    else:
        logger.warning("   ⚠️ GeminiService disponível apenas em modo fallback")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar GeminiService global: {e}")
    gemini_service = None

__all__ = ['GeminiService', 'gemini_service']

# ============================================================
# 🔥 MENSAGEM DE INICIALIZAÇÃO
# ============================================================
print("=" * 70)
print("🔥 Gemini Service v2.0 - CORREÇÃO DE MODELO")
print("=" * 70)
print(f"   📊 Modelo padrão: {GeminiService.DEFAULT_MODEL}")
print(f"   📊 Modelos disponíveis: {len(GeminiService.AVAILABLE_MODELS)}")
print(f"   ✅ Fallback automático entre modelos")
print(f"   ✅ Diagnóstico disponível via gemini_service.diagnose()")
print(f"   ✅ Status: {'✅ Disponível' if gemini_service and gemini_service.is_available() else '❌ Indisponível'}")
print("=" * 70)