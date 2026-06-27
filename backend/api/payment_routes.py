# backend/api/payment_routes.py - VERSÃO COMPLETA CORRIGIDA
"""
ROTAS DE PAGAMENTO - SISTEMA DE PREÇO FUNDADOR VITALÍCIO
- 100 primeiros compradores pagam R$ 97,00 (vitalício)
- Demais compradores pagam R$ 149,90
- Usuários que compraram na promoção mantêm o preço vitalício para sempre
"""

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
from backend.services.credits_consumer import (
    can_perform_analysis, 
    consume_analysis_credit, 
    get_credits_display,
    _is_premium_user,
    _get_plan_value
)
from backend.services.payment_service import MercadoPagoService, get_mp_service
from backend.observability.sentinel import alert_payment_approved, alert_payment_pending, alert_payment_failed, get_webhook

# 🔥 CONSTANTES SINCRONIZADAS COM CRUD.PY
from backend.crud import MAX_CREDITS_PREMIUM, INITIAL_FREE_CREDITS, _now_brasil, _today_brasil

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# ==============================================
# CONFIGURAÇÕES
# ==============================================

DAYS_PREMIUM = 30
CREDITS_PER_DAY = 1
MAX_PAYMENT_ATTEMPTS_PER_DAY = 3
PIX_QR_CODE_EXPIRY_MINUTES = 30
USE_REAL_MERCADO_PAGO = os.getenv("USE_REAL_MERCADO_PAGO", "true").lower() == "true"
SIMULATION_DELAY_SECONDS = int(os.getenv("SIMULATION_DELAY_SECONDS", "8"))

# 🔥 PREÇOS (SINCRONIZADOS COM PROMOTION CONTROL)
PROMOTIONAL_PRICE = 97.00  # Preço de fundador (vitalício)
REGULAR_PRICE = 149.90      # Preço cheio
TOTAL_PROMOTIONAL_SLOTS = 100  # 100 primeiros compradores

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
        if v is None:
            return v
        
        cpf_clean = re.sub(r'\D', '', v)
        
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
    max_credits_balance: int = MAX_CREDITS_PREMIUM
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
    is_vitalicio: bool = True
    message: str


# ==============================================
# SANITIZAÇÃO
# ==============================================

def sanitize_string(text: str) -> str:
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'<[^>]*>', '', text)
    text = html.escape(text)
    text = re.sub(r'[<>\"\'\/\\;`]', '', text)
    text = re.sub(r'(?i)javascript\s*:', '', text)
    text = re.sub(r'(?i)on\w+\s*=', '', text)
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
    """Busca ou cria a promoção com valores padrão"""
    promo = db.query(PromotionControl).first()
    if not promo:
        promo = PromotionControl(
            total_slots=TOTAL_PROMOTIONAL_SLOTS,
            used_slots=0,
            promotional_price=PROMOTIONAL_PRICE,
            regular_price=REGULAR_PRICE,
            is_active=True
        )
        db.add(promo)
        crud.safe_commit(db, "Erro ao criar promoção")
        db.refresh(promo)
        logger.info(f"✅ Promoção de fundador criada: {TOTAL_PROMOTIONAL_SLOTS} vagas a R$ {PROMOTIONAL_PRICE}")
    return promo


def use_promotional_slot_atomic(db: Session, promo_id: int) -> bool:
    """
    🔥 Usa pessimistic locking para evitar race condition
    Retorna True se conseguiu usar uma vaga
    """
    promo = db.query(PromotionControl).filter(
        PromotionControl.id == promo_id
    ).with_for_update().first()
    
    if not promo or not promo.has_available_slots():
        return False
    
    promo.use_slot()
    crud.safe_commit(db, "Erro ao usar vaga promocional")
    
    remaining = promo.get_remaining_slots()
    logger.info(f"🎟️ Vaga de fundador utilizada! Restam: {remaining}/{TOTAL_PROMOTIONAL_SLOTS}")
    return True


