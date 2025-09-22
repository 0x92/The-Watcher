from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.extensions import csrf
from app.models import Source
from app.security import role_required
from app.services.gematria import list_available_schemes
from app.services.settings import (
    DEFAULT_GEMATRIA_SETTINGS,
    get_gematria_settings,
    get_worker_settings,
    update_gematria_settings,
    update_worker_settings,
)
from app.services.workers import (
    WorkerCommandError,
    WorkerUnavailableError,
    execute_worker_command,
    get_worker_overview,
)


admin_api_bp = Blueprint("api_admin", __name__)


def _database_url() -> str | None:
    return current_app.config.get("DATABASE_URL") or current_app.config.get(
        "SQLALCHEMY_DATABASE_URI"
    )


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


def _serialize_source(source: Source) -> Dict[str, Any]:
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
    }


def _open_session():
    return get_session(_database_url())


def _serialize_gematria_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": settings.get("enabled_schemes", []),
        "ignore_pattern": settings.get("ignore_pattern"),
        "available": list_available_schemes(),
        "defaults": {
            "enabled": list(DEFAULT_GEMATRIA_SETTINGS.enabled_schemes),
            "ignore_pattern": DEFAULT_GEMATRIA_SETTINGS.ignore_pattern,
        },
    }


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


@admin_api_bp.get("/gematria-settings")
@login_required
@role_required("admin")
def get_gematria_settings_endpoint():
    session = _open_session()
    try:
        settings = get_gematria_settings(session)
        return jsonify(_serialize_gematria_settings(settings)), 200
    finally:
        session.close()


@admin_api_bp.put("/gematria-settings")
@csrf.exempt
@login_required
@role_required("admin")
def update_gematria_settings_endpoint():
    session = _open_session()
    try:
        payload = request.get_json() or {}
        settings = update_gematria_settings(session, payload)
        return jsonify(_serialize_gematria_settings(settings)), 200
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
        sources = session.scalars(stmt).all()
        return jsonify([_serialize_source(src) for src in sources]), 200
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

