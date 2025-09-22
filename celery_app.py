from __future__ import annotations

import os
import time
from datetime import timedelta

try:  # pragma: no cover - optional dependency
    from celery import Celery
    from celery.signals import task_postrun, task_prerun, task_sent
except Exception:  # pragma: no cover - optional dependency
    class _Signal:
        def connect(self, func=None, **_kwargs):
            if func is None:
                def decorator(fn):
                    return fn
                return decorator
            return func

    task_postrun = _Signal()
    task_prerun = _Signal()
    task_sent = _Signal()

    class _Conf(dict):
        def __getattr__(self, item):
            return self.get(item)

        def __setattr__(self, key, value):
            self[key] = value

    class Celery:  # type: ignore
        def __init__(self, *args, **_kwargs):
            self._conf = _Conf()

        @property
        def conf(self):
            return self._conf

        def task(self, *args, **_kwargs):
            def decorator(func):
                def wrapper(*fargs, **fkwargs):
                    return func(*fargs, **fkwargs)

                wrapper.__name__ = func.__name__
                wrapper.run = func
                return wrapper

            return decorator

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

@celery.task
def ping() -> str:
    return "pong"


# Simple beat schedule placeholder
# Periodic task schedule
celery.conf.beat_schedule = {
    "ping": {"task": ping.name, "schedule": timedelta(minutes=1)},
    # Regularly check which sources need to be scraped so that the UI shows data
    # without requiring manual task invocation.
    "ingest-due-sources": {
        "task": "run_due_sources",
        "schedule": timedelta(minutes=1),
    },
    # Evaluate alerts shortly after ingestion so the dashboard stays in sync.
    "evaluate-alerts": {
        "task": "evaluate_alerts",
        "schedule": timedelta(minutes=2),
    },
    # Pattern discovery is slightly more expensive; run it less frequently.
    "discover-patterns": {
        "task": "discover_patterns",
        "schedule": timedelta(minutes=15),
    },
}

