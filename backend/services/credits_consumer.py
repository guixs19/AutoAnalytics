# backend/services/credits_consumer.py - VERSÃO 2.3
"""
Serviço para consumo de créditos em análises
COM SUPORTE PARA PLANO PREMIUM E LIMITE DE 3 CRÉDITOS

🔥 REGRAS V2.3:
   - FREE: Consome créditos, NÃO ganha bônus ao zerar
   - PREMIUM: Consome créditos, ganha bônus automático se zerar E não recebeu hoje
   - PREMIUM: Só ganha se saldo < 3 e NÃO recebeu hoje
   - 👑 Admin: créditos ilimitados, não consome

🔥 MELHORIAS v2.3:
   - ✅ Usa get_credit_eligibility() do crud
   - ✅ Usa manage_credits_after_consumption() para consumo unificado
   - ✅ FREE explicitamente bloqueado de ganhar bônus
   - ✅ Logs mais informativos
   - ✅ Funções simplificadas e consistentes
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
    
    🔥 V2.3: Usa get_credit_eligibility() para verificação consistente
    
    ✅ Admin sempre pode
    ⭐ Premium verifica saldo (respeitando limite de 3)
    💰 Comum verifica saldo normal
    
    Retorna:
        bool: True se pode realizar a análise
    """
    # 👑 Admin tem acesso ilimitado
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} pode realizar análise (ilimitado)")
        return True
    
    # 🔥 Verificar se tem créditos suficientes
    has_credits = user.credits >= required_credits
    
    if not has_credits:
        # 🔥 USAR FUNÇÃO DE ELEGIBILIDADE DO CRUD
        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)
        
        is_premium = eligibility.get("is_premium", False)
        
        if is_premium:
            # ⭐ Premium: verifica se pode receber crédito hoje
            if eligibility.get("can_receive_today", False):
                logger.info(f"⭐ Premium {user.email} pode ganhar crédito hoje - sugerir ação")
                return False
            elif eligibility.get("at_max_limit", False):
                logger.warning(f"⚠️ Premium {user.email} atingiu limite de {eligibility.get('max_credits', 3)} créditos")
            else:
                reason = eligibility.get("reason", "Créditos insuficientes")
                logger.info(f"📌 Premium {user.email}: {reason}")
        else:
            # ❌ FREE: não ganha créditos
            logger.info(f"📌 Usuário free {user.email} não tem créditos suficientes. Tem: {user.credits}, Precisa: {required_credits}")
        
        logger.warning(f"❌ Usuário {user.email} não tem créditos suficientes. Tem: {user.credits}, Necessário: {required_credits}")
    
    return has_credits


def consume_analysis_credit(user: User, db: Session, required_credits: int = 1) -> bool:
    """
    Consome crédito de uma análise
    
    🔥 V2.3: Usa manage_credits_after_consumption() para gerenciamento unificado
    
    ✅ Admin não consome nada
    ⭐ Premium consome normalmente e ganha bônus se zerar
    💰 Usuário comum consome normalmente, NÃO ganha bônus
    
    Retorna:
        bool: True se sucesso, False se erro
    """
    # 👑 Admin não consome créditos
    if user.is_admin:
        logger.info(f"👑 Admin {user.email} realizou análise sem consumir créditos")
        return True
    
    # 🔥 USAR O NOVO GERENCIADOR UNIFICADO
    from backend.crud import manage_credits_after_consumption
    
    result = manage_credits_after_consumption(
        db=db,
        user=user,
        amount=required_credits,
        description=f"Análise de {required_credits} arquivo(s)"
    )
    
    if result.get("success"):
        logger.info(f"💰 {user.email} consumiu {required_credits} crédito(s). Saldo: {result.get('remaining')}")
        
        if result.get("bonus_granted"):
            logger.info(f"⭐ Bônus concedido para {user.email}: +{result.get('bonus_amount')} crédito(s)")
        
        if result.get("needs_attention"):
            logger.info(f"📌 Atenção necessária para {user.email}: {result.get('message')}")
        
        return True
    
    logger.error(f"❌ Falha ao consumir créditos para {user.email}: {result.get('error')}")
    return False


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
    """
    Retorna saldo numérico de créditos
    
    Admin: 999999 (infinito)
    Outros: saldo real
    """
    if user.is_admin:
        return 999999
    return user.credits or 0