def get_user_price(user: User, db: Session) -> tuple:
    """
    🔥 DETERMINA O PREÇO CORRETO PARA O USUÁRIO
    
    RETORNA: (price, price_type, was_promotional)
    
    Regras:
    1. Se usuário já tem preço vitalício (promotional_price_locked=True) -> usa esse preço
    2. Se ainda tem vagas promocionais -> R$ 97,00 (fundador)
    3. Se acabaram as vagas -> R$ 149,90 (preço cheio)
    """
    
    # 🔥 REGRA 1: Usuário já comprou na promoção - preço vitalício garantido
    if user.promotional_price_locked and user.promotional_price:
        logger.info(f"💰 Usuário {user.email} tem preço vitalício: R$ {user.promotional_price}")
        return (user.promotional_price, "locked_promotional", True)
    
    # 🔥 REGRA 2: Verificar se ainda tem vagas promocionais
    promo = get_or_create_promotion(db)
    
    if promo.has_available_slots():
        # Ainda tem vagas - preço de fundador R$ 97,00
        price = PROMOTIONAL_PRICE
        price_type = "promotional"
        was_promotional = True
        logger.info(f"💰 Usuário {user.email} - PREÇO FUNDADOR: R$ {price} (vaga {promo.used_slots + 1}/{TOTAL_PROMOTIONAL_SLOTS})")
    else:
        # Acabaram as vagas - preço cheio R$ 149,90
        price = REGULAR_PRICE
        price_type = "regular"
        was_promotional = False
        logger.info(f"💰 Usuário {user.email} - PREÇO CHEIO: R$ {price} (promoção esgotada)")
    
    return (price, price_type, was_promotional)


def check_payment_rate_limit(user_id: int, db: Session) -> bool:
    """Verifica limite de tentativas de pagamento por dia"""
    today = _today_brasil()
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
    """Inicializa créditos para novo usuário usando CRUD"""
    try:
        user = crud.get_user_by_id(db, user_id)
        if not user:
            return {"success": False, "error": "Usuário não encontrado"}
        
        if (user.credits is None or user.credits == 0) and not user.is_admin:
            success = crud.add_credits(
                db, user_id, INITIAL_FREE_CREDITS, 
                f"Créditos iniciais (boas-vindas)"
            )
            
            if success:
                log = DailyCreditLog(
                    user_id=user.id,
                    credits_added=INITIAL_FREE_CREDITS,
                    date=_today_brasil(),
                    total_after=user.credits,
                    source="initial_bonus"
                )
                db.add(log)
                crud.safe_commit(db, "Erro ao salvar log de créditos iniciais")
                
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
    """Simula aprovação de pagamento (apenas para modo simulado)"""
    await asyncio.sleep(SIMULATION_DELAY_SECONDS)
    
    db = SessionLocal()
    
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if payment and payment.status == "pending":
            user = crud.get_user_by_id(db, user_id)
            
            if user:
                # 🔥 ATIVAR PLANO PREMIUM
                success = crud.activate_premium_plan(db, user_id, payment_id)
                
                if success:
                    # Adicionar crédito inicial
                    crud.add_credits(db, user_id, 1, "Crédito inicial do plano premium")
                    
                    # 🔥 VERIFICAR SE FOI PROMOCIONAL (FUNDADOR)
                    price_type = payment.payment_metadata.get("price_type", "regular")
                    was_promotional = price_type == "promotional" or price_type == "locked_promotional"
                    
                    if was_promotional and not user.promotional_price_locked:
                        promo = get_or_create_promotion(db)
                        if promo.has_available_slots():
                            # Usa lock pessimista para garantir atomicidade
                            use_promotional_slot_atomic(db, promo.id)
                            user.promotional_price_locked = True
                            user.promotional_price = payment.amount
                            user.purchased_at_promotion = _now_brasil()
                            db.commit()
                            logger.info(f"🎟️ Preço fundador vitalício garantido para {user.email} - R$ {payment.amount}")
                    
                    # Atualizar status do pagamento
                    payment.status = "approved"
                    payment.approved_at = _now_brasil()
                    db.commit()
                    
                    logger.info(f"✅ Pagamento SIMULADO {payment_id} APROVADO após {SIMULATION_DELAY_SECONDS}s!")
    except Exception as e:
        logger.error(f"❌ Erro na simulação: {e}")
        db.rollback()
    finally:
        db.close()


