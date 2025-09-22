from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Source, Item, Gematria, Setting
from app.services.gematria import DEFAULT_ENABLED_SCHEMES
from app.services.ingest import fetch
from app.services.ingest import rss as rss_module
from app.tasks import ingest as ingest_tasks
from app.tasks.ingest import run_source, run_due_sources


def _setup_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _write_feed(tmp_path: Path) -> Path:
    content = """<?xml version='1.0'?>
    <rss version='2.0'>
      <channel>
        <title>Example</title>
        <item>
          <title>Hello World</title>
          <link>http://example.com/hello</link>
          <pubDate>Mon, 10 Feb 2025 10:00:00 GMT</pubDate>
        </item>
        <item>
          <title>Another</title>
          <link>http://example.com/another</link>
          <pubDate>Tue, 11 Feb 2025 10:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>"""
    feed_file = tmp_path / "feed.xml"
    feed_file.write_text(content)
    return feed_file


def test_run_source_creates_items_and_gematria(tmp_path):
    session = _setup_session()
    feed_file = _write_feed(tmp_path)
    source = Source(name="rss", type="rss", endpoint=str(feed_file))
    session.add(source)
    session.commit()

    created = run_source(source_id=source.id, session=session)
    assert created == 2
    assert session.query(Item).count() == 2
    expected_per_item = len(DEFAULT_ENABLED_SCHEMES)
    items = session.query(Item).all()
    assert session.query(Gematria).count() == len(items) * expected_per_item
    values = {
        (row.item_id, row.scheme): row.value
        for row in session.query(Gematria).order_by(Gematria.item_id, Gematria.scheme)
    }
    assert all((item.id, scheme) in values for scheme in DEFAULT_ENABLED_SCHEMES for item in items)

    # running again should not create duplicates
    created_again = run_source(source_id=source.id, session=session)
    assert created_again == 0
    assert session.query(Item).count() == len(items)
    assert session.query(Gematria).count() == len(items) * expected_per_item


def test_run_source_respects_worker_settings(tmp_path):
    session = _setup_session()
    feed_file = _write_feed(tmp_path)
    source = Source(name="rss", type="rss", endpoint=str(feed_file))
    session.add_all([
        source,
        Setting(key="worker.scrape", value_json={"scrape_enabled": False}),
    ])
    session.commit()

    created = run_source(source_id=source.id, session=session)
    assert created == 0
    assert session.query(Item).count() == 0


def test_run_due_sources_respects_limits(tmp_path):
    session = _setup_session()
    feed_a = _write_feed(tmp_path)
    feed_b = _write_feed(tmp_path)
    source_a = Source(name="rss-a", type="rss", endpoint=str(feed_a))
    source_b = Source(name="rss-b", type="rss", endpoint=str(feed_b))
    session.add_all([
        source_a,
        source_b,
        Setting(
            key="worker.scrape",
            value_json={"scrape_enabled": True, "max_sources_per_cycle": 1},
        ),
    ])
    session.commit()

    processed = run_due_sources(session=session)
    assert processed == 1
    # Only one source should have executed so we expect exactly one last_run_at value
    executed = session.query(Source).filter(Source.last_run_at.isnot(None)).count()
    assert executed == 1


def test_fetch_uses_sample_feed_when_http_fails(monkeypatch):
    original_parse = rss_module.feedparser.parse

    class Dummy(dict):
        def __init__(self):
            super().__init__()
            self.entries: list[dict] = []

        def get(self, key, default=None):
            return super().get(key, default)

    def fake_parse(url, *args, **kwargs):
        if isinstance(url, (bytes, bytearray)):
            return original_parse(url, *args, **kwargs)
        if url == "https://example.com/fail":
            dummy = Dummy()
            dummy["entries"] = []
            dummy["status"] = 503
            return dummy
        return original_parse(url, *args, **kwargs)

    monkeypatch.setattr(rss_module.feedparser, "parse", fake_parse)
    monkeypatch.setattr(rss_module, "_fetch_with_requests", lambda *_, **__: ([], None, None))

    sample_entries = [
        rss_module.FeedEntry(
            title="Fallback", url="https://example.com/fallback", published_at=None, dedupe_hash="abc"
        )
    ]
    monkeypatch.setattr(rss_module, "_load_sample_entries", lambda *_: sample_entries)

    entries, etag, modified = fetch("https://example.com/fail")
    assert entries == sample_entries  # bundled sample feed should provide fallback items
    assert etag is None
    assert modified is None


def test_session_from_env_respects_database_url(monkeypatch, tmp_path):
    custom_url = f"sqlite:///{tmp_path}/worker.db"
    monkeypatch.setenv("DATABASE_URL", custom_url)

    session = ingest_tasks._session_from_env()
    try:
        assert str(session.get_bind().url) == custom_url
    finally:
        session.close()


def test_session_from_env_uses_shared_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    session = ingest_tasks._session_from_env()
    try:
        assert str(session.get_bind().url) == "sqlite:///app.db"
    finally:
        session.close()
