# backend/api/payment_routes.py - VERSÃO CORRIGIDA (ordem correta)

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import uuid
import traceback
import logging
import re

from backend.database import get_db
from backend import crud
from backend.api.auth_routes import get_current_user
from backend.models import User, Payment, DailyCreditLog, UserPlan
from backend.services.payment_service import MercadoPagoService

# Importar funções do sentinel
from backend.observability.sentinel import (
    alert_payment_approved,
    alert_payment_pending,
    alert_payment_failed,
    alert_system_error,
    alert_premium_activated
)

logger = logging.getLogger(__name__)

# ==============================================
# 🔥 CRIAÇÃO DO ROUTER (AQUI! ANTES DAS ROTAS)
# ==============================================
router = APIRouter(prefix="/payments", tags=["payments"])

mp_service = MercadoPagoService()

# ==============================================
# PROTEÇÃO XSS E SANITIZAÇÃO
# ==============================================

def sanitize_input(text: str) -> str:
    """Sanitiza entrada para evitar XSS"""
    if not text:
        return ""
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'[<>\"\'\/\\;`]', '', text)
    return text[:500]

# ==============================================
# PLANO PREMIUM - R$97
# ==============================================
PLANO_PREMIUM = {
    "id": "premium_mensal",
    "name": "Plano Premium Mensal",
    "price": 97.00,
    "description": "1 crédito por dia durante 30 dias",
    "popular": True,
    "features": [
        "✅ 1 crédito novo todo dia",
        "✅ 30 créditos no total",
        "✅ Válido por 30 dias",
        "✅ Análises com IA avançada",
        "✅ Suporte prioritário",
        "⚠️ Limite máximo de 3 créditos acumulados"
    ],
    "credits_per_day": 1,
    "total_days": 30,
    "total_credits": 30,
    "max_credits_balance": 3
}

PLANO_GRATUITO = {
    "id": "gratuito",
    "name": "Plano Gratuito",
    "price": 0,
    "credits": 3,
    "description": "3 créditos iniciais para testes",
    "max_credits_balance": 3
}


# ==============================================
# ROTAS (DEPOIS DO router)
# ==============================================

@router.get("/plans")
async def get_plans():
    """Retorna os planos disponíveis"""
    try:
        logger.info("👀 Planos consultados")
        return {
            "success": True,
            "plans": {
                "gratuito": PLANO_GRATUITO,
                "premium_mensal": PLANO_PREMIUM
            },
            "public_key": getattr(mp_service, 'public_key', None),
            "max_credits_balance": 3,
            "max_files_per_batch": 3
        }
    except Exception as e:
        logger.error(f"❌ Erro ao listar planos: {e}")
        return {
            "success": False,
            "error": str(e),
            "plans": {
                "gratuito": PLANO_GRATUITO,
                "premium_mensal": PLANO_PREMIUM
            }
        }


@router.get("/premium/subscribers-count")
async def get_premium_subscribers_count(db: Session = Depends(get_db)):
    """Retorna a quantidade de assinantes ativos do plano premium"""
    try:
        today = date.today()
        stmt = select(func.count(User.id)).where(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at >= today
        )
        active_subscribers = db.execute(stmt).scalar() or 0
        
        BATCH_LIMIT = 100
        vagas_restantes = max(0, BATCH_LIMIT - active_subscribers)
        
        return {
            "success": True,
            "subscribers_count": active_subscribers,
            "batch_limit": BATCH_LIMIT,
            "remaining_slots": vagas_restantes,
            "is_promotional_active": vagas_restantes > 0,
            "message": f"🔥 {vagas_restantes} vagas restantes!" if vagas_restantes > 0 else "⚠️ Lote promocional esgotado!"
        }
    except Exception as e:
        logger.error(f"❌ Erro ao contar assinantes: {e}")
        return {"success": False, "error": str(e), "subscribers_count": 0, "remaining_slots": 0}