async def create_simulated_pix_payment(
    user: User, db: Session, background_tasks: BackgroundTasks,
    price: float, price_type: str, was_promotional: bool
) -> Dict:
    """Cria pagamento PIX simulado"""
    payment_uuid = str(uuid.uuid4())
    pix_code = f"00020126360014BR.GOV.BCB.PIX0114{payment_uuid[:14]}5204000053039865404{int(price)}.005802BR5913AutoAnalytics6008SaoPaulo62070503***6304E2F3"
    
    payment = Payment(
        user_id=user.id,
        mp_id=f"SIM_{payment_uuid[:8].upper()}",
        amount=price,
        credits=DAYS_PREMIUM,
        payment_method="pix",
        status="pending",
        created_at=_now_brasil(),
        expires_at=_now_brasil() + timedelta(minutes=15),
        description=f"Plano Bronze - {price_type}",
        payment_metadata={
            "plan_id": "premium_mensal",
            "days": DAYS_PREMIUM,
            "price_type": price_type,
            "was_promotional": was_promotional,
            "real_payment": False,
            "simulated": True
        }
    )
    
    db.add(payment)
    crud.safe_commit(db, "Erro ao criar pagamento simulado")
    db.refresh(payment)
    
    promo = get_or_create_promotion(db)
    remaining_slots = promo.get_remaining_slots()
    
    logger.info(f"🔄 Pagamento SIMULADO criado: ID {payment.id} (aprovação em {SIMULATION_DELAY_SECONDS}s)")
    logger.info(f"   💰 Valor: R$ {price} - Tipo: {price_type} - Vagas restantes: {remaining_slots}")
    
    background_tasks.add_task(simulate_payment_approval, payment.id, user.id)
    
    return sanitize_response({
        "success": True,
        "payment_id": payment.id,
        "status": "pending",
        "amount": price,
        "price_type": price_type,
        "was_promotional": was_promotional,
        "remaining_slots": remaining_slots,
        "qr_code": pix_code,
        "expires_in": 15 * 60,
        "simulated": True,
        "simulation_delay": SIMULATION_DELAY_SECONDS,
        "message": f"💰 Pagamento de R$ {price:.2f} gerado! {'🔥 Preço de fundador garantido!' if was_promotional else ''}"
    })


# ==============================================
# 🔥 ROTAS - CORRIGIDAS COM PREÇO FUNDADOR VITALÍCIO
# ==============================================

@router.get("/promotion-status", response_model=PromotionStatusResponse)
async def get_promotion_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Retorna status da promoção de fundador"""
    promo = get_or_create_promotion(db)
    
    # Verificar se o usuário já tem preço vitalício
    user_price = None
    if current_user.promotional_price_locked and current_user.promotional_price:
        user_price = current_user.promotional_price
    
    return PromotionStatusResponse(
        success=True,
        total_slots=promo.total_slots,
        used_slots=promo.used_slots,
        remaining_slots=promo.get_remaining_slots(),
        promotional_price=float(promo.promotional_price),
        regular_price=float(promo.regular_price),
        current_price=float(promo.get_current_price()),
        is_active=promo.has_available_slots(),
        user_locked_price=user_price,
        is_vitalicio=True,
        message=(
            f"🔥 Preço de fundador: R$ {promo.promotional_price} (vitalício) - "
            f"{promo.get_remaining_slots()} vagas restantes!"
            if promo.has_available_slots() 
            else f"⛔ Promoção esgotada! Preço cheio: R$ {promo.regular_price}"
        )
    )


@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtém saldo de créditos do usuário"""
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "credits": 0, "error": "Usuário não encontrado"})
    
    is_new_user = (user.credits is None or user.credits == 0) and not user.is_admin
    if is_new_user:
        initialize_new_user_credits(user.id, db)
        db.refresh(user)
    
    premium_status = crud.check_premium_status(db, user.id)
    
    return sanitize_response({
        "success": True,
        "credits": user.credits or 0,
        "credits_display": crud.get_credits_display(user),
        "is_admin": user.is_admin,
        "max_credits_balance": MAX_CREDITS_PREMIUM,
        "plan": {
            "type": _get_plan_value(user),
            "is_premium": premium_status.get("is_premium", False),
            "days_left": premium_status.get("days_left", 0)
        },
        "promotional": {
            "has_locked_price": user.promotional_price_locked,
            "locked_price": user.promotional_price,
            "is_vitalicio": user.promotional_price_locked
        }
    })


