from __future__ import annotations

import json
import time
from typing import List, Optional

from flask import Blueprint, Response, current_app, render_template, request

from app.db import get_session
from app.services.analytics import compute_heatmap
from app.services.items import fetch_new_items, parse_iso_datetime

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def overview():
    return render_template("ui/overview.html")


@ui_bp.route("/stream")
def stream():
    return render_template("ui/stream.html")


@ui_bp.route("/stream/live")
def stream_live() -> Response:
    refresh_raw = request.args.get("refresh")
    try:
        refresh = int(refresh_raw) if refresh_raw not in (None, "") else 10
    except ValueError:
        return {"error": "Parameter 'refresh' muss eine Ganzzahl sein."}, 400
    refresh = max(2, min(refresh, 60))

    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw not in (None, "") else 25
    except ValueError:
        return {"error": "Parameter 'limit' muss eine Ganzzahl sein."}, 400
    limit = max(1, min(limit, 100))

    after_raw = request.args.get("after_id")
    after_id: int | None
    if after_raw in (None, ""):
        after_id = None
    else:
        try:
            after_id = int(after_raw)
        except ValueError:
            return {"error": "Parameter 'after_id' muss eine Ganzzahl sein."}, 400
        if after_id < 0:
            after_id = 0

    query = request.args.get("query")
    lang = request.args.get("lang")
    scheme = request.args.get("scheme")

    value_raw = request.args.get("value")
    if value_raw in (None, ""):
        value = None
    else:
        try:
            value = int(value_raw)
        except ValueError:
            return {"error": "Parameter 'value' muss eine Ganzzahl sein."}, 400

    sources_param = request.args.get("source") or request.args.get("sources")
    sources = _parse_sources_param(sources_param)

    since_raw = request.args.get("from") or request.args.get("since")
    until_raw = request.args.get("to") or request.args.get("until")

    try:
        since = parse_iso_datetime(since_raw)
        until = parse_iso_datetime(until_raw)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    if since and until and since > until:
        return {"error": "Parameter 'from' darf nicht nach 'to' liegen."}, 400

    db_url = current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")

    def serialize(items):
        payload = []
        for item in items:
            payload.append(
                {
                    "id": item.id,
                    "source": item.source,
                    "title": item.title,
                    "url": item.url,
                    "lang": item.lang,
                    "fetched_at": item.fetched_at.isoformat(),
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "gematria": item.gematria,
                }
            )
        return payload

    def event_stream():
        cursor = after_id
        try:
            while True:
                session = get_session(db_url)
                try:
                    items = fetch_new_items(
                        session,
                        after_id=cursor,
                        limit=limit,
                        query=query,
                        sources=sources,
                        lang=lang,
                        since=since,
                        until=until,
                        scheme=scheme,
                        value=value,
                    )
                finally:
                    session.close()

                if items:
                    highest_id = max(item.id for item in items)
                    cursor = highest_id if cursor is None else max(cursor, highest_id)
                    payload = {"items": serialize(items), "cursor": cursor}
                    yield f"data: {json.dumps(payload)}\n\n"
                else:
                    yield ": heartbeat\n\n"

                time.sleep(refresh)
        except GeneratorExit:
            return

    headers = {"Cache-Control": "no-cache"}
    return Response(event_stream(), mimetype="text/event-stream", headers=headers)


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

