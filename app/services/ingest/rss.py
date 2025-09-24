"""RSS/Atom ingestion helpers."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse
from xml.etree import ElementTree

import feedparser
import requests

LOGGER = logging.getLogger(__name__)

_SAMPLE_FEED = Path(__file__).with_name("samples").joinpath("sample_feed.xml")
_USER_AGENT = "TheWatcherBot/1.0 (+https://github.com/The-Watcher)"


@dataclass
class FeedEntry:
    title: str
    url: str
    published_at: Optional[datetime]
    dedupe_hash: str


@dataclass
class FeedFetchResult:
    entries: List[FeedEntry]
    etag: str | None = None
    modified: datetime | None = None
    discovered_feeds: List[str] = field(default_factory=list)

    def __iter__(self):
        yield self.entries
        yield self.etag
        yield self.modified


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


def _struct_time_to_datetime(value) -> Optional[datetime]:
    """Convert a struct_time or tuple to a naive ``datetime`` instance."""

    if value is None:
        return None
    try:
        return datetime(*value[:6])
    except Exception:  # pragma: no cover - defensive conversion
        return None


def _normalize_entries(raw_entries) -> List[FeedEntry]:
    """Normalize feedparser entries into :class:`FeedEntry` objects."""

    entries: List[FeedEntry] = []
    for entry in raw_entries or []:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title", "")
        link = entry.get("link") or entry.get("id") or ""
        published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = _struct_time_to_datetime(published_struct)
        dedupe_hash = hashlib.sha256(f"{title}{link}".encode("utf-8")).hexdigest()
        entries.append(
            FeedEntry(
                title=title,
                url=link,
                published_at=published_at,
                dedupe_hash=dedupe_hash,
            )
        )
    return entries


def _fetch_with_requests(
    url: str, *, etag: str | None, modified: datetime | None
) -> Tuple[List[FeedEntry], str | None, datetime | None]:
    """Fetch the feed via ``requests`` as a fallback for HTTP endpoints."""

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = format_datetime(modified, usegmt=True)

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as exc:  # pragma: no cover - network specific
        LOGGER.warning("HTTP fetch for %s failed: %s", url, exc)
        return FeedFetchResult(entries=[])

    if response.status_code == 304:
        return [], etag, modified

    if response.status_code >= 400:
        LOGGER.warning(
            "Feed %s returned HTTP %s – falling back to bundled sample", url, response.status_code
        )
        return FeedFetchResult(entries=[])

    parsed = feedparser.parse(response.content)
    entries = _normalize_entries(getattr(parsed, "entries", None))
    etag_new = response.headers.get("ETag")
    modified_header = response.headers.get("Last-Modified")
    modified_dt: Optional[datetime] = None
    if modified_header:
        try:
            modified_dt = parsedate_to_datetime(modified_header).replace(tzinfo=None)
        except (TypeError, ValueError):  # pragma: no cover - header parsing guard
            modified_dt = None

    return entries, etag_new, modified_dt


def _load_sample_entries(url: str) -> List[FeedEntry]:
    """Load bundled sample entries when remote endpoints cannot be reached."""

    if not _SAMPLE_FEED.exists():  # pragma: no cover - developer error guard
        return []

    try:
        parsed = feedparser.parse(_SAMPLE_FEED.read_bytes())
    except Exception as exc:  # pragma: no cover - defensive I/O handling
        LOGGER.error("Failed to read sample feed for %s: %s", url, exc)
        return []

    entries = _normalize_entries(getattr(parsed, "entries", None))
    if entries:
        LOGGER.info("Using bundled sample feed for %s", url)
    return entries


def _is_http_url(url: str) -> bool:
    scheme = urlparse(url).scheme.lower()
    return scheme in {"http", "https"}


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
    FeedFetchResult
        Structured result containing feed entries and optional cache metadata.
    """
    request_headers = {"User-Agent": _USER_AGENT, "Accept": "application/rss+xml"}
    parsed = feedparser.parse(
        url,
        etag=etag,
        modified=modified.timetuple() if modified else None,
        agent=_USER_AGENT,
        request_headers=request_headers,
    )
    entries = _normalize_entries(getattr(parsed, "entries", None))
    if entries:
        etag_new = getattr(parsed, "get", lambda *_a, **_k: None)("etag")
        modified_struct = getattr(parsed, "get", lambda *_a, **_k: None)("modified_parsed")
        modified_dt = _struct_time_to_datetime(modified_struct)
        return FeedFetchResult(entries=entries, etag=etag_new, modified=modified_dt)

    if _is_http_url(url):
        http_entries, http_etag, http_modified = _fetch_with_requests(
            url, etag=etag, modified=modified
        )
        if http_entries:
            return FeedFetchResult(entries=http_entries, etag=http_etag, modified=http_modified)

    fallback_entries = _fallback_parse(url)
    if fallback_entries:
        return FeedFetchResult(entries=fallback_entries)

    if _is_http_url(url):
        sample_entries = _load_sample_entries(url)
        if sample_entries:
            return FeedFetchResult(entries=sample_entries)

    return FeedFetchResult(entries=[])


__all__ = ["FeedEntry", "FeedFetchResult", "fetch"]
