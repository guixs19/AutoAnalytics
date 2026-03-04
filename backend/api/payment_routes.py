# backend/api/payment_routes.py
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json
import os
import uuid

from backend.database import get_db
from backend import crud
from backend.security import get_current_user
from backend.models import User, PaymentStatus
from backend.services.payment_service import MercadoPagoService

router = APIRouter(prefix="/payments", tags=["payments"])
mp_service = MercadoPagoService()

# ==============================================
# PLANOS DISPONÍVEIS
# ==============================================
@router.get("/plans")
async def get_plans():
    """Retorna planos disponíveis (público)"""
    try:
        return {
            "success": True,
            "plans": mp_service.plans,
            "public_key": mp_service.public_key
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "plans": {
                "basico": {
                    "id": "basico",
                    "name": "Básico",
                    "credits": 10,
                    "price": 29.90,
                    "description": "10 análises - Ideal para começar",
                    "popular": False
                },
                "profissional": {
                    "id": "profissional",
                    "name": "Profissional",
                    "credits": 30,
                    "price": 79.90,
                    "description": "30 análises - Para uso regular",
                    "popular": True
                },
                "empresarial": {
                    "id": "empresarial",
                    "name": "Empresarial",
                    "credits": 100,
                    "price": 199.90,
                    "description": "100 análises - Uso intensivo",
                    "popular": False
                }
            }
        }

