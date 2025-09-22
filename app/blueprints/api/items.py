from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import current_app, request
from pydantic import BaseModel, Field

from app.db import get_session
from app.services.items import ItemsPage, list_items, parse_iso_datetime


class ItemDTO(BaseModel):
    id: int
    source: str
    title: str | None = None
    url: str
    lang: str | None = None
    fetched_at: datetime
    published_at: datetime | None = None
    gematria: dict[str, int] = Field(default_factory=dict)


class ItemsMetaDTO(BaseModel):
    page: int
    size: int
    total: int
    has_next: bool
    next_cursor: int | None = None


class ItemsResponse(BaseModel):
    items: list[ItemDTO] = Field(default_factory=list)
    meta: ItemsMetaDTO


def _parse_sources() -> Optional[list[str]]:
    values = [value.strip() for value in request.args.getlist("source") if value.strip()]
    raw = request.args.get("sources")
    if raw:
        values.extend(part.strip() for part in raw.split(",") if part.strip())
    return values or None


def _parse_int_param(name: str, *, default: Optional[int] = None, minimum: Optional[int] = None) -> tuple[Optional[int], Optional[str]]:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None
    try:
        value = int(raw)
    except ValueError:
        return None, f"Parameter '{name}' muss eine Ganzzahl sein."
    if minimum is not None and value < minimum:
        return None, f"Parameter '{name}' muss mindestens {minimum} sein."
    return value, None


def _make_response(page: ItemsPage) -> dict:
    payload = ItemsResponse(
        items=[
            ItemDTO(
                id=item.id,
                source=item.source,
                title=item.title,
                url=item.url,
                lang=item.lang,
                fetched_at=item.fetched_at,
                published_at=item.published_at,
                gematria=item.gematria,
            )
            for item in page.items
        ],
        meta=ItemsMetaDTO(
            page=page.page,
            size=page.size,
            total=page.total,
            has_next=page.has_next,
            next_cursor=page.next_cursor,
        ),
    )
    data = payload.model_dump()
    for entry in data["items"]:
        entry["fetched_at"] = entry["fetched_at"].isoformat()
        if entry["published_at"] is not None:
            entry["published_at"] = entry["published_at"].isoformat()
    return data


def get_items() -> tuple[dict, int]:
    page_value, error = _parse_int_param("page", default=1, minimum=1)
    if error:
        return {"error": error}, 400
    size_value, error = _parse_int_param("size", default=25, minimum=1)
    if error:
        return {"error": error}, 400
    value_param, error = _parse_int_param("value")
    if error:
        return {"error": error}, 400

    query = request.args.get("query")
    lang = request.args.get("lang")
    scheme = request.args.get("scheme")
    sources = _parse_sources()

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
    session = get_session(db_url)
    try:
        page = list_items(
            session,
            page=page_value or 1,
            size=size_value or 25,
            query=query,
            sources=sources,
            lang=lang,
            since=since,
            until=until,
            scheme=scheme,
            value=value_param,
        )
    finally:
        session.close()

    data = _make_response(page)
    return data, 200


__all__ = ["ItemDTO", "ItemsMetaDTO", "ItemsResponse", "get_items"]
