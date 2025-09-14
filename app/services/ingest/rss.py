"""RSS/Atom ingestion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple
import hashlib

import feedparser


@dataclass
class FeedEntry:
    title: str
    url: str
    published_at: Optional[datetime]
    dedupe_hash: str


def fetch(
    url: str,
    *,
    etag: str | None = None,
    modified: datetime | None = None,
) -> Tuple[List[FeedEntry], str | None, datetime | None]:
    """Fetch and parse ``url`` returning normalized entries.

    Parameters
    ----------
    url:
        URL or path to the RSS/Atom feed.
    etag, modified:
        Optional caching headers forwarded to ``feedparser``.

    Returns
    -------
    entries, etag, modified
        Parsed entries and potential caching headers for subsequent calls.
    """
    parsed = feedparser.parse(
        url,
        etag=etag,
        modified=modified.timetuple() if modified else None,
    )
    entries: List[FeedEntry] = []
    for entry in parsed.entries:
        title = entry.get("title", "")
        link = entry.get("link") or entry.get("id") or ""
        published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = datetime(*published_struct[:6]) if published_struct else None
        dedupe_hash = hashlib.sha256(f"{title}{link}".encode("utf-8")).hexdigest()
        entries.append(
            FeedEntry(
                title=title,
                url=link,
                published_at=published_at,
                dedupe_hash=dedupe_hash,
            )
        )

    etag_new = parsed.get("etag")
    modified_struct = parsed.get("modified_parsed")
    modified_dt = datetime(*modified_struct[:6]) if modified_struct else None
    return entries, etag_new, modified_dt


__all__ = ["FeedEntry", "fetch"]
