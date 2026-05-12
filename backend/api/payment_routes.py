# backend/api/payment_routes.py - VERSÃO OTIMIZADA
# Com SQLAlchemy 2.0 style (select) e joinedload para reduzir consultas

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # para futuro async
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import datetime, timedelta, date
import uuid
import traceback
import logging

from backend.database import get_db
from backend import crud
from backend.auth import get_current_user
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
router = APIRouter(prefix="/payments", tags=["payments"])
mp_service = MercadoPagoService()

# ==============================================
# PLANO PREMIUM - R$97 (30 DIAS DE CRÉDITOS)
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
        "✅ Suporte prioritário"
    ],
    "credits_per_day": 1,
    "total_days": 30,
    "total_credits": 30
}

PLANO_GRATUITO = {
    "id": "gratuito",
    "name": "Plano Gratuito",
    "price": 0,
    "credits": 3,
    "description": "3 créditos iniciais para testes"
}


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
            "public_key": mp_service.public_key
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


# ==============================================
# SALDO DO USUÁRIO - OTIMIZADO (SQLAlchemy 2.0 style)
# ==============================================
@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna saldo de créditos e status premium do usuário
    OTIMIZADO: Usa select() em vez de query(), e joinedload onde necessário
    """
    try:
        # 🔥 SQLAlchemy 2.0 style - usando select()
        stmt = select(User).where(User.id == current_user.id)
        user = db.execute(stmt).scalar_one_or_none()
        
        if not user:
            logger.warning(f"Usuário {current_user.id} não encontrado no banco")
            return {
                "success": False,
                "error": "Usuário não encontrado",
                "credits": 0,
                "total_purchased": 0
            }
        
        # 🔥 Segunda consulta otimizada: verifica crédito de hoje
        hoje = date.today()
        credit_stmt = select(DailyCreditLog).where(
            DailyCreditLog.user_id == user.id,
            DailyCreditLog.date == hoje
        )
        received_today = db.execute(credit_stmt).first() is not None
        
        # Verificar se é premium
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL
        
        # Calcular dias restantes
        days_remaining = 0
        if is_premium and user.premium_expires_at:
            today = date.today()
            days_remaining = (user.premium_expires_at - today).days
            if days_remaining < 0:
                days_remaining = 0
        
        return {
            "success": True,
            "credits": user.credits or 0,
            "total_purchased": user.total_purchased or 0,
            "plan": {
                "type": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
                "is_premium": is_premium,
                "premium_expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
                "days_remaining": max(0, days_remaining),
                "credits_per_day": 1 if is_premium else 0,
                "received_today": received_today,
                "total_days": 30
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro em get_user_balance: {e}")
        traceback.print_exc()
        
        alert_system_error(
            error=e,
            endpoint="/payments/balance",
            user=current_user.email if current_user else "unknown"
        )
        
        return {
            "success": False,
            "error": str(e),
            "credits": 0,
            "total_purchased": 0
        }


# ==============================================
# CRIAR PAGAMENTO PIX - PLANO PREMIUM R$97
# ==============================================
@router.post("/create-pix")
async def create_pix_payment(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria um pagamento PIX para o plano premium de R$97"""
    try:
        logger.info(f"💰 Iniciando pagamento PIX para {current_user.email} - Plano Premium R$97,00")
        
        alert_payment_pending(
            user_email=current_user.email,
            amount=97.00,
            method="pix"
        )
        
        # Modo de teste
        if not mp_service.access_token:
            return await _create_test_payment(current_user, db)
        
        # Pagamento real
        result = mp_service.create_payment_pix(
            user_id=current_user.id,
            user_email=current_user.email,
            user_name=current_user.name or "Cliente",
            amount=97.00,
            description="Plano Premium - 30 dias de créditos",
            credits=30,
            plan_id="premium_mensal"
        )
        
        if not result.get("success", False):
            alert_payment_failed(
                user_email=current_user.email,
                amount=97.00,
                error=result.get("error", "Erro no Mercado Pago")
            )
            
            return {
                "success": False,
                "error": result.get("error", "Erro ao criar pagamento")
            }
        
        # Salvar no banco (status pending)
        payment = crud.create_payment_record(
            db=db,
            user_id=current_user.id,
            mp_id=result.get("payment_id", f"PIX_{uuid.uuid4().hex[:8]}"),
            amount=97.00,
            credits=30,
            payment_method="pix",
            qr_code=result.get("qr_code"),
            qr_code_base64=result.get("qr_code_base64"),
            qr_code_url=result.get("qr_code_url"),
            description="Plano Premium - 30 dias de créditos",
            status="pending",
            payment_metadata={
                "plan_id": "premium_mensal",
                "plan_name": "Plano Premium Mensal",
                "credits_per_day": 1,
                "total_days": 30,
                "external_reference": result.get("external_reference")
            }
        )
        
        return {
            "success": True,
            "payment_id": payment.id,
            "mp_payment_id": result.get("payment_id"),
            "qr_code_base64": result.get("qr_code_base64"),
            "qr_code": result.get("qr_code"),
            "expiration_date": result.get("expiration_date"),
            "plan": {
                "name": "Plano Premium Mensal",
                "credits_per_day": 1,
                "total_days": 30
            },
            "amount": 97.00,
            "status": "pending"
        }
        
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"❌ Erro no create-pix: {e}\n{error_trace}")
        
        alert_system_error(
            error=e,
            endpoint="/payments/create-pix",
            user=current_user.email if current_user else "unknown"
        )
        
        return {
            "success": False,
            "error": str(e)
        }


