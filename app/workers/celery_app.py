from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("event_data_export", broker=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=20 * 60,
    task_soft_time_limit=18 * 60,
    worker_prefetch_multiplier=1,
)

