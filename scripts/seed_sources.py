"""Seed example sources and an alert into the database."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

try:  # pragma: no cover - defensive import setup
    from app.models import Alert, Base, Source
except ModuleNotFoundError:  # pragma: no cover - ensure repo root on path
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from app.models import Alert, Base, Source


def _session_from_env() -> Session:
    """Create a session using the ``DATABASE_URL`` environment variable."""

    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///app.db"))
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_demo_data(session: Session) -> None:
    """Insert demo sources and a sample alert if they don't exist."""

    sources = [
        Source(
            name="Reuters",
            type="rss",
            endpoint="https://feeds.reuters.com/reuters/topNews",
            interval_sec=300,
        ),
        Source(
            name="Associated Press",
            type="rss",
            endpoint="https://apnews.com/apf-topnews?format=rss",
            interval_sec=300,
        ),
        Source(
            name="Mastodon #news",
            type="mastodon",
            endpoint="https://mastodon.social/tags/news.rss",
            interval_sec=300,
        ),
        Source(
            name="YouTube Channel",
            type="youtube",
            endpoint="https://www.youtube.com/feeds/videos.xml?channel_id=UC_x5XG1OV2P6uZZ5FSM9Ttw",
            interval_sec=300,
        ),
    ]

    for src in sources:
        exists = session.query(Source).filter_by(endpoint=src.endpoint).first()
        if not exists:
            session.add(src)

    alert_rule = """
when:
  all:
    - scheme: ordinal
      value_in: [93]
    - source_in: ["Reuters"]
    - window: { period: "24h", min_count: 1 }
"""
    alert = session.query(Alert).filter_by(name="reuters_93").first()
    if alert is None:
        session.add(Alert(name="reuters_93", rule_yaml=alert_rule))

    session.commit()


def main(*, session: Session | None = None) -> None:
    close = False
    if session is None:
        session = _session_from_env()
        close = True

    seed_demo_data(session)

    if close:
        session.close()


if __name__ == "__main__":
    main()
