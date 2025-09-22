"""RSS/Atom ingestion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Optional, Tuple
from xml.etree import ElementTree
import hashlib

import feedparser


@dataclass
class FeedEntry:
    title: str
    url: str
    published_at: Optional[datetime]
    dedupe_hash: str


def _parse_timestamp(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _fallback_entries(url: str) -> List[FeedEntry]:
    path = Path(url)
    if not path.exists():
        return []
    try:
        text = path.read_text()
    except OSError:
        return []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []

    entries: List[FeedEntry] = []

    def _collect(nodes, title_tag: str = "title", link_tag: str = "link", date_tag: str = "pubDate") -> None:
        for node in nodes:
            title = (node.findtext(title_tag) or "").strip()
            link = (node.findtext(link_tag) or node.findtext("id") or "").strip()
            published_raw = node.findtext(date_tag) or node.findtext("updated")
            published_at = _parse_timestamp(published_raw)
            dedupe_hash = hashlib.sha256(f"{title}{link}".encode("utf-8")).hexdigest()
            entries.append(
                FeedEntry(
                    title=title,
                    url=link,
                    published_at=published_at,
                    dedupe_hash=dedupe_hash,
                )
            )

    _collect(root.findall(".//item"))
    if not entries:
        _collect(root.findall(".//entry"), date_tag="updated")

    return entries


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

    if not entries:
        entries = _fallback_entries(url)

    etag_new = parsed.get("etag")
    modified_struct = parsed.get("modified_parsed")
    modified_dt = datetime(*modified_struct[:6]) if modified_struct else None
    return entries, etag_new, modified_dt


__all__ = ["FeedEntry", "fetch"]
