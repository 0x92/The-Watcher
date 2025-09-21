#!/usr/bin/env python
"""CLI helper to inspect recently discovered patterns."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Iterable

from app.db import get_session
from app.models import Pattern
from app.services.analytics.graph import parse_window


def _format_terms(terms: Iterable[str]) -> str:
    return ", ".join(terms) if terms else "-"


def _format_score(score: float | None) -> str:
    return f"{score:.3f}" if isinstance(score, float) else "-"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect stored pattern clusters")
    parser.add_argument("--window", default="24h", help="Zeitfenster z. B. 24h, 7d, all")
    parser.add_argument("--limit", type=int, default=10, help="Maximale Anzahl an Mustern")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optionaler Datenbank-DSN. Nutzt ansonsten env/Dotenv Konfiguration.",
    )
    args = parser.parse_args()

    try:
        delta = parse_window(args.window)
    except ValueError as exc:
        parser.error(str(exc))

    since = datetime.utcnow() - delta if delta else None

    session = get_session(args.database_url)
    try:
        query = session.query(Pattern).order_by(Pattern.created_at.desc())
        if since is not None:
            query = query.filter(Pattern.created_at >= since)
        patterns = query.limit(args.limit).all()
    finally:
        session.close()

    if not patterns:
        print("Keine Muster gefunden.")
        return

    for pattern in patterns:
        created = pattern.created_at.isoformat(sep=" ", timespec="seconds")
        print(f"[{pattern.id}] {pattern.label} @ {created}")
        print(f"  Score: {_format_score(pattern.anomaly_score)} | Items: {len(pattern.item_ids or [])}")
        print(f"  Terms: {_format_terms(pattern.top_terms or [])}")
        if pattern.meta:
            print(f"  Meta: {pattern.meta}")
        print()


if __name__ == "__main__":
    main()
