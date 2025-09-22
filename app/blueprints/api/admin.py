from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.extensions import csrf
from app.models import Item, Source
from app.security import role_required
from app.services.settings import get_worker_settings, update_worker_settings
from app.services.workers import (
    WorkerCommandError,
    WorkerUnavailableError,
    execute_worker_command,
    get_worker_overview,
)


admin_api_bp = Blueprint("api_admin", __name__)


def _database_url() -> str | None:
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


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, integer)


def _serialize_source(source: Source, stats: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stats = stats or {}

    def _iso(value: Any) -> str | None:
        return value.isoformat() if isinstance(value, datetime) else None

    latest = stats.get("latest_item") or {}

    return {
        "id": source.id,
        "name": source.name,
        "type": source.type,
        "endpoint": source.endpoint,
        "enabled": bool(source.enabled),
        "interval_minutes": int((source.interval_sec or 0) / 60),
        "last_run_at": source.last_run_at.isoformat() if source.last_run_at else None,
        "created_at": source.created_at.isoformat() if isinstance(source.created_at, datetime) else None,
        "auth": source.auth_json or {},
        "filters": source.filters_json or {},
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


def _open_session():
    return get_session(_database_url())


@admin_api_bp.get("/worker-settings")
@login_required
@role_required("admin")
def get_worker_settings_endpoint():
    session = _open_session()
    try:
        settings = get_worker_settings(session)
        return jsonify(settings), 200
    finally:
        session.close()


@admin_api_bp.put("/worker-settings")
@csrf.exempt
@login_required
@role_required("admin")
def update_worker_settings_endpoint():
    session = _open_session()
    try:
        payload = request.get_json() or {}
        settings = update_worker_settings(session, payload)
        return jsonify(settings), 200
    finally:
        session.close()


@admin_api_bp.get("/workers")
@login_required
@role_required("admin")
def list_workers_endpoint():
    overview = get_worker_overview()
    return jsonify(overview), 200


@admin_api_bp.post("/workers/<path:worker_name>/control")
@csrf.exempt
@login_required
@role_required("admin")
def control_worker_endpoint(worker_name: str):
    payload = request.get_json() or {}
    action = (payload.get("action") or "").strip()
    if not action:
        return jsonify({"error": "action is required"}), 400

    try:
        result = execute_worker_command(worker_name, action)
    except ValueError:
        return jsonify({"error": "invalid action"}), 400
    except WorkerUnavailableError as exc:
        return jsonify({"error": str(exc)}), 404
    except WorkerCommandError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(result), 200


@admin_api_bp.get("/sources")
@login_required
@role_required("admin")
def list_sources_endpoint():
    session = _open_session()
    try:
        stmt = select(Source).order_by(Source.name.asc())

        search = (request.args.get("q") or "").strip()
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Source.name).like(pattern),
                    func.lower(Source.endpoint).like(pattern),
                    func.lower(Source.type).like(pattern),
                )
            )

        type_param = request.args.get("type") or request.args.get("types")
        type_values = [segment.strip() for segment in (type_param or "").split(",") if segment.strip()]
        if type_values:
            stmt = stmt.where(Source.type.in_(type_values))

        enabled_param = request.args.get("enabled")
        enabled_filter: bool | None = None
        if enabled_param not in (None, ""):
            enabled_filter = _coerce_bool(enabled_param, True)
            stmt = stmt.where(Source.enabled.is_(True if enabled_filter else False))

        sources = session.scalars(stmt).all()
        source_ids = [source.id for source in sources]

        stats_map: Dict[int, Dict[str, Any]] = {
            source.id: {
                "total_items": 0,
                "last_published_at": None,
                "last_fetched_at": None,
            }
            for source in sources
        }

        if source_ids:
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
                stats_map[source_id]["total_items"] = int(total_items or 0)
                stats_map[source_id]["last_published_at"] = last_published
                stats_map[source_id]["last_fetched_at"] = last_fetched

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
                    Item.published_at.desc().nulls_last(),
                    Item.fetched_at.desc().nulls_last(),
                    Item.id.desc(),
                )
            )
            seen: set[int] = set()
            for source_id, title, url, published_at, fetched_at in session.execute(latest_stmt):
                if source_id in seen:
                    continue
                stats_map[source_id]["latest_item"] = {
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                    "fetched_at": fetched_at,
                }
                seen.add(source_id)
                if len(seen) == len(source_ids):
                    break

        serialized = [_serialize_source(src, stats_map.get(src.id)) for src in sources]

        type_counter = Counter(source.type for source in sources)
        active_sources = sum(1 for source in sources if source.enabled)
        total_items = sum(entry.get("total_items", 0) for entry in stats_map.values())
        last_run_at = None
        for source in sources:
            if source.last_run_at and (last_run_at is None or source.last_run_at > last_run_at):
                last_run_at = source.last_run_at

        total_sources_all = session.scalar(select(func.count()).select_from(Source)) or 0

        meta = {
            "total_sources": len(serialized),
            "active_sources": active_sources,
            "inactive_sources": len(serialized) - active_sources,
            "total_items": int(total_items),
            "type_breakdown": dict(sorted(type_counter.items())),
            "last_run_at": last_run_at.isoformat() if isinstance(last_run_at, datetime) else None,
            "total_sources_all": int(total_sources_all),
            "filters_applied": bool(search or type_values or enabled_param not in (None, "")),
        }

        filters_payload = {
            "query": search or None,
            "types": type_values,
            "enabled": enabled_filter,
        }

        payload = {
            "sources": serialized,
            "meta": meta,
            "filters": filters_payload,
        }

        return jsonify(payload), 200
    finally:
        session.close()


