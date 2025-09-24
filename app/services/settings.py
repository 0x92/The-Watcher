"""Utility helpers for application settings management."""

from __future__ import annotations

import os

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Setting
from app.services.gematria import DEFAULT_ENABLED_SCHEMES, SCHEMES

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)



@dataclass(frozen=True)
class WorkerSettingsDefaults:
    """Container for default worker settings."""

    scrape_enabled: bool = True
    default_interval_minutes: int = 15
    max_sources_per_cycle: int = 10


DEFAULT_WORKER_SETTINGS = WorkerSettingsDefaults(
    scrape_enabled=_env_bool("WORKER_SCRAPE_ENABLED", True),
    default_interval_minutes=_env_int("WORKER_DEFAULT_INTERVAL_MINUTES", 15, minimum=1),
    max_sources_per_cycle=_env_int("WORKER_MAX_SOURCES_PER_CYCLE", 10, minimum=0),
)
WORKER_SETTING_KEY = "worker.scrape"


@dataclass(frozen=True)
class GematriaSettingsDefaults:
    """Default configuration for gematria computation."""

    enabled_schemes: tuple[str, ...] = DEFAULT_ENABLED_SCHEMES
    ignore_pattern: str = r"[^A-Z]"


DEFAULT_GEMATRIA_SETTINGS = GematriaSettingsDefaults()
GEMATRIA_SETTING_KEY = "gematria.settings"


def _ensure_settings_table(session: Session) -> None:
    """Create the settings table on demand when it is missing."""

    bind = session.get_bind()
    if bind is None:
        return
    try:
        Setting.__table__.create(bind=bind, checkfirst=True)
    except SQLAlchemyError:
        session.rollback()
        Setting.__table__.create(bind=bind, checkfirst=True)


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


def _sanitize_scheme_list(values: Iterable[Any]) -> List[str]:
    """Ensure only known scheme identifiers are returned."""

    available = {name.lower(): name for name in SCHEMES.keys()}
    aliases = {
        "sumerian": "english_sumerian",
        "english sumerian": "english_sumerian",
    }
    available.update(aliases)
    sanitized: List[str] = []
    seen = set()
    for value in values:
        if value is None:
            continue
        key = str(value).strip().lower()
        if not key:
            continue
        normalized = available.get(key)
        if not normalized or normalized in seen:
            continue
        sanitized.append(normalized)
        seen.add(normalized)

    if not sanitized:
        sanitized = list(DEFAULT_GEMATRIA_SETTINGS.enabled_schemes)
    return sanitized


def _merge_gematria_defaults(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    defaults = {
        "enabled_schemes": list(DEFAULT_GEMATRIA_SETTINGS.enabled_schemes),
        "ignore_pattern": DEFAULT_GEMATRIA_SETTINGS.ignore_pattern,
    }
    if not raw:
        return defaults

    merged = defaults.copy()
    enabled_raw = raw.get("enabled_schemes")
    if isinstance(enabled_raw, str):
        merged["enabled_schemes"] = _sanitize_scheme_list([enabled_raw])
    elif isinstance(enabled_raw, Iterable):
        merged["enabled_schemes"] = _sanitize_scheme_list(enabled_raw)
    if isinstance(raw.get("ignore_pattern"), str) and raw["ignore_pattern"].strip():
        merged["ignore_pattern"] = raw["ignore_pattern"].strip()
    return merged


def get_worker_settings(session: Session) -> Dict[str, Any]:
    """Return worker scraping settings merged with defaults."""

    _ensure_settings_table(session)
    setting = session.get(Setting, WORKER_SETTING_KEY)
    data = setting.value_json if setting and isinstance(setting.value_json, dict) else None
    return _merge_with_defaults(data)


def update_worker_settings(session: Session, values: Dict[str, Any]) -> Dict[str, Any]:
    """Persist worker settings and return the sanitized payload."""

    _ensure_settings_table(session)
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

    session.merge(Setting(key=WORKER_SETTING_KEY, value_json=merged))
    session.commit()
    return merged


def get_gematria_settings(session: Session) -> Dict[str, Any]:
    """Return gematria settings merged with defaults."""

    _ensure_settings_table(session)
    setting = session.get(Setting, GEMATRIA_SETTING_KEY)
    data = setting.value_json if setting and isinstance(setting.value_json, dict) else None
    return _merge_gematria_defaults(data)


def update_gematria_settings(session: Session, values: Dict[str, Any]) -> Dict[str, Any]:
    """Persist gematria settings and return the sanitized payload."""

    _ensure_settings_table(session)
    merged = get_gematria_settings(session)

    enabled_values = values.get("enabled_schemes")
    if enabled_values is None and "enabled" in values:
        enabled_values = values.get("enabled")
    if enabled_values is not None:
        if isinstance(enabled_values, str):
            iterable = [enabled_values]
        elif isinstance(enabled_values, Iterable):
            iterable = list(enabled_values)
        else:
            iterable = []
        merged["enabled_schemes"] = _sanitize_scheme_list(iterable)

    if "ignore_pattern" in values:
        pattern = values.get("ignore_pattern")
        if isinstance(pattern, str) and pattern.strip():
            merged["ignore_pattern"] = pattern.strip()
        else:
            merged["ignore_pattern"] = DEFAULT_GEMATRIA_SETTINGS.ignore_pattern

    session.merge(Setting(key=GEMATRIA_SETTING_KEY, value_json=merged))
    session.commit()
    return merged


__all__ = [
    "DEFAULT_GEMATRIA_SETTINGS",
    "DEFAULT_WORKER_SETTINGS",
    "GEMATRIA_SETTING_KEY",
    "WORKER_SETTING_KEY",
    "get_gematria_settings",
    "get_worker_settings",
    "update_gematria_settings",
    "update_worker_settings",
]
