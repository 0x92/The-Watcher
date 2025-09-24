
"""Scheduler-backed tasks for ingesting sources, deriving metrics and discovering patterns."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import CrawlerRun, Gematria, Item, Pattern, Source
from app.services.alerts import evaluate_alerts as evaluate_alerts_service
from app.services.gematria import compute_all, normalize
from app.services.ingest import FeedFetchResult, fetch
from app.services.nlp import cluster_embeddings, embed_items
from app.services.settings import get_gematria_settings, get_worker_settings
from app.services.worker_state import ingestion_tracker

LOGGER = logging.getLogger(__name__)


# --- Session utilities -----------------------------------------------------


def _session_from_env() -> Session:
    """Create a SQLAlchemy session based on the DATABASE_URL env var."""

    database_url = os.getenv("DATABASE_URL")
    return get_session(database_url)


def _derive_source_name(url: str, fallback: str | None = None) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.split(':', 1)[0] if parsed.netloc else ""
    if host:
        return host
    if parsed.path:
        trimmed = parsed.path.strip('/')
        if trimmed:
            return trimmed.split('/')[0]
    return fallback or url


# --- Core logic ------------------------------------------------------------


def compute_gematria_for_item(
    item_id: int, *, session: Session | None = None
) -> Dict[str, int]:
    """Compute gematria for the given item and persist configured schemes."""
    close = False
    if session is None:
        session = _session_from_env()
        close = True

    item = session.get(Item, item_id)
    if item is None or not item.title:
        if close:
            session.close()
        return {}

    gematria_settings = get_gematria_settings(session)
    enabled_schemes = gematria_settings.get("enabled_schemes", [])
    if enabled_schemes:
        enabled_schemes = list(dict.fromkeys(enabled_schemes))
    ignore_pattern = gematria_settings.get("ignore_pattern", r"[^A-Z]")
    values = compute_all(item.title, enabled_schemes, ignore_pattern=ignore_pattern)
    normalized = normalize(item.title, ignore_pattern=ignore_pattern)
    token_count = len(item.title.split())

    existing = {
        row.scheme: row
        for row in session.query(Gematria).filter(Gematria.item_id == item.id).all()
    }

    computed: Dict[str, int] = {}
    for scheme in enabled_schemes:
        value = values.get(scheme, 0)
        computed[scheme] = value
        if scheme in existing:
            entry = existing[scheme]
            entry.value = value
            entry.token_count = token_count
            entry.normalized_title = normalized
        else:
            session.add(
                Gematria(
                    item_id=item.id,
                    scheme=scheme,
                    value=value,
                    token_count=token_count,
                    normalized_title=normalized,
                )
            )

    for scheme, row in existing.items():
        if scheme not in enabled_schemes:
            session.delete(row)

    session.commit()
    if close:
        session.close()
    return computed


def _apply_discovered_feeds(
    session: Session, source: Source, result: FeedFetchResult, *, source_name: str
) -> None:
    created = 0
    for feed_url in result.discovered_feeds:
        if not feed_url or feed_url == source.endpoint:
            continue
        exists = session.query(Source).filter_by(endpoint=feed_url).first()
        if exists:
            continue
        discovered = Source(
            name=_derive_source_name(feed_url, fallback=f"{source_name} feed"),
            type="rss",
            endpoint=feed_url,
            enabled=False,
            interval_sec=source.interval_sec,
            auto_discovered=True,
            discovered_at=datetime.utcnow(),
        )
        session.add(discovered)
        created += 1
    if created:
        LOGGER.info("Discovered %s candidate feeds from %s", created, source.endpoint)


def run_source(source_id: int, *, session: Session | None = None) -> int:
    """Fetch a source's feed, store new items and update crawler telemetry."""
    close = False
    if session is None:
        session = _session_from_env()
        close = True

    settings = get_worker_settings(session)
    if not settings.get("scrape_enabled", True):
        if close:
            session.close()
        return 0

    source = session.get(Source, source_id)
    if source is None:
        if close:
            session.close()
        return 0

    source_name = source.name or _derive_source_name(source.endpoint)
    endpoint = source.endpoint
    tracker_started_at = datetime.now(timezone.utc)
    job_id = ingestion_tracker.job_started(source_id=source.id, name=source_name, endpoint=endpoint)
    started_at = datetime.utcnow()
    start_perf = time.perf_counter()
    status = "running"
    error_text: Optional[str] = None
    new_count = 0
    duration_ms: Optional[int] = None

    try:
        result = fetch(endpoint)
        ingestion_tracker.job_progress(job_id, items_fetched=len(result.entries))

        for entry in result.entries:
            exists = session.query(Item).filter_by(dedupe_hash=entry.dedupe_hash).first()
            if exists:
                continue
            item = Item(
                source_id=source.id,
                url=entry.url,
                title=entry.title,
                published_at=entry.published_at,
                dedupe_hash=entry.dedupe_hash,
            )
            session.add(item)
            session.flush()
            compute_gematria_for_item(item.id, session=session)
            new_count += 1
            ingestion_tracker.job_progress(job_id, items_fetched=new_count)

        _apply_discovered_feeds(session, source, result, source_name=source_name)

        now = datetime.utcnow()
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        if new_count:
            status = "ok"
        elif result.entries:
            status = "unchanged"
        else:
            status = "empty"

        source.last_run_at = now
        source.last_checked_at = now
        source.last_status = status
        source.last_error = None
        source.last_duration_ms = duration_ms
        source.last_item_count = new_count
        source.consecutive_failures = 0

        session.add(
            CrawlerRun(
                source_id=source.id,
                started_at=started_at,
                finished_at=now,
                status=status,
                items_fetched=new_count,
                duration_ms=duration_ms,
                error=None,
            )
        )
        session.commit()
        return new_count
    except Exception as exc:  # pragma: no cover - defensive logging
        session.rollback()
        status = "error"
        error_text = str(exc)
        LOGGER.exception("Ingestion failed for %s", endpoint)
        try:
            failing_source = session.get(Source, source_id)
            if failing_source is not None:
                now = datetime.utcnow()
                failing_source.last_checked_at = now
                failing_source.last_status = status
                failing_source.last_error = error_text[:500]
                failing_source.consecutive_failures = (failing_source.consecutive_failures or 0) + 1
                session.add(
                    CrawlerRun(
                        source_id=failing_source.id,
                        started_at=started_at,
                        finished_at=now,
                        status=status,
                        items_fetched=0,
                        duration_ms=None,
                        error=error_text[:1000],
                    )
                )
                session.commit()
        except Exception:  # pragma: no cover - defensive fallback
            session.rollback()
        return 0
    finally:
        duration = int((time.perf_counter() - start_perf) * 1000) if duration_ms is None else duration_ms
        ingestion_tracker.job_finished(
            job_id,
            source_id=source_id,
            name=source_name,
            endpoint=endpoint,
            started_at=tracker_started_at,
            status=status,
            items_fetched=new_count,
            duration_ms=duration,
            error=error_text,
        )
        if close:
            session.close()


