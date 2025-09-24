from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import CrawlerRun, Item, Source


def _iso(value: Optional[datetime]) -> Optional[str]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def coerce_int(
    value: Any,
    default: int,
    *,
    minimum: int = 0,
    maximum: Optional[int] = None,
) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        integer = default
    integer = max(minimum, integer)
    if maximum is not None:
        integer = min(integer, maximum)
    return integer


def normalize_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.replace(";", ",")
        parts = [segment.strip() for segment in raw.split(",") if segment.strip()]
    elif isinstance(value, Iterable):
        parts = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                parts.append(text)
    else:
        return []
    normalized: List[str] = []
    seen = set()
    for part in parts:
        lowered = part.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(lowered)
    return normalized


def serialize_source(
    source: Source,
    stats: Optional[Dict[str, Any]] = None,
    *,
    include_runs: bool = False,
) -> Dict[str, Any]:
    stats = stats or {}
    latest = stats.get("latest_item") or {}
    recent_runs = stats.get("recent_runs", []) if include_runs else []

    payload: Dict[str, Any] = {
        "id": source.id,
        "name": source.name,
        "type": source.type,
        "endpoint": source.endpoint,
        "enabled": bool(source.enabled),
        "interval_minutes": int((source.interval_sec or 0) / 60),
        "created_at": _iso(source.created_at),
        "last_run_at": _iso(source.last_run_at),
        "priority": int(source.priority or 0),
        "tags": list(source.tags_json or []),
        "notes": source.notes or None,
        "auto_discovered": bool(source.auto_discovered),
        "discovered_at": _iso(source.discovered_at),
        "health": {
            "status": source.last_status or "unknown",
            "consecutive_failures": int(source.consecutive_failures or 0),
            "last_checked_at": _iso(source.last_checked_at),
            "last_error": source.last_error,
        },
        "stats": {
            "total_items": int(stats.get("total_items", 0) or 0),
            "last_published_at": _iso(stats.get("last_published_at")),
            "last_fetched_at": _iso(stats.get("last_fetched_at")),
            "latest_item": {
                "title": latest.get("title"),
                "url": latest.get("url"),
                "published_at": _iso(latest.get("published_at")),
                "fetched_at": _iso(latest.get("fetched_at")),
            },
        },
    }

    if include_runs:
        payload["runs"] = [
            {
                "started_at": _iso(run.get("started_at")),
                "finished_at": _iso(run.get("finished_at")),
                "status": run.get("status"),
                "items_fetched": int(run.get("items_fetched") or 0)
                if run.get("items_fetched") is not None
                else None,
                "duration_ms": int(run.get("duration_ms"))
                if run.get("duration_ms") is not None
                else None,
                "error": run.get("error"),
            }
            for run in recent_runs
        ]

    return payload


def _collect_source_stats(
    session: Session,
    sources: Sequence[Source],
    *,
    include_runs: bool = False,
    runs_limit: int = 5,
) -> Dict[int, Dict[str, Any]]:
    stats_map: Dict[int, Dict[str, Any]] = {
        source.id: {
            "total_items": 0,
            "last_published_at": None,
            "last_fetched_at": None,
        }
        for source in sources
    }

    if not sources:
        return stats_map

    source_ids = [source.id for source in sources]

    metrics_stmt = (
        select(
            Item.source_id,
            func.count(Item.id),
            func.max(Item.published_at),
            func.max(Item.fetched_at),
        )
        .where(Item.source_id.in_(source_ids))
        .group_by(Item.source_id)
    )
    for source_id, total_items, last_published, last_fetched in session.execute(metrics_stmt):
        stats = stats_map.get(source_id)
        if stats is None:
            continue
        stats["total_items"] = int(total_items or 0)
        stats["last_published_at"] = last_published
        stats["last_fetched_at"] = last_fetched

    latest_stmt = (
        select(
            Item.source_id,
            Item.title,
            Item.url,
            Item.published_at,
            Item.fetched_at,
        )
        .where(Item.source_id.in_(source_ids))
        .order_by(
            Item.source_id.asc(),
            Item.published_at.desc(),
            Item.fetched_at.desc(),
            Item.id.desc(),
        )
    )
    seen: Dict[int, bool] = {}
    for source_id, title, url, published_at, fetched_at in session.execute(latest_stmt):
        if seen.get(source_id):
            continue
        stats = stats_map.get(source_id)
        if stats is None:
            continue
        stats["latest_item"] = {
            "title": title,
            "url": url,
            "published_at": published_at,
            "fetched_at": fetched_at,
        }
        seen[source_id] = True
        if len(seen) == len(source_ids):
            break

    if include_runs:
        runs_stmt = (
            select(
                CrawlerRun.source_id,
                CrawlerRun.started_at,
                CrawlerRun.finished_at,
                CrawlerRun.status,
                CrawlerRun.items_fetched,
                CrawlerRun.duration_ms,
                CrawlerRun.error,
            )
            .where(CrawlerRun.source_id.in_(source_ids))
            .order_by(
                CrawlerRun.source_id.asc(),
                CrawlerRun.started_at.desc(),
                CrawlerRun.id.desc(),
            )
        )
        counters = {source_id: 0 for source_id in source_ids}
        for (
            source_id,
            started_at,
            finished_at,
            status,
            items_fetched,
            duration_ms,
            error,
        ) in session.execute(runs_stmt):
            if counters[source_id] >= runs_limit:
                continue
            stats = stats_map.setdefault(source_id, {})
            runs = stats.setdefault("recent_runs", [])
            runs.append(
                {
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "status": status,
                    "items_fetched": items_fetched,
                    "duration_ms": duration_ms,
                    "error": error,
                }
            )
            counters[source_id] += 1

    return stats_map


