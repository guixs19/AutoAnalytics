# backend/scheduler/daily_credits_job.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.database import SessionLocal
from backend.services.daily_credits_service import DailyCreditsService
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def distribute_daily_credits_job():
    """
    Job que roda todo dia às 00:05 para distribuir créditos diários
    """
    logger.info("⏰ Iniciando job de distribuição de créditos diários")
    
    db = SessionLocal()
    try:
        service = DailyCreditsService()
        stats = service.distribute_daily_credits(db)
        
        logger.info(f"✅ Job concluído: {stats['credits_distributed']} créditos distribuídos")
        
    except Exception as e:
        logger.error(f"❌ Erro no job: {e}")
    finally:
        db.close()

def init_scheduler():
    """Inicializa o scheduler"""
    scheduler = BackgroundScheduler()
    
    # Agendar para rodar todo dia às 00:05
    scheduler.add_job(
        distribute_daily_credits_job,
        trigger=CronTrigger(hour=0, minute=5),
        id="daily_credits_distribution",
        name="Distribuir créditos diários do plano premium",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Scheduler de créditos diários iniciado")
    
    return scheduler