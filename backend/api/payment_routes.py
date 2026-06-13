# backend/api/payment_routes.py - VERSÃO COMPLETA CORRIGIDA
# CORREÇÕES: Lock pessimista + timeout ajustado + validação CPF + imports otimizados

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import uuid
import logging
import re
import html
import asyncio
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import json
from backend.database import get_db, SessionLocal
from backend import crud
from backend.api.auth_routes import get_current_user
from backend.models import User, Payment, DailyCreditLog, UserPlan, Analysis, PromotionControl, PaymentStatus
from backend.services.daily_credits_service import DailyCreditsService
from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display
from backend.services.payment_service import MercadoPagoService, get_mp_service
from backend.observability.sentinel import alert_payment_approved, alert_payment_pending, alert_payment_failed, get_webhook

# 🔥 IMPORTS OTIMIZADOS (movidos para o topo)
import re as regex_module

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# ==============================================
# CONFIGURAÇÕES
# ==============================================

MAX_CREDITS_BALANCE = 3
DAYS_PREMIUM = 30
CREDITS_PER_DAY = 1
INITIAL_FREE_CREDITS = 3
MAX_PAYMENT_ATTEMPTS_PER_DAY = 3
PIX_QR_CODE_EXPIRY_MINUTES = 30
USE_REAL_MERCADO_PAGO = os.getenv("USE_REAL_MERCADO_PAGO", "true").lower() == "true"

# 🔥 CONFIGURAÇÃO DA SIMULAÇÃO (aumentado para evitar race)
SIMULATION_DELAY_SECONDS = int(os.getenv("SIMULATION_DELAY_SECONDS", "8"))

# ==============================================
# MODELOS PYDANTIC
# ==============================================

class CreatePaymentRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano")
    cpf: Optional[str] = Field(None, description="CPF do usuário")
    
    @validator('plan_id')
    def validate_plan_id(cls, v):
        allowed = ['premium_mensal', 'gratuito']
        if v not in allowed:
            raise ValueError(f'Plano inválido. Permitidos: {allowed}')
        return v
    
    @validator('cpf')
    def validate_cpf(cls, v):
        """
        🔥 CORREÇÃO: Validação robusta de CPF
        Se o campo foi enviado, DEVE ter 11 dígitos numéricos após limpeza
        """
        if v is None:
            return v
        
        # Remove caracteres não numéricos
        cpf_clean = regex_module.sub(r'\D', '', v)
        
        # 🔥 CORREÇÃO: String vazia não é aceita se o campo foi enviado
        if not cpf_clean:
            raise ValueError('CPF não pode estar vazio')
        
        if len(cpf_clean) != 11:
            raise ValueError('CPF deve conter exatamente 11 dígitos numéricos')
        
        return cpf_clean


class PixQRCodeResponse(BaseModel):
    success: bool
    qr_code_base64: Optional[str] = None
    qr_code: Optional[str] = None
    status: str
    max_credits_balance: int = MAX_CREDITS_BALANCE
    expires_in: int = PIX_QR_CODE_EXPIRY_MINUTES * 60
    message: str = ""


class PromotionStatusResponse(BaseModel):
    success: bool
    total_slots: int
    used_slots: int
    remaining_slots: int
    promotional_price: float
    regular_price: float
    current_price: float
    is_active: bool
    user_locked_price: Optional[float] = None
    message: str


# ==============================================
# SANITIZAÇÃO
# ==============================================

def sanitize_string(text: str) -> str:
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = regex_module.sub(r'<[^>]*>', '', text)
    text = html.escape(text)
    text = regex_module.sub(r'[<>\"\'\/\\;`]', '', text)
    text = regex_module.sub(r'(?i)javascript\s*:', '', text)
    text = regex_module.sub(r'(?i)on\w+\s*=', '', text)
    return text[:500]


def sanitize_response(data: Any) -> Any:
    if isinstance(data, dict):
        return {sanitize_string(k): sanitize_response(v) for k, v in data.items()}
    elif isinstance(data, str):
        return sanitize_string(data)
    elif isinstance(data, list):
        return [sanitize_response(item) for item in data]
    elif isinstance(data, float):
        return round(data, 2)
    return data


