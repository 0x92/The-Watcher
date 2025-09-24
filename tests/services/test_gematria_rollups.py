from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Gematria, Item, Source
from app.services.analytics.gematria_rollups import (
    DEFAULT_WINDOWS,
    compute_rollup,
    get_rollup,
    refresh_rollups,
)


NOW = datetime(2025, 9, 24, 12, 0, 0)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session) -> None:
    source_a = Source(name="Reuters", type="rss", endpoint="https://a.example/rss", priority=5)
    source_b = Source(name="AP", type="rss", endpoint="https://b.example/rss", priority=2)
    session.add_all([source_a, source_b])
    session.flush()

    item_a = Item(
        source_id=source_a.id,
        fetched_at=NOW - timedelta(hours=2),
        published_at=NOW - timedelta(hours=2),
        url="https://a.example/1",
        title="World leaders meet",
    )
    item_b = Item(
        source_id=source_a.id,
        fetched_at=NOW - timedelta(hours=8),
        published_at=NOW - timedelta(hours=8),
        url="https://a.example/2",
        title="Markets rally",
    )
    item_c = Item(
        source_id=source_b.id,
        fetched_at=NOW - timedelta(hours=20),
        published_at=NOW - timedelta(hours=20),
        url="https://b.example/1",
        title="Elections ahead",
    )
    session.add_all([item_a, item_b, item_c])
    session.flush()

    session.add_all(
        [
            Gematria(item_id=item_a.id, scheme="simple", value=93),
            Gematria(item_id=item_b.id, scheme="simple", value=74),
            Gematria(item_id=item_c.id, scheme="simple", value=93),
        ]
    )
    session.commit()


def test_compute_rollup_summary_values():
    session = _session()
    _seed(session)

    payload = compute_rollup(session, "simple", 24, now=NOW)

    summary = payload["summary"]
    assert summary["total_items"] == 3
    assert summary["unique_sources"] == 2
    assert summary["min"] == 74
    assert summary["max"] == 93
    assert summary["percentiles"]["p50"] == 93.0
    assert payload["top_values"][0]["value"] == 93
    assert payload["source_breakdown"][0]["name"] == "Reuters"
    session.close()


def test_get_rollup_caches_and_refreshes():
    session = _session()
    _seed(session)

    first = get_rollup(session, scheme="simple", window_hours=24, now=NOW)
    assert first["summary"]["total_items"] == 3

    # Insert new item but ensure cached result remains until refresh requested
    session.add(
        Item(
            source_id=1,
            fetched_at=NOW - timedelta(hours=1),
            published_at=NOW - timedelta(hours=1),
            url="https://a.example/3",
            title="Energy update",
        )
    )
    session.flush()
    session.add(Gematria(item_id=4, scheme="simple", value=120))
    session.commit()

    cached = get_rollup(session, scheme="simple", window_hours=24, now=NOW + timedelta(minutes=5))
    assert cached["summary"]["total_items"] == 3

    refreshed = get_rollup(
        session,
        scheme="simple",
        window_hours=24,
        now=NOW + timedelta(minutes=5),
        refresh=True,
    )
    assert refreshed["summary"]["total_items"] == 4
    session.close()


def test_refresh_rollups_creates_records():
    session = _session()
    _seed(session)

    results = refresh_rollups(
        session,
        schemes=["simple"],
        window_hours=[24],
        source_ids=[None],
        now=NOW,
        commit=True,
    )
    assert len(results) == 1
    payload = results[0].payload
    assert payload["summary"]["total_items"] == 3
    assert DEFAULT_WINDOWS[0] == 24
    session.close()


