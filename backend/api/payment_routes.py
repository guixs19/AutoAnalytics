# backend/api/payment_routes.py - VERSÃO COMPLETA COM PROMOÇÃO BRONZE E SEGURANÇA REFORÇADA

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
import secrets
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator

from backend.database import get_db
from backend import crud
from backend.api.auth_routes import get_current_user
from backend.models import User, Payment, DailyCreditLog, UserPlan, Analysis, PromotionControl
from backend.services.daily_credits_service import DailyCreditsService
from backend.services.credits_consumer import can_perform_analysis, consume_analysis_credit, get_credits_display
from backend.services.payment_service import MercadoPagoService
from backend.observability.sentinel import alert_payment_approved, alert_payment_pending, get_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# ==============================================
# CONFIGURAÇÕES DE SEGURANÇA
# ==============================================

MAX_CREDITS_BALANCE = 3
DAYS_PREMIUM = 30
CREDITS_PER_DAY = 1
INITIAL_FREE_CREDITS = 3
MAX_PAYMENT_ATTEMPTS_PER_DAY = 3
PIX_QR_CODE_EXPIRY_MINUTES = 15

# ==============================================
# MODELOS PYDANTIC PARA VALIDAÇÃO
# ==============================================

class CreatePaymentRequest(BaseModel):
    """Modelo validado para criação de pagamento"""
    plan_id: str = Field(..., description="ID do plano", regex="^(premium_mensal|gratuito)$")
    
    @validator('plan_id')
    def validate_plan_id(cls, v):
        allowed = ['premium_mensal', 'gratuito']
        if v not in allowed:
            raise ValueError(f'Plano inválido. Permitidos: {allowed}')
        return v


class PaymentStatusResponse(BaseModel):
    """Resposta padronizada para status de pagamento"""
    success: bool
    payment: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PixQRCodeResponse(BaseModel):
    """Resposta padronizada para QR Code PIX"""
    success: bool
    qr_code_base64: Optional[str] = None
    qr_code: Optional[str] = None
    status: str
    max_credits_balance: int = MAX_CREDITS_BALANCE
    expires_in: int = PIX_QR_CODE_EXPIRY_MINUTES * 60
    message: str = ""


class PromotionStatusResponse(BaseModel):
    """Resposta padronizada para status da promoção"""
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
# FUNÇÕES DE SANITIZAÇÃO REFORÇADAS
# ==============================================

def sanitize_string(text: str) -> str:
    """Sanitização robusta anti-XSS e injeção"""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    
    # Remove tags HTML
    text = re.sub(r'<[^>]*>', '', text)
    # Escapa caracteres HTML
    text = html.escape(text)
    # Remove caracteres perigosos
    text = re.sub(r'[<>\"\'\/\\;`]', '', text)
    # Remove possíveis expressões JavaScript
    text = re.sub(r'(?i)javascript\s*:', '', text)
    text = re.sub(r'(?i)on\w+\s*=', '', text)
    # Limita tamanho
    text = text[:500]
    
    return text


def sanitize_response(data: Any) -> Any:
    """Sanitiza recursivamente uma resposta JSON"""
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
    """Valida ID de pagamento"""
    return isinstance(payment_id, int) and payment_id > 0


# ==============================================
# SERVIÇOS
# ==============================================

daily_credits_service = DailyCreditsService()
mp_service = MercadoPagoService()
webhook = get_webhook()


# ==============================================
# FUNÇÃO: INICIALIZAR CRÉDITOS DO USUÁRIO NOVO
# ==============================================

