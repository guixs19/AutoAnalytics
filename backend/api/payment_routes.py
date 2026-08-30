# backend/api/payment_routes.py - VERSÃO 3.4 (COM LIMPEZA AUTOMÁTICA - 5 MINUTOS)
"""
🔥 ROTAS DE PAGAMENTO - SISTEMA DE PREÇO FUNDADOR VITALÍCIO
VERSÃO: 3.4 - COM LIMPEZA AUTOMÁTICA DE PAGAMENTOS (5 MINUTOS)

🔥 CORREÇÕES v3.4:
   1. ✅ ADICIONADO: Sistema de limpeza automática de pagamentos expirados
   2. ✅ ADICIONADO: Scheduler que roda a cada 5 minutos
   3. ✅ ADICIONADO: Cancelamento automático de pagamentos com +5 minutos
   4. ✅ ADICIONADO: Reset automático do rate limit
   5. ✅ ADICIONADO: LOGS detalhados do QR Code
   6. ✅ MELHORADO: Validação de resposta do Mercado Pago
   7. ✅ ADICIONADO: Rotas admin para reset manual
   8. ✅ ADICIONADO: Rota para usuário resetar próprias tentativas
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
from backend.services.payment_service import MercadoPagoService, get_mp_service
from backend.observability.sentinel import alert_payment_approved, alert_payment_pending, alert_payment_failed, get_webhook

# 🔥 CONSTANTES SINCRONIZADAS COM CRUD.PY
from backend.crud import (
    MAX_CREDITS_PREMIUM, 
    INITIAL_FREE_CREDITS, 
    _now_brasil, 
    _today_brasil,
    get_credit_eligibility,
    receive_daily_credit,
    manage_credits_after_consumption
)

# ==============================================
# 🔥 IMPORTS PARA LIMPEZA AUTOMÁTICA
# ==============================================

import atexit
import time as time_module

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# ==============================================
# 🔥 CONFIGURAÇÕES
# ==============================================

DAYS_PREMIUM = 30
CREDITS_PER_DAY = 1
MAX_PAYMENT_ATTEMPTS_PER_DAY = 5
PIX_QR_CODE_EXPIRY_MINUTES = 30
USE_REAL_MERCADO_PAGO = True
SIMULATION_DELAY_SECONDS = int(os.getenv("SIMULATION_DELAY_SECONDS", "8"))

# 🔥 CACHE
PROMOTION_CACHE_TTL = 60  # segundos
_promotion_cache = {
    "data": None,
    "timestamp": 0
}

# 🔥 MÉTRICAS
_payment_metrics = {
    "total_attempts": 0,
    "successful_payments": 0,
    "failed_payments": 0,
    "total_revenue": 0.0,
    "last_payment_at": None,
    "started_at": _now_brasil().isoformat()
}

# 🔥 PREÇOS
PROMOTIONAL_PRICE = 97.00
REGULAR_PRICE = 149.90
TOTAL_PROMOTIONAL_SLOTS = 100

# ==============================================
# 🔥 SISTEMA DE LIMPEZA AUTOMÁTICA DE PAGAMENTOS (5 MINUTOS)
# ==============================================

_scheduler_started = False

def cleanup_expired_payments():
    """
    🔥 Remove pagamentos pendentes com mais de 5 MINUTOS
    Isso automaticamente reseta o rate limit dos usuários
    """
    db = None
    try:
        db = SessionLocal()
        
        # 🔥 MUDADO: 5 MINUTOS em vez de 30
        cutoff = _now_brasil() - timedelta(minutes=5)
        expired_payments = db.query(Payment).filter(
            Payment.status == "pending",
            Payment.created_at < cutoff
        ).all()
        
        if expired_payments:
            count = len(expired_payments)
            
            for payment in expired_payments:
                payment.status = "cancelled"
                if not payment.payment_metadata:
                    payment.payment_metadata = {}
                payment.payment_metadata["auto_cancelled_at"] = _now_brasil().isoformat()
                payment.payment_metadata["auto_cancelled_reason"] = "expirado_5min"
            
            db.commit()
            logger.info(f"🧹 {count} pagamentos expirados (5min) cancelados automaticamente")
            
            try:
                from backend.observability.sentinel import alert_payment_failed
                for payment in expired_payments:
                    alert_payment_failed(payment.user_id, payment.amount, "pix")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao disparar alerta: {e}")
                
            invalidate_promotion_cache()
        else:
            logger.debug("🧹 Nenhum pagamento expirado encontrado")
            
    except Exception as e:
        logger.error(f"❌ Erro ao limpar pagamentos expirados: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()

def start_payment_cleanup_scheduler():
    """
    🔥 Inicia o scheduler de limpeza de pagamentos
    Roda a cada 2 minutos para ser mais rápido
    """
    global _scheduler_started
    
    if _scheduler_started:
        logger.debug("🧹 Scheduler já está rodando")
        return
    
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            cleanup_expired_payments,
            'interval',
            minutes=2,  # 🔥 Executa a cada 2 minutos
            id='payment_cleanup',
            replace_existing=True
        )
        scheduler.start()
        _scheduler_started = True
        logger.info("🧹 Scheduler de limpeza de pagamentos iniciado (intervalo: 2min)")
        
        # 🔥 Executa uma vez imediatamente
        cleanup_expired_payments()
        
        atexit.register(lambda: scheduler.shutdown())
        
    except ImportError:
        logger.warning("⚠️ apscheduler não instalado. Instale com: pip install apscheduler")
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar scheduler: {e}")

# 🔥 Iniciar scheduler automaticamente
start_payment_cleanup_scheduler()

# ==============================================
# 🔥 MODELOS PYDANTIC
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
    success: bool
    qr_code_base64: Optional[str] = None
    qr_code: Optional[str] = None
    status: str
    max_credits_balance: int = MAX_CREDITS_PREMIUM
    expires_in: int = PIX_QR_CODE_EXPIRY_MINUTES * 60
    message: str = ""


# ==============================================
# 🔥 SISTEMA DE CACHE CORRIGIDO
# ==============================================

def get_cached_promotion_data(db: Session, force_refresh: bool = False) -> Dict[str, Any]:
    """
    🔥 Obtém dados da promoção com cache
    ✅ CORRIGIDO: Retorna dict, não objeto SQLAlchemy
    """
    global _promotion_cache
    
    now = time_module.time()
    
    if not force_refresh and _promotion_cache["data"] is not None:
        if now - _promotion_cache["timestamp"] < PROMOTION_CACHE_TTL:
            logger.debug("📦 Usando promoção em cache")
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
    
    logger.debug(f"💾 Promoção em cache: {promo_data['remaining_slots']} vagas restantes")
    
    return promo_data


def invalidate_promotion_cache():
    """🔥 Invalida o cache da promoção"""
    global _promotion_cache
    _promotion_cache["data"] = None
    _promotion_cache["timestamp"] = 0
    logger.info("🔄 Cache da promoção invalidado")


# ==============================================
# 🔥 FUNÇÕES AUXILIARES
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
    """🔥 Usa pessimistic locking para evitar race condition"""
    promo = db.query(PromotionControl).filter(
        PromotionControl.id == promo_id
    ).with_for_update().first()
    
    if not promo or not promo.has_available_slots():
        return False
    
    promo.use_slot()
    crud.safe_commit(db, "Erro ao usar vaga promocional")
    
    remaining = promo.get_remaining_slots()
    logger.info(f"🎟️ Vaga de fundador utilizada! Restam: {remaining}/{TOTAL_PROMOTIONAL_SLOTS}")
    
    invalidate_promotion_cache()
    
    return True


def get_user_price(user: User, db: Session) -> tuple:
    """
    🔥 DETERMINA O PREÇO CORRETO PARA O USUÁRIO
    
    RETORNA: (price, price_type, was_promotional)
    """
    if user.promotional_price_locked and user.promotional_price:
        logger.info(f"💰 Usuário {user.email} tem preço vitalício: R$ {user.promotional_price}")
        return (user.promotional_price, "locked_promotional", True)
    
    promo_data = get_cached_promotion_data(db)
    
    if promo_data["has_available_slots"]:
        price = PROMOTIONAL_PRICE
        price_type = "promotional"
        was_promotional = True
        logger.info(f"💰 Usuário {user.email} - PREÇO FUNDADOR: R$ {price} (vaga {promo_data['used_slots'] + 1}/{TOTAL_PROMOTIONAL_SLOTS})")
    else:
        price = REGULAR_PRICE
        price_type = "regular"
        was_promotional = False
        logger.info(f"💰 Usuário {user.email} - PREÇO CHEIO: R$ {price} (promoção esgotada)")
    
    return (price, price_type, was_promotional)


def check_payment_rate_limit(user_id: int, db: Session) -> bool:
    """🔥 Verifica limite de tentativas"""
    today = _today_brasil()
    payments_today = db.query(Payment).filter(
        Payment.user_id == user_id,
        func.date(Payment.created_at) == today,
        Payment.status == "pending"
    ).count()
    
    if payments_today >= MAX_PAYMENT_ATTEMPTS_PER_DAY:
        logger.warning(f"⚠️ Rate limit excedido para usuário {user_id} ({payments_today}/{MAX_PAYMENT_ATTEMPTS_PER_DAY})")
        return False
    
    return True


def update_payment_metrics(success: bool, amount: float):
    """🔥 Atualiza métricas de pagamento"""
    global _payment_metrics
    
    _payment_metrics["total_attempts"] += 1
    
    if success:
        _payment_metrics["successful_payments"] += 1
        _payment_metrics["total_revenue"] += amount
        _payment_metrics["last_payment_at"] = _now_brasil().isoformat()
    else:
        _payment_metrics["failed_payments"] += 1


# ==============================================
# 🔥 SERVIÇOS
# ==============================================

daily_credits_service = DailyCreditsService()
mp_service = get_mp_service() or MercadoPagoService()
webhook = get_webhook()


# ==============================================
# 🔥 FUNÇÃO DESATIVADA
# ==============================================

def initialize_new_user_credits(user_id: int, db: Session) -> Dict:
    """🔥 FUNÇÃO DESATIVADA"""
    logger.warning(f"⚠️ [DESATIVADO] initialize_new_user_credits chamado para user_id {user_id}")
    return {
        "success": False, 
        "error": "Créditos iniciais são concedidos apenas no cadastro",
        "message": "Usuário já recebeu créditos iniciais ou não é elegível"
    }


# ==============================================
# 🔥 ROTAS ADMIN
# ==============================================

@router.post("/admin/cleanup-expired")
async def admin_cleanup_expired(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 ROTA ADMIN: Executa limpeza manual de pagamentos expirados (5min)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores")
    
    try:
        cutoff = _now_brasil() - timedelta(minutes=5)  # 🔥 5 MINUTOS
        expired_payments = db.query(Payment).filter(
            Payment.status == "pending",
            Payment.created_at < cutoff
        ).all()
        
        count = len(expired_payments)
        for payment in expired_payments:
            payment.status = "cancelled"
            if not payment.payment_metadata:
                payment.payment_metadata = {}
            payment.payment_metadata["admin_cleaned_at"] = _now_brasil().isoformat()
            payment.payment_metadata["admin_cleaned_reason"] = "expirado_5min"
        
        db.commit()
        
        return {
            "success": True,
            "message": f"✅ {count} pagamentos expirados (5min) cancelados",
            "cancelled_count": count
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro na limpeza manual: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/reset-rate-limit/{user_id}")
async def admin_reset_rate_limit(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 ROTA ADMIN: Reseta o rate limit de um usuário específico"""
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
            "message": f"✅ {count} pagamentos pendentes cancelados para usuário {user_id}",
            "user_id": user_id,
            "cancelled_count": count
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro ao resetar rate limit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# 🔥 ROTA USUÁRIO: RESETAR PRÓPRIAS TENTATIVAS
# ==============================================

