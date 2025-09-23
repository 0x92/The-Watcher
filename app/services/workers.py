from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

scheduler = None


def _get_scheduler():
    global scheduler
    if scheduler is not None:
        return scheduler
    try:  # pragma: no cover - optional dependency
        from scheduler_app import scheduler as scheduler_instance
    except Exception:
        return None
    scheduler = scheduler_instance
    return scheduler


@dataclass
class WorkerUnavailableError(RuntimeError):
    """Raised when a requested job or worker does not exist."""

    worker: str

    def __str__(self) -> str:  # pragma: no cover - trivial representation
        return f"Worker '{self.worker}' ist nicht verfügbar"


class WorkerCommandError(RuntimeError):
    """Raised when a scheduler command cannot be executed."""


def _normalize_action(action: str) -> str:
    normalized = (action or "").strip().lower()
    if normalized not in {"start", "stop", "restart"}:
        raise ValueError(f"Unbekannte Aktion: {action}")
    return normalized


def _serialize_worker_snapshot(snapshot: Dict[str, Any], *, running: bool) -> Dict[str, Any]:
    jobs = []
    for job in snapshot.get("jobs", []):
        jobs.append(
            {
                "name": job.get("name"),
                "interval_seconds": job.get("interval_seconds"),
                "next_run_at": job.get("next_run_at"),
                "last_run_at": job.get("last_run_at"),
                "last_duration_seconds": job.get("last_duration_seconds"),
                "total_runs": job.get("total_runs", 0),
                "running": job.get("running", False),
                "enabled": job.get("enabled", True),
                "error": job.get("error"),
            }
        )

    return {
        "id": snapshot.get("name", "scheduler"),
        "name": snapshot.get("name", "scheduler"),
        "status": "online" if running else "stopped",
        "online": bool(running),
        "active_jobs": snapshot.get("active_jobs", 0),
        "queued_jobs": snapshot.get("queued_jobs", 0),
        "max_workers": snapshot.get("max_workers", 1),
        "jobs": jobs,
    }


def get_worker_overview() -> Dict[str, Any]:
    """Return scheduler status information for the admin API."""

    timestamp = datetime.now(timezone.utc).isoformat()
    scheduler_app = _get_scheduler()
    if scheduler_app is None:
        return {
            "workers": [],
            "status": "unavailable",
            "updated_at": timestamp,
            "message": "Scheduler ist nicht verfügbar.",
        }

    snapshot = scheduler_app.snapshot()
    running = scheduler_app.is_running
    worker_info = _serialize_worker_snapshot(snapshot, running=running)
    status = "ok" if running else "stopped"

    return {
        "workers": [worker_info],
        "status": status,
        "updated_at": timestamp,
    }


def _ensure_scheduler() -> Any:
    scheduler_app = _get_scheduler()
    if scheduler_app is None:
        raise WorkerCommandError("Scheduler-Steuerung ist nicht verfügbar")
    return scheduler_app


def execute_worker_command(worker_name: str, action: str) -> Dict[str, Any]:
    """Execute a control command on the scheduler or an individual job."""

    normalized = _normalize_action(action)
    scheduler_app = _ensure_scheduler()

    try:
        if worker_name == "scheduler":
            if normalized == "start":
                scheduler_app.start()
                message = "Scheduler wurde gestartet."
            elif normalized == "stop":
                scheduler_app.stop()
                message = "Scheduler wurde gestoppt."
            else:
                scheduler_app.restart()
                message = "Scheduler wurde neu gestartet."
            return {"status": "ok", "action": normalized, "worker": worker_name, "message": message}

        job = scheduler_app.get_job(worker_name)
        if job is None:
            raise WorkerUnavailableError(worker_name)

        if normalized == "start":
            scheduler_app.enable_job(worker_name, delay=0.0)
            message = f"Job {worker_name} wurde aktiviert."
        elif normalized == "stop":
            scheduler_app.disable_job(worker_name)
            message = f"Job {worker_name} wurde deaktiviert."
        else:
            triggered = scheduler_app.trigger_job(worker_name)
            if not triggered:
                message = f"Job {worker_name} läuft bereits."
            else:
                message = f"Job {worker_name} wurde ausgelöst."

        return {
            "status": "ok",
            "action": normalized,
            "worker": worker_name,
            "message": message,
        }
    except WorkerUnavailableError:
        raise
    except KeyError as exc:
        raise WorkerUnavailableError(str(exc)) from exc
    except ValueError as exc:
        raise WorkerCommandError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise WorkerCommandError(str(exc)) from exc


__all__ = [
    "execute_worker_command",
    "get_worker_overview",
    "WorkerCommandError",
    "WorkerUnavailableError",
]
