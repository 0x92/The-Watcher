# The Watcher

The Watcher is a modular news and social media observability platform built around a Flask web
application and a lightweight Python scheduler. It ingests RSS/Atom feeds (and other endpoints in the
future), calculates gematria metrics, evaluates alert rules, and exposes dashboards, APIs, and
Prometheus metrics for downstream automation.

## Project overview

* **Web application** – Flask blueprints provide the UI, public APIs, authentication, and an admin
  surface.
* **Background processing** – A threaded Python scheduler fetches sources, computes gematria values,
  evaluates alerts, and periodically discovers NLP-based patterns.
* **Persistence** – PostgreSQL (or SQLite for local development) stores sources, items, alerts,
  events, patterns, and worker settings. Optional OpenSearch integration is prepared for full-text
  and aggregation use cases.
* **Frontend assets** – A small Vite project in `frontend/` compiles JavaScript and CSS bundles that
  are served from `app/static/dist`.
* **Observability** – Structured JSON logging, Prometheus metrics, and health/readiness endpoints are
  available for both web and worker processes.

## Repository structure

```
app/                Flask application package
  blueprints/       UI, API, auth, and admin blueprints
  models/           SQLAlchemy models (Source, Item, Gematria, Tag, Alert, Event, Pattern, Setting, User)
  services/         Business logic for ingestion, analytics, alerts, search, NLP, and worker control
  tasks/            Background job implementations
  templates/        Jinja templates for the HTML dashboards
  static/           Pre-built assets served by Flask
scheduler_app.py    Threaded scheduler configuration and job registry
config.py           Base configuration resolved from environment variables
scripts/            Utility scripts (seed sources, inspect patterns)
frontend/           Vite project for JavaScript and CSS modules
migrations/         Alembic database migrations
Makefile            Common development and deployment helpers
  docker-compose.yml  Local container stack (web, scheduler, nginx, postgres, opensearch)
```

## Requirements

* Python 3.11+ (tested with the toolchain in `requirements.txt`).
* Node.js 20+ and npm for building the Vite frontend bundles.
* PostgreSQL and (optionally) OpenSearch for a complete stack.
* Docker Compose ≥ 2.5 is recommended for local orchestration.
* Optional machine learning extras for pattern discovery:
  ```bash
  pip install -r requirements-ml.txt
  ```

## Configuration

1. Copy `.env.example` to `.env` and adjust the values.
2. Important environment variables:
   * `FLASK_ENV` – `development` or `production`.
   * `SECRET_KEY` – secret used for session signing.
   * `DATABASE_URL` – PostgreSQL DSN (e.g. `postgresql+psycopg2://...`) or `sqlite:///app.db`.
   * `OPENSEARCH_HOST` – URL of the OpenSearch cluster (Compose exposes `http://opensearch:9200`).
   * `SCHEDULER_MAX_WORKERS` – number of concurrent background job threads (default: 4).
   * `SENTRY_DSN` – optional error reporting for Flask and scheduler processes.
3. The Flask app auto-populates secure cookie defaults and provides a development secret if none is
   configured.

## Running with Docker Compose

1. Ensure `.env` is present (see above).
2. Build and start the stack:
   ```bash
   docker compose up --build
   # or
   make up
   ```
3. Apply migrations inside the web container:
   ```bash
   docker compose run --rm web alembic upgrade head
   ```
4. Seed demo data (sample sources and an alert):
   ```bash
   docker compose run --rm web python scripts/seed_sources.py
   ```
