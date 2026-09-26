# backend/services/credits_consumer.py - VERSÃO 2.4 (SIMPLIFICADA)
"""
Serviço para consumo de créditos em análises
COM SUPORTE PARA PLANO PREMIUM E LIMITE DE 3 CRÉDITOS

🔥 MUDANÇAS v2.4:
   - ✅ REMOVIDO: _is_premium_user (usar user.is_premium())
   - ✅ REMOVIDO: _get_plan_value (usar crud._get_plan_value)
   - ✅ CLEAN: imports de dentro de função mantidos (evitam circular import)
   - ✅ CLEAN: logs padronizados com prefixo [credits_consumer]

🔥 REGRAS (mantidas da v2.3):
   - FREE: Consome créditos, NÃO ganha bônus ao zerar
   - PREMIUM: Consome créditos, ganha bônus automático se zerar E não recebeu hoje
   - PREMIUM: Só ganha se saldo < 3 e NÃO recebeu hoje
   - 👑 Admin: créditos ilimitados, não consome
"""

import logging
from sqlalchemy.orm import Session
from backend.models import User
from backend.services.daily_credits_service import DailyCreditsService

logger = logging.getLogger(__name__)

# Instância do serviço de créditos diários
daily_credits_service = DailyCreditsService()


# ==============================================
# 🔥 HELPERS INTERNOS
# ==============================================

def _is_premium(user: User) -> bool:
    """🔥 Wrapper fino: delega para user.is_premium()."""
    if not user:
        return False
    return user.is_premium()


# ==============================================
# 🔥 VERIFICAÇÃO DE ANÁLISE
# ==============================================

def can_perform_analysis(db: Session, user: User, required_credits: int = 1) -> bool:
    """
    Verifica se usuário pode realizar uma análise.

    ✅ Admin sempre pode
    ⭐ Premium verifica saldo (respeitando limite de 3)
    💰 Comum verifica saldo normal
    """
    if not user:
        return False

    # 👑 Admin tem acesso ilimitado
    if user.is_admin:
        logger.info(f"[credits_consumer] 👑 Admin {user.email} pode realizar análise")
        return True

    current = user.credits or 0
    has_credits = current >= required_credits

    if not has_credits:
        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)

        if eligibility.get("is_premium", False):
            if eligibility.get("can_receive_today", False):
                logger.info(f"[credits_consumer] ⭐ Premium {user.email} pode ganhar crédito hoje")
            elif eligibility.get("at_max_limit", False):
                logger.warning(f"[credits_consumer] ⚠️ Premium {user.email} atingiu limite de {eligibility.get('max_credits', 3)} créditos")
            else:
                logger.info(f"[credits_consumer] 📌 Premium {user.email}: {eligibility.get('reason', '')}")
        else:
            logger.info(f"[credits_consumer] 📌 Free {user.email}: saldo {current}, precisa {required_credits}")

    return has_credits


# ==============================================
# 🔥 CONSUMO
# ==============================================

def consume_analysis_credit(user: User, db: Session, required_credits: int = 1) -> bool:
    """
    Consome crédito de uma análise.

    ✅ Admin não consome
    ⭐ Premium consome e ganha bônus se zerar
    💰 Free consome, sem bônus
    """
    if not user:
        return False

    if user.is_admin:
        logger.info(f"[credits_consumer] 👑 Admin {user.email} realizou análise sem consumir")
        return True

    from backend.crud import manage_credits_after_consumption

    result = manage_credits_after_consumption(
        db=db,
        user=user,
        amount=required_credits,
        description=f"Análise de {required_credits} arquivo(s)",
    )

    if result.get("success"):
        logger.info(f"[credits_consumer] 💰 {user.email} consumiu {required_credits} crédito(s). Saldo: {result.get('remaining')}")
        if result.get("bonus_granted"):
            logger.info(f"[credits_consumer] ⭐ Bônus: +{result.get('bonus_amount')} para {user.email}")
        if result.get("needs_attention"):
            logger.info(f"[credits_consumer] 📌 Atenção: {result.get('message')}")
        return True

    logger.error(f"[credits_consumer] ❌ Falha ao consumir créditos de {user.email}: {result.get('error')}")
    return False


# ==============================================
# 🔥 DISPLAY / BALANÇO
# ==============================================

def get_credits_display(user: User) -> str:
    """Admin: ∞ | Premium: X/3 | Free: X"""
    if not user:
        return "0"
    if user.is_admin:
        return "∞"
    if _is_premium(user):
        return f"{user.credits or 0}/3"
    return str(user.credits or 0)


def get_credits_balance(user: User) -> int:
    """Admin: 999999 | Outros: saldo real"""
    if not user:
        return 0
    if user.is_admin:
        return 999999
    return user.credits or 0


