import os
from typing import Optional


def _get_bool_env(name: str, default: bool = False) -> bool:
    """Return a boolean configuration value based on an environment variable."""

    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read an environment variable returning ``default`` when unset or empty."""

    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value


class Config:
    SECRET_KEY = _get_env("SECRET_KEY", "change-me")
    DATABASE_URL = _get_env("DATABASE_URL")
    OPENSEARCH_HOST = _get_env("OPENSEARCH_HOST", "http://localhost:9200")
    REDIS_URL = _get_env("REDIS_URL", "redis://localhost:6379/0")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _get_bool_env("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = _get_env("SESSION_COOKIE_SAMESITE", "Lax")
