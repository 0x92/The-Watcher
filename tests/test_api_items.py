from datetime import datetime, timedelta

from dateutil import parser as date_parser
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.blueprints.api.items import ItemsResponse
from app.models import Base, Gematria, Item, ItemTag, Source, Tag


def _seed_items(db_url: str) -> None:
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    with Session(engine) as session:
        reuters = Source(name="Reuters", type="rss", endpoint="https://example.com/reuters")
        ap = Source(name="AP", type="rss", endpoint="https://example.com/ap")
        session.add_all([reuters, ap])
        session.flush()

        climate = Tag(label="Klima")
        session.add(climate)
        session.flush()

        first = Item(
            source_id=reuters.id,
            fetched_at=now - timedelta(minutes=20),
            published_at=now - timedelta(minutes=25),
            url="https://example.com/reuters-1",
            title="Reuters Headline",
            author="Alice",
            lang="en",
            dedupe_hash="r1",
        )
        second = Item(
            source_id=ap.id,
            fetched_at=now - timedelta(minutes=10),
            published_at=now - timedelta(minutes=12),
            url="https://example.com/ap-1",
            title="AP Markets",
            author="Bob",
            lang="en",
            dedupe_hash="ap1",
        )
        third = Item(
            source_id=reuters.id,
            fetched_at=now - timedelta(minutes=5),
            published_at=now - timedelta(minutes=6),
            url="https://example.com/reuters-2",
            title="Breaking: Energy",
            author="Cara",
            lang="de",
            dedupe_hash="r2",
        )

        session.add_all([first, second, third])
        session.flush()

        session.add_all(
            [
                Gematria(item_id=first.id, scheme="ordinal", value=123),
                Gematria(item_id=second.id, scheme="ordinal", value=222),
                Gematria(item_id=third.id, scheme="ordinal", value=111),
            ]
        )

        session.add(ItemTag(item_id=first.id, tag_id=climate.id, weight=0.8))
        session.commit()
    engine.dispose()


def test_items_endpoint_returns_latest_items(monkeypatch, tmp_path):
    db_path = tmp_path / "items.db"
    url = f"sqlite:///{db_path}"
    _seed_items(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/items?limit=2")
    assert response.status_code == 200
    payload = response.get_json()
    ItemsResponse(**payload)

    items = payload["items"]
    assert len(items) == 2
    # Items sorted by fetched_at descending
    assert items[0]["url"] == "https://example.com/reuters-2"
    assert items[1]["url"] == "https://example.com/ap-1"
    assert items[0]["gematria"]["ordinal"] == 111
    assert payload["meta"]["count"] == 2
    assert "latest_fetched_at" in payload["meta"]


def test_items_endpoint_filters(monkeypatch, tmp_path):
    db_path = tmp_path / "items-filter.db"
    url = f"sqlite:///{db_path}"
    _seed_items(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/items?sources=Reuters")
    assert response.status_code == 200
    payload = response.get_json()
    ItemsResponse(**payload)
    assert all(item["source"] == "Reuters" for item in payload["items"])

    since = payload["items"][0]["fetched_at"]
    response_since = client.get(f"/api/items?since={since}")
    assert response_since.status_code == 200
    payload_since = response_since.get_json()
    ItemsResponse(**payload_since)
    since_dt = date_parser.isoparse(since)
    assert all(date_parser.isoparse(item["fetched_at"]) >= since_dt for item in payload_since["items"])


def test_items_endpoint_invalid_since(monkeypatch, tmp_path):
    db_path = tmp_path / "items-invalid.db"
    url = f"sqlite:///{db_path}"
    _seed_items(url)
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/items?since=not-a-date")
    assert response.status_code == 400
    payload = response.get_json()
    assert "error" in payload
