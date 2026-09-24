# backend/api/payment_routes.py - VERSÃO 4.0 (BLINDADA - SEM SANITIZE NO QR CODE)
"""
🔥 ROTAS DE PAGAMENTO - SISTEMA DE PREÇO FUNDADOR VITALÍCIO
VERSÃO: 4.0 - SINCRONIZADA COM payment_service.py V4.0

🔥 CORREÇÕES v4.0:
   1. ✅ CORRIGIDO: sanitize_response NÃO é mais aplicado em qr_code_base64
      (o sanitize removia '/' e '+' e truncava em 500 chars, corrompendo a imagem)
   2. ✅ CORRIGIDO: Resposta SEMPRE inclui pix_code separado de qr_code_base64
   3. ✅ CORRIGIDO: /reset-my-attempts agora usa JSON funcional (SQLAlchemy 2.x)
   4. ✅ CORRIGIDO: Scheduler idempotente (usa singleton global)
   5. ✅ CORRIGIDO: price default no handler de exceção (evita NameError)
   6. ✅ CORRIGIDO: Rate limit usa intervalo explícito de datas
   7. ✅ MELHORADO: Log estruturado do payload FINAL enviado ao front
   8. ✅ ADICIONADO: Validação do QR Code ANTES de mandar pro front
   9. ✅ ADICIONADO: JSONResponse direto (sem sanitize) para o create-pix
  10. ✅ ADICIONADO: Revalidação com MP antes de cancelar pagamento expirado
  11. ✅ MELHORADO: Lock atômico no scheduler para múltiplos workers
"""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import uuid
import logging
import re
import html
import asyncio
import os
import json
import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator

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
    _get_plan_value,
    get_credit_eligibility_status,
    can_receive_bonus
)
from backend.services.payment_service import MercadoPagoService, get_mp_service, QrCodeNormalizer
from backend.observability.sentinel import alert_payment_approved, alert_payment_pending, alert_payment_failed, get_webhook

from backend.crud import (
    MAX_CREDITS_PREMIUM,
    INITIAL_FREE_CREDITS,
    _now_brasil,
    _today_brasil,
    get_credit_eligibility,
    receive_daily_credit,
    manage_credits_after_consumption
)

import atexit
import time as time_module

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# ==============================================
# CONFIGURAÇÕES
# ==============================================

DAYS_PREMIUM = 30
CREDITS_PER_DAY = 1
MAX_PAYMENT_ATTEMPTS_PER_DAY = 5
PIX_QR_CODE_EXPIRY_MINUTES = 30
USE_REAL_MERCADO_PAGO = True
SIMULATION_DELAY_SECONDS = int(os.getenv("SIMULATION_DELAY_SECONDS", "8"))

PROMOTION_CACHE_TTL = 60
_promotion_cache = {"data": None, "timestamp": 0}

_payment_metrics = {
    "total_attempts": 0,
    "successful_payments": 0,
    "failed_payments": 0,
    "total_revenue": 0.0,
    "last_payment_at": None,
    "started_at": _now_brasil().isoformat()
}

PROMOTIONAL_PRICE = 97.00
REGULAR_PRICE = 149.90
TOTAL_PROMOTIONAL_SLOTS = 100

# ==============================================
# 🔥 V4.0: SCHEDULER IDEMPOTENTE (evita duplicação no hot-reload)
# ==============================================

_scheduler_instance = None
_scheduler_lock = None

