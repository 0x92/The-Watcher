"""RSS/Atom ingestion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple
import hashlib
from xml.etree import ElementTree

import feedparser


@dataclass
class FeedEntry:
    title: str
    url: str
    published_at: Optional[datetime]
    dedupe_hash: str


def _fallback_parse(url: str) -> List[FeedEntry]:
    """Parse RSS items using ElementTree as a fallback when feedparser is unavailable."""

    try:
        tree = ElementTree.parse(url)
    except (ElementTree.ParseError, FileNotFoundError, OSError):
        return []

    root = tree.getroot()
    items: List[FeedEntry] = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        link = item.findtext("link") or item.findtext("guid") or ""
        published_text = item.findtext("pubDate") or item.findtext("updated")
        published_at: Optional[datetime] = None
        if published_text:
            try:
                parsed = parsedate_to_datetime(published_text)
                published_at = parsed.replace(tzinfo=None)
            except (TypeError, ValueError):
                published_at = None
        dedupe_hash = hashlib.sha256(f"{title}{link}".encode("utf-8")).hexdigest()
        items.append(
            FeedEntry(
                title=title,
                url=link,
                published_at=published_at,
                dedupe_hash=dedupe_hash,
            )
        )
    return items


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
    raw_entries = getattr(parsed, "entries", None) or []
    entries: List[FeedEntry] = []

    if raw_entries:
        for entry in raw_entries:
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
        etag_new = getattr(parsed, "get", lambda *_a, **_k: None)("etag")
        modified_struct = getattr(parsed, "get", lambda *_a, **_k: None)("modified_parsed")
        modified_dt = datetime(*modified_struct[:6]) if modified_struct else None
        return entries, etag_new, modified_dt

    # Fallback parser for environments where feedparser returns no data (e.g. during tests)
    fallback_entries = _fallback_parse(url)
    return fallback_entries, None, None


__all__ = ["FeedEntry", "fetch"]
