from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict

from flask import current_app, g

_DEFAULT_LOCALE = "de"
_SUPPORTED_LOCALES = ("de", "en")
_TRANSLATION_DIR = "translations"


@lru_cache(maxsize=len(_SUPPORTED_LOCALES))
def _load_catalog(locale: str) -> Dict[str, str]:
    locale = locale if locale in _SUPPORTED_LOCALES else _DEFAULT_LOCALE
    base_path = current_app.root_path if current_app else os.getcwd()
    path = os.path.join(base_path, _TRANSLATION_DIR, f"{locale}.json")
    if not os.path.exists(path):
        locale = _DEFAULT_LOCALE
        path = os.path.join(base_path, _TRANSLATION_DIR, f"{locale}.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    return {str(key): str(value) for key, value in data.items()}


def get_locale() -> str:
    return getattr(g, "ui_locale", _DEFAULT_LOCALE)


def set_locale(locale: str) -> None:
    g.ui_locale = locale if locale in _SUPPORTED_LOCALES else _DEFAULT_LOCALE


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