def validate_payment_id(payment_id: int) -> bool:
    return isinstance(payment_id, int) and payment_id > 0


# ==============================================
# SERVIÇOS E FUNÇÕES AUXILIARES
# ==============================================

daily_credits_service = DailyCreditsService()
mp_service = get_mp_service() or MercadoPagoService()
webhook = get_webhook()


def get_or_create_promotion(db: Session) -> PromotionControl:
    promo = db.query(PromotionControl).first()
    if not promo:
        promo = PromotionControl()
        db.add(promo)
        db.commit()
        db.refresh(promo)
        logger.info("✅ Promoção Bronze inicializada (100 vagas a R$ 97,00)")
    return promo


def use_promotional_slot_atomic(db: Session, promo_id: int) -> bool:
    """
    🔥 CORREÇÃO: Usa pessimistic locking para evitar race condition
    Retorna True se conseguiu usar uma vaga, False se não há vagas
    """
    from sqlalchemy import select
    
    # 🔥 Lock pessimista: bloqueia a linha para leitura/atualização
    promo = db.query(PromotionControl).filter(
        PromotionControl.id == promo_id
    ).with_for_update().first()
    
    if not promo or not promo.has_available_slots():
        return False
    
    promo.use_slot()
    db.commit()
    logger.info(f"🎟️ Vaga promocional utilizada atomicamente! Restam: {promo.get_remaining_slots()}")
    return True


def check_payment_rate_limit(user_id: int, db: Session) -> bool:
    today = date.today()
    payments_today = db.query(Payment).filter(
        Payment.user_id == user_id,
        func.date(Payment.created_at) == today,
        Payment.status == "pending"
    ).count()
    if payments_today >= MAX_PAYMENT_ATTEMPTS_PER_DAY:
        logger.warning(f"⚠️ Rate limit excedido para usuário {user_id}")
        return False
    return True


def initialize_new_user_credits(user_id: int, db: Session) -> Dict:
    try:
        user = crud.get_user_by_id(db, user_id)
        if not user:
            return {"success": False, "error": "Usuário não encontrado"}
        
        if (user.credits is None or user.credits == 0) and not user.is_admin:
            user.credits = INITIAL_FREE_CREDITS
            user.total_purchased = (user.total_purchased or 0) + INITIAL_FREE_CREDITS
            
            log = DailyCreditLog(
                user_id=user.id,
                credits_added=INITIAL_FREE_CREDITS,
                date=date.today(),
                total_after=user.credits,
                source="initial_bonus"
            )
            db.add(log)
            db.commit()
            
            logger.info(f"🎉 Usuário ID {user.id} ganhou {INITIAL_FREE_CREDITS} créditos gratuitos!")
            
            return {
                "success": True,
                "credits_added": INITIAL_FREE_CREDITS,
                "current_credits": user.credits,
                "message": f"🎉 Boas-vindas! Você ganhou {INITIAL_FREE_CREDITS} créditos grátis!"
            }
        
        return {"success": False, "message": "Usuário já possui créditos"}
        
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar créditos: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}


async def simulate_payment_approval(payment_id: int, user_id: int):
    """
    Simula aprovação de pagamento (apenas para modo simulado)
    🔥 CORREÇÃO: Tempo aumentado para SIMULATION_DELAY_SECONDS (padrão 8 segundos)
    """
    await asyncio.sleep(SIMULATION_DELAY_SECONDS)
    
    db = SessionLocal()
    
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if payment and payment.status == "pending":
            user = crud.get_user_by_id(db, user_id)
            if user:
                user.plan = UserPlan.PREMIUM_MENSAL
                user.premium_activated_at = datetime.now()
                user.premium_expires_at = date.today() + timedelta(days=DAYS_PREMIUM)
                
                price_type = payment.payment_metadata.get("price_type", "regular")
                was_promotional = price_type == "promotional"
                
                if was_promotional and not user.promotional_price_locked:
                    promo = get_or_create_promotion(db)
                    if promo.has_available_slots():
                        # 🔥 Usa lock pessimista
                        use_promotional_slot_atomic(db, promo.id)
                        user.promotional_price_locked = True
                        user.promotional_price = payment.amount
                        user.purchased_at_promotion = datetime.now()
                        logger.info(f"🎟️ Vaga promocional utilizada!")
                
                payment.status = "approved"
                payment.approved_at = datetime.now()
                db.commit()
                logger.info(f"✅ Pagamento SIMULADO {payment_id} APROVADO após {SIMULATION_DELAY_SECONDS}s!")
    except Exception as e:
        logger.error(f"❌ Erro na simulação: {e}")
        db.rollback()
    finally:
        db.close()


