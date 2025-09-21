from __future__ import annotations

import json
import time
from typing import List, Optional

from flask import Blueprint, Response, current_app, render_template, request

from app.db import get_session
from app.services.analytics import compute_heatmap

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def overview():
    return render_template("ui/overview.html")


@ui_bp.route("/stream")
def stream():
    return render_template("ui/stream.html")


@ui_bp.route("/heatmap")
def heatmap():
    return render_template("ui/heatmap.html")


@ui_bp.route("/graph")
def graph():
    return render_template("ui/graph.html")


@ui_bp.route("/alerts")
def alerts():
    return render_template("ui/alerts.html")


@ui_bp.route("/admin")
def admin():
    return render_template("ui/admin.html")


@ui_bp.route("/patterns")
def patterns():
    return render_template("ui/patterns.html")


def _parse_sources_param(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [segment.strip() for segment in value.split(",") if segment.strip()]
    return parts or None


@ui_bp.route("/stream/analytics/heatmap")
def heatmap_stream() -> Response:
    interval = request.args.get("interval", "24h")
    value_min = request.args.get("value_min", type=int) or 0
    sources = _parse_sources_param(request.args.get("source") or request.args.get("sources"))
    refresh = request.args.get("refresh", type=int) or 15
    refresh = max(5, min(refresh, 300))

    db_url = current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")

    def serialize(response):
        payload = {
            "buckets": [bucket.isoformat() for bucket in response.buckets],
            "series": [
                {"source": series.source, "counts": series.counts, "total": series.total}
                for series in response.series
            ],
            "timeline": [
                {
                    "at": event.at.isoformat(),
                    "alert": event.alert,
                    "severity": event.severity,
                    "meta": event.meta,
                }
                for event in response.timeline
            ],
            "meta": response.meta,
        }
        return payload

    def event_stream():
        try:
            while True:
                session = get_session(db_url)
                try:
                    result = compute_heatmap(
                        session,
                        interval=interval,
                        sources=sources,
                        value_min=value_min,
                    )
                except ValueError as exc:
                    session.close()
                    error_payload = json.dumps({"error": str(exc)})
                    yield f"data: {error_payload}\n\n"
                    return
                finally:
                    session.close()

                payload = serialize(result)
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(refresh)
        except GeneratorExit:
            return

    headers = {"Cache-Control": "no-cache"}
    return Response(event_stream(), mimetype="text/event-stream", headers=headers)

