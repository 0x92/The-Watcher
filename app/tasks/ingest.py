"""Celery tasks for ingesting sources, deriving metrics and discovering patterns."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from celery_app import celery
from app.models import Gematria, Item, Pattern, Source
from app.services.alerts import evaluate_alerts as evaluate_alerts_service
from app.services.gematria import compute_all, normalize
from app.services.ingest import fetch
from app.services.nlp import cluster_embeddings, embed_items


# --- Session utilities -----------------------------------------------------


def _session_from_env() -> Session:
    """Create a SQLAlchemy session based on the DATABASE_URL env var."""
    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///:memory:"))
    return Session(engine)


# --- Core logic ------------------------------------------------------------


def compute_gematria_for_item(
    item_id: int, *, session: Session | None = None
) -> Dict[str, int]:
    """Compute gematria for the given item and persist a single scheme."""
    close = False
    if session is None:
        session = _session_from_env()
        close = True

    item = session.get(Item, item_id)
    if item is None or not item.title:
        if close:
            session.close()
        return {}

    values = compute_all(item.title)
    scheme = "ordinal"
    value = values[scheme]
    normalized = normalize(item.title)
    token_count = len(item.title.split())
    gem = Gematria(
        item_id=item.id,
        scheme=scheme,
        value=value,
        token_count=token_count,
        normalized_title=normalized,
    )
    session.merge(gem)
    session.commit()
    if close:
        session.close()
    return {scheme: value}


def run_source(source_id: int, *, session: Session | None = None) -> int:
    """Fetch a source's feed and store new items."""
    close = False
    if session is None:
        session = _session_from_env()
        close = True

    source = session.get(Source, source_id)
    if source is None:
        if close:
            session.close()
        return 0

    entries, _, _ = fetch(source.endpoint)
    new_count = 0
    for entry in entries:
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

    source.last_run_at = datetime.utcnow()
    session.commit()
    if close:
        session.close()
    return new_count


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


# --- Celery task wrappers --------------------------------------------------


@celery.task(name="run_source")
def run_source_task(source_id: int) -> int:
    return run_source(source_id)


@celery.task(name="compute_gematria_for_item")
def compute_gematria_for_item_task(item_id: int) -> Dict[str, int]:
    return compute_gematria_for_item(item_id)


@celery.task(name="index_item_to_opensearch")
def index_item_to_opensearch_task(item_id: int) -> int:
    return index_item_to_opensearch(item_id)


@celery.task(name="evaluate_alerts")
def evaluate_alerts_task() -> int:
    return evaluate_alerts()


@celery.task(name="discover_patterns")
def discover_patterns_task(
    hours: int = 24,
    max_items: int = 200,
    min_cluster_size: int = 2,
    max_clusters: int = 5,
    max_patterns: int = 10,
) -> int:
    return discover_patterns(
        hours=hours,
        max_items=max_items,
        min_cluster_size=min_cluster_size,
        max_clusters=max_clusters,
        max_patterns=max_patterns,
    )


__all__ = [
    "run_source",
    "compute_gematria_for_item",
    "index_item_to_opensearch",
    "evaluate_alerts",
    "discover_patterns",
    "run_source_task",
    "compute_gematria_for_item_task",
    "index_item_to_opensearch_task",
    "evaluate_alerts_task",
    "discover_patterns_task",
]