async def create_simulated_pix_payment(
    user: User, db: Session, background_tasks: BackgroundTasks,
    promo: PromotionControl, price: float, price_type: str
) -> Dict:
    payment_uuid = str(uuid.uuid4())
    pix_code = f"00020126360014BR.GOV.BCB.PIX0114{payment_uuid[:14]}5204000053039865404{int(price)}.005802BR5913AutoAnalytics6008SaoPaulo62070503***6304E2F3"
    
    payment = Payment(
        user_id=user.id,
        mp_id=f"SIM_{payment_uuid[:8].upper()}",
        amount=price,
        credits=DAYS_PREMIUM,
        payment_method="pix",
        status="pending",
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(minutes=15),
        description=f"Plano Bronze - SIMULADO",
        payment_metadata={
            "plan_id": "premium_mensal",
            "days": DAYS_PREMIUM,
            "price_type": price_type,
            "real_payment": False,
            "simulated": True
        }
    )
    
    db.add(payment)
    db.commit()
    db.refresh(payment)
    
    logger.info(f"🔄 Pagamento SIMULADO criado: ID {payment.id} (aprovação em {SIMULATION_DELAY_SECONDS}s)")
    background_tasks.add_task(simulate_payment_approval, payment.id, user.id)
    
    return sanitize_response({
        "success": True,
        "payment_id": payment.id,
        "status": "pending",
        "amount": price,
        "price_type": price_type,
        "qr_code": pix_code,
        "expires_in": 15 * 60,
        "simulated": True,
        "simulation_delay": SIMULATION_DELAY_SECONDS
    })


# ==============================================
# 🔥 ROTAS (mantidas iguais, apenas chamam as funções corrigidas)
# ==============================================

@router.get("/promotion-status", response_model=PromotionStatusResponse)
async def get_promotion_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    promo = get_or_create_promotion(db)
    return PromotionStatusResponse(
        success=True,
        total_slots=promo.total_slots,
        used_slots=promo.used_slots,
        remaining_slots=promo.get_remaining_slots(),
        promotional_price=float(promo.promotional_price),
        regular_price=float(promo.regular_price),
        current_price=float(promo.get_current_price()),
        is_active=promo.has_available_slots(),
        user_locked_price=current_user.promotional_price if current_user.promotional_price_locked else None,
        message=f"🔥 {promo.get_remaining_slots()} vagas restantes!" if promo.has_available_slots() else "⛔ Promoção esgotada!"
    )


@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "credits": 0, "error": "Usuário não encontrado"})
    
    is_new_user = (user.credits is None or user.credits == 0) and not user.is_admin
    if is_new_user:
        initialize_new_user_credits(user.id, db)
        db.refresh(user)
    
    is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
    days_left = max(0, (user.premium_expires_at - date.today()).days) if is_premium and user.premium_expires_at else 0
    
    return sanitize_response({
        "success": True,
        "credits": user.credits or 0,
        "credits_display": crud.get_credits_display(user),
        "is_admin": user.is_admin,
        "max_credits_balance": MAX_CREDITS_BALANCE,
        "plan": {
            "type": str(user.plan),
            "is_premium": is_premium,
            "days_left": days_left
        }
    })


