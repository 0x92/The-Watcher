from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sqlalchemy import select

from app import create_app
from app.db import get_engine, get_session
from app.models import Base, Gematria, GematriaRollup, Item, Source


@pytest.fixture()
def client_with_rollups(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "analytics.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as client:
        yield client, db_url


def _login(client, role: str = "analyst") -> None:
    credentials = {
        "analyst": {"email": "analyst@example.com", "password": "analystpass"},
        "admin": {"email": "admin@example.com", "password": "adminpass"},
    }[role]
    resp = client.post("/auth/login", json=credentials)
    assert resp.status_code == 200


def _seed(session, now: datetime) -> None:
    source = Source(name="Reuters", type="rss", endpoint="https://example.com/rss", priority=4)
    session.add(source)
    session.flush()

    for index, value in enumerate([93, 74, 88], start=1):
        item = Item(
            source_id=source.id,
            fetched_at=now - timedelta(hours=index * 3),
            published_at=now - timedelta(hours=index * 3),
            url=f"https://example.com/{index}",
            title=f"Sample headline {index}",
        )
        session.add(item)
        session.flush()
        session.add(Gematria(item_id=item.id, scheme="simple", value=value))
    session.commit()


def test_gematria_analytics_requires_auth(client_with_rollups):
    client, _ = client_with_rollups
    response = client.get("/api/analytics/gematria")
    assert response.status_code in {302, 401}


def test_gematria_analytics_returns_rollup(client_with_rollups):
    client, db_url = client_with_rollups
    _login(client, "admin")

    current = datetime.utcnow()
    session = get_session(db_url)
    try:
        _seed(session, current)
    finally:
        session.close()

    rebuild = client.post("/api/analytics/gematria/rebuild", json={"windows": [24], "schemes": ["simple"]})
    assert rebuild.status_code == 202

    response = client.get("/api/analytics/gematria?window=24&scheme=simple")
    assert response.status_code == 200
    payload = response.get_json()
    assert "summary" in payload
    assert isinstance(payload["summary"].get("total_items"), int)


def test_gematria_rebuild_requires_admin(client_with_rollups):
    client, db_url = client_with_rollups
    _login(client, "admin")

    current = datetime.utcnow()
    session = get_session(db_url)
    try:
        _seed(session, current)
    finally:
        session.close()

    response = client.post("/api/analytics/gematria/rebuild", json={"windows": [24], "schemes": ["simple"]})
    assert response.status_code == 202
    payload = response.get_json()
    assert payload["updated"] >= 1


def test_invalid_scheme_returns_error(client_with_rollups):
    client, _ = client_with_rollups
    _login(client, "analyst")
    response = client.get("/api/analytics/gematria?scheme=unknown-scheme")
    assert response.status_code == 400
    assert "error" in response.get_json()

