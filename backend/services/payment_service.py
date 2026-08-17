# backend/services/payment_service.py - VERSÃO 2.1 (CORRIGIDA E ESTÁVEL)
"""
🔥 SISTEMA DE PAGAMENTO - AUTOANALYTICS
================================================================================
VERSÃO 2.1 - CORREÇÃO DE LOGGER E MELHORIAS
================================================================================
✅ CORREÇÕES:
   1. ✅ LOGGER CORRIGIDO: logger definido corretamente no escopo
   2. ✅ DATA COM MILISSEGUNDOS: formato aceito pelo Mercado Pago
   3. ✅ VALIDAÇÃO DE CPF: com dígitos verificadores
   4. ✅ TRATAMENTO DE ERROS: robusto e com fallback
   5. ✅ LOGS ESTRUTURADOS: facilitam debug
================================================================================
"""

import mercadopago
import os
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import json
import uuid
import logging
import re

# ==============================================
# LOGGER CONFIGURADO
# ==============================================

logger = logging.getLogger(__name__)

# ==============================================
# WEBHOOK (IMPORTAÇÃO SEGURA)
# ==============================================

try:
    from backend.observability.sentinel import get_webhook
except ImportError:
    def get_webhook():
        return None
    logger.warning("⚠️ webhook não disponível, usando fallback")


# ==============================================
# VALIDADOR DE CPF
# ==============================================

class CpfValidator:
    """🔥 Validador de CPF com algoritmo de dígitos verificadores"""
    
    @staticmethod
    def validate(cpf: str) -> Dict[str, Any]:
        """Valida CPF com algoritmo completo"""
        cleaned = re.sub(r'\D', '', str(cpf))
        
        if len(cleaned) != 11:
            return {"valid": False, "cleaned": cleaned, "message": "CPF deve conter 11 dígitos"}
        
        # Verifica dígitos repetidos
        if cleaned == cleaned[0] * 11:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (dígitos repetidos)"}
        
        # Primeiro dígito verificador
        sum_ = 0
        for i in range(9):
            sum_ += int(cleaned[i]) * (10 - i)
        remainder = 11 - (sum_ % 11)
        first_digit = 0 if remainder >= 10 else remainder
        
        if int(cleaned[9]) != first_digit:
            return {"valid": False, "cleaned": cleaned, "message": "CPF inválido (primeiro dígito verificador)"}
        
        # Segundo dígito verificador
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
        """Formata CPF para exibição"""
        cleaned = re.sub(r'\D', '', str(cpf))
        if len(cleaned) != 11:
            return cpf
        return f"{cleaned[:3]}.{cleaned[3:6]}.{cleaned[6:9]}-{cleaned[9:]}"


# ==============================================
# CLASSE PRINCIPAL
# ==============================================

