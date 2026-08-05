# backend/gemini.py - VERSÃO 3.0 (INTELIGENTE E AUTOADAPTÁVEL)
"""
🔥 Serviço de integração com Google Gemini - VERSÃO 3.0
================================================================================
✅ NOVIDADES V3.0:
   - 🔥 DETECÇÃO AUTOMÁTICA DE VERSÃO DO SDK
   - 🔥 VALIDAÇÃO DE COMPATIBILIDADE DA API
   - 🔥 AUTO-ADAPTAÇÃO PARA DIFERENTES VERSÕES
   - 🔥 HEALTH CHECK COMPLETO
   - 🔥 CACHE INTELIGENTE COM TTL
   - 🔥 MÉTRICAS DE PERFORMANCE DETALHADAS
   - 🔥 SISTEMA DE VERSÃO DE MODELOS
   - 🔥 TESTE AUTOMÁTICO DE DISPONIBILIDADE

✅ CORREÇÕES:
   - 🔧 Caminho do .env mais flexível
   - 🔧 Tratamento de erros mais específico
   - 🔧 Extração de insights mais robusta
   - 🔧 Cache de respostas com invalidação
================================================================================
"""

import google.generativeai as genai
import json
import asyncio
import logging
import re
import os
import time
import hashlib
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    retry_if_exception_message
)

# Carregar variáveis de ambiente
from dotenv import load_dotenv

# Configuração de logging
logger = logging.getLogger(__name__)


# ==============================================
# 🔥 ENUMS E DATACLASSES
# ==============================================

class SDKVersion(str, Enum):
    """Versões do SDK google-generativeai"""
    V0_1 = "0.1.0"
    V0_2 = "0.2.0"
    V0_3 = "0.3.0"
    V0_4 = "0.4.0"
    V0_5 = "0.5.0"
    V0_6 = "0.6.0"
    V0_7 = "0.7.0"
    V0_8 = "0.8.0"
    UNKNOWN = "unknown"


class APIVersion(str, Enum):
    """Versões da API Gemini"""
    V1 = "v1"
    V1BETA = "v1beta"
    UNKNOWN = "unknown"


