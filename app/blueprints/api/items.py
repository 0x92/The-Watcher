from __future__ import annotations

from collections import defaultdict

from datetime import datetime, timezone
from typing import Optional, Sequence

from dateutil import parser as date_parser
from flask import current_app, request
from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Gematria, Item as ItemModel, ItemTag, Source, Tag


class ItemTagDTO(BaseModel):
    label: str
    weight: float | None = None


class Item(BaseModel):
    id: int
    source: str | None = None
    title: str | None = None
    url: str | None = None
    fetched_at: datetime | None = None
    published_at: datetime | None = None
    lang: str | None = None
    author: str | None = None
    gematria: dict[str, int] = Field(default_factory=dict)
    tags: list[ItemTagDTO] = Field(default_factory=list)


class ItemsResponse(BaseModel):
    items: list[Item] = Field(default_factory=list)
    meta: dict[str, object] = Field(default_factory=dict)


def parse_sources(value: Optional[str]) -> Optional[list[str]]:
    if not value:
        return None
    values = [segment.strip() for segment in value.split(",") if segment.strip()]
    return values or None


def parse_limit(raw: Optional[int]) -> int:
    limit = raw or 50
    return max(1, min(limit, 200))


def parse_since(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = date_parser.isoparse(value)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise ValueError("Ungltiger since-Parameter. Erwartet ISO-8601-Zeitstempel.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _collect_gematria(session: Session, item_ids: Sequence[int]) -> dict[int, dict[str, int]]:
    gematria_map: dict[int, dict[str, int]] = defaultdict(dict)
    if not item_ids:
        return gematria_map
    stmt: Select = select(Gematria.item_id, Gematria.scheme, Gematria.value).where(Gematria.item_id.in_(item_ids))
    for item_id, scheme, value in session.execute(stmt):
        if scheme:
            gematria_map[int(item_id)][str(scheme)] = int(value)
    return gematria_map


def _collect_tags(session: Session, item_ids: Sequence[int]) -> dict[int, list[ItemTagDTO]]:
    tag_map: dict[int, list[ItemTagDTO]] = defaultdict(list)
    if not item_ids:
        return tag_map
    stmt: Select = (
        select(ItemTag.item_id, Tag.label, ItemTag.weight)
        .join(Tag, ItemTag.tag_id == Tag.id)
        .where(ItemTag.item_id.in_(item_ids))
    )
    for item_id, label, weight in session.execute(stmt):
        tag_map[int(item_id)].append(
            ItemTagDTO(label=str(label), weight=float(weight) if weight is not None else None)
        )
    return tag_map


def fetch_items(
    session: Session,
    *,
    limit: int,
    sources: Optional[Sequence[str]] = None,
    since: Optional[datetime] = None,
) -> ItemsResponse:
    stmt: Select = (
        select(ItemModel, Source.name.label("source_name"))
        .join(Source, ItemModel.source_id == Source.id)
        .order_by(ItemModel.fetched_at.desc(), ItemModel.id.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(ItemModel.fetched_at >= since)
    if sources:
        stmt = stmt.where(Source.name.in_(sources))

    rows = session.execute(stmt).all()
    results: list[tuple[ItemModel, str | None]] = []
    item_ids: list[int] = []
    for row in rows:
        item: ItemModel = row[0]
        source_name: str | None = row[1]
        results.append((item, source_name))
        item_ids.append(int(item.id))

    gematria_map = _collect_gematria(session, item_ids)
    tag_map = _collect_tags(session, item_ids)

    items: list[Item] = []
    for model, source_name in results:
        items.append(
            Item(
                id=int(model.id),
                source=source_name,
                title=model.title,
                url=model.url,
                fetched_at=model.fetched_at,
                published_at=model.published_at,
                lang=model.lang,
                author=model.author,
                gematria=gematria_map.get(int(model.id), {}),
                tags=tag_map.get(int(model.id), []),
            )
        )

    latest_fetched_at = max((item.fetched_at for item in items if item.fetched_at), default=None)
    meta: dict[str, object] = {
        "count": len(items),
        "limit": limit,
        "sources": sorted({item.source for item in items if item.source}),
    }
    if since is not None:
        meta["since"] = since
    if latest_fetched_at is not None:
        meta["latest_fetched_at"] = latest_fetched_at

    return ItemsResponse(items=items, meta=meta)


def serialize_items_response(response: ItemsResponse) -> dict:
    payload = response.model_dump()
    for item in payload.get("items", []):
        fetched_at = item.get("fetched_at")
        if isinstance(fetched_at, datetime):
            item["fetched_at"] = fetched_at.isoformat()
        published_at = item.get("published_at")
        if isinstance(published_at, datetime):
            item["published_at"] = published_at.isoformat()
    meta = payload.get("meta")
    if isinstance(meta, dict):
        latest = meta.get("latest_fetched_at")
        if isinstance(latest, datetime):
            meta["latest_fetched_at"] = latest.isoformat()
        since = meta.get("since")
        if isinstance(since, datetime):
            meta["since"] = since.isoformat()
    return payload


def get_items() -> tuple[dict, int]:
    limit = parse_limit(request.args.get("limit", type=int))
    sources_param = request.args.get("source") or request.args.get("sources")
    sources = parse_sources(sources_param)
    since_raw = request.args.get("since")
    try:
        since = parse_since(since_raw)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    db_url = current_app.config.get("DATABASE_URL") or current_app.config.get("SQLALCHEMY_DATABASE_URI")
    session = get_session(db_url)
    try:
        response = fetch_items(session, limit=limit, sources=sources, since=since)
    finally:
        session.close()

    payload = serialize_items_response(response)
    return payload, 200


__all__ = [
    "Item",
    "ItemTagDTO",
    "ItemsResponse",
    "fetch_items",
    "get_items",
    "parse_limit",
    "parse_since",
    "parse_sources",
    "serialize_items_response",
]