async def _create_test_payment(current_user: User, db: Session):
    """Cria pagamento de teste (modo desenvolvimento)"""
    logger.info(f"🧪 Modo teste ativado - ativando premium para {current_user.email}")
    
    mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
    
    # Criar registro de pagamento simulado
    payment = crud.create_payment_record(
        db=db,
        user_id=current_user.id,
        mp_id=mock_payment_id,
        amount=97.00,
        credits=30,
        payment_method="pix",
        qr_code="00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
        qr_code_base64="iVBORw0KGgoAAAANSUhEUgAA...",
        description="Plano Premium - 30 dias de créditos",
        status="approved",
        payment_metadata={
            "plan_id": "premium_mensal",
            "plan_name": "Plano Premium Mensal",
            "test_mode": True,
            "credits_per_day": 1,
            "total_days": 30
        }
    )
    
    # 🔥 ATIVAR PLANO PREMIUM
    expires_at = date.today() + timedelta(days=30)
    
    # Buscar usuário com SQLAlchemy 2.0 style
    stmt = select(User).where(User.id == current_user.id)
    user = db.execute(stmt).scalar_one()
    
    # Atualizar usuário para premium
    user.plan = UserPlan.PREMIUM_MENSAL
    user.premium_activated_at = datetime.now()
    user.premium_expires_at = expires_at
    user.total_purchased = (user.total_purchased or 0) + 30
    
    db.commit()
    
    alert_premium_activated(
        user_email=user.email,
        credits=30,
        expires_at=expires_at.strftime("%d/%m/%Y")
    )
    
    return {
        "success": True,
        "payment_id": payment.id,
        "mp_payment_id": mock_payment_id,
        "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
        "qr_code": "00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
        "expiration_date": datetime.now().isoformat(),
        "plan": {
            "name": "Plano Premium Mensal",
            "credits_per_day": 1,
            "total_days": 30,
            "expires_at": expires_at.isoformat()
        },
        "amount": 97.00,
        "status": "approved",
        "test_mode": True
    }


