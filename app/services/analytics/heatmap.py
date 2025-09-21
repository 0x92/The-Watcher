from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Item, Source


@dataclass
class HeatmapSeries:
    source: str
    counts: List[int]
    total: int


@dataclass
class TimelineEvent:
    at: datetime
    alert: str
    severity: int | None
    meta: dict = field(default_factory=dict)


@dataclass
class HeatmapResponse:
    buckets: List[datetime]
    series: List[HeatmapSeries]
    timeline: List[TimelineEvent]
    meta: dict = field(default_factory=dict)


_INTERVAL_DEFAULT = {
    "6h": (timedelta(hours=6), 30),
    "12h": (timedelta(hours=12), 60),
    "24h": (timedelta(hours=24), 60),
    "3d": (timedelta(days=3), 180),
    "7d": (timedelta(days=7), 360),
    "30d": (timedelta(days=30), 1440),
}


def parse_interval(value: str | None) -> tuple[timedelta, int]:
    value = (value or "24h").lower().strip()
    if value in _INTERVAL_DEFAULT:
        return _INTERVAL_DEFAULT[value]
    if value.endswith("h") and value[:-1].isdigit():
        hours = int(value[:-1])
        minutes = 60 if hours <= 48 else 180
        return timedelta(hours=hours), minutes
    if value.endswith("d") and value[:-1].isdigit():
        days = int(value[:-1])
        minutes = 180 if days <= 3 else 1440
        return timedelta(days=days), minutes
    raise ValueError(f"Unsupported interval '{value}'")


def _select_recent_items(
    session: Session,
    *,
    since: datetime,
    until: datetime,
    sources: Optional[Sequence[str]] = None,
) -> List[tuple[datetime, str]]:
    stmt = (
        select(Item.fetched_at, Source.name)
        .join(Source, Item.source_id == Source.id)
        .where(Item.fetched_at >= since)
        .where(Item.fetched_at <= until)
        .order_by(Item.fetched_at.asc())
    )
    if sources:
        stmt = stmt.where(Source.name.in_(sources))
    return session.execute(stmt).all()


def _select_recent_events(
    session: Session, *, since: datetime, until: datetime
) -> List[tuple[datetime, str, Optional[int]]]:
    stmt = (
        select(Event.triggered_at, Alert.name, Alert.severity)
        .join(Alert, Event.alert_id == Alert.id)
        .where(Event.triggered_at >= since)
        .where(Event.triggered_at <= until)
        .order_by(Event.triggered_at.asc())
    )
    return session.execute(stmt).all()


def compute_heatmap(
    session: Session,
    *,
    interval: str = "24h",
    sources: Optional[Sequence[str]] = None,
    value_min: int = 0,
    bucket_minutes: Optional[int] = None,
) -> HeatmapResponse:
    delta, default_bucket_minutes = parse_interval(interval)
    bucket_span = bucket_minutes or default_bucket_minutes
    bucket_span = max(5, bucket_span)

    now = datetime.utcnow()
    since = now - delta
    until = now

    items = _select_recent_items(session, since=since, until=until, sources=sources)
    timeline_rows = _select_recent_events(session, since=since, until=until)

    bucket_count = max(1, int(((until - since).total_seconds() // (bucket_span * 60)) + 1))
    buckets: List[datetime] = [since + timedelta(minutes=bucket_span * i) for i in range(bucket_count)]

    counts: Dict[str, List[int]] = {}
    totals: Dict[str, int] = {}

    for fetched_at, source_name in items:
        offset = fetched_at - since
        index = int(offset.total_seconds() // (bucket_span * 60))
        if index >= bucket_count:
            index = bucket_count - 1
        series = counts.setdefault(source_name, [0] * bucket_count)
        series[index] += 1
        totals[source_name] = totals.get(source_name, 0) + 1

    series_list: List[HeatmapSeries] = []
    for source_name, values in counts.items():
        total = totals.get(source_name, 0)
        if total < value_min:
            continue
        series_list.append(HeatmapSeries(source=source_name, counts=values, total=total))

    series_list.sort(key=lambda item: item.total, reverse=True)

    timeline: List[TimelineEvent] = [
        TimelineEvent(at=triggered_at, alert=alert_name, severity=severity)
        for triggered_at, alert_name, severity in timeline_rows
    ]

    meta = {
        "interval": interval,
        "bucket_minutes": bucket_span,
        "bucket_count": bucket_count,
        "sources": list(sources) if sources else None,
        "value_min": value_min,
        "item_count": len(items),
        "event_count": len(timeline_rows),
        "source_totals": {series.source: series.total for series in series_list},
    }

    return HeatmapResponse(buckets=buckets, series=series_list, timeline=timeline, meta=meta)
