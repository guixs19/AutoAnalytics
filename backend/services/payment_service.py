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
    """Serviço para integração REAL com Mercado Pago"""
    
    def __init__(self):
        # Pegar credenciais do ambiente
        self.access_token = os.getenv("MP_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MP_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "https://seu-dominio.com")
        
        # Inicializar SDK apenas se tiver token
        if self.access_token:
            self.sdk = mercadopago.SDK(self.access_token)
            logger.info("✅ Mercado Pago SDK inicializado")
        else:
            self.sdk = None
            logger.warning("⚠️ MP_ACCESS_TOKEN não configurado - PIX real não funcionará")
        
        self.webhook = get_webhook()
    
    def create_real_pix_payment(self, plan_id: str, user_email: str, user_id: int, 
                                 user_name: str = "", price: float = None) -> Dict[str, Any]:
        """
        CRIA PAGAMENTO PIX REAL NO MERCADO PAGO
        
        Args:
            plan_id: ID do plano (premium_mensal)
            user_email: Email do usuário
            user_id: ID do usuário
            user_name: Nome do usuário
            price: Preço (opcional, usa do plano se não informado)
        """
        if not self.sdk:
            return {
                "success": False,
                "error": "Mercado Pago não configurado. Configure MP_ACCESS_TOKEN no .env",
                "simulated": True
            }
        
        # Configurações do plano
        if plan_id == "premium_mensal":
            plan_name = "Plano Bronze - AutoAnalytics Pro"
            if price is None:
                price = 97.00  # Preço promocional padrão
            description = "Plano Bronze - 30 dias de acesso premium com 1 crédito por dia"
            credits = 30
        else:
            return {
                "success": False,
                "error": f"Plano {plan_id} não suportado para PIX real"
            }
        
        # ID único para o pagamento (external_reference)
        external_reference = f"user_{user_id}_{plan_id}_{uuid.uuid4().hex[:8]}"
        
        # Data de expiração (30 minutos)
        expiration_date = (datetime.now() + timedelta(minutes=30)).isoformat()
        
        # Dados do pagamento PIX
        payment_data = {
            "transaction_amount": price,
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": user_email,
                "first_name": user_name[:50] if user_name else "Cliente",
                "identification": {
                    "type": "CPF",
                    "number": "00000000000"  # Placeholder - idealmente pedir CPF
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
                "max_credits_balance": 3
            }
        }
        
        try:
            logger.info(f"💰 Criando pagamento PIX real para {user_email} - Valor: R$ {price}")
            
            # Chamar API do Mercado Pago
            response = self.sdk.payment().create(payment_data)
            
            if response["status"] == 201:
                payment = response["response"]
                
                # Extrair QR Code
                qr_code_base64 = None
                qr_code_text = None
                
                if "point_of_interaction" in payment and "transaction_data" in payment["point_of_interaction"]:
                    transaction_data = payment["point_of_interaction"]["transaction_data"]
                    qr_code_text = transaction_data.get("qr_code")
                    qr_code_base64 = transaction_data.get("qr_code_base64")
                    
                    # Se não veio base64, gerar a partir do código
                    if qr_code_text and not qr_code_base64:
                        qr_code_base64 = self.generate_qr_code_base64(qr_code_text)
                
                logger.info(f"✅ Pagamento PIX criado: {payment['id']} - QR Code gerado")
                
                return {
                    "success": True,
                    "payment_id": str(payment["id"]),
                    "external_reference": external_reference,
                    "qr_code_base64": qr_code_base64,
                    "qr_code": qr_code_text,
                    "expiration_date": payment.get("date_of_expiration"),
                    "status": payment["status"],
                    "amount": price,
                    "credits": credits,
                    "plan_type": "daily_credits",
                    "price_type": "real"
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
    
    def get_payment_status_real(self, payment_id: str) -> Dict[str, Any]:
        """Consulta status REAL de um pagamento no Mercado Pago"""
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
    
    def get_plan_details(self, plan_id: str) -> Dict[str, Any]:
        """Retorna detalhes do plano"""
        plans = {
            "premium_mensal": {
                "name": "Plano Bronze",
                "price": 97.00,
                "regular_price": 149.90,
                "credits": 30,
                "description": "1 crédito por dia durante 30 dias",
                "credits_per_day": 1,
                "duration_days": 30,
                "max_credits_balance": 3
            }
        }
        return plans.get(plan_id, {})


# Instância global
mp_service = MercadoPagoService()


def get_mp_service() -> Optional[MercadoPagoService]:
    """Retorna instância do MercadoPagoService"""
    return mp_service