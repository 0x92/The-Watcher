from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Source, Item, Gematria
from app.tasks.ingest import run_source


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
    assert session.query(Gematria).count() == 2

    # running again should not create duplicates
    created_again = run_source(source_id=source.id, session=session)
    assert created_again == 0
    assert session.query(Item).count() == 2