# ==============================================
# 🔥 ELEGIBILIDADE / CRÉDITO DIÁRIO
# ==============================================

def can_receive_daily_credit(db: Session, user: User) -> dict:
    """Verifica se premium pode receber crédito diário (via crud)."""
    if not user:
        return {"can_receive": False, "message": "Usuário inválido", "is_premium": False}

    if user.is_admin:
        return {
            "can_receive": False,
            "message": "Admin tem créditos ilimitados",
            "is_premium": False,
            "is_admin": True,
        }

    from backend.crud import get_credit_eligibility
    eligibility = get_credit_eligibility(db, user)

    if not eligibility.get("is_premium", False):
        return {
            "can_receive": False,
            "message": "Assine o plano premium para ganhar créditos diários",
            "is_premium": False,
            "is_admin": False,
            "credits_balance": user.credits or 0,
            "max_credits": 3,
        }

    return {
        "can_receive": eligibility.get("can_receive_today", False),
        "message": eligibility.get("reason", ""),
        "is_premium": True,
        "is_admin": False,
        "received_today": eligibility.get("received_today", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "credits_balance": eligibility.get("credits_balance", user.credits or 0),
        "max_credits": eligibility.get("max_credits", 3),
        "days_left": eligibility.get("days_left", 0),
        "next_credit_date": eligibility.get("next_credit_date"),
        "timezone": "America/Sao_Paulo (UTC-3)",
    }


def award_daily_credit(db: Session, user: User) -> dict:
    """Concede crédito diário para premium (via crud.receive_daily_credit)."""
    if not user:
        return {"success": False, "error": "Usuário inválido"}

    from backend.crud import receive_daily_credit
    result = receive_daily_credit(db, user.id)

    if result.get("success"):
        logger.info(f"[credits_consumer] ⭐ Crédito diário para {user.email}")
    else:
        logger.warning(f"[credits_consumer] ⚠️ Falha para {user.email}: {result.get('error')}")

    return result


# ==============================================
# 🔥 ADD CRÉDITOS (SAFE)
# ==============================================

def add_credits_safe(db: Session, user: User, amount: int, description: str = "") -> bool:
    """Adiciona créditos com validação do crud."""
    if not user or amount <= 0:
        return False

    if user.is_admin:
        return True

    from backend.crud import add_credits
    success = add_credits(db, user.id, amount, description)

    if success:
        logger.info(f"[credits_consumer] 💰 {user.email} +{amount} ({description})")
    else:
        logger.warning(f"[credits_consumer] ⚠️ Falha ao adicionar para {user.email}")

    return success


# ==============================================
# 🔥 ELEGIBILIDADE / BÔNUS
# ==============================================

def get_credit_eligibility_status(db: Session, user: User) -> dict:
    """Status completo de elegibilidade (via crud)."""
    from backend.crud import get_credit_eligibility
    return get_credit_eligibility(db, user)


def can_receive_bonus(db: Session, user: User) -> dict:
    """Verifica se premium pode receber bônus (saldo 0 + não recebeu hoje)."""
    if not user:
        return {"can_receive": False, "message": "Usuário inválido", "is_premium": False}

    if user.is_admin:
        return {
            "can_receive": False,
            "message": "Admin tem créditos ilimitados",
            "is_premium": True,
        }

    from backend.crud import get_credit_eligibility
    eligibility = get_credit_eligibility(db, user)

    if not eligibility.get("is_premium", False):
        return {
            "can_receive": False,
            "message": "Bônus exclusivo para usuários Premium. Assine o plano!",
            "is_premium": False,
            "credits_balance": user.credits or 0,
        }

    can_receive = (
        eligibility.get("credits_balance", 0) == 0
        and eligibility.get("can_receive_today", False)
    )

    return {
        "can_receive": can_receive,
        "message": eligibility.get("reason", "") if can_receive else "Você não pode receber bônus no momento",
        "is_premium": True,
        "credits_balance": eligibility.get("credits_balance", 0),
        "max_credits": eligibility.get("max_credits", 3),
        "received_today": eligibility.get("received_today", False),
        "at_max_limit": eligibility.get("at_max_limit", False),
        "next_credit_date": eligibility.get("next_credit_date"),
    }


# ==============================================
# 🔥 PRINTS
# ==============================================

print("=" * 70)
print("✅ credits_consumer.py v2.4 carregado - SIMPLIFICADO!")
print("   🔥 REMOVIDO: _is_premium_user e _get_plan_value")
print("   🔥 USA: user.is_premium() como fonte única de verdade")
print("   📌 FREE: consome, não ganha bônus")
print("   📌 PREMIUM: consome, ganha bônus se zerar")
print("=" * 70)