class ModelStatus(str, Enum):
    """Status de um modelo"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEPRECATED = "deprecated"
    UNKNOWN = "unknown"


@dataclass
class ModelInfo:
    """Informações de um modelo Gemini"""
    name: str
    status: ModelStatus
    version: str
    max_tokens: int
    supports_system_instruction: bool
    supports_function_calling: bool
    last_tested: Optional[datetime] = None
    response_time_ms: float = 0.0


@dataclass
class CacheEntry:
    """Entrada de cache com metadados"""
    value: Any
    timestamp: datetime
    ttl_seconds: int = 300
    hits: int = 0
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.timestamp).seconds > self.ttl_seconds


# ==============================================
# 🔥 CLASSE PRINCIPAL
# ==============================================

class GeminiService:
    """
    🔥 Serviço Gemini V3.0 - Inteligente e Autoadaptável
    
    Características:
    - Detecção automática de versão do SDK
    - Validação de compatibilidade da API
    - Auto-adaptação para diferentes versões
    - Health check completo
    - Cache inteligente com TTL
    - Métricas de performance
    """
    
    # ==========================================
    # CONFIGURAÇÕES
    # ==========================================
    
    # Modelos disponíveis (ordem de preferência)
    AVAILABLE_MODELS = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-1.0-pro',
    ]
    
    # Modelo padrão
    DEFAULT_MODEL = 'gemini-2.0-flash'
    
    # Configurações de timeout e retry
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    MAX_TOKENS = 8192
    MAX_PROMPT_SIZE = 50000
    
    # Cache
    CACHE_TTL = 300  # 5 minutos
    CACHE_MAX_SIZE = 100
    
    # Health check
    HEALTH_CHECK_INTERVAL = 60  # 1 minuto
    
    # System instruction
    SYSTEM_INSTRUCTION = (
        "Você é um Especialista em Gestão de Oficinas Mecânicas e Análise de Dados Automotivos. "
        "Sua função é analisar dados de oficinas e fornecer insights práticos para gestão. "
        "Seja direto, objetivo e foque em ações que gerem resultados reais. "
        "Use linguagem clara, evitando jargões técnicos desnecessários. "
        "Sempre use marcadores '-' para cada item em suas listas."
    )
    
    # ==========================================
    # CONSTRUTOR
    # ==========================================
    
    def __init__(self, force_reload: bool = False):
        """Inicializa o serviço Gemini com auto-detecção"""
        
        # Estado base
        self.api_key = None
        self.model = None
        self.model_name = None
        self.model_info: Optional[ModelInfo] = None
        
        # Versões
        self.sdk_version = SDKVersion.UNKNOWN
        self.api_version = APIVersion.UNKNOWN
        
        # Cache
        self._available_models_cache: Optional[List[str]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._response_cache: Dict[str, CacheEntry] = {}
        
        # Estatísticas
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "model_used": None,
            "last_call": None,
            "total_tokens": 0,
            "avg_response_time_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "started_at": datetime.now().isoformat(),
            "last_health_check": None,
            "health_status": "unknown"
        }
        
        # Health check
        self._last_health_check: Optional[datetime] = None
        self._health_status: ModelStatus = ModelStatus.UNKNOWN
        
        # Inicialização
        self._detect_sdk_version()
        self.api_key = self._get_api_key(force_reload=force_reload)
        
        if self.api_key:
            self._initialize_model()
            self._run_health_check()
        else:
            logger.error("❌ Não foi possível inicializar Gemini sem API key válida")
    
    # ==========================================
    # 🔥 DETECÇÃO DE VERSÃO DO SDK
    # ==========================================
    
    def _detect_sdk_version(self) -> SDKVersion:
        """
        🔥 Detecta a versão do SDK google-generativeai
        """
        try:
            version = genai.__version__
            
            # Mapear versões conhecidas
            if version.startswith('0.8'):
                self.sdk_version = SDKVersion.V0_8
            elif version.startswith('0.7'):
                self.sdk_version = SDKVersion.V0_7
            elif version.startswith('0.6'):
                self.sdk_version = SDKVersion.V0_6
            elif version.startswith('0.5'):
                self.sdk_version = SDKVersion.V0_5
            elif version.startswith('0.4'):
                self.sdk_version = SDKVersion.V0_4
            elif version.startswith('0.3'):
                self.sdk_version = SDKVersion.V0_3
            elif version.startswith('0.2'):
                self.sdk_version = SDKVersion.V0_2
            elif version.startswith('0.1'):
                self.sdk_version = SDKVersion.V0_1
            else:
                self.sdk_version = SDKVersion.UNKNOWN
            
            logger.info(f"📦 SDK version: {version} (detected: {self.sdk_version.value})")
            return self.sdk_version
            
        except (AttributeError, ImportError) as e:
            logger.warning(f"⚠️ Não foi possível detectar versão do SDK: {e}")
            self.sdk_version = SDKVersion.UNKNOWN
            return self.sdk_version
    
    def _detect_api_version(self) -> APIVersion:
        """
        🔥 Detecta a versão da API Gemini disponível
        """
        try:
            # Testar com v1beta (mais recente)
            test_model = genai.GenerativeModel('gemini-2.0-flash')
            test_response = test_model.generate_content("Teste")
            if test_response and test_response.text:
                self.api_version = APIVersion.V1BETA
                logger.info(f"🌐 API version: v1beta")
                return self.api_version
        except Exception:
            pass
        
        try:
            # Testar com v1 (legado)
            genai.configure(api_key=self.api_key, transport='rest')
            test_model = genai.GenerativeModel('gemini-1.0-pro')
            test_response = test_model.generate_content("Teste")
            if test_response and test_response.text:
                self.api_version = APIVersion.V1
                logger.info(f"🌐 API version: v1 (legacy)")
                return self.api_version
        except Exception:
            pass
        
        self.api_version = APIVersion.UNKNOWN
        logger.warning("⚠️ Não foi possível detectar versão da API")
        return self.api_version
    
    def _supports_system_instruction(self) -> bool:
        """
        🔥 Verifica se o SDK suporta system_instruction
        """
        # Versões 0.7+ suportam system_instruction
        if self.sdk_version in [SDKVersion.V0_7, SDKVersion.V0_8]:
            return True
        
        # Tentar detectar via inspeção
        try:
            import inspect
            sig = inspect.signature(genai.GenerativeModel.__init__)
            return 'system_instruction' in sig.parameters
        except Exception:
            return False
    
    def _supports_function_calling(self) -> bool:
        """
        🔥 Verifica se o SDK suporta function calling
        """
        # Versões 0.8+ suportam function calling
        if self.sdk_version == SDKVersion.V0_8:
            return True
        
        try:
            import inspect
            sig = inspect.signature(genai.GenerativeModel.__init__)
            return 'tools' in sig.parameters
        except Exception:
            return False
    
    # ==========================================
    # 🔥 API KEY - VALIDAÇÃO ROBUSTA
    # ==========================================
    
    def _get_api_key(self, force_reload: bool = False) -> Optional[str]:
        """
        🔥 Obtém API key com múltiplas estratégias
        """
        if force_reload:
            self._reload_env()
        
        # Estratégias em ordem
        strategies = [
            self._get_key_from_settings,
            self._get_key_from_environ,
            self._get_key_from_alternatives,
            self._get_key_from_file,
        ]
        
        for strategy in strategies:
            key = strategy()
            if key and self._is_valid_key(key):
                return key
        
        logger.error("❌ NENHUMA API key válida encontrada!")
        return None
    
    def _reload_env(self):
        """Recarrega o arquivo .env"""
        env_path = self._find_env_file()
        if env_path:
            load_dotenv(dotenv_path=env_path, override=True)
            logger.info(f"🔄 .env recarregado: {env_path}")
    
    def _find_env_file(self) -> Optional[Path]:
        """Encontra o arquivo .env em múltiplos lugares"""
        possible_paths = [
            Path(__file__).parent.parent / '.env',   # backend/../.env
            Path.cwd() / '.env',                      # Diretório atual
            Path.home() / '.env',                     # Home do usuário
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        return None
    
    def _get_key_from_settings(self) -> Optional[str]:
        """Tenta obter do settings"""
        try:
            from config.settings import settings
            key = getattr(settings, "GEMINI_API_KEY", None)
            if key and self._is_valid_key(key):
                logger.info("✅ API key do settings")
                return key
        except ImportError:
            pass
        return None
    
    def _get_key_from_environ(self) -> Optional[str]:
        """Tenta obter do os.environ"""
        key = os.environ.get("GEMINI_API_KEY")
        if key and self._is_valid_key(key):
            logger.info("✅ API key do os.environ")
            return key
        return None
    
    def _get_key_from_alternatives(self) -> Optional[str]:
        """Tenta obter de variáveis alternativas"""
        for var_name in ["GEMINI_KEY", "GOOGLE_API_KEY"]:
            key = os.environ.get(var_name)
            if key and self._is_valid_key(key):
                logger.info(f"✅ API key de {var_name}")
                return key
        return None
    
    def _get_key_from_file(self) -> Optional[str]:
        """Tenta obter de arquivo .gemini_key"""
        try:
            key_file = Path(__file__).parent.parent / '.gemini_key'
            if key_file.exists():
                key = key_file.read_text().strip()
                if key and self._is_valid_key(key):
                    logger.info("✅ API key do .gemini_key")
                    return key
        except Exception:
            pass
        return None
    
    def _is_valid_key(self, api_key: str) -> bool:
        """Valida se a chave é uma API key válida do Google"""
        if not api_key:
            return False
        
        api_key = str(api_key).strip().replace('\n', '').replace('\r', '')
        
        invalid_values = [None, "", "opcional", "sua_chave_aqui", "your_api_key_here", "API_KEY_AQUI"]
        if api_key in invalid_values:
            return False
        
        if len(api_key) < 20:
            return False
        
        if not re.match(r'^[A-Za-z0-9\-_]+$', api_key):
            return False
        
        return True
    
    # ==========================================
    # 🔥 INICIALIZAÇÃO DO MODELO
    # ==========================================
    
    def _initialize_model(self) -> bool:
        """
        🔥 Inicializa o modelo com auto-detecção de versão
        """
        if not self.api_key:
            return False
        
        try:
            clean_key = self.api_key.strip().replace('\n', '').replace('\r', '')
            
            # Configurar API
            genai.configure(api_key=clean_key)
            
            # Detectar versão da API
            self._detect_api_version()
            
            # Verificar suporte a system_instruction
            supports_system = self._supports_system_instruction()
            supports_function = self._supports_function_calling()
            
            logger.info(f"📊 SDK features:")
            logger.info(f"   - system_instruction: {supports_system}")
            logger.info(f"   - function_calling: {supports_function}")
            
            # Gerar config
            generation_config = {
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": self.MAX_TOKENS,
            }
            
            # Tentar modelos
            for model_name in self.AVAILABLE_MODELS:
                if self._try_model(model_name, generation_config, supports_system):
                    return True
            
            logger.error("❌ NENHUM modelo disponível!")
            return False
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Gemini: {str(e)}")
            return False
    
    def _try_model(self, model_name: str, generation_config: Dict, supports_system: bool) -> bool:
        """
        🔥 Tenta inicializar um modelo específico
        """
        try:
            logger.info(f"🔄 Tentando modelo: {model_name}")
            
            if supports_system:
                self.model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=self.SYSTEM_INSTRUCTION,
                    generation_config=generation_config
                )
            else:
                self.model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config
                )
                # Fallback: guardar system_instruction para usar no prompt
                self._system_instruction_fallback = self.SYSTEM_INSTRUCTION
            
            # Testar modelo
            test_response = self.model.generate_content("Teste de conexão. Responda apenas 'OK'.")
            
            if test_response and test_response.text and "OK" in test_response.text:
                self.model_name = model_name
                
                # Registrar informações do modelo
                self.model_info = ModelInfo(
                    name=model_name,
                    status=ModelStatus.AVAILABLE,
                    version=self.sdk_version.value,
                    max_tokens=self.MAX_TOKENS,
                    supports_system_instruction=supports_system,
                    supports_function_calling=self._supports_function_calling(),
                    last_tested=datetime.now(),
                    response_time_ms=0.0
                )
                
                logger.info(f"✅ Gemini inicializado: {model_name}")
                logger.info(f"   SDK: {self.sdk_version.value}")
                logger.info(f"   API: {self.api_version.value}")
                return True
            
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                logger.warning(f"⚠️ Modelo {model_name} não disponível")
            elif "429" in error_msg:
                logger.warning(f"⚠️ Rate limit para {model_name}")
            else:
                logger.warning(f"⚠️ Falha em {model_name}: {error_msg[:100]}")
        
        self.model = None
        return False
    
    # ==========================================
    # 🔥 HEALTH CHECK
    # ==========================================
    
    def _run_health_check(self) -> Dict[str, Any]:
        """
        🔥 Executa health check completo
        """
        self._last_health_check = datetime.now()
        
        result = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "model": self.model_name,
            "api_key_valid": bool(self.api_key),
            "sdk_version": self.sdk_version.value,
            "api_version": self.api_version.value,
            "supports_system_instruction": self._supports_system_instruction(),
            "supports_function_calling": self._supports_function_calling(),
        }
        
        # Testar modelo se estiver disponível
        if self.model:
            try:
                start_time = time.time()
                test_response = self.model.generate_content("Health check. Responda 'OK'.")
                elapsed = (time.time() - start_time) * 1000
                
                if test_response and test_response.text:
                    result["model_status"] = "responding"
                    result["response_time_ms"] = round(elapsed, 2)
                    result["response"] = test_response.text.strip()
                    self._health_status = ModelStatus.AVAILABLE
                else:
                    result["model_status"] = "no_response"
                    self._health_status = ModelStatus.UNAVAILABLE
                    
            except Exception as e:
                result["model_status"] = "error"
                result["error"] = str(e)
                self._health_status = ModelStatus.UNAVAILABLE
        else:
            result["model_status"] = "not_initialized"
            self._health_status = ModelStatus.UNAVAILABLE
        
        self._stats["health_status"] = result["model_status"]
        self._stats["last_health_check"] = datetime.now().isoformat()
        
        logger.info(f"💚 Health check: {result['model_status']}")
        return result
    
    async def health_check(self, force: bool = False) -> Dict[str, Any]:
        """
        🔥 Health check público com cache
        """
        if not force and self._last_health_check:
            elapsed = (datetime.now() - self._last_health_check).seconds
            if elapsed < self.HEALTH_CHECK_INTERVAL:
                return {
                    "status": "cached",
                    "cached_at": self._last_health_check.isoformat(),
                    "result": self._health_status.value
                }
        
        return self._run_health_check()
    
    def is_available(self) -> bool:
        """Verifica se o serviço está disponível"""
        return self.model is not None and bool(self.api_key)
    
    def is_healthy(self) -> bool:
        """Verifica se o serviço está saudável"""
        return self.is_available() and self._health_status == ModelStatus.AVAILABLE
    
    # ==========================================
    # 🔥 CACHE INTELIGENTE
    # ==========================================
    
    def _get_cache_key(self, prompt: str) -> str:
        """Gera chave de cache para um prompt"""
        return hashlib.md5(prompt.encode()).hexdigest()
    
    def _get_cached_response(self, prompt: str) -> Optional[str]:
        """Obtém resposta do cache"""
        key = self._get_cache_key(prompt)
        if key in self._response_cache:
            entry = self._response_cache[key]
            if not entry.is_expired():
                entry.hits += 1
                self._stats["cache_hits"] += 1
                logger.debug(f"✅ Cache hit: {key[:8]}")
                return entry.value
            else:
                del self._response_cache[key]
        self._stats["cache_misses"] += 1
        return None
    
    def _set_cached_response(self, prompt: str, response: str, ttl: Optional[int] = None):
        """Salva resposta no cache"""
        if len(self._response_cache) >= self.CACHE_MAX_SIZE:
            # Remover entrada mais antiga
            oldest_key = min(self._response_cache.keys(), 
                           key=lambda k: self._response_cache[k].timestamp)
            del self._response_cache[oldest_key]
        
        key = self._get_cache_key(prompt)
        self._response_cache[key] = CacheEntry(
            value=response,
            timestamp=datetime.now(),
            ttl_seconds=ttl or self.CACHE_TTL
        )
        logger.debug(f"💾 Cache saved: {key[:8]}")
    
    def clear_cache(self):
        """Limpa o cache de respostas"""
        self._response_cache.clear()
        logger.info("🧹 Cache limpo")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        return {
            "size": len(self._response_cache),
            "max_size": self.CACHE_MAX_SIZE,
            "ttl_seconds": self.CACHE_TTL,
            "hits": self._stats["cache_hits"],
            "misses": self._stats["cache_misses"],
            "hit_rate": self._stats["cache_hits"] / max(1, self._stats["cache_hits"] + self._stats["cache_misses"]) * 100
        }
    
    # ==========================================
    # 🔥 CHAMADA GEMINI COM RETRY E CACHE
    # ==========================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception))
    )
    async def _call_gemini(self, prompt: str, use_cache: bool = True) -> Optional[str]:
        """
        🔥 Chama Gemini com retry, cache e métricas
        """
        if not self.model:
            logger.error("❌ Modelo Gemini não disponível")
            return None
        
        # Verificar cache
        if use_cache:
            cached = self._get_cached_response(prompt)
            if cached is not None:
                return cached
        
        start_time = time.time()
        
        try:
            loop = asyncio.get_event_loop()
            
            logger.debug(f"📤 Enviando prompt ({len(prompt)} caracteres)")
            
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.model.generate_content(prompt)),
                timeout=self.TIMEOUT_SECONDS
            )
            
            elapsed = (time.time() - start_time) * 1000
            
            self._stats["total_calls"] += 1
            self._stats["avg_response_time_ms"] = (
                (self._stats["avg_response_time_ms"] * (self._stats["total_calls"] - 1) + elapsed) /
                self._stats["total_calls"]
            )
            
            if response and response.text:
                self._stats["successful_calls"] += 1
                self._stats["model_used"] = self.model_name
                self._stats["last_call"] = datetime.now().isoformat()
                
                # Extrair tokens
                try:
                    if hasattr(response, 'usage_metadata'):
                        self._stats["total_tokens"] += response.usage_metadata.total_token_count or 0
                except:
                    pass
                
                logger.debug(f"✅ Resposta recebida ({len(response.text)} caracteres) em {elapsed:.0f}ms")
                
                # Salvar no cache
                if use_cache:
                    self._set_cached_response(prompt, response.text)
                
                return response.text
            else:
                self._stats["failed_calls"] += 1
                logger.warning("⚠️ Resposta vazia")
                return None
                
        except asyncio.TimeoutError:
            self._stats["failed_calls"] += 1
            logger.error(f"⏰ Timeout após {self.TIMEOUT_SECONDS}s")
            raise
        
        except Exception as e:
            self._stats["failed_calls"] += 1
            logger.error(f"❌ Erro: {str(e)}")
            
            # Tentar recarregar modelo se for erro 404
            if "404" in str(e) or "not found" in str(e).lower():
                logger.warning("🔄 Tentando recarregar modelo...")
                self._initialize_model()
            
            raise
    
    # ==========================================
    # 🔥 ANÁLISE PRINCIPAL
    # ==========================================
    
    async def analyze_office_data(self, data_type: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔥 Analisa dados de oficina com Gemini
        """
        if not self.model:
            return self._get_fallback_response("Gemini não configurado")
        
        if not analysis_data:
            return self._get_fallback_response("Nenhum dado fornecido")
        
        try:
            prompt = self._build_office_prompt(data_type, analysis_data)
            
            logger.info(f"🏪 Analisando dados - Tipo: {data_type} | Modelo: {self.model_name}")
            logger.info(f"📏 Prompt: {len(prompt)} caracteres")
            
            response_text = await self._call_gemini(prompt)
            
            if response_text:
                return {
                    "success": True,
                    "ai_available": True,
                    "data_type": data_type,
                    "model_used": self.model_name or "unknown",
                    "model_info": {
                        "sdk_version": self.sdk_version.value,
                        "api_version": self.api_version.value,
                    },
                    "insights": self._extract_insights(response_text),
                    "recommendations": self._extract_recommendations(response_text),
                    "full_analysis": response_text,
                    "timestamp": datetime.now().isoformat(),
                    "cache_used": False,
                }
            else:
                return self._get_fallback_response("Falha na geração da análise")
                
        except Exception as e:
            logger.error(f"❌ Erro na análise: {str(e)}")
            return self._get_fallback_response(f"Erro: {str(e)}")
    
    # ==========================================
    # 🔥 CONSTRUÇÃO DE PROMPT (OTIMIZADA)
    # ==========================================
    
    def _build_office_prompt(self, data_type: str, data: Dict[str, Any]) -> str:
        """Constrói prompt com formato de resposta explícito"""
        
        icons = {
            "clientes": "👥", "servicos": "🔧", "estoque": "📦",
            "financeiro": "💰", "metricas": "📊", "default": "📈"
        }
        icon = icons.get(data_type, icons["default"])
        
        # Converter dados para JSON
        data_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        
        # Truncar se necessário
        if len(data_str) > self.MAX_PROMPT_SIZE:
            data_str = data_str[:self.MAX_PROMPT_SIZE] + "\n... (dados truncados)"
        
        # System instruction fallback
        system_prefix = ""
        if hasattr(self, '_system_instruction_fallback'):
            system_prefix = f"{self._system_instruction_fallback}\n\n"
        
        prompt = f"""{system_prefix}{icon} ANALISE DE {data_type.upper()}

**Formato obrigatório da resposta:**

## Principais Padrões Identificados
- [insight 1 descritivo]
- [insight 2 descritivo]
- [insight 3 descritivo]

## Oportunidades de Melhoria
- [oportunidade 1]
- [oportunidade 2]

## Recomendações Práticas
- [recomendação 1]
- [recomendação 2]
- [recomendação 3]

**Dados para análise:**
{data_str}

Responda APENAS no formato acima, usando marcadores '-' para cada item.
Seja específico e objetivo baseado nos dados fornecidos."""

        return prompt
    
    # ==========================================
    # 🔥 EXTRAÇÃO DE INSIGHTS (MELHORADA)
    # ==========================================
    
    def _extract_insights(self, text: str) -> List[str]:
        """Extrai insights de forma robusta"""
        insights = []
        
        # Tentar extrair por seção
        sections = re.split(r'##\s+', text)
        for section in sections:
            if any(kw in section.lower() for kw in ['insight', 'padrão', 'observação']):
                lines = section.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('-') or line.startswith('•'):
                        clean = line[1:].strip()
                        if 10 < len(clean) < 300:
                            insights.append(clean)
        
        # Fallback: buscar linhas com marcadores
        if not insights:
            matches = re.findall(r'[-•*]\s*([^\n]{10,300})', text)
            insights = [m.strip() for m in matches]
        
        # Fallback final
        if not insights:
            sentences = re.split(r'[.!?]+', text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 20 and any(kw in sentence.lower() 
                    for kw in ['padrão', 'oportunidade', 'melhoria', 'tendência']):
                    insights.append(sentence)
        
        return insights[:5]
    
    def _extract_recommendations(self, text: str) -> List[str]:
        """Extrai recomendações de forma robusta"""
        recommendations = []
        
        # Tentar extrair por seção
        sections = re.split(r'##\s+', text)
        for section in sections:
            if any(kw in section.lower() for kw in ['recomend', 'ação', 'prática']):
                lines = section.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('-') or line.startswith('•'):
                        clean = line[1:].strip()
                        if 10 < len(clean) < 250:
                            recommendations.append(clean)
        
        # Fallback: buscar linhas com palavras-chave
        if not recommendations:
            action_words = ['recomend', 'sugest', 'implement', 'melhor', 'otimize']
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if any(kw in line.lower() for kw in action_words):
                    clean = re.sub(r'^[-•*\d][\.\)]?\s*', '', line)
                    if 10 < len(clean) < 250:
                        recommendations.append(clean)
        
        return recommendations[:4]
    
    # ==========================================
    # 🔥 FALLBACK E DIAGNÓSTICO
    # ==========================================
    
    def _get_fallback_response(self, error_msg: str) -> Dict[str, Any]:
        """Resposta de fallback"""
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
                "Verificar conexão com a internet"
            ],
            "timestamp": datetime.now().isoformat()
        }
    
    def get_available_models(self, force_refresh: bool = False) -> List[str]:
        """Lista modelos disponíveis"""
        if not force_refresh and self._available_models_cache is not None:
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).seconds < 3600:
                return self._available_models_cache
        
        available = []
        for model_name in self.AVAILABLE_MODELS:
            try:
                temp_model = genai.GenerativeModel(model_name)
                response = temp_model.generate_content("Teste")
                if response and response.text:
                    available.append(model_name)
            except Exception:
                continue
        
        self._available_models_cache = available
        self._cache_timestamp = datetime.now()
        return available
    
    def get_model_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas completas"""
        return {
            "total_calls": self._stats["total_calls"],
            "successful_calls": self._stats["successful_calls"],
            "failed_calls": self._stats["failed_calls"],
            "success_rate": round(
                self._stats["successful_calls"] / max(1, self._stats["total_calls"]) * 100, 1
            ),
            "model_used": self._stats["model_used"] or self.model_name or "none",
            "last_call": self._stats["last_call"],
            "total_tokens": self._stats["total_tokens"],
            "avg_response_time_ms": round(self._stats["avg_response_time_ms"], 2),
            "model_initialized": self.model is not None,
            "api_key_valid": bool(self.api_key),
            "sdk_version": self.sdk_version.value,
            "api_version": self.api_version.value,
            "health_status": self._health_status.value,
            "cache": self.get_cache_stats(),
            "started_at": self._stats["started_at"],
            "uptime_seconds": (
                datetime.now() - datetime.fromisoformat(self._stats["started_at"])
            ).total_seconds()
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Diagnóstico completo"""
        available_models = self.get_available_models(force_refresh=True)
        
        return {
            "status": "healthy" if self.is_healthy() else "unhealthy",
            "api_key_valid": bool(self.api_key),
            "model_initialized": self.model is not None,
            "model_name": self.model_name or "none",
            "model_info": {
                "name": self.model_info.name if self.model_info else None,
                "status": self.model_info.status.value if self.model_info else None,
                "supports_system_instruction": self.model_info.supports_system_instruction if self.model_info else False,
                "supports_function_calling": self.model_info.supports_function_calling if self.model_info else False,
            } if self.model_info else None,
            "sdk_version": self.sdk_version.value,
            "api_version": self.api_version.value,
            "available_models": available_models,
            "stats": self.get_model_stats(),
            "cache": self.get_cache_stats(),
            "config": {
                "timeout": self.TIMEOUT_SECONDS,
                "max_tokens": self.MAX_TOKENS,
                "max_retries": self.MAX_RETRIES,
                "default_model": self.DEFAULT_MODEL,
                "cache_ttl": self.CACHE_TTL,
                "cache_max_size": self.CACHE_MAX_SIZE,
            },
            "timestamp": datetime.now().isoformat()
        }


# ============================================================
# 🔥 INSTÂNCIA GLOBAL
# ============================================================

try:
    gemini_service = GeminiService()
    logger.info("✅ GeminiService V3.0 global inicializado")
    
    # Mostrar status no console
    print("\n" + "=" * 70)
    print("🔥 Gemini Service v3.0 - INTELIGENTE E AUTOADAPTÁVEL")
    print("=" * 70)
    if gemini_service.is_available():
        print(f"   ✅ Status: ONLINE")
        print(f"   📊 Modelo: {gemini_service.model_name}")
        print(f"   📦 SDK: {gemini_service.sdk_version.value}")
        print(f"   🌐 API: {gemini_service.api_version.value}")
        print(f"   💚 Health: {gemini_service._health_status.value}")
        print(f"   📈 Cache: {len(gemini_service._response_cache)} entradas")
    else:
        print("   ❌ Status: OFFLINE")
        print("   ⚠️ Verifique sua API key e conexão")
    print("=" * 70)

except Exception as e:
    logger.error(f"❌ Erro ao inicializar GeminiService: {e}")
    gemini_service = None


__all__ = ['GeminiService', 'gemini_service']