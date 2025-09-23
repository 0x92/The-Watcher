-- This script is idempotent and can be executed multiple times safely.

-- Ensure the default schema exists and is active for the session. This avoids
-- "no schema has been selected to create in" errors when the search_path is
-- cleared by managed database providers or client configuration.
CREATE SCHEMA IF NOT EXISTS public;
SET search_path TO public;

CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    endpoint TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    interval_sec INTEGER DEFAULT 0,
    auth_json JSONB,
    filters_json JSONB,
    last_run_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    url TEXT NOT NULL,
    title TEXT,
    author VARCHAR(255),
    lang VARCHAR(8),
    dedupe_hash VARCHAR(64),
    raw_json JSONB,
    CONSTRAINT uq_items_url UNIQUE (url)
);

CREATE INDEX IF NOT EXISTS ix_item_published_at ON items (published_at);
CREATE INDEX IF NOT EXISTS ix_item_dedupe_hash ON items (dedupe_hash);

CREATE TABLE IF NOT EXISTS gematria (
    item_id INTEGER NOT NULL REFERENCES items(id),
    scheme VARCHAR(50) NOT NULL,
    value INTEGER NOT NULL,
    token_count INTEGER,
    normalized_title TEXT,
    PRIMARY KEY (item_id, scheme)
);

CREATE INDEX IF NOT EXISTS ix_gematria_value ON gematria (value);
CREATE INDEX IF NOT EXISTS ix_gematria_scheme ON gematria (scheme);

CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    label VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id INTEGER NOT NULL REFERENCES items(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    weight DOUBLE PRECISION DEFAULT 1.0,
    PRIMARY KEY (item_id, tag_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    rule_yaml TEXT NOT NULL,
    last_eval_at TIMESTAMP,
    notify_json JSONB,
    severity INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alerts(id),
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload_json JSONB,
    severity INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value_json JSONB
);

CREATE TABLE IF NOT EXISTS patterns (
    id SERIAL PRIMARY KEY,
    label VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    top_terms JSONB,
    anomaly_score DOUBLE PRECISION,
    item_ids JSONB,
    meta JSONB
);
