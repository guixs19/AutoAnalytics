# backend/services/payment_service.py
import mercadopago
import os
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import json
import uuid
import logging

# 🔧 CORREÇÃO: import seguro do webhook
try:
    from backend.observability.sentinel import get_webhook
except ImportError:
    # Fallback se não existir
    def get_webhook():
        return None
    print("⚠️ webhook não disponível, usando fallback")

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """Serviço para integração com Mercado Pago"""
    
    def __init__(self):
        # Pegar credenciais do ambiente
        self.access_token = os.getenv("MP_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MP_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")
        
        # Inicializar SDK
        self.sdk = mercadopago.SDK(self.access_token)
        
        # 🔧 CORREÇÃO: usar get_webhook() com segurança
        self.webhook = get_webhook()
        
        # Planos disponíveis
        self.plans = {
            "basico": {
                "id": "basico",
                "name": "Básico",
                "credits": 10,
                "price": 29.90,
                "description": "10 análises - Ideal para começar",
                "popular": False,
                "savings": "0%",
                "type": "one_time"
            },
            "profissional": {
                "id": "profissional",
                "name": "Profissional",
                "credits": 30,
                "price": 79.90,
                "description": "30 análises - Para uso regular",
                "popular": True,
                "savings": "11%",
                "type": "one_time"
            },
            "empresarial": {
                "id": "empresarial",
                "name": "Empresarial",
                "credits": 100,
                "price": 199.90,
                "description": "100 análises - Uso intensivo",
                "popular": False,
                "savings": "33%",
                "type": "one_time"
            },
            "premium_mensal": {
                "id": "premium_mensal",
                "name": "Premium Mensal",
                "credits": 30,
                "price": 58.90,
                "description": "1 crédito por dia durante 30 dias",
                "popular": True,
                "savings": "26%",
                "type": "daily_credits",
                "credits_per_day": 1,
                "duration_days": 30,
                "max_credits_balance": 3  # 🔥 Limite de créditos acumulados
            }
        }
    
    def create_payment_preference(self, plan_id: str, user_email: str, user_id: int) -> Dict[str, Any]:
        """
        Cria preferência de pagamento no Mercado Pago
        
        Suporta:
        - Planos avulsos (créditos únicos)
        - Premium Mensal (créditos diários)
        """
        if plan_id not in self.plans:
            return {
                "success": False,
                "error": "Plano não encontrado"
            }
        
        plan = self.plans[plan_id]
        
        # ID único para a preferência
        external_reference = f"{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        
        # Criar preferência
        preference_data = {
            "items": [
                {
                    "title": plan["name"],
                    "description": plan["description"],
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": plan["price"]
                }
            ],
            "payer": {
                "email": user_email
            },
            "back_urls": {
                "success": f"{self.webhook_base_url}/payment/success",
                "failure": f"{self.webhook_base_url}/payment/failure",
                "pending": f"{self.webhook_base_url}/payment/pending"
            },
            "auto_return": "approved",
            "external_reference": external_reference,
            "notification_url": f"{self.webhook_base_url}/api/payments/webhook",
            "statement_descriptor": "ANALISE DE OFICINA",
            "metadata": {
                "plan_id": plan_id,
                "user_id": user_id,
                "plan_type": plan["type"],
                "credits": plan["credits"]
            }
        }
        
        # Para planos premium, adicionar metadados extras
        if plan["type"] == "daily_credits":
            preference_data["metadata"].update({
                "credits_per_day": plan.get("credits_per_day", 1),
                "duration_days": plan.get("duration_days", 30),
                "max_credits_balance": plan.get("max_credits_balance", 3)
            })
        
        try:
            response = self.sdk.preference().create(preference_data)
            
            if response["status"] == 201:
                preference = response["response"]
                return {
                    "success": True,
                    "preference_id": preference["id"],
                    "checkout_url": preference["init_point"],
                    "external_reference": external_reference,
                    "plan": plan
                }
            else:
                logger.error(f"Erro ao criar preferência: {response}")
                return {
                    "success": False,
                    "error": "Erro ao criar preferência de pagamento",
                    "details": response
                }
        except Exception as e:
            logger.error(f"Exceção ao criar preferência: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_pix_payment(self, plan_id: str, user_email: str, user_id: int) -> Dict[str, Any]:
        """
        Cria pagamento PIX para plano selecionado
        """
        if plan_id not in self.plans:
            return {
                "success": False,
                "error": "Plano não encontrado"
            }
        
        plan = self.plans[plan_id]
        
        # ID único para o pagamento
        external_reference = f"{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        
        # Criar pagamento PIX
        payment_data = {
            "transaction_amount": plan["price"],
            "description": plan["description"],
            "payment_method_id": "pix",
            "payer": {
                "email": user_email,
                "first_name": user_email.split("@")[0],
                "identification": {
                    "type": "CPF",
                    "number": "00000000000"  # Placeholder
                }
            },
            "external_reference": external_reference,
            "metadata": {
                "plan_id": plan_id,
                "user_id": user_id,
                "plan_type": plan["type"],
                "credits": plan["credits"]
            },
            "notification_url": f"{self.webhook_base_url}/api/payments/webhook"
        }
        
        # Para planos premium, adicionar metadados extras
        if plan["type"] == "daily_credits":
            payment_data["metadata"].update({
                "credits_per_day": plan.get("credits_per_day", 1),
                "duration_days": plan.get("duration_days", 30),
                "max_credits_balance": plan.get("max_credits_balance", 3)
            })
        
        try:
            response = self.sdk.payment().create(payment_data)
            
            if response["status"] == 201:
                payment = response["response"]
                
                # Gerar QR Code
                qr_code_base64 = None
                if "point_of_interaction" in payment and "transaction_data" in payment["point_of_interaction"]:
                    qr_code = payment["point_of_interaction"]["transaction_data"].get("qr_code")
                    qr_code_base64 = payment["point_of_interaction"]["transaction_data"].get("qr_code_base64")
                    
                    # Se não veio base64, gerar a partir do código
                    if qr_code and not qr_code_base64:
                        qr_code_base64 = self.generate_qr_code_base64(qr_code)
                
                return {
                    "success": True,
                    "payment_id": payment["id"],
                    "external_reference": external_reference,
                    "qr_code_base64": qr_code_base64,
                    "qr_code": payment.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code"),
                    "expiration_date": payment.get("date_of_expiration"),
                    "status": payment["status"],
                    "amount": plan["price"],
                    "credits": plan["credits"],
                    "plan": plan
                }
            else:
                logger.error(f"Erro ao criar pagamento PIX: {response}")
                return {
                    "success": False,
                    "error": "Erro ao criar pagamento PIX",
                    "details": response
                }
        except Exception as e:
            logger.error(f"Exceção ao criar pagamento PIX: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_qr_code_base64(self, qr_code_text: str) -> str:
        """Gera QR Code em base64 a partir do texto"""
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
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Consulta status de um pagamento"""
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
                    "metadata": payment.get("metadata", {})
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
    
    def process_webhook_notification(self, payment_id: str, payment_status: str) -> Dict[str, Any]:
        """
        Processa notificação do webhook do Mercado Pago
        """
        logger.info(f"📢 Webhook recebido - Payment ID: {payment_id}, Status: {payment_status}")
        
        # Consultar detalhes do pagamento
        payment_info = self.get_payment_status(payment_id)
        
        if not payment_info.get("success"):
            return {
                "success": False,
                "error": "Não foi possível obter informações do pagamento"
            }
        
        return {
            "success": True,
            "payment_id": payment_id,
            "status": payment_status,
            "external_reference": payment_info.get("external_reference"),
            "amount": payment_info.get("amount"),
            "metadata": payment_info.get("metadata", {})
        }
    
    def calculate_premium_benefits(self) -> Dict[str, Any]:
        """Calcula benefícios do plano premium"""
        plan = self.plans["premium_mensal"]
        
        return {
            "total_credits": plan["credits"],
            "daily_credits": plan["credits_per_day"],
            "duration_days": plan["duration_days"],
            "max_credits_balance": plan.get("max_credits_balance", 3),
            "price_per_credit": round(plan["price"] / plan["credits"], 2),
            "price_per_day": round(plan["price"] / plan["duration_days"], 2),
            "savings_vs_profissional": {
                "profissional_price": 79.90,
                "premium_price": plan["price"],
                "savings": round(79.90 - plan["price"], 2),
                "savings_percentage": round((79.90 - plan["price"]) / 79.90 * 100, 1)
            }
        }
    
    def get_plan_recommendation(self, user_usage: Dict = None) -> Dict[str, Any]:
        """Recomenda plano baseado no uso do usuário"""
        benefits = self.calculate_premium_benefits()
        
        return {
            "premium_mensal": {
                "best_for": "Uso diário consistente",
                "daily_cost": benefits["price_per_day"],
                "price_per_analysis": benefits["price_per_credit"],
                "max_credits_balance": benefits["max_credits_balance"],
                "comparison": f"Economia de R$ {benefits['savings_vs_profissional']['savings']} comparado ao Profissional",
                "message": "Perfeito para quem usa todo dia! 🎯"
            },
            "one_time_plans": {
                "best_for": "Uso esporádico",
                "message": "Compre créditos avulsos quando precisar"
            }
        }
    
    def get_all_plans(self) -> Dict[str, Any]:
        """Retorna todos os planos disponíveis com benefícios"""
        benefits = self.calculate_premium_benefits()
        
        plans = {}
        for plan_id, plan in self.plans.items():
            plans[plan_id] = {
                **plan,
                "benefits": benefits if plan["type"] == "daily_credits" else None
            }
        
        return {
            "success": True,
            "plans": plans,
            "premium_info": benefits
        }


# Instância global do serviço (opcional)
mp_service = MercadoPagoService() if os.getenv("MP_ACCESS_TOKEN") else None


def get_mp_service() -> Optional[MercadoPagoService]:
    """Retorna instância do MercadoPagoService se configurado"""
    return mp_service