@router.post("/create-pix")
async def create_pix_payment(
    background_tasks: BackgroundTasks,
    request_data: CreatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 CRIA PAGAMENTO PIX COM PREÇO CORRETO (FUNDADOR VITALÍCIO)
    
    Regras de preço:
    1. Usuário já comprou na promoção -> R$ 97,00 (vitalício)
    2. Ainda tem vagas -> R$ 97,00 (fundador)
    3. Acabaram as vagas -> R$ 149,90 (preço cheio)
    """
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Administradores têm acesso ilimitado")
    
    if not check_payment_rate_limit(user.id, db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail="Muitas tentativas. Aguarde até amanhã."
        )
    
    # Verificar se já é premium
    premium_status = crud.check_premium_status(db, user.id)
    if premium_status.get("is_premium", False):
        raise HTTPException(status_code=400, detail="Você já possui plano premium ativo!")
    
    # 🔥 DETERMINAR PREÇO CORRETO PARA O USUÁRIO
    price, price_type, was_promotional = get_user_price(user, db)
    
    # 🔥 REGISTRAR LOG DA DECISÃO DE PREÇO
    promo = get_or_create_promotion(db)
    remaining_slots = promo.get_remaining_slots()
    
    logger.info(f"💰 PREÇO DEFINIDO para {user.email}:")
    logger.info(f"   - Valor: R$ {price:.2f}")
    logger.info(f"   - Tipo: {price_type}")
    logger.info(f"   - Promocional: {was_promotional}")
    logger.info(f"   - Vagas restantes: {remaining_slots}/{TOTAL_PROMOTIONAL_SLOTS}")
    logger.info(f"   - Usuário tem preço vitalício: {user.promotional_price_locked}")
    
    if USE_REAL_MERCADO_PAGO and mp_service and mp_service.sdk:
        try:
            result = mp_service.create_real_pix_payment(
                plan_id=request_data.plan_id,
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
                # Criar pagamento com os metadados corretos
                payment = crud.create_payment(
                    db=db,
                    user_id=user.id,
                    mp_id=result["payment_id"],
                    amount=result["amount"],
                    credits=result["credits"],
                    payment_method="pix",
                    qr_code=result.get("qr_code"),
                    qr_code_base64=result.get("qr_code_base64"),
                    description=f"Plano Bronze - {price_type}",
                    payment_metadata={
                        "price_type": price_type,
                        "was_promotional": was_promotional,
                        "real_payment": True,
                        "mp_payment_id": result["payment_id"],
                        "cpf_provided": bool(request_data.cpf),
                        "plan_id": request_data.plan_id,
                        "remaining_slots_at_purchase": remaining_slots
                    }
                )
                
                alert_payment_pending(user.email, price)
                
                # 🔥 SE FOI PROMOCIONAL, REGISTRA QUE O USUÁRIO TEM PREÇO VITALÍCIO
                if was_promotional and not user.promotional_price_locked:
                    # 🔥 IMPORTANTE: O preço só é travado após confirmação do pagamento (webhook)
                    # Mas já registramos no metadata que foi promocional
                    logger.info(f"🎟️ Usuário {user.email} comprou na promoção - aguardando confirmação para travar preço vitalício")
                
                return sanitize_response({
                    "success": True,
                    "payment_id": payment.id,
                    "status": result["status"],
                    "amount": price,
                    "price_type": price_type,
                    "was_promotional": was_promotional,
                    "remaining_slots": remaining_slots,
                    "qr_code_base64": result.get("qr_code_base64"),
                    "qr_code": result.get("qr_code"),
                    "expires_in": PIX_QR_CODE_EXPIRY_MINUTES * 60,
                    "message": f"💰 Pagamento PIX gerado! Valor: R$ {price:.2f} - {'🔥 Preço de fundador garantido!' if was_promotional else 'Preço regular'}"
                })
            else:
                raise HTTPException(status_code=400, detail=result.get("error"))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Exceção: {e}")
            if os.getenv("MP_FALLBACK_SIMULATED", "false").lower() == "true":
                return await create_simulated_pix_payment(user, db, background_tasks, price, price_type, was_promotional)
            raise HTTPException(status_code=400, detail=str(e))
    else:
        return await create_simulated_pix_payment(user, db, background_tasks, price, price_type, was_promotional)


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
    
    if payment.expires_at and payment.expires_at < _now_brasil():
        return PixQRCodeResponse(success=False, status="expired", message="QR Code expirado", expires_in=0)
    
    return PixQRCodeResponse(
        success=True,
        qr_code_base64=payment.qr_code_base64,
        qr_code=payment.qr_code or payment.mp_id,
        status=payment.status,
        expires_in=max(0, int((payment.expires_at - _now_brasil()).total_seconds())) if payment.expires_at else PIX_QR_CODE_EXPIRY_MINUTES * 60
    )


@router.get("/plans")
async def get_plans(db: Session = Depends(get_db)):
    """🔥 Retorna informações dos planos com preços corretos"""
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
                "max_credits_balance": MAX_CREDITS_PREMIUM
            },
            "premium_mensal": {
                "id": "premium_mensal",
                "name": "Plano Bronze",
                "price": float(promo.get_current_price()),
                "regular_price": float(promo.regular_price),
                "promotional_price": float(promo.promotional_price),
                "is_vitalicio": True,
                "remaining_slots": promo.get_remaining_slots(),
                "total_slots": promo.total_slots,
                "description": f"1 crédito por dia durante {DAYS_PREMIUM} dias",
                "credits_per_day": CREDITS_PER_DAY,
                "total_days": DAYS_PREMIUM,
                "max_credits_balance": MAX_CREDITS_PREMIUM,
                "price_message": (
                    f"🔥 Preço de fundador: R$ {promo.promotional_price} (vitalício) - {promo.get_remaining_slots()} vagas"
                    if promo.has_available_slots()
                    else f"💰 Preço cheio: R$ {promo.regular_price} (promoção esgotada)"
                )
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
            "approved_at": payment.approved_at.isoformat() if payment.approved_at else None,
            "was_promotional": payment.payment_metadata.get("was_promotional", False),
            "price_type": payment.payment_metadata.get("price_type", "regular")
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
    
    crud.update_payment_status(db, payment.id, PaymentStatus.CANCELLED)
    
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
        "max_credits_balance": MAX_CREDITS_PREMIUM,
        "credits_display": crud.get_credits_display(user)
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
    
    success = crud.deduct_credits(db, user, 1, "Análise realizada")
    if success:
        db.refresh(user)
        return sanitize_response({
            "success": True, 
            "credits_consumed": 1, 
            "credits_remaining": user.credits,
            "credits_display": crud.get_credits_display(user)
        })
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
    
    premium_status = crud.check_premium_status(db, user.id)
    if not premium_status.get("is_premium", False):
        return sanitize_response({"success": False, "message": "Recurso exclusivo para premium"})
    
    can_receive = crud.can_receive_daily_credit(db, user.id)
    
    if can_receive.get("can_receive", False):
        success = crud.add_credits(db, user.id, 1, "Crédito diário premium")
        if success:
            log = DailyCreditLog(
                user_id=user.id,
                credits_added=1,
                date=_today_brasil(),
                total_after=user.credits,
                source="premium_daily"
            )
            db.add(log)
            crud.safe_commit(db, "Erro ao salvar log de crédito diário")
            db.refresh(user)
            
            return sanitize_response({
                "success": True,
                "credits_added": 1,
                "current_credits": user.credits,
                "max_credits": MAX_CREDITS_PREMIUM,
                "message": "🎉 Você ganhou 1 crédito do seu plano premium hoje!"
            })
    
    return sanitize_response({
        "success": False,
        "message": can_receive.get("message", "Você já recebeu seu crédito hoje ou atingiu o limite"),
        "current_credits": user.credits,
        "max_credits": MAX_CREDITS_PREMIUM
    })


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
            "success": True, 
            "has_subscription": True, 
            "is_admin": True,
            "days_left": 999, 
            "is_active": True, 
            "message": "👑 Administrador"
        })
    
    premium_status = crud.check_premium_status(db, user.id)
    
    is_premium = premium_status.get("is_premium", False)
    days_left = premium_status.get("days_left", 0)
    is_active = is_premium and days_left > 0
    
    if not is_active and user.plan == UserPlan.PREMIUM_MENSAL:
        crud.downgrade_expired_premium(db)
    
    return sanitize_response({
        "success": True,
        "has_subscription": is_active,
        "is_premium": is_active,
        "days_left": max(0, days_left),
        "is_active": is_active,
        "expires_at": premium_status.get("expires_at"),
        "activated_at": premium_status.get("activated_at"),
        "plan": premium_status.get("plan"),
        "max_credits": MAX_CREDITS_PREMIUM,
        # 🔥 INFORMAÇÕES DO PREÇO VITALÍCIO
        "promotional_price_locked": user.promotional_price_locked,
        "promotional_price": user.promotional_price,
        "is_vitalicio": user.promotional_price_locked,
        "message": "✅ Plano ativo" if is_active else "❌ Plano expirado"
    })


# ==============================================
# 🔥 WEBHOOK - CORRIGIDO COM response_model=None
# ==============================================

@router.post("/webhook", response_model=None)  # ✅ ADICIONADO response_model=None
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Webhook para receber notificações REAIS do Mercado Pago
    - response_model=None evita que o FastAPI tente inferir o tipo de retorno
    """
    try:
        body = await request.body()
        if not body:
            logger.warning("⚠️ Webhook recebido sem corpo")
            return {"status": "ignored"}
        
        try:
            data = json.loads(body)
            logger.info(f"🔔 Webhook JSON recebido: {json.dumps(data, indent=2)[:500]}")
        except json.JSONDecodeError:
            # Pode ser webhook do Mercado Pago em formato x-www-form-urlencoded
            text_body = body.decode('utf-8')
            logger.info(f"🔔 Webhook recebido em formato texto: {text_body[:200]}")
            match = re.search(r'id=(\d+)', text_body)
            if match:
                payment_id = match.group(1)
                logger.info(f"📦 Payment ID extraído: {payment_id}")
                background_tasks.add_task(process_payment_webhook, payment_id)
            else:
                logger.warning(f"⚠️ Não foi possível extrair payment_id do webhook")
            return {"status": "received"}
        
        # Extrair payment_id do JSON
        payment_id = data.get("data", {}).get("id") or data.get("id")
        if payment_id:
            logger.info(f"📦 Payment ID extraído: {payment_id}")
            background_tasks.add_task(process_payment_webhook, str(payment_id))
        else:
            # Tentar encontrar em outros lugares
            for key in ["payment_id", "preference_id", "resource"]:
                if key in data:
                    payment_id = data[key]
                    logger.info(f"📦 Payment ID encontrado em '{key}': {payment_id}")
                    background_tasks.add_task(process_payment_webhook, str(payment_id))
                    break
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}", exc_info=True)
        return {"status": "error"}


