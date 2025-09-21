from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Gematria, Item, ItemTag, Source, Tag


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    value: int
    meta: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str
    weight: float
    meta: dict[str, object] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    meta: dict[str, object] = Field(default_factory=dict)


_TIME_SUFFIX = {"m": "minutes", "h": "hours", "d": "days"}


def parse_window(value: str | None) -> Optional[timedelta]:
    if not value:
        return None
    value = value.strip().lower()
    if value == "all":
        return None
    if value.isdigit():
        return timedelta(hours=int(value))
    suffix = value[-1]
    number = value[:-1]
    if suffix in _TIME_SUFFIX and number.isdigit():
        kwargs = {_TIME_SUFFIX[suffix]: int(number)}
        return timedelta(**kwargs)
    raise ValueError(f"Unsupported window '{value}'")


def _time_filter(column, since: Optional[datetime]):
    if since is None:
        return None
    return column >= since


def _coerce_roles(roles: Iterable[str] | None) -> Optional[Set[str]]:
    if roles is None:
        return None
    cleaned = {role.strip().lower() for role in roles if role}
    return cleaned or None


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _parse_alert_conditions(alert: Alert) -> tuple[Optional[str], list[int], list[str]]:
    try:
        data = yaml.safe_load(alert.rule_yaml) or {}
    except yaml.YAMLError:
        return None, [], []
    conditions = data.get("when", {}).get("all", [])
    scheme: Optional[str] = None
    values: list[int] = []
    sources: list[str] = []
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        if "scheme" in condition:
            scheme = condition.get("scheme")
            candidate_values = condition.get("value_in", [])
            if _is_sequence(candidate_values):
                values = [int(v) for v in candidate_values if str(v).lstrip("-").isdigit()]
        if "source_in" in condition:
            candidate_sources = condition.get("source_in", [])
            if _is_sequence(candidate_sources):
                sources = [str(name) for name in candidate_sources]
    return scheme, values, sources


