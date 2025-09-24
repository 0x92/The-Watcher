from __future__ import annotations

import os
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.extensions import csrf
from app.models import Source
from app.security import role_required
from app.services.gematria import list_available_schemes
from app.services.crawlers import (
    coerce_bool as crawler_coerce_bool,
    coerce_int as crawler_coerce_int,
    create_source as crawler_create_source,
    list_sources as crawler_list_sources,
    serialize_source as crawler_serialize_source,
    update_source as crawler_update_source,
)
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


_coerce_bool = crawler_coerce_bool

_coerce_int = crawler_coerce_int

_serialize_source = crawler_serialize_source

def _open_session():
    return get_session(_database_url())


DISPLAY_SCHEME_ALIASES = {
    "english_sumerian": "sumerian",
}


def _display_scheme(key: str) -> str:
    return DISPLAY_SCHEME_ALIASES.get(key, key)


def _serialize_gematria_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    enabled_values = settings.get("enabled_schemes", [])
    enabled_display = [_display_scheme(value) for value in enabled_values]
    defaults_display = [_display_scheme(value) for value in DEFAULT_GEMATRIA_SETTINGS.enabled_schemes]
    return {
        "enabled": enabled_display,
        "ignore_pattern": settings.get("ignore_pattern"),
        "available": list_available_schemes(),
        "defaults": {
            "enabled": list(defaults_display),
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
        search_param = (request.args.get("q") or request.args.get("query") or "").strip()
        search = search_param or None

        type_param = request.args.get("type") or request.args.get("types")
        type_values = [segment.strip() for segment in (type_param or "").split(",") if segment.strip()]

        enabled_param = request.args.get("enabled")
        enabled_filter = None
        if enabled_param not in (None, ""):
            enabled_filter = _coerce_bool(enabled_param, True)

        tags_param = request.args.get("tags")
        tag_values = [segment.strip() for segment in (tags_param or "").split(",") if segment.strip()]

        include_runs_param = request.args.get("include_runs")
        include_runs_flag = False
        if include_runs_param not in (None, ""):
            include_runs_flag = _coerce_bool(include_runs_param, False)

        serialized, meta, filters_payload = crawler_list_sources(
            session,
            search=search,
            types=type_values,
            enabled=enabled_filter,
            tags=tag_values,
            include_runs=include_runs_flag,
        )

        total_sources_all = session.scalar(select(func.count(Source.id))) or 0
        meta.setdefault("total_sources_all", int(total_sources_all))

        filters_payload.setdefault("query", search)
        filters_payload.setdefault("types", type_values)
        filters_payload.setdefault("enabled", enabled_filter)
        filters_payload.setdefault("tags", tag_values)
        if not tag_values:
            filters_payload.pop("tags", None)

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