def can_receive_daily_credit(db: Session, user: User) -> dict:
    """
    Verifica se usuário premium pode receber crédito diário
    
    🔥 V2.3: Usa get_credit_eligibility() para consistência
    
    Retorna dicionário com status e mensagem
    """
    if user.is_admin:
        return {
            "can_receive": False,
            "message": "Admin tem créditos ilimitados",
            "is_premium": False,
            "is_admin": True
        }
    
    # 🔥 USAR FUNÇÃO DE ELEGIBILIDADE
    from backend.crud import get_credit_eligibility
    eligibility = get_credit_eligibility(db, user)
    
    is_premium = eligibility.get("is_premium", False)
    
    if not is_premium:
        return {
            "can_receive": False,
            "message": "Assine o plano premium para ganhar créditos diários",
            "is_premium": False,
            "is_admin": False,
            "credits_balance": user.credits or 0,
            "max_credits": 3
        }
    
    # ⭐ PREMIUM
    return {
        "can_receive": eligibility.get("can_receive_today", False),
        "message": eligibility.get("reason", ""),
        "is_premium": True,
        "is_admin": False,
        "received_today": eligibility.get("received_today", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "credits_balance": eligibility.get("credits_balance", user.credits),
        "max_credits": eligibility.get("max_credits", 3),
        "days_left": eligibility.get("days_left", 0),
        "next_credit_date": eligibility.get("next_credit_date"),
        "timezone": "America/Sao_Paulo (UTC-3)"
    }


def award_daily_credit(db: Session, user: User) -> dict:
    """
    Concede crédito diário para usuário premium
    
    🔥 V2.3: Usa receive_daily_credit() do crud
    
    Retorna resultado da operação
    """
    from backend.crud import receive_daily_credit
    
    result = receive_daily_credit(db, user.id)
    
    if result.get("success"):
        logger.info(f"⭐ Crédito diário concedido para {user.email}")
    else:
        logger.warning(f"⚠️ Falha ao conceder crédito diário para {user.email}: {result.get('error')}")
    
    return result


def add_credits_safe(db: Session, user: User, amount: int, description: str = "") -> bool:
    """
    Adiciona créditos ao usuário com commit seguro
    
    🔥 V2.3: Usa add_credits() do crud com validação
    
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
    
    # 🔥 USAR add_credits DO CRUD (já tem validação)
    from backend.crud import add_credits
    
    success = add_credits(db, user.id, amount, description)
    
    if success:
        logger.info(f"💰 {user.email} recebeu +{amount} créditos ({description})")
    else:
        logger.warning(f"⚠️ Falha ao adicionar créditos para {user.email}")
    
    return success


def get_credit_eligibility_status(db: Session, user: User) -> dict:
    """
    🔥 NOVA FUNÇÃO: Retorna status completo de elegibilidade do usuário
    
    Útil para chamadas AJAX do frontend
    """
    from backend.crud import get_credit_eligibility
    
    return get_credit_eligibility(db, user)


def can_receive_bonus(db: Session, user: User) -> dict:
    """
    🔥 NOVA FUNÇÃO: Verifica se o usuário pode receber bônus premium
    
    APENAS para usuários PREMIUM que zeraram os créditos
    """
    if user.is_admin:
        return {
            "can_receive": False,
            "message": "Admin tem créditos ilimitados",
            "is_premium": True
        }
    
    from backend.crud import get_credit_eligibility
    eligibility = get_credit_eligibility(db, user)
    
    is_premium = eligibility.get("is_premium", False)
    
    if not is_premium:
        return {
            "can_receive": False,
            "message": "Bônus exclusivo para usuários Premium. Assine o plano!",
            "is_premium": False,
            "credits_balance": user.credits or 0
        }
    
    # ⭐ PREMIUM: verifica se pode receber bônus
    can_receive = (
        is_premium and
        eligibility.get("credits_balance", 0) == 0 and
        eligibility.get("can_receive_today", False)
    )
    
    return {
        "can_receive": can_receive,
        "message": eligibility.get("reason", "Você pode receber bônus premium!") if can_receive else "Você não pode receber bônus no momento",
        "is_premium": True,
        "credits_balance": eligibility.get("credits_balance", 0),
        "max_credits": eligibility.get("max_credits", 3),
        "received_today": eligibility.get("received_today", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "next_credit_date": eligibility.get("next_credit_date")
    }


print("=" * 70)
print("✅ credits_consumer.py v2.3 carregado!")
print("   🔥 REGRAS DE CRÉDITOS CORRETAS:")
print("   📌 FREE: Consome créditos, NÃO ganha bônus")
print("   📌 PREMIUM: Consome créditos, ganha bônus se zerar")
print("   📌 PREMIUM: Só ganha se saldo < 3 e NÃO recebeu hoje")
print("   📌 Usa manage_credits_after_consumption() do crud")
print("   📌 NOVAS FUNÇÕES: get_credit_eligibility_status(), can_receive_bonus()")
print("=" * 70)