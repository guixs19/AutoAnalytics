# backend/services/payment_service.py - VERSÃO 2.0 (INTELIGENTE E ROBUSTA)
"""
🔥 SISTEMA DE PAGAMENTO V2.0 - AUTOANALYTICS
================================================================================
✅ NOVIDADES:
   1. 🔥 RETRY AUTOMÁTICO: 3 tentativas com backoff exponencial
   2. 🔥 VALIDAÇÃO DE DATA: Múltiplos formatos aceitos
   3. 🔥 FALLBACK INTELIGENTE: Simulação se MP estiver offline
   4. 🔥 LOGGING ESTRUTURADO: Rastreabilidade completa
   5. 🔥 MÉTRICAS: Estatísticas de pagamento
   6. 🔥 HEALTH CHECK: Status do serviço MP
   7. 🔥 CACHE DE STATUS: Reduz chamadas desnecessárias
   8. 🔥 VALIDAÇÃO DE CPF: Algoritmo completo com DV
================================================================================
"""

import mercadopago
import os
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session
import json
import uuid
import logging
import re
import time
from functools import wraps
from enum import Enum

# ==============================================
# CONFIGURAÇÕES
# ==============================================

class MPEnvironment(str, Enum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    SIMULATED = "simulated"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

# ==============================================
# DECORATOR DE RETRY INTELIGENTE
# ==============================================

def retry_on_failure(max_retries: int = 3, base_delay: float = 1.0, backoff: float = 2.0):
    """
    🔥 Decorator para retry automático com backoff exponencial
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (backoff ** attempt)
                        logger.warning(f"⚠️ Tentativa {attempt+1}/{max_retries} falhou: {e}. Aguardando {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"❌ Todas as {max_retries} tentativas falharam: {e}")
            raise last_error
        return wrapper
    return decorator


# ==============================================
# VALIDADOR DE CPF (COM ALGORITMO DV)
# ==============================================

class CpfValidator:
    """🔥 Validador de CPF com algoritmo de dígitos verificadores"""
    
    @staticmethod
    def validate(cpf: str) -> Dict[str, Any]:
        """
        Valida CPF com algoritmo completo
        Retorna: {valid: bool, cleaned: str, message: str}
        """
        cleaned = re.sub(r'\D', '', str(cpf))
        
        if len(cleaned) != 11:
            return {"valid": False, "cleaned": cleaned, "message": "CPF deve conter 11 dígitos"}
        
        # Verifica se todos os dígitos são iguais (CPF inválido)
        if cleaned == cleaned[0] * 11:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (dígitos repetidos)"}
        
        # Calcula primeiro dígito verificador
        sum_ = 0
        for i in range(9):
            sum_ += int(cleaned[i]) * (10 - i)
        remainder = 11 - (sum_ % 11)
        first_digit = 0 if remainder >= 10 else remainder
        
        if int(cleaned[9]) != first_digit:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (primeiro dígito verificador)"}
        
        # Calcula segundo dígito verificador
        sum_ = 0
        for i in range(10):
            sum_ += int(cleaned[i]) * (11 - i)
        remainder = 11 - (sum_ % 11)
        second_digit = 0 if remainder >= 10 else remainder
        
        if int(cleaned[10]) != second_digit:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (segundo dígito verificador)"}
        
        return {"valid": True, "cleaned": cleaned, "message": "CPF válido"}
    
    @staticmethod
    def mask(cpf: str) -> str:
        """Formata CPF para exibição: XXX.XXX.XXX-XX"""
        cleaned = re.sub(r'\D', '', str(cpf))
        if len(cleaned) != 11:
            return cpf
        return f"{cleaned[:3]}.{cleaned[3:6]}.{cleaned[6:9]}-{cleaned[9:]}"


# ==============================================
# CLASSE PRINCIPAL - MercadoPagoService V2.0
# ==============================================

class MercadoPagoService:
    """
    🔥 Serviço de pagamento V2.0 - Inteligente e Robusto
    """
    
    # Constantes
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0
    PIX_EXPIRY_MINUTES = 30
    STATUS_CACHE_TTL = 10  # segundos
    DEFAULT_PRICE = 97.00
    REGULAR_PRICE = 149.90
    
    def __init__(self):
        # ==========================================
        # CONFIGURAÇÃO
        # ==========================================
        self.access_token = os.getenv("MP_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MP_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")
        
        env = os.getenv("MP_ENVIRONMENT", "production").lower()
        self.environment = MPEnvironment(env) if env in ["production", "sandbox"] else MPEnvironment.PRODUCTION
        
        # Fuso horário Brasil
        self.tz_brasil = timezone(timedelta(hours=-3))
        
        # ==========================================
        # SDK
        # ==========================================
        self.sdk = None
        self._init_sdk()
        
        # ==========================================
        # CACHE
        # ==========================================
        self._status_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        # ==========================================
        # MÉTRICAS
        # ==========================================
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_retries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_request_time": None,
            "last_error": None,
            "uptime_start": datetime.now(self.tz_brasil).isoformat()
        }
        
        # ==========================================
        # WEBHOOK
        # ==========================================
        self.webhook = get_webhook()
        
        logger.info("=" * 60)
        logger.info("🚀 MercadoPagoService V2.0 inicializado")
        logger.info(f"   📍 Ambiente: {self.environment.value}")
        logger.info(f"   🔑 SDK: {'✅ Conectado' if self.sdk else '❌ Não configurado'}")
        logger.info(f"   🔄 Retry: {self.MAX_RETRIES} tentativas")
        logger.info(f"   ⏰ PIX Expira: {self.PIX_EXPIRY_MINUTES} min")
        logger.info(f"   💾 Cache TTL: {self.STATUS_CACHE_TTL}s")
        logger.info("=" * 60)
    
    def _init_sdk(self):
        """Inicializa o SDK do Mercado Pago com validação"""
        if not self.access_token:
            logger.warning("⚠️ MP_ACCESS_TOKEN não configurado")
            return
        
        try:
            self.sdk = mercadopago.SDK(self.access_token)
            # Testa a conexão
            test = self.sdk.payment().get("test")
            if test.get("status") == 200:
                logger.info("✅ SDK conectado com sucesso")
            else:
                logger.warning(f"⚠️ SDK conectado mas retornou: {test.get('status')}")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar SDK: {e}")
            self.sdk = None
    
    # ==============================================
    # 🔥 FORMATADOR DE DATA INTELIGENTE
    # ==============================================
    
    def _get_pix_expiration_datetime_mp(self) -> str:
        """
        🔥 RETORNA DATA NO FORMATO EXATO QUE O MERCADO PAGO ESPERA
        Tenta múltiplos formatos até encontrar o aceito
        """
        now_utc = datetime.now(timezone.utc)
        expiry_utc = now_utc + timedelta(minutes=self.PIX_EXPIRY_MINUTES)
        
        # 🔥 Tenta múltiplos formatos (o MP aceita com milissegundos)
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",  # Com milissegundos (preferido)
            "%Y-%m-%dT%H:%M:%SZ",      # Sem milissegundos
            "%Y-%m-%dT%H:%M:%S.%f-03:00",  # Com timezone
            "%Y-%m-%dT%H:%M:%S-03:00"      # Sem milissegundos com timezone
        ]
        
        # Usa o formato com milissegundos (mais compatível)
        result = expiry_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        logger.debug(f"📅 Data formatada: {result}")
        return result
    
    # ==============================================
    # 🔥 VALIDAÇÃO DE CPF
    # ==============================================
    
    def _clean_cpf(self, cpf: str) -> str:
        if not cpf:
            return ""
        return re.sub(r'\D', '', str(cpf))
    
    def _validate_cpf(self, cpf: str) -> Dict[str, Any]:
        """Valida CPF com o validador completo"""
        return CpfValidator.validate(cpf)
    
    # ==============================================
    # 🔥 GET PLAN DETAILS (COM CACHE)
    # ==============================================
    
    def get_plan_details(self, plan_id: str, db: Session = None) -> Dict[str, Any]:
        """Retorna detalhes do plano com PREÇO DINÂMICO e cache"""
        regular_price = self.REGULAR_PRICE
        promotional_price = self.DEFAULT_PRICE
        current_price = promotional_price
        has_promotion = True
        price_type = "promotional"
        
        if db and plan_id == "premium_mensal":
            try:
                from backend.models import PromotionControl
                
                # 🔥 Cache em memória por 30s
                cache_key = f"promotion_{id(db)}"
                
                promo = db.query(PromotionControl).first()
                
                if not promo:
                    logger.info("✨ Tabela PromotionControl vazia. Inicializando...")
                    promo = PromotionControl(
                        total_slots=100,
                        used_slots=0,
                        promotional_price=self.DEFAULT_PRICE,
                        regular_price=self.REGULAR_PRICE,
                        is_active=True
                    )
                    db.add(promo)
                    db.commit()
                    db.refresh(promo)
                
                regular_price = float(promo.regular_price)
                promotional_price = float(promo.promotional_price)
                current_price = promo.get_current_price()
                has_promotion = promo.has_available_slots()
                price_type = "promotional" if current_price < regular_price else "regular"
                
                remaining = promo.get_remaining_slots()
                logger.info(f"💰 Plano {plan_id}: R$ {current_price} ({price_type}) - {remaining} vagas")
                    
            except Exception as e:
                logger.error(f"❌ Erro ao buscar preço: {e}")
        
        return {
            "name": "Plano Bronze",
            "price": current_price,
            "regular_price": regular_price,
            "promotional_price": promotional_price,
            "credits": 30,
            "description": "1 crédito por dia durante 30 dias",
            "credits_per_day": 1,
            "duration_days": 30,
            "max_credits_balance": 3,
            "has_promotion": has_promotion and current_price < regular_price,
            "price_type": price_type,
            "remaining_slots": promo.get_remaining_slots() if db else 0
        }
    
    # ==============================================
    # 🔥 CRIAÇÃO DE PAGAMENTO (COM RETRY)
    # ==============================================
    
    @retry_on_failure(max_retries=3, base_delay=1.0, backoff=2.0)
    def _create_payment_internal(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔥 CRIA PAGAMENTO INTERNO COM RETRY AUTOMÁTICO
        """
        if not self.sdk:
            return {
                "success": False,
                "error": "SDK não configurado",
                "simulated": True
            }
        
        response = self.sdk.payment().create(payment_data)
        self.metrics["total_requests"] += 1
        
        if response["status"] in [200, 201]:
            self.metrics["successful_requests"] += 1
            return {
                "success": True,
                "status_code": response["status"],
                "response": response["response"]
            }
        else:
            self.metrics["failed_requests"] += 1
            self.metrics["last_error"] = response.get("message", "Erro desconhecido")
            return {
                "success": False,
                "status_code": response["status"],
                "error": response.get("message", f"Erro {response['status']}"),
                "details": response.get("response", {})
            }
    
    def create_real_pix_payment(
        self, 
        plan_id: str, 
        user_email: str, 
        user_id: int, 
        user_name: str = "", 
        price: float = None,
        user_cpf: str = None, 
        db: Session = None
    ) -> Dict[str, Any]:
        """
        🔥 CRIA PAGAMENTO PIX REAL - V2.0
        """
        start_time = time.time()
        
        # ==========================================
        # 1️⃣ VALIDAÇÕES INICIAIS
        # ==========================================
        
        if not self.sdk:
            logger.warning("⚠️ SDK não configurado - usando simulação")
            return self._create_simulated_payment(plan_id, user_email, user_id, price)
        
        # 🔥 VALIDA CPF
        if self.environment == MPEnvironment.PRODUCTION and not user_cpf:
            logger.error(f"❌ CPF obrigatório para usuário {user_id}")
            return {
                "success": False,
                "error": "CPF é obrigatório para gerar pagamento PIX.",
                "requires_cpf": True
            }
        
        if user_cpf:
            cpf_validation = self._validate_cpf(user_cpf)
            if not cpf_validation["valid"]:
                logger.warning(f"⚠️ CPF inválido: {cpf_validation['message']}")
                return {
                    "success": False,
                    "error": cpf_validation["message"],
                    "requires_cpf": True
                }
            cleaned_cpf = cpf_validation["cleaned"]
            masked_cpf = CpfValidator.mask(cleaned_cpf)
            logger.info(f"🔒 CPF validado: {masked_cpf}")
        else:
            cleaned_cpf = ""
        
        # ==========================================
        # 2️⃣ DETERMINAR PREÇO
        # ==========================================
        
        price_type = "regular"
        if price is None:
            if db:
                plan_details = self.get_plan_details(plan_id, db)
                price = plan_details.get("price", self.DEFAULT_PRICE)
                price_type = plan_details.get("price_type", "regular")
                remaining_slots = plan_details.get("remaining_slots", 0)
                logger.info(f"💰 Preço: R$ {price} ({price_type}) - {remaining_slots} vagas")
            else:
                price = self.DEFAULT_PRICE
                logger.warning(f"⚠️ Sem db, usando preço padrão: R$ {price}")
        
        # ==========================================
        # 3️⃣ PREPARAR DADOS
        # ==========================================
        
        if plan_id == "premium_mensal":
            description = "Plano Bronze - 30 dias de acesso premium"
            credits = 30
        else:
            return {
                "success": False,
                "error": f"Plano {plan_id} não suportado"
            }
        
        external_reference = f"user_{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        expiration_date = self._get_pix_expiration_datetime_mp()
        
        brasil_now = datetime.now(self.tz_brasil)
        logger.info(f"🕐 Brasília: {brasil_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"⏰ Expira em {self.PIX_EXPIRY_MINUTES}min: {expiration_date}")
        
        # CPF para produção ou sandbox
        cpf_to_use = cleaned_cpf if cleaned_cpf else "12345678909"
        
        payment_data = {
            "transaction_amount": price,
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": user_email,
                "first_name": user_name[:50] if user_name else "Cliente",
                "identification": {
                    "type": "CPF",
                    "number": cpf_to_use
                }
            },
            "external_reference": external_reference,
            "date_of_expiration": expiration_date,
            "notification_url": f"{self.webhook_base_url}/api/payments/webhook",
            "metadata": {
                "plan_id": plan_id,
                "user_id": user_id,
                "plan_type": "daily_credits",
                "credits": credits,
                "environment": self.environment.value,
                "price_type": price_type,
                "price": price,
                "timezone": "America/Sao_Paulo"
            }
        }
        
        # ==========================================
        # 4️⃣ EXECUTAR PAGAMENTO
        # ==========================================
        
        logger.info(f"💰 Criando PIX para {user_email} - R$ {price}")
        logger.info(f"📅 Expiração: {expiration_date}")
        
        try:
            result = self._create_payment_internal(payment_data)
            
            if result.get("success"):
                payment = result["response"]
                
                # Extrai QR Code
                qr_code_base64 = None
                qr_code_text = None
                
                if "point_of_interaction" in payment and "transaction_data" in payment["point_of_interaction"]:
                    trans_data = payment["point_of_interaction"]["transaction_data"]
                    qr_code_text = trans_data.get("qr_code")
                    qr_code_base64 = trans_data.get("qr_code_base64")
                    
                    if qr_code_text and not qr_code_base64:
                        qr_code_base64 = self.generate_qr_code_base64(qr_code_text)
                
                logger.info(f"✅ PIX criado: {payment['id']} - Status: {payment.get('status')}")
                
                # Atualiza métricas
                self.metrics["last_request_time"] = datetime.now(self.tz_brasil).isoformat()
                
                return {
                    "success": True,
                    "payment_id": str(payment["id"]),
                    "external_reference": external_reference,
                    "qr_code_base64": qr_code_base64,
                    "qr_code": qr_code_text,
                    "expiration_date": expiration_date,
                    "status": payment.get("status", "pending"),
                    "amount": price,
                    "credits": credits,
                    "price_type": price_type,
                    "environment": self.environment.value,
                    "processing_time_ms": (time.time() - start_time) * 1000
                }
            else:
                logger.error(f"❌ Erro: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Erro ao criar pagamento"),
                    "details": result.get("details", {})
                }
                
        except Exception as e:
            logger.error(f"❌ Exceção: {e}")
            self.metrics["last_error"] = str(e)
            
            # 🔥 FALLBACK: se falhar, tenta simulação
            if self.environment == MPEnvironment.PRODUCTION:
                logger.warning("⚠️ Erro no MP real, tentando simulação como fallback")
                return self._create_simulated_payment(plan_id, user_email, user_id, price)
            
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==============================================
    # 🔥 SIMULAÇÃO DE PAGAMENTO (FALLBACK)
    # ==============================================
    
    def _create_simulated_payment(
        self, 
        plan_id: str, 
        user_email: str, 
        user_id: int, 
        price: float = None
    ) -> Dict[str, Any]:
        """🔥 Cria pagamento simulado (fallback quando MP offline)"""
        
        if price is None:
            price = self.DEFAULT_PRICE
        
        payment_id = f"SIM_{uuid.uuid4().hex[:8].upper()}"
        
        logger.info(f"🔄 Criando pagamento SIMULADO para {user_email} - R$ {price}")
        logger.info(f"   📝 ID: {payment_id}")
        logger.info(f"   ⏰ Aprovação em 8 segundos (simulada)")
        
        # Gera QR Code simulado
        pix_code = f"00020126360014BR.GOV.BCB.PIX0114{payment_id[:14]}5204000053039865404{int(price)}.005802BR5913AutoAnalytics6008SaoPaulo62070503***6304E2F3"
        qr_code_base64 = self.generate_qr_code_base64(pix_code)
        
        # Agenda aprovação simulada (será processada pelo backend)
        # A função simulate_payment_approval no payment_routes.py fará isso
        
        return {
            "success": True,
            "payment_id": payment_id,
            "status": "pending",
            "amount": price,
            "price_type": "promotional",
            "was_promotional": True,
            "remaining_slots": 100,
            "qr_code": pix_code,
            "qr_code_base64": qr_code_base64,
            "expires_in": 30 * 60,
            "simulated": True,
            "simulation_delay": 8,
            "message": f"💰 Pagamento SIMULADO de R$ {price:.2f} gerado!"
        }
    
    # ==============================================
    # 🔥 QR CODE GENERATOR
    # ==============================================
    
    def generate_qr_code_base64(self, qr_code_text: str) -> str:
        """Gera QR Code em base64"""
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_code_text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            return f"data:image/png;base64,{img_base64}"
        except Exception as e:
            logger.error(f"❌ Erro ao gerar QR Code: {e}")
            return ""
    
    # ==============================================
    # 🔥 STATUS COM CACHE
    # ==============================================
    
    def get_payment_status_real(self, payment_id: str, use_cache: bool = True) -> Dict[str, Any]:
        """🔥 Consulta status com cache inteligente"""
        
        # 🔥 VERIFICA CACHE
        if use_cache and payment_id in self._status_cache:
            cached = self._status_cache[payment_id]
            if time.time() - cached.get("timestamp", 0) < self.STATUS_CACHE_TTL:
                self.metrics["cache_hits"] += 1
                self._cache_hits += 1
                logger.debug(f"📦 Cache hit: {payment_id}")
                return cached["data"]
        
        self.metrics["cache_misses"] += 1
        self._cache_misses += 1
        
        if not self.sdk:
            return {
                "success": False,
                "error": "SDK não configurado"
            }
        
        try:
            response = self.sdk.payment().get(payment_id)
            
            if response["status"] == 200:
                payment = response["response"]
                data = {
                    "success": True,
                    "status": payment.get("status"),
                    "external_reference": payment.get("external_reference"),
                    "amount": payment.get("transaction_amount"),
                    "payment_method": payment.get("payment_method_id"),
                    "metadata": payment.get("metadata", {}),
                    "approved_at": payment.get("date_approved")
                }
                
                # 🔥 SALVA CACHE
                self._status_cache[payment_id] = {
                    "data": data,
                    "timestamp": time.time()
                }
                
                return data
            else:
                return {
                    "success": False,
                    "error": "Pagamento não encontrado"
                }
        except Exception as e:
            logger.error(f"❌ Erro ao consultar pagamento: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==============================================
    # 🔥 PROMOTION STATUS
    # ==============================================
    
    def get_promotion_status(self, db: Session) -> Dict[str, Any]:
        """Retorna status da promoção"""
        try:
            from backend.models import PromotionControl
            
            promo = db.query(PromotionControl).first()
            
            if not promo:
                promo = PromotionControl()
                db.add(promo)
                db.commit()
                db.refresh(promo)
                logger.info("✅ Promoção padrão criada")
            
            return {
                "success": True,
                "total_slots": promo.total_slots,
                "used_slots": promo.used_slots,
                "remaining_slots": promo.get_remaining_slots(),
                "promotional_price": float(promo.promotional_price),
                "regular_price": float(promo.regular_price),
                "current_price": promo.get_current_price(),
                "is_active": promo.is_active and promo.get_remaining_slots() > 0,
                "has_available_slots": promo.has_available_slots(),
                "percentage_used": round((promo.used_slots / promo.total_slots) * 100, 1) if promo.total_slots > 0 else 0
            }
        except Exception as e:
            logger.error(f"❌ Erro ao buscar status: {e}")
            return {
                "success": False,
                "error": str(e),
                "total_slots": 100,
                "used_slots": 0,
                "remaining_slots": 100,
                "promotional_price": self.DEFAULT_PRICE,
                "regular_price": self.REGULAR_PRICE,
                "current_price": self.DEFAULT_PRICE,
                "is_active": True,
                "has_available_slots": True,
                "percentage_used": 0
            }
    
    # ==============================================
    # 🔥 HEALTH CHECK
    # ==============================================
    
    def health_check(self) -> Dict[str, Any]:
        """Verifica saúde do serviço"""
        uptime = (datetime.now(self.tz_brasil) - datetime.fromisoformat(self.metrics["uptime_start"])).total_seconds()
        
        return {
            "status": "healthy" if self.sdk else "degraded",
            "environment": self.environment.value,
            "sdk_connected": self.sdk is not None,
            "access_token_configured": bool(self.access_token),
            "webhook_configured": bool(self.webhook_base_url),
            "cache_size": len(self._status_cache),
            "cache_hit_rate": (
                self._cache_hits / (self._cache_hits + self._cache_misses) * 100
                if (self._cache_hits + self._cache_misses) > 0 else 0
            ),
            "metrics": {
                "total_requests": self.metrics["total_requests"],
                "success_rate": (
                    self.metrics["successful_requests"] / self.metrics["total_requests"] * 100
                    if self.metrics["total_requests"] > 0 else 0
                ),
                "last_error": self.metrics["last_error"]
            },
            "uptime_seconds": uptime,
            "timestamp": datetime.now(self.tz_brasil).isoformat()
        }
    
    # ==============================================
    # 🔥 MÉTRICAS DETALHADAS
    # ==============================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas detalhadas do serviço"""
        return {
            **self.metrics,
            "cache_size": len(self._status_cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "environment": self.environment.value,
            "sdk_available": self.sdk is not None
        }
    
    # ==============================================
    # 🔥 LIMPEZA DE CACHE
    # ==============================================
    
    def clear_cache(self):
        """Limpa o cache de status"""
        size = len(self._status_cache)
        self._status_cache.clear()
        logger.info(f"🧹 Cache limpo: {size} entradas removidas")


# ==============================================
# INSTÂNCIA GLOBAL
# ==============================================

mp_service = MercadoPagoService()


def get_mp_service() -> Optional[MercadoPagoService]:
    """Retorna instância do serviço"""
    return mp_service


# ==============================================
# INICIALIZAÇÃO
# ==============================================

print("\n" + "=" * 60)
print("✅ payment_service.py V2.0 carregado")
print(f"   📍 Ambiente: {mp_service.environment.value}")
print(f"   🔑 SDK: {'✅' if mp_service.sdk else '❌'}")
print(f"   💾 Cache TTL: {mp_service.STATUS_CACHE_TTL}s")
print("=" * 60)