def list_sources(
    session: Session,
    *,
    search: Optional[str] = None,
    types: Sequence[str] | None = None,
    enabled: Optional[bool] = None,
    tags: Sequence[str] | None = None,
    include_runs: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    stmt = select(Source).order_by(Source.name.asc())

    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Source.name).like(pattern),
                func.lower(Source.endpoint).like(pattern),
                func.lower(Source.type).like(pattern),
            )
        )

    if types:
        stmt = stmt.where(Source.type.in_(list(types)))

    if enabled is not None:
        stmt = stmt.where(Source.enabled.is_(True if enabled else False))

    sources = session.scalars(stmt).all()

    if tags:
        normalized_tags = [tag.lower() for tag in tags if tag]
        if normalized_tags:
            filtered_sources = []
            for source in sources:
                stored_tags = [value.lower() for value in (source.tags_json or [])]
                if all(tag in stored_tags for tag in normalized_tags):
                    filtered_sources.append(source)
            sources = filtered_sources
    stats_map = _collect_source_stats(session, sources, include_runs=include_runs)
    serialized = [
        serialize_source(source, stats_map.get(source.id), include_runs=include_runs)
        for source in sources
    ]

    total_sources = len(serialized)
    active_sources = sum(1 for source in sources if source.enabled)
    degraded_sources = sum(1 for source in sources if (source.consecutive_failures or 0) > 0)
    auto_sources = sum(1 for source in sources if source.auto_discovered)

    last_run_at: Optional[datetime] = None
    for source in sources:
        if source.last_run_at and (last_run_at is None or source.last_run_at > last_run_at):
            last_run_at = source.last_run_at

    total_items = sum(stats_map.get(source.id, {}).get("total_items", 0) for source in sources)
    type_counter = Counter(source.type for source in sources)
    aggregated_tags = Counter()
    for source in sources:
        for tag in source.tags_json or []:
            aggregated_tags[tag] += 1

    filters_payload = {
        "query": search or None,
        "types": list(types) if types else [],
        "enabled": enabled,
        "tags": list(tags) if tags else [],
    }

    meta = {
        "total_sources": total_sources,
        "active_sources": active_sources,
        "inactive_sources": total_sources - active_sources,
        "degraded_sources": degraded_sources,
        "auto_discovered_sources": auto_sources,
        "total_items": int(total_items),
        "type_breakdown": dict(sorted(type_counter.items())),
        "tag_breakdown": dict(sorted(aggregated_tags.items())),
        "last_run_at": _iso(last_run_at),
        "filters_applied": bool(
            (search or "").strip()
            or (types and len(list(types)))
            or enabled is not None
            or (tags and len(list(tags)))
        ),
    }

    return serialized, meta, filters_payload


