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

# Importar sentinel
from backend.observability.sentinel import get_sentinel

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
        
        # Inicializar sentinel
        self.sentinel = get_sentinel()
        
        # Planos disponíveis (ATUALIZADO COM PLANO PREMIUM MENSAL)
        self.plans = {
            "basico": {
                "id": "basico",
                "name": "Básico",
                "credits": 10,
                "price": 29.90,
                "description": "10 análises - Ideal para começar",
                "popular": False,
                "savings": "0%",
                "type": "one_time",
                "credits_per_day": 0,
                "duration_days": 0  # uso imediato
            },
            "profissional": {
                "id": "profissional",
                "name": "Profissional",
                "credits": 30,
                "price": 79.90,
                "description": "30 análises - Para uso regular",
                "popular": True,
                "savings": "11%",
                "type": "one_time",
                "credits_per_day": 0,
                "duration_days": 0
            },
            "empresarial": {
                "id": "empresarial",
                "name": "Empresarial",
                "credits": 100,
                "price": 199.90,
                "description": "100 análises - Uso intensivo",
                "popular": False,
                "savings": "33%",
                "type": "one_time",
                "credits_per_day": 0,
                "duration_days": 0
            },
            "premium_mensal": {  # NOVO PLANO - CORRIGIDO
                "id": "premium_mensal",
                "name": "Premium Mensal",
                "credits": 30,  # 30 créditos no total
                "price": 58.90,
                "description": "1 crédito por dia durante 30 dias",
                "popular": True,
                "savings": "26%",  # Economia comparado ao profissional (79.90 -> 58.90)
                "type": "daily_credits",  # Créditos liberados diariamente
                "credits_per_day": 1,  # 1 crédito por dia
                "duration_days": 30,  # Durante 30 dias
                "features": [
                    "📅 1 crédito NOVO todo dia",
                    "⏳ Válido por 30 dias",
                    "💰 Menos de R$ 2,00 por dia",
                    "🔄 Ideal para uso diário",
                    "🎯 30 análises no mês"
                ]
            }
        }
    
    def calculate_premium_benefits(self):
        """Calcula benefícios do plano premium"""
        plan = self.plans["premium_mensal"]
        
        return {
            "total_credits": plan["credits"],
            "daily_credits": plan["credits_per_day"],
            "duration_days": plan["duration_days"],
            "price_per_credit": round(plan["price"] / plan["credits"], 2),
            "price_per_day": round(plan["price"] / plan["duration_days"], 2),
            "savings_vs_profissional": {
                "profissional_price": 79.90,
                "premium_price": plan["price"],
                "savings": round(79.90 - plan["price"], 2),
                "savings_percentage": round((79.90 - plan["price"]) / 79.90 * 100, 1)
            }
        }
    
    def get_plan_recommendation(self, user_usage: Dict = None):
        """Recomenda plano baseado no uso do usuário"""
        benefits = self.calculate_premium_benefits()
        
        return {
            "premium_mensal": {
                "best_for": "Uso diário consistente",
                "daily_cost": benefits["price_per_day"],
                "price_per_analysis": benefits["price_per_credit"],
                "comparison": f"Economia de R$ {benefits['savings_vs_profissional']['savings']} comparado ao Profissional",
                "message": "Perfeito para quem usa todo dia! 🎯"
            }
        }