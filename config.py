import os
import socket
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


def _resolve_service_host(service: str, fallback: str) -> str:
    """Return ``service`` when resolvable otherwise ``fallback``.

    Docker Compose provides DNS entries that match the service name. When the
    lookup fails we gracefully fall back to the host used for local
    development.
    """

    try:
        socket.gethostbyname(service)
    except OSError:
        return fallback
    return service


def _default_opensearch_host() -> str:
    configured = _get_env("OPENSEARCH_HOST")
    if configured:
        return configured
    host = _resolve_service_host("opensearch", "localhost")
    return f"http://{host}:9200"


def _get_int_env(name: str, default: int) -> int:
    value = _get_env(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class Config:
    SECRET_KEY = _get_env("SECRET_KEY", "change-me")
    DATABASE_URL = _get_env("DATABASE_URL")
    OPENSEARCH_HOST = _default_opensearch_host()
    SCHEDULER_MAX_WORKERS = _get_int_env("SCHEDULER_MAX_WORKERS", 4)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _get_bool_env("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = _get_env("SESSION_COOKIE_SAMESITE", "Lax")
