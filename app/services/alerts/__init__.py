"""Alert evaluation service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import yaml
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Gematria, Item, Source


def _parse_period(period: str) -> timedelta:
    """Convert a shorthand period string like ``"24h"`` to ``timedelta``."""

    if period.endswith("h"):
        return timedelta(hours=int(period[:-1]))
    if period.endswith("d"):
        return timedelta(days=int(period[:-1]))
    raise ValueError(f"Unsupported period '{period}'")


def _extract_rule(alert: Alert) -> dict:
    """Parse the YAML rule stored on an alert."""

    try:
        return yaml.safe_load(alert.rule_yaml) or {}
    except yaml.YAMLError:
        return {}


def evaluate_alerts(session: Session) -> int:
    """Evaluate enabled alerts and create events for matches.

    Currently supports a minimal rule format::

        when:
          all:
            - scheme: ordinal
              value_in: [93]
            - source_in: ["Reuters"]
            - window: { period: "24h", min_count: 1 }

    Returns the number of alerts that triggered.
    """

    now = datetime.utcnow()
    triggered = 0

    alerts: Iterable[Alert] = session.scalars(
        select(Alert).where(Alert.enabled.is_(True))
    )

    for alert in alerts:
        rule = _extract_rule(alert)
        conditions = rule.get("when", {}).get("all", [])
        scheme = None
        value_in: list[int] = []
        source_in: list[str] = []
        period = "24h"
        min_count = 1
        for cond in conditions:
            if "scheme" in cond:
                scheme = cond["scheme"]
                value_in = cond.get("value_in", [])
            if "source_in" in cond:
                source_in = cond["source_in"]
            if "window" in cond:
                win = cond["window"]
                period = win.get("period", period)
                min_count = win.get("min_count", min_count)

        if not (scheme and value_in and source_in):
            continue

        since = now - _parse_period(period)
        stmt: Select[int] = (
            select(func.count())
            .select_from(Gematria)
            .join(Item, Gematria.item_id == Item.id)
            .join(Source, Item.source_id == Source.id)
            .where(Gematria.scheme == scheme)
            .where(Gematria.value.in_(value_in))
            .where(Source.name.in_(source_in))
            .where(Item.fetched_at >= since)
        )
        count = session.scalar(stmt) or 0
        if count >= min_count:
            session.add(Event(alert_id=alert.id, payload_json={"count": count}))
            alert.last_eval_at = now
            triggered += 1

    if triggered:
        session.commit()
    return triggered


__all__ = ["evaluate_alerts"]
