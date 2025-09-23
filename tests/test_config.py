from __future__ import annotations

import importlib

import config


def test_default_opensearch_host_prefers_compose(monkeypatch):
    monkeypatch.delenv("OPENSEARCH_HOST", raising=False)
    monkeypatch.setattr(config.socket, "gethostbyname", lambda host: "127.0.0.1")

    assert config._default_opensearch_host() == "http://opensearch:9200"


def test_default_opensearch_host_falls_back(monkeypatch):
    monkeypatch.delenv("OPENSEARCH_HOST", raising=False)

    def raise_oserror(_host: str) -> str:
        raise OSError("unresolvable")

    monkeypatch.setattr(config.socket, "gethostbyname", raise_oserror)

    assert config._default_opensearch_host() == "http://localhost:9200"


def test_scheduler_max_workers_from_env(monkeypatch):
    monkeypatch.setenv("SCHEDULER_MAX_WORKERS", "8")
    reloaded = importlib.reload(config)
    assert reloaded.Config.SCHEDULER_MAX_WORKERS == 8

    monkeypatch.setenv("SCHEDULER_MAX_WORKERS", "-3")
    reloaded = importlib.reload(config)
    assert reloaded.Config.SCHEDULER_MAX_WORKERS == 4

    monkeypatch.delenv("SCHEDULER_MAX_WORKERS", raising=False)
    reloaded = importlib.reload(config)
    assert reloaded.Config.SCHEDULER_MAX_WORKERS == 4