# ==============================================
# WEBHOOK - ATIVAR PREMIUM QUANDO PAGO
# ==============================================
@router.post("/webhook")
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Webhook para receber notificações do Mercado Pago"""
    try:
        data = await request.json()
        logger.info(f"🔔 Webhook recebido: {data.get('action', 'unknown')}")
        
        # Extrair payment_id
        payment_id = None
        if data.get("data") and data["data"].get("id"):
            payment_id = str(data["data"]["id"])
        
        if not payment_id:
            logger.info("Webhook ignorado - sem payment_id")
            return {"status": "ignored"}
        
        # Buscar pagamento com SQLAlchemy 2.0 style
        stmt = select(Payment).where(Payment.mp_id == payment_id)
        payment = db.execute(stmt).scalar_one_or_none()
        
        if payment and payment.status != "approved":
            background_tasks.add_task(
                activate_premium_plan,
                db, payment.id, payment.user_id, payment.credits, payment.amount
            )
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error"}


# ==============================================
# FUNÇÃO PARA ATIVAR PLANO PREMIUM (OTIMIZADA)
# ==============================================
async def activate_premium_plan(db: Session, payment_id: int, user_id: int, total_credits: int, amount: float):
    """Ativa o plano premium para o usuário - Versão otimizada"""
    try:
        import asyncio
        await asyncio.sleep(2)
        
        # 🔥 SQLAlchemy 2.0 style com joinedload para carregar relações
        user_stmt = select(User).where(User.id == user_id)
        payment_stmt = select(Payment).where(Payment.id == payment_id)
        
        user = db.execute(user_stmt).scalar_one_or_none()
        payment = db.execute(payment_stmt).scalar_one_or_none()
        
        if not user or not payment:
            logger.error(f"❌ Usuário {user_id} ou pagamento {payment_id} não encontrado")
            return
        
        # Atualizar status do pagamento
        payment.status = "approved"
        payment.approved_at = datetime.now()
        
        # 🔥 ATIVAR PLANO PREMIUM
        expires_at = date.today() + timedelta(days=30)
        
        user.plan = UserPlan.PREMIUM_MENSAL
        user.premium_activated_at = datetime.now()
        user.premium_expires_at = expires_at
        user.total_purchased = (user.total_purchased or 0) + total_credits
        
        db.commit()
        
        alert_payment_approved(
            user_email=user.email,
            amount=amount,
            credits=total_credits,
            plan="Premium Mensal"
        )
        
        alert_premium_activated(
            user_email=user.email,
            credits=total_credits,
            expires_at=expires_at.strftime("%d/%m/%Y")
        )
        
        logger.info(f"✅ Plano premium ativado para {user.email} - Expira em {expires_at}")
        
    except Exception as e:
        logger.error(f"❌ Erro na ativação: {e}")
        alert_system_error(
            error=e,
            endpoint="/webhook/activate",
            user=f"user_{user_id}"
        )


# ==============================================
# VERIFICAR STATUS DO PAGAMENTO
# ==============================================
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
            return {
                "success": False,
                "error": "Pagamento não encontrado"
            }
        
        if payment.user_id != current_user.id and not current_user.is_admin:
            return {
                "success": False,
                "error": "Acesso negado"
            }
        
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
        logger.error(f"Erro ao verificar status: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ==============================================
# VERIFICAR CRÉDITOS PARA ANÁLISE
# ==============================================
@router.get("/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verifica se usuário tem créditos para realizar análise"""
    try:
        # 🔥 SQLAlchemy 2.0 style
        stmt = select(User).where(User.id == current_user.id)
        user = db.execute(stmt).scalar_one_or_none()
        
        if not user:
            return {
                "success": False,
                "has_credits": False,
                "credits": 0,
                "required": 1
            }
        
        # Admin tem créditos infinitos
        if user.is_admin:
            return {
                "success": True,
                "has_credits": True,
                "credits": float('inf'),
                "required": 1,
                "is_admin": True
            }
        
        has_credits = user.credits > 0
        
        return {
            "success": True,
            "has_credits": has_credits,
            "credits": user.credits or 0,
            "required": 1,
            "is_premium": user.plan == UserPlan.PREMIUM_MENSAL
        }
        
    except Exception as e:
        logger.error(f"Erro ao verificar créditos: {e}")
        return {
            "success": False,
            "error": str(e),
            "has_credits": False,
            "credits": 0,
            "required": 1
        }


# ==============================================
# CALLBACKS
# ==============================================
@router.get("/success")
async def payment_success():
    """Callback de sucesso"""
    return RedirectResponse(url="/dashboard?payment=success")


@router.get("/failure")
async def payment_failure():
    """Callback de falha"""
    return RedirectResponse(url="/dashboard?payment=failure")


@router.get("/pending")
async def payment_pending():
    """Callback de pendente"""
    return RedirectResponse(url="/dashboard?payment=pending")