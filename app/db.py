from __future__ import annotations

import os
from typing import Dict

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


_ENGINE_CACHE: Dict[str, Engine] = {}
_SESSION_CACHE: Dict[str, sessionmaker] = {}


def _resolve_url(url: str | None) -> str:
    if url:
        return url
    return os.getenv("DATABASE_URL", "sqlite:///app.db")


def get_engine(url: str | None = None) -> Engine:
    resolved = _resolve_url(url)
    engine = _ENGINE_CACHE.get(resolved)
    if engine is None:
        engine = create_engine(resolved)
        _ENGINE_CACHE[resolved] = engine
        _SESSION_CACHE[resolved] = sessionmaker(bind=engine)
    return engine


def get_session(url: str | None = None) -> Session:
    resolved = _resolve_url(url)
    factory = _SESSION_CACHE.get(resolved)
    if factory is None:
        engine = get_engine(resolved)
        factory = _SESSION_CACHE[resolved]
    return factory()