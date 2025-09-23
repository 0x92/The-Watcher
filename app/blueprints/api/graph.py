from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

import os
from flask import current_app, request

from app.db import get_session
from app.services.analytics.graph import GraphResponse, build_graph, parse_window


def _extract_roles() -> Optional[List[str]]:
    roles: List[str] = []
    roles.extend(request.args.getlist("role"))
    roles_param = request.args.get("roles")
    if roles_param:
        roles.extend(value.strip() for value in roles_param.split(","))
    cleaned = [role.lower() for role in roles if role.strip()]
    return cleaned or None


def graph() -> tuple[dict, int]:
    window_param = request.args.get("window")
    try:
        delta = parse_window(window_param)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    since = datetime.utcnow() - delta if delta else None

    limit = request.args.get("limit", type=int)
    if limit is None:
        limit = 50
    limit = max(1, min(limit, 200))

    roles = _extract_roles()

    db_url = os.getenv("DATABASE_URL") or current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")

    session = get_session(db_url)
    try:
        graph_data: GraphResponse = build_graph(
            session,
            since=since,
            roles=roles,
            limit_per_type=limit,
        )
    finally:
        session.close()

    payload = graph_data.model_dump()
    payload["meta"].update({"window": window_param or None, "limit": limit})
    return payload, 200


__all__ = ["graph"]
