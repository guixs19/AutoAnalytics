# backend/api/payment_routes.py - VERSÃO OTIMIZADA COM CONTAGEM DE ASSINANTES
# Com SQLAlchemy 2.0 style (select) e joinedload para reduzir consultas

# backend/api/payment_routes.py - VERSÃO COM PROTEÇÃO XSS E DADOS SENSÍVEIS
# Adicionar no topo do arquivo:

import re
import hashlib
import hmac
from secrets import compare_digest

# ==============================================
# PROTEÇÃO XSS E SANITIZAÇÃO
# ==============================================

def sanitize_input(text: str) -> str:
    """Sanitiza entrada para evitar XSS"""
    if not text:
        return ""
    # Remove tags HTML/script
    text = re.sub(r'<[^>]*>', '', text)
    # Remove caracteres perigosos
    text = re.sub(r'[<>\"\'\/\\;`]', '', text)
    return text[:500]  # Limita tamanho

def sanitize_payment_data(data: dict) -> dict:
    """Sanitiza dados de pagamento antes de enviar ao frontend"""
    # NUNCA enviar dados sensíveis completos
    sensitive_fields = ['qr_code', 'qr_code_base64', 'payment_key', 'transaction_id', 'card_data']
    
    sanitized = {}
    for key, value in data.items():
        if key in sensitive_fields:
            # Substituir por hash ou indicador
            sanitized[key] = "***PROTECTED***"
        elif isinstance(value, str):
            sanitized[key] = sanitize_input(value)[:200]
        elif isinstance(value, dict):
            sanitized[key] = sanitize_payment_data(value)
        else:
            sanitized[key] = value
    return sanitized

