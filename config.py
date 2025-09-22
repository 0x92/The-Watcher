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


def _default_redis_url() -> str:
    configured = _get_env("REDIS_URL")
    if configured:
        return configured
    host = _resolve_service_host("redis", "localhost")
    return f"redis://{host}:6379/0"


class Config:
    SECRET_KEY = _get_env("SECRET_KEY", "change-me")
    DATABASE_URL = _get_env("DATABASE_URL")
    OPENSEARCH_HOST = _default_opensearch_host()
    REDIS_URL = _default_redis_url()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _get_bool_env("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = _get_env("SESSION_COOKIE_SAMESITE", "Lax")