5. The UI and API are served via Nginx on [http://localhost](http://localhost). The Flask service
   itself listens on port 5000. PostgreSQL and OpenSearch are exposed on their standard ports for
   debugging, and pgAdmin is available on [http://localhost:5050](http://localhost:5050) with the
   default credentials `admin@example.com` / `admin` (adjust these in `docker-compose.yml` or your
   `.env`).
6. Optional: initialize the OpenSearch index from a Python shell using
   `app.services.search.create_items_index`.

## Local development without Docker

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
2. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Install optional ML helpers for pattern discovery as needed.
3. Install frontend dependencies and build the asset bundle when templates change:
   ```bash
   npm install
   npm run build
   # npm run dev can be used for a hot-reload Vite development server
   ```
4. Configure `.env` with `DATABASE_URL=sqlite:///app.db` (or point to PostgreSQL).
5. Run database migrations and seed data:
   ```bash
   alembic upgrade head
   python scripts/seed_sources.py
   ```
6. Start the Flask development server:
   ```bash
   flask --app wsgi run --debug
   # or: python wsgi.py
   ```
7. Start the background scheduler in a separate terminal:
   ```bash
   python scheduler_app.py
   ```

## Background jobs and data flow

* **Sources** – Configured `Source` rows describe endpoints, polling intervals, and optional
  authentication. RSS/Atom feeds are fetched via `app.services.ingest.fetch`, with fallbacks for
  HTTP errors and bundled sample data.
* **Ingestion tasks** – `run_source` and `run_due_sources` fetch feeds, deduplicate items, persist
  `Item` records, and immediately compute gematria metrics.
* **Gematria** – `compute_gematria_for_item` persists an `ordinal` scheme value for each item using
  the pluggable mappings in `app/services/gematria`.
* **Alerts** – `evaluate_alerts` reads YAML rules from the `Alert` table, counts matching items over
  rolling windows, and stores triggered `Event` rows.
* **Pattern discovery** – `discover_patterns` embeds recent items with SentenceTransformers (or a
  deterministic hash fallback), clusters them, and stores representative `Pattern` rows for the UI.
* **Scheduler configuration** – `scheduler_app.py` registers recurring jobs that ping the worker,
  scrape due sources every minute, evaluate alerts, and refresh patterns every 15 minutes.
* **Worker settings** – Toggled through the admin API (`/api/admin/worker-settings`) and persisted in
  the `Setting` table to allow pausing scraping or adjusting source limits.
* **OpenSearch indexing** – A placeholder task (`index_item_to_opensearch`) and the helper module in
  `app/services/search` provide the index mapping when full-text indexing is required.

## User interface and APIs

### UI routes

* `/` – high-level overview.
* `/stream` – live stream dashboard fed by Server-Sent Events from `/stream/live`.
* `/heatmap` – heatmap and timeline dashboard using the `/api/analytics/heatmap` endpoint and SSE
  stream `/stream/analytics/heatmap`.
* `/graph` – entity graph dashboard backed by `/api/graph`.
* `/alerts` – alert list and status view.
* `/patterns` – explorer for the latest discovered patterns.
* `/admin` – entry point for administrative tooling (requires an admin session).

### Public APIs

* `GET /api/health` – status probe used by readiness checks.
* `GET /api/items` – paginated, filterable item listing (query, source, language, gematria filters,
  time ranges, paging).
* `GET /api/graph` – returns nodes/edges linking sources, tags, and alerts; supports window and role
  filters.
* `GET /api/patterns/latest` – latest pattern clusters.
* `GET /api/analytics/heatmap` – aggregated ingestion counts and alert timeline metadata.
* `GET /metrics` – Prometheus scrape target (HTTP counters/latency, scheduler metrics).
* `GET /health` and `GET /ready` – simple liveness/readiness checks for container orchestration.

### Admin and authentication endpoints

* `POST /auth/login`, `POST /auth/logout` – session management using the in-memory demo user store in
  `app/security.py`.
* `GET/PUT /api/admin/worker-settings` – inspect or update scraping configuration (admin role).
* `GET /api/admin/workers` – Scheduler overview (online status, registered jobs).
* `POST /api/admin/workers/<worker>/control` – start/stop/restart the scheduler or individual jobs.
* `GET/POST/PUT/DELETE /api/admin/sources` – CRUD API for ingestion sources.
* `GET /admin/panel` – authenticated admin probe.

Rate limiting is enforced via Flask-Limiter (10 requests per minute for the API blueprints), CSRF
protection is enabled for HTML forms and exempted where JSON APIs need programmatic access, and demo
credentials are provided for quick evaluation.

## Data storage and search

* SQLAlchemy models define the relational schema and are managed via Alembic migrations in
  `migrations/`.
* Items capture source metadata, timestamps, language tags, and gematria values (stored in the
  `Gematria` table).
* Tags (`Tag`/`ItemTag`) and patterns (`Pattern`) support richer analytics and visualisations.
* Alerts and events persist rule definitions and trigger history.
* Worker settings (`Setting`) store scrape configuration that survives restarts.
* `app/services/search/index.py` exposes an `items` index mapping tailored for OpenSearch (keyword
  metadata, text fields, gematria objects) and a `create_items_index` helper to bootstrap the index.

## Observability and monitoring

* `/metrics` exposes Prometheus counters and histograms for HTTP traffic and scheduler job durations.
* The scheduler emits queue depth and job timing metrics via the Prometheus client in `scheduler_app.py`.
* Structured logging is configured in `app/logging.py` for both web and worker processes; logs are
  JSON-formatted for easy aggregation.
* Sentry can be enabled for both Flask and the scheduler by setting `SENTRY_DSN`.
* Health checks: `/health` (liveness) and `/ready` (readiness) return HTTP 200 when the service is
  up.

## Testing and quality

* Run the full test suite:
  ```bash
  pytest
  # or
  make test
  ```
* Linting and formatting:
  ```bash
  pre-commit run --all-files
  # or individually
  ruff check .
  black .
  mypy
  ```
* The repository includes extensive unit tests for models, services, API endpoints, scheduler jobs, and
  seed scripts under `tests/`.

## Helpful commands and scripts

* `make install` – install Python dependencies.
* `make up` / `make down` – start or stop the Docker Compose stack.
* `make migrate` – run Alembic migrations inside the web container.
* `make seed-rss` – execute the RSS seed script inside the container.
* `make logs service=worker` – follow logs for a specific Compose service.
* `scripts/seed_sources.py` – populate demo sources and a sample alert in any environment.
* `scripts/eval_patterns.py` – inspect stored pattern clusters from the command line.

## Demo accounts

The bundled in-memory user store provides three roles for testing (`app/security.py`):

| Role    | Email                 | Password    |
| ------- | --------------------- | ----------- |
| admin   | `admin@example.com`   | `adminpass` |
| analyst | `analyst@example.com` | `analystpass` |
| viewer  | `viewer@example.com`  | `viewerpass` |

## License

Released under the MIT License. See [`LICENSE`](LICENSE) for details.
