# backend/services/daily_credits_service.py - VERSÃO 2.3
"""
SERVIÇO DE CRÉDITOS DIÁRIOS - V2.3
-----------------------------------
GERENCIAMENTO DE CRÉDITOS DIÁRIOS DO PLANO PREMIUM

🔥 REGRAS V2.3:
   - FREE: NUNCA ganha créditos diários (só os 3 iniciais)
   - PREMIUM: Ganha 1 crédito por dia (máx 3)
   - PREMIUM: Só ganha se saldo < 3 e NÃO recebeu hoje
   - PREMIUM: PRECISA gastar para ganhar mais
   - 👑 Admin: créditos ilimitados

🔥 MELHORIAS v2.3:
   - ✅ Usa get_credit_eligibility() do crud
   - ✅ Verificação unificada de elegibilidade
   - ✅ FREE explicitamente bloqueado
   - ✅ Logs mais informativos
"""

from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import cast, Date
from backend.models import User, DailyCreditLog, Payment, Analysis, UserPlan
from backend.observability.sentinel import alert_daily_credits_distributed
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class DailyCreditsService:
    """
    GERENCIAMENTO DE CRÉDITOS DIÁRIOS DO PLANO PREMIUM
    -------------------------------------------------
    ⭐ Usuários PREMIUM: ganham 1 crédito por dia (máx 3)
    ❌ Usuários FREE: NÃO ganham créditos diários
    👑 Admin: créditos ilimitados
    🔥 REGRA: Só ganha se saldo < 3 e NÃO recebeu hoje
    🕐 TODAS as datas são baseadas no fuso horário de Brasília (UTC-3)
    """
    
    def __init__(self):
        self.credits_per_day = 1
        self.max_credits_balance = 3  # 🔥 Limite máximo de créditos acumulados
        
        # 🔥 Fuso horário de Brasília (UTC-3)
        self.tz_brasil = timezone(timedelta(hours=-3))
        logger.info(f"🕐 DailyCreditsService v2.3 inicializado com fuso UTC-3 (Brasília)")
    
    def _get_today_brasil(self) -> date:
        """
        Retorna data atual no fuso horário de Brasília (UTC-3)
        🚨 CRÍTICO: Não usar date.today() sem timezone em containers Docker!
        """
        return datetime.now(self.tz_brasil).date()
    
    def _get_now_brasil(self) -> datetime:
        """
        Retorna datetime atual no fuso horário de Brasília (UTC-3)
        """
        return datetime.now(self.tz_brasil)
    
    def _get_next_credit_date_brasil(self, days_ahead: int = 1) -> date:
        """
        Retorna data futura no fuso horário de Brasília
        """
        return self._get_today_brasil() + timedelta(days=days_ahead)
    
    def check_and_add_daily_credit(self, db: Session, user_id: int) -> Dict:
        """
        ⭐ APENAS para usuários PREMIUM
        Verifica se já ganhou crédito hoje e adiciona se for premium E saldo < 3
        
        REGRAS:
        - FREE: NÃO ganha nada
        - PREMIUM: Ganha 1/dia se saldo < 3 e NÃO recebeu hoje
        - PREMIUM: PRECISA gastar para ganhar mais
        - 👑 Admin: retorno especial
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {
                "success": False,
                "error": "Usuário não encontrado"
            }
        
        # 👑 ADMIN - ilimitado
        if user.is_admin:
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": "∞",
                "message": "Admin tem créditos ilimitados",
                "already_received_today": False,
                "is_admin": True,
                "is_premium": False
            }
        
        # 🔥 USAR A FUNÇÃO DE ELEGIBILIDADE DO CRUD
        from backend.crud import get_credit_eligibility
        eligibility = get_credit_eligibility(db, user)
        
        # ❌ USUÁRIO FREE - NUNCA RECEBE
        if not eligibility.get("is_premium", False):
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": user.credits or 0,
                "message": "Assine o plano premium para ganhar 1 crédito por dia!",
                "next_credit": "Assine o plano premium 🚀",
                "already_received_today": False,
                "is_admin": False,
                "is_premium": False,
                "max_credits": self.max_credits_balance,
                "timezone": "America/Sao_Paulo (UTC-3)"
            }
        
        # ⭐ USUÁRIO PREMIUM
        today = self._get_today_brasil()
        current_credits = user.credits or 0
        
        # 🔥 REGRA 1: Verifica limite máximo (3)
        if current_credits >= self.max_credits_balance:
            return {
                "success": False,
                "has_premium": True,
                "error": f"❌ Limite máximo de {self.max_credits_balance} créditos atingido.",
                "message": f"Gaste seus {current_credits} créditos para poder receber mais!",
                "current_credits": current_credits,
                "max_credits": self.max_credits_balance,
                "already_received_today": False,
                "is_admin": False,
                "is_premium": True,
                "needs_to_spend": True,
                "timezone": "America/Sao_Paulo (UTC-3)"
            }
        
        # 🔥 REGRA 2: Verifica se já recebeu hoje
        already_got = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            cast(DailyCreditLog.date, Date) == today,
            DailyCreditLog.source == "premium_daily"
        ).first()
        
        if already_got:
            next_credit_date = self._get_next_credit_date_brasil(1)
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": current_credits,
                "message": "Você já ganhou seu crédito premium hoje! Volte amanhã.",
                "next_credit": "Amanhã você ganha mais 1 crédito",
                "next_credit_date": next_credit_date.isoformat(),
                "already_received_today": True,
                "is_admin": False,
                "is_premium": True,
                "premium_days_left": user.get_premium_days_left(),
                "max_credits": self.max_credits_balance,
                "timezone": "America/Sao_Paulo (UTC-3)"
            }
        
        # ✅ REGRA 3: Conceder crédito (saldo < 3 e NÃO recebeu hoje)
        old_credits = user.credits or 0
        user.credits = old_credits + self.credits_per_day
        
        # Registrar log
        log = DailyCreditLog(
            user_id=user_id,
            credits_added=self.credits_per_day,
            date=today,
            total_after=user.credits,
            source="premium_daily"
        )
        db.add(log)
        db.commit()
        
        # Calcular streak (dias seguidos de premium)
        streak_logs = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.source == "premium_daily"
        ).order_by(DailyCreditLog.date.desc()).all()
        
        streak = len(streak_logs)
        
        # ALERTA: Crédito premium concedido
        alert_daily_credits_distributed(
            user_email=user.email,
            day=streak,
            credits=self.credits_per_day,
            total=user.credits
        )
        
        logger.info(f"⭐ Crédito premium para {user.email} - Dia {streak}/30 - Data Brasília: {today}")
        
        # Verificar se atingiu o limite após adicionar
        warning_message = ""
        if user.credits >= self.max_credits_balance:
            warning_message = f" ⚠️ Atenção: Você atingiu o limite máximo de {self.max_credits_balance} créditos!"
        
        return {
            "success": True,
            "credits_added": self.credits_per_day,
            "current_credits": user.credits,
            "streak_days": streak,
            "message": f"🎉 Você ganhou 1 crédito do seu plano premium hoje!{warning_message}",
            "already_received_today": False,
            "is_admin": False,
            "is_premium": True,
            "premium_days_left": user.get_premium_days_left(),
            "max_credits_reached": user.credits >= self.max_credits_balance,
            "max_credits": self.max_credits_balance,
            "timezone": "America/Sao_Paulo (UTC-3)",
            "date_processed": today.isoformat()
        }
    
    def get_user_credit_status(self, db: Session, user_id: int) -> Dict:
        """
        Retorna status completo dos créditos do usuário
        Inclui informações do plano premium e limite máximo
        
        🔥 V2.3: Usa get_credit_eligibility() para consistência
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "Usuário não encontrado"}
        
        # 🔥 USAR FUNÇÃO DE ELEGIBILIDADE
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
                "today_date": today.isoformat()
            }
        
        is_premium = eligibility.get("is_premium", False)
        current_credits = user.credits or 0
        
        # Verificar se já ganhou hoje (apenas para premium)
        got_today = None
        if is_premium:
            got_today = db.query(DailyCreditLog).filter(
                DailyCreditLog.user_id == user_id,
                cast(DailyCreditLog.date, Date) == today,
                DailyCreditLog.source == "premium_daily"
            ).first()
        
        # Contar total de créditos premium já recebidos
        premium_credits_received = 0
        if is_premium:
            premium_credits_received = db.query(DailyCreditLog).filter(
                DailyCreditLog.user_id == user_id,
                DailyCreditLog.source == "premium_daily"
            ).count()
        
        # Calcular dias restantes do premium
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
            "credits_needed_to_receive": max(0, self.max_credits_balance - current_credits),
            "timezone": "America/Sao_Paulo (UTC-3)",
            "today_date": today.isoformat(),
            "premium_info": {
                "active": is_premium,
                "days_left": premium_days_left,
                "progress": premium_progress,
                "credits_received_today": got_today is not None,
                "total_premium_credits_received": premium_credits_received,
                "next_credit_tomorrow": is_premium and not got_today and current_credits < self.max_credits_balance,
                "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan
            } if is_premium else None,
            "analyses_used": db.query(Analysis).filter(
                Analysis.user_id == user_id
            ).count()
        }
    
    def check_premium_daily_credit(self, db: Session, user_id: int) -> Dict:
        """
        ⭐ Verifica especificamente o crédito diário do premium
        Útil para chamadas AJAX no frontend
        
        🔥 V2.3: Usa get_credit_eligibility() para consistência
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "Usuário não encontrado"}
        
        # 🔥 USAR FUNÇÃO DE ELEGIBILIDADE
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
                "max_credits": self.max_credits_balance
            }
        
        today = self._get_today_brasil()
        current_credits = user.credits or 0
        
        # 🔥 Verificar se já recebeu hoje
        received_today = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            cast(DailyCreditLog.date, Date) == today,
            DailyCreditLog.source == "premium_daily"
        ).first() is not None
        
        # 🔥 Verificar se está no limite
        at_max_limit = current_credits >= self.max_credits_balance
        
        # 🔥 Verificar se pode receber
        can_receive_today = (
            is_premium and
            not received_today and
            user.get_premium_days_left() > 0 and
            not at_max_limit
        )
        
        # Próximo crédito
        next_credit_date = None
        if not received_today and not at_max_limit and user.get_premium_days_left() > 0:
            next_credit_date = today
        elif user.get_premium_days_left() > 0:
            next_credit_date = self._get_next_credit_date_brasil(1)
        
        # Mensagem de motivo
        if at_max_limit:
            reason = f"⚠️ Você atingiu o limite máximo de {self.max_credits_balance} créditos. Gaste alguns para receber mais!"
        elif received_today:
            reason = "✅ Você já recebeu seu crédito hoje! Volte amanhã."
        elif user.get_premium_days_left() <= 0:
            reason = "⏰ Seu plano premium expirou. Renove para continuar recebendo créditos!"
        else:
            reason = "✅ Você pode receber seu crédito premium hoje!"
        
        return {
            "success": True,
            "is_premium": True,
            "received_today": received_today,
            "can_receive_today": can_receive_today,
            "reason": reason,
            "next_credit_date": next_credit_date.isoformat() if next_credit_date else None,
            "days_left": user.get_premium_days_left(),
            "credits_balance": current_credits,
            "max_credits": self.max_credits_balance,
            "at_max_limit": at_max_limit,
            "credits_until_limit": max(0, self.max_credits_balance - current_credits),
            "timezone": "America/Sao_Paulo (UTC-3)",
            "today_date": today.isoformat()
        }
    
    def get_premium_summary(self, db: Session, user_id: int) -> Dict:
        """
        Retorna resumo completo do plano premium
        
        🕐 Todas as datas usam fuso horário de Brasília (UTC-3)
        """
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
                        "credits_per_day": 1,
                        "total_days": 30,
                        "total_credits": 30,
                        "features": [
                            "1 crédito novo todo dia",
                            "30 créditos no total",
                            "Válido por 30 dias",
                            f"Limite máximo de {self.max_credits_balance} créditos acumulados"
                        ]
                    }
                }
            }
        
        # Logs de créditos premium (ordenados do MAIS ANTIGO para o MAIS NOVO)
        logs = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.source == "premium_daily"
        ).order_by(DailyCreditLog.date.asc()).all()
        
        today = self._get_today_brasil()
        days_received = len(logs)
        days_left = user.get_premium_days_left()
        current_credits = user.credits or 0
        
        # Calcular próximos créditos
        upcoming_credits = []
        credits_to_receive = min(days_left, self.max_credits_balance - current_credits)
        for i in range(1, min(credits_to_receive + 1, 5)):
            next_date = self._get_next_credit_date_brasil(i)
            upcoming_credits.append({
                "date": next_date.isoformat(),
                "credits": 1,
                "day": days_received + i
            })
        
        # Verificar se já recebeu hoje
        if logs:
            last_log_date = logs[-1].date
            already_received_today = (last_log_date == today)
        else:
            already_received_today = False
        
        has_days_left = days_left > 0
        has_room_for_more = current_credits < self.max_credits_balance
        next_credit_today = has_days_left and has_room_for_more and not already_received_today
        
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
                "total_days": 30
            },
            "credits": {
                "total_received": days_received,
                "current_balance": current_credits,
                "used": (days_received + 3) - current_credits,
                "max_balance": self.max_credits_balance,
                "can_receive_more": has_room_for_more,
                "next_credit_today": next_credit_today,
                "upcoming_credits": upcoming_credits
            },
            "history": [
                {
                    "date": log.date.isoformat(),
                    "credits": log.credits_added,
                    "day": i + 1,
                    "balance_after": log.total_after
                }
                for i, log in enumerate(logs)
            ]
        }


print("=" * 70)
print("✅ daily_credits_service.py v2.3 carregado!")
print("   🔥 REGRAS DE CRÉDITOS CORRETAS:")
print("   📌 FREE: NUNCA ganha créditos diários")
print("   📌 PREMIUM: Ganha 1/dia se saldo < 3 e NÃO recebeu hoje")
print("   📌 PREMIUM: PRECISA gastar para ganhar mais")
print("   📌 Se saldo = 3, NÃO ganha")
print("   🔥 Usa get_credit_eligibility() do crud")
print("=" * 70)