@admin_api_bp.post("/sources")
@csrf.exempt
@login_required
@role_required("admin")
def create_source_endpoint():
    session = _open_session()
    try:
        payload = request.get_json() or {}
        name = (payload.get("name") or "").strip()
        endpoint = (payload.get("endpoint") or "").strip()
        if not name or not endpoint:
            return jsonify({"error": "name and endpoint are required"}), 400

        source_type = (payload.get("type") or "rss").strip() or "rss"
        settings = get_worker_settings(session)
        interval_minutes = payload.get("interval_minutes")
        if interval_minutes is None:
            interval_minutes = settings.get("default_interval_minutes", 15)
        interval_minutes = _coerce_int(interval_minutes, settings.get("default_interval_minutes", 15), minimum=0)

        source = Source(
            name=name,
            type=source_type,
            endpoint=endpoint,
            enabled=_coerce_bool(payload.get("enabled"), True),
            interval_sec=interval_minutes * 60,
        )
        if isinstance(payload.get("auth"), dict):
            source.auth_json = payload.get("auth")
        if isinstance(payload.get("filters"), dict):
            source.filters_json = payload.get("filters")

        session.add(source)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return jsonify({"error": "could not create source"}), 409
        return jsonify(_serialize_source(source)), 201
    finally:
        session.close()


@admin_api_bp.put("/sources/<int:source_id>")
@csrf.exempt
@login_required
@role_required("admin")
def update_source_endpoint(source_id: int):
    session = _open_session()
    try:
        source = session.get(Source, source_id)
        if source is None:
            return jsonify({"error": "source not found"}), 404

        payload = request.get_json() or {}

        if "name" in payload:
            name = (payload.get("name") or "").strip()
            if not name:
                return jsonify({"error": "name cannot be empty"}), 400
            source.name = name
        if "endpoint" in payload:
            endpoint = (payload.get("endpoint") or "").strip()
            if not endpoint:
                return jsonify({"error": "endpoint cannot be empty"}), 400
            source.endpoint = endpoint
        if "type" in payload:
            source.type = (payload.get("type") or source.type).strip() or source.type
        if "enabled" in payload:
            source.enabled = _coerce_bool(payload.get("enabled"), bool(source.enabled))
        if "interval_minutes" in payload:
            interval_minutes = _coerce_int(
                payload.get("interval_minutes"),
                int((source.interval_sec or 0) / 60),
                minimum=0,
            )
            source.interval_sec = interval_minutes * 60
        if "auth" in payload and isinstance(payload.get("auth"), dict):
            source.auth_json = payload.get("auth")
        if "filters" in payload and isinstance(payload.get("filters"), dict):
            source.filters_json = payload.get("filters")

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return jsonify({"error": "could not update source"}), 409
        return jsonify(_serialize_source(source)), 200
    finally:
        session.close()


@admin_api_bp.delete("/sources/<int:source_id>")
@csrf.exempt
@login_required
@role_required("admin")
def delete_source_endpoint(source_id: int):
    session = _open_session()
    try:
        source = session.get(Source, source_id)
        if source is None:
            return jsonify({"error": "source not found"}), 404
        session.delete(source)
        session.commit()
        return jsonify({"status": "deleted"}), 200
    finally:
        session.close()


__all__ = ["admin_api_bp"]