def run_due_sources(*, session: Session | None = None) -> int:
    """Execute scraping for sources that are due based on worker settings."""

    close = False
    if session is None:
        session = _session_from_env()
        close = True

    settings = get_worker_settings(session)
    if not settings.get("scrape_enabled", True):
        if close:
            session.close()
        return 0

    now = datetime.utcnow()
    limit = settings.get("max_sources_per_cycle", 0) or 0
    processed = 0

    stmt = select(Source).where(Source.enabled.is_(True)).order_by(Source.last_run_at.asc())
    for source in session.scalars(stmt):
        if limit and processed >= limit:
            break
        interval = source.interval_sec or 0
        if interval and source.last_run_at:
            if source.last_run_at + timedelta(seconds=interval) > now:
                continue
        created = run_source(source.id, session=session)
        processed += 1
        if created:
            LOGGER.debug("Source %s produced %s new items", source.id, created)

    if close:
        session.close()
    return processed


def index_item_to_opensearch(item_id: int) -> int:  # pragma: no cover - placeholder
    """Placeholder for indexing logic."""
    return item_id


def evaluate_alerts(*, session: Session | None = None) -> int:
    """Evaluate alerts using the alert service."""
    close = False
    if session is None:
        session = _session_from_env()
        close = True
    result = evaluate_alerts_service(session)
    if close:
        session.close()
    return result


def discover_patterns(
    *,
    session: Session | None = None,
    hours: int = 24,
    max_items: int = 200,
    min_cluster_size: int = 2,
    max_clusters: int = 5,
    max_patterns: int = 10,
) -> int:
    """Embed recent items, cluster them and persist discovered patterns."""
    close = False
    if session is None:
        session = _session_from_env()
        close = True

    since = datetime.utcnow() - timedelta(hours=hours)
    stmt = (
        select(Item)
        .where(Item.fetched_at >= since)
        .order_by(Item.fetched_at.desc())
        .limit(max_items)
    )
    items = session.scalars(stmt).all()
    if not items:
        if close:
            session.close()
        return 0

    embedded = embed_items(items)
    candidates = cluster_embeddings(
        embedded,
        min_cluster_size=min_cluster_size,
        max_clusters=max_clusters,
    )
    if not candidates:
        if close:
            session.close()
        return 0

    session.query(Pattern).filter(Pattern.created_at < since).delete(synchronize_session=False)

    inserted = 0
    for candidate in candidates[:max_patterns]:
        existing = (
            session.query(Pattern)
            .filter(Pattern.label == candidate.label)
            .order_by(Pattern.created_at.desc())
            .first()
        )
        if existing and set(existing.item_ids or []) == set(candidate.item_ids):
            continue
        pattern = Pattern(
            label=candidate.label,
            top_terms=candidate.top_terms,
            anomaly_score=candidate.anomaly_score,
            item_ids=candidate.item_ids,
            meta=candidate.meta,
        )
        session.add(pattern)
        inserted += 1

    if inserted:
        session.commit()
    else:
        session.rollback()

    if close:
        session.close()
    return inserted


__all__ = [
    "run_source",
    "run_due_sources",
    "compute_gematria_for_item",
    "index_item_to_opensearch",
    "evaluate_alerts",
    "discover_patterns",
]