def create_source(
    session: Session,
    payload: Dict[str, Any],
    *,
    defaults: Dict[str, Any],
) -> Tuple[Optional[Source], List[str]]:
    errors: List[str] = []

    name = (payload.get("name") or "").strip()
    endpoint = (payload.get("endpoint") or "").strip()

    if not name:
        errors.append("name is required")
    if not endpoint:
        errors.append("endpoint is required")

    if errors:
        return None, errors

    source_type = (payload.get("type") or "rss").strip() or "rss"
    default_interval = int(defaults.get("default_interval_minutes", 15) or 15)
    interval_minutes = coerce_int(payload.get("interval_minutes"), default_interval, minimum=0)

    source = Source(
        name=name,
        type=source_type,
        endpoint=endpoint,
        enabled=coerce_bool(payload.get("enabled"), True),
        interval_sec=interval_minutes * 60,
        priority=coerce_int(payload.get("priority"), 0, minimum=0),
    )

    auth_payload = payload.get("auth")
    if isinstance(auth_payload, dict):
        source.auth_json = auth_payload

    filters_payload = payload.get("filters")
    if isinstance(filters_payload, dict):
        source.filters_json = filters_payload

    tags = normalize_tags(payload.get("tags"))
    if tags:
        source.tags_json = tags

    notes_value = payload.get("notes")
    if isinstance(notes_value, str):
        stripped = notes_value.strip()
        source.notes = stripped or None

    source.auto_discovered = coerce_bool(payload.get("auto_discovered"), False)

    session.add(source)
    return source, []


