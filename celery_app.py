from __future__ import annotations

import os
import time
from datetime import timedelta

from celery import Celery
from celery.signals import task_postrun, task_prerun, task_sent
from prometheus_client import Gauge, Histogram

from app import create_app
from app.logging import configure_logging

try:  # pragma: no cover - optional dependency
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None


configure_logging()
dsn = os.getenv("SENTRY_DSN")
if sentry_sdk and dsn:  # pragma: no cover - optional dependency
    sentry_sdk.init(dsn=dsn, integrations=[CeleryIntegration()])

task_duration = Histogram(
    "celery_task_duration_seconds", "Task duration in seconds", ["task_name"]
)
queue_depth = Gauge("celery_queue_depth", "Number of tasks waiting in the queue")

_start_times: dict[str, float] = {}


@task_sent.connect
def _task_sent_handler(**_kwargs) -> None:  # pragma: no cover - metrics bookkeeping
    queue_depth.inc()


@task_prerun.connect
def _task_prerun_handler(task_id: str, task, **_kwargs) -> None:  # pragma: no cover
    queue_depth.dec()
    _start_times[task_id] = time.perf_counter()


@task_postrun.connect
def _task_postrun_handler(task_id: str, task, **_kwargs) -> None:  # pragma: no cover
    start = _start_times.pop(task_id, None)
    if start is not None:
        task_duration.labels(task.name).observe(time.perf_counter() - start)

flask_app = create_app()
celery = Celery(
    __name__, broker=flask_app.config.get("REDIS_URL", "redis://redis:6379/0")
)
celery.conf.update(flask_app.config)

# Import task modules so Celery discovers them
import app.tasks.ingest  # noqa: F401,E402

# Simple beat schedule placeholder
celery.conf.beat_schedule = {
    "ping": {"task": "ping", "schedule": timedelta(minutes=1)}
}


@celery.task
def ping() -> str:
    return "pong"
