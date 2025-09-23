from __future__ import annotations

import pytest

from app.services import workers


class DummyScheduler:
    def __init__(self) -> None:
        self.is_running = True
        self.snapshot_data = {
            "name": "scheduler",
            "max_workers": 2,
            "active_jobs": 1,
            "queued_jobs": 3,
            "jobs": [
                {
                    "name": "run_due_sources",
                    "interval_seconds": 60.0,
                    "next_run_at": "2024-01-01T00:00:00Z",
                    "last_run_at": None,
                    "last_duration_seconds": 1.2,
                    "total_runs": 5,
                    "running": False,
                    "enabled": True,
                    "error": None,
                }
            ],
        }
        self.commands: list[tuple[str, str | None]] = []
        self.jobs = {"run_due_sources": object()}

    def snapshot(self):
        return self.snapshot_data

    def start(self):
        self.commands.append(("start", None))
        self.is_running = True

    def stop(self):
        self.commands.append(("stop", None))
        self.is_running = False

    def restart(self):
        self.commands.append(("restart", None))
        self.is_running = True

    def get_job(self, name: str):
        return self.jobs.get(name)

    def enable_job(self, name: str, delay: float = 0.0):
        self.commands.append(("enable", name))

    def disable_job(self, name: str):
        self.commands.append(("disable", name))

    def trigger_job(self, name: str):
        self.commands.append(("trigger", name))
        return True


@pytest.fixture(autouse=True)
def _reset_scheduler(monkeypatch):
    monkeypatch.setattr(workers, "scheduler", None)
    yield
    monkeypatch.setattr(workers, "scheduler", None)


def test_get_worker_overview_serializes_scheduler(monkeypatch):
    dummy = DummyScheduler()
    monkeypatch.setattr(workers, "scheduler", dummy)
    monkeypatch.setattr(workers, "_get_scheduler", lambda: dummy)

    overview = workers.get_worker_overview()

    assert overview["status"] == "ok"
    assert overview["workers"]
    worker = overview["workers"][0]
    assert worker["id"] == "scheduler"
    assert worker["online"] is True
    assert worker["active_jobs"] == 1
    assert worker["queued_jobs"] == 3
    assert worker["jobs"][0]["name"] == "run_due_sources"


def test_get_worker_overview_when_scheduler_missing(monkeypatch):
    monkeypatch.setattr(workers, "scheduler", None)
    monkeypatch.setattr(workers, "_get_scheduler", lambda: None)

    overview = workers.get_worker_overview()

    assert overview["status"] == "unavailable"
    assert overview["workers"] == []


def test_execute_worker_command_controls_scheduler(monkeypatch):
    dummy = DummyScheduler()
    monkeypatch.setattr(workers, "scheduler", dummy)
    monkeypatch.setattr(workers, "_get_scheduler", lambda: dummy)

    start_result = workers.execute_worker_command("scheduler", "start")
    assert start_result["status"] == "ok"
    assert ("start", None) in dummy.commands

    stop_result = workers.execute_worker_command("scheduler", "stop")
    assert stop_result["status"] == "ok"
    assert ("stop", None) in dummy.commands

    restart_result = workers.execute_worker_command("scheduler", "restart")
    assert restart_result["status"] == "ok"
    assert ("restart", None) in dummy.commands


def test_execute_worker_command_controls_jobs(monkeypatch):
    dummy = DummyScheduler()
    monkeypatch.setattr(workers, "scheduler", dummy)
    monkeypatch.setattr(workers, "_get_scheduler", lambda: dummy)

    start_result = workers.execute_worker_command("run_due_sources", "start")
    assert start_result["status"] == "ok"
    assert ("enable", "run_due_sources") in dummy.commands

    stop_result = workers.execute_worker_command("run_due_sources", "stop")
    assert stop_result["status"] == "ok"
    assert ("disable", "run_due_sources") in dummy.commands

    restart_result = workers.execute_worker_command("run_due_sources", "restart")
    assert restart_result["status"] == "ok"
    assert ("trigger", "run_due_sources") in dummy.commands


def test_execute_worker_command_validates(monkeypatch):
    dummy = DummyScheduler()
    monkeypatch.setattr(workers, "scheduler", dummy)
    monkeypatch.setattr(workers, "_get_scheduler", lambda: dummy)

    with pytest.raises(ValueError):
        workers.execute_worker_command("scheduler", "invalid")

    dummy.jobs.clear()
    with pytest.raises(workers.WorkerUnavailableError):
        workers.execute_worker_command("unknown", "restart")

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("kaputt")

    dummy.jobs["run_due_sources"] = object()
    monkeypatch.setattr(dummy, "trigger_job", raise_error)
    with pytest.raises(workers.WorkerCommandError):
        workers.execute_worker_command("run_due_sources", "restart")