async def process_payment_webhook(payment_id: str):
    """
    🔥 Processa notificação de pagamento do Mercado Pago
    - TRAVA O PREÇO VITALÍCIO quando o pagamento é aprovado
    - Usa lock pessimista para vagas promocionais
    - É idempotente (não processa duas vezes)
    - Adiciona validação de integridade dos dados
    """
    # Aguardar um pouco para garantir que o pagamento foi criado no banco
    await asyncio.sleep(2)
    
    db = SessionLocal()
    
    try:
        # Validar payment_id
        if not payment_id or not str(payment_id).strip():
            logger.error(f"❌ Payment ID inválido: {payment_id}")
            return
        
        # Buscar pagamento
        payment = db.query(Payment).filter(Payment.mp_id == str(payment_id)).first()
        
        if not payment:
            logger.warning(f"⚠️ Pagamento {payment_id} não encontrado no banco")
            # Tentar buscar por ID numérico
            if str(payment_id).isdigit():
                payment = db.query(Payment).filter(Payment.id == int(payment_id)).first()
                if payment:
                    logger.info(f"✅ Pagamento encontrado pelo ID numérico: {payment.id}")
        
        if not payment:
            logger.error(f"❌ Pagamento {payment_id} não encontrado após tentativas")
            return
        
        # 🔥 IDEMPOTÊNCIA: Se já foi aprovado, não processar novamente
        if payment.status == PaymentStatus.APPROVED:
            logger.info(f"✅ Pagamento {payment_id} já estava aprovado. Ignorando webhook duplicado.")
            return
        
        if payment.status != PaymentStatus.PENDING:
            logger.info(f"ℹ️ Pagamento {payment_id} não está pendente (status: {payment.status}). Ignorando.")
            return
        
        # Consultar status no Mercado Pago
        logger.info(f"🔍 Consultando status do pagamento {payment_id} no Mercado Pago...")
        payment_info = mp_service.get_payment_status_real(payment_id)
        
        if not payment_info.get("success"):
            logger.error(f"❌ Não foi possível consultar pagamento {payment_id}: {payment_info.get('error')}")
            return
        
        status = payment_info.get("status")
        logger.info(f"📊 Status do pagamento {payment_id}: {status}")
        
        if status == "approved":
            # 🔥 ATUALIZAR STATUS DO PAGAMENTO
            crud.update_payment_status(db, payment.id, PaymentStatus.APPROVED, payment_info)
            logger.info(f"✅ Status do pagamento {payment_id} atualizado para APPROVED")
            
            user = crud.get_user_by_id(db, payment.user_id)
            
            if user:
                logger.info(f"👤 Processando usuário: {user.email} (ID: {user.id})")
                
                # Verificar se usuário já é premium
                if user.is_premium():
                    logger.info(f"⚠️ Usuário {user.email} já era premium. Pulando ativação duplicada.")
                else:
                    # 🔥 ATIVAR PLANO PREMIUM
                    success = crud.activate_premium_plan(db, user.id, payment.id)
                    
                    if success:
                        # Adicionar crédito inicial
                        crud.add_credits(db, user.id, 1, "Crédito inicial do plano premium")
                        logger.info(f"✅ Premium ativado para {user.email}")
                    else:
                        logger.error(f"❌ Falha ao ativar premium para {user.email}")
                
                # 🔥🔥🔥 TRAVAR PREÇO VITALÍCIO - CRÍTICO!
                # Verificar se o pagamento foi promocional
                was_promotional = payment.payment_metadata.get("was_promotional", False)
                price_type = payment.payment_metadata.get("price_type", "regular")
                
                logger.info(f"💰 Verificando preço promocional: was_promotional={was_promotional}, price_type={price_type}")
                
                if was_promotional and not user.promotional_price_locked:
                    # 🔥 USAR LOCK PESSIMISTA PARA USAR VAGA
                    promo = get_or_create_promotion(db)
                    
                    # Verifica se ainda tem vagas (proteção extra)
                    if promo.has_available_slots():
                        # Usa lock pessimista para garantir atomicidade
                        if use_promotional_slot_atomic(db, promo.id):
                            # 🔥 TRAVA O PREÇO VITALÍCIO NO USUÁRIO
                            user.promotional_price_locked = True
                            user.promotional_price = payment.amount  # R$ 97,00
                            user.purchased_at_promotion = _now_brasil()
                            db.commit()
                            
                            logger.info(f"🎟️🔥 PREÇO VITALÍCIO GARANTIDO para {user.email}!")
                            logger.info(f"   💰 Valor travado: R$ {user.promotional_price}")
                            logger.info(f"   📅 Data: {user.purchased_at_promotion}")
                            logger.info(f"   🎯 Vaga utilizada: {promo.used_slots}/{TOTAL_PROMOTIONAL_SLOTS}")
                            
                            # 🔥 Log adicional para auditoria
                            audit_log = {
                                "event": "preco_vitalicio_travado",
                                "user_id": user.id,
                                "user_email": user.email,
                                "payment_id": payment.id,
                                "amount": float(user.promotional_price),
                                "timestamp": _now_brasil().isoformat(),
                                "slot_used": promo.used_slots,
                                "total_slots": TOTAL_PROMOTIONAL_SLOTS
                            }
                            logger.info(f"📋 AUDIT: {json.dumps(audit_log)}")
                        else:
                            # Não conseguiu usar vaga (race condition)
                            logger.warning(f"⚠️ Não foi possível usar vaga promocional para {user.email}")
                    else:
                        logger.warning(f"⚠️ Promoção esgotada ao tentar travar preço para {user.email}")
                else:
                    logger.info(f"ℹ️ Usuário {user.email} não é elegível para preço vitalício: was_promotional={was_promotional}, locked={user.promotional_price_locked}")
                
                db.commit()
                
                # Enviar alerta de aprovação
                alert_payment_approved(user.email, payment.amount)
                logger.info(f"✅ Alerta de aprovação enviado para {user.email}")
                
            else:
                logger.error(f"❌ Usuário não encontrado para pagamento {payment_id} (user_id: {payment.user_id})")
        
        elif status == "rejected":
            crud.update_payment_status(db, payment.id, PaymentStatus.REJECTED, payment_info)
            logger.warning(f"⚠️ Pagamento {payment_id} REJEITADO: {payment_info.get('status_detail')}")
            alert_payment_failed(payment.user_id, payment.amount)
            logger.info(f"✅ Alerta de falha enviado para usuário {payment.user_id}")
        
        elif status == "cancelled":
            crud.update_payment_status(db, payment.id, PaymentStatus.CANCELLED, payment_info)
            logger.info(f"ℹ️ Pagamento {payment_id} CANCELADO")
        
        else:
            logger.info(f"ℹ️ Status do pagamento {payment_id}: {status} (não processado)")
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar webhook: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
        logger.info(f"✅ Processamento do webhook {payment_id} finalizado")

