from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

# Lazy Celery import is required to avoid circular imports during app initialisation.
celery = None


def _get_celery():
    global celery
    if celery is not None:
        return celery
    try:  # pragma: no cover - import guarded for circular dependencies
        from celery_app import celery as celery_instance
    except Exception:
        return None
    celery = celery_instance
    return celery


@dataclass
class WorkerUnavailableError(RuntimeError):
    """Raised when a worker cannot be reached."""

    worker: str

    def __str__(self) -> str:  # pragma: no cover - trivial representation
        return f"Worker '{self.worker}' ist nicht erreichbar"


class WorkerCommandError(RuntimeError):
    """Raised when a worker command could not be executed."""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return repr(value)
    except Exception:  # pragma: no cover - defensive fallback
        return str(value)


def _serialize_task_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        return {"name": "", "id": ""}

    request = entry.get("request")
    if isinstance(request, dict):
        base = request
    else:
        base = entry

    delivery_info = base.get("delivery_info")
    queue = None
    if isinstance(delivery_info, dict):
        queue = delivery_info.get("routing_key") or delivery_info.get("queue")

    return {
        "id": str(base.get("id") or ""),
        "name": base.get("name") or base.get("task") or "",
        "args": base.get("argsrepr") or _stringify(base.get("args")),
        "kwargs": base.get("kwargsrepr") or _stringify(base.get("kwargs")),
        "eta": entry.get("eta") or base.get("eta"),
        "state": base.get("state") or entry.get("state"),
        "runtime": base.get("runtime"),
        "queue": queue,
        "retries": base.get("retries"),
    }


def _current_processes(info: Dict[str, Any]) -> int:
    processes = info.get("processes")
    if isinstance(processes, (list, tuple, set)):
        return len(processes)
    if isinstance(processes, dict):
        return len(processes)
    return _safe_int(info.get("writes"), 0)


def _configured_processes(stats: Dict[str, Any]) -> int:
    pool = stats.get("pool") or {}
    for key in ("max-concurrency", "max_concurrency", "limit"):
        if key in pool:
            value = _safe_int(pool.get(key))
            if value > 0:
                return value
    fallback = stats.get("concurrency")
    if isinstance(fallback, (int, float)):
        return max(1, int(fallback))
    return max(_current_processes(pool), 1)


def _collect_worker_names(mappings: Iterable[Dict[str, Any] | None]) -> List[str]:
    names: set[str] = set()
    for mapping in mappings:
        if isinstance(mapping, dict):
            names.update(mapping.keys())
    return sorted(names)


def get_worker_overview() -> Dict[str, Any]:
    """Return an overview of all known Celery workers."""

    timestamp = datetime.now(timezone.utc).isoformat()
    celery_app = _get_celery()
    control = getattr(celery_app, "control", None)
    if control is None:
        return {
            "workers": [],
            "status": "unavailable",
            "updated_at": timestamp,
            "message": "Celery-Steuerung ist nicht verfügbar.",
        }

    try:
        inspector = control.inspect()
    except Exception as exc:  # pragma: no cover - connectivity issues
        return {
            "workers": [],
            "status": "error",
            "updated_at": timestamp,
            "message": f"Celery-Inspektion fehlgeschlagen: {exc}",
        }

    if inspector is None:
        return {
            "workers": [],
            "status": "unavailable",
            "updated_at": timestamp,
            "message": "Keine Worker erreichbar.",
        }

    ping = inspector.ping() or {}
    stats = inspector.stats() or {}
    active = inspector.active() or {}
    reserved = inspector.reserved() or {}
    scheduled = inspector.scheduled() or {}
    queues = inspector.active_queues() or {}
    registered = inspector.registered() or {}

    workers: List[Dict[str, Any]] = []
    for name in _collect_worker_names(
        [stats, active, reserved, scheduled, queues, registered, ping]
    ):
        info = stats.get(name, {})
        pool = info.get("pool") or {}
        current_processes = _current_processes(pool)
        configured_processes = _configured_processes(info) if info else None

        active_tasks = [
            _serialize_task_entry(task)
            for task in active.get(name, [])
            if isinstance(task, dict)
        ]
        reserved_tasks = [
            _serialize_task_entry(task)
            for task in reserved.get(name, [])
            if isinstance(task, dict)
        ]
        scheduled_tasks = [
            _serialize_task_entry(task)
            for task in scheduled.get(name, [])
            if isinstance(task, dict)
        ]

        queue_names = []
        for queue in queues.get(name, []) or []:
            if isinstance(queue, dict):
                label = queue.get("name") or queue.get("routing_key")
                if label:
                    queue_names.append(str(label))

        total_tasks = 0
        totals = info.get("total")
        if isinstance(totals, dict):
            total_tasks = sum(_safe_int(value) for value in totals.values())

        workers.append(
            {
                "id": name,
                "name": name,
                "online": name in ping,
                "status": "online" if name in ping else "offline",
                "active_processes": current_processes,
                "configured_processes": configured_processes,
                "queues": queue_names,
                "active_tasks": active_tasks,
                "reserved_tasks": reserved_tasks,
                "scheduled_tasks": scheduled_tasks,
                "registered_tasks": registered.get(name, []),
                "total_tasks": total_tasks,
                "pid": info.get("pid"),
                "uptime": info.get("uptime"),
                "hostname": info.get("hostname"),
                "sw_ver": info.get("sw_ver"),
            }
        )

    return {"workers": workers, "status": "ok", "updated_at": timestamp}