@router.post("/create-pix")
async def create_pix_payment(
    background_tasks: BackgroundTasks,
    request_data: CreatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Administradores têm acesso ilimitado")
    
    if not check_payment_rate_limit(user.id, db):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Muitas tentativas. Aguarde até amanhã.")
    
    if user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium():
        raise HTTPException(status_code=400, detail="Você já possui plano premium ativo!")
    
    promo = get_or_create_promotion(db)
    
    if user.promotional_price_locked and user.promotional_price:
        price = user.promotional_price
        price_type = "locked_promotional"
    else:
        price = promo.get_current_price()
        price_type = "promotional" if promo.has_available_slots() else "regular"
    
    if USE_REAL_MERCADO_PAGO and mp_service and mp_service.sdk:
        try:
            result = mp_service.create_real_pix_payment(
                plan_id="premium_mensal",
                user_email=user.email,
                user_id=user.id,
                user_name=user.name or "Cliente",
                price=price,
                user_cpf=request_data.cpf,
                db=db
            )
            
            if result.get("requires_cpf"):
                raise HTTPException(status_code=400, detail=result.get("error"))
            
            if result.get("success"):
                payment = Payment(
                    user_id=user.id,
                    mp_id=result["payment_id"],
                    amount=result["amount"],
                    credits=result["credits"],
                    payment_method="pix",
                    status=result["status"],
                    qr_code=result.get("qr_code"),
                    qr_code_base64=result.get("qr_code_base64"),
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(minutes=PIX_QR_CODE_EXPIRY_MINUTES),
                    description=f"Plano Bronze - {price_type}",
                    payment_metadata={
                        "price_type": price_type,
                        "real_payment": True,
                        "mp_payment_id": result["payment_id"],
                        "cpf_provided": bool(request_data.cpf)
                    }
                )
                db.add(payment)
                db.commit()
                db.refresh(payment)
                
                alert_payment_pending(user.email, price)
                
                return sanitize_response({
                    "success": True,
                    "payment_id": payment.id,
                    "status": result["status"],
                    "amount": price,
                    "price_type": price_type,
                    "qr_code_base64": result.get("qr_code_base64"),
                    "qr_code": result.get("qr_code"),
                    "expires_in": PIX_QR_CODE_EXPIRY_MINUTES * 60,
                    "message": f"💰 Pagamento PIX gerado! Valor: R$ {price:.2f}"
                })
            else:
                raise HTTPException(status_code=400, detail=result.get("error"))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Exceção: {e}")
            if os.getenv("MP_FALLBACK_SIMULATED", "false").lower() == "true":
                return await create_simulated_pix_payment(user, db, background_tasks, promo, price, price_type)
            raise HTTPException(status_code=400, detail=str(e))
    else:
        return await create_simulated_pix_payment(user, db, background_tasks, promo, price, price_type)


@router.get("/pix-qrcode/{payment_id}", response_model=PixQRCodeResponse)
async def get_pix_qrcode(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not validate_payment_id(payment_id):
        raise HTTPException(status_code=400, detail="ID inválido")
    
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        return PixQRCodeResponse(success=False, status="not_found", message="Pagamento não encontrado")
    
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if payment.expires_at and payment.expires_at < datetime.now():
        return PixQRCodeResponse(success=False, status="expired", message="QR Code expirado", expires_in=0)
    
    return PixQRCodeResponse(
        success=True,
        qr_code_base64=payment.qr_code_base64,
        qr_code=payment.qr_code or payment.mp_id,
        status=payment.status,
        expires_in=max(0, int((payment.expires_at - datetime.now()).total_seconds())) if payment.expires_at else PIX_QR_CODE_EXPIRY_MINUTES * 60
    )


@router.get("/plans")
async def get_plans(db: Session = Depends(get_db)):
    promo = get_or_create_promotion(db)
    
    return sanitize_response({
        "success": True,
        "plans": {
            "gratuito": {
                "id": "gratuito",
                "name": "Plano Gratuito",
                "price": 0,
                "credits": INITIAL_FREE_CREDITS,
                "description": f"{INITIAL_FREE_CREDITS} créditos iniciais",
                "max_credits_balance": MAX_CREDITS_BALANCE
            },
            "premium_mensal": {
                "id": "premium_mensal",
                "name": "Plano Bronze",
                "price": promo.get_current_price(),
                "regular_price": promo.regular_price,
                "promotional_price": promo.promotional_price,
                "description": f"1 crédito por dia durante {DAYS_PREMIUM} dias",
                "credits_per_day": CREDITS_PER_DAY,
                "total_days": DAYS_PREMIUM,
                "max_credits_balance": MAX_CREDITS_BALANCE,
                "remaining_slots": promo.get_remaining_slots(),
                "total_slots": promo.total_slots
            }
        },
        "real_payment_enabled": USE_REAL_MERCADO_PAGO and mp_service and mp_service.sdk is not None
    })


@router.get("/status/{payment_id}")
async def check_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not validate_payment_id(payment_id):
        raise HTTPException(status_code=400, detail="ID inválido")
    
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        return sanitize_response({"success": False, "error": "Pagamento não encontrado"})
    
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return sanitize_response({
        "success": True,
        "payment": {
            "id": payment.id,
            "status": payment.status,
            "amount": float(payment.amount),
            "credits": payment.credits,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
            "approved_at": payment.approved_at.isoformat() if payment.approved_at else None
        }
    })


@router.post("/cancel/{payment_id}")
async def cancel_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not validate_payment_id(payment_id):
        raise HTTPException(status_code=400, detail="ID inválido")
    
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if payment.status != "pending":
        raise HTTPException(status_code=400, detail="Apenas pagamentos pendentes podem ser cancelados")
    
    payment.status = "cancelled"
    db.commit()
    
    return sanitize_response({"success": True, "message": "Pagamento cancelado"})


@router.get("/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "has_credits": False})
    
    if user.is_admin:
        return sanitize_response({"success": True, "has_credits": True, "credits_display": "∞"})
    
    current_credits = user.credits or 0
    return sanitize_response({
        "success": True,
        "has_credits": current_credits > 0,
        "credits": current_credits,
        "max_credits_balance": MAX_CREDITS_BALANCE
    })


@router.post("/consume")
async def consume_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "error": "Usuário não encontrado"})
    
    if user.is_admin:
        return sanitize_response({"success": True, "credits_consumed": 0, "message": "Admin não consome créditos"})
    
    success = consume_analysis_credit(user, db, 1)
    if success:
        db.refresh(user)
        return sanitize_response({"success": True, "credits_consumed": 1, "credits_remaining": user.credits})
    else:
        return sanitize_response({"success": False, "error": "Créditos insuficientes"})


@router.post("/premium/check-daily")
async def check_daily_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "error": "Usuário não encontrado"})
    
    is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
    if not is_premium:
        return sanitize_response({"success": False, "message": "Recurso exclusivo para premium"})
    
    result = daily_credits_service.check_and_add_daily_credit(db, current_user.id)
    return sanitize_response(result)


