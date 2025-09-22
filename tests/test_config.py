from __future__ import annotations

import importlib
import config


def test_default_redis_url_prefers_compose_host(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(config.socket, "gethostbyname", lambda host: "127.0.0.1")

    assert config._default_redis_url() == "redis://redis:6379/0"


def test_default_redis_url_falls_back_to_local(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    def raise_oserror(_host: str) -> str:
        raise OSError("unresolvable")

    monkeypatch.setattr(config.socket, "gethostbyname", raise_oserror)

    assert config._default_redis_url() == "redis://localhost:6379/0"


def test_default_redis_url_uses_environment(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://custom:6379/1")

    assert config._default_redis_url() == "redis://custom:6379/1"


def test_config_class_reads_environment(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://override:6379/5")
    reloaded = importlib.reload(config)
    assert reloaded.Config.REDIS_URL == "redis://override:6379/5"

    monkeypatch.delenv("REDIS_URL", raising=False)
    importlib.reload(config)