# ==============================================
# SALDO DO USUÁRIO
# ==============================================
@router.get("/balance")
async def get_user_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna saldo de créditos do usuário"""
    try:
        # Refresh para garantir dados atualizados
        db.refresh(current_user)
        
        return {
            "success": True,
            "credits": current_user.credits or 0,
            "total_purchased": current_user.total_purchased or 0,
            "last_payment": current_user.last_payment_date.isoformat() if current_user.last_payment_date else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "credits": 0,
            "total_purchased": 0,
            "last_payment": None
        }

# ==============================================
# CRIAR PAGAMENTO PIX
# ==============================================
@router.post("/create-pix")
async def create_pix_payment(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cria um pagamento PIX (QR Code gerado diretamente)
    """
    try:
        # Tentar ler JSON do corpo da requisição
        try:
            data = await request.json()
        except:
            data = {}
        
        plan_id = data.get("plan_id", "basico")
        
        # Verificar se o MP service está configurado
        if not mp_service.access_token:
            # Modo de teste/simulação
            mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
            
            # Criar registro de pagamento simulado
            payment = crud.create_payment_record(
                db=db,
                user_id=current_user.id,
                mp_id=mock_payment_id,
                amount=29.90,
                credits=10,
                payment_method="pix",
                qr_code="00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
                qr_code_base64="iVBORw0KGgoAAAANSUhEUgAA...",  # Base64 simulado
                description="10 créditos - Modo Teste",
                payment_metadata={
                    "plan_id": plan_id,
                    "plan_name": "Básico (Teste)",
                    "test_mode": True
                }
            )
            
            return {
                "success": True,
                "payment_id": payment.id,
                "mp_payment_id": mock_payment_id,
                "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",  # Base64 simulado
                "qr_code": "00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
                "expiration_date": (datetime.now().isoformat()),
                "credits": 10,
                "amount": 29.90,
                "status": "pending",
                "test_mode": True
            }
        
        # Validar plano
        if plan_id not in mp_service.plans:
            plan_id = "basico"  # Fallback para plano básico
        
        plan = mp_service.plans[plan_id]
        
        # Criar pagamento PIX
        result = mp_service.create_payment_pix(
            user_id=current_user.id,
            user_email=current_user.email,
            user_name=current_user.name or "Cliente",
            amount=plan["price"],
            description=plan["description"],
            credits=plan["credits"],
            plan_id=plan_id
        )
        
        if not result.get("success", False):
            # Fallback para modo de teste
            mock_payment_id = f"PIX_{uuid.uuid4().hex[:8].upper()}"
            
            payment = crud.create_payment_record(
                db=db,
                user_id=current_user.id,
                mp_id=mock_payment_id,
                amount=plan["price"],
                credits=plan["credits"],
                payment_method="pix",
                qr_code="00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
                qr_code_base64="iVBORw0KGgoAAAANSUhEUgAA...",
                description=plan["description"],
                payment_metadata={
                    "plan_id": plan_id,
                    "plan_name": plan["name"],
                    "test_mode": True,
                    "error": result.get("error", "Erro no MP")
                }
            )
            
            return {
                "success": True,
                "payment_id": payment.id,
                "mp_payment_id": mock_payment_id,
                "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
                "qr_code": "00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
                "expiration_date": datetime.now().isoformat(),
                "credits": plan["credits"],
                "amount": plan["price"],
                "status": "pending",
                "test_mode": True
            }
        
        # Salvar no banco
        payment = crud.create_payment_record(
            db=db,
            user_id=current_user.id,
            mp_id=result.get("payment_id", f"PIX_{uuid.uuid4().hex[:8]}"),
            amount=plan["price"],
            credits=plan["credits"],
            payment_method="pix",
            qr_code=result.get("qr_code"),
            qr_code_base64=result.get("qr_code_base64"),
            qr_code_url=result.get("qr_code_url"),
            description=plan["description"],
            payment_metadata={
                "plan_id": plan_id,
                "plan_name": plan["name"],
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
            "credits": plan["credits"],
            "amount": plan["price"],
            "status": result.get("status", "pending")
        }
        
    except Exception as e:
        print(f"❌ Erro no create-pix: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback: retornar resposta de teste
        return {
            "success": True,
            "payment_id": 0,
            "mp_payment_id": f"PIX_{uuid.uuid4().hex[:8].upper()}",
            "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
            "qr_code": "00020126580014BR.GOV.BCB.PIX0136teste@simulacao.com520400005303986540410.005802BR5913TesteSimulado6008BRASILIA62070503***6304E2B7",
            "expiration_date": datetime.now().isoformat(),
            "credits": 10,
            "amount": 29.90,
            "status": "pending",
            "test_mode": True,
            "error_details": str(e)
        }

# ==============================================
# CRIAR CHECKOUT (LINK DE PAGAMENTO)
# ==============================================
@router.post("/create-checkout")
async def create_checkout(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cria um link de checkout (página do Mercado Pago)
    """
    try:
        # Tentar ler JSON
        try:
            data = await request.json()
        except:
            data = {}
        
        plan_id = data.get("plan_id", "basico")
        
        # Validar plano
        if plan_id not in mp_service.plans:
            plan_id = "basico"
        
        plan = mp_service.plans[plan_id]
        
        # Criar preferência de checkout
        if mp_service.access_token:
            result = mp_service.create_checkout_preference(
                user_id=current_user.id,
                user_email=current_user.email,
                user_name=current_user.name or "Cliente",
                amount=plan["price"],
                description=plan["description"],
                credits=plan["credits"],
                plan_id=plan_id
            )
        else:
            # Modo de teste
            result = {
                "success": True,
                "preference_id": f"TEST_{uuid.uuid4().hex[:8]}",
                "init_point": f"/checkout/test?plan={plan_id}",
                "credits": plan["credits"],
                "amount": plan["price"]
            }
        
        # Salvar no banco
        payment = crud.create_payment_record(
            db=db,
            user_id=current_user.id,
            mp_id=result.get("preference_id", f"CHECKOUT_{uuid.uuid4().hex[:8]}"),
            amount=plan["price"],
            credits=plan["credits"],
            payment_method="checkout",
            checkout_url=result.get("init_point", "#"),
            preference_id=result.get("preference_id"),
            description=plan["description"],
            payment_metadata={
                "plan_id": plan_id,
                "plan_name": plan["name"],
                "external_reference": result.get("external_reference"),
                "type": "checkout"
            }
        )
        
        return {
            "success": True,
            "payment_id": payment.id,
            "preference_id": result.get("preference_id"),
            "checkout_url": result.get("init_point", "#"),
            "credits": plan["credits"],
            "amount": plan["price"]
        }
        
    except Exception as e:
        print(f"❌ Erro no create-checkout: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ==============================================
# WEBHOOK DO MERCADO PAGO
# ==============================================
@router.post("/webhook")
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Webhook para receber notificações do Mercado Pago
    """
    try:
        body = await request.body()
        
        # Tentar parsear JSON
        try:
            data = await request.json()
        except:
            data = {}
        
        print(f"🔔 Webhook recebido: {json.dumps(data, indent=2)[:200]}...")
        
        # Extrair payment_id
        payment_id = None
        if data.get("data") and data["data"].get("id"):
            payment_id = str(data["data"]["id"])
        elif data.get("id"):
            payment_id = str(data["id"])
        
        if not payment_id:
            return {"status": "ignored", "message": "No payment_id"}
        
        # Buscar pagamento
        payment = crud.get_payment_by_mp_id(db, payment_id)
        
        if payment and payment.status != PaymentStatus.APPROVED:
            # Simular aprovação para teste
            background_tasks.add_task(
                simulate_payment_approval,
                db, payment.id, payment.user_id, payment.credits
            )
        
        return {"status": "received", "payment_id": payment_id}
        
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}

# Função para simular aprovação de pagamento (para teste)
async def simulate_payment_approval(db: Session, payment_id: int, user_id: int, credits: int):
    """Simula aprovação de pagamento (apenas para teste)"""
    try:
        # Aguardar alguns segundos para simular processamento
        import asyncio
        await asyncio.sleep(5)
        
        # Atualizar status
        crud.update_payment_status(db, payment_id, PaymentStatus.APPROVED)
        
        # Adicionar créditos
        crud.add_credits(db, user_id, credits)
        
        print(f"💰 Pagamento {payment_id} simulado como aprovado! {credits} créditos adicionados")
    except Exception as e:
        print(f"❌ Erro na simulação: {e}")

# ==============================================
# VERIFICAR STATUS DO PAGAMENTO
# ==============================================
@router.get("/status/{payment_id}")
async def check_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verifica status de um pagamento específico
    """
    try:
        # Buscar pagamento
        from backend.models import Payment
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        
        if not payment:
            return {
                "success": False,
                "error": "Pagamento não encontrado"
            }
        
        # Verificar se pertence ao usuário
        if payment.user_id != current_user.id:
            return {
                "success": False,
                "error": "Acesso negado"
            }
        
        return {
            "success": True,
            "payment": payment.to_dict() if hasattr(payment, 'to_dict') else {
                "id": payment.id,
                "status": payment.status.value if hasattr(payment.status, 'value') else str(payment.status),
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
# HISTÓRICO DE PAGAMENTOS
# ==============================================
@router.get("/history")
async def get_payment_history(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna histórico de pagamentos do usuário
    """
    try:
        from backend.models import Payment
        payments = db.query(Payment).filter(
            Payment.user_id == current_user.id
        ).order_by(Payment.created_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "payments": [p.to_dict() if hasattr(p, 'to_dict') else {
                "id": p.id,
                "amount": p.amount,
                "credits": p.credits,
                "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
                "payment_method": p.payment_method,
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p in payments]
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "payments": []
        }

# ==============================================
# VERIFICAR CRÉDITOS PARA ANÁLISE
# ==============================================
@router.get("/check-analysis")
async def check_analysis_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verifica se usuário tem créditos para realizar análise
    """
    try:
        # Refresh para garantir dados atualizados
        db.refresh(current_user)
        
        has_credits = current_user.credits > 0 if current_user else False
        
        return {
            "success": True,
            "has_credits": has_credits,
            "credits": current_user.credits if current_user else 0,
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
# CALLBACKS (para retorno do Mercado Pago)
# ==============================================
@router.get("/success")
async def payment_success(
    payment_id: str = None,
    status: str = None,
    external_reference: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
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