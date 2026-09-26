# backend/services/renewal_checker.py - VERSÃO 2.0
"""
SERVIÇO DE RENOVAÇÃO E EXPIRAÇÃO DE PLANOS
------------------------------------------
- Job diário para verificar planos expirados
- Rebaixa automaticamente usuários com plano vencido
- Avisos para usuários próximos do vencimento

🔥 MUDANÇAS v2.0:
   - ✅ FIX: usa _today_brasil() (não date.today()) — respeita UTC-3
   - ✅ FIX: usa _as_date() antes de subtrair premium_expires_at
   - ✅ FIX: filtros SQL usam UserPlan.PREMIUM_MENSAL.value explicitamente
   - ✅ FIX: commit único no final do rebaixamento (não um por usuário)
   - ✅ IMPROVE: helper _premium_expired_filter() e _premium_active_filter()
   - ✅ IMPROVE: get_user_status usa user.is_premium() como fonte única
   - ✅ CLEAN: imports não usados removidos (func)
   - ✅ CLEAN: logs padronizados com prefixo [renewal]
"""

from datetime import timedelta
from sqlalchemy.orm import Session
from backend.models import User, UserPlan, _today_brasil, _as_date
import logging

logger = logging.getLogger(__name__)


# ==============================================
# HELPERS DE FILTRO (usam .value explícito)
# ==============================================

def _premium_plan_value() -> str:
    """🔥 Valor minúsculo do plano premium (como está no banco)."""
    return UserPlan.PREMIUM_MENSAL.value


def _premium_active_filter():
    """Filtros SQL para usuários com premium ATIVO."""
    return (
        User.plan == _premium_plan_value(),
        User.premium_expires_at >= _today_brasil(),
        User.is_active == True,
        User.is_admin == False,
    )


def _premium_expired_filter():
    """Filtros SQL para usuários com premium EXPIRADO."""
    return (
        User.plan == _premium_plan_value(),
        User.premium_expires_at < _today_brasil(),
        User.is_active == True,
        User.is_admin == False,
    )