class MercadoPagoService:
    """Serviço para integração REAL com Mercado Pago"""
    
    # Constantes
    DEFAULT_PRICE = 97.00
    REGULAR_PRICE = 149.90
    PIX_EXPIRY_MINUTES = 30
    TOTAL_SLOTS = 100
    
    def __init__(self):
        # ==========================================
        # CONFIGURAÇÃO
        # ==========================================
        self.access_token = os.getenv("MP_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MP_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")
        
        self.environment = os.getenv("MP_ENVIRONMENT", "production")
        self.tz_brasil = timezone(timedelta(hours=-3))
        
        # ==========================================
        # SDK
        # ==========================================
        self.sdk = None
        self._init_sdk()
        
        # ==========================================
        # WEBHOOK
        # ==========================================
        self.webhook = get_webhook()
        
        logger.info("=" * 60)
        logger.info("🚀 MercadoPagoService inicializado")
        logger.info(f"   📍 Ambiente: {self.environment}")
        logger.info(f"   🔑 SDK: {'✅ Conectado' if self.sdk else '❌ Não configurado'}")
        logger.info(f"   ⏰ PIX Expira: {self.PIX_EXPIRY_MINUTES} min")
        logger.info("=" * 60)
    
    # ==============================================
    # SDK
    # ==============================================
    
    def _init_sdk(self):
        """Inicializa SDK do Mercado Pago"""
        if not self.access_token:
            logger.warning("⚠️ MP_ACCESS_TOKEN não configurado - PIX real não funcionará")
            return
        
        try:
            self.sdk = mercadopago.SDK(self.access_token)
            logger.info(f"✅ Mercado Pago SDK inicializado ({self.environment})")
            logger.info(f"🕐 Fuso horário configurado: UTC-3 (Brasília)")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar SDK: {e}")
            self.sdk = None
    
    # ==============================================
    # DATAS
    # ==============================================
    
    def _get_current_datetime_brasil(self) -> datetime:
        """Retorna datetime atual no fuso Brasília"""
        return datetime.now(self.tz_brasil)
    
    def _get_pix_expiration_datetime_mp(self) -> str:
        """
        🔥 RETORNA DATA NO FORMATO EXATO QUE O MERCADO PAGO ESPERA
        Formato: yyyy-MM-dd'T'HH:mm:ss.SSSZ (com milissegundos)
        """
        now_utc = datetime.now(timezone.utc)
        expiry_utc = now_utc + timedelta(minutes=self.PIX_EXPIRY_MINUTES)
        # Com milissegundos (3 casas decimais)
        return expiry_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
    # ==============================================
    # CPF
    # ==============================================
    
    def _clean_cpf(self, cpf: str) -> str:
        """Remove caracteres não numéricos do CPF"""
        if not cpf:
            return ""
        return re.sub(r'\D', '', str(cpf))
    
    def _validate_cpf(self, cpf: str) -> Dict[str, Any]:
        """Valida CPF com o validador completo"""
        return CpfValidator.validate(cpf)
    
    # ==============================================
    # PLANOS
    # ==============================================
    
    def get_plan_details(self, plan_id: str, db: Session = None) -> Dict[str, Any]:
        """Retorna detalhes do plano com PREÇO DINÂMICO"""
        regular_price = self.REGULAR_PRICE
        promotional_price = self.DEFAULT_PRICE
        current_price = promotional_price
        has_promotion = True
        price_type = "promotional"
        remaining_slots = self.TOTAL_SLOTS
        
        if db and plan_id == "premium_mensal":
            try:
                from backend.models import PromotionControl
                
                promo = db.query(PromotionControl).first()
                
                if not promo:
                    logger.info("✨ Tabela PromotionControl vazia. Inicializando...")
                    promo = PromotionControl(
                        total_slots=self.TOTAL_SLOTS,
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
                remaining_slots = promo.get_remaining_slots()
                
                logger.info(f"💰 Plano {plan_id}: R$ {current_price} ({price_type}) - {remaining_slots} vagas")
                    
            except Exception as e:
                logger.error(f"❌ Erro ao buscar preço: {e}")
                logger.warning(f"⚠️ Usando preço padrão: R$ {current_price}")
        
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
            "remaining_slots": remaining_slots
        }
    
    def get_current_price(self, plan_id: str, db: Session = None) -> float:
        """Retorna o preço atual do plano"""
        details = self.get_plan_details(plan_id, db)
        return details.get("price", self.DEFAULT_PRICE)
    
    # ==============================================
    # PROMOÇÃO
    # ==============================================
    
    def get_promotion_status(self, db: Session) -> Dict[str, Any]:
        """Retorna status da promoção"""
        try:
            from backend.models import PromotionControl
            
            promo = db.query(PromotionControl).first()
            
            if not promo:
                promo = PromotionControl(
                    total_slots=self.TOTAL_SLOTS,
                    used_slots=0,
                    promotional_price=self.DEFAULT_PRICE,
                    regular_price=self.REGULAR_PRICE,
                    is_active=True
                )
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
                "has_available_slots": promo.has_available_slots()
            }
        except Exception as e:
            logger.error(f"❌ Erro ao buscar status: {e}")
            return {
                "success": False,
                "error": str(e),
                "total_slots": self.TOTAL_SLOTS,
                "used_slots": 0,
                "remaining_slots": self.TOTAL_SLOTS,
                "promotional_price": self.DEFAULT_PRICE,
                "regular_price": self.REGULAR_PRICE,
                "current_price": self.DEFAULT_PRICE,
                "is_active": True,
                "has_available_slots": True
            }
    
    # ==============================================
    # PAGAMENTO
    # ==============================================
    
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
        🔥 CRIA PAGAMENTO PIX REAL NO MERCADO PAGO
        """
        # ==========================================
        # 1. VALIDAÇÕES
        # ==========================================
        
        if not self.sdk:
            logger.warning("⚠️ SDK não configurado")
            return {
                "success": False,
                "error": "Mercado Pago não configurado. Configure MP_ACCESS_TOKEN no .env",
                "simulated": True
            }
        
        # CPF obrigatório em produção
        if self.environment == "production" and not user_cpf:
            logger.error(f"❌ CPF obrigatório para usuário {user_id}")
            return {
                "success": False,
                "error": "CPF é obrigatório para gerar pagamento PIX.",
                "requires_cpf": True
            }
        
        # Valida CPF
        cleaned_cpf = ""
        if user_cpf:
            validation = self._validate_cpf(user_cpf)
            if not validation["valid"]:
                logger.warning(f"⚠️ CPF inválido: {validation['message']}")
                return {
                    "success": False,
                    "error": validation["message"],
                    "requires_cpf": True
                }
            cleaned_cpf = validation["cleaned"]
            logger.info(f"🔒 CPF validado: {CpfValidator.mask(cleaned_cpf)}")
        
        # ==========================================
        # 2. PREÇO
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
        # 3. DADOS DO PAGAMENTO
        # ==========================================
        
        if plan_id != "premium_mensal":
            return {
                "success": False,
                "error": f"Plano {plan_id} não suportado para PIX real"
            }
        
        description = "Plano Bronze - 30 dias de acesso premium com 1 crédito por dia"
        credits = 30
        
        external_reference = f"user_{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        expiration_date = self._get_pix_expiration_datetime_mp()
        
        brasil_now = self._get_current_datetime_brasil()
        logger.info(f"🕐 Horário Brasília: {brasil_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"⏰ Expira em {self.PIX_EXPIRY_MINUTES}min (UTC): {expiration_date}")
        
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
                "credits_per_day": 1,
                "duration_days": 30,
                "max_credits_balance": 3,
                "cpf_provided": bool(user_cpf),
                "environment": self.environment,
                "timezone": "America/Sao_Paulo (UTC-3)",
                "expiration_minutes": self.PIX_EXPIRY_MINUTES,
                "price_type": price_type,
                "price": price
            }
        }
        
        # ==========================================
        # 4. EXECUTA
        # ==========================================
        
        try:
            logger.info(f"💰 Criando PIX para {user_email} - R$ {price}")
            logger.info(f"📅 Data expiração: {expiration_date}")
            
            response = self.sdk.payment().create(payment_data)
            
            if response["status"] == 201:
                payment = response["response"]
                
                # Extrai QR Code
                qr_code_base64 = None
                qr_code_text = None
                
                if "point_of_interaction" in payment and "transaction_data" in payment["point_of_interaction"]:
                    transaction_data = payment["point_of_interaction"]["transaction_data"]
                    qr_code_text = transaction_data.get("qr_code")
                    qr_code_base64 = transaction_data.get("qr_code_base64")
                    
                    if qr_code_text and not qr_code_base64:
                        qr_code_base64 = self.generate_qr_code_base64(qr_code_text)
                
                logger.info(f"✅ PIX criado: {payment['id']} - Status: {payment.get('status')}")
                
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
                    "plan_type": "daily_credits",
                    "price_type": price_type,
                    "environment": self.environment,
                    "cpf_used": bool(user_cpf),
                    "timezone": "America/Sao_Paulo (UTC-3)"
                }
            else:
                logger.error(f"❌ Erro ao criar pagamento: {response}")
                return {
                    "success": False,
                    "error": response.get("message", "Erro ao criar pagamento PIX"),
                    "details": response
                }
                
        except Exception as e:
            logger.error(f"❌ Exceção: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==============================================
    # QR CODE
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
    # STATUS
    # ==============================================
    
    def get_payment_status_real(self, payment_id: str) -> Dict[str, Any]:
        """Consulta status do pagamento"""
        if not self.sdk:
            return {
                "success": False,
                "error": "Mercado Pago não configurado"
            }
        
        try:
            response = self.sdk.payment().get(payment_id)
            
            if response["status"] == 200:
                payment = response["response"]
                return {
                    "success": True,
                    "status": payment.get("status"),
                    "external_reference": payment.get("external_reference"),
                    "amount": payment.get("transaction_amount"),
                    "payment_method": payment.get("payment_method_id"),
                    "metadata": payment.get("metadata", {}),
                    "approved_at": payment.get("date_approved")
                }
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
# INSTÂNCIA GLOBAL
# ==============================================

mp_service = MercadoPagoService()


def get_mp_service() -> Optional[MercadoPagoService]:
    """Retorna instância do serviço"""
    return mp_service


# ==============================================
# INICIALIZAÇÃO
# ==============================================

logger.info("=" * 60)
logger.info("✅ payment_service.py V2.1 carregado")
logger.info(f"   📍 Ambiente: {mp_service.environment}")
logger.info(f"   🔑 SDK: {'✅' if mp_service.sdk else '❌'}")
logger.info("=" * 60)