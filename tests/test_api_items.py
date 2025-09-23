from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.models import Base, Gematria, Item, Source


def _seed(db_url: str) -> datetime:
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    with Session(engine) as session:
        reuters = Source(name="Reuters", type="rss", endpoint="https://example.com/reuters")
        ap = Source(name="AP", type="rss", endpoint="https://example.com/ap")
        session.add_all([reuters, ap])
        session.flush()

        items = [
            Item(
                source_id=reuters.id,
                fetched_at=now - timedelta(hours=2),
                published_at=now - timedelta(hours=2),
                url="https://example.com/reuters-1",
                title="Markets Rally",
                lang="en",
                dedupe_hash="r1",
            ),
            Item(
                source_id=reuters.id,
                fetched_at=now - timedelta(minutes=25),
                published_at=now - timedelta(minutes=30),
                url="https://example.com/reuters-2",
                title="Breaking Story",
                lang="en",
                dedupe_hash="r2",
            ),
            Item(
                source_id=ap.id,
                fetched_at=now - timedelta(minutes=10),
                published_at=now - timedelta(minutes=15),
                url="https://example.com/ap-1",
                title="Local Update",
                lang="de",
                dedupe_hash="ap1",
            ),
        ]
        session.add_all(items)
        session.flush()

        session.add_all(
            [
                Gematria(item_id=items[0].id, scheme="simple", value=74),
                Gematria(item_id=items[1].id, scheme="simple", value=144),
                Gematria(item_id=items[2].id, scheme="simple", value=88),
            ]
        )
        session.commit()
    engine.dispose()
    return now


def test_items_endpoint_returns_filtered_items(monkeypatch, tmp_path):
    db_path = tmp_path / "items.db"
    url = f"sqlite:///{db_path}"
    now = _seed(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/items?source=Reuters&size=10")
    assert response.status_code == 200
    data = response.get_json()
    assert data["meta"]["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["source"] == "Reuters"
    assert data["items"][0]["gematria"]["simple"] in {74, 144}

    search_response = client.get("/api/items?query=Breaking")
    assert search_response.status_code == 200
    search_data = search_response.get_json()
    assert len(search_data["items"]) == 1
    assert search_data["items"][0]["title"] == "Breaking Story"

    gematria_response = client.get("/api/items?scheme=simple&value=74")
    assert gematria_response.status_code == 200
    gematria_data = gematria_response.get_json()
    assert len(gematria_data["items"]) == 1
    assert gematria_data["items"][0]["title"] == "Markets Rally"

    since = (now - timedelta(minutes=30)).isoformat()
    window_response = client.get(f"/api/items?from={since}")
    assert window_response.status_code == 200
    window_data = window_response.get_json()
    assert len(window_data["items"]) == 2
    assert all(item["fetched_at"] >= since for item in window_data["items"])


def test_items_endpoint_rejects_invalid_parameters(monkeypatch, tmp_path):
    db_path = tmp_path / "items-invalid.db"
    url = f"sqlite:///{db_path}"
    _seed(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    invalid = client.get("/api/items?from=not-a-date")
    assert invalid.status_code == 400
    assert "error" in invalid.get_json()

    invalid_value = client.get("/api/items?value=abc")
    assert invalid_value.status_code == 400
    assert "error" in invalid_value.get_json()
