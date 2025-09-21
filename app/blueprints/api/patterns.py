from __future__ import annotations

from datetime import datetime
from typing import List

from flask import current_app, request
from pydantic import BaseModel, Field

from app.db import get_session
from app.models import Pattern
from app.services.analytics.graph import parse_window


class PatternDTO(BaseModel):
    id: int
    label: str
    created_at: datetime
    top_terms: List[str] = Field(default_factory=list)
    anomaly_score: float | None = None
    item_ids: List[int] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class PatternsResponse(BaseModel):
    patterns: List[PatternDTO]
    meta: dict = Field(default_factory=dict)


def latest_patterns() -> tuple[dict, int]:
    limit = request.args.get("limit", type=int) or 10
    limit = max(1, min(limit, 50))
    window_param = request.args.get("window", "48h")

    try:
        delta = parse_window(window_param)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    since = datetime.utcnow() - delta if delta else None

    db_url = current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")
    session = get_session(db_url)
    try:
        query = session.query(Pattern).order_by(Pattern.created_at.desc())
        if since is not None:
            query = query.filter(Pattern.created_at >= since)
        rows = query.limit(limit).all()

        payload = PatternsResponse(
            patterns=[
                PatternDTO(
                    id=row.id,
                    label=row.label,
                    created_at=row.created_at,
                    top_terms=list(row.top_terms or []),
                    anomaly_score=row.anomaly_score,
                    item_ids=list(row.item_ids or []),
                    meta=row.meta or {},
                )
                for row in rows
            ],
            meta={
                "limit": limit,
                "window": window_param if delta else "all",
                "count": len(rows),
            },
        )
        return payload.model_dump(), 200
    finally:
        session.close()


__all__ = ["latest_patterns"]
