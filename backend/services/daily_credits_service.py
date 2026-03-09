# backend/services/daily_credits_service.py
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from backend.models import User, Payment, DailyCreditLog
from backend.observability.sentinel import get_sentinel
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)
sentinel = get_sentinel()

class DailyCreditsService:
    """
    Serviço para gerenciar créditos diários do plano Premium Mensal
    Usuário paga R$ 58,90 e recebe 1 crédito por dia durante 30 dias
    """
    
    def __init__(self):
        self.premium_plan_id = "premium_mensal"
        self.daily_credits = 1
        self.total_days = 30
    
    def get_active_premium_users(self, db: Session) -> List[User]:
        """Retorna usuários com plano premium mensal ativo"""
        
        today = date.today()
        
        # Buscar usuários com plano premium que ainda estão dentro do período
        users = db.query(User).filter(
            User.plan == self.premium_plan_id,
            User.is_active == True,
            User.premium_activated_at.isnot(None),
            User.premium_expires_at >= today  # Ainda não expirou
        ).all()
        
        return users
    
    def get_user_daily_credit_status(self, db: Session, user_id: int) -> Dict:
        """Verifica status dos créditos diários do usuário"""
        
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or user.plan != self.premium_plan_id:
            return {
                "is_premium": False,
                "message": "Usuário não possui plano premium"
            }
        
        today = date.today()
        
        # Calcular dias desde a ativação
        days_since_activation = (today - user.premium_activated_at.date()).days if user.premium_activated_at else 0
        days_remaining = max(0, self.total_days - days_since_activation)
        
        # Verificar quantos créditos já recebeu
        credits_received = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id
        ).count()
        
        # Verificar se já recebeu hoje
        received_today = db.query(DailyCreditLog).filter(
            DailyCreditLog.user_id == user_id,
            DailyCreditLog.date == today
        ).first() is not None
        
        # Calcular próximos créditos
        next_credit_date = None
        if not received_today and days_remaining > 0:
            next_credit_date = today
        elif days_remaining > 0:
            next_credit_date = today + timedelta(days=1)
        
        return {
            "is_premium": True,
            "plan": "Premium Mensal",
            "activated_at": user.premium_activated_at,
            "expires_at": user.premium_expires_at,
            "days_since_activation": days_since_activation,
            "days_remaining": days_remaining,
            "total_days": self.total_days,
            "credits_received": credits_received,
            "credits_remaining": days_remaining,  # Créditos que ainda vai receber
            "received_today": received_today,
            "next_credit_date": next_credit_date,
            "current_balance": user.credits or 0,
            "daily_credit": self.daily_credits
        }
    
    def distribute_daily_credits(self, db: Session) -> Dict:
        """
        Distribui 1 crédito para cada usuário premium ativo
        Este método deve ser chamado por um scheduler TODO DIA às 00:00
        """
        
        today = date.today()
        logger.info(f"📅 Iniciando distribuição de créditos diários - {today}")
        
        stats = {
            "date": today,
            "total_users": 0,
            "credits_distributed": 0,
            "users_processed": [],
            "errors": []
        }
        
        try:
            # Buscar usuários ativos
            premium_users = self.get_active_premium_users(db)
            stats["total_users"] = len(premium_users)
            
            if not premium_users:
                logger.info("📭 Nenhum usuário premium ativo encontrado")
                sentinel.alert(
                    "ℹ️",
                    "📭 Sem usuários premium",
                    data=today.isoformat()
                )
                return stats
            
            logger.info(f"👥 Encontrados {len(premium_users)} usuários premium")
            
            for user in premium_users:
                try:
                    # Verificar se já recebeu hoje
                    already_received = db.query(DailyCreditLog).filter(
                        DailyCreditLog.user_id == user.id,
                        DailyCreditLog.date == today
                    ).first()
                    
                    if already_received:
                        logger.info(f"⏭️ Usuário {user.email} já recebeu crédito hoje")
                        continue
                    
                    # Verificar se ainda está dentro do período
                    if user.premium_expires_at and user.premium_expires_at < today:
                        logger.info(f"⏰ Usuário {user.email} está com plano expirado")
                        continue
                    
                    # ADICIONAR 1 CRÉDITO
                    user.credits = (user.credits or 0) + self.daily_credits
                    
                    # Registrar log
                    log = DailyCreditLog(
                        user_id=user.id,
                        credits_added=self.daily_credits,
                        date=today,
                        total_after=user.credits,
                        day_number=(today - user.premium_activated_at.date()).days + 1
                    )
                    db.add(log)
                    
                    # Commit
                    db.commit()
                    
                    stats["credits_distributed"] += 1
                    stats["users_processed"].append({
                        "user_id": user.id,
                        "email": user.email,
                        "day": log.day_number,
                        "new_balance": user.credits
                    })
                    
                    logger.info(f"✅ Crédito adicionado para {user.email} - Dia {log.day_number}/30")
                    
                    # ALERTA: Crédito diário (silencioso - só log)
                    if log.day_number in [1, 10, 20, 30]:  # Alertas em dias especiais
                        sentinel.alert(
                            "📅",
                            f"🎯 Dia {log.day_number}/30 - Premium",
                            usuario=user.email,
                            creditos_hoje=self.daily_credits,
                            saldo_atual=user.credits,
                            dias_restantes=30 - log.day_number
                        )
                    
                except Exception as e:
                    logger.error(f"❌ Erro ao processar usuário {user.id}: {e}")
                    stats["errors"].append({
                        "user_id": user.id,
                        "error": str(e)
                    })
                    db.rollback()
            
            # ALERTA: Resumo da distribuição
            if stats["credits_distributed"] > 0:
                sentinel.alert(
                    "📊",
                    "📊 Distribuição Diária Concluída",
                    total_usuarios=stats["total_users"],
                    creditos_distribuidos=stats["credits_distributed"],
                    data=today.isoformat(),
                    proxima_distribuicao=(today + timedelta(days=1)).isoformat()
                )
            
            logger.info(f"✅ Distribuição concluída: {stats['credits_distributed']} créditos para {len(stats['users_processed'])} usuários")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Erro na distribuição diária: {e}")
            sentinel.alert(
                "🔥",
                "❌ ERRO na Distribuição Diária",
                erro=str(e),
                data=today.isoformat()
            )
            return stats
    
    def activate_premium_plan(self, db: Session, user_id: int, payment_id: int) -> bool:
        """
        Ativa plano premium para usuário após pagamento aprovado
        """
        try:
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user:
                logger.error(f"Usuário {user_id} não encontrado")
                return False
            
            today = date.today()
            expires_at = today + timedelta(days=self.total_days)
            
            # Atualizar usuário
            user.plan = self.premium_plan_id
            user.premium_activated_at = datetime.now()
            user.premium_expires_at = expires_at
            user.credits = (user.credits or 0) + self.daily_credits  # Já ganha o primeiro crédito
            
            # Registrar log do primeiro dia
            log = DailyCreditLog(
                user_id=user.id,
                credits_added=self.daily_credits,
                date=today,
                total_after=user.credits,
                day_number=1,
                payment_id=payment_id
            )
            db.add(log)
            db.commit()
            
            # ALERTA: Novo assinante premium
            sentinel.first_payment(
                user_id=user.id,
                user_email=user.email,
                amount=58.90,
                plan="Premium Mensal"
            )
            
            sentinel.alert(
                "🎉",
                "✨ NOVO ASSINANTE PREMIUM",
                usuario=user.email,
                validade=expires_at.isoformat(),
                primeiro_credito="✅ Adicionado",
                mensagem="1 crédito por dia durante 30 dias! 🌟"
            )
            
            logger.info(f"✅ Plano premium ativado para {user.email} até {expires_at}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao ativar premium: {e}")
            sentinel.alert(
                "🔥",
                "❌ Erro ao ativar Premium",
                usuario_id=user_id,
                erro=str(e)
            )
            db.rollback()
            return False