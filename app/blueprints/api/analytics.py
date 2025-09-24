from __future__ import annotations

import os
from typing import Iterable, Optional

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from app.db import get_session
from app.security import role_required
from app.services.analytics.gematria_rollups import (
    DEFAULT_WINDOWS,
    get_rollup,
    refresh_rollups,
)
from app.services.gematria.schemes import SCHEME_DEFINITIONS

analytics_api_bp = Blueprint("api_analytics", __name__)


AVAILABLE_SCHEMES = tuple(SCHEME_DEFINITIONS.keys())


def _open_session():
    db_url = (
        current_app.config.get("DATABASE_URL")
        or current_app.config.get("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_URL")
    )
    return get_session(db_url)


def _parse_window(param: Optional[str]) -> int:
    if not param:
        return DEFAULT_WINDOWS[0]
    token = param.strip().lower()
    if token.endswith("h"):
        token = token[:-1]
    try:
        value = int(token)
    except ValueError as exc:
        raise ValueError("window must be an integer number of hours") from exc
    if value <= 0:
        raise ValueError("window must be positive")
    return value


def _parse_source(param: Optional[str]) -> Optional[int]:
    if param in (None, "", "global", "all"):
        return None
    try:
        return int(param)
    except ValueError as exc:
        raise ValueError("source must be an integer id") from exc


def _parse_list(raw: Optional[Iterable]) -> Optional[list]:
    if raw is None:
        return None
    values = []
    for item in raw:
        if item is None:
            continue
        token = str(item).strip()
        if not token:
            continue
        values.append(token)
    return values or None


@analytics_api_bp.get("/gematria")
@login_required
@role_required("analyst", "admin")
def gematria_rollup_view():
    window_param = request.args.get("window") or request.args.get("window_hours")
    scheme_param = request.args.get("scheme") or request.args.get("cipher")
    ranking = (request.args.get("ranking") or "top").strip().lower()
    refresh_flag = request.args.get("refresh")

    try:
        window_hours = _parse_window(window_param)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    scheme = (scheme_param or AVAILABLE_SCHEMES[0]).strip().lower()
    if scheme not in SCHEME_DEFINITIONS:
        return jsonify({"error": f"Unknown scheme '{scheme}'"}), 400

    try:
        source_id = _parse_source(request.args.get("source") or request.args.get("source_id"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    refresh = str(refresh_flag).lower() in {"1", "true", "yes", "on"}

    session = _open_session()
    try:
        payload = get_rollup(
            session,
            scheme=scheme,
            window_hours=window_hours,
            source_id=source_id,
            refresh=refresh,
        )
    finally:
        session.close()

    payload.setdefault("meta", {})
    payload["meta"].update(
        {
            "available_windows": list(DEFAULT_WINDOWS),
            "available_schemes": list(AVAILABLE_SCHEMES),
            "ranking": ranking,
            "source_id": source_id,
        }
    )

    if ranking == "sources":
        payload["source_breakdown"] = sorted(
            payload.get("source_breakdown", []),
            key=lambda entry: (-entry.get("count", 0), entry.get("name", "")),
        )
    elif ranking == "trend":
        payload["trend"] = sorted(
            payload.get("trend", []),
            key=lambda bucket: bucket.get("bucket_start", ""),
        )
    else:
        payload["top_values"] = sorted(
            payload.get("top_values", []),
            key=lambda entry: (-entry.get("count", 0), entry.get("value", 0)),
        )

    return jsonify(payload), 200


@analytics_api_bp.post("/gematria/rebuild")
@login_required
@role_required("admin")
def rebuild_gematria_rollups():
    payload = request.get_json(silent=True) or {}
    try:
        windows_raw = _parse_list(payload.get("windows") or payload.get("window_hours"))
        schemes_raw = _parse_list(payload.get("schemes"))
        sources_raw = _parse_list(payload.get("sources") or payload.get("source_ids"))

        windows = [
            _parse_window(token) for token in windows_raw
        ] if windows_raw else list(DEFAULT_WINDOWS)
        schemes = [
            token.lower() for token in schemes_raw
        ] if schemes_raw else list(AVAILABLE_SCHEMES)
        for scheme in schemes:
            if scheme not in SCHEME_DEFINITIONS:
                raise ValueError(f"Unknown scheme '{scheme}'")

        source_ids: list[Optional[int]] = [None]
        if sources_raw:
            source_ids = []
            for token in sources_raw:
                source_ids.append(_parse_source(token))
            if not source_ids:
                source_ids = [None]
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    session = _open_session()
    try:
        results = refresh_rollups(
            session,
            window_hours=windows,
            schemes=schemes,
            source_ids=source_ids,
            commit=True,
        )
    finally:
        session.close()

    return (
        jsonify(
            {
                "status": "ok",
                "updated": len(results),
                "windows": windows,
                "schemes": schemes,
                "sources": source_ids,
            }
        ),
        202,
    )


__all__ = ["analytics_api_bp", "gematria_rollup_view", "rebuild_gematria_rollups"]