def update_source(
    source: Source,
    payload: Dict[str, Any],
    *,
    defaults: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            errors.append("name cannot be empty")
        else:
            source.name = name

    if "endpoint" in payload:
        endpoint = (payload.get("endpoint") or "").strip()
        if not endpoint:
            errors.append("endpoint cannot be empty")
        else:
            source.endpoint = endpoint

    if "type" in payload:
        source.type = (payload.get("type") or source.type).strip() or source.type

    if "enabled" in payload:
        source.enabled = coerce_bool(payload.get("enabled"), bool(source.enabled))

    if "interval_minutes" in payload:
        current_interval = int((source.interval_sec or 0) / 60)
        default_interval = int(defaults.get("default_interval_minutes", current_interval) or current_interval)
        interval_minutes = coerce_int(payload.get("interval_minutes"), default_interval, minimum=0)
        source.interval_sec = interval_minutes * 60

    if "priority" in payload:
        source.priority = coerce_int(payload.get("priority"), source.priority or 0, minimum=0)

    if "auth" in payload and isinstance(payload.get("auth"), dict):
        source.auth_json = payload.get("auth")

    if "filters" in payload and isinstance(payload.get("filters"), dict):
        source.filters_json = payload.get("filters")

    if "tags" in payload:
        tags = normalize_tags(payload.get("tags"))
        source.tags_json = tags or None

    if "notes" in payload:
        notes_value = payload.get("notes")
        if isinstance(notes_value, str):
            stripped = notes_value.strip()
            source.notes = stripped or None
        else:
            source.notes = None

    if "auto_discovered" in payload:
        source.auto_discovered = coerce_bool(payload.get("auto_discovered"), bool(source.auto_discovered))

    return errors


def bulk_update_sources(
    session: Session,
    source_ids: Sequence[int],
    *,
    action: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = payload or {}
    normalized_action = (action or "").strip().lower()

    if not source_ids:
        return {"processed": 0, "action": normalized_action}

    sources = session.scalars(select(Source).where(Source.id.in_(list(source_ids)))).all()
    if not sources:
        return {"processed": 0, "action": normalized_action}

    processed = 0

    if normalized_action == "enable":
        for source in sources:
            if not source.enabled:
                source.enabled = True
                processed += 1
    elif normalized_action == "disable":
        for source in sources:
            if source.enabled:
                source.enabled = False
                processed += 1
    elif normalized_action == "delete":
        for source in sources:
            session.delete(source)
            processed += 1
    elif normalized_action == "set_priority":
        priority = coerce_int(payload.get("priority"), 0, minimum=0)
        for source in sources:
            source.priority = priority
            processed += 1
    elif normalized_action == "set_tags":
        tags = normalize_tags(payload.get("tags"))
        for source in sources:
            source.tags_json = tags or None
            processed += 1
    elif normalized_action == "set_notes":
        notes_value = payload.get("notes")
        if isinstance(notes_value, str):
            stripped = notes_value.strip()
        else:
            stripped = None
        for source in sources:
            source.notes = stripped or None
            processed += 1
    else:
        raise ValueError(f"unsupported bulk action: {action}")

    session.commit()
    return {"processed": processed, "action": normalized_action}


def trigger_health_check(
    session: Session,
    source: Source,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    timestamp = now or datetime.now(timezone.utc)
    naive = timestamp.replace(tzinfo=None)
    source.last_checked_at = naive
    source.last_status = "manual_check_pending"
    source.last_error = None
    session.commit()
    return {
        "status": source.last_status,
        "last_checked_at": _iso(source.last_checked_at),
    }


def get_crawler_metrics(
    session: Session,
    *,
    window_hours: int = 24,
    recent_limit: int = 10,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)

    total_sources = session.scalar(select(func.count(Source.id))) or 0
    active_sources = session.scalar(
        select(func.count(Source.id)).where(Source.enabled.is_(True))
    ) or 0
    degraded_sources = session.scalar(
        select(func.count(Source.id)).where(func.coalesce(Source.consecutive_failures, 0) > 0)
    ) or 0
    auto_sources = session.scalar(
        select(func.count(Source.id)).where(Source.auto_discovered.is_(True))
    ) or 0
    last_run_at = session.scalar(select(func.max(Source.last_run_at)))
    avg_priority = session.scalar(select(func.avg(Source.priority)))

    tag_rows = session.scalars(select(Source.tags_json).where(Source.tags_json.isnot(None))).all()
    tag_counter: Counter[str] = Counter()
    for row in tag_rows:
        if not isinstance(row, list):
            continue
        for tag in row:
            if tag:
                tag_counter[tag] += 1

    runs_filter = [CrawlerRun.started_at >= window_start]

    total_runs = session.scalar(
        select(func.count(CrawlerRun.id)).where(and_(*runs_filter))
    ) or 0

    failed_runs = session.scalar(
        select(func.count(CrawlerRun.id)).where(
            and_(
                *runs_filter,
                or_(CrawlerRun.status == "failed", CrawlerRun.error.isnot(None)),
            )
        )
    ) or 0

    items_processed = session.scalar(
        select(func.coalesce(func.sum(CrawlerRun.items_fetched), 0)).where(and_(*runs_filter))
    ) or 0

    avg_duration_ms = session.scalar(
        select(func.avg(CrawlerRun.duration_ms)).where(
            and_(*runs_filter, CrawlerRun.duration_ms.isnot(None))
        )
    )

    recent_stmt = (
        select(
            CrawlerRun.id,
            CrawlerRun.source_id,
            Source.name.label("source_name"),
            CrawlerRun.status,
            CrawlerRun.started_at,
            CrawlerRun.finished_at,
            CrawlerRun.items_fetched,
            CrawlerRun.duration_ms,
            CrawlerRun.error,
        )
        .join(Source, Source.id == CrawlerRun.source_id)
        .order_by(CrawlerRun.started_at.desc(), CrawlerRun.id.desc())
        .limit(recent_limit)
    )

    recent_runs: List[Dict[str, Any]] = []
    for row in session.execute(recent_stmt):
        mapping = row._mapping
        recent_runs.append(
            {
                "id": mapping["id"],
                "source_id": mapping["source_id"],
                "source": mapping["source_name"],
                "status": mapping["status"],
                "started_at": _iso(mapping["started_at"]),
                "finished_at": _iso(mapping["finished_at"]),
                "items_fetched": int(mapping["items_fetched"] or 0)
                if mapping["items_fetched"] is not None
                else None,
                "duration_ms": int(mapping["duration_ms"])
                if mapping["duration_ms"] is not None
                else None,
                "error": mapping["error"],
            }
        )

    return {
        "updated_at": now.isoformat(),
        "sources": {
            "total": int(total_sources),
            "active": int(active_sources),
            "inactive": int(total_sources - active_sources),
            "degraded": int(degraded_sources),
            "auto_discovered": int(auto_sources),
            "avg_priority": float(avg_priority) if avg_priority is not None else 0.0,
            "last_run_at": _iso(last_run_at),
            "tag_breakdown": dict(tag_counter.most_common()),
        },
        "runs": {
            "window_hours": window_hours,
            "total": int(total_runs),
            "failed": int(failed_runs),
            "items_processed": int(items_processed or 0),
            "avg_duration_ms": float(avg_duration_ms) if avg_duration_ms is not None else None,
            "recent": recent_runs,
        },
        "discoveries": {
            "pending": 0,
            "approved": 0,
            "sources": [],
        },
    }


__all__ = [
    "coerce_bool",
    "coerce_int",
    "normalize_tags",
    "serialize_source",
    "list_sources",
    "create_source",
    "update_source",
    "bulk_update_sources",
    "trigger_health_check",
    "get_crawler_metrics",
]
