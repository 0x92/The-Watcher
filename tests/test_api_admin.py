from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect

from app import create_app

from app.db import get_engine, get_session
from app.models import Base, Item, Setting, Source
from app.services.workers import WorkerCommandError, WorkerUnavailableError


@pytest.fixture()
def client_with_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "admin.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as client:
        yield client, db_url


@pytest.fixture()
def client_without_tables(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "empty.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as client:
        yield client, db_url


def _login(client):
    resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass"},
    )
    assert resp.status_code == 200


def test_worker_settings_flow(client_with_db):
    client, db_url = client_with_db
    _login(client)

    resp = client.get("/api/admin/worker-settings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["scrape_enabled"] is True
    assert data["default_interval_minutes"] >= 1

    update_resp = client.put(
        "/api/admin/worker-settings",
        json={
            "scrape_enabled": False,
            "default_interval_minutes": 42,
            "max_sources_per_cycle": 3,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()
    assert updated["scrape_enabled"] is False
    assert updated["default_interval_minutes"] == 42
    assert updated["max_sources_per_cycle"] == 3

    session = get_session(db_url)
    try:
        setting = session.get(Setting, "worker.scrape")
        assert setting is not None
        assert setting.value_json["scrape_enabled"] is False
        assert setting.value_json["default_interval_minutes"] == 42
        assert setting.value_json["max_sources_per_cycle"] == 3
    finally:
        session.close()


def test_worker_settings_initializes_table(client_without_tables):
    client, db_url = client_without_tables
    _login(client)

    resp = client.get("/api/admin/worker-settings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["scrape_enabled"] is True

    engine = get_engine(db_url)
    assert inspect(engine).has_table("settings")

    update_resp = client.put(
        "/api/admin/worker-settings",
        json={
            "scrape_enabled": False,
            "default_interval_minutes": 30,
            "max_sources_per_cycle": 2,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()
    assert updated["scrape_enabled"] is False
    assert updated["default_interval_minutes"] == 30
    assert updated["max_sources_per_cycle"] == 2

    session = get_session(db_url)
    try:
        setting = session.get(Setting, "worker.scrape")
        assert setting is not None
        assert setting.value_json["scrape_enabled"] is False
        assert setting.value_json["default_interval_minutes"] == 30
        assert setting.value_json["max_sources_per_cycle"] == 2
    finally:
        session.close()


def test_gematria_settings_flow(client_with_db):
    client, db_url = client_with_db
    _login(client)

    resp = client.get("/api/admin/gematria-settings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["available"], list) and data["available"]
    assert isinstance(data["enabled"], list) and data["enabled"]
    assert "defaults" in data and isinstance(data["defaults"].get("enabled"), list)

    update_resp = client.put(
        "/api/admin/gematria-settings",
        json={"enabled": ["prime", "sumerian"], "ignore_pattern": "[^A-ZÄÖÜ]"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()
    assert updated["enabled"] == ["prime", "sumerian"]
    assert updated["ignore_pattern"] == "[^A-ZÄÖÜ]"

    session = get_session(db_url)
    try:
        setting = session.get(Setting, "gematria.settings")
        assert setting is not None
        assert setting.value_json["enabled_schemes"] == ["prime", "sumerian"]
        assert setting.value_json["ignore_pattern"] == "[^A-ZÄÖÜ]"
    finally:
        session.close()


def test_sources_crud(client_with_db):
    client, db_url = client_with_db
    _login(client)

    # Adjust worker default to verify usage when creating a source
    client.put(
        "/api/admin/worker-settings",
        json={"default_interval_minutes": 25},
    )

    list_resp = client.get("/api/admin/sources")
    assert list_resp.status_code == 200
    listing = list_resp.get_json()
    assert listing["sources"] == []
    assert listing["meta"]["total_sources"] == 0
    assert listing["meta"]["total_sources_all"] == 0

    create_resp = client.post(
        "/api/admin/sources",
        json={
            "name": "Example Feed",
            "type": "rss",
            "endpoint": "http://example.com/feed",
            "enabled": True,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.get_json()
    assert created["name"] == "Example Feed"
    assert created["interval_minutes"] == 25
    assert created["stats"]["total_items"] == 0
    source_id = created["id"]

    update_resp = client.put(
        f"/api/admin/sources/{source_id}",
        json={"enabled": False, "interval_minutes": 5},
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()
    assert updated["enabled"] is False
    assert updated["interval_minutes"] == 5
    assert updated["stats"]["total_items"] == 0

    delete_resp = client.delete(f"/api/admin/sources/{source_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()["status"] == "deleted"

    final_resp = client.get("/api/admin/sources")
    assert final_resp.status_code == 200
    final_listing = final_resp.get_json()
    assert final_listing["sources"] == []
    assert final_listing["meta"]["total_sources_all"] == 0


def test_sources_overview_and_filters(client_with_db):
    client, db_url = client_with_db
    _login(client)

    session = get_session(db_url)
    try:
        rss_source = Source(
            name="Alpha Feed",
            type="rss",
            endpoint="http://alpha.test/feed",
            enabled=True,
            interval_sec=900,
        )
        atom_source = Source(
            name="Beta Feed",
            type="atom",
            endpoint="http://beta.test/feed",
            enabled=False,
            interval_sec=1800,
        )
        session.add_all([rss_source, atom_source])
        session.commit()

        now = datetime.utcnow()
        session.add_all(
            [
                Item(
                    source_id=rss_source.id,
                    url="http://alpha.test/item-1",
                    title="Alpha One",
                    fetched_at=now - timedelta(minutes=30),
                    published_at=now - timedelta(minutes=40),
                ),
                Item(
                    source_id=rss_source.id,
                    url="http://alpha.test/item-2",
                    title="Alpha Two",
                    fetched_at=now - timedelta(minutes=10),
                    published_at=now - timedelta(minutes=12),
                ),
                Item(
                    source_id=atom_source.id,
                    url="http://beta.test/item-1",
                    title="Beta One",
                    fetched_at=now - timedelta(minutes=20),
                    published_at=now - timedelta(minutes=25),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    resp = client.get("/api/admin/sources")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["meta"]["total_sources"] == 2
    assert payload["meta"]["active_sources"] == 1
    assert payload["meta"]["inactive_sources"] == 1
    assert payload["meta"]["total_items"] == 3
    assert payload["meta"]["type_breakdown"] == {"atom": 1, "rss": 1}
    assert payload["filters"] == {"query": None, "types": [], "enabled": None}

    alpha = next(entry for entry in payload["sources"] if entry["name"] == "Alpha Feed")
    assert alpha["stats"]["total_items"] == 2
    assert alpha["stats"]["latest_item"]["title"] == "Alpha Two"

    beta = next(entry for entry in payload["sources"] if entry["name"] == "Beta Feed")
    assert beta["enabled"] is False
    assert beta["stats"]["total_items"] == 1

    query_resp = client.get("/api/admin/sources?q=Beta")
    assert query_resp.status_code == 200
    query_payload = query_resp.get_json()
    assert len(query_payload["sources"]) == 1
    assert query_payload["sources"][0]["name"] == "Beta Feed"
    assert query_payload["filters"]["query"] == "Beta"

    disabled_resp = client.get("/api/admin/sources?enabled=false")
    assert disabled_resp.status_code == 200
    disabled_payload = disabled_resp.get_json()
    assert len(disabled_payload["sources"]) == 1
    assert disabled_payload["sources"][0]["enabled"] is False
    assert disabled_payload["filters"]["enabled"] is False

    rss_resp = client.get("/api/admin/sources?type=rss")
    assert rss_resp.status_code == 200
    rss_payload = rss_resp.get_json()
    assert len(rss_payload["sources"]) == 1
    assert rss_payload["sources"][0]["type"] == "rss"


def test_worker_overview_endpoint(client_with_db, monkeypatch):
    client, _ = client_with_db
    _login(client)

    payload = {
        "status": "ok",
        "updated_at": "2024-01-01T00:00:00Z",
        "workers": [{"id": "scheduler", "status": "online"}],
    }
    monkeypatch.setattr("app.blueprints.api.admin.get_worker_overview", lambda: payload)

    resp = client.get("/api/admin/workers")
    assert resp.status_code == 200
    assert resp.get_json() == payload


def test_worker_command_endpoint(client_with_db, monkeypatch):
    client, _ = client_with_db
    _login(client)

    called = {}

    def fake_execute(worker_name, action):
        called["worker"] = worker_name
        called["action"] = action
        return {"status": "ok", "action": action, "message": "done"}

    monkeypatch.setattr("app.blueprints.api.admin.execute_worker_command", fake_execute)

    resp = client.post(
        "/api/admin/workers/scheduler/control",
        json={"action": "restart"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "restart"
    assert called == {"worker": "scheduler", "action": "restart"}

    invalid_resp = client.post(
        "/api/admin/workers/scheduler/control",
        json={"action": ""},
    )
    assert invalid_resp.status_code == 400


def test_worker_command_endpoint_handles_errors(client_with_db, monkeypatch):
    client, _ = client_with_db
    _login(client)

    def raise_unavailable(*_args, **_kwargs):
        raise WorkerUnavailableError("scheduler")

    monkeypatch.setattr(
        "app.blueprints.api.admin.execute_worker_command",
        raise_unavailable,
    )

    unavailable = client.post(
        "/api/admin/workers/scheduler/control",
        json={"action": "start"},
    )
    assert unavailable.status_code == 404

    def raise_command_error(*_args, **_kwargs):
        raise WorkerCommandError("kaputt")

    monkeypatch.setattr(
        "app.blueprints.api.admin.execute_worker_command",
        raise_command_error,
    )

    failed = client.post(
        "/api/admin/workers/scheduler/control",
        json={"action": "restart"},
    )
    assert failed.status_code == 503
    assert "kaputt" in failed.get_json()["error"]