class RenewalChecker:
    """Gerenciador de renovação de planos premium."""

    def __init__(self, db: Session):
        self.db = db

    # ==========================================
    # REBAIXAMENTO
    # ==========================================

    def check_expired_subscriptions(self) -> int:
        """
        Verifica e rebaixa planos que expiraram.
        Retorna o número de usuários rebaixados.

        🔥 Commit único no final (não um por usuário).
        """
        expired_users = self.db.query(User).filter(
            *_premium_expired_filter()
        ).all()

        if not expired_users:
            return 0

        for user in expired_users:
            old_plan = user.plan.value if hasattr(user.plan, "value") else str(user.plan)
            user.plan = UserPlan.BASICO
            logger.warning(f"[renewal] ⏰ EXPIRADO: {user.email} ({old_plan} → basico)")

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"[renewal] ❌ Erro ao rebaixar planos: {e}")
            raise

        logger.info(f"[renewal] ✅ {len(expired_users)} usuários rebaixados")
        return len(expired_users)

    # ==========================================
    # AVISOS
    # ==========================================

    def check_expiring_soon(self, days_before: int = 5) -> list:
        """
        Retorna usuários cujo premium expira exatamente daqui a N dias.
        """
        target_date = _today_brasil() + timedelta(days=days_before)

        return self.db.query(User).filter(
            User.plan == _premium_plan_value(),
            User.premium_expires_at == target_date,
            User.is_active == True,
            User.is_admin == False,
        ).all()

    def get_expiring_summary(self) -> dict:
        """
        Resumo de planos premium ativos/expirados.
        """
        today = _today_brasil()
        plan_value = _premium_plan_value()

        active_premium = self.db.query(User).filter(
            User.plan == plan_value,
            User.premium_expires_at >= today,
        ).count()

        expiring_today = self.db.query(User).filter(
            User.plan == plan_value,
            User.premium_expires_at == today,
        ).count()

        expiring_week = self.db.query(User).filter(
            User.plan == plan_value,
            User.premium_expires_at > today,
            User.premium_expires_at <= today + timedelta(days=7),
        ).count()

        already_expired = self.db.query(User).filter(
            User.plan == plan_value,
            User.premium_expires_at < today,
        ).count()

        return {
            "active_premium": active_premium,
            "expiring_today": expiring_today,
            "expiring_this_week": expiring_week,
            "already_expired": already_expired,
            "total_premium": active_premium + already_expired,
        }

    # ==========================================
    # STATUS INDIVIDUAL
    # ==========================================

    def get_user_status(self, user: User) -> dict:
        """
        Status detalhado para um usuário.
        🔥 Usa user.is_premium() como fonte única e _as_date() para dias.
        """
        if not user:
            return {
                "has_premium": False,
                "is_admin": False,
                "days_left": 0,
                "is_active": False,
                "needs_renewal": False,
                "is_expired": False,
                "message": "Usuário inválido",
            }

        # 👑 Admin nunca expira
        if user.is_admin:
            return {
                "has_premium": True,
                "is_admin": True,
                "days_left": 999,
                "is_active": True,
                "needs_renewal": False,
                "is_expired": False,
                "message": "👑 Admin - acesso ilimitado",
            }

        # 🔥 Fonte única: user.is_premium()
        is_active = user.is_premium()

        # Se não tem plano premium setado
        if not user.premium_expires_at:
            return {
                "has_premium": False,
                "is_admin": False,
                "days_left": 0,
                "is_active": False,
                "needs_renewal": False,
                "is_expired": False,
                "message": "Nenhum plano premium ativo",
            }

        # 🔥 Normaliza para date antes de aritmética
        expires = _as_date(user.premium_expires_at)
        days_left = (expires - _today_brasil()).days

        is_expired = days_left <= 0
        needs_renewal = 0 < days_left <= 5

        if is_expired:
            message = "Seu plano expirou! Renove agora."
        elif needs_renewal:
            message = f"Seu plano expira em {days_left} dias! Renove para não perder o acesso."
        else:
            message = f"Plano ativo por mais {days_left} dias."

        activated = _as_date(user.premium_activated_at)

        return {
            "has_premium": is_active,
            "is_admin": False,
            "days_left": max(0, days_left),
            "is_active": is_active,
            "needs_renewal": needs_renewal,
            "is_expired": is_expired,
            "expires_at": expires.isoformat() if expires else None,
            "activated_at": activated.isoformat() if activated else None,
            "message": message,
        }


# ==============================================
# JOB DIÁRIO
# ==============================================

def run_daily_renewal_check(db: Session) -> dict:
    """
    Executa a verificação diária completa.
    Ideal para rodar via APScheduler / cron às 00:00 (UTC-3).
    """
    checker = RenewalChecker(db)

    # 1. Rebaixa expirados
    expired_count = checker.check_expired_subscriptions()

    # 2. Avisa quem expira em 5 dias
    expiring_soon = checker.check_expiring_soon(5)
    for user in expiring_soon:
        expires = _as_date(user.premium_expires_at)
        days_left = (expires - _today_brasil()).days
        logger.info(f"[renewal] 📢 AVISO: {user.email} - expira em {days_left} dias")

    # 3. Resumo
    summary = checker.get_expiring_summary()

    return {
        "success": True,
        "expired_rebaixados": expired_count,
        "expiring_soon_count": len(expiring_soon),
        "summary": summary,
        "timestamp": _today_brasil().isoformat(),
    }


# ==============================================
# CONSULTA INDIVIDUAL (API)
# ==============================================

def check_user_subscription_status(db: Session, user_id: int) -> dict:
    """Status de um usuário específico (uso em endpoints)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "Usuário não encontrado"}

    return RenewalChecker(db).get_user_status(user)


# ==============================================
# PRINTS
# ==============================================

print("=" * 70)
print("✅ renewal_checker.py v2.0 carregado - TIMEZONE + DATE FIX!")
print("   ✅ _today_brasil() em vez de date.today()")
print("   ✅ _as_date() antes de aritmética de datas")
print("   ✅ UserPlan.PREMIUM_MENSAL.value explícito nos filtros SQL")
print("   ✅ Commit único no rebaixamento")
print("   ✅ user.is_premium() como fonte única em get_user_status")
print("=" * 70)