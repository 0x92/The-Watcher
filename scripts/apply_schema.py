from __future__ import annotations

import os
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError


RETRY_ATTEMPTS = 10
RETRY_DELAY = 2


def _load_statements(schema_path: Path) -> list[str]:
    sql = schema_path.read_text(encoding="utf-8")
    statements: list[str] = []
    buffer: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).rstrip(";\n ")
            statements.append(statement)
            buffer = []

    if buffer:
        statements.append("\n".join(buffer).rstrip(";\n "))

    return statements


def apply_schema() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set; skipping schema initialization.")
        return

    if database_url.startswith("sqlite"):
        print("DATABASE_URL points to SQLite; skipping schema initialization.")
        return

    schema_path = Path(__file__).resolve().parent.parent / "database-schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    statements = _load_statements(schema_path)
    if not statements:
        print("No SQL statements found in schema file; nothing to execute.")
        return

    engine = create_engine(database_url, future=True)

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with engine.begin() as connection:
                for statement in statements:
                    connection.exec_driver_sql(statement)
            print("Database schema ensured via database-schema.sql.")
            break
        except OperationalError as exc:  # pragma: no cover - requires failing DB
            if attempt == RETRY_ATTEMPTS:
                raise
            print(
                "Database not ready yet (attempt %s/%s): %s" %
                (attempt, RETRY_ATTEMPTS, exc)
            )
            time.sleep(RETRY_DELAY)


def main() -> None:
    apply_schema()


if __name__ == "__main__":
    main()
