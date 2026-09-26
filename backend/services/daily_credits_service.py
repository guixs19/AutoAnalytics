# backend/services/daily_credits_service.py - VERSÃO 3.0 (CICLO DE 24H)
"""
SERVIÇO DE CRÉDITOS DIÁRIOS - V3.0
-----------------------------------
GERENCIAMENTO DO CICLO DE CRÉDITO DO PLANO PREMIUM

🔥 REGRAS V3.0 (CICLO DE 24H):
   - FREE: NUNCA ganha crédito diário (só os 3 iniciais)
   - PREMIUM: 1º crédito NO ATO do pagamento (âncora do ciclo)
   - PREMIUM: ganha +1 a cada 24h desde `last_daily_credit_at`
   - PREMIUM: só ganha se saldo < 3
   - PREMIUM: se saldo = 3, o ciclo pausa
   - 👑 Admin: créditos ilimitados

🔥 MUDANÇAS v3.0:
   - ✅ CICLO: checagem por "24h desde o último crédito" (não calendário)
   - ✅ Delega a decisão pro `crud.get_credit_eligibility()`
   - ✅ Atualiza `user.last_daily_credit_at` ao conceder
   - ✅ Retorna `next_credit_at_human` pro front
   - ✅ Remove cast(Date) — não é mais calendário
   - ✅ Log com próximo ciclo
"""