@router.post("/reset-my-attempts")
async def reset_my_attempts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Usuário pode resetar suas próprias tentativas (com cooldown de 24h)"""
    try:
        # 🔥 Verifica se já resetou nas últimas 24h
        last_reset = db.query(Payment).filter(
            Payment.user_id == current_user.id,
            Payment.status == "cancelled",
            Payment.payment_metadata.get("reset_by_user").astext == "true",
            Payment.updated_at > (_now_brasil() - timedelta(hours=24))
        ).first()
        
        if last_reset:
            raise HTTPException(
                status_code=429,
                detail="Você já resetou suas tentativas nas últimas 24h. Aguarde o reset automático."
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
            "message": f"✅ {count} pagamentos cancelados. Você pode tentar novamente!",
            "cancelled_count": count,
            "next_reset_available": (_now_brasil() + timedelta(hours=24)).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erro ao resetar tentativas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# 🔥 ROTAS DE ELEGIBILIDADE E CRÉDITOS
# ==============================================

@router.get("/credits/eligibility", response_model=CreditEligibilityResponse)
async def get_credit_eligibility_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Retorna elegibilidade para receber créditos"""
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
    """🔥 Recebe crédito diário (apenas Premium)"""
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
        "message": result.get("message", "🌅 Crédito recebido com sucesso!"),
        "remaining_until_limit": result.get("remaining_until_limit", 0)
    })