def build_graph(
    session: Session,
    *,
    since: Optional[datetime] = None,
    roles: Iterable[str] | None = None,
    limit_per_type: int = 50,
) -> GraphResponse:
    role_filter = _coerce_roles(roles)
    since_filter = _time_filter(Item.fetched_at, since)
    event_filter = _time_filter(Event.triggered_at, since)

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    sources = session.scalars(select(Source)).all()
    source_name_to_id = {source.name: source.id for source in sources}

    item_counts_stmt: Select = select(Item.source_id, func.count(Item.id)).group_by(Item.source_id)
    if since_filter is not None:
        item_counts_stmt = item_counts_stmt.where(since_filter)
    item_counts: Dict[int, int] = {row[0]: row[1] for row in session.execute(item_counts_stmt)}

    if role_filter is None or "source" in role_filter:
        source_nodes: list[GraphNode] = []
        for source in sources:
            value = item_counts.get(source.id, 0)
            source_nodes.append(
                GraphNode(
                    id=f"source:{source.id}",
                    label=source.name,
                    kind="source",
                    value=value,
                    meta={"type": source.type, "enabled": source.enabled, "interval_sec": source.interval_sec},
                )
            )
        nodes.extend(_limit_nodes(source_nodes, limit_per_type, kind="source"))

    tag_stmt: Select = (
        select(Tag.id, Tag.label, func.count(ItemTag.item_id))
        .join(ItemTag, Tag.id == ItemTag.tag_id)
        .join(Item, Item.id == ItemTag.item_id)
        .group_by(Tag.id)
    )
    if since_filter is not None:
        tag_stmt = tag_stmt.where(since_filter)
    tag_rows = session.execute(tag_stmt).all()
    tag_counts = {row[0]: (row[1], row[2]) for row in tag_rows}

    included_tag_ids: Optional[Set[int]] = None
    if role_filter is None or "tag" in role_filter:
        tag_nodes: list[GraphNode] = []
        for tag_id, (label, count) in tag_counts.items():
            tag_nodes.append(
                GraphNode(
                    id=f"tag:{tag_id}",
                    label=label,
                    kind="tag",
                    value=int(count),
                )
            )
        limited_tags = _limit_nodes(tag_nodes, limit_per_type, kind="tag")
        nodes.extend(limited_tags)
        included_tag_ids = {int(node.id.split(":", 1)[1]) for node in limited_tags}

    source_tag_stmt: Select = (
        select(Item.source_id, ItemTag.tag_id, func.sum(ItemTag.weight))
        .join(ItemTag, Item.id == ItemTag.item_id)
        .group_by(Item.source_id, ItemTag.tag_id)
    )
    if since_filter is not None:
        source_tag_stmt = source_tag_stmt.where(since_filter)
    if included_tag_ids is not None:
        for source_id, tag_id, weight in session.execute(source_tag_stmt):
            if tag_id not in included_tag_ids:
                continue
            weight_value = float(weight)
            if weight_value <= 0:
                continue
            edges.append(
                GraphEdge(
                    source=f"source:{source_id}",
                    target=f"tag:{tag_id}",
                    kind="source_tag",
                    weight=weight_value,
                )
            )

    alerts = session.scalars(select(Alert)).all()

    event_counts_stmt: Select = select(Event.alert_id, func.count(Event.id)).group_by(Event.alert_id)
    if event_filter is not None:
        event_counts_stmt = event_counts_stmt.where(event_filter)
    event_counts = {row[0]: row[1] for row in session.execute(event_counts_stmt)}

    included_alert_ids: Optional[Set[int]] = None
    if role_filter is None or "alert" in role_filter:
        alert_nodes: list[GraphNode] = []
        for alert in alerts:
            value = int(event_counts.get(alert.id, 0))
            alert_nodes.append(
                GraphNode(
                    id=f"alert:{alert.id}",
                    label=alert.name,
                    kind="alert",
                    value=value,
                    meta={"enabled": alert.enabled, "severity": alert.severity},
                )
            )
        limited_alerts = _limit_nodes(alert_nodes, limit_per_type, kind="alert")
        nodes.extend(limited_alerts)
        included_alert_ids = {int(node.id.split(":", 1)[1]) for node in limited_alerts}

    if included_alert_ids:
        for alert in alerts:
            if alert.id not in included_alert_ids:
                continue
            scheme, values, source_names = _parse_alert_conditions(alert)
            if not (scheme and values and source_names):
                continue
            source_ids = [source_name_to_id[name] for name in source_names if name in source_name_to_id]
            if not source_ids:
                continue
            counts_stmt: Select = (
                select(Item.source_id, func.count(Gematria.item_id))
                .select_from(Gematria)
                .join(Item, Gematria.item_id == Item.id)
                .where(Gematria.scheme == scheme)
                .where(Gematria.value.in_(values))
                .where(Item.source_id.in_(source_ids))
                .group_by(Item.source_id)
            )
            if since_filter is not None:
                counts_stmt = counts_stmt.where(since_filter)
            counts = {row[0]: row[1] for row in session.execute(counts_stmt)}
            for source_id, count in counts.items():
                weight_value = float(count)
                if weight_value <= 0:
                    continue
                edges.append(
                    GraphEdge(
                        source=f"source:{source_id}",
                        target=f"alert:{alert.id}",
                        kind="source_alert",
                        weight=weight_value,
                        meta={"scheme": scheme, "values": values},
                    )
                )

    nodes = _limit_per_kind(nodes, limit_per_type)
    active_ids = {node.id for node in nodes}
    filtered_edges = [edge for edge in edges if edge.source in active_ids and edge.target in active_ids]

    return GraphResponse(
        nodes=nodes,
        edges=filtered_edges,
        meta={"since": since.isoformat() if since else None, "roles": sorted(role_filter) if role_filter else None},
    )


def _limit_nodes(nodes: list[GraphNode], limit: int, *, kind: str) -> list[GraphNode]:
    filtered = [node for node in nodes if node.kind == kind]
    if len(filtered) <= limit:
        return filtered
    sorted_nodes = sorted(filtered, key=lambda node: node.value, reverse=True)
    return sorted_nodes[:limit]


def _limit_per_kind(nodes: list[GraphNode], limit: int) -> list[GraphNode]:
    grouped: Dict[str, List[GraphNode]] = defaultdict(list)
    for node in nodes:
        grouped[node.kind].append(node)
    result: list[GraphNode] = []
    for kind, group in grouped.items():
        if len(group) > limit:
            group = sorted(group, key=lambda node: node.value, reverse=True)[:limit]
        result.extend(group)
    return result