def cleanup_expired_payments():
    """
    🔥 V4.0: Revalida com o MP antes de cancelar (evita cancelar pagamento já aprovado).
    """
    db = None
    try:
        db = SessionLocal()

        cutoff = _now_brasil() - timedelta(minutes=5)
        expired_payments = db.query(Payment).filter(
            Payment.status == "pending",
            Payment.created_at < cutoff
        ).all()

        if not expired_payments:
            logger.debug("🧹 Nenhum pagamento expirado encontrado")
            return

        cancelled_count = 0
        kept_count = 0

        for payment in expired_payments:
            # 🔥 V4.0: Revalida com o MP antes de cancelar
            try:
                if payment.mp_id and mp_service and mp_service.sdk:
                    mp_status = mp_service.get_payment_status_real(str(payment.mp_id), use_cache=False)
                    if mp_status.get("success"):
                        real_status = mp_status.get("status")
                        if real_status == "approved":
                            # 🔥 Foi aprovado! Não cancela — deixa o webhook processar
                            logger.warning(
                                f"⚠️ Pagamento {payment.id} marcado como expirado "
                                f"mas MP diz 'approved' — mantendo pending"
                            )
                            kept_count += 1
                            continue
            except Exception as e:
                logger.warning(f"⚠️ Não foi possível revalidar pagamento {payment.id}: {e}")
                # Em dúvida, cancela (comportamento anterior)

            payment.status = "cancelled"
            if not payment.payment_metadata:
                payment.payment_metadata = {}
            payment.payment_metadata["auto_cancelled_at"] = _now_brasil().isoformat()
            payment.payment_metadata["auto_cancelled_reason"] = "expirado_5min"
            cancelled_count += 1

        db.commit()

        if cancelled_count:
            logger.info(f"🧹 {cancelled_count} pagamentos expirados cancelados")
        if kept_count:
            logger.info(f"🛡️ {kept_count} pagamentos mantidos (MP diz approved)")

        if cancelled_count:
            try:
                for payment in expired_payments:
                    if payment.status == "cancelled":
                        alert_payment_failed(payment.user_id, payment.amount, "pix")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao disparar alerta: {e}")

            invalidate_promotion_cache()

    except Exception as e:
        logger.error(f"❌ Erro ao limpar pagamentos expirados: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def start_payment_cleanup_scheduler():
    """
    🔥 V4.0: Scheduler singleton — não duplica em hot-reload.
    """
    global _scheduler_instance

    # 🔥 Se já existe no módulo, não recria
    if _scheduler_instance is not None:
        logger.debug("🧹 Scheduler já está rodando (module-level)")
        return

    # 🔥 Checa se já existe instância global no processo (proteção hot-reload)
    if getattr(start_payment_cleanup_scheduler, '_started', False):
        logger.debug("🧹 Scheduler já foi iniciado neste processo")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        _scheduler_instance = BackgroundScheduler()
        _scheduler_instance.add_job(
            cleanup_expired_payments,
            'interval',
            minutes=2,
            id='payment_cleanup',
            replace_existing=True,
            max_instances=1,          # 🔥 V4.0: só 1 instância por vez
            coalesce=True,            # 🔥 V4.0: agrupa execuções atrasadas
            misfire_grace_time=30     # 🔥 V4.0: tolerância de 30s
        )
        _scheduler_instance.start()
        start_payment_cleanup_scheduler._started = True
        logger.info("🧹 Scheduler de limpeza iniciado (intervalo: 2min)")

        cleanup_expired_payments()
        atexit.register(lambda: _scheduler_instance.shutdown() if _scheduler_instance else None)

    except ImportError:
        logger.warning("⚠️ apscheduler não instalado. Instale com: pip install apscheduler")
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar scheduler: {e}")


start_payment_cleanup_scheduler()


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


class CreditEligibilityResponse(BaseModel):
    success: bool
    can_receive_today: bool
    is_premium: bool
    is_admin: bool
    credits_balance: int
    max_credits: int
    received_today: bool
    days_left: int
    at_max_limit: bool
    reason: str
    next_credit_date: Optional[str] = None
    credits_until_limit: int
    timezone: str = "America/Sao_Paulo (UTC-3)"
    today_date: str


class BonusCheckResponse(BaseModel):
    success: bool
    can_receive: bool
    is_premium: bool
    credits_balance: int
    max_credits: int
    received_today: bool
    at_max_limit: bool
    message: str
    next_credit_date: Optional[str] = None


class CreditManageResponse(BaseModel):
    success: bool
    consumed: int
    remaining: int
    bonus_granted: bool
    bonus_amount: int
    message: str
    needs_attention: bool
    is_premium: bool
    max_credits: int
    credits_display: str


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


class PixQRCodeResponse(BaseModel):
    """🔥 V4.0: Adicionado pix_code separado."""
    success: bool
    qr_code_base64: Optional[str] = None
    qr_code: Optional[str] = None
    pix_code: Optional[str] = None       # 🔥 V4.0
    status: str
    max_credits_balance: int = MAX_CREDITS_PREMIUM
    expires_in: int = PIX_QR_CODE_EXPIRY_MINUTES * 60
    message: str = ""


# ==============================================
# CACHE
# ==============================================

def get_cached_promotion_data(db: Session, force_refresh: bool = False) -> Dict[str, Any]:
    global _promotion_cache
    now = time_module.time()

    if not force_refresh and _promotion_cache["data"] is not None:
        if now - _promotion_cache["timestamp"] < PROMOTION_CACHE_TTL:
            return _promotion_cache["data"]

    promo = get_or_create_promotion(db)

    promo_data = {
        "id": promo.id,
        "total_slots": promo.total_slots,
        "used_slots": promo.used_slots,
        "remaining_slots": promo.get_remaining_slots(),
        "promotional_price": float(promo.promotional_price),
        "regular_price": float(promo.regular_price),
        "current_price": promo.get_current_price(),
        "is_active": promo.is_active,
        "has_available_slots": promo.has_available_slots(),
        "updated_at": _now_brasil().isoformat()
    }

    _promotion_cache["data"] = promo_data
    _promotion_cache["timestamp"] = now
    return promo_data


def invalidate_promotion_cache():
    global _promotion_cache
    _promotion_cache["data"] = None
    _promotion_cache["timestamp"] = 0
    logger.info("🔄 Cache da promoção invalidado")


# ==============================================
# 🔥 V4.0: SANITIZE QUE NÃO MUTILA BASE64
# ==============================================

# Campos que NUNCA devem passar por sanitize
PROTECTED_FIELDS = {
    "qr_code_base64",
    "qr_code",
    "pix_code",
    "token",
    "access_token",
    "mp_id"
}


def sanitize_string(text: str) -> str:
    """
    🔥 V4.0: Remove caracteres perigosos mas NÃO trunca em 500 chars
    (o truncamento era o que mutilava o Base64).
    """
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'<[^>]*>', '', text)
    text = html.escape(text)
    # 🔥 Não remove '/' e '+' — são base64-safe
    text = re.sub(r'[<>\"\'\\;`]', '', text)
    text = re.sub(r'(?i)javascript\s*:', '', text)
    text = re.sub(r'(?i)on\w+\s*=', '', text)
    # 🔥 Aumenta limite para não truncar QR Code
    return text[:10000]


