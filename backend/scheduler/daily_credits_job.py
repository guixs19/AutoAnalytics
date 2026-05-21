# backend/services/daily_credits_job.py
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from backend.models import User, DailyCreditLog, Payment, Analysis, UserPlan
from backend.observability.sentinel import alert_daily_credits_distributed
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class DailyCreditsService:
    """
    GERENCIAMENTO DE CRÉDITOS DIÁRIOS DO PLANO PREMIUM
    -------------------------------------------------
    - ⭐ Usuários com plano premium ganham 1 crédito por dia
    - 💰 Usuários comuns começam com 3 créditos (compram mais quando acabam)
    - 👑 Admin tem créditos ilimitados
    - 🔥 LIMITE MÁXIMO DE 3 CRÉDITOS ACUMULADOS
    """
    
    def __init__(self):
        self.credits_per_day = 1
        self.max_credits_balance = 3  # 🔥 Limite máximo de créditos acumulados
    
    def check_and_add_daily_credit(self, db: Session, user_id: int) -> Dict:
        """
        ⭐ APENAS para usuários com PLANO PREMIUM
        Verifica se já ganhou crédito hoje e adiciona se for premium
        
        ✅ Usuário comum: não ganha nada (volta status)
        ⭐ Usuário premium: ganha 1 crédito por dia (se saldo < 3)
        👑 Admin: retorno especial
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
        
        # 🔥 NOVA TRAVA: Não deixa acumular mais de 3 créditos no saldo total
        current_credits = user.credits or 0
        if current_credits >= self.max_credits_balance:
            return {
                "success": False,
                "has_premium": user.plan == UserPlan.PREMIUM_MENSAL,
                "error": f"❌ O seu saldo já atingiu o limite máximo de {self.max_credits_balance} créditos acumulados.",
                "message": f"Gaste seus {current_credits} créditos para poder receber mais!",
                "current_credits": current_credits,
                "max_credits": self.max_credits_balance,
                "already_received_today": False,
                "is_admin": False,
                "is_premium": user.plan == UserPlan.PREMIUM_MENSAL
            }
        
        # ⭐ Verificar se é PREMIUM
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        today = date.today()
        
        # Verificar se já ganhou crédito hoje (apenas para premium)
        already_got = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.date == today
        ).first()
        
        # ⭐ Se for PREMIUM e ainda não ganhou hoje, adicionar crédito
        if is_premium and not already_got:
            old_credits = user.credits or 0
            user.credits = old_credits + self.credits_per_day
            
            # Registrar log
            log = DailyCreditLog(
                user_id=user_id,
                credits_added=self.credits_per_day,
                date=today,
                total_after=user.credits,
                source="premium_daily"  # IMPORTANTE: veio do plano premium
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
            
            logger.info(f"⭐ Crédito premium para {user.email} - Dia {streak}/30")
            
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
                "max_credits": self.max_credits_balance
            }
        
        # ⭐ Se for PREMIUM mas já ganhou hoje
        if is_premium and already_got:
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": user.credits or 0,
                "message": "Você já ganhou seu crédito premium hoje! Volte amanhã.",
                "next_credit": "Amanhã você ganha mais 1 crédito",
                "already_received_today": True,
                "is_admin": False,
                "is_premium": True,
                "premium_days_left": user.get_premium_days_left(),
                "max_credits": self.max_credits_balance
            }
        
        # ✅ Usuário comum (não premium) - apenas retorna status
        return {
            "success": True,
            "credits_added": 0,
            "current_credits": user.credits or 0,
            "message": f"Você tem {user.credits or 0} créditos. Assine o plano premium para ganhar 1 crédito por dia!",
            "next_credit": "Assine o plano premium 🚀",
            "already_received_today": False,
            "is_admin": False,
            "is_premium": False,
            "max_credits": self.max_credits_balance
        }
    
    def get_user_credit_status(self, db: Session, user_id: int) -> Dict:
        """
        Retorna status completo dos créditos do usuário
        Inclui informações do plano premium e limite máximo
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "Usuário não encontrado"}
        
        today = date.today()
        
        # 👑 ADMIN
        if user.is_admin:
            return {
                "success": True,
                "current_credits": "∞",
                "current_credits_numeric": 999999,
                "message": "👑 Admin - créditos ilimitados",
                "is_admin": True,
                "is_premium": False,
                "max_credits": self.max_credits_balance
            }
        
        # ⭐ Verificar se é premium
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        # Verificar se já ganhou hoje (apenas para premium)
        got_today = None
        if is_premium:
            got_today = db.query(DailyCreditLog).filter(
                DailyCreditLog.user_id == user_id,
                DailyCreditLog.date == today,
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
        
        current_credits = user.credits or 0
        
        return {
            "success": True,
            "current_credits": current_credits,
            "message": f"Você tem {current_credits} créditos",
            "is_admin": False,
            "is_premium": is_premium,
            "max_credits": self.max_credits_balance,
            "can_receive_more": current_credits < self.max_credits_balance,
            "credits_needed_to_receive": max(0, self.max_credits_balance - current_credits),
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
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "Usuário não encontrado"}
        
        # Verificar se é premium
        is_premium = user.plan == UserPlan.PREMIUM_MENSAL and user.is_premium()
        
        if not is_premium:
            return {
                "success": True,
                "is_premium": False,
                "message": "Usuário não tem plano premium",
                "can_receive_today": False
            }
        
        today = date.today()
        current_credits = user.credits or 0
        
        # Verificar limite de créditos
        if current_credits >= self.max_credits_balance:
            return {
                "success": True,
                "is_premium": True,
                "received_today": False,
                "can_receive_today": False,
                "reason": "max_credits_reached",
                "message": f"⚠️ Você atingiu o limite máximo de {self.max_credits_balance} créditos. Gaste alguns para receber mais!",
                "next_credit_date": None,
                "days_left": user.get_premium_days_left(),
                "credits_balance": current_credits,
                "max_credits": self.max_credits_balance
            }
        
        # Verificar se já recebeu hoje
        received_today = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.date == today,
            DailyCreditLog.source == "premium_daily"
        ).first() is not None
        
        # Próximo crédito
        next_credit_date = None
        if not received_today:
            next_credit_date = today
        else:
            # Verificar se ainda tem dias restantes
            if user.get_premium_days_left() > 0:
                next_credit_date = today + timedelta(days=1)
        
        return {
            "success": True,
            "is_premium": True,
            "received_today": received_today,
            "can_receive_today": not received_today and user.get_premium_days_left() > 0 and current_credits < self.max_credits_balance,
            "next_credit_date": next_credit_date.isoformat() if next_credit_date else None,
            "days_left": user.get_premium_days_left(),
            "credits_balance": current_credits,
            "max_credits": self.max_credits_balance,
            "credits_until_limit": max(0, self.max_credits_balance - current_credits)
        }
    
    def get_premium_summary(self, db: Session, user_id: int) -> Dict:
        """
        Retorna resumo completo do plano premium
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
        
        # Logs de créditos premium
        logs = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.source == "premium_daily"
        ).order_by(DailyCreditLog.date.desc()).all()
        
        today = date.today()
        days_received = len(logs)
        days_left = user.get_premium_days_left()
        current_credits = user.credits or 0
        
        # Calcular próximos créditos
        upcoming_credits = []
        credits_to_receive = min(days_left, self.max_credits_balance - current_credits)
        for i in range(1, min(credits_to_receive + 1, 5)):  # Próximos 5 dias (ou até o limite)
            next_date = today + timedelta(days=i)
            upcoming_credits.append({
                "date": next_date.isoformat(),
                "credits": 1,
                "day": days_received + i
            })
        
        return {
            "success": True,
            "has_premium": True,
            "max_credits": self.max_credits_balance,
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
                "used": (days_received + 3) - current_credits,  # 3 é o inicial
                "max_balance": self.max_credits_balance,
                "can_receive_more": current_credits < self.max_credits_balance,
                "next_credit_today": not logs or logs[0].date != today if days_left > 0 and current_credits < self.max_credits_balance else False,
                "upcoming_credits": upcoming_credits
            },
            "history": [
                {
                    "date": log.date.isoformat(),
                    "credits": log.credits_added,
                    "day": i+1,
                    "balance_after": log.total_after
                }
                for i, log in enumerate(logs[:10])  # Últimos 10
            ]
        }