# backend/services/payment_service.py - VERSÃO CORRIGIDA

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

try:
    from backend.observability.sentinel import get_webhook
except ImportError:
    def get_webhook():
        return None
    print("⚠️ webhook não disponível, usando fallback")

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """Serviço para integração REAL com Mercado Pago"""
    
    def __init__(self):
        self.access_token = os.getenv("MP_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MP_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")
        
        self.environment = os.getenv("MP_ENVIRONMENT", "production")
        self.tz_brasil = timezone(timedelta(hours=-3))
        
        if self.access_token:
            self.sdk = mercadopago.SDK(self.access_token)
            logger.info(f"✅ Mercado Pago SDK inicializado ({self.environment})")
            logger.info(f"🕐 Fuso horário configurado: UTC-3 (Brasília)")
        else:
            self.sdk = None
            logger.warning("⚠️ MP_ACCESS_TOKEN não configurado - PIX real não funcionará")
        
        self.webhook = get_webhook()
    
    def _get_current_datetime_brasil(self) -> datetime:
        return datetime.now(self.tz_brasil)
    
    def _get_pix_expiration_datetime_mp(self) -> str:
        """
        🔥 RETORNA DATA NO FORMATO EXATO QUE O MERCADO PAGO ESPERA
        Formato: yyyy-MM-dd'T'HH:mm:ssZ
        Exemplo: 2026-08-17T20:23:00Z
        
        IMPORTANTE: O Mercado Pago NÃO aceita milissegundos nem timezone offset (+/-)
        """
        # Data atual em UTC (Mercado Pago usa UTC)
        now_utc = datetime.now(timezone.utc)
        # Adiciona 30 minutos
        expiry_utc = now_utc + timedelta(minutes=30)
        # Formato exato: yyyy-MM-dd'T'HH:mm:ssZ
        return expiry_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def _clean_cpf(self, cpf: str) -> str:
        if not cpf:
            return ""
        return re.sub(r'\D', '', str(cpf))
    
    def _validate_cpf_length(self, cpf: str) -> bool:
        cleaned = self._clean_cpf(cpf)
        return len(cleaned) == 11
    
    def get_plan_details(self, plan_id: str, db: Session = None) -> Dict[str, Any]:
        """Retorna detalhes do plano com PREÇO DINÂMICO"""
        regular_price = 149.90
        promotional_price = 97.00
        current_price = promotional_price
        has_promotion = True
        price_type = "promotional"
        
        if db and plan_id == "premium_mensal":
            try:
                from backend.models import PromotionControl
                
                promo = db.query(PromotionControl).first()
                
                if not promo:
                    logger.info("✨ Tabela PromotionControl vazia. Inicializando lote de fundador...")
                    promo = PromotionControl(
                        total_slots=100,
                        used_slots=0,
                        promotional_price=97.00,
                        regular_price=149.90,
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
                
                logger.info(f"💰 Preço dinâmico para plano {plan_id}: R$ {current_price} ({price_type})")
                logger.info(f"   Vagas restantes: {promo.get_remaining_slots()}/{promo.total_slots}")
                    
            except Exception as e:
                logger.error(f"❌ Erro ao buscar preço dinâmico do banco: {e}")
                logger.warning(f"⚠️ Usando preço padrão de fallback: R$ {current_price}")
        
        plans = {
            "premium_mensal": {
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
                "price_type": price_type
            }
        }
        
        return plans.get(plan_id, {})
    
    def get_current_price(self, plan_id: str, db: Session = None) -> float:
        details = self.get_plan_details(plan_id, db)
        return details.get("price", 97.00)
    
    def get_promotion_status(self, db: Session) -> Dict[str, Any]:
        try:
            from backend.models import PromotionControl
            
            promo = db.query(PromotionControl).first()
            
            if not promo:
                promo = PromotionControl()
                db.add(promo)
                db.commit()
                db.refresh(promo)
                logger.info("✅ Promoção padrão criada (100 vagas a R$ 97,00)")
            
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
            logger.error(f"❌ Erro ao buscar status da promoção: {e}")
            return {
                "success": False,
                "error": str(e),
                "total_slots": 100,
                "used_slots": 0,
                "remaining_slots": 100,
                "promotional_price": 97.00,
                "regular_price": 149.90,
                "current_price": 97.00,
                "is_active": True,
                "has_available_slots": True
            }
    
    def create_real_pix_payment(self, plan_id: str, user_email: str, user_id: int, 
                                 user_name: str = "", price: float = None,
                                 user_cpf: str = None, db: Session = None) -> Dict[str, Any]:
        """
        🔥 CRIA PAGAMENTO PIX REAL NO MERCADO PAGO
        """
        if not self.sdk:
            return {
                "success": False,
                "error": "Mercado Pago não configurado. Configure MP_ACCESS_TOKEN no .env",
                "simulated": True
            }
        
        if self.environment == "production" and not user_cpf:
            logger.error(f"❌ Tentativa de criar PIX sem CPF para usuário {user_id} - BLOQUEADO")
            return {
                "success": False,
                "error": "CPF é obrigatório para gerar pagamento PIX. Por favor, informe seu CPF.",
                "requires_cpf": True
            }
        
        cleaned_cpf = self._clean_cpf(user_cpf) if user_cpf else ""
        if user_cpf and not self._validate_cpf_length(cleaned_cpf):
            logger.warning(f"⚠️ CPF inválido para usuário {user_id}")
            return {
                "success": False,
                "error": "CPF inválido. O CPF deve conter 11 dígitos.",
                "requires_cpf": True
            }
        
        price_type = "regular"
        if price is None:
            if db:
                plan_details = self.get_plan_details(plan_id, db)
                price = plan_details.get("price", 97.00)
                price_type = plan_details.get("price_type", "regular")
                logger.info(f"💰 Preço dinâmico obtido do banco: R$ {price} ({price_type})")
            else:
                price = 97.00
                logger.warning(f"⚠️ Sem acesso ao banco, usando preço padrão: R$ {price}")
        
        if plan_id == "premium_mensal":
            description = "Plano Bronze - 30 dias de acesso premium com 1 crédito por dia"
            credits = 30
        else:
            return {
                "success": False,
                "error": f"Plano {plan_id} não suportado para PIX real"
            }
        
        external_reference = f"user_{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        
        # 🔥 CORREÇÃO: Usar formato exato do Mercado Pago
        expiration_date = self._get_pix_expiration_datetime_mp()
        
        brasil_now = self._get_current_datetime_brasil()
        logger.info(f"🕐 Horário atual Brasília (UTC-3): {brasil_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"⏰ PIX expira em 30 minutos (UTC): {expiration_date}")
        
        if self.environment == "production":
            cpf_to_use = cleaned_cpf
            logger.info(f"🔒 Usando CPF do usuário para pagamento (produção)")
        else:
            cpf_to_use = cleaned_cpf if cleaned_cpf else "12345678909"
            logger.info(f"🧪 Ambiente sandbox")
        
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
            "date_of_expiration": expiration_date,  # 🔥 FORMATO CORRETO
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
                "expiration_minutes": 30,
                "price_type": price_type,
                "price": price
            }
        }
        
        try:
            logger.info(f"💰 Criando pagamento PIX real para {user_email} - Valor: R$ {price}")
            logger.info(f"📅 Data expiração (formato MP): {expiration_date}")
            
            response = self.sdk.payment().create(payment_data)
            
            if response["status"] == 201:
                payment = response["response"]
                
                qr_code_base64 = None
                qr_code_text = None
                
                if "point_of_interaction" in payment and "transaction_data" in payment["point_of_interaction"]:
                    transaction_data = payment["point_of_interaction"]["transaction_data"]
                    qr_code_text = transaction_data.get("qr_code")
                    qr_code_base64 = transaction_data.get("qr_code_base64")
                    
                    if qr_code_text and not qr_code_base64:
                        qr_code_base64 = self.generate_qr_code_base64(qr_code_text)
                
                logger.info(f"✅ Pagamento PIX criado: {payment['id']}")
                
                return {
                    "success": True,
                    "payment_id": str(payment["id"]),
                    "external_reference": external_reference,
                    "qr_code_base64": qr_code_base64,
                    "qr_code": qr_code_text,
                    "expiration_date": expiration_date,
                    "status": payment["status"],
                    "amount": price,
                    "credits": credits,
                    "plan_type": "daily_credits",
                    "price_type": price_type,
                    "environment": self.environment,
                    "cpf_used": bool(user_cpf),
                    "timezone": "America/Sao_Paulo (UTC-3)"
                }
            else:
                logger.error(f"❌ Erro ao criar pagamento PIX: {response}")
                return {
                    "success": False,
                    "error": response.get("message", "Erro ao criar pagamento PIX"),
                    "details": response
                }
                
        except Exception as e:
            logger.error(f"❌ Exceção ao criar pagamento PIX: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_qr_code_base64(self, qr_code_text: str) -> str:
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
            logger.error(f"Erro ao gerar QR Code: {e}")
            return ""
    
    def get_payment_status_real(self, payment_id: str) -> Dict[str, Any]:
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
                    "status": payment["status"],
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
            logger.error(f"Erro ao consultar pagamento: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Instância global
mp_service = MercadoPagoService()


def get_mp_service() -> Optional[MercadoPagoService]:
    return mp_service