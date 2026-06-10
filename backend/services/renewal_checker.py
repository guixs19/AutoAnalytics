# backend/services/renewal_checker.py
"""
SERVIÇO DE RENOVAÇÃO E EXPIRAÇÃO DE PLANOS
------------------------------------------
- Job diário para verificar planos expirados
- Rebaixa automaticamente usuários com plano vencido
- Envia alertas para usuários próximos do vencimento
"""

from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models import User, UserPlan
import logging

logger = logging.getLogger(__name__)


class RenewalChecker:
    """Gerenciador de renovação de planos premium"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_expired_subscriptions(self) -> int:
        """
        Verifica e rebaixa planos que expiraram
        Retorna número de usuários rebaixados
        """
        today = date.today()
        
        # Buscar usuários premium com data de expiração menor que hoje
        expired_users = self.db.query(User).filter(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at < today,
            User.is_active == True,
            User.is_admin == False  # Admin nunca expira
        ).all()
        
        count = 0
        for user in expired_users:
            # Rebaixar para plano básico
            old_plan = user.plan.value if hasattr(user.plan, 'value') else user.plan
            user.plan = UserPlan.BASICO
            
            # Limpar dados de premium (opcional)
            # user.premium_activated_at = None
            # user.premium_expires_at = None
            
            self.db.commit()
            count += 1
            
            logger.warning(f"⏰ PLANO EXPIRADO: {user.email} - {old_plan} -> BASICO")
        
        if count > 0:
            logger.info(f"✅ {count} usuários tiveram planos expirados e foram rebaixados")
        
        return count
    
    def check_expiring_soon(self, days_before: int = 5) -> list:
        """
        Verifica usuários com plano expirando em breve
        Retorna lista de usuários que precisam de aviso
        """
        target_date = date.today() + timedelta(days=days_before)
        
        expiring_users = self.db.query(User).filter(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at == target_date,
            User.is_active == True,
            User.is_admin == False
        ).all()
        
        return expiring_users
    
    def get_expiring_summary(self) -> dict:
        """
        Retorna resumo de todos os planos prestes a expirar
        """
        today = date.today()
        
        # Planos que expiram hoje
        expiring_today = self.db.query(User).filter(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at == today
        ).count()
        
        # Planos que expiram nos próximos 7 dias
        expiring_week = self.db.query(User).filter(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at > today,
            User.premium_expires_at <= today + timedelta(days=7)
        ).count()
        
        # Planos já expirados (mas ainda não rebaixados)
        already_expired = self.db.query(User).filter(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at < today
        ).count()
        
        # Total de planos ativos
        active_premium = self.db.query(User).filter(
            User.plan == UserPlan.PREMIUM_MENSAL,
            User.premium_expires_at >= today
        ).count()
        
        return {
            "active_premium": active_premium,
            "expiring_today": expiring_today,
            "expiring_this_week": expiring_week,
            "already_expired": already_expired,
            "total_premium": active_premium + already_expired
        }
    
    def get_user_status(self, user: User) -> dict:
        """
        Retorna status detalhado para um usuário específico
        """
        if user.is_admin:
            return {
                "has_premium": True,
                "is_admin": True,
                "days_left": 999,
                "is_active": True,
                "needs_renewal": False,
                "is_expired": False,
                "message": "👑 Admin - acesso ilimitado"
            }
        
        if user.plan != UserPlan.PREMIUM_MENSAL or not user.premium_expires_at:
            return {
                "has_premium": False,
                "is_admin": False,
                "days_left": 0,
                "is_active": False,
                "needs_renewal": False,
                "is_expired": False,
                "message": "Nenhum plano premium ativo"
            }
        
        today = date.today()
        days_left = (user.premium_expires_at - today).days
        is_expired = days_left <= 0
        is_active = not is_expired
        needs_renewal = 0 < days_left <= 5
        
        if is_expired:
            message = "Seu plano expirou! Renove agora."
        elif needs_renewal:
            message = f"Seu plano expira em {days_left} dias! Renove para não perder o acesso."
        else:
            message = f"Plano ativo por mais {days_left} dias."
        
        return {
            "has_premium": is_active,
            "is_admin": False,
            "days_left": max(0, days_left),
            "is_active": is_active,
            "needs_renewal": needs_renewal,
            "is_expired": is_expired,
            "expires_at": user.premium_expires_at.isoformat(),
            "activated_at": user.premium_activated_at.isoformat() if user.premium_activated_at else None,
            "message": message
        }


def run_daily_renewal_check(db: Session) -> dict:
    """
    Função para ser chamada por um job agendado (ex: a cada dia às 00:00)
    Retorna resultados da verificação
    """
    checker = RenewalChecker(db)
    
    # Rebaixar expirados
    expired_count = checker.check_expired_subscriptions()
    
    # Verificar quem vai expirar em breve
    expiring_soon = checker.check_expiring_soon(5)
    
    # Resumo geral
    summary = checker.get_expiring_summary()
    
    # Log dos que vão expirar (para possíveis notificações)
    for user in expiring_soon:
        days_left = (user.premium_expires_at - date.today()).days
        logger.info(f"📢 AVISO: {user.email} - plano expira em {days_left} dias")
    
    return {
        "success": True,
        "expired_rebaixados": expired_count,
        "expiring_soon_count": len(expiring_soon),
        "summary": summary,
        "timestamp": date.today().isoformat()
    }


# Função para uso em background task
def check_user_subscription_status(db: Session, user_id: int) -> dict:
    """
    Verifica status de um usuário específico
    Útil para chamadas da API
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "Usuário não encontrado"}
    
    checker = RenewalChecker(db)
    return checker.get_user_status(user)


print("✅ renewal_checker.py carregado - Sistema de renovação manual ativo")