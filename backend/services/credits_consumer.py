# backend/services/credits_consumer.py
"""
Serviço para consumo de créditos em análises
COM SUPORTE PARA PLANO PREMIUM E LIMITE DE 3 CRÉDITOS
"""
import logging
from sqlalchemy.orm import Session
from backend.models import User, UserPlan
from backend.services.daily_credits_service import DailyCreditsService
from backend.crud import safe_commit

logger = logging.getLogger(__name__)

# Instância do serviço de créditos diários
daily_credits_service = DailyCreditsService()


def _is_premium_user(user: User) -> bool:
    """
    🔥 FUNÇÃO AUXILIAR: Verifica se usuário tem plano premium ativo
    Lida corretamente com Enum do SQLAlchemy, comparando valor ou objeto
    """
    if not user:
        return False
    
    # Se user.is_premium() existe e é confiável, usar ele primeiro
    if hasattr(user, 'is_premium') and callable(user.is_premium):
        return user.is_premium()
    
    # Caso contrário, verificar o plan manualmente
    plan = user.plan
    
    # Se for Enum do SQLAlchemy
    if hasattr(plan, 'value'):
        return plan.value == "premium_mensal"
    elif hasattr(plan, 'name'):
        return plan.name == "PREMIUM_MENSAL"
    else:
        return plan == "premium_mensal"


def _get_plan_value(user: User) -> str:
    """
    🔥 FUNÇÃO AUXILIAR: Retorna o valor do plano como string
    Normaliza Enum para string de forma segura
    """
    if not user:
        return "basico"
    
    plan = user.plan
    
    if hasattr(plan, 'value'):
        return plan.value
    elif hasattr(plan, 'name'):
        return plan.name.lower()
    else:
        return str(plan).lower()


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
        is_premium = _is_premium_user(user)
        
        if is_premium:
            # Verificar status do crédito premium
            status = daily_credits_service.check_premium_daily_credit(db, user.id)
            if status.get('can_receive_today'):
                logger.info(f"⭐ Premium {user.email} pode ganhar crédito hoje - sugerir ação")
                return False
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
    
    🔥 safe_commit já trata rollback automático em caso de erro
    """
    # Admin não consome créditos
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} realizou análise sem consumir créditos")
        return True
    
    # Verificar se tem créditos
    if user.credits < required_credits:
        logger.warning(f"❌ Usuário {user.email} tentou consumir {required_credits} créditos mas só tem {user.credits}")
        return False
    
    old_credits = user.credits
    user.credits -= required_credits
    
    try:
        # safe_commit já faz rollback interno em caso de erro
        safe_commit(db, f"Erro ao consumir créditos de análise para o usuário {user.email}")
    except Exception as e:
        logger.error(f"❌ Falha crítica no banco ao consumir crédito para {user.email}: {e}")
        return False

    # Executado APENAS se o commit correu bem
    logger.info(f"💰 Usuário {user.email} consumiu {required_credits} crédito(s). Antes: {old_credits}, Agora: {user.credits}")
    
    if _is_premium_user(user) and user.credits < 3:
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
    
    is_premium = _is_premium_user(user)
    
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
    
    is_premium = _is_premium_user(user)
    
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
        "days_left": status.get('days_left', 0),
        "timezone": status.get('timezone', 'America/Sao_Paulo (UTC-3)')
    }


def award_daily_credit(db: Session, user: User) -> dict:
    """
    Concede crédito diário para usuário premium
    Retorna resultado da operação
    """
    result = daily_credits_service.check_and_add_daily_credit(db, user.id)
    return result


def add_credits_safe(db: Session, user: User, amount: int, description: str = "") -> bool:
    """
    Adiciona créditos ao usuário com commit seguro
    
    Args:
        db: Sessão do banco
        user: Usuário
        amount: Quantidade de créditos a adicionar
        description: Descrição do motivo (para log)
    
    Returns:
        bool: True se sucesso, False se erro
    """
    if not user or amount <= 0:
        logger.warning(f"⚠️ Tentativa inválida de adicionar {amount} créditos")
        return False
    
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} - créditos ilimitados (operação ignorada)")
        return True
    
    # Verificar limite para premium
    is_premium = _is_premium_user(user)
    max_credits = 3 if is_premium else float('inf')
    
    if user.credits + amount > max_credits:
        logger.warning(f"⚠️ {user.email} excederia limite de {max_credits} créditos")
        return False
    
    old_credits = user.credits
    user.credits += amount
    
    try:
        safe_commit(db, f"Erro ao adicionar {amount} créditos para {user.email}")
        logger.info(f"💰 {user.email} recebeu +{amount} créditos ({description}). Antes: {old_credits}, Agora: {user.credits}")
        return True
    except Exception as e:
        logger.error(f"❌ Falha crítica ao adicionar créditos para {user.email}: {e}")
        return False