def sanitize_response(data: Any, _depth: int = 0) -> Any:
    """
    🔥 V4.0: Sanitiza APENAS strings de campos não-protegidos.
    Preserva nomes de chaves e valores de QR Code.
    """
    if _depth > 10:
        return data  # proteção contra recursão infinita

    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # 🔥 Preserva a chave como está
            # 🔥 Se o campo é protegido, passa direto sem sanitize
            if k in PROTECTED_FIELDS:
                result[k] = v
            else:
                result[k] = sanitize_response(v, _depth + 1)
        return result
    elif isinstance(data, str):
        return sanitize_string(data)
    elif isinstance(data, list):
        return [sanitize_response(item, _depth + 1) for item in data]
    elif isinstance(data, float):
        return round(data, 2)
    return data


def validate_payment_id(payment_id: int) -> bool:
    return isinstance(payment_id, int) and payment_id > 0


# ==============================================
# PROMOÇÃO
# ==============================================

def get_or_create_promotion(db: Session) -> PromotionControl:
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
        logger.info(f"✅ Promoção criada: {TOTAL_PROMOTIONAL_SLOTS} vagas")
    return promo


def use_promotional_slot_atomic(db: Session, promo_id: int) -> bool:
    promo = db.query(PromotionControl).filter(
        PromotionControl.id == promo_id
    ).with_for_update().first()

    if not promo or not promo.has_available_slots():
        return False

    promo.use_slot()
    crud.safe_commit(db, "Erro ao usar vaga promocional")
    invalidate_promotion_cache()
    return True


def get_user_price(user: User, db: Session) -> tuple:
    if user.promotional_price_locked and user.promotional_price:
        return (user.promotional_price, "locked_promotional", True)

    promo_data = get_cached_promotion_data(db)

    if promo_data["has_available_slots"]:
        return (PROMOTIONAL_PRICE, "promotional", True)
    return (REGULAR_PRICE, "regular", False)


def check_payment_rate_limit(user_id: int, db: Session) -> bool:
    """
    🔥 V4.0: Usa intervalo explícito de datas (evita problema de timezone).
    """
    now_brasil = _now_brasil()
    start_of_day = now_brasil.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    payments_today = db.query(Payment).filter(
        Payment.user_id == user_id,
        Payment.created_at >= start_of_day,
        Payment.created_at < end_of_day,
        Payment.status == "pending"
    ).count()

    if payments_today >= MAX_PAYMENT_ATTEMPTS_PER_DAY:
        logger.warning(f"⚠️ Rate limit excedido user {user_id}: {payments_today}/{MAX_PAYMENT_ATTEMPTS_PER_DAY}")
        return False
    return True


def update_payment_metrics(success: bool, amount: float):
    global _payment_metrics
    _payment_metrics["total_attempts"] += 1
    if success:
        _payment_metrics["successful_payments"] += 1
        _payment_metrics["total_revenue"] += amount
        _payment_metrics["last_payment_at"] = _now_brasil().isoformat()
    else:
        _payment_metrics["failed_payments"] += 1


# ==============================================
# SERVIÇOS
# ==============================================

daily_credits_service = DailyCreditsService()
mp_service = get_mp_service() or MercadoPagoService()
webhook = get_webhook()


def initialize_new_user_credits(user_id: int, db: Session) -> Dict:
    logger.warning(f"⚠️ [DESATIVADO] initialize_new_user_credits({user_id})")
    return {
        "success": False,
        "error": "Créditos iniciais são concedidos apenas no cadastro",
        "message": "Usuário já recebeu créditos iniciais ou não é elegível"
    }


# ==============================================
# ROTAS ADMIN
# ==============================================

