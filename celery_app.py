from celery import Celery
from app import create_app

flask_app = create_app()
celery = Celery(__name__, broker=flask_app.config.get('REDIS_URL', 'redis://redis:6379/0'))
celery.conf.update(flask_app.config)

@celery.task
def ping() -> str:
    return 'pong'
