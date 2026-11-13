from celery import Celery
from api.core.config import config


celery_app = Celery("chess", broker=config.REDIS_URL, backend=config.REDIS_URL)
