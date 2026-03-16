# backend/api/payment_routes.py - CORREÇÃO DO ERRO DE SESSÃO
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import json
import uuid
import traceback

from backend.database import get_db
from backend import crud
from backend.security import get_current_user
from backend.models import User, PaymentStatus, UserPlan
from backend.services.payment_service import MercadoPagoService

# Importar funções do sentinel
from backend.observability.sentinel import (
    alert_payment_approved,
    alert_payment_pending,
    alert_payment_failed,
    alert_system_error,
    alert_premium_activated
)

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

# Plano gratuito (para referência)
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
        print("👀 Planos consultados")
        
        return {
            "success": True,
            "plans": {
                "gratuito": PLANO_GRATUITO,
                "premium_mensal": PLANO_PREMIUM
            },
            "public_key": mp_service.public_key
        }
    except Exception as e:
        print(f"❌ Erro ao listar planos: {e}")
        return {
            "success": False,
            "error": str(e),
            "plans": {
                "gratuito": PLANO_GRATUITO,
                "premium_mensal": PLANO_PREMIUM
            }
        }

# ==============================================
# 🔥 SALDO DO USUÁRIO - CORRIGIDO (SEM DB.REFRESH)
# ==============================================
@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna saldo de créditos e status premium do usuário"""
    try:
        # 🔥 CORREÇÃO: NÃO usar db.refresh() - causa erro!
        # db.refresh(current_user)  ← ISSO ESTAVA CAUSANDO O ERRO!
        
        # 🔥 Buscar dados atualizados do banco diretamente
        from backend.models import DailyCreditLog
        from sqlalchemy import select
        
        # Buscar usuário atualizado do banco
        user = db.query(User).filter(User.id == current_user.id).first()
        
        if not user:
            return {
                "success": False,
                "error": "Usuário não encontrado",
                "credits": 0,
                "total_purchased": 0
            }
        
        # Verificar se é premium
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL
        
        # Calcular dias restantes se for premium
        days_remaining = 0
        if is_premium and user.premium_expires_at:
            today = date.today()
            days_remaining = (user.premium_expires_at - today).days
            if days_remaining < 0:
                days_remaining = 0
        
        # Verificar se já recebeu o crédito hoje
        hoje = date.today()
        received_today = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user.id,
            DailyCreditLog.date == hoje
        ).first() is not None
        
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
        # Log do erro para debug
        print(f"❌ Erro em get_user_balance: {e}")
        import traceback
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
    """
    Cria um pagamento PIX para o plano premium de R$97
    """
    try:
        print(f"💰 Iniciando pagamento PIX para {current_user.email} - Plano Premium R$97,00")
        
        # Alertar pagamento pendente
        alert_payment_pending(
            user_email=current_user.email,
            amount=97.00,
            method="pix"
        )
        
        # Verificar se o MP service está configurado
        if not mp_service.access_token:
            # Modo de teste - já aprova automaticamente
            print(f"🧪 Modo teste ativado - ativando premium")
            
            mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
            
            # Criar registro de pagamento simulado
            payment = crud.create_payment_record(
                db=db,
                user_id=current_user.id,
                mp_id=mock_payment_id,
                amount=97.00,
                credits=30,  # Total de créditos do plano
                payment_method="pix",
                qr_code="00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
                qr_code_base64="iVBORw0KGgoAAAANSUhEUgAA...",
                description="Plano Premium - 30 dias de créditos",
                status="approved",  # Já aprovado no modo teste
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
            
            # Buscar usuário atualizado
            user = db.query(User).filter(User.id == current_user.id).first()
            
            # Atualizar usuário para premium
            user.plan = UserPlan.PREMIUM_MENSAL
            user.premium_activated_at = datetime.now()
            user.premium_expires_at = expires_at
            user.total_purchased = (user.total_purchased or 0) + 30
            
            db.commit()
            
            # Alertar ativação do premium
            alert_premium_activated(
                user_email=user.email,
                credits=30,  # Total que vai receber ao longo dos 30 dias
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
        
        # Criar pagamento PIX real (aguardando pagamento)
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
        print(f"❌ Erro no create-pix: {e}")
        
        alert_system_error(
            error=e,
            endpoint="/payments/create-pix",
            user=current_user.email if current_user else "unknown"
        )
        
        return {
            "success": False,
            "error": str(e)
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
    """Webhook para receber notificações do Mercado Pago e ativar premium"""
    try:
        data = await request.json()
        print(f"🔔 Webhook recebido")
        
        # Extrair payment_id
        payment_id = None
        if data.get("data") and data["data"].get("id"):
            payment_id = str(data["data"]["id"])
        
        if not payment_id:
            return {"status": "ignored"}
        
        # Buscar pagamento
        from backend.models import Payment
        payment = db.query(Payment).filter(Payment.mp_id == payment_id).first()
        
        if payment and payment.status != "approved":
            # 🔥 ATIVAR PREMIUM
            background_tasks.add_task(
                activate_premium_plan,
                db, payment.id, payment.user_id, payment.credits, payment.amount
            )
        
        return {"status": "received"}
        
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return {"status": "error"}

# ==============================================
# FUNÇÃO PARA ATIVAR PLANO PREMIUM
# ==============================================
async def activate_premium_plan(db: Session, payment_id: int, user_id: int, total_credits: int, amount: float):
    """Ativa o plano premium para o usuário"""
    try:
        import asyncio
        await asyncio.sleep(2)  # Pequeno delay
        
        # Buscar usuário e pagamento
        from backend.models import User, Payment
        user = db.query(User).filter(User.id == user_id).first()
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        
        if not user or not payment:
            print(f"❌ Usuário ou pagamento não encontrado")
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
        
        # Alertar ativação
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
        
        print(f"✅ Plano premium ativado para {user.email} - Expira em {expires_at}")
        
    except Exception as e:
        print(f"❌ Erro na ativação: {e}")
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
        from backend.models import Payment
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        
        if not payment:
            return {
                "success": False,
                "error": "Pagamento não encontrado"
            }
        
        if payment.user_id != current_user.id:
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
                "created_at": payment.created_at.isoformat() if payment.created_at else None
            }
        }
        
    except Exception as e:
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
        # 🔥 CORREÇÃO: Buscar usuário atualizado do banco
        user = db.query(User).filter(User.id == current_user.id).first()
        
        if not user:
            return {
                "success": False,
                "has_credits": False,
                "credits": 0,
                "required": 1
            }
        
        has_credits = user.credits > 0
        
        return {
            "success": True,
            "has_credits": has_credits,
            "credits": user.credits or 0,
            "required": 1
        }
        
    except Exception as e:
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