from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Gematria, Item, Source


@dataclass
class ItemRecord:
    """Representation of an item enriched with display information."""

    id: int
    source: str
    title: str | None
    url: str
    fetched_at: datetime
    published_at: datetime | None
    lang: str | None
    gematria: Dict[str, int] = field(default_factory=dict)


@dataclass
class ItemsPage:
    items: List[ItemRecord]
    total: int
    page: int
    size: int
    has_next: bool
    next_cursor: int | None = None


def _base_statement() -> Select:
    return select(
        Item.id,
        Item.title,
        Item.url,
        Item.lang,
        Item.fetched_at,
        Item.published_at,
        Source.name.label("source"),
    ).join(Source, Source.id == Item.source_id)


def _apply_filters(
    stmt: Select,
    *,
    query: str | None = None,
    sources: Optional[Sequence[str]] = None,
    lang: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    scheme: str | None = None,
    value: int | None = None,
    after_id: int | None = None,
) -> Select:
    if query:
        pattern = f"%{query.lower()}%"
        stmt = stmt.where(func.lower(Item.title).like(pattern))
    if sources:
        stmt = stmt.where(Source.name.in_(list(sources)))
    if lang:
        stmt = stmt.where(Item.lang == lang)
    if since:
        stmt = stmt.where(Item.fetched_at >= since)
    if until:
        stmt = stmt.where(Item.fetched_at <= until)
    if after_id is not None:
        stmt = stmt.where(Item.id > after_id)

    if scheme or value is not None:
        gematria_filter = select(Gematria.item_id).where(Gematria.item_id == Item.id)
        if scheme:
            gematria_filter = gematria_filter.where(Gematria.scheme == scheme)
        if value is not None:
            gematria_filter = gematria_filter.where(Gematria.value == value)
        stmt = stmt.where(gematria_filter.exists())

    return stmt


def _load_gematria(session: Session, item_ids: Iterable[int]) -> Dict[int, Dict[str, int]]:
    ids = list(item_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(Gematria.item_id, Gematria.scheme, Gematria.value).where(Gematria.item_id.in_(ids))
    ).all()
    mapping: Dict[int, Dict[str, int]] = {item_id: {} for item_id in ids}
    for item_id, scheme, value in rows:
        mapping.setdefault(item_id, {})[scheme] = value
    return mapping


def _rows_to_records(session: Session, rows: Sequence) -> List[ItemRecord]:
    item_ids = [row.id for row in rows]
    gematria_map = _load_gematria(session, item_ids)
    records: List[ItemRecord] = []
    for row in rows:
        records.append(
            ItemRecord(
                id=row.id,
                source=row.source,
                title=row.title,
                url=row.url,
                fetched_at=row.fetched_at,
                published_at=row.published_at,
                lang=row.lang,
                gematria=gematria_map.get(row.id, {}),
            )
        )
    return records


def list_items(
    session: Session,
    *,
    page: int = 1,
    size: int = 25,
    query: str | None = None,
    sources: Optional[Sequence[str]] = None,
    lang: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    scheme: str | None = None,
    value: int | None = None,
) -> ItemsPage:
    page = max(1, page)
    size = max(1, min(size, 100))

    stmt = _base_statement()
    stmt = _apply_filters(
        stmt,
        query=query,
        sources=sources,
        lang=lang,
        since=since,
        until=until,
        scheme=scheme,
        value=value,
    )
    stmt = stmt.order_by(Item.fetched_at.desc(), Item.id.desc())
    stmt = stmt.limit(size).offset((page - 1) * size)

    rows = session.execute(stmt).all()
    records = _rows_to_records(session, rows)

    count_stmt = select(func.count()).select_from(Item).join(Source, Source.id == Item.source_id)
    count_stmt = _apply_filters(
        count_stmt,
        query=query,
        sources=sources,
        lang=lang,
        since=since,
        until=until,
        scheme=scheme,
        value=value,
    )
    total = session.execute(count_stmt).scalar_one()
    has_next = page * size < total
    next_cursor = records[-1].id if has_next and records else None

    return ItemsPage(
        items=records,
        total=total,
        page=page,
        size=size,
        has_next=has_next,
        next_cursor=next_cursor,
    )


def fetch_new_items(
    session: Session,
    *,
    after_id: int | None = None,
    limit: int = 20,
    query: str | None = None,
    sources: Optional[Sequence[str]] = None,
    lang: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    scheme: str | None = None,
    value: int | None = None,
) -> List[ItemRecord]:
    limit = max(1, min(limit, 100))
    stmt = _base_statement()
    stmt = _apply_filters(
        stmt,
        query=query,
        sources=sources,
        lang=lang,
        since=since,
        until=until,
        scheme=scheme,
        value=value,
        after_id=after_id,
    )

    if after_id is None:
        stmt = stmt.order_by(Item.fetched_at.desc(), Item.id.desc())
    else:
        stmt = stmt.order_by(Item.id.asc())

    stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()
    return _rows_to_records(session, rows)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        from dateutil import parser

        return parser.isoparse(value)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Ungültiges Datumsformat: {value}") from exc


__all__ = [
    "ItemRecord",
    "ItemsPage",
    "list_items",
    "fetch_new_items",
    "parse_iso_datetime",
]
