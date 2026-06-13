from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "teammatex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# Periodic jobs (worker-beat). Both are self-gating: the digest no-ops when Slack
# isn't configured, and git-pull only pulls when update_settings.method=git_pull.
celery_app.conf.beat_schedule = {
    "weekly-digest": {
        "task": "send_weekly_digest",
        "schedule": crontab(day_of_week="mon", hour=9, minute=0),
    },
    "git-pull-sync": {
        "task": "git_pull_scheduled",
        "schedule": 900.0,  # every 15 min
    },
}
