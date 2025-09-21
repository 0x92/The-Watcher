from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from flask import current_app, request
from pydantic import BaseModel, Field

from app.db import get_session
from app.services.analytics import HeatmapResponse, HeatmapSeries, TimelineEvent, compute_heatmap


class HeatmapSeriesDTO(BaseModel):
    source: str
    counts: List[int]
    total: int


class TimelineEventDTO(BaseModel):
    at: datetime
    alert: str
    severity: int | None = None
    meta: dict = Field(default_factory=dict)


class HeatmapDTO(BaseModel):
    buckets: List[datetime]
    series: List[HeatmapSeriesDTO]
    timeline: List[TimelineEventDTO]
    meta: dict


def _parse_sources(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    values = [part.strip() for part in raw.split(",") if part.strip()]
    return values or None


def heatmap() -> tuple[dict, int]:
    interval = request.args.get("interval", "24h")
    bucket_override = request.args.get("bucket", type=int)
    value_min = request.args.get("value_min", type=int)
    if value_min is None:
        value_min = 0
    sources_param = request.args.get("source") or request.args.get("sources")
    sources = _parse_sources(sources_param)

    db_url = current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")
    session = get_session(db_url)
    try:
        response: HeatmapResponse = compute_heatmap(
            session,
            interval=interval,
            sources=sources,
            value_min=value_min,
            bucket_minutes=bucket_override,
        )
    except ValueError as exc:
        session.close()
        return {"error": str(exc)}, 400
    finally:
        if session:
            session.close()

    payload = HeatmapDTO(
        buckets=response.buckets,
        series=[
            HeatmapSeriesDTO(source=series.source, counts=series.counts, total=series.total)
            for series in response.series
        ],
        timeline=[
            TimelineEventDTO(at=event.at, alert=event.alert, severity=event.severity, meta=event.meta)
            for event in response.timeline
        ],
        meta=response.meta,
    )
    data = payload.model_dump()
    data["buckets"] = [bucket.isoformat() for bucket in payload.buckets]
    for event in data["timeline"]:
        event["at"] = event["at"].isoformat()
    return data, 200


__all__ = ["heatmap"]