def execute_worker_command(worker_name: str, action: str) -> Dict[str, Any]:
    """Execute a control command on a Celery worker."""

    normalized = (action or "").strip().lower()
    if not normalized:
        raise ValueError("Aktion darf nicht leer sein")
    if normalized not in {"start", "stop", "restart"}:
        raise ValueError(f"Unbekannte Aktion: {action}")

    celery_app = _get_celery()
    control = getattr(celery_app, "control", None)
    if control is None:
        raise WorkerCommandError("Celery-Steuerung ist nicht verfügbar")

    try:
        inspector = control.inspect([worker_name])
    except Exception as exc:  # pragma: no cover - connectivity issues
        raise WorkerCommandError(f"Celery-Inspektion fehlgeschlagen: {exc}") from exc

    if inspector is None:
        raise WorkerUnavailableError(worker_name)

    ping = inspector.ping() or {}
    if worker_name not in ping:
        raise WorkerUnavailableError(worker_name)

    stats = inspector.stats() or {}
    info = stats.get(worker_name, {})
    pool = info.get("pool") or {}
    current_processes = _current_processes(pool)
    configured_processes = _configured_processes(info) if info else 1

    try:
        if normalized == "stop":
            if current_processes <= 0:
                return {
                    "status": "ok",
                    "action": normalized,
                    "message": "Worker ist bereits gestoppt.",
                }
            reply = control.broadcast(
                "pool_shrink",
                destination=[worker_name],
                reply=True,
                arguments={"n": current_processes},
            )
            return {
                "status": "ok",
                "action": normalized,
                "message": f"Worker {worker_name} wurde gestoppt.",
                "details": reply,
            }

        if normalized == "start":
            grow_by = max(configured_processes - current_processes, 0)
            if grow_by <= 0:
                if current_processes <= 0:
                    grow_by = max(configured_processes, 1)
                else:
                    return {
                        "status": "ok",
                        "action": normalized,
                        "message": "Worker läuft bereits mit voller Kapazität.",
                    }
            reply = control.broadcast(
                "pool_grow",
                destination=[worker_name],
                reply=True,
                arguments={"n": grow_by},
            )
            return {
                "status": "ok",
                "action": normalized,
                "message": f"Worker {worker_name} wurde gestartet.",
                "details": reply,
            }

        reply = control.broadcast(
            "pool_restart", destination=[worker_name], reply=True
        )
        return {
            "status": "ok",
            "action": normalized,
            "message": f"Worker {worker_name} wurde neu gestartet.",
            "details": reply,
        }
    except Exception as exc:  # pragma: no cover - connectivity issues
        raise WorkerCommandError(str(exc)) from exc


__all__ = [
    "execute_worker_command",
    "get_worker_overview",
    "WorkerCommandError",
    "WorkerUnavailableError",
]
