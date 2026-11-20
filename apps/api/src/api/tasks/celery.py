from celery import Celery

from api.core.config import app_config

celery_app = Celery(
    "knowledge",
    broker=app_config.REDIS_URL,
    backend=app_config.REDIS_URL,
    # Modules containing @celery_app.task functions. The worker imports these on startup.
    include=["api.tasks.ingestion", "api.tasks.maintenance"],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,  # re-deliver if a worker dies mid-task
    worker_prefetch_multiplier=1,  # long tasks: don't hoard jobs
    beat_schedule={
        # Run by the `beat` service in docker-compose.
        "reap-stale-ingestion-jobs": {
            "task": "maintenance.reap_stale_jobs",
            "schedule": 300.0,  # every 5 minutes
        },
        "purge-expired-sessions": {
            "task": "maintenance.purge_expired_sessions",
            "schedule": 3600.0,  # hourly
        },
    },
)