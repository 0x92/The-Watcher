from __future__ import annotations

import os
import json
import time
from typing import Any, Dict, List, Optional

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    stream_with_context,
)
from flask_login import login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.extensions import csrf
from app.models import Source
from app.security import role_required
from app.services.crawlers import (
    bulk_update_sources,
    coerce_bool,
    coerce_int,
    create_source as crawler_create_source,
    get_crawler_metrics,
    list_sources as crawler_list_sources,
    serialize_source as crawler_serialize_source,
    trigger_health_check,
    update_source as crawler_update_source,
)
from app.services.settings import get_worker_settings
from app.services.workers import (
    WorkerCommandError,
    WorkerUnavailableError,
    execute_worker_command,
    get_worker_overview,
)


crawlers_api_bp = Blueprint("api_crawlers", __name__)


def _database_url() -> Optional[str]:
    config_url = current_app.config.get("DATABASE_URL")
    env_url = os.getenv("DATABASE_URL")
    if env_url and env_url != config_url:
        return env_url
    if config_url:
        return config_url
    alt = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if alt:
        return alt
    return env_url


def _open_session():
    return get_session(_database_url())


def _build_overview(session, *, window_hours: int = 24) -> Dict[str, Any]:
    metrics = get_crawler_metrics(session, window_hours=window_hours)
    worker_snapshot = get_worker_overview()

    updated_at = metrics.pop("updated_at", None)
    return {
        "updated_at": updated_at,
        "sources": metrics.get("sources", {}),
        "runs": metrics.get("runs", {}),
        "discoveries": metrics.get("discoveries", {}),
        "workers": worker_snapshot,
    }


@crawlers_api_bp.get("")
@login_required
@role_required("admin")
def crawler_overview():
    session = _open_session()
    try:
        window_hours = coerce_int(request.args.get("window_hours"), 24, minimum=1, maximum=168)
        payload = _build_overview(session, window_hours=window_hours)
        return jsonify(payload), 200
    finally:
        session.close()


@crawlers_api_bp.get("/stream")
@login_required
@role_required("admin")
def crawler_overview_stream():
    window_hours = coerce_int(request.args.get("window_hours"), 24, minimum=1, maximum=168)
    refresh = coerce_int(request.args.get("refresh"), 5, minimum=2, maximum=60)

    def event_stream():
        while True:
            session = _open_session()
            try:
                payload = _build_overview(session, window_hours=window_hours)
            finally:
                session.close()
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(refresh)

    headers = {"Cache-Control": "no-cache"}
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream", headers=headers)


@crawlers_api_bp.get("/feeds")
@login_required
@role_required("admin")
def list_feeds():
    session = _open_session()
    try:
        search_param = (request.args.get("q") or request.args.get("query") or "").strip()
        search = search_param or None

        type_param = request.args.get("type") or request.args.get("types")
        type_values = [segment.strip() for segment in (type_param or "").split(",") if segment.strip()]

        enabled_param = request.args.get("enabled")
        enabled_filter: Optional[bool] = None
        if enabled_param not in (None, ""):
            enabled_filter = coerce_bool(enabled_param, True)

        tags_param = request.args.get("tags")
        tag_values = [segment.strip() for segment in (tags_param or "").split(",") if segment.strip()]

        include_runs_param = request.args.get("include_runs")
        include_runs = False
        if include_runs_param not in (None, ""):
            include_runs = coerce_bool(include_runs_param, False)

        serialized, meta, filters_payload = crawler_list_sources(
            session,
            search=search,
            types=type_values,
            enabled=enabled_filter,
            tags=tag_values,
            include_runs=include_runs,
        )

        total_sources_all = session.scalar(select(func.count(Source.id))) or 0
        meta.setdefault("total_sources_all", int(total_sources_all))

        filters_payload.setdefault("query", search)
        filters_payload.setdefault("types", type_values)
        filters_payload.setdefault("enabled", enabled_filter)
        filters_payload.setdefault("tags", tag_values)

        payload = {
            "sources": serialized,
            "meta": meta,
            "filters": filters_payload,
        }
        return jsonify(payload), 200
    finally:
        session.close()


@crawlers_api_bp.post("/feeds")
@csrf.exempt
@login_required
@role_required("admin")
def create_feed():
    session = _open_session()
    try:
        payload = request.get_json() or {}
        settings = get_worker_settings(session)

        source, errors = crawler_create_source(session, payload, defaults=settings)
        if errors:
            session.rollback()
            message = errors[0] if errors else "invalid source payload"
            return jsonify({"error": message, "errors": errors}), 400

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return jsonify({"error": "could not create feed"}), 409

        return jsonify(crawler_serialize_source(source)), 201
    finally:
        session.close()


@crawlers_api_bp.put("/feeds/<int:source_id>")
@csrf.exempt
@login_required
@role_required("admin")
def update_feed(source_id: int):
    session = _open_session()
    try:
        source = session.get(Source, source_id)
        if source is None:
            return jsonify({"error": "feed not found"}), 404

        payload = request.get_json() or {}
        settings = get_worker_settings(session)
        errors = crawler_update_source(source, payload, defaults=settings)
        if errors:
            session.rollback()
            message = errors[0] if errors else "invalid payload"
            return jsonify({"error": message, "errors": errors}), 400

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return jsonify({"error": "could not update feed"}), 409

        return jsonify(crawler_serialize_source(source)), 200
    finally:
        session.close()


@crawlers_api_bp.delete("/feeds/<int:source_id>")
@csrf.exempt
@login_required
@role_required("admin")
def delete_feed(source_id: int):
    session = _open_session()
    try:
        source = session.get(Source, source_id)
        if source is None:
            return jsonify({"error": "feed not found"}), 404
        session.delete(source)
        session.commit()
        return jsonify({"status": "deleted"}), 200
    finally:
        session.close()


@crawlers_api_bp.post("/feeds/<int:source_id>/actions/health-check")
@csrf.exempt
@login_required
@role_required("admin")
def health_check_feed(source_id: int):
    session = _open_session()
    try:
        source = session.get(Source, source_id)
        if source is None:
            return jsonify({"error": "feed not found"}), 404
        result = trigger_health_check(session, source)
        return jsonify(result), 200
    finally:
        session.close()


@crawlers_api_bp.post("/feeds/bulk")
@csrf.exempt
@login_required
@role_required("admin")
def bulk_update_feeds():
    session = _open_session()
    try:
        payload = request.get_json() or {}
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            return jsonify({"error": "ids must be a non-empty list"}), 400
        action = (payload.get("action") or "").strip()
        if not action:
            return jsonify({"error": "action is required"}), 400

        try:
            result = bulk_update_sources(session, ids, action=action, payload=payload.get("payload"))
        except ValueError as exc:
            session.rollback()
            return jsonify({"error": str(exc)}), 400

        return jsonify(result), 200
    finally:
        session.close()


@crawlers_api_bp.post("/<string:worker_name>/control")
@csrf.exempt
@login_required
@role_required("admin")
def control_worker(worker_name: str):
    payload = request.get_json() or {}
    action = (payload.get("action") or "").strip().lower()
    if not action:
        return jsonify({"error": "action is required"}), 400

    try:
        result = execute_worker_command(worker_name, action)
    except WorkerUnavailableError as exc:
        return jsonify({"error": str(exc)}), 404
    except WorkerCommandError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(result), 200


__all__ = ["crawlers_api_bp"]