# backend/api/payment_routes.py - ADICIONAR ESTA ROTA

@router.get("/premium-status", response_model=None)
async def get_premium_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 Retorna status premium do usuário (compatível com payment.js)
    Esta rota é chamada pelo loadPremiumStatus() no frontend
    """
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Verifica status premium
    premium_status = crud.check_premium_status(db, user.id)
    is_premium = premium_status.get("is_premium", False)
    days_left = premium_status.get("days_left", 0)
    expires_at = premium_status.get("expires_at")
    activated_at = premium_status.get("activated_at")
    
    # Verifica se pode receber crédito hoje
    can_receive = crud.can_receive_daily_credit(db, user.id) if is_premium else {"can_receive": False}
    
    # Verifica se já recebeu hoje
    received_today = False
    if is_premium:
        today = _today_brasil()
        daily_log = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user.id,
            DailyCreditLog.date == today,
            DailyCreditLog.source == "premium_daily"
        ).first()
        received_today = daily_log is not None
    
    # 🔥 Verifica se é admin
    if user.is_admin:
        return sanitize_response({
            "is_premium": True,
            "days_left": 999,
            "is_admin": True,
            "credits_balance": "∞",
            "max_credits_balance": MAX_CREDITS_PREMIUM,
            "plan": "admin",
            "can_receive_today": False,
            "received_today": True,
            "promotional_price_locked": user.promotional_price_locked,
            "promotional_price": user.promotional_price,
            "is_vitalicio": user.promotional_price_locked,
            "next_credit_date": None,
            "activated_at": None,
            "expires_at": None,
            "days_used": 0
        })
    
    # 🔥 Verifica se é gratuito
    if not is_premium:
        return sanitize_response({
            "is_premium": False,
            "days_left": 0,
            "is_admin": False,
            "credits_balance": user.credits or 0,
            "max_credits_balance": MAX_CREDITS_PREMIUM,
            "plan": "free",
            "can_receive_today": False,
            "received_today": False,
            "promotional_price_locked": user.promotional_price_locked,
            "promotional_price": user.promotional_price,
            "is_vitalicio": user.promotional_price_locked,
            "next_credit_date": None,
            "activated_at": None,
            "expires_at": None,
            "days_used": 0
        })
    
    # 🔥 Usuário premium
    # Calcular dias usados
    days_used = 0
    if activated_at:
        days_used = (date.today() - activated_at.date()).days
        days_used = max(0, min(DAYS_PREMIUM, days_used))
    
    # Próximo crédito
    next_credit_date = None
    if is_premium and not received_today and can_receive.get("can_receive", False):
        next_credit_date = _today_brasil().isoformat()
    elif is_premium and received_today:
        next_credit_date = (_today_brasil() + timedelta(days=1)).isoformat()
    
    return sanitize_response({
        "is_premium": True,
        "days_left": max(0, days_left),
        "is_admin": False,
        "credits_balance": user.credits or 0,
        "max_credits_balance": MAX_CREDITS_PREMIUM,
        "plan": "premium_mensal",
        "can_receive_today": can_receive.get("can_receive", False),
        "received_today": received_today,
        "promotional_price_locked": user.promotional_price_locked,
        "promotional_price": user.promotional_price,
        "is_vitalicio": user.promotional_price_locked,
        "next_credit_date": next_credit_date,
        "activated_at": activated_at.isoformat() if activated_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "days_used": days_used,
        "total_days": DAYS_PREMIUM
    })
print("✅ payment_routes.py carregado - SISTEMA DE PREÇO FUNDADOR VITALÍCIO")
print(f"   💰 Preço de fundador: R$ {PROMOTIONAL_PRICE} (vitalício)")
print(f"   💰 Preço cheio: R$ {REGULAR_PRICE}")
print(f"   🎯 Vagas totais: {TOTAL_PROMOTIONAL_SLOTS}")
print(f"   🔒 Preço travado no usuário após confirmação do pagamento")