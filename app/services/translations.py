from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict

from flask import current_app, g

from pathlib import Path

_DEFAULT_LOCALE = "en"
_SUPPORTED_LOCALES = ("de", "en")
_TRANSLATION_DIR = "translations"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _catalog_path(locale: str) -> Path | None:
    candidates = []
    if current_app:
        candidates.append(Path(current_app.root_path))
    candidates.append(_PROJECT_ROOT)
    candidates.append(Path(os.getcwd()))
    seen: set[Path] = set()
    for base in candidates:
        base = base.resolve()
        if base in seen:
            continue
        seen.add(base)
        path = base / _TRANSLATION_DIR / f"{locale}.json"
        if path.exists():
            return path
    return None


@lru_cache(maxsize=len(_SUPPORTED_LOCALES))
def _load_catalog(locale: str) -> Dict[str, str]:
    locale = locale if locale in _SUPPORTED_LOCALES else _DEFAULT_LOCALE
    path = _catalog_path(locale)
    if path is None and locale != _DEFAULT_LOCALE:
        path = _catalog_path(_DEFAULT_LOCALE)
        locale = _DEFAULT_LOCALE
    if path is None:
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    return {str(key): str(value) for key, value in data.items()}


def get_locale() -> str:
    return getattr(g, "ui_locale", _DEFAULT_LOCALE)


def set_locale(locale: str | None) -> None:
    candidate = (locale or "").split("-", 1)[0].lower()
    g.ui_locale = candidate if candidate in _SUPPORTED_LOCALES else _DEFAULT_LOCALE


def translate(key: str, *, locale: str | None = None, default: str | None = None) -> str:
    active_locale = locale or get_locale()
    catalog = _load_catalog(active_locale)
    if key in catalog:
        return catalog[key]
    fallback_catalog = _load_catalog(_DEFAULT_LOCALE)
    if key in fallback_catalog:
        return fallback_catalog[key]
    return default or key


__all__ = ["translate", "set_locale", "get_locale"]