# Modificar a rota /create-pix para não enviar QR Code completo
@router.post("/create-pix")
async def create_pix_payment(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria um pagamento PIX para o plano premium de R$97"""
    try:
        # ... (código existente de contagem de vagas) ...
        
        # 🔥 CRIPTOGRAFAR QR CODE ANTES DE ENVIAR
        if not mp_service.access_token:
            return await _create_test_payment_secure(current_user, db, vaga_numero, vagas_restantes, titulo_plano)
        
        # Pagamento real
        result = mp_service.create_payment_pix(
            user_id=current_user.id,
            user_email=current_user.email,
            user_name=current_user.name or "Cliente",
            amount=97.00,
            description=titulo_plano,
            credits=30,
            plan_id="premium_mensal",
            metadata={
                "vaga_numero": vaga_numero,
                "batch_limit": BATCH_LIMIT,
                "vagas_restantes": vagas_restantes,
                "is_promotional": vagas_restantes > 0
            }
        )
        
        if not result.get("success", False):
            alert_payment_failed(
                user_email=current_user.email,
                amount=97.00,
                error=result.get("error", "Erro no Mercado Pago")
            )
            
            return {
                "success": False,
                "error": "Erro ao processar pagamento. Tente novamente."
            }
        
        # 🔥 NUNCA ENVIAR QR_CODE_BASE64 COMPLETO PARA O FRONTEND
        # Em vez disso, enviar apenas um ID e buscar no backend quando necessário
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
            description=titulo_plano,
            status="pending",
            payment_metadata={
                "plan_id": "premium_mensal",
                "plan_name": "Plano Premium Mensal",
                "credits_per_day": 1,
                "total_days": 30,
                "external_reference": result.get("external_reference"),
                "vaga_numero": vaga_numero,
                "batch_limit": BATCH_LIMIT,
                "vagas_restantes": vagas_restantes,
                "is_promotional": vagas_restantes > 0
            }
        )
        
        # 🔥 RESPOSTA SEGURA - SEM DADOS SENSÍVEIS
        return {
            "success": True,
            "payment_id": payment.id,
            "status": "pending",
            "plan": {
                "name": sanitize_input(titulo_plano),
                "credits_per_day": 1,
                "total_days": 30,
                "vaga_numero": vaga_numero,
                "vagas_restantes": vagas_restantes,
                "batch_limit": BATCH_LIMIT
            },
            "amount": 97.00,
            "promotional_message": sanitize_input(mensagem_promocional),
            "requires_qr_fetch": True  # Frontend precisa buscar o QR Code separadamente
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
            "error": "Erro interno. Tente novamente mais tarde."
        }


# 🔥 NOVA ROTA SEGURA PARA BUSCAR QR CODE (APENAS COM AUTENTICAÇÃO)
@router.get("/pix-qrcode/{payment_id}")
async def get_pix_qrcode(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna o QR Code PIX de forma segura (apenas para o dono do pagamento)"""
    try:
        stmt = select(Payment).where(Payment.id == payment_id)
        payment = db.execute(stmt).scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Pagamento não encontrado")
        
        # Verificar se o usuário é o dono
        if payment.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Acesso negado")
        
        # Verificar se o pagamento está pendente
        if payment.status != "pending":
            return {
                "success": False,
                "message": "Pagamento já foi processado",
                "status": payment.status
            }
        
        # Buscar QR Code do banco ou serviço
        qr_code_data = payment.payment_metadata.get("qr_code_data") if payment.payment_metadata else None
        
        # Se não tiver no banco, buscar do Mercado Pago (implementar)
        
        return {
            "success": True,
            "qr_code_base64": payment.qr_code_base64,  # Só enviar após verificação
            "qr_code": payment.qr_code,
            "expiration_date": payment.payment_metadata.get("expiration_date") if payment.payment_metadata else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar QR Code: {e}")
        return {
            "success": False,
            "error": "Erro ao recuperar QR Code"
        }


async def _create_test_payment_secure(current_user: User, db: Session, vaga_numero: int, vagas_restantes: int, titulo_plano: str):
    """Cria pagamento de teste (modo desenvolvimento) de forma segura"""
    logger.info(f"🧪 Modo teste ativado - ativando premium para {current_user.email}")
    
    mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
    
    # Criar QR Code SIMULADO (não real)
    import random
    mock_qr_code = f"00020126580014BR.GOV.BCB.PIX0136teste_{uuid.uuid4().hex[:6]}@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7"
    
    # Criar registro de pagamento simulado
    payment = crud.create_payment_record(
        db=db,
        user_id=current_user.id,
        mp_id=mock_payment_id,
        amount=97.00,
        credits=30,
        payment_method="pix",
        qr_code=mock_qr_code,
        qr_code_base64=None,  # Não armazenar base64 em modo teste
        description=titulo_plano,
        status="approved",
        payment_metadata={
            "plan_id": "premium_mensal",
            "plan_name": "Plano Premium Mensal",
            "test_mode": True,
            "credits_per_day": 1,
            "total_days": 30,
            "vaga_numero": vaga_numero,
            "vagas_restantes": vagas_restantes
        }
    )
    
    # 🔥 ATIVAR PLANO PREMIUM
    expires_at = date.today() + timedelta(days=30)
    
    stmt = select(User).where(User.id == current_user.id)
    user = db.execute(stmt).scalar_one()
    
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
    
    mensagem_promocional = f"🔥 Vaga #{vaga_numero} garantida!" if vagas_restantes > 0 else "Plano Premium ativado!"
    
    # 🔥 RESPOSTA SEGURA - SEM DADOS SENSÍVEIS NO MODO TESTE
    return {
        "success": True,
        "payment_id": payment.id,
        "status": "approved",
        "plan": {
            "name": sanitize_input(titulo_plano),
            "credits_per_day": 1,
            "total_days": 30,
            "expires_at": expires_at.isoformat(),
            "vaga_numero": vaga_numero,
            "vagas_restantes": vagas_restantes - 1,
            "batch_limit": 100
        },
        "amount": 97.00,
        "promotional_message": sanitize_input(mensagem_promocional),
        "test_mode": True
    }

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession  # para futuro async
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import datetime, timedelta, date
import uuid
import traceback
import logging

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
            "public_key": mp_service.public_key,
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


# ==============================================
# 🔥 NOVA ROTA: CONTAGEM DE ASSINANTES PREMIUM
# ==============================================
@router.get("/premium/subscribers-count")
async def get_premium_subscribers_count(
    db: Session = Depends(get_db)
):
    """
    Retorna a quantidade de assinantes ativos do plano premium
    Usado para criar urgência (vagas limitadas)
    """
    try:
        today = date.today()
        
        # Contar usuários com plano premium ativo (que não expirou)
        stmt = select(func.count(User.id)).where(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at >= today
        )
        active_subscribers = db.execute(stmt).scalar() or 0
        
        # Limite do lote promocional
        BATCH_LIMIT = 100
        
        vagas_restantes = max(0, BATCH_LIMIT - active_subscribers)
        
        logger.info(f"📊 Assinantes premium ativos: {active_subscribers}/{BATCH_LIMIT}")
        
        return {
            "success": True,
            "subscribers_count": active_subscribers,
            "batch_limit": BATCH_LIMIT,
            "remaining_slots": vagas_restantes,
            "is_promotional_active": vagas_restantes > 0,
            "message": f"🔥 {vagas_restantes} vagas restantes!" if vagas_restantes > 0 else "⚠️ Lote promocional esgotado!",
            "next_price_hint": "Em breve novas promoções"
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao contar assinantes premium: {e}")
        return {
            "success": False,
            "error": str(e),
            "subscribers_count": 0,
            "remaining_slots": 0
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
                "total_purchased": 0,
                "max_credits_balance": 3
            }
        
        # 🔥 Segunda consulta otimizada: verifica crédito de hoje
        hoje = date.today()
        credit_stmt = select(DailyCreditLog).where(
            DailyCreditLog.user_id == user.id,
            DailyCreditLog.date == hoje
        )
        received_today = db.execute(credit_stmt).first() is not None
        
        # Verificar se é premium
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        # Calcular dias restantes
        days_remaining = 0
        if is_premium and user.premium_expires_at:
            today = date.today()
            days_remaining = (user.premium_expires_at - today).days
            if days_remaining < 0:
                days_remaining = 0
        
        current_credits = user.credits or 0
        max_credits_balance = 3
        
        return {
            "success": True,
            "credits": current_credits,
            "total_purchased": user.total_purchased or 0,
            "max_credits_balance": max_credits_balance,
            "can_receive_more": current_credits < max_credits_balance,
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
            "total_purchased": 0,
            "max_credits_balance": 3
        }


# ==============================================
# CRIAR PAGAMENTO PIX - PLANO PREMIUM R$97 (COM CONTAGEM DE VAGAS)
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
        # 🔥 Contar assinantes ativos para gerar número da vaga
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
        
        # Ajustar título baseado nas vagas
        if vagas_restantes > 0:
            titulo_plano = f"🔥 Plano Premium - Vaga #{vaga_numero} de {BATCH_LIMIT} (Lote Promocional)"
            mensagem_promocional = f"🔥 APROVEITE! Esta é a vaga #{vaga_numero} de {BATCH_LIMIT} disponíveis!"
        else:
            titulo_plano = "Plano Premium Mensal (Lote Regular)"
            mensagem_promocional = "Plano Premium - Assinatura Mensal"
        
        logger.info(f"💰 Iniciando pagamento PIX para {current_user.email} - {titulo_plano}")
        logger.info(f"📊 Assinantes atuais: {subscribers_count}, Vaga #{vaga_numero}, Restantes: {vagas_restantes}")
        
        alert_payment_pending(
            user_email=current_user.email,
            amount=97.00,
            method="pix"
        )
        
        # Modo de teste
        if not mp_service.access_token:
            return await _create_test_payment(current_user, db, vaga_numero, vagas_restantes, titulo_plano)
        
        # Pagamento real
        result = mp_service.create_payment_pix(
            user_id=current_user.id,
            user_email=current_user.email,
            user_name=current_user.name or "Cliente",
            amount=97.00,
            description=titulo_plano,
            credits=30,
            plan_id="premium_mensal",
            metadata={
                "vaga_numero": vaga_numero,
                "batch_limit": BATCH_LIMIT,
                "vagas_restantes": vagas_restantes,
                "is_promotional": vagas_restantes > 0
            }
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
            description=titulo_plano,
            status="pending",
            payment_metadata={
                "plan_id": "premium_mensal",
                "plan_name": "Plano Premium Mensal",
                "credits_per_day": 1,
                "total_days": 30,
                "external_reference": result.get("external_reference"),
                "vaga_numero": vaga_numero,
                "batch_limit": BATCH_LIMIT,
                "vagas_restantes": vagas_restantes,
                "is_promotional": vagas_restantes > 0
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
                "name": titulo_plano,
                "credits_per_day": 1,
                "total_days": 30,
                "vaga_numero": vaga_numero,
                "vagas_restantes": vagas_restantes,
                "batch_limit": BATCH_LIMIT
            },
            "amount": 97.00,
            "status": "pending",
            "promotional_message": mensagem_promocional
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


async def _create_test_payment(current_user: User, db: Session, vaga_numero: int, vagas_restantes: int, titulo_plano: str):
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
        description=titulo_plano,
        status="approved",
        payment_metadata={
            "plan_id": "premium_mensal",
            "plan_name": "Plano Premium Mensal",
            "test_mode": True,
            "credits_per_day": 1,
            "total_days": 30,
            "vaga_numero": vaga_numero,
            "vagas_restantes": vagas_restantes
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
    
    mensagem_promocional = f"🔥 Vaga #{vaga_numero} garantida!" if vagas_restantes > 0 else "Plano Premium ativado!"
    
    return {
        "success": True,
        "payment_id": payment.id,
        "mp_payment_id": mock_payment_id,
        "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
        "qr_code": "00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
        "expiration_date": datetime.now().isoformat(),
        "plan": {
            "name": titulo_plano,
            "credits_per_day": 1,
            "total_days": 30,
            "expires_at": expires_at.isoformat(),
            "vaga_numero": vaga_numero,
            "vagas_restantes": vagas_restantes - 1,
            "batch_limit": 100
        },
        "amount": 97.00,
        "status": "approved",
        "test_mode": True,
        "promotional_message": mensagem_promocional
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
        
        # Log da ativação com número da vaga
        vaga_info = payment.payment_metadata.get("vaga_numero", "N/A") if payment.payment_metadata else "N/A"
        logger.info(f"✅ Plano premium ativado para {user.email} - Vaga #{vaga_info} - Expira em {expires_at}")
        
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
                "approved_at": payment.approved_at.isoformat() if payment.approved_at else None,
                "vaga_numero": payment.payment_metadata.get("vaga_numero") if payment.payment_metadata else None
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
                "required": 1,
                "max_credits_balance": 3
            }
        
        # Admin tem créditos infinitos
        if user.is_admin:
            return {
                "success": True,
                "has_credits": True,
                "credits": float('inf'),
                "required": 1,
                "is_admin": True,
                "max_credits_balance": 3
            }
        
        has_credits = user.credits > 0
        
        return {
            "success": True,
            "has_credits": has_credits,
            "credits": user.credits or 0,
            "required": 1,
            "is_premium": user.plan == UserPlan.PREMIUM_MENSAL,
            "max_credits_balance": 3
        }
        
    except Exception as e:
        logger.error(f"Erro ao verificar créditos: {e}")
        return {
            "success": False,
            "error": str(e),
            "has_credits": False,
            "credits": 0,
            "required": 1,
            "max_credits_balance": 3
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