@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna saldo de créditos e status premium do usuário"""
    try:
        stmt = select(User).where(User.id == current_user.id)
        user = db.execute(stmt).scalar_one_or_none()
        
        if not user:
            return {"success": False, "error": "Usuário não encontrado", "credits": 0, "max_credits_balance": 3}
        
        hoje = date.today()
        credit_stmt = select(DailyCreditLog).where(
            DailyCreditLog.user_id == user.id,
            DailyCreditLog.date == hoje
        )
        received_today = db.execute(credit_stmt).first() is not None
        
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        days_remaining = 0
        if is_premium and user.premium_expires_at:
            days_remaining = max(0, (user.premium_expires_at - date.today()).days)
        
        current_credits = user.credits or 0
        max_credits_balance = 3
        
        return {
            "success": True,
            "credits": current_credits,
            "total_purchased": user.total_purchased or 0,
            "max_credits_balance": max_credits_balance,
            "can_receive_more": current_credits < max_credits_balance,
            "plan": {
                "type": str(user.plan),
                "is_premium": is_premium,
                "premium_expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
                "days_remaining": days_remaining,
                "credits_per_day": 1 if is_premium else 0,
                "received_today": received_today,
                "total_days": 30
            }
        }
    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        return {"success": False, "error": str(e), "credits": 0, "max_credits_balance": 3}


@router.post("/create-pix")
async def create_pix_payment(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria um pagamento PIX para o plano premium de R$97"""
    try:
        today_date = date.today()
        subscribers_count = db.execute(
            select(func.count(User.id)).where(
                User.plan == UserPlan.PREMIUM_MENSAL,
                User.premium_expires_at >= today_date
            )
        ).scalar() or 0
        
        BATCH_LIMIT = 100
        vaga_numero = subscribers_count + 1
        vagas_restantes = BATCH_LIMIT - subscribers_count
        
        if vagas_restantes > 0:
            titulo_plano = f"Plano Premium - Vaga #{vaga_numero} de {BATCH_LIMIT}"
            mensagem_promocional = f"🔥 Vaga #{vaga_numero} de {BATCH_LIMIT}!"
        else:
            titulo_plano = "Plano Premium Mensal"
            mensagem_promocional = "Plano Premium - Assinatura Mensal"
        
        logger.info(f"💰 Iniciando pagamento PIX para {current_user.email}")
        
        alert_payment_pending(user_email=current_user.email, amount=97.00, method="pix")
        
        # Modo de teste
        if not mp_service.access_token:
            return await _create_test_payment(current_user, db, vaga_numero, vagas_restantes, titulo_plano)
        
        # Pagamento real (implementar com Mercado Pago)
        mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
        
        payment = crud.create_payment_record(
            db=db,
            user_id=current_user.id,
            mp_id=mock_payment_id,
            amount=97.00,
            credits=30,
            payment_method="pix",
            qr_code=None,
            qr_code_base64=None,
            description=titulo_plano,
            status="pending",
            payment_metadata={
                "plan_id": "premium_mensal",
                "vaga_numero": vaga_numero,
                "vagas_restantes": vagas_restantes
            }
        )
        
        return {
            "success": True,
            "payment_id": payment.id,
            "status": "pending",
            "plan": {
                "name": sanitize_input(titulo_plano),
                "credits_per_day": 1,
                "total_days": 30,
                "vaga_numero": vaga_numero,
                "vagas_restantes": vagas_restantes
            },
            "amount": 97.00,
            "promotional_message": sanitize_input(mensagem_promocional)
        }
        
    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        return {"success": False, "error": "Erro ao criar pagamento"}


async def _create_test_payment(current_user: User, db: Session, vaga_numero: int, vagas_restantes: int, titulo_plano: str):
    """Cria pagamento de teste (modo desenvolvimento)"""
    logger.info(f"🧪 Modo teste - ativando premium para {current_user.email}")
    
    mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
    
    payment = crud.create_payment_record(
        db=db,
        user_id=current_user.id,
        mp_id=mock_payment_id,
        amount=97.00,
        credits=30,
        payment_method="pix",
        qr_code=None,
        qr_code_base64=None,
        description=titulo_plano,
        status="approved",
        payment_metadata={"plan_id": "premium_mensal", "test_mode": True}
    )
    
    expires_at = date.today() + timedelta(days=30)
    
    stmt = select(User).where(User.id == current_user.id)
    user = db.execute(stmt).scalar_one()
    
    user.plan = UserPlan.PREMIUM_MENSAL
    user.premium_activated_at = datetime.now()
    user.premium_expires_at = expires_at
    user.total_purchased = (user.total_purchased or 0) + 30
    
    db.commit()
    
    return {
        "success": True,
        "payment_id": payment.id,
        "status": "approved",
        "plan": {"name": titulo_plano, "credits_per_day": 1, "total_days": 30},
        "amount": 97.00,
        "test_mode": True
    }


@router.post("/webhook")
async def mercadopago_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook para receber notificações do Mercado Pago"""
    try:
        data = await request.json()
        logger.info(f"🔔 Webhook recebido")
        return {"status": "received"}
    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        return {"status": "error"}


@router.get("/status/{payment_id}")
async def check_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verifica status de um pagamento específico"""
    try:
        stmt = select(Payment).where(Payment.id == payment_id)
        payment = db.execute(stmt).scalar_one_or_none()
        
        if not payment:
            return {"success": False, "error": "Pagamento não encontrado"}
        
        if payment.user_id != current_user.id and not current_user.is_admin:
            return {"success": False, "error": "Acesso negado"}
        
        return {
            "success": True,
            "payment": {
                "id": payment.id,
                "status": payment.status,
                "amount": payment.amount,
                "credits": payment.credits,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
                "approved_at": payment.approved_at.isoformat() if payment.approved_at else None
            }
        }
    except Exception as e:
        logger.error(f"Erro: {e}")
        return {"success": False, "error": str(e)}


@router.get("/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verifica se usuário tem créditos para realizar análise"""
    try:
        stmt = select(User).where(User.id == current_user.id)
        user = db.execute(stmt).scalar_one_or_none()
        
        if not user:
            return {"success": False, "has_credits": False, "credits": 0}
        
        if user.is_admin:
            return {"success": True, "has_credits": True, "credits": float('inf'), "is_admin": True}
        
        return {
            "success": True,
            "has_credits": user.credits > 0,
            "credits": user.credits or 0,
            "required": 1,
            "is_premium": user.plan == UserPlan.PREMIUM_MENSAL,
            "max_credits_balance": 3
        }
    except Exception as e:
        return {"success": False, "has_credits": False, "credits": 0}


@router.get("/success")
async def payment_success():
    return RedirectResponse(url="/dashboard?payment=success")


@router.get("/failure")
async def payment_failure():
    return RedirectResponse(url="/dashboard?payment=failure")


@router.get("/pending")
async def payment_pending():
    return RedirectResponse(url="/dashboard?payment=pending")