from __future__ import annotations

import types

import pytest

from app.services import workers


class DummyInspect:
    def __init__(self, data: dict):
        self._data = data

    def ping(self):
        return self._data.get("ping")

    def stats(self):
        return self._data.get("stats")

    def active(self):
        return self._data.get("active")

    def reserved(self):
        return self._data.get("reserved")

    def scheduled(self):
        return self._data.get("scheduled")

    def active_queues(self):
        return self._data.get("queues")

    def registered(self):
        return self._data.get("registered")


class DummyControl:
    def __init__(self, data: dict):
        self._data = data
        self.broadcast_calls: list[tuple[str, list[str] | None, dict | None]] = []

    def inspect(self, *_args, **_kwargs):
        return DummyInspect(self._data)

    def broadcast(self, command: str, destination=None, reply=True, arguments=None):
        self.broadcast_calls.append((command, destination, arguments))
        return [{"ok": True}]


def make_celery(control) -> types.SimpleNamespace:
    return types.SimpleNamespace(control=control)


def test_get_worker_overview_serializes_data(monkeypatch):
    inspect_data = {
        "ping": {"celery@host": {"ok": "pong"}},
        "stats": {
            "celery@host": {
                "hostname": "celery@host",
                "pid": 123,
                "pool": {
                    "max-concurrency": 4,
                    "processes": [111, 222],
                },
                "total": {"run_due_sources": 5},
            }
        },
        "active": {
            "celery@host": [
                {
                    "id": "task-1",
                    "name": "run_due_sources",
                    "args": [1, 2],
                    "kwargs": {"limit": 5},
                }
            ]
        },
        "reserved": {"celery@host": []},
        "scheduled": {
            "celery@host": [
                {
                    "eta": "2024-01-01T00:00:00",
                    "request": {
                        "id": "task-2",
                        "name": "run_due_sources",
                        "argsrepr": "(3,)",
                        "kwargsrepr": "{}",
                    },
                }
            ]
        },
        "queues": {"celery@host": [{"name": "celery"}]},
        "registered": {"celery@host": ["run_due_sources"]},
    }
    control = DummyControl(inspect_data)
    monkeypatch.setattr(workers, "celery", make_celery(control))

    overview = workers.get_worker_overview()

    assert overview["status"] == "ok"
    assert overview["workers"]
    worker = overview["workers"][0]
    assert worker["name"] == "celery@host"
    assert worker["online"] is True
    assert worker["queues"] == ["celery"]
    assert worker["active_processes"] == 2
    assert worker["configured_processes"] == 4
    assert worker["total_tasks"] == 5
    assert worker["active_tasks"][0]["args"].startswith("[1")
    assert worker["scheduled_tasks"][0]["args"] == "(3,)"


def test_execute_worker_command_start_stop_restart(monkeypatch):
    inspect_data = {
        "ping": {"celery@host": {"ok": "pong"}},
        "stats": {
            "celery@host": {
                "pool": {"max-concurrency": 3, "processes": [11, 12, 13]},
                "total": {},
            }
        },
    }
    control = DummyControl(inspect_data)
    monkeypatch.setattr(workers, "celery", make_celery(control))

    stop_result = workers.execute_worker_command("celery@host", "stop")
    assert stop_result["status"] == "ok"
    assert control.broadcast_calls[0][0] == "pool_shrink"
    assert control.broadcast_calls[0][2] == {"n": 3}

    control.broadcast_calls.clear()
    inspect_data["stats"]["celery@host"]["pool"]["processes"] = []
    start_result = workers.execute_worker_command("celery@host", "start")
    assert start_result["status"] == "ok"
    assert control.broadcast_calls[0][0] == "pool_grow"
    assert control.broadcast_calls[0][2] == {"n": 3}

    control.broadcast_calls.clear()
    restart_result = workers.execute_worker_command("celery@host", "restart")
    assert restart_result["status"] == "ok"
    assert control.broadcast_calls[0][0] == "pool_restart"


def test_execute_worker_command_validates(monkeypatch):
    inspect_data = {"ping": {}, "stats": {}}
    control = DummyControl(inspect_data)
    monkeypatch.setattr(workers, "celery", make_celery(control))

    with pytest.raises(ValueError):
        workers.execute_worker_command("celery@host", "invalid")

    with pytest.raises(workers.WorkerUnavailableError):
        workers.execute_worker_command("celery@host", "restart")


def test_execute_worker_command_wraps_errors(monkeypatch):
    class FailingControl(DummyControl):
        def broadcast(self, *args, **kwargs):  # pragma: no cover - explicit failure path
            raise RuntimeError("boom")

    inspect_data = {
        "ping": {"celery@host": {"ok": "pong"}},
        "stats": {"celery@host": {"pool": {"max-concurrency": 1, "processes": [1]}}},
    }
    control = FailingControl(inspect_data)
    monkeypatch.setattr(workers, "celery", make_celery(control))

    with pytest.raises(workers.WorkerCommandError):
        workers.execute_worker_command("celery@host", "restart")


def test_get_worker_overview_when_control_missing(monkeypatch):
    monkeypatch.setattr(workers, "celery", types.SimpleNamespace(control=None))

    overview = workers.get_worker_overview()

    assert overview["status"] == "unavailable"
    assert overview["workers"] == []
