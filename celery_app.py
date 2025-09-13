from __future__ import annotations

from datetime import timedelta

from celery import Celery

from app import create_app

flask_app = create_app()
celery = Celery(
    __name__, broker=flask_app.config.get("REDIS_URL", "redis://redis:6379/0")
)
celery.conf.update(flask_app.config)

# Import task modules so Celery discovers them
import app.tasks.ingest  # noqa: F401

# Simple beat schedule placeholder
celery.conf.beat_schedule = {
    "ping": {"task": "ping", "schedule": timedelta(minutes=1)}
}


@celery.task
def ping() -> str:
    return "pong"