@router.get("/bonus/check", response_model=BonusCheckResponse)
async def check_bonus_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Verifica se o usuário pode receber bônus premium"""
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
    """🔥 Resgata o bônus premium (1 crédito por zerar)"""
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    is_premium = _is_premium_user(user)
    if not is_premium:
        raise HTTPException(
            status_code=403,
            detail="Bônus exclusivo para usuários Premium. Assine o plano!"
        )
    
    eligibility = get_credit_eligibility(db, user)
    if not eligibility.get("can_receive_today", False):
        raise HTTPException(
            status_code=400,
            detail=eligibility.get("reason", "Você não pode receber bônus no momento")
        )
    
    result = manage_credits_after_consumption(
        db=db,
        user=user,
        amount=0,
        description="Bônus premium por zerar créditos"
    )
    
    if not result.get("success"):
        user.credits = (user.credits or 0) + 1
        
        log = DailyCreditLog(
            user_id=user.id,
            credits_added=1,
            date=_today_brasil(),
            total_after=user.credits,
            source="premium_bonus_claimed"
        )
        db.add(log)
        crud.safe_commit(db, "Erro ao conceder bônus premium")
        db.refresh(user)
        
        logger.info(f"⭐ Bônus premium concedido para {user.email} via claim")
        
        return sanitize_response({
            "success": True,
            "credits_added": 1,
            "current_credits": user.credits,
            "message": "⭐ Bônus premium concedido! Você recebeu 1 crédito.",
            "is_premium": True,
            "max_credits": MAX_CREDITS_PREMIUM,
            "credits_display": crud.get_credits_display(user)
        })
    
    return sanitize_response({
        "success": True,
        "credits_added": result.get("bonus_amount", 1),
        "current_credits": result.get("remaining", user.credits),
        "message": result.get("message", "⭐ Bônus premium concedido!"),
        "is_premium": True,
        "max_credits": MAX_CREDITS_PREMIUM,
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
    """🔥 Gerenciamento unificado de créditos"""
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    result = manage_credits_after_consumption(
        db=db,
        user=user,
        amount=amount,
        description=description
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao gerenciar créditos"))
    
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
# 🔥 ROTAS DE PAGAMENTO
# ==============================================

@router.get("/promotion-status", response_model=PromotionStatusResponse)
async def get_promotion_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    force_refresh: bool = False
):
    """🔥 Retorna status da promoção de fundador com cache"""
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
            f"🔥 Preço de fundador: R$ {promo_data['promotional_price']} (vitalício) - "
            f"{promo_data['remaining_slots']} vagas restantes!"
            if promo_data["has_available_slots"] 
            else f"⛔ Promoção esgotada! Preço cheio: R$ {promo_data['regular_price']}"
        )
    )


@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Obtém saldo de créditos do usuário"""
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
# 🔥 ROTA PRINCIPAL: CREATE PIX
# ==============================================

@router.post("/create-pix")
async def create_pix_payment(
    background_tasks: BackgroundTasks,
    request_data: CreatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔥 CRIA PAGAMENTO PIX REAL NO MERCADO PAGO
    V3.4 - COM LOGS DETALHADOS DO QR CODE
    """
    start_time = time_module.time()
    
    # ==========================================
    # 1️⃣ VALIDAÇÕES
    # ==========================================
    
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Administradores têm acesso ilimitado")
    
    # ==========================================
    # 2️⃣ RATE LIMIT
    # ==========================================
    
    if not check_payment_rate_limit(user.id, db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail="Muitas tentativas. Aguarde até amanhã."
        )
    
    # ==========================================
    # 3️⃣ VERIFICA SE JÁ É PREMIUM
    # ==========================================
    
    premium_status = crud.check_premium_status(db, user.id)
    if premium_status.get("is_premium", False):
        raise HTTPException(status_code=400, detail="Você já possui plano premium ativo!")
    
    # ==========================================
    # 4️⃣ DETERMINA PREÇO
    # ==========================================
    
    price, price_type, was_promotional = get_user_price(user, db)
    promo_data = get_cached_promotion_data(db)
    remaining_slots = promo_data["remaining_slots"]
    
    logger.info(f"💰 PREÇO DEFINIDO para {user.email}:")
    logger.info(f"   - Valor: R$ {price:.2f}")
    logger.info(f"   - Tipo: {price_type}")
    logger.info(f"   - Promocional: {was_promotional}")
    logger.info(f"   - Vagas restantes: {remaining_slots}/{TOTAL_PROMOTIONAL_SLOTS}")
    
    # ==========================================
    # 5️⃣ CRIA PAGAMENTO REAL NO MERCADO PAGO
    # ==========================================
    
    if not mp_service or not mp_service.sdk:
        logger.error("❌ Mercado Pago SDK não disponível")
        raise HTTPException(
            status_code=503, 
            detail="Serviço de pagamento indisponível no momento. Tente novamente."
        )
    
    try:
        logger.info(f"💳 Criando pagamento REAL no Mercado Pago para {user.email}")
        
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
            logger.error(f"❌ Erro no Mercado Pago: {result.get('error')}")
            update_payment_metrics(False, price)
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao criar pagamento"))
        
        # ==========================================
        # 6️⃣ 🔥 LOG DETALHADO DO QR CODE
        # ==========================================
        
        qr_code = result.get("qr_code")
        qr_code_base64 = result.get("qr_code_base64")
        
        logger.info("=" * 70)
        logger.info("📱 [QR CODE RECEBIDO DO MERCADO PAGO]")
        logger.info(f"   📍 QR Code (textual): {'✅' if qr_code else '❌'}")
        if qr_code:
            logger.info(f"   📍 Tamanho: {len(qr_code)} caracteres")
            logger.info(f"   📍 Preview: {qr_code[:50]}...")
        logger.info(f"   📍 QR Code Base64: {'✅' if qr_code_base64 else '❌'}")
        if qr_code_base64:
            logger.info(f"   📍 Tamanho: {len(qr_code_base64)} caracteres")
            logger.info(f"   📍 Preview: {qr_code_base64[:50]}...")
            logger.info(f"   📍 Tem prefixo: {'✅' if qr_code_base64.startswith('data:image') else '❌'}")
        logger.info("=" * 70)
        
        # 🔥 CORRIGE PREFIXO SE NECESSÁRIO
        if qr_code_base64 and not qr_code_base64.startswith('data:image'):
            logger.warning("⚠️ QR Code base64 SEM prefixo! Adicionando...")
            qr_code_base64 = f"data:image/png;base64,{qr_code_base64}"
            logger.info(f"✅ Prefixo adicionado: {qr_code_base64[:50]}...")
            result["qr_code_base64"] = qr_code_base64
        
        if not qr_code_base64:
            logger.error("❌ QR Code base64 NÃO FOI GERADO pelo Mercado Pago!")
            logger.error("   📱 Apenas QR Code textual disponível.")
        
        if not qr_code and not qr_code_base64:
            logger.error("❌ NENHUM QR CODE foi gerado pelo Mercado Pago!")
        
        # ==========================================
        # 7️⃣ SALVA NO BANCO
        # ==========================================
        
        payment = crud.create_payment(
            db=db,
            user_id=user.id,
            mp_id=result["payment_id"],
            amount=result["amount"],
            credits=result["credits"],
            payment_method="pix",
            qr_code=qr_code,
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
                "environment": mp_service.environment if hasattr(mp_service, 'environment') else "production",
                "qr_code_generated": bool(qr_code or qr_code_base64),
                "qr_code_base64_size": len(qr_code_base64) if qr_code_base64 else 0,
                "qr_code_text_size": len(qr_code) if qr_code else 0,
                "qr_code_has_prefix": qr_code_base64.startswith('data:image') if qr_code_base64 else False
            }
        )
        
        alert_payment_pending(user.email, price, "pix")
        
        if was_promotional and not user.promotional_price_locked:
            logger.info(f"🎟️ Usuário {user.email} comprou na promoção - aguardando confirmação")
        
        # ==========================================
        # 8️⃣ RETORNA RESPOSTA
        # ==========================================
        
        update_payment_metrics(True, price)
        
        elapsed = (time_module.time() - start_time) * 1000
        logger.info(f"✅ Pagamento PIX criado em {elapsed:.0f}ms - ID: {payment.id} - MP ID: {result['payment_id']}")
        logger.info(f"   📱 QR Code gerado: {'✅' if (qr_code or qr_code_base64) else '❌'}")
        
        return sanitize_response({
            "success": True,
            "payment_id": payment.id,
            "status": result["status"],
            "amount": price,
            "price_type": price_type,
            "was_promotional": was_promotional,
            "remaining_slots": remaining_slots,
            "qr_code_base64": qr_code_base64,
            "qr_code": qr_code,
            "expires_in": PIX_QR_CODE_EXPIRY_MINUTES * 60,
            "message": f"💰 Pagamento PIX gerado! Valor: R$ {price:.2f} - {'🔥 Preço de fundador garantido!' if was_promotional else 'Preço regular'}"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Exceção ao criar pagamento: {e}", exc_info=True)
        update_payment_metrics(False, price)
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================
# 🔥 ROTAS DE CONSULTA
# ==============================================

@router.get("/pix-qrcode/{payment_id}", response_model=PixQRCodeResponse)
async def get_pix_qrcode(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Obtém QR Code de um pagamento"""
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
        expires_in=max(0, int((payment.expires_at - _now_brasil()).total_seconds())) if payment.expires_at else PIX_QR_CODE_EXPIRY_MINUTES * 60,
        message="QR Code disponível"
    )


@router.get("/status/{payment_id}")
async def check_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Verifica status do pagamento"""
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
            "price_type": payment.payment_metadata.get("price_type", "regular"),
            "is_real": payment.payment_metadata.get("real_payment", True),
            "qr_code_generated": payment.payment_metadata.get("qr_code_generated", False)
        }
    })


@router.post("/cancel/{payment_id}")
async def cancel_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Cancela um pagamento pendente"""
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
        "real_payment_enabled": True,
        "mp_sdk_available": mp_service and mp_service.sdk is not None
    })


# ==============================================
# 🔥 MÉTRICAS E HEALTH CHECK
# ==============================================

@router.get("/metrics")
async def get_payment_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Retorna métricas de pagamento (apenas admin)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores")
    
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
    """🔥 Health check do serviço de pagamento"""
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
# 🔥 ROTAS ADMIN (MANUTENÇÃO)
# ==============================================

@router.post("/admin/fix-initial-credits")
async def fix_initial_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    confirm: bool = False
):
    """🔥 ROTA ADMIN: Corrige usuários existentes"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado. Apenas administradores.")
    
    if not confirm:
        return sanitize_response({
            "success": False,
            "message": "⚠️ Use confirm=true para executar.",
            "dry_run": True
        })
    
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
        logger.error(f"❌ Erro ao corrigir usuários: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/check-initial-credits")
async def check_initial_credits_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 ROTA ADMIN: Verifica status dos créditos iniciais"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores")
    
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
        logger.error(f"❌ Erro ao verificar status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# 🔥 WEBHOOK
# ==============================================

@router.post("/webhook", response_model=None)
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Webhook para receber notificações do Mercado Pago"""
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
            match = re.search(r'id=(\d+)', text_body)
            if match:
                payment_id = match.group(1)
                background_tasks.add_task(process_payment_webhook, payment_id)
            return {"status": "received"}
        
        payment_id = data.get("data", {}).get("id") or data.get("id")
        if payment_id:
            background_tasks.add_task(process_payment_webhook, str(payment_id))
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}", exc_info=True)
        return {"status": "error"}


async def process_payment_webhook(payment_id: str):
    """🔥 Processa notificação de pagamento do Mercado Pago"""
    await asyncio.sleep(2)
    
    db = SessionLocal()
    
    try:
        if not payment_id or not str(payment_id).strip():
            return
        
        payment = db.query(Payment).filter(Payment.mp_id == str(payment_id)).first()
        
        if not payment:
            if str(payment_id).isdigit():
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
                success = crud.activate_premium_plan(db, user.id, payment.id)
                if success:
                    crud.add_credits(db, user.id, 1, "Crédito inicial do plano premium")
            
            if user:
                was_promotional = payment.payment_metadata.get("was_promotional", False)
                
                if was_promotional and not user.promotional_price_locked:
                    promo = get_or_create_promotion(db)
                    if promo.has_available_slots() and use_promotional_slot_atomic(db, promo.id):
                        user.promotional_price_locked = True
                        user.promotional_price = payment.amount
                        user.purchased_at_promotion = _now_brasil()
                        db.commit()
                        logger.info(f"🎟️🔥 PREÇO VITALÍCIO GARANTIDO para {user.email}!")
                
                db.commit()
                alert_payment_approved(user.email, payment.amount, payment.payment_method)
        
        elif status == "rejected":
            crud.update_payment_status(db, payment.id, PaymentStatus.REJECTED, payment_info)
            alert_payment_failed(payment.user_id, payment.amount, payment.payment_method)
        
        elif status == "cancelled":
            crud.update_payment_status(db, payment.id, PaymentStatus.CANCELLED, payment_info)
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


# ==============================================
# 🔥 OUTRAS ROTAS
# ==============================================

@router.get("/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔥 Verifica se o usuário tem créditos para análise"""
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
    """🔥 Consome crédito usando o gerenciador unificado"""
    user = crud.get_user_by_id(db, current_user.id)
    if not user:
        return sanitize_response({"success": False, "error": "Usuário não encontrado"})
    
    if user.is_admin:
        return sanitize_response({"success": True, "credits_consumed": 0, "message": "Admin não consome créditos"})
    
    result = manage_credits_after_consumption(
        db=db,
        user=user,
        amount=1,
        description="Análise realizada"
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
    """🔥 Verifica e concede crédito diário premium"""
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
                "message": result.get("message", "🎉 Você ganhou 1 crédito do seu plano premium hoje!"),
                "remaining_until_limit": result.get("remaining_until_limit", 0)
            })
    
    return sanitize_response({
        "success": False,
        "message": eligibility.get("reason", "Você já recebeu seu crédito hoje ou atingiu o limite"),
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
    """🔥 Retorna status da assinatura premium"""
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
# 🔥 PRINTS DE CARREGAMENTO
# ==============================================

print("=" * 70)
print("✅ payment_routes.py v3.4 carregado - COM LIMPEZA AUTOMÁTICA (5 MIN)!")
print("   🔥 NOVIDADES v3.4:")
print("      - ✅ Limpeza automática a cada 2 minutos")
print("      - ✅ Pagamentos com 5 minutos são cancelados")
print("      - ✅ Rate limit reseta automaticamente")
print("      - ✅ Logs detalhados do QR Code")
print("      - ✅ Rota admin: /admin/cleanup-expired")
print("      - ✅ Rota admin: /admin/reset-rate-limit/{user_id}")
print("      - ✅ Rota usuário: /reset-my-attempts")
print("   📊 CONFIGURAÇÕES:")
print(f"      - Rate limit: {MAX_PAYMENT_ATTEMPTS_PER_DAY} tentativas/dia")
print(f"      - Limpeza: 2 em 2 minutos")
print(f"      - Expiração: 5 minutos")
print("   💰 PREÇOS:")
print(f"      - Promocional: R$ {PROMOTIONAL_PRICE}")
print(f"      - Regular: R$ {REGULAR_PRICE}")
print("=" * 70)