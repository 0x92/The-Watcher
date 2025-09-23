#!/bin/sh
set -e

if [ -n "${DATABASE_URL:-}" ]; then
    echo "Applying database schema from database-schema.sql..."
    python scripts/apply_schema.py
else
    echo "DATABASE_URL not set; skipping schema initialization."
fi

echo "Starting service: $*"
exec "$@"
