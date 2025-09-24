"""Backfill helper for gematria rollup aggregates."""

from __future__ import annotations

import argparse
import os
from typing import Iterable, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

try:  # pragma: no cover - ensure package import works in script context
    from app.models import Base
    from app.services.analytics.gematria_rollups import DEFAULT_WINDOWS, refresh_rollups
    from app.services.gematria.schemes import SCHEME_DEFINITIONS
except ModuleNotFoundError:  # pragma: no cover
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from app.models import Base
    from app.services.analytics.gematria_rollups import DEFAULT_WINDOWS, refresh_rollups
    from app.services.gematria.schemes import SCHEME_DEFINITIONS


SCHEME_KEYS = tuple(SCHEME_DEFINITIONS.keys())


def _session_from_env() -> Session:
    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///app.db"))
    Base.metadata.create_all(engine)
    return Session(engine)


def _parse_windows(raw: Optional[str]) -> Iterable[int]:
    if not raw:
        return DEFAULT_WINDOWS
    windows = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.endswith("h"):
            token = token[:-1]
        try:
            hours = int(token)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid window '{token}'") from exc
        if hours <= 0:
            raise argparse.ArgumentTypeError("Window hours must be positive")
        windows.append(hours)
    return windows or DEFAULT_WINDOWS


def _parse_schemes(raw: Optional[str]) -> Iterable[str]:
    if not raw:
        return SCHEME_KEYS
    schemes = []
    for token in raw.split(","):
        key = token.strip().lower()
        if not key:
            continue
        if key not in SCHEME_DEFINITIONS:
            raise argparse.ArgumentTypeError(f"Unknown scheme '{token}'")
        schemes.append(key)
    return schemes or SCHEME_KEYS


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Backfill gematria rollup aggregates")
    parser.add_argument(
        "--windows",
        help="Comma separated list of window sizes in hours (e.g. 24,48,168)",
    )
    parser.add_argument(
        "--schemes",
        help="Comma separated list of scheme keys (default: all)",
    )
    parser.add_argument(
        "--sources",
        help="Comma separated list of source ids to include (default: global only)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    windows = list(_parse_windows(args.windows))
    schemes = list(_parse_schemes(args.schemes))
    source_ids: list[Optional[int]] = [None]
    if args.sources:
        source_ids = []
        for token in args.sources.split(","):
            token = token.strip()
            if not token:
                continue
            if token.lower() in {"global", "all"}:
                source_ids.append(None)
                continue
            try:
                source_ids.append(int(token))
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"Invalid source id '{token}'") from exc
        if not source_ids:
            source_ids = [None]

    session = _session_from_env()
    try:
        refresh_rollups(
            session,
            schemes=schemes,
            window_hours=windows,
            source_ids=source_ids,
            commit=True,
        )
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    main()
