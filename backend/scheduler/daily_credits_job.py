# backend/services/daily_credits_service.py
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from backend.models import User, DailyCreditLog, Payment, Analysis
from backend.observability.sentinel import alert_daily_credits_distributed
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class DailyCreditsService:
    """
    GERENCIAMENTO DE CRÉDITOS DIÁRIOS
    ---------------------------------
    - Usuário começa com 0 créditos
    - Ganha 1 crédito por dia ao fazer upload
    - Máximo de 1 crédito por dia
    - Créditos acumulam (não expiram)
    - ✅ ADMIN tem créditos ilimitados (não consome e não precisa ganhar)
    """
    
    def __init__(self):
        self.credits_per_day = 1
    
    def check_and_add_daily_credit(self, db: Session, user_id: int) -> Dict:
        """
        Verifica se usuário já ganhou crédito hoje
        Se NÃO ganhou, adiciona 1 crédito
        Chamado quando usuário faz upload
        
        ✅ ADMIN: Não ganha créditos (já tem ilimitado)
        """
        # Buscar usuário
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {
                "success": False,
                "error": "Usuário não encontrado"
            }
        
        # ✅ ADMIN NÃO PRECISA GANHAR CRÉDITOS DIÁRIOS
        if user.is_admin:
            logger.info(f"👑 Admin {user.email} - créditos ilimitados (ignorando daily credit)")
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": "∞",
                "message": "Admin tem créditos ilimitados",
                "already_received_today": False,
                "is_admin": True
            }
        
        today = date.today()
        
        # Verificar se já ganhou crédito hoje
        already_got = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.date == today
        ).first()
        
        if already_got:
            # Já ganhou hoje
            return {
                "success": True,
                "credits_added": 0,
                "current_credits": user.credits or 0,
                "message": "Você já ganhou seu crédito diário hoje!",
                "next_credit": "Amanhã você ganha mais 1 crédito",
                "already_received_today": True,
                "is_admin": False
            }
        
        # ADICIONAR 1 CRÉDITO
        old_credits = user.credits or 0
        user.credits = old_credits + self.credits_per_day
        
        # Registrar log
        log = DailyCreditLog(
            user_id=user_id,
            credits_added=self.credits_per_day,
            date=today,
            total_after=user.credits,
            source="daily_upload"  # IMPORTANTE: veio do upload
        )
        db.add(log)
        db.commit()
        
        # Calcular streak (dias seguidos)
        yesterday = today - timedelta(days=1)
        got_yesterday = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.date == yesterday
        ).first()
        
        streak = 1
        if got_yesterday:
            # Calcular streak real
            streak_logs = db.query(DailyCreditLog).filter(
                DailyCreditLog.user_id == user_id
            ).order_by(DailyCreditLog.date.desc()).limit(30).all()
            
            streak = 1
            for i in range(len(streak_logs) - 1):
                if (streak_logs[i].date - streak_logs[i+1].date).days == 1:
                    streak += 1
                else:
                    break
        
        # ALERTA: Crédito diário concedido
        alert_daily_credits_distributed(
            user_email=user.email,
            day=streak,
            credits=self.credits_per_day,
            total=user.credits
        )
        
        logger.info(f"✅ Crédito diário para {user.email} - Streak: {streak} dias")
        
        return {
            "success": True,
            "credits_added": self.credits_per_day,
            "current_credits": user.credits,
            "streak_days": streak,
            "message": "🎉 Você ganhou 1 crédito por fazer upload hoje!",
            "already_received_today": False,
            "is_admin": False
        }
    
    def get_user_credit_status(self, db: Session, user_id: int) -> Dict:
        """
        Retorna status completo dos créditos do usuário
        
        ✅ ADMIN: Mostra ∞ (ilimitado)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "Usuário não encontrado"}
        
        today = date.today()
        
        # ✅ ADMIN - retorno especial
        if user.is_admin:
            # Total de análises feitas (apenas para informação)
            analyses_count = db.query(Analysis).filter(
                Analysis.user_id == user_id
            ).count()
            
            return {
                "success": True,
                "current_credits": "∞",
                "current_credits_numeric": 999999,  # Para cálculos internos
                "total_earned_all_time": "∞",
                "streak_days": "∞",
                "received_today": True,
                "credits_per_day": self.credits_per_day,
                "next_credit_available": True,
                "message": "👑 Admin - créditos ilimitados",
                "is_admin": True,
                "analyses_used": analyses_count,
                "history_last_30_days": []
            }
        
        # Verificar se já ganhou hoje
        got_today = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.date == today
        ).first()
        
        # Total de créditos já ganhos
        total_earned = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id
        ).count()
        
        # Calcular streak
        logs = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id
        ).order_by(DailyCreditLog.date.desc()).all()
        
        streak = 0
        if logs:
            streak = 1
            for i in range(len(logs) - 1):
                if (logs[i].date - logs[i+1].date).days == 1:
                    streak += 1
                else:
                    break
        
        # Histórico dos últimos 30 dias
        last_30_days = []
        for i in range(30):
            day = today - timedelta(days=i)
            got_on_day = any(log.date == day for log in logs)
            last_30_days.append({
                "date": day.isoformat(),
                "got_credit": got_on_day,
                "day_name": day.strftime("%A")
            })
        
        return {
            "success": True,
            "current_credits": user.credits or 0,
            "total_earned_all_time": total_earned,
            "streak_days": streak,
            "received_today": got_today is not None,
            "credits_per_day": self.credits_per_day,
            "next_credit_available": not got_today,
            "message": "Faça upload hoje para ganhar +1 crédito!" if not got_today else "Você já ganhou seu crédito hoje!",
            "history_last_30_days": last_30_days,
            "analyses_used": db.query(Analysis).filter(
                Analysis.user_id == user_id
            ).count(),
            "is_admin": False
        }
    
    def bulk_distribute_missed_credits(self, db: Session, user_id: int, days_back: int = 30):
        """
        Caso especial: Distribuir créditos que o usuário perdeu
        (útil para migração ou correção)
        
        ✅ ADMIN: Ignora (não precisa)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "Usuário não encontrado"}
        
        # ✅ ADMIN NÃO PRECISA RECUPERAR CRÉDITOS
        if user.is_admin:
            return {
                "success": True,
                "credits_recovered": 0,
                "current_credits": "∞",
                "message": "Admin não precisa recuperar créditos (já tem ilimitado)",
                "is_admin": True
            }
        
        today = date.today()
        credits_added = 0
        
        for days_ago in range(days_back):
            check_date = today - timedelta(days=days_ago)
            
            # Verificar se já tem registro nesse dia
            exists = db.query(DailyCreditLog).filter(
                DailyCreditLog.user_id == user_id,
                DailyCreditLog.date == check_date
            ).first()
            
            if not exists and check_date <= today:
                # Adicionar crédito perdido
                user.credits = (user.credits or 0) + self.credits_per_day
                
                log = DailyCreditLog(
                    user_id=user_id,
                    credits_added=self.credits_per_day,
                    date=check_date,
                    total_after=user.credits,
                    source="bulk_recovery"
                )
                db.add(log)
                credits_added += 1
        
        db.commit()
        
        return {
            "success": True,
            "credits_recovered": credits_added,
            "current_credits": user.credits,
            "message": f"Recuperados {credits_added} créditos perdidos",
            "is_admin": False
        }