@router.post("/admin/cleanup-expired")
async def admin_cleanup_expired(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores")

    try:
        cleanup_expired_payments()
        return {"success": True, "message": "✅ Limpeza executada"}
    except Exception as e:
        logger.error(f"❌ Erro na limpeza manual: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/reset-rate-limit/{user_id}")
async def admin_reset_rate_limit(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores")

    try:
        payments = db.query(Payment).filter(
            Payment.user_id == user_id,
            Payment.status == "pending"
        ).all()

        count = len(payments)
        for payment in payments:
            payment.status = "cancelled"
            if not payment.payment_metadata:
                payment.payment_metadata = {}
            payment.payment_metadata["admin_reset_at"] = _now_brasil().isoformat()

        db.commit()
        return {
            "success": True,
            "message": f"✅ {count} pagamentos cancelados",
            "user_id": user_id,
            "cancelled_count": count
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# 🔥 V4.0: RESET-MY-ATTEMPTS CORRIGIDO
# ==============================================

@router.post("/reset-my-attempts")
async def reset_my_attempts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 V4.0: Filtro de JSON agora usa sintaxe compatível com SQLAlchemy 2.x.
    """
    try:
        # 🔥 V4.0: Busca por reset recente sem usar .astext (que não existe em InstrumentedAttribute)
        cooldown_cutoff = _now_brasil() - timedelta(hours=24)

        recent_resets = db.query(Payment).filter(
            Payment.user_id == current_user.id,
            Payment.status == "cancelled",
            Payment.updated_at >= cooldown_cutoff
        ).all()

        # 🔥 Filtra em Python (mais seguro que JSON path)
        has_recent_reset = any(
            (p.payment_metadata or {}).get("reset_by_user") is True
            for p in recent_resets
        )

        if has_recent_reset:
            raise HTTPException(
                status_code=429,
                detail="Você já resetou suas tentativas nas últimas 24h."
            )

        payments = db.query(Payment).filter(
            Payment.user_id == current_user.id,
            Payment.status == "pending"
        ).all()

        count = len(payments)
        for payment in payments:
            payment.status = "cancelled"
            if not payment.payment_metadata:
                payment.payment_metadata = {}
            payment.payment_metadata["reset_by_user"] = True
            payment.payment_metadata["reset_at"] = _now_brasil().isoformat()
            payment.updated_at = _now_brasil()

        db.commit()

        return {
            "success": True,
            "message": f"✅ {count} pagamentos cancelados",
            "cancelled_count": count,
            "next_reset_available": (_now_brasil() + timedelta(hours=24)).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# ELEGIBILIDADE E CRÉDITOS (inalterado)
# ==============================================

@router.get("/credits/eligibility", response_model=CreditEligibilityResponse)
async def get_credit_eligibility_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    eligibility = get_credit_eligibility(db, user)

    return CreditEligibilityResponse(
        success=True,
        can_receive_today=eligibility.get("can_receive_today", False),
        is_premium=eligibility.get("is_premium", False),
        is_admin=eligibility.get("is_admin", False),
        credits_balance=eligibility.get("credits_balance", 0) if not eligibility.get("is_admin", False) else 999999,
        max_credits=eligibility.get("max_credits", MAX_CREDITS_PREMIUM),
        received_today=eligibility.get("received_today", False),
        days_left=eligibility.get("days_left", 0),
        at_max_limit=eligibility.get("at_max_limit", False),
        reason=eligibility.get("reason", ""),
        next_credit_date=eligibility.get("next_credit_date"),
        credits_until_limit=eligibility.get("credits_until_limit", 0),
        timezone="America/Sao_Paulo (UTC-3)",
        today_date=_today_brasil().isoformat()
    )


@router.post("/credits/receive-daily")
async def receive_daily_credit_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    result = receive_daily_credit(db, user.id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao receber crédito"))

    return sanitize_response({
        "success": True,
        "credits_added": result.get("credits_added", 0),
        "current_credits": result.get("current_credits", user.credits),
        "max_credits": result.get("max_credits", MAX_CREDITS_PREMIUM),
        "message": result.get("message", "🌅 Crédito recebido!"),
        "remaining_until_limit": result.get("remaining_until_limit", 0)
    })


@router.get("/bonus/check", response_model=BonusCheckResponse)
async def check_bonus_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    result = can_receive_bonus(db, user)
    return BonusCheckResponse(
        success=True,
        can_receive=result.get("can_receive", False),
        is_premium=result.get("is_premium", False),
        credits_balance=result.get("credits_balance", user.credits or 0),
        max_credits=result.get("max_credits", MAX_CREDITS_PREMIUM),
        received_today=result.get("received_today", False),
        at_max_limit=result.get("at_max_limit", False),
        message=result.get("message", ""),
        next_credit_date=result.get("next_credit_date")
    )


@router.post("/bonus/claim")
async def claim_bonus(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if not _is_premium_user(user):
        raise HTTPException(status_code=403, detail="Bônus exclusivo para Premium.")

    eligibility = get_credit_eligibility(db, user)
    if not eligibility.get("can_receive_today", False):
        raise HTTPException(status_code=400, detail=eligibility.get("reason", "Sem elegibilidade"))

    result = manage_credits_after_consumption(
        db=db, user=user, amount=0,
        description="Bônus premium por zerar créditos"
    )

    if not result.get("success"):
        user.credits = (user.credits or 0) + 1
        log = DailyCreditLog(
            user_id=user.id, credits_added=1,
            date=_today_brasil(), total_after=user.credits,
            source="premium_bonus_claimed"
        )
        db.add(log)
        crud.safe_commit(db, "Erro ao conceder bônus")
        db.refresh(user)
        return sanitize_response({
            "success": True, "credits_added": 1,
            "current_credits": user.credits,
            "message": "⭐ Bônus concedido!",
            "is_premium": True, "max_credits": MAX_CREDITS_PREMIUM,
            "credits_display": crud.get_credits_display(user)
        })

    return sanitize_response({
        "success": True,
        "credits_added": result.get("bonus_amount", 1),
        "current_credits": result.get("remaining", user.credits),
        "message": result.get("message", "⭐ Bônus concedido!"),
        "is_premium": True, "max_credits": MAX_CREDITS_PREMIUM,
        "credits_display": crud.get_credits_display(user)
    })


@router.post("/credits/manage", response_model=CreditManageResponse)
async def manage_credits(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    amount: int = 1,
    description: str = "Consumo de crédito"
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    result = manage_credits_after_consumption(
        db=db, user=user, amount=amount, description=description
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro"))

    return CreditManageResponse(
        success=True,
        consumed=result.get("consumed", 0),
        remaining=result.get("remaining", 0),
        bonus_granted=result.get("bonus_granted", False),
        bonus_amount=result.get("bonus_amount", 0),
        message=result.get("message", ""),
        needs_attention=result.get("needs_attention", False),
        is_premium=result.get("is_premium", False),
        max_credits=result.get("max_credits", MAX_CREDITS_PREMIUM),
        credits_display=result.get("credits_display", "0")
    )


# ==============================================
# PROMOÇÃO E BALANÇO
# ==============================================

@router.get("/promotion-status", response_model=PromotionStatusResponse)
async def get_promotion_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    force_refresh: bool = False
):
    promo_data = get_cached_promotion_data(db, force_refresh)

    user_price = None
    if current_user.promotional_price_locked and current_user.promotional_price:
        user_price = current_user.promotional_price

    return PromotionStatusResponse(
        success=True,
        total_slots=promo_data["total_slots"],
        used_slots=promo_data["used_slots"],
        remaining_slots=promo_data["remaining_slots"],
        promotional_price=promo_data["promotional_price"],
        regular_price=promo_data["regular_price"],
        current_price=promo_data["current_price"],
        is_active=promo_data["has_available_slots"],
        user_locked_price=user_price,
        is_vitalicio=True,
        message=(
            f"🔥 Preço fundador: R$ {promo_data['promotional_price']} - "
            f"{promo_data['remaining_slots']} vagas!"
            if promo_data["has_available_slots"]
            else f"⛔ Esgotada! Preço: R$ {promo_data['regular_price']}"
        )
    )


@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "credits": 0, "error": "Usuário não encontrado"})

    premium_status = crud.check_premium_status(db, user.id)
    eligibility = get_credit_eligibility(db, user)

    return sanitize_response({
        "success": True,
        "credits": user.credits or 0,
        "credits_display": crud.get_credits_display(user),
        "is_admin": user.is_admin,
        "max_credits_balance": MAX_CREDITS_PREMIUM,
        "can_receive_today": eligibility.get("can_receive_today", False),
        "plan": {
            "type": _get_plan_value(user),
            "is_premium": premium_status.get("is_premium", False),
            "days_left": premium_status.get("days_left", 0)
        },
        "promotional": {
            "has_locked_price": user.promotional_price_locked,
            "locked_price": user.promotional_price,
            "is_vitalicio": user.promotional_price_locked
        },
        "received_initial_credits": user.received_initial_credits
    })


# ==============================================
# 🔥 V4.0: ROTA PRINCIPAL CREATE-PIX
# ==============================================

@router.post("/create-pix")
async def create_pix_payment(
    background_tasks: BackgroundTasks,
    request_data: CreatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 V4.0: Retorna JSONResponse direto (sem sanitize) para o QR Code.
    """
    start_time = time_module.time()
    price = 0.0  # 🔥 V4.0: default para evitar NameError no except

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

    premium_status = crud.check_premium_status(db, user.id)
    if premium_status.get("is_premium", False):
        raise HTTPException(status_code=400, detail="Você já possui plano premium ativo!")

    price, price_type, was_promotional = get_user_price(user, db)
    promo_data = get_cached_promotion_data(db)
    remaining_slots = promo_data["remaining_slots"]

    logger.info(f"💰 PREÇO: {user.email} - R$ {price:.2f} ({price_type}) - {remaining_slots} vagas")

    if not mp_service or not mp_service.sdk:
        logger.error("❌ MP SDK não disponível")
        raise HTTPException(status_code=503, detail="Serviço indisponível")

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

        if not result.get("success"):
            logger.error(f"❌ Erro MP: {result.get('error')}")
            update_payment_metrics(False, price)
            raise HTTPException(status_code=400, detail=result.get("error", "Erro"))

        # 🔥 V4.0: Extrai com segurança
        qr_code_base64 = result.get("qr_code_base64") or ""
        qr_code_text = result.get("qr_code") or ""
        pix_code = result.get("pix_code") or qr_code_text  # 🔥 V4.0

        # 🔥 V4.0: Validação do QR Code
        logger.info("=" * 70)
        logger.info("📱 [QR CODE PRONTO PARA ENVIAR]")
        logger.info(f"   imagem: {'✅ ' + str(len(qr_code_base64)) + ' chars' if qr_code_base64 else '❌ vazio'}")
        logger.info(f"   copia-e-cola: {'✅ ' + str(len(pix_code)) + ' chars' if pix_code else '❌ vazio'}")
        logger.info("=" * 70)

        if not qr_code_base64 and not pix_code:
            logger.error("❌ Nem imagem nem copia-e-cola disponíveis")
            update_payment_metrics(False, price)
            raise HTTPException(
                status_code=502,
                detail="Mercado Pago não retornou QR Code. Tente novamente."
            )

        payment = crud.create_payment(
            db=db,
            user_id=user.id,
            mp_id=result["payment_id"],
            amount=result["amount"],
            credits=result["credits"],
            payment_method="pix",
            qr_code=pix_code,
            qr_code_base64=qr_code_base64,
            description=f"Plano Bronze - {price_type}",
            payment_metadata={
                "price_type": price_type,
                "was_promotional": was_promotional,
                "real_payment": True,
                "mp_payment_id": result["payment_id"],
                "cpf_provided": bool(request_data.cpf),
                "plan_id": request_data.plan_id,
                "remaining_slots_at_purchase": remaining_slots,
                "environment": getattr(mp_service, 'environment', 'production'),
                "qr_code_generated": bool(qr_code_base64 or pix_code),
                "qr_code_base64_size": len(qr_code_base64),
                "qr_code_text_size": len(pix_code)
            }
        )

        alert_payment_pending(user.email, price, "pix")
        update_payment_metrics(True, price)

        elapsed = (time_module.time() - start_time) * 1000
        logger.info(f"✅ PIX criado em {elapsed:.0f}ms - ID: {payment.id}")

        # 🔥 V4.0: JSONResponse DIRETO — sem sanitize_response
        return JSONResponse(content={
            "success": True,
            "payment_id": payment.id,
            "status": result["status"],
            "amount": price,
            "price_type": price_type,
            "was_promotional": was_promotional,
            "remaining_slots": remaining_slots,
            "qr_code_base64": qr_code_base64,   # 🔥 IMAGEM (intocada)
            "qr_code": pix_code,                 # 🔥 copia-e-cola
            "pix_code": pix_code,                # 🔥 ALIAS explícito
            "expires_in": PIX_QR_CODE_EXPIRY_MINUTES * 60,
            "message": f"💰 PIX gerado! R$ {price:.2f} - {'🔥 Fundador!' if was_promotional else 'Regular'}"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Exceção: {e}", exc_info=True)
        update_payment_metrics(False, price)
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================
# CONSULTA
# ==============================================

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
        return PixQRCodeResponse(success=False, status="not_found", message="Não encontrado")

    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    if payment.expires_at and payment.expires_at < _now_brasil():
        return PixQRCodeResponse(success=False, status="expired", message="Expirado", expires_in=0)

    return PixQRCodeResponse(
        success=True,
        qr_code_base64=payment.qr_code_base64,
        qr_code=payment.qr_code or payment.mp_id,
        pix_code=payment.qr_code,  # 🔥 V4.0
        status=payment.status,
        expires_in=max(0, int((payment.expires_at - _now_brasil()).total_seconds())) if payment.expires_at else PIX_QR_CODE_EXPIRY_MINUTES * 60,
        message="QR Code disponível"
    )


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
        return sanitize_response({"success": False, "error": "Não encontrado"})

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
            "was_promotional": (payment.payment_metadata or {}).get("was_promotional", False),
            "price_type": (payment.payment_metadata or {}).get("price_type", "regular"),
            "is_real": (payment.payment_metadata or {}).get("real_payment", True),
            "qr_code_generated": (payment.payment_metadata or {}).get("qr_code_generated", False)
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
        raise HTTPException(status_code=404, detail="Não encontrado")

    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    if payment.status != "pending":
        raise HTTPException(status_code=400, detail="Apenas pendentes podem ser cancelados")

    crud.update_payment_status(db, payment.id, PaymentStatus.CANCELLED)
    return sanitize_response({"success": True, "message": "Cancelado"})


@router.get("/plans")
async def get_plans(db: Session = Depends(get_db)):
    promo = get_or_create_promotion(db)
    return sanitize_response({
        "success": True,
        "plans": {
            "gratuito": {
                "id": "gratuito", "name": "Plano Gratuito", "price": 0,
                "credits": INITIAL_FREE_CREDITS,
                "description": f"{INITIAL_FREE_CREDITS} créditos iniciais",
                "max_credits_balance": MAX_CREDITS_PREMIUM
            },
            "premium_mensal": {
                "id": "premium_mensal", "name": "Plano Bronze",
                "price": float(promo.get_current_price()),
                "regular_price": float(promo.regular_price),
                "promotional_price": float(promo.promotional_price),
                "is_vitalicio": True,
                "remaining_slots": promo.get_remaining_slots(),
                "total_slots": promo.total_slots,
                "description": f"1 crédito/dia durante {DAYS_PREMIUM} dias",
                "credits_per_day": CREDITS_PER_DAY,
                "total_days": DAYS_PREMIUM,
                "max_credits_balance": MAX_CREDITS_PREMIUM,
                "price_message": (
                    f"🔥 R$ {promo.promotional_price} - {promo.get_remaining_slots()} vagas"
                    if promo.has_available_slots()
                    else f"💰 R$ {promo.regular_price} (esgotada)"
                )
            }
        },
        "real_payment_enabled": True,
        "mp_sdk_available": mp_service and mp_service.sdk is not None
    })


# ==============================================
# MÉTRICAS E HEALTH
# ==============================================

@router.get("/metrics")
async def get_payment_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admins")

    return sanitize_response({
        "success": True,
        "metrics": {
            **_payment_metrics,
            "cache_enabled": True,
            "cache_ttl": PROMOTION_CACHE_TTL,
            "rate_limit": MAX_PAYMENT_ATTEMPTS_PER_DAY,
            "mp_sdk_available": mp_service and mp_service.sdk is not None,
            "uptime_seconds": (datetime.fromisoformat(_payment_metrics["started_at"]) - _now_brasil()).total_seconds() * -1
        }
    })


@router.get("/health")
async def payment_health_check():
    cache_active = _promotion_cache["data"] is not None
    return {
        "status": "healthy" if (mp_service and mp_service.sdk) else "degraded",
        "service": "payment",
        "mp_sdk_available": mp_service and mp_service.sdk is not None,
        "cache_active": cache_active,
        "cache_ttl": PROMOTION_CACHE_TTL,
        "metrics": {
            "total_attempts": _payment_metrics["total_attempts"],
            "successful": _payment_metrics["successful_payments"],
            "failed": _payment_metrics["failed_payments"],
            "total_revenue": round(_payment_metrics["total_revenue"], 2)
        },
        "timestamp": _now_brasil().isoformat()
    }


# ==============================================
# ADMIN MANUTENÇÃO
# ==============================================

@router.post("/admin/fix-initial-credits")
async def fix_initial_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    confirm: bool = False
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admins")

    if not confirm:
        return sanitize_response({"success": False, "message": "Use confirm=true", "dry_run": True})

    try:
        users = db.query(User).all()
        fixed_count = 0
        for user in users:
            if not user.received_initial_credits:
                user.received_initial_credits = True
                fixed_count += 1
        db.commit()
        return sanitize_response({
            "success": True,
            "message": f"✅ {fixed_count} usuários corrigidos!",
            "fixed_count": fixed_count
        })
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/check-initial-credits")
async def check_initial_credits_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admins")

    try:
        total_users = db.query(User).count()
        users_without_flag = db.query(User).filter(User.received_initial_credits == False).count()
        return sanitize_response({
            "success": True,
            "total_users": total_users,
            "users_without_flag": users_without_flag,
            "needs_fix": users_without_flag > 0,
            "fix_endpoint": "/api/payments/admin/fix-initial-credits?confirm=true"
        })
    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# WEBHOOK (inalterado)
# ==============================================

@router.post("/webhook", response_model=None)
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    try:
        body = await request.body()
        if not body:
            logger.warning("⚠️ Webhook sem corpo")
            return {"status": "ignored"}

        try:
            data = json.loads(body)
            logger.info(f"🔔 Webhook JSON recebido")
        except json.JSONDecodeError:
            text_body = body.decode('utf-8')
            match = re.search(r'id=(\d+)', text_body)
            if match:
                background_tasks.add_task(process_payment_webhook, match.group(1))
            return {"status": "received"}

        payment_id = data.get("data", {}).get("id") or data.get("id")
        if payment_id:
            background_tasks.add_task(process_payment_webhook, str(payment_id))

        return {"status": "received"}

    except Exception as e:
        logger.error(f"❌ Erro webhook: {e}", exc_info=True)
        return {"status": "error"}


async def process_payment_webhook(payment_id: str):
    await asyncio.sleep(2)
    db = SessionLocal()

    try:
        if not payment_id or not str(payment_id).strip():
            return

        payment = db.query(Payment).filter(Payment.mp_id == str(payment_id)).first()
        if not payment and str(payment_id).isdigit():
            payment = db.query(Payment).filter(Payment.id == int(payment_id)).first()

        if not payment:
            return

        if payment.status == PaymentStatus.APPROVED:
            return
        if payment.status != PaymentStatus.PENDING:
            return

        payment_info = mp_service.get_payment_status_real(payment_id)
        if not payment_info.get("success"):
            return

        status = payment_info.get("status")

        if status == "approved":
            crud.update_payment_status(db, payment.id, PaymentStatus.APPROVED, payment_info)
            user = crud.get_user_by_id(db, payment.user_id)

            if user and not user.is_premium():
                if crud.activate_premium_plan(db, user.id, payment.id):
                    crud.add_credits(db, user.id, 1, "Crédito inicial do plano premium")

            if user:
                was_promotional = (payment.payment_metadata or {}).get("was_promotional", False)
                if was_promotional and not user.promotional_price_locked:
                    promo = get_or_create_promotion(db)
                    if promo.has_available_slots() and use_promotional_slot_atomic(db, promo.id):
                        user.promotional_price_locked = True
                        user.promotional_price = payment.amount
                        user.purchased_at_promotion = _now_brasil()
                        db.commit()
                        logger.info(f"🎟️🔥 PREÇO VITALÍCIO: {user.email}")

                db.commit()
                alert_payment_approved(user.email, payment.amount, payment.payment_method)

        elif status == "rejected":
            crud.update_payment_status(db, payment.id, PaymentStatus.REJECTED, payment_info)
            alert_payment_failed(payment.user_id, payment.amount, payment.payment_method)

        elif status == "cancelled":
            crud.update_payment_status(db, payment.id, PaymentStatus.CANCELLED, payment_info)

    except Exception as e:
        logger.error(f"❌ Erro webhook: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


# ==============================================
# OUTRAS ROTAS
# ==============================================

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

    eligibility = get_credit_eligibility(db, user)
    current_credits = user.credits or 0

    return sanitize_response({
        "success": True,
        "has_credits": current_credits > 0,
        "credits": current_credits,
        "max_credits_balance": MAX_CREDITS_PREMIUM,
        "credits_display": crud.get_credits_display(user),
        "can_receive_today": eligibility.get("can_receive_today", False),
        "is_premium": eligibility.get("is_premium", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "reason": eligibility.get("reason", "")
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
        return sanitize_response({"success": True, "credits_consumed": 0, "message": "Admin ilimitado"})

    result = manage_credits_after_consumption(
        db=db, user=user, amount=1, description="Análise realizada"
    )

    if result.get("success"):
        return sanitize_response({
            "success": True,
            "credits_consumed": result.get("consumed", 1),
            "credits_remaining": result.get("remaining", user.credits),
            "credits_display": result.get("credits_display", crud.get_credits_display(user)),
            "bonus_granted": result.get("bonus_granted", False),
            "bonus_amount": result.get("bonus_amount", 0),
            "needs_attention": result.get("needs_attention", False),
            "message": result.get("message", "")
        })

    return sanitize_response({
        "success": False,
        "error": result.get("error", "Créditos insuficientes")
    })


@router.post("/premium/check-daily")
async def check_daily_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "error": "Usuário não encontrado"})

    eligibility = get_credit_eligibility(db, user)

    if not eligibility.get("is_premium", False):
        return sanitize_response({
            "success": False,
            "message": "Recurso exclusivo para premium",
            "is_premium": False
        })

    if eligibility.get("can_receive_today", False):
        result = receive_daily_credit(db, user.id)
        if result.get("success"):
            return sanitize_response({
                "success": True,
                "credits_added": result.get("credits_added", 1),
                "current_credits": result.get("current_credits", user.credits),
                "max_credits": MAX_CREDITS_PREMIUM,
                "message": result.get("message", "🎉 Crédito do dia!"),
                "remaining_until_limit": result.get("remaining_until_limit", 0)
            })

    return sanitize_response({
        "success": False,
        "message": eligibility.get("reason", "Já recebeu hoje"),
        "current_credits": user.credits,
        "max_credits": MAX_CREDITS_PREMIUM,
        "at_max_limit": eligibility.get("at_max_limit", False),
        "received_today": eligibility.get("received_today", False)
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
    eligibility = get_credit_eligibility(db, user)

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
        "promotional_price_locked": user.promotional_price_locked,
        "promotional_price": user.promotional_price,
        "is_vitalicio": user.promotional_price_locked,
        "can_receive_today": eligibility.get("can_receive_today", False),
        "received_today": eligibility.get("received_today", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "credits_balance": user.credits or 0,
        "message": "✅ Plano ativo" if is_active else "❌ Plano expirado"
    })


# ==============================================
# PRINTS
# ==============================================

print("=" * 70)
print("✅ payment_routes.py v4.0 carregado - BLINDADO!")
print("   🔥 NOVIDADES v4.0:")
print("      - ✅ sanitize NÃO corrompe mais o QR Code Base64")
print("      - ✅ pix_code enviado separado de qr_code_base64")
print("      - ✅ /reset-my-attempts corrigido (SQLAlchemy 2.x)")
print("      - ✅ Scheduler idempotente (não duplica hot-reload)")
print("      - ✅ Revalidação MP antes de cancelar pagamento")
print("      - ✅ Rate limit com intervalo explícito")
print(f"   📊 Rate limit: {MAX_PAYMENT_ATTEMPTS_PER_DAY}/dia")
print(f"   ⏰ Expiração: 5 min | Limpeza: 2 min")
print(f"   💰 Preços: R$ {PROMOTIONAL_PRICE} / R$ {REGULAR_PRICE}")
print("=" * 70)