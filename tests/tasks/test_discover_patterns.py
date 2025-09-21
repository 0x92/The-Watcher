from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Item, Pattern, Source
from app.tasks.ingest import discover_patterns


@pytest.fixture()
def sqlite_session(tmp_path):
    db_path = tmp_path / "patterns.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _add_item(session: Session, source: Source, *, title: str, minutes_ago: int = 0) -> None:
    fetched = datetime.utcnow() - timedelta(minutes=minutes_ago)
    session.add(
        Item(
            source_id=source.id,
            fetched_at=fetched,
            published_at=fetched,
            url=f"https://example.com/{title.replace(' ', '-')}-{minutes_ago}",
            title=title,
            dedupe_hash=f"{title.lower().replace(' ', '-')}-{minutes_ago}",
        )
    )


def test_discover_patterns_creates_entries(sqlite_session: Session):
    source = Source(name="rss", type="rss", endpoint="https://example.com/feed")
    sqlite_session.add(source)
    sqlite_session.flush()

    _add_item(sqlite_session, source, title="Cyber attack hits banks", minutes_ago=5)
    _add_item(sqlite_session, source, title="Cyber breach exposes data", minutes_ago=4)
    _add_item(sqlite_session, source, title="Elections debate draws crowd", minutes_ago=3)
    sqlite_session.commit()

    created = discover_patterns(
        session=sqlite_session,
        hours=12,
        min_cluster_size=2,
        max_clusters=3,
        max_patterns=5,
    )

    assert created >= 1
    patterns = sqlite_session.query(Pattern).all()
    assert patterns
    assert any("cyber" in (pattern.top_terms or []) for pattern in patterns)


def test_discover_patterns_task_reads_from_env(tmp_path, monkeypatch):
    db_path = tmp_path / "patterns-task.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        source = Source(name="rss", type="rss", endpoint="https://example.com/feed2")
        session.add(source)
        session.flush()
        _add_item(session, source, title="Market rally surprises analysts", minutes_ago=10)
        _add_item(session, source, title="Market turbulence triggers alerts", minutes_ago=9)
        session.commit()

    engine.dispose()

    monkeypatch.setenv("DATABASE_URL", url)

    inserted = discover_patterns(
        hours=24,
        max_items=500,
        min_cluster_size=2,
        max_clusters=2,
        max_patterns=3,
    )
    assert inserted >= 1

    engine = create_engine(url)
    with Session(engine) as session:
        patterns = session.query(Pattern).all()
        assert patterns
    engine.dispose()