from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from backend.models import User, DailyCreditLog, Payment, Analysis, UserPlan
from backend.models import _ensure_timezone
from backend.observability.sentinel import alert_daily_credits_distributed
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DailyCreditsService:
    """
    GERENCIAMENTO DO CICLO DE CRÉDITO DO PLANO PREMIUM
    -------------------------------------------------
    ⭐ Usuários PREMIUM: ganham 1 crédito a cada 24h (máx 3)
    ❌ Usuários FREE: NÃO ganham crédito diário
    👑 Admin: créditos ilimitados
    🔥 REGRA: Só ganha se saldo < 3 e já completou 24h desde o último
    🕐 TODAS as datas usam fuso de Brasília (UTC-3)
    """

    def __init__(self):
        self.credits_per_day = 1
        self.max_credits_balance = 3
        self.cycle_hours = 24
        self.tz_brasil = timezone(timedelta(hours=-3))
        logger.info(
            "🕐 DailyCreditsService v3.0 inicializado "
            "(ciclo de 24h ancorado em last_daily_credit_at)"
        )

    # ==========================================
    # HELPERS DE DATA
    # ==========================================

    def _get_today_brasil(self) -> date:
        return datetime.now(self.tz_brasil).date()

    def _get_now_brasil(self) -> datetime:
        return datetime.now(self.tz_brasil)

    def _get_next_credit_date_brasil(self, days_ahead: int = 1) -> date:
        return self._get_today_brasil() + timedelta(days=days_ahead)

    def _format_next_credit_human(self, dt: Optional[datetime]) -> str:
        """Formata 'hoje às HH:MM' / 'amanhã às HH:MM' no fuso UTC-3."""
        if not dt:
            return ""
        aware = _ensure_timezone(dt)
        local = aware.astimezone(self.tz_brasil)
        today = self._get_today_brasil()
        time_str = local.strftime("%H:%M")
        if local.date() == today:
            return f"hoje às {time_str}"
        diff_days = (local.date() - today).days
        if diff_days == 1:
            return f"amanhã às {time_str}"
        if diff_days > 1:
            return f"em {diff_days} dias ({local.strftime('%d/%m')} às {time_str})"
        return f"às {time_str}"

    # ==========================================
    # 🔥 CHECK + ADD (coração do ciclo)
    # ==========================================

    def check_and_add_daily_credit(self, db: Session, user_id: int) -> Dict:
        """
        ⭐ Verifica se o usuário pode receber o crédito do ciclo ATUAL.

        Modelo v3.0:
          - 1º crédito: no ato do pagamento
          - Próximo: 24h depois de `last_daily_credit_at`
          - Se saldo >= 3: ciclo pausado
          - Se saldo < 3 e 24h passaram: pode receber

        Delega a decisão pro `crud.get_credit_eligibility()`.
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "Usuário não encontrado"}

        # 👑 ADMIN
        if user.is_admin:
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": "∞",
                "message": "Admin tem créditos ilimitados",
                "already_received_today": False,
                "is_admin": True,
                "is_premium": False,
            }

        # 🔥 ELEGIBILIDADE (usa o ciclo)
        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)

        # ❌ FREE
        if not eligibility.get("is_premium", False):
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": user.credits or 0,
                "message": "Assine o plano premium para ganhar 1 crédito a cada 24h!",
                "already_received_today": False,
                "is_admin": False,
                "is_premium": False,
                "max_credits": self.max_credits_balance,
                "timezone": "America/Sao_Paulo (UTC-3)",
            }

        current_credits = user.credits or 0

        # ⚠️ LIMITE MÁXIMO
        if eligibility.get("at_max_limit", False):
            return {
                "success": False,
                "has_premium": True,
                "error": f"❌ Limite máximo de {self.max_credits_balance} créditos atingido.",
                "message": f"Gaste seus {current_credits} créditos para retomar o ciclo.",
                "current_credits": current_credits,
                "max_credits": self.max_credits_balance,
                "already_received_today": False,
                "is_admin": False,
                "is_premium": True,
                "needs_to_spend": True,
                "timezone": "America/Sao_Paulo (UTC-3)",
            }

        # ⏳ AINDA NÃO COMPLETOU 24H
        if not eligibility.get("can_receive_today", False):
            next_human = eligibility.get("next_credit_at_human") or "em breve"
            next_iso = eligibility.get("next_credit_at")
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": current_credits,
                "message": f"⏰ Próximo crédito {next_human}.",
                "next_credit_at": next_iso,
                "next_credit_at_human": next_human,
                "already_received_today": True,
                "is_admin": False,
                "is_premium": True,
                "premium_days_left": user.get_premium_days_left(),
                "max_credits": self.max_credits_balance,
                "timezone": "America/Sao_Paulo (UTC-3)",
            }

        # ✅ CONCEDE
        now = self._get_now_brasil()
        old_credits = user.credits or 0
        user.credits = old_credits + self.credits_per_day
        user.last_daily_credit_at = now  # 🔥 move a âncora do ciclo
        db.add(user)

        log = DailyCreditLog(
            user_id=user_id,
            credits_added=self.credits_per_day,
            date=now.date(),
            total_after=user.credits,
            source="premium_daily",
        )
        db.add(log)
        db.commit()
        db.refresh(user)

        # Próximo ciclo = daqui a 24h
        next_at = now + timedelta(hours=self.cycle_hours)
        next_human = self._format_next_credit_human(next_at)

        # Streak (contagem total)
        streak = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.source == "premium_daily",
        ).count()

        # Alerta
        try:
            alert_daily_credits_distributed(
                user_email=user.email,
                day=streak,
                credits=self.credits_per_day,
                total=user.credits,
            )
        except Exception as e:
            logger.warning(f"[daily_credits] Alerta falhou: {e}")

        logger.info(
            f"[daily_credits] ⭐ +1 crédito para {user.email} "
            f"(saldo: {user.credits}, próximo: {next_human})"
        )

        warning = ""
        if user.credits >= self.max_credits_balance:
            warning = f" ⚠️ Atenção: você atingiu o limite de {self.max_credits_balance} créditos."

        return {
            "success": True,
            "credits_added": self.credits_per_day,
            "current_credits": user.credits,
            "streak_days": streak,
            "message": f"🎉 Você recebeu +1 crédito do seu plano!{warning}",
            "next_credit_at": next_at.isoformat(),
            "next_credit_at_human": next_human,
            "already_received_today": False,
            "is_admin": False,
            "is_premium": True,
            "premium_days_left": user.get_premium_days_left(),
            "max_credits_reached": user.credits >= self.max_credits_balance,
            "max_credits": self.max_credits_balance,
            "timezone": "America/Sao_Paulo (UTC-3)",
            "date_processed": now.date().isoformat(),
        }

    # ==========================================
    # STATUS DO USUÁRIO
    # ==========================================

    def get_user_credit_status(self, db: Session, user_id: int) -> Dict:
        """Status completo dos créditos do usuário (com ciclo)."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "Usuário não encontrado"}

        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)

        today = self._get_today_brasil()

        # 👑 ADMIN
        if user.is_admin:
            return {
                "success": True,
                "current_credits": "∞",
                "current_credits_numeric": 999999,
                "message": "👑 Admin - créditos ilimitados",
                "is_admin": True,
                "is_premium": False,
                "max_credits": self.max_credits_balance,
                "can_receive_today": False,
                "received_today": True,
                "timezone": "America/Sao_Paulo (UTC-3)",
                "today_date": today.isoformat(),
            }

        is_premium = eligibility.get("is_premium", False)
        current_credits = user.credits or 0

        # Total de créditos já recebidos
        premium_credits_received = 0
        if is_premium:
            premium_credits_received = db.query(DailyCreditLog).filter(
                DailyCreditLog.user_id == user_id,
                DailyCreditLog.source == "premium_daily",
            ).count()

        premium_days_left = user.get_premium_days_left() if is_premium else 0
        premium_progress = user.get_premium_progress() if is_premium else 0

        return {
            "success": True,
            "current_credits": current_credits,
            "message": f"Você tem {current_credits} créditos",
            "is_admin": False,
            "is_premium": is_premium,
            "max_credits": self.max_credits_balance,
            "can_receive_more": current_credits < self.max_credits_balance,
            "can_receive_today": eligibility.get("can_receive_today", False),
            "received_today": eligibility.get("received_today", False),
            "next_credit_at": eligibility.get("next_credit_at"),
            "next_credit_at_human": eligibility.get("next_credit_at_human"),
            "expires_at_human": eligibility.get("expires_at_human"),
            "credits_needed_to_receive": max(0, self.max_credits_balance - current_credits),
            "timezone": "America/Sao_Paulo (UTC-3)",
            "today_date": today.isoformat(),
            "premium_info": {
                "active": is_premium,
                "days_left": premium_days_left,
                "progress": premium_progress,
                "total_premium_credits_received": premium_credits_received,
                "plan": user.plan.value if hasattr(user.plan, "value") else user.plan,
            } if is_premium else None,
            "analyses_used": db.query(Analysis).filter(
                Analysis.user_id == user_id
            ).count(),
        }

    # ==========================================
    # CHECK PREMIUM DAILY (AJAX)
    # ==========================================

    def check_premium_daily_credit(self, db: Session, user_id: int) -> Dict:
        """Checagem do crédito do ciclo (AJAX)."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "Usuário não encontrado"}

        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)

        is_premium = eligibility.get("is_premium", False)

        if not is_premium:
            return {
                "success": True,
                "is_premium": False,
                "message": "Usuário não tem plano premium",
                "can_receive_today": False,
                "credits_balance": user.credits or 0,
                "max_credits": self.max_credits_balance,
            }

        return {
            "success": True,
            "is_premium": True,
            "received_today": eligibility.get("received_today", False),
            "can_receive_today": eligibility.get("can_receive_today", False),
            "reason": eligibility.get("reason", ""),
            "next_credit_at": eligibility.get("next_credit_at"),
            "next_credit_at_human": eligibility.get("next_credit_at_human"),
            "expires_at_human": eligibility.get("expires_at_human"),
            "days_left": eligibility.get("days_left", 0),
            "credits_balance": user.credits or 0,
            "max_credits": self.max_credits_balance,
            "at_max_limit": eligibility.get("at_max_limit", False),
            "credits_until_limit": eligibility.get("credits_until_limit", 0),
            "timezone": "America/Sao_Paulo (UTC-3)",
            "today_date": self._get_today_brasil().isoformat(),
        }

    # ==========================================
    # RESUMO PREMIUM
    # ==========================================

    def get_premium_summary(self, db: Session, user_id: int) -> Dict:
        """Resumo completo do plano premium com ciclo."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "Usuário não encontrado"}

        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()

        if not is_premium:
            return {
                "success": True,
                "has_premium": False,
                "message": "Usuário não possui plano premium",
                "max_credits": self.max_credits_balance,
                "timezone": "America/Sao_Paulo (UTC-3)",
                "plans_available": {
                    "premium_mensal": {
                        "name": "Premium Mensal",
                        "price": 97.00,
                        "cycle_hours": self.cycle_hours,
                        "total_days": 30,
                        "total_credits": 30,
                        "features": [
                            "1º crédito no ato da compra",
                            "Depois, 1 crédito a cada 24h",
                            "30 créditos no total",
                            "Válido por 30 dias",
                            f"Limite máximo de {self.max_credits_balance} créditos acumulados",
                        ],
                    }
                },
            }

        logs = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.source == "premium_daily",
        ).order_by(DailyCreditLog.date.asc()).all()

        today = self._get_today_brasil()
        days_received = len(logs)
        days_left = user.get_premium_days_left()
        current_credits = user.credits or 0

        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)

        next_at = user.get_next_credit_at()
        next_human = self._format_next_credit_human(next_at)

        return {
            "success": True,
            "has_premium": True,
            "max_credits": self.max_credits_balance,
            "timezone": "America/Sao_Paulo (UTC-3)",
            "today_date": today.isoformat(),
            "plan": {
                "name": "Premium Mensal",
                "activated_at": user.premium_activated_at.isoformat() if user.premium_activated_at else None,
                "expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
                "days_passed": days_received,
                "days_left": days_left,
                "progress": user.get_premium_progress(),
                "total_days": 30,
                "cycle_hours": self.cycle_hours,
            },
            "credits": {
                "total_received": days_received,
                "current_balance": current_credits,
                "max_balance": self.max_credits_balance,
                "can_receive_more": current_credits < self.max_credits_balance,
                "can_receive_today": eligibility.get("can_receive_today", False),
                "next_credit_at_human": next_human,
                "expires_at_human": eligibility.get("expires_at_human"),
                "last_daily_credit_at": (
                    user.last_daily_credit_at.isoformat()
                    if user.last_daily_credit_at else None
                ),
            },
            "history": [
                {
                    "date": log.date.isoformat(),
                    "credits": log.credits_added,
                    "day": i + 1,
                    "balance_after": log.total_after,
                }
                for i, log in enumerate(logs)
            ],
        }


print("=" * 70)
print("✅ daily_credits_service.py v3.0 carregado - CICLO DE 24H!")
print("   📌 FREE: nunca ganha crédito diário")
print("   📌 PREMIUM: 1º no ato, depois a cada 24h")
print("   📌 Ciclo ancorado em last_daily_credit_at")
print("   📌 Delega a decisão pro crud.get_credit_eligibility()")
print("   📌 Retorna next_credit_at_human pro front")
print("=" * 70)