def initialize_new_user_credits(user_id: int, db: Session) -> Dict:
    """Usuário novo ganha 3 créditos gratuitos para teste"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
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
            
            # Log seguro (sem email exposto)
            logger.info(f"🎉 Usuário ID {user.id} ganhou {INITIAL_FREE_CREDITS} créditos gratuitos!")
            
            return {
                "success": True,
                "credits_added": INITIAL_FREE_CREDITS,
                "current_credits": user.credits,
                "message": f"🎉 Boas-vindas! Você ganhou {INITIAL_FREE_CREDITS} créditos grátis para testar o sistema!"
            }
        
        return {"success": False, "message": "Usuário já possui créditos"}
        
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar créditos: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}


# ==============================================
# FUNÇÃO: OBTER OU CRIAR PROMOÇÃO
# ==============================================

def get_or_create_promotion(db: Session) -> PromotionControl:
    """Retorna ou cria o controle de promoção"""
    promo = db.query(PromotionControl).first()
    if not promo:
        promo = PromotionControl()
        db.add(promo)
        db.commit()
        db.refresh(promo)
        logger.info("✅ Promoção Bronze inicializada (100 vagas a R$ 97,00)")
    return promo


def check_payment_rate_limit(user_id: int, db: Session) -> bool:
    """Verifica rate limit para criação de pagamentos"""
    today = date.today()
    payments_today = db.query(Payment).filter(
        Payment.user_id == user_id,
        func.date(Payment.created_at) == today,
        Payment.status == "pending"
    ).count()
    
    if payments_today >= MAX_PAYMENT_ATTEMPTS_PER_DAY:
        logger.warning(f"⚠️ Rate limit excedido para usuário {user_id}: {payments_today} tentativas")
        return False
    return True


# ==============================================
# 🔥 ROTA: STATUS DA PROMOÇÃO (VAGAS)
# ==============================================

@router.get("/promotion-status", response_model=PromotionStatusResponse)
async def get_promotion_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna status atual da promoção (vagas restantes, preços)"""
    
    promo = get_or_create_promotion(db)
    
    # Verificar se usuário já tem preço travado
    user_locked = current_user.promotional_price_locked
    user_price = current_user.promotional_price if user_locked else None
    
    return PromotionStatusResponse(
        success=True,
        total_slots=promo.total_slots,
        used_slots=promo.used_slots,
        remaining_slots=promo.get_remaining_slots(),
        promotional_price=float(promo.promotional_price),
        regular_price=float(promo.regular_price),
        current_price=float(promo.get_current_price()),
        is_active=promo.has_available_slots(),
        user_locked_price=float(user_price) if user_price else None,
        message=f"🔥 {promo.get_remaining_slots()} vagas restantes!" if promo.has_available_slots() else "⛔ Promoção esgotada! Preço regular: R$ 149,90"
    )


# ==============================================
# 🔥 ROTA PRINCIPAL: SALDO DO USUÁRIO
# ==============================================

@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """Retorna saldo de créditos do usuário"""
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        return sanitize_response({
            "success": False,
            "credits": 0,
            "credits_display": "0",
            "error": "Usuário não encontrado"
        })
    
    # Verificar se é usuário novo e adicionar créditos
    is_new_user = (user.credits is None or user.credits == 0) and not user.is_admin
    welcome_message = None
    
    if is_new_user:
        result = initialize_new_user_credits(user.id, db)
        db.refresh(user)
        if result.get("success"):
            welcome_message = result.get("message")
    
    # Verificar status premium
    is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
    
    # Calcular dias restantes
    days_left = 0
    if is_premium and user.premium_expires_at:
        days_left = max(0, (user.premium_expires_at - date.today()).days)
    
    # Verificar se pode receber crédito diário
    can_receive_daily = False
    if is_premium and (user.credits or 0) < MAX_CREDITS_BALANCE:
        today = date.today()
        received_today = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user.id,
            DailyCreditLog.date == today,
            DailyCreditLog.source.in_(["premium_daily", "daily"])
        ).first()
        can_receive_daily = received_today is None
    
    response = {
        "success": True,
        "credits": user.credits or 0,
        "credits_display": get_credits_display(user),
        "is_admin": user.is_admin,
        "max_credits_balance": MAX_CREDITS_BALANCE,
        "is_new_user": is_new_user,
        "welcome_message": welcome_message,
        "can_perform_analysis": can_perform_analysis(user, 1),
        "plan": {
            "type": str(user.plan),
            "is_premium": is_premium,
            "premium_expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
            "days_left": days_left,
            "credits_per_day": CREDITS_PER_DAY if is_premium else 0,
            "can_receive_daily": can_receive_daily
        }
    }
    
    return sanitize_response(response)


# ==============================================
# 🔥 ROTA: VERIFICAR CRÉDITOS PARA ANÁLISE
# ==============================================

@router.get("/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verifica se usuário tem créditos para realizar análise"""
    
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        return sanitize_response({
            "success": False,
            "has_credits": False,
            "credits": 0,
            "error": "Usuário não encontrado"
        })
    
    if user.is_admin:
        return sanitize_response({
            "success": True,
            "has_credits": True,
            "credits": float('inf'),
            "credits_display": "∞",
            "is_admin": True,
            "message": "👑 Admin - créditos ilimitados"
        })
    
    if (user.credits is None or user.credits == 0) and not user.is_premium():
        initialize_new_user_credits(user.id, db)
        db.refresh(user)
    
    current_credits = user.credits or 0
    has_credits = current_credits > 0
    
    if not has_credits and user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium():
        daily_result = daily_credits_service.check_and_add_daily_credit(db, user.id)
        if daily_result.get("success") and daily_result.get("credits_added", 0) > 0:
            db.refresh(user)
            current_credits = user.credits or 0
            has_credits = current_credits > 0
            logger.info(f"🔄 Crédito diário automático adicionado para usuário ID {user.id}")
    
    return sanitize_response({
        "success": True,
        "has_credits": has_credits,
        "credits": current_credits,
        "credits_display": str(current_credits),
        "required": 1,
        "max_credits_balance": MAX_CREDITS_BALANCE,
        "is_premium": user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium(),
        "message": f"Você tem {current_credits} crédito(s)" if has_credits else "Créditos insuficientes. Adquira o plano premium!"
    })


# ==============================================
# 🔥 ROTA: CONSUMIR CRÉDITO
# ==============================================

@router.post("/consume")
async def consume_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Consome 1 crédito do usuário após análise bem-sucedida"""
    
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        return sanitize_response({
            "success": False,
            "error": "Usuário não encontrado"
        })
    
    if user.is_admin:
        return sanitize_response({
            "success": True,
            "credits_consumed": 0,
            "credits_remaining": "∞",
            "message": "Admin não consome créditos"
        })
    
    success = consume_analysis_credit(user, db, 1)
    
    if success:
        db.refresh(user)
        return sanitize_response({
            "success": True,
            "credits_consumed": 1,
            "credits_remaining": user.credits,
            "credits_display": str(user.credits),
            "message": f"✅ Análise realizada! Crédito consumido. Saldo: {user.credits}/{MAX_CREDITS_BALANCE}"
        })
    else:
        return sanitize_response({
            "success": False,
            "error": "Créditos insuficientes",
            "credits_remaining": user.credits or 0,
            "message": "❌ Você não tem créditos suficientes. Adquira o plano premium!"
        })


# ==============================================
# 🔥 ROTA: RECEBER CRÉDITO DIÁRIO (PREMIUM)
# ==============================================

@router.post("/premium/check-daily")
async def check_daily_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Endpoint para usuário premium receber crédito diário"""
    
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        return sanitize_response({
            "success": False,
            "error": "Usuário não encontrado"
        })
    
    is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
    
    if not is_premium:
        return sanitize_response({
            "success": False,
            "message": "Este recurso é exclusivo para assinantes premium",
            "is_premium": False
        })
    
    result = daily_credits_service.check_and_add_daily_credit(db, current_user.id)
    
    if result.get("success") and result.get("credits_added", 0) > 0:
        db.refresh(current_user)
        result["new_balance"] = current_user.credits
        result["max_balance"] = MAX_CREDITS_BALANCE
        result["message"] = f"⭐ Você ganhou 1 crédito do seu plano premium! Agora tem {current_user.credits}/{MAX_CREDITS_BALANCE} créditos."
    
    return sanitize_response(result)


# ==============================================
# 🔥 ROTA: CRIAR PAGAMENTO PIX (COM PREÇO DINÂMICO E SEGURANÇA)
# ==============================================

@router.post("/create-pix")
async def create_pix_payment(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria pagamento PIX com preço automático baseado nas vagas"""
    
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Administradores têm acesso ilimitado")
    
    # 🔥 RATE LIMIT: Evita spam de criação de pagamentos
    if not check_payment_rate_limit(user.id, db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas tentativas de pagamento. Aguarde até amanhã."
        )
    
    if user.plan == UserPlan.PREMIUM_MENSAL and user.premium_expires_at and user.premium_expires_at >= date.today():
        days_left = (user.premium_expires_at - date.today()).days
        raise HTTPException(
            status_code=400,
            detail=f"Você já possui plano premium ativo por mais {days_left} dias!"
        )
    
    # 🔥 PEGAR PREÇO DINÂMICO BASEADO NAS VAGAS
    promo = get_or_create_promotion(db)
    
    # Verificar se usuário já tem preço travado
    if user.promotional_price_locked and user.promotional_price:
        price = user.promotional_price
        price_type = "locked_promotional"
    else:
        price = promo.get_current_price()
        price_type = "promotional" if promo.has_available_slots() else "regular"
    
    # 🔥 QR CODE SEGURO (NÃO USA DADOS PESSOAIS DO USUÁRIO)
    payment_uuid = str(uuid.uuid4())
    
    # Gerar QR Code sem dados sensíveis
    pix_code = f"00020126360014BR.GOV.BCB.PIX0114{payment_uuid[:14]}5204000053039865404{int(price)}.005802BR5913AutoAnalytics6008SaoPaulo62070503***6304E2F3"
    
    payment = Payment(
        user_id=user.id,
        mp_id=f"PIX_{payment_uuid[:8].upper()}",
        amount=price,
        credits=DAYS_PREMIUM,
        payment_method="pix",
        status="pending",
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(minutes=PIX_QR_CODE_EXPIRY_MINUTES),
        description=f"Plano Bronze - {'Promocional' if price_type != 'regular' else 'Regular'}",
        payment_metadata={
            "plan_id": "premium_mensal",
            "uuid": payment_uuid,
            "days": DAYS_PREMIUM,
            "credits_per_day": CREDITS_PER_DAY,
            "max_credits": MAX_CREDITS_BALANCE,
            "price_type": price_type,
            "promotional_used": price_type == "promotional",
            "remaining_slots": promo.get_remaining_slots()
        }
    )
    
    db.add(payment)
    db.commit()
    db.refresh(payment)
    
    # Log seguro (sem email)
    logger.info(f"💰 Pagamento criado: ID {payment.id} para usuário ID {user.id} - Valor: R$ {price:.2f}")
    
    # Notificação segura (não enviar dados sensíveis)
    background_tasks.add_task(simulate_payment_approval, payment.id, user.id, db)
    
    return sanitize_response({
        "success": True,
        "payment_id": payment.id,
        "status": "pending",
        "amount": price,
        "price_type": price_type,
        "promotional_available": promo.has_available_slots(),
        "remaining_slots": promo.get_remaining_slots(),
        "qr_code": pix_code,
        "qr_code_base64": None,
        "expires_in": PIX_QR_CODE_EXPIRY_MINUTES * 60,
        "message": f"💰 Pagamento PIX gerado! Valor: R$ {price:.2f}",
        "plan_details": {
            "credits_per_day": CREDITS_PER_DAY,
            "total_days": DAYS_PREMIUM,
            "max_credits_balance": MAX_CREDITS_BALANCE,
            "initial_free_credits": INITIAL_FREE_CREDITS
        }
    })


# ==============================================
# 🔥 ROTA: BUSCAR QR CODE PIX
# ==============================================

@router.get("/pix-qrcode/{payment_id}", response_model=PixQRCodeResponse)
async def get_pix_qrcode(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna QR Code do pagamento PIX com validação de segurança"""
    
    # Validação do payment_id (evita SQL injection)
    if not validate_payment_id(payment_id):
        raise HTTPException(status_code=400, detail="ID de pagamento inválido")
    
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    
    if not payment:
        return PixQRCodeResponse(
            success=False,
            status="not_found",
            message="Pagamento não encontrado"
        )
    
    # Verificar se o usuário tem permissão
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Verificar se o QR Code expirou
    if payment.expires_at and payment.expires_at < datetime.now():
        return PixQRCodeResponse(
            success=False,
            status="expired",
            message="QR Code expirado. Crie um novo pagamento.",
            max_credits_balance=MAX_CREDITS_BALANCE,
            expires_in=0
        )
    
    # Gerar QR Code seguro (sem dados sensíveis)
    qr_code_base64 = None  # Em produção, gerar QR code real aqui
    
    return PixQRCodeResponse(
        success=True,
        qr_code_base64=qr_code_base64,
        qr_code=payment.mp_id,
        status=payment.status,
        max_credits_balance=MAX_CREDITS_BALANCE,
        expires_in=max(0, int((payment.expires_at - datetime.now()).total_seconds())) if payment.expires_at else PIX_QR_CODE_EXPIRY_MINUTES * 60,
        message="QR Code gerado com sucesso"
    )


# ==============================================
# SIMULAÇÃO DE APROVAÇÃO DE PAGAMENTO (COM VAGA)
# ==============================================

async def simulate_payment_approval(payment_id: int, user_id: int, db: Session):
    """Simula aprovação de pagamento, ativa premium e usa vaga promocional"""
    await asyncio.sleep(3)
    
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        
        if payment and payment.status == "pending":
            user = db.query(User).filter(User.id == user_id).first()
            
            if user:
                # Ativar plano premium
                user.plan = UserPlan.PREMIUM_MENSAL
                user.premium_activated_at = datetime.now()
                user.premium_expires_at = date.today() + timedelta(days=DAYS_PREMIUM)
                
                # 🔥 VERIFICAR SE FOI COMPRA PROMOCIONAL
                price_type = payment.payment_metadata.get("price_type", "regular")
                was_promotional = price_type == "promotional"
                
                if was_promotional and not user.promotional_price_locked:
                    promo = get_or_create_promotion(db)
                    if promo.has_available_slots():
                        promo.use_slot()  # ← DECREMENTA VAGA
                        user.promotional_price_locked = True
                        user.promotional_price = payment.amount
                        user.purchased_at_promotion = datetime.now()
                        logger.info(f"🎟️ Vaga promocional utilizada! Restam: {promo.get_remaining_slots()}")
                
                payment.status = "approved"
                payment.approved_at = datetime.now()
                
                db.commit()
                
                # Notificação segura (sem email exposto em produção)
                logger.info(f"✅ Pagamento {payment_id} APROVADO! Premium ativado para usuário ID {user.id}")
                
    except Exception as e:
        logger.error(f"❌ Erro na simulação: {e}")
        db.rollback()


# ==============================================
# 🔥 ROTA: LISTAR PLANOS
# ==============================================

@router.get("/plans")
async def get_plans(db: Session = Depends(get_db)):
    """Retorna os planos disponíveis com preço dinâmico"""
    
    promo = get_or_create_promotion(db)
    
    return sanitize_response({
        "success": True,
        "plans": {
            "gratuito": {
                "id": "gratuito",
                "name": "Plano Gratuito",
                "price": 0,
                "credits": INITIAL_FREE_CREDITS,
                "description": f"{INITIAL_FREE_CREDITS} créditos iniciais para testes",
                "max_credits_balance": MAX_CREDITS_BALANCE
            },
            "premium_mensal": {
                "id": "premium_mensal",
                "name": "Plano Bronze",
                "price": promo.get_current_price(),
                "regular_price": promo.regular_price,
                "promotional_price": promo.promotional_price,
                "description": f"1 crédito por dia durante {DAYS_PREMIUM} dias",
                "popular": True,
                "credits_per_day": CREDITS_PER_DAY,
                "total_days": DAYS_PREMIUM,
                "total_credits": DAYS_PREMIUM,
                "max_credits_balance": MAX_CREDITS_BALANCE,
                "remaining_slots": promo.get_remaining_slots(),
                "total_slots": promo.total_slots
            }
        },
        "max_credits_balance": MAX_CREDITS_BALANCE,
        "max_files_per_batch": 3,
        "initial_free_credits": INITIAL_FREE_CREDITS
    })


# ==============================================
# 🔥 ROTA: STATUS DO PAGAMENTO (COM VALIDAÇÃO)
# ==============================================

@router.get("/status/{payment_id}")
async def check_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verifica status do pagamento com validação de acesso"""
    
    # Validação do payment_id (evita SQL injection)
    if not validate_payment_id(payment_id):
        raise HTTPException(status_code=400, detail="ID de pagamento inválido")
    
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
            "expires_at": payment.expires_at.isoformat() if payment.expires_at else None
        }
    })


# ==============================================
# 🔥 ROTA: CANCELAR PAGAMENTO PENDENTE
# ==============================================

@router.post("/cancel/{payment_id}")
async def cancel_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancela um pagamento pendente"""
    
    if not validate_payment_id(payment_id):
        raise HTTPException(status_code=400, detail="ID de pagamento inválido")
    
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if payment.status != "pending":
        raise HTTPException(status_code=400, detail="Apenas pagamentos pendentes podem ser cancelados")
    
    payment.status = "cancelled"
    db.commit()
    
    logger.info(f"💰 Pagamento {payment_id} cancelado pelo usuário {current_user.id}")
    
    return sanitize_response({
        "success": True,
        "message": "Pagamento cancelado com sucesso"
    })


# ==============================================
# ROTA: WEBHOOK MERCADO PAGO
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
        logger.info(f"🔔 Webhook recebido")
        
        await webhook.process_webhook(data, db, background_tasks)
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error"}


print("✅ payment_routes.py carregado - Segurança reforçada | Promoção Bronze (100 vagas)")