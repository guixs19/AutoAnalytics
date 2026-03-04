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
        
        # Planos disponíveis (R$ 3,00 por crédito)
        self.plans = {
            "basico": {
                "id": "basico",
                "name": "Básico",
                "credits": 10,
                "price": 29.90,
                "description": "10 análises - Ideal para começar",
                "popular": False,
                "savings": "0%"
            },
            "profissional": {
                "id": "profissional",
                "name": "Profissional",
                "credits": 30,
                "price": 79.90,
                "description": "30 análises - Para uso regular",
                "popular": True,
                "savings": "11%"  # Economia de 11% comparado ao básico
            },
            "empresarial": {
                "id": "empresarial",
                "name": "Empresarial",
                "credits": 100,
                "price": 199.90,
                "description": "100 análises - Uso intensivo",
                "popular": False,
                "savings": "33%"  # Economia de 33% comparado ao básico
            }
        }
    
    def get_plans(self) -> Dict:
        """Retorna lista de planos disponíveis"""
        return self.plans
    
    def calculate_credits(self, amount: float) -> int:
        """Calcula créditos baseado no valor (R$ 3,00 por crédito)"""
        return int(amount / 3.0)
    
    def calculate_price(self, credits: int) -> float:
        """Calcula preço baseado nos créditos"""
        return credits * 3.0
    
    def generate_qr_base64(self, text: str) -> str:
        """Gera QR Code em base64"""
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    
    def create_payment_pix(
        self,
        user_id: int,
        user_email: str,
        user_name: str,
        amount: float,
        description: str = "Créditos AutoAnalytics",
        credits: int = None,
        plan_id: str = None
    ) -> Dict[str, Any]:
        """
        Cria pagamento via PIX
        """
        if not credits:
            credits = self.calculate_credits(amount)
        
        # Gerar ID único para a transação
        external_reference = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
        
        # Dados do pagamento
        payment_data = {
            "transaction_amount": amount,
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": user_email,
                "first_name": user_name.split()[0] if user_name else "Cliente",
                "last_name": " ".join(user_name.split()[1:]) if len(user_name.split()) > 1 else "",
            },
            "external_reference": external_reference,
            "metadata": {
                "credits": credits,
                "user_id": user_id,
                "user_email": user_email,
                "plan_id": plan_id,
                "system": "autoanalytics"
            },
            "notification_url": f"{self.webhook_base_url}/api/payments/webhook"
        }
        
        try:
            # Criar pagamento no Mercado Pago
            result = self.sdk.payment().create(payment_data)
            
            if result["status"] == 201 or result["status"] == 200:
                payment = result["response"]
                
                # Extrair dados do PIX
                point_of_interaction = payment.get("point_of_interaction", {})
                transaction_data = point_of_interaction.get("transaction_data", {})
                
                # Gerar QR Code como base64
                qr_code_text = transaction_data.get("qr_code", "")
                qr_code_base64 = None
                
                if qr_code_text:
                    qr_code_base64 = self.generate_qr_base64(qr_code_text)
                
                return {
                    "success": True,
                    "payment_id": str(payment["id"]),
                    "status": payment["status"],
                    "qr_code": qr_code_text,
                    "qr_code_base64": qr_code_base64,
                    "qr_code_url": transaction_data.get("qr_code_base64"),
                    "expiration_date": transaction_data.get("expiration_date"),
                    "credits": credits,
                    "amount": amount,
                    "external_reference": external_reference
                }
            else:
                return {
                    "success": False,
                    "error": f"Erro ao criar pagamento: {result['status']}",
                    "details": result.get("response", {})
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_checkout_preference(
        self,
        user_id: int,
        user_email: str,
        user_name: str,
        amount: float,
        description: str = "Créditos AutoAnalytics",
        credits: int = None,
        plan_id: str = None
    ) -> Dict[str, Any]:
        """
        Cria preferência de checkout (página do Mercado Pago)
        """
        if not credits:
            credits = self.calculate_credits(amount)
        
        # Gerar ID único para referência externa
        external_reference = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
        
        # Configurar preferência
        preference_data = {
            "items": [
                {
                    "id": plan_id or "credits",
                    "title": f"{credits} Créditos AutoAnalytics",
                    "description": description,
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": amount,
                    "picture_url": f"{self.webhook_base_url}/static/img/credits.png"
                }
            ],
            "payer": {
                "name": user_name.split()[0] if user_name else "Cliente",
                "surname": " ".join(user_name.split()[1:]) if len(user_name.split()) > 1 else "",
                "email": user_email
            },
            "back_urls": {
                "success": f"{self.webhook_base_url}/checkout/success",
                "failure": f"{self.webhook_base_url}/checkout/failure",
                "pending": f"{self.webhook_base_url}/checkout/pending"
            },
            "auto_return": "approved",
            "external_reference": external_reference,
            "payment_methods": {
                "excluded_payment_types": [],  # Nenhum excluído
                "installments": 12  # Máximo de parcelas
            },
            "metadata": {
                "credits": credits,
                "user_id": user_id,
                "user_email": user_email,
                "plan_id": plan_id,
                "system": "autoanalytics"
            },
            "notification_url": f"{self.webhook_base_url}/api/payments/webhook"
        }
        
        try:
            # Criar preferência
            result = self.sdk.preference().create(preference_data)
            
            if result["status"] == 201 or result["status"] == 200:
                preference = result["response"]
                
                return {
                    "success": True,
                    "preference_id": preference["id"],
                    "init_point": preference["init_point"],  # URL do checkout
                    "sandbox_init_point": preference.get("sandbox_init_point"),
                    "credits": credits,
                    "amount": amount,
                    "external_reference": external_reference,
                    "status": "pending"
                }
            else:
                return {
                    "success": False,
                    "error": f"Erro ao criar preferência: {result['status']}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Consulta status de um pagamento
        """
        try:
            result = self.sdk.payment().get(payment_id)
            
            if result["status"] == 200:
                payment = result["response"]
                
                # Extrair créditos dos metadados
                metadata = payment.get("metadata", {})
                credits = metadata.get("credits", 0)
                
                return {
                    "success": True,
                    "payment_id": str(payment["id"]),
                    "status": payment["status"],
                    "status_detail": payment.get("status_detail"),
                    "amount": payment["transaction_amount"],
                    "payment_method": payment["payment_method_id"],
                    "payment_type": payment["payment_type_id"],
                    "approved_at": payment.get("date_approved"),
                    "external_reference": payment.get("external_reference"),
                    "credits": credits,
                    "metadata": metadata
                }
            else:
                return {
                    "success": False,
                    "error": f"Erro ao consultar pagamento: {result['status']}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def process_webhook(self, data: Dict[str, Any]) -> Tuple[bool, str, Dict]:
        """
        Processa webhook do Mercado Pago
        
        Retorna: (sucesso, ação, dados)
        """
        try:
            # Verificar tipo de notificação
            action = data.get("action")
            payment_id = data.get("data", {}).get("id")
            
            if not payment_id:
                # Pode ser notificação de preferência
                return False, "ignored", {"error": "ID não encontrado"}
            
            # Consultar status do pagamento
            payment_info = self.get_payment_status(payment_id)
            
            if not payment_info["success"]:
                return False, "error", payment_info
            
            # Determinar ação baseada no status
            if payment_info["status"] == "approved":
                return True, "approved", payment_info
            elif payment_info["status"] in ["rejected", "cancelled"]:
                return True, "rejected", payment_info
            elif payment_info["status"] == "pending":
                return True, "pending", payment_info
            else:
                return True, "other", payment_info
                
        except Exception as e:
            return False, "error", {"error": str(e)}