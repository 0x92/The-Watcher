from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import create_app
from app.db import get_engine, get_session
from app.models import Base, CrawlerRun, Source
from app.services.workers import WorkerCommandError, WorkerUnavailableError


@pytest.fixture()
def client_with_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "crawlers.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as client:
        yield client, db_url


def _login(client):
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass"},
    )
    assert response.status_code == 200


def _create_source(session, **overrides):
    source = Source(
        name=overrides.get("name", "Test Feed"),
        type=overrides.get("type", "rss"),
        endpoint=overrides.get("endpoint", "http://example.com/feed"),
        enabled=overrides.get("enabled", True),
        interval_sec=overrides.get("interval_sec", 900),
        priority=overrides.get("priority", 0),
    )
    if overrides.get("tags") is not None:
        source.tags_json = overrides["tags"]
    if overrides.get("notes") is not None:
        source.notes = overrides["notes"]
    session.add(source)
    session.commit()
    return source


def test_crawler_overview_returns_metrics(client_with_db, monkeypatch):
    client, db_url = client_with_db
    _login(client)

    session = get_session(db_url)
    try:
        source = _create_source(
            session,
            name="Alpha",
            endpoint="http://alpha.test/feed",
            priority=3,
            tags=["breaking"],
        )
        session.add(
            CrawlerRun(
                source_id=source.id,
                started_at=datetime.utcnow() - timedelta(hours=1),
                finished_at=datetime.utcnow() - timedelta(minutes=50),
                status="ok",
                items_fetched=7,
                duration_ms=2500,
            )
        )
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(
        "app.blueprints.api.crawlers.get_worker_overview",
        lambda: {
            "status": "ok",
            "updated_at": "2024-01-01T00:00:00Z",
            "workers": [
                {
                    "id": "scheduler",
                    "status": "online",
                    "queued_jobs": 0,
                    "active_jobs": 0,
                    "max_workers": 4,
                    "jobs": [],
                }
            ],
        },
    )

    response = client.get("/api/crawlers?window_hours=24")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["sources"]["total"] == 1
    assert payload["sources"]["degraded"] == 0
    assert payload["runs"]["total"] == 1
    assert payload["runs"]["failed"] == 0
    assert payload["workers"]["status"] == "ok"


def test_list_feeds_with_filters(client_with_db):
    client, db_url = client_with_db
    _login(client)

    session = get_session(db_url)
    try:
        primary = _create_source(
            session,
            name="Primary",
            endpoint="http://primary.test/rss",
            priority=5,
            tags=["alert", "world"],
            notes="High priority",
        )
        secondary = _create_source(
            session,
            name="Secondary",
            endpoint="http://secondary.test/rss",
            enabled=False,
            tags=["local"],
        )
        session.add_all(
            [
                CrawlerRun(
                    source_id=primary.id,
                    started_at=datetime.utcnow() - timedelta(hours=2),
                    finished_at=datetime.utcnow() - timedelta(hours=2, minutes=10),
                    status="ok",
                    items_fetched=4,
                    duration_ms=1500,
                ),
                CrawlerRun(
                    source_id=secondary.id,
                    started_at=datetime.utcnow() - timedelta(hours=3),
                    finished_at=datetime.utcnow() - timedelta(hours=3, minutes=5),
                    status="failed",
                    items_fetched=0,
                    duration_ms=1200,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get("/api/crawlers/feeds?tags=alert&include_runs=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["meta"]["total_sources"] == 1
    feed = payload["sources"][0]
    assert feed["name"] == "Primary"
    assert feed["priority"] == 5
    assert feed["tags"] == ["alert", "world"]
    assert feed["notes"] == "High priority"
    assert feed["runs"]


def test_create_and_update_feed_flow(client_with_db):
    client, db_url = client_with_db
    _login(client)

    create_payload = {
        "name": "Watcher",
        "endpoint": "http://watcher.test/rss",
        "type": "rss",
        "interval_minutes": 30,
        "priority": 2,
        "tags": ["watch", "risk"],
        "notes": "Initial",
        "enabled": True,
    }

    response = client.post("/api/crawlers/feeds", json=create_payload)
    assert response.status_code == 201
    created = response.get_json()
    assert created["priority"] == 2
    assert created["tags"] == ["watch", "risk"]
    assert created["notes"] == "Initial"

    source_id = created["id"]
    update_payload = {
        "priority": 8,
        "tags": ["watch", "urgent"],
        "notes": "Überarbeitet",
        "enabled": False,
    }
    update_resp = client.put(f"/api/crawlers/feeds/{source_id}", json=update_payload)
    assert update_resp.status_code == 200
    updated = update_resp.get_json()
    assert updated["priority"] == 8
    assert updated["tags"] == ["watch", "urgent"]
    assert updated["notes"] == "Überarbeitet"
    assert updated["enabled"] is False

    session = get_session(db_url)
    try:
        stored = session.get(Source, source_id)
        assert stored.priority == 8
        assert stored.tags_json == ["watch", "urgent"]
        assert stored.notes == "Überarbeitet"
        assert stored.enabled is False
    finally:
        session.close()


def test_health_check_endpoint_sets_status(client_with_db):
    client, db_url = client_with_db
    _login(client)

    session = get_session(db_url)
    try:
        source = _create_source(session, name="Health", endpoint="http://health.test/rss")
    finally:
        session.close()

    response = client.post(f"/api/crawlers/feeds/{source.id}/actions/health-check")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "manual_check_pending"

    session = get_session(db_url)
    try:
        refreshed = session.get(Source, source.id)
        assert refreshed.last_status == "manual_check_pending"
        assert refreshed.last_checked_at is not None
    finally:
        session.close()


def test_bulk_action_updates_priority(client_with_db):
    client, db_url = client_with_db
    _login(client)

    session = get_session(db_url)
    try:
        a = _create_source(session, name="Alpha", endpoint="http://alpha.test/rss", priority=1)
        b = _create_source(session, name="Beta", endpoint="http://beta.test/rss", priority=1)
    finally:
        session.close()

    response = client.post(
        "/api/crawlers/feeds/bulk",
        json={
            "ids": [a.id, b.id],
            "action": "set_priority",
            "payload": {"priority": 9},
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["processed"] == 2

    session = get_session(db_url)
    try:
        refreshed = session.query(Source).filter(Source.id.in_([a.id, b.id])).all()
        assert all(src.priority == 9 for src in refreshed)
    finally:
        session.close()


def test_worker_control_handles_errors(client_with_db, monkeypatch):
    client, _ = client_with_db
    _login(client)

    def raise_unavailable(*_args, **_kwargs):
        raise WorkerUnavailableError("scheduler")

    monkeypatch.setattr("app.blueprints.api.crawlers.execute_worker_command", raise_unavailable)
    unavailable = client.post("/api/crawlers/scheduler/control", json={"action": "start"})
    assert unavailable.status_code == 404

    def raise_command_error(*_args, **_kwargs):
        raise WorkerCommandError("kaputt")

    monkeypatch.setattr("app.blueprints.api.crawlers.execute_worker_command", raise_command_error)
    failed = client.post("/api/crawlers/scheduler/control", json={"action": "restart"})
    assert failed.status_code == 503
    assert "kaputt" in failed.get_json()["error"]
