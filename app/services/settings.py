"""Utility helpers for application settings management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models import Setting


@dataclass(frozen=True)
class WorkerSettingsDefaults:
    """Container for default worker settings."""

    scrape_enabled: bool = True
    default_interval_minutes: int = 15
    max_sources_per_cycle: int = 10


DEFAULT_WORKER_SETTINGS = WorkerSettingsDefaults()


def _coerce_bool(value: Any, default: bool) -> bool:
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


def _merge_with_defaults(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    defaults = {
        "scrape_enabled": DEFAULT_WORKER_SETTINGS.scrape_enabled,
        "default_interval_minutes": DEFAULT_WORKER_SETTINGS.default_interval_minutes,
        "max_sources_per_cycle": DEFAULT_WORKER_SETTINGS.max_sources_per_cycle,
    }
    if not raw:
        return defaults

    merged = defaults.copy()
    if "scrape_enabled" in raw:
        merged["scrape_enabled"] = _coerce_bool(
            raw["scrape_enabled"], DEFAULT_WORKER_SETTINGS.scrape_enabled
        )
    if "default_interval_minutes" in raw:
        merged["default_interval_minutes"] = _coerce_int(
            raw["default_interval_minutes"],
            DEFAULT_WORKER_SETTINGS.default_interval_minutes,
            minimum=1,
        )
    if "max_sources_per_cycle" in raw:
        merged["max_sources_per_cycle"] = _coerce_int(
            raw["max_sources_per_cycle"],
            DEFAULT_WORKER_SETTINGS.max_sources_per_cycle,
            minimum=0,
        )
    return merged


def get_worker_settings(session: Session) -> Dict[str, Any]:
    """Return worker scraping settings merged with defaults."""

    setting = session.get(Setting, "worker.scrape")
    data = setting.value_json if setting and isinstance(setting.value_json, dict) else None
    return _merge_with_defaults(data)


def update_worker_settings(session: Session, values: Dict[str, Any]) -> Dict[str, Any]:
    """Persist worker settings and return the sanitized payload."""

    merged = get_worker_settings(session)
    if "scrape_enabled" in values:
        merged["scrape_enabled"] = _coerce_bool(
            values["scrape_enabled"], merged["scrape_enabled"]
        )
    if "default_interval_minutes" in values:
        merged["default_interval_minutes"] = _coerce_int(
            values["default_interval_minutes"],
            merged["default_interval_minutes"],
            minimum=1,
        )
    if "max_sources_per_cycle" in values:
        merged["max_sources_per_cycle"] = _coerce_int(
            values["max_sources_per_cycle"],
            merged["max_sources_per_cycle"],
            minimum=0,
        )

    session.merge(Setting(key="worker.scrape", value_json=merged))
    session.commit()
    return merged


__all__ = ["DEFAULT_WORKER_SETTINGS", "get_worker_settings", "update_worker_settings"]