@router.get("/subscription-status")
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "error": "Usuário não encontrado"})
    
    if user.is_admin:
        return sanitize_response({
            "success": True, "has_subscription": True, "is_admin": True,
            "days_left": 999, "is_active": True, "message": "👑 Administrador"
        })
    
    is_premium = user.plan == UserPlan.PREMIUM_MENSAL
    if not is_premium or not user.premium_expires_at:
        return sanitize_response({
            "success": True, "has_subscription": False, "is_premium": False,
            "message": "Você não possui um plano premium ativo"
        })
    
    days_left = (user.premium_expires_at - date.today()).days
    is_expired = days_left <= 0
    is_active = not is_expired
    
    if is_expired:
        user.plan = UserPlan.BASICO
        db.commit()
        logger.info(f"⏰ Plano expirado: {user.email}")
    
    return sanitize_response({
        "success": True,
        "has_subscription": is_active,
        "is_premium": is_active,
        "days_left": max(0, days_left),
        "is_active": is_active,
        "expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
        "activated_at": user.premium_activated_at.isoformat() if user.premium_activated_at else None,
        "message": "✅ Plano ativo" if is_active else "❌ Plano expirado"
    })


# ==============================================
# 🔥 WEBHOOK COM SESSÃO PRÓPRIA E IDEMPOTÊNCIA
# ==============================================

@router.post("/webhook")
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Webhook para receber notificações REAIS do Mercado Pago
    🔥 CORRIGIDO: NÃO recebe db - a background task cria sua própria sessão!
    """
    try:
        body = await request.body()
        if not body:
            logger.warning("⚠️ Webhook recebido sem corpo")
            return {"status": "ignored"}
        
        try:
            data = json.loads(body)
            logger.info(f"🔔 Webhook JSON recebido")
        except json.JSONDecodeError:
            text_body = body.decode('utf-8')
            match = regex_module.search(r'id=(\d+)', text_body)
            if match:
                payment_id = match.group(1)
                background_tasks.add_task(process_payment_webhook, payment_id)
            return {"status": "received"}
        
        payment_id = data.get("data", {}).get("id") or data.get("id")
        if payment_id:
            background_tasks.add_task(process_payment_webhook, str(payment_id))
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error"}


async def process_payment_webhook(payment_id: str):
    """
    Processa notificação de pagamento do Mercado Pago
    🔥 CORRIGIDO: Cria sua PRÓPRIA sessão do banco!
    🔥 IDEMPOTENTE: Verifica se já foi processado antes
    🔥 ATOMICIDADE: Usa lock pessimista para vagas promocionais
    """
    await asyncio.sleep(2)
    
    db = SessionLocal()
    
    try:
        # 🔥 1. Buscar pagamento no banco
        db_payment = db.query(Payment).filter(Payment.mp_id == str(payment_id)).first()
        
        if not db_payment:
            logger.warning(f"⚠️ Pagamento {payment_id} não encontrado no banco")
            return
        
        # 🔥 2. IDEMPOTÊNCIA: Se já foi aprovado, NÃO processar novamente!
        if db_payment.status == PaymentStatus.APPROVED:
            logger.info(f"✅ Pagamento {payment_id} já estava aprovado. Ignorando webhook duplicado.")
            return
        
        # 🔥 3. Se não está pendente, também ignorar
        if db_payment.status != PaymentStatus.PENDING:
            logger.info(f"ℹ️ Pagamento {payment_id} não está pendente (status: {db_payment.status}). Ignorando.")
            return
        
        # Consultar status no Mercado Pago
        payment_info = mp_service.get_payment_status_real(payment_id)
        
        if not payment_info.get("success"):
            logger.error(f"❌ Não foi possível consultar pagamento {payment_id}")
            return
        
        status = payment_info.get("status")
        
        if status == "approved":
            # Atualizar pagamento
            db_payment.status = PaymentStatus.APPROVED
            db_payment.approved_at = datetime.now()
            
            user = crud.get_user_by_id(db, db_payment.user_id)
            
            if user:
                # 🔥 4. Verificar se usuário já é premium (evita duplicação)
                if user.is_premium():
                    logger.info(f"⚠️ Usuário {user.email} já era premium. Pulando ativação duplicada.")
                else:
                    # Ativar premium
                    user.plan = UserPlan.PREMIUM_MENSAL
                    user.premium_activated_at = datetime.now()
                    user.premium_expires_at = date.today() + timedelta(days=DAYS_PREMIUM)
                    
                    # Adicionar crédito inicial (apenas 1)
                    user.credits = (user.credits or 0) + 1
                    
                    logger.info(f"✅ Premium ativado para {user.email}")
                
                # 🔥 5. Promoção com LOCK PESSIMISTA (atomicidade)
                price_type = db_payment.payment_metadata.get("price_type", "regular")
                was_promotional = price_type == "promotional"
                
                if was_promotional and not user.promotional_price_locked:
                    promo = get_or_create_promotion(db)
                    # 🔥 Lock pessimista para evitar race condition
                    if use_promotional_slot_atomic(db, promo.id):
                        user.promotional_price_locked = True
                        user.promotional_price = db_payment.amount
                        user.purchased_at_promotion = datetime.now()
                        logger.info(f"🎟️ Vaga promocional utilizada atomicamente!")
                
                db.commit()
                
                alert_payment_approved(user.email, db_payment.amount)
            else:
                logger.error(f"❌ Usuário não encontrado para pagamento {payment_id}")
        
        elif status == "rejected":
            db_payment.status = PaymentStatus.REJECTED
            db.commit()
            logger.warning(f"⚠️ Pagamento {payment_id} REJEITADO")
            alert_payment_failed(db_payment.user_id, db_payment.amount)
        
        elif status == "cancelled":
            db_payment.status = PaymentStatus.CANCELLED
            db.commit()
            logger.info(f"ℹ️ Pagamento {payment_id} CANCELADO")
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar webhook: {e}")
        db.rollback()
    finally:
        db.close()


print("✅ payment_routes.py carregado - Webhook com sessão própria + idempotência + lock pessimista")