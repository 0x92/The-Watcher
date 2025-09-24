from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from prometheus_client import Gauge, Histogram

from app import create_app
from app.logging import configure_logging
from app.tasks.ingest import discover_patterns, evaluate_alerts, run_due_sources\nfrom app.services.analytics.gematria_rollups import refresh_rollups_job

try:  # pragma: no cover - optional dependency
    import sentry_sdk
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None


def _utc_iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    if ts == float("inf"):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


job_duration = Histogram(
    "scheduler_job_duration_seconds", "Duration of scheduler jobs", ["job_name"]
)
active_jobs_gauge = Gauge(
    "scheduler_jobs_active", "Number of scheduler jobs currently running"
)
scheduled_jobs_gauge = Gauge(
    "scheduler_jobs_enabled", "Number of scheduler jobs that are enabled"
)


@dataclass
class ScheduledJob:
    """Metadata describing a registered scheduler job."""

    name: str
    func: Callable[..., Any]
    interval: float
    args: tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    next_run: float = field(default_factory=lambda: time.time())
    last_run: Optional[float] = None
    last_duration: Optional[float] = None
    total_runs: int = 0
    running: bool = False
    enabled: bool = True
    error: Optional[str] = None


class Scheduler:
    """A lightweight threaded scheduler using the standard library."""

    def __init__(self, *, max_workers: int = 4, name: str = "scheduler") -> None:
        self._name = name
        self._max_workers = max(1, int(max_workers))
        self._jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.RLock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._tick = threading.Event()
        self._active_jobs = 0
        self._logger = logging.getLogger(name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_gauges(self) -> None:
        with self._lock:
            enabled = sum(1 for job in self._jobs.values() if job.enabled)
            scheduled_jobs_gauge.set(enabled)
            active_jobs_gauge.set(self._active_jobs)

    def _prepare_job(self, job: ScheduledJob) -> Optional[ThreadPoolExecutor]:
        with self._lock:
            if job.running:
                return None
            job.running = True
            job.error = None
            job.next_run = float("inf")
            self._active_jobs += 1
            executor = self._executor
        self._update_gauges()
        return executor

    def _finalize_job(self, job: ScheduledJob, *, completed_at: float, duration: float, error: Optional[str]) -> None:
        with self._lock:
            job.last_run = completed_at
            job.last_duration = duration
            job.total_runs += 1
            job.error = error
            job.running = False
            if job.enabled:
                job.next_run = completed_at + job.interval
            else:
                job.next_run = float("inf")
            self._active_jobs = max(self._active_jobs - 1, 0)
        self._update_gauges()

    def _dispatch(self, job: ScheduledJob, *, force_sync: bool = False) -> None:
        executor = self._prepare_job(job)

        def _run() -> None:
            start = time.perf_counter()
            err_text: Optional[str] = None
            try:
                job.func(*job.args, **job.kwargs)
            except Exception:  # pragma: no cover - defensive logging
                err_text = traceback.format_exc()
                self._logger.exception("Scheduler job '%s' failed", job.name)
            duration = time.perf_counter() - start
            job_duration.labels(job.name).observe(duration)
            completed_at = time.time()
            self._finalize_job(job, completed_at=completed_at, duration=duration, error=err_text)
            self._tick.set()

        if executor is None or force_sync:
            # Run synchronously when the scheduler isn't active yet or when forced.
            _run()
        else:
            executor.submit(_run)

    def _loop(self) -> None:
        self._logger.info("Scheduler loop started with max_workers=%s", self._max_workers)
        while not self._stop_event.is_set():
            due: list[ScheduledJob] = []
            next_deadline: Optional[float] = None
            now = time.time()
            with self._lock:
                for job in self._jobs.values():
                    if not job.enabled or job.running:
                        continue
                    if job.next_run <= now:
                        due.append(job)
                    else:
                        if next_deadline is None or job.next_run < next_deadline:
                            next_deadline = job.next_run
            if due:
                for job in due:
                    self._dispatch(job)
                continue

            timeout = 1.0
            if next_deadline is not None:
                timeout = max(min(next_deadline - time.time(), 5.0), 0.1)
            triggered = self._tick.wait(timeout)
            if triggered:
                self._tick.clear()
        self._logger.info("Scheduler loop stopped")

    def _wake(self) -> None:
        self._tick.set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._tick.clear()
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers, thread_name_prefix=f"{self._name}-job"
            )
            self._thread = threading.Thread(
                target=self._loop,
                name=f"{self._name}-loop",
                daemon=True,
            )
            self._thread.start()
        self._update_gauges()

    def stop(self, *, wait: bool = True) -> None:
        with self._lock:
            if not self.is_running:
                return
            self._stop_event.set()
            self._tick.set()
            thread = self._thread
            executor = self._executor
        if thread is not None and wait:
            thread.join()
        if executor is not None:
            executor.shutdown(wait=wait)
        with self._lock:
            self._thread = None
            self._executor = None
            self._stop_event.clear()
            self._tick.clear()
            self._active_jobs = 0
        self._update_gauges()

    def restart(self) -> None:
        self.stop()
        self.start()

    def join(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.join()

    def register_job(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        interval: float,
        args: Optional[Iterable[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        start_after: Optional[float] = None,
        enabled: bool = True,
    ) -> ScheduledJob:
        if interval <= 0:
            raise ValueError("interval must be greater than zero")
        job = ScheduledJob(
            name=name,
            func=func,
            interval=float(interval),
            args=tuple(args) if args else (),
            kwargs=dict(kwargs or {}),
            enabled=enabled,
        )
        now = time.time()
        if enabled:
            if start_after is None:
                job.next_run = now + job.interval
            else:
                job.next_run = now + max(start_after, 0.0)
        else:
            job.next_run = float("inf")
        with self._lock:
            self._jobs[name] = job
        self._update_gauges()
        self._wake()
        return job

    def remove_job(self, name: str) -> bool:
        with self._lock:
            removed = self._jobs.pop(name, None)
        self._update_gauges()
        return removed is not None

    def enable_job(self, name: str, *, delay: Optional[float] = None) -> bool:
        with self._lock:
            job = self._jobs.get(name)
            if job is None:
                raise KeyError(name)
            job.enabled = True
            offset = delay if delay is not None else job.interval
            job.next_run = time.time() + max(offset, 0.0)
        self._update_gauges()
        self._wake()
        return True

    def disable_job(self, name: str) -> bool:
        with self._lock:
            job = self._jobs.get(name)
            if job is None:
                raise KeyError(name)
            job.enabled = False
            job.next_run = float("inf")
        self._update_gauges()
        return True

    def trigger_job(self, name: str, *, synchronous: bool = False) -> bool:
        with self._lock:
            job = self._jobs.get(name)
            if job is None:
                raise KeyError(name)
            if job.running:
                return False
            job.enabled = True
        self._dispatch(job, force_sync=synchronous)
        if not synchronous:
            self._wake()
        return True

    def get_job(self, name: str) -> Optional[ScheduledJob]:
        with self._lock:
            return self._jobs.get(name)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            jobs = [
                {
                    "name": job.name,
                    "interval_seconds": job.interval,
                    "next_run_at": _utc_iso(job.next_run),
                    "last_run_at": _utc_iso(job.last_run),
                    "last_duration_seconds": job.last_duration,
                    "total_runs": job.total_runs,
                    "running": job.running,
                    "enabled": job.enabled,
                    "error": job.error,
                }
                for job in self._jobs.values()
            ]
            queued = sum(1 for job in self._jobs.values() if job.enabled and not job.running)
            active = self._active_jobs
        return {
            "name": self._name,
            "max_workers": self._max_workers,
            "active_jobs": active,
            "queued_jobs": queued,
            "jobs": jobs,
        }


configure_logging()

dsn = os.getenv("SENTRY_DSN")
if sentry_sdk and dsn:  # pragma: no cover - optional dependency
    sentry_sdk.init(dsn=dsn)

flask_app = create_app()

scheduler = Scheduler(
    max_workers=int(flask_app.config.get("SCHEDULER_MAX_WORKERS", 4)),
)


def ping() -> str:
    return "pong"


scheduler.register_job("ping", ping, interval=60.0)
scheduler.register_job("run_due_sources", run_due_sources, interval=60.0)
scheduler.register_job("evaluate_alerts", evaluate_alerts, interval=120.0, start_after=30.0)
scheduler.register_job("discover_patterns", discover_patterns, interval=900.0, start_after=120.0)
scheduler.register_job("refresh_gematria_rollups", refresh_rollups_job, interval=900.0, start_after=180.0)


def main() -> None:
    scheduler.start()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:  # pragma: no cover - graceful shutdown
        scheduler.stop()


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()

