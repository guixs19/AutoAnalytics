# backend/services/credits_consumer.py
"""
Serviço para consumo de créditos em análises
COM SUPORTE PARA PLANO PREMIUM E LIMITE DE 3 CRÉDITOS
"""
import logging
from sqlalchemy.orm import Session
from backend.models import User
from backend.services.daily_credits_service import DailyCreditsService

logger = logging.getLogger(__name__)

# Instância do serviço de créditos diários
daily_credits_service = DailyCreditsService()


def can_perform_analysis(db: Session, user: User, required_credits: int = 1) -> bool:
    """
    Verifica se usuário pode realizar uma análise
    
    ✅ Admin sempre pode
    ⭐ Premium verifica saldo (respeitando limite de 3)
    💰 Comum verifica saldo normal
    """
    # Admin tem acesso ilimitado
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} pode realizar análise (ilimitado)")
        return True
    
    # Verificar se tem créditos suficientes
    has_credits = user.credits >= required_credits
    
    if not has_credits:
        # Verificar se é premium e pode ganhar crédito hoje
        is_premium = user.plan.value == "premium_mensal" and user.is_premium() if hasattr(user, 'is_premium') else False
        
        if is_premium:
            # Verificar status do crédito premium
            status = daily_credits_service.check_premium_daily_credit(db, user.id)
            if status.get('can_receive_today'):
                logger.info(f"⭐ Premium {user.email} pode ganhar crédito hoje - sugerir ação")
                return False  # Ainda não tem crédito, mas poderia ganhar
            elif status.get('max_credits_reached'):
                logger.warning(f"⚠️ Premium {user.email} atingiu limite de 3 créditos")
        
        logger.warning(f"❌ Usuário {user.email} não tem créditos suficientes. Tem: {user.credits}, Necessário: {required_credits}")
    
    return has_credits


def consume_analysis_credit(user: User, db: Session, required_credits: int = 1) -> bool:
    """
    Consome crédito de uma análise
    
    ✅ Admin não consome nada
    ⭐ Premium consome normalmente
    💰 Usuário comum consome normalmente
    """
    # Admin não consome créditos
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} realizou análise sem consumir créditos")
        return True
    
    # Verificar se tem créditos
    if user.credits < required_credits:
        logger.warning(f"❌ Usuário {user.email} tentou consumir {required_credits} créditos mas só tem {user.credits}")
        return False
    
    # Consumir crédito
    old_credits = user.credits
    user.credits -= required_credits
    db.commit()
    
    logger.info(f"💰 Usuário {user.email} consumiu {required_credits} crédito(s). Antes: {old_credits}, Agora: {user.credits}")
    
    # Se for premium, verificar se atingiu limite após consumo
    is_premium = user.plan.value == "premium_mensal" if hasattr(user.plan, 'value') else False
    if is_premium and user.credits < 3:
        logger.info(f"⭐ Premium {user.email} agora tem {user.credits}/3 créditos - pode receber mais")
    
    return True


def get_credits_display(user: User) -> str:
    """
    Retorna string formatada para exibição dos créditos
    
    Admin: "∞" (infinito)
    Premium: "X/3" (mostra limite)
    Usuário: número normal
    """
    if user.is_admin:
        return "∞"
    
    # Verificar se é premium (tem limite de 3)
    is_premium = user.plan.value == "premium_mensal" if hasattr(user.plan, 'value') else False
    
    if is_premium:
        return f"{user.credits}/3"
    
    return str(user.credits)


def get_credits_balance(user: User) -> int:
    """Retorna saldo numérico de créditos (admin retorna 999999)"""
    if user.is_admin:
        return 999999
    return user.credits or 0


def can_receive_daily_credit(db: Session, user: User) -> dict:
    """
    Verifica se usuário premium pode receber crédito diário
    Retorna dicionário com status e mensagem
    """
    if user.is_admin:
        return {
            "can_receive": False,
            "message": "Admin tem créditos ilimitados",
            "is_premium": False
        }
    
    # Verificar se é premium
    is_premium = user.plan.value == "premium_mensal" and user.is_premium() if hasattr(user, 'is_premium') else False
    
    if not is_premium:
        return {
            "can_receive": False,
            "message": "Assine o plano premium para ganhar créditos diários",
            "is_premium": False
        }
    
    # Verificar status do crédito premium
    status = daily_credits_service.check_premium_daily_credit(db, user.id)
    
    return {
        "can_receive": status.get('can_receive_today', False),
        "message": status.get('message', ''),
        "is_premium": True,
        "received_today": status.get('received_today', False),
        "max_credits_reached": status.get('max_credits_reached', False),
        "credits_balance": status.get('credits_balance', user.credits),
        "max_credits": status.get('max_credits', 3),
        "days_left": status.get('days_left', 0)
    }


def award_daily_credit(db: Session, user: User) -> dict:
    """
    Concede crédito diário para usuário premium
    Retorna resultado da operação
    """
    result = daily_credits_service.check_and_add_daily_credit(db, user.id)
    return result