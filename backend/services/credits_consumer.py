# backend/services/credits_consumer.py
"""
Serviço para consumo de créditos em análises
"""
import logging
from sqlalchemy.orm import Session
from backend.models import User

logger = logging.getLogger(__name__)

def can_perform_analysis(user: User, required_credits: int = 1) -> bool:
    """
    Verifica se usuário pode realizar uma análise
    
    ✅ Admin sempre pode
    Usuário comum precisa ter créditos suficientes
    """
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} pode realizar análise (ilimitado)")
        return True
    
    has_credits = user.credits >= required_credits
    
    if not has_credits:
        logger.warning(f"Usuário {user.email} não tem créditos suficientes. Tem: {user.credits}, Necessário: {required_credits}")
    
    return has_credits

def consume_analysis_credit(user: User, db: Session, required_credits: int = 1) -> bool:
    """
    Consome crédito de uma análise
    
    ✅ Admin não consome nada
    Usuário comum consome 1 crédito
    """
    # Admin não consome créditos
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} realizou análise sem consumir créditos")
        return True
    
    # Verificar se tem créditos
    if user.credits < required_credits:
        logger.warning(f"Usuário {user.email} tentou consumir {required_credits} créditos mas só tem {user.credits}")
        return False
    
    # Consumir crédito
    old_credits = user.credits
    user.credits -= required_credits
    db.commit()
    
    logger.info(f"Usuário {user.email} consumiu {required_credits} crédito(s). Antes: {old_credits}, Agora: {user.credits}")
    return True

def get_credits_display(user: User) -> str:
    """
    Retorna string formatada para exibição dos créditos
    
    Admin: "∞" (infinito)
    Usuário: número normal
    """
    if user.is_admin:
        return "∞"
    return str(user.credits)