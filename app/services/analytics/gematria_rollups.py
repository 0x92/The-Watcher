from __future__ import annotations

import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Gematria, GematriaRollup, Item, Source
from app.services.gematria.schemes import SCHEME_DEFINITIONS

DEFAULT_WINDOWS: Tuple[int, int, int] = (24, 48, 168)
DEFAULT_MAX_TOP_VALUES = 8
DEFAULT_TREND_BUCKETS = 12
ROLLUP_TTL_SECONDS = int(os.getenv("GEMATRIA_ROLLUP_TTL", "900"))



def _scope_key(source_id: Optional[int]) -> str:
    return "global" if source_id is None else f"source:{int(source_id)}"


def _window_bounds(window_hours: int, *, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    if window_hours <= 0:
        raise ValueError("window_hours must be greater than zero")
    end = (now or datetime.utcnow()).replace(microsecond=0)
    start = end - timedelta(hours=window_hours)
    return start, end


def _percentile(sorted_values: Sequence[int], percentile: float) -> Optional[float]:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = percentile * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    lower_val = sorted_values[lower]
    upper_val = sorted_values[upper]
    if lower == upper:
        return float(lower_val)
    weight = rank - lower
    return float(lower_val + weight * (upper_val - lower_val))


def _pearson(x_values: List[float], y_values: List[float]) -> Optional[float]:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(y_values) / len(y_values)
    var_x = sum((value - mean_x) ** 2 for value in x_values)
    var_y = sum((value - mean_y) ** 2 for value in y_values)
    if var_x == 0 or var_y == 0:
        return None
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    return round(covariance / math.sqrt(var_x * var_y), 4)


def _trend_buckets(start: datetime, end: datetime, *, bucket_count: int) -> List[Dict[str, object]]:
    bucket_count = max(1, min(bucket_count, DEFAULT_TREND_BUCKETS))
    total_seconds = max((end - start).total_seconds(), 1)
    bucket_seconds = total_seconds / bucket_count
    buckets: List[Dict[str, object]] = []
    cursor = start
    for index in range(bucket_count):
        bucket_end = start + timedelta(seconds=bucket_seconds * (index + 1))
        buckets.append(
            {
                "bucket_start": cursor,
                "bucket_end": bucket_end if bucket_end <= end else end,
                "count": 0,
                "sum": 0.0,
            }
        )
        cursor = bucket_end
    buckets[-1]["bucket_end"] = end
    return buckets


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat()


def compute_rollup(
    session: Session,
    scheme: str,
    window_hours: int,
    *,
    source_id: Optional[int] = None,
    now: Optional[datetime] = None,
    max_top_values: int = DEFAULT_MAX_TOP_VALUES,
    trend_buckets: int = DEFAULT_TREND_BUCKETS,
) -> Dict[str, object]:
    if scheme not in SCHEME_DEFINITIONS:
        raise ValueError(f"Unknown scheme '{scheme}'")

    window_start, window_end = _window_bounds(window_hours, now=now)

    stmt = (
        select(
            Gematria.value,
            Item.id,
            Item.title,
            Item.fetched_at,
            Item.published_at,
            Item.lang,
            Source.id,
            Source.name,
            Source.priority,
        )
        .join(Item, Gematria.item_id == Item.id)
        .join(Source, Item.source_id == Source.id)
        .where(Gematria.scheme == scheme)
        .where(Item.fetched_at >= window_start)
        .where(Item.fetched_at <= window_end)
    )
    if source_id is not None:
        stmt = stmt.where(Source.id == source_id)

    rows = session.execute(stmt).all()

    values: List[int] = []
    fetched_at: List[datetime] = []
    title_lengths: List[int] = []
    priority_pairs: List[Tuple[float, float]] = []

    source_stats: Dict[int, Dict[str, object]] = defaultdict(
        lambda: {"count": 0, "sum": 0.0, "name": "", "priority": None}
    )
    top_samples: Dict[int, List[Dict[str, object]]] = defaultdict(list)

    for row in rows:
        value = int(row[0])
        item_id = row[1]
        title = row[2] or ""
        fetched = row[3] or row[4] or window_start
        lang = row[5] or ""
        src_id = int(row[6])
        src_name = row[7] or f"Source {src_id}"
        priority = row[8]

        values.append(value)
        fetched_at.append(fetched)
        title_lengths.append(len(title))
        if priority is not None:
            priority_pairs.append((float(value), float(priority)))

        stats = source_stats[src_id]
        stats["count"] = int(stats["count"]) + 1
        stats["sum"] = float(stats["sum"]) + value
        stats["name"] = src_name
        stats["priority"] = priority if priority is not None else stats["priority"]

        if len(top_samples[value]) < 3:
            top_samples[value].append(
                {
                    "item_id": item_id,
                    "title": title,
                    "lang": lang,
                    "source_id": src_id,
                    "source": src_name,
                }
            )

    total_items = len(values)
    sorted_values = sorted(values)
    scope = _scope_key(source_id)
    summary = {
        "total_items": total_items,
        "unique_sources": len(source_stats),
        "sum": float(sum(values)),
        "avg": (float(sum(values)) / total_items) if total_items else 0.0,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "percentiles": {
            "p50": _percentile(sorted_values, 0.5),
            "p90": _percentile(sorted_values, 0.9),
            "p99": _percentile(sorted_values, 0.99),
        },
    }

    value_counter = Counter(values)
    top_values = []
    for value, count in value_counter.most_common(max_top_values):
        share = (count / total_items) if total_items else 0
        top_values.append(
            {
                "value": value,
                "count": count,
                "share": round(share, 4),
                "samples": top_samples.get(value, []),
            }
        )

    buckets = _trend_buckets(window_start, window_end, bucket_count=min(trend_buckets, window_hours or 1))
    if values:
        bucket_seconds = max((window_end - window_start).total_seconds() / len(buckets), 1)
        for value, when in zip(values, fetched_at):
            seconds = (when - window_start).total_seconds()
            index = int(min(len(buckets) - 1, max(0, seconds // bucket_seconds)))
            bucket = buckets[index]
            bucket["count"] = int(bucket["count"]) + 1
            bucket["sum"] = float(bucket["sum"]) + value
        trend = [
            {
                "bucket_start": _serialize_datetime(bucket["bucket_start"]),
                "bucket_end": _serialize_datetime(bucket["bucket_end"]),
                "count": int(bucket["count"]),
                "avg": round(bucket["sum"] / bucket["count"], 2) if bucket["count"] else 0.0,
            }
            for bucket in buckets
        ]
    else:
        trend = []

    source_breakdown = []
    for src_id, stats in sorted(source_stats.items(), key=lambda item: (-int(item[1]["count"]), item[0])):
        count = int(stats["count"])
        total = float(stats["sum"])
        source_breakdown.append(
            {
                "source_id": src_id,
                "name": stats["name"],
                "count": count,
                "avg": round(total / count, 2) if count else 0.0,
                "priority": stats["priority"],
            }
        )

    correlations = {
        "value_vs_title_length": _pearson([float(v) for v in values], [float(length) for length in title_lengths]) if values else None,
        "value_vs_source_priority": _pearson([pair[0] for pair in priority_pairs], [pair[1] for pair in priority_pairs]) if priority_pairs else None,
    }

    payload: Dict[str, object] = {
        "scheme": scheme,
        "scope": scope,
        "window_hours": window_hours,
        "window_start": _serialize_datetime(window_start),
        "window_end": _serialize_datetime(window_end),
        "summary": summary,
        "top_values": top_values,
        "trend": trend,
        "source_breakdown": source_breakdown,
        "correlations": correlations,
        "meta": {
            "total_values": total_items,
            "generated_at": _serialize_datetime(now or datetime.utcnow()),
        },
    }
    return payload


def _upsert_rollup(
    session: Session,
    *,
    scope: str,
    window_hours: int,
    scheme: str,
    payload: Dict[str, object],
    computed_at: Optional[datetime] = None,
) -> GematriaRollup:
    rollup = session.execute(
        select(GematriaRollup).where(
            GematriaRollup.scope == scope,
            GematriaRollup.window_hours == window_hours,
            GematriaRollup.scheme == scheme,
        )
    ).scalar_one_or_none()

    timestamp = (computed_at or datetime.utcnow()).replace(microsecond=0)
    if rollup is None:
        rollup = GematriaRollup(
            scope=scope,
            window_hours=window_hours,
            scheme=scheme,
            computed_at=timestamp,
            payload=payload,
        )
        session.add(rollup)
    else:
        rollup.payload = payload
        rollup.computed_at = timestamp
    return rollup


def refresh_rollups(
    session: Session,
    *,
    schemes: Optional[Iterable[str]] = None,
    window_hours: Optional[Iterable[int]] = None,
    source_ids: Optional[Iterable[Optional[int]]] = None,
    now: Optional[datetime] = None,
    commit: bool = True,
) -> List[GematriaRollup]:
    resolved_schemes = list(schemes or SCHEME_DEFINITIONS.keys())
    resolved_windows = list(window_hours or DEFAULT_WINDOWS)
    resolved_sources = list(source_ids) if source_ids is not None else [None]
    results: List[GematriaRollup] = []
    for scheme in resolved_schemes:
        for window in resolved_windows:
            for source_id in resolved_sources:
                payload = compute_rollup(session, scheme, window, source_id=source_id, now=now)
                rollup = _upsert_rollup(
                    session,
                    scope=_scope_key(source_id),
                    window_hours=window,
                    scheme=scheme,
                    payload=payload,
                    computed_at=now,
                )
                results.append(rollup)
    if commit:
        session.commit()
    return results


def get_rollup(
    session: Session,
    *,
    scheme: str,
    window_hours: int,
    source_id: Optional[int] = None,
    now: Optional[datetime] = None,
    refresh: bool = False,
) -> Dict[str, object]:
    scope = _scope_key(source_id)
    rollup = session.execute(
        select(GematriaRollup).where(
            GematriaRollup.scope == scope,
            GematriaRollup.window_hours == window_hours,
            GematriaRollup.scheme == scheme,
        )
    ).scalar_one_or_none()

    current_time = (now or datetime.utcnow()).replace(microsecond=0)
    if rollup and not refresh:
        age_seconds = (current_time - (rollup.computed_at or current_time)).total_seconds()
        if age_seconds <= ROLLUP_TTL_SECONDS and rollup.payload:
            return rollup.payload

    payload = compute_rollup(
        session,
        scheme,
        window_hours,
        source_id=source_id,
        now=current_time,
    )
    _upsert_rollup(
        session,
        scope=scope,
        window_hours=window_hours,
        scheme=scheme,
        payload=payload,
        computed_at=current_time,
    )
    session.commit()
    return payload


def refresh_rollups_job() -> None:
    from app.db import get_session

    session = get_session()
    try:
        refresh_rollups(session)
    finally:
        session.close()


__all__ = [
    "DEFAULT_WINDOWS",
    "RollupRequest",
    "compute_rollup",
    "get_rollup",
    "refresh_rollups",
    "refresh_rollups_job",
]

