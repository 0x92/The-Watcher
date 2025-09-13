Tasks.md — Gematria Observer (Flask + Celery + OpenSearch) ⌬

Kurzer Sinn & Zweck: Headlines & Social-Feeds einsammeln → Gematria-Werte berechnen → Muster/Verbindungen erkennen → interaktive Dashboards & Alerts.
Modul-Ziele: saubere Services, wiederholbare Deployments, reproduzierbare Analysen, klare Tests & Observability.


---

0) Projekt-Scaffold

[x] Repo initialisieren

[x] LICENSE (MIT), README.md, Tasks.md (diese Datei)

[x] .gitignore (Python, venv, pycache, .env, data/*, .pytest_cache, .mypy_cache)

[x] pyproject.toml (poetry oder hatch) oder requirements.txt

[x] Makefile (Shortcuts, s. unten)


[x] Verzeichnisstruktur

/app
  /blueprints/{ui,api,admin}
  /services/{gematria,ingest,nlp,search,alerts}
  /models
  /tasks
  /templates
  /static/{js,css,img}
/deploy/{nginx.conf,opensearch.json}
/migrations (Alembic)
.env.example
docker-compose.yml
wsgi.py
celery_app.py
config.py

[x] Paketabhängigkeiten festlegen

Flask, gunicorn, Jinja2, Flask-Login, Flask-WTF

SQLAlchemy, Alembic, psycopg2-binary

Celery, redis

requests, feedparser, python-dateutil

opensearch-py

langdetect / fasttext (optional), sentence-transformers (optional)

pydantic, PyYAML, python-dotenv

tests: pytest, pytest-cov, factory_boy

lint: ruff, black, mypy (optional)


[x] Env-Template .env.example

FLASK_ENV=production
SECRET_KEY=change-me
DATABASE_URL=postgresql+psycopg2://gematria:gematria@postgres:5432/gematria
OPENSEARCH_HOST=http://opensearch:9200
REDIS_URL=redis://redis:6379/0
SENTRY_DSN=


Definition of Done (DoD): Alle Dateien existieren, make up startet Container, /health liefert 200.


---

1) Datenmodell (PostgreSQL + Alembic)

[ ] SQLAlchemy-Modelle erstellen:

Source(id, name, type, endpoint, enabled, interval_sec, auth_json, filters_json, last_run_at, created_at)

Item(id, source_id→Source, fetched_at, published_at, url UNIQUE, title, author, lang, dedupe_hash, raw_json)

Gematria(item_id UNIQUE→Item, scheme, value, token_count, normalized_title)

Tag(id, label) + ItemTag(item_id, tag_id, weight)

Alert(id, name, enabled, rule_yaml, last_eval_at, notify_json, severity)

Event(id, alert_id→Alert, triggered_at, payload_json, severity)

User(id, email UNIQUE, role, password_hash, created_at)

Setting(key UNIQUE, value_json)


[ ] Alembic init & Revision: alembic revision --autogenerate -m "init"

[ ] Constraints/Indices

UNIQUE: Item.url, Gematria.item_id

BTREE: Item.published_at, Gematria.value, Gematria.scheme

HASH: Item.dedupe_hash



Akzeptanzkriterien: Migration läuft ohne Fehler, Foreign Keys korrekt, pytest -k models grün.


---

2) OpenSearch-Index & Mapping

[ ] Index items anlegen mit Mapping:

Felder: id (keyword), source (keyword), published_at (date), lang (keyword), title (text, analyzer english), url (keyword),
gematria_values (object per scheme → integer), tags (keyword), author (keyword)


[ ] Shards/Replicas: 1/0 lokal; prod 3/1

[ ] Aggregationen testen: by scheme, value, source, hour_of_day


DoD: make seed-os erzeugt Index, GET /api/search liefert Aggregationen.


---

3) Gematria-Engine (Services)

[ ] Schemes definieren (app/services/gematria/schemes.py)

ordinal, reduction (Pythagorean), reverse, reverse_reduction

optional: ALW/ALB/KFW als JSON-Mapping


[ ] Normalizer (ignore_pattern = r'[^A-Z]', konfigurierbar)

[ ] API

compute_all(text:str, schemes:list[str]) -> dict[str,int]
digital_root(n:int) -> int
factor_signature(n:int) -> dict[int,int]

[ ] Unit-Tests: bekannte Beispiele, Edge Cases (Zahlen, Emojis, Unicode)


DoD: 100% Tests für compute_all, Benchmarks (<0.2ms/Headline avg. lokal).


---

4) Ingestion Pipelines (Celery)

[ ] Celery-App celery_app.py + Beat-Schedule

[ ] RSS/Atom Ingest (app/services/ingest/rss.py)

ETag/If-Modified-Since, Retry/Backoff, dedupe via SHA256(title+url)

Ergebnisspeicher: Postgres Item, Gematria, Indexierung in OS


[ ] News API Adapters (Platzhalter, keys via .env)

[ ] Reddit, Mastodon, YouTube (modulare Adapter, Feature-flagged)

[ ] Tasks

run_source(source_id)

compute_gematria_for_item(item_id)

index_item_to_opensearch(item_id)

evaluate_alerts()


[ ] Beat-Plan: pro Source interval_sec dynamisch


Akzeptanz: make seed-rss fügt 1–2 Feeds hinzu; make run-once zieht Items, berechnet Gematria, indiziert OS.


---

5) REST API (Blueprint api)

[ ] Routen

GET /api/health → {status:"ok"}

GET /api/items (Filter: query, value, scheme, source, from, to, lang, page, size)

GET /api/graph (Param: scheme, value, window) → Kanten zwischen gleichwertigen Items

POST /api/admin/sources (CRUD)

POST /api/admin/alerts (CRUD)

GET /api/aggregations (Buckets by value/source/time)

GET /api/patterns (Top-Spikes, digitale Wurzeln, Sequenzen)


[ ] Schemas (Pydantic) & Fehlerhandling (HTTP 4xx/5xx)

[ ] Pagination (cursor/offset)


DoD: OpenAPI (via flask-openapi3 oder YAML) generiert; pytest -k api grün.


---

6) UI/Dashboard (Blueprint ui)

[ ] Pages

/ Overview: KPIs (Items 24h, Top Werte, Quellen), Sparklines

/stream Live-Feed mit Badges (Scheme/Value/Quelle/Zeit)

/heatmap Wert (x) × Stunde/Wochentag (y) mit Drilldown

/graph Cytoscape.js: Cluster gleichwertiger Headlines (Gewichtung: Zeitnähe/Quellen-Diversity)

/alerts Liste + Events

/admin Quellen/Intervalle, Regl-Editor (YAML)


[ ] Assets

Plotly/ECharts für Charts, Cytoscape für Graph

Tailwind oder minimal CSS


[ ] UX

Filterleiste (Zeit, Quelle, Sprache, Scheme, Wert-Range)

Persistente Filter (Query-Params), Copy-Link



DoD: Man kann via UI: filtern, Heatmap & Graph sehen, Details öffnen.


---

7) Alerts (Rules Engine)

[ ] YAML-Regeln (Parser & Validator)

name: Reuters_93_spike
enabled: true
when:
  all:
    - scheme: ordinal
      value_in: [93]
    - source_in: ["Reuters"]
    - window: { period: "24h", min_count: 3 }
notify:
  - type: email
    to: ["alerts@example.com"]
  - type: webhook
    url: "https://example/hook"
severity: high

[ ] Evaluator (zeitfensterbasierte Zählung via OS Aggregation)

[ ] Notifier (E-Mail, Webhook; spätere Slack/Matrix optional)

[ ] Event-Logging (Postgres Event)


DoD: Manuell auslösendes Test-Item erzeugt Event; E-Mail/Webhook-Call sichtbar.


---

8) Sicherheit & Auth

[ ] RBAC: admin, analyst, viewer

[ ] Auth: Flask-Login (später OAuth Google optional)

[ ] CSRF für Admin-POSTs, sichere Cookie-Flags

[ ] Rate-Limits (Flask-Limiter) für öffentliche Endpunkte

[ ] Robots/ToS beachten (nur erlaubte APIs/Feeds)


DoD: Rollen prüfen; Admin-only Routen geschützt; Security-Header via Nginx.


---

9) Observability & Logs

[ ] Structured Logging (JSON) für Web & Worker

[ ] Prometheus-Metrics (Requests, Task-Duration, Queue-Depth)

[ ] Healthchecks /health, /ready

[ ] Sentry (optional) DSN in .env


DoD: curl /metrics zeigt Counter/Gauges; Task-Laufzeiten sichtbar.


---

10) Deployment (Docker Compose + Nginx)

[ ] docker-compose.yml mit Services:

web (gunicorn), worker, beat, nginx, postgres, opensearch, redis


[ ] Nginx Reverse Proxy (GZip, HSTS optional, caching static)

[ ] Volumes/Backups: Postgres (pgdata), OS (osdata)

[ ] Commands

make up / make down

make logs web|worker

make migrate (alembic upgrade head)

make seed-rss Beispielquellen laden



DoD: Lokales Deployment erreichbar auf https://localhost (oder 80/443 je nach Setup).


---

11) Tests & Qualität

[ ] Pytest Suites: models, gematria, api, alerts, ingest (mit VCR.py für HTTP-Mocks)

[ ] Coverage ≥ 85% Kernmodule (services/gematria, alerts, api)

[ ] Ruff + Black via pre-commit

[ ] Type-Checking (mypy, tolerant)


DoD: make test grün, Lint sauber.


---

12) Beispiel-Seed & Demo

[ ] Seed-Sources: 2–3 RSS (Reuters, AP), 1 Mastodon (public/hashtag), 1 YouTube-Channel

[ ] Seed-Alerts: 1 Regel für Wert 93, Quelle=Reuters

[ ] Demo-Notebook (optional): Query + Plot (repro für Readme GIF)


DoD: Demo-Daten erzeugen sichtbare Heatmap/Graph in UI.


---

13) Risiko & Compliance Checks

[ ] API Terms prüfen (nur zulässige Endpunkte)

[ ] Rate-Limit Guards je Quelle

[ ] PII-Armut sicherstellen (nur Titel & Meta)

[ ] Archivierung (optional S3/Lifecycle)


DoD: Dokumentierte Policy im README.md Abschnitt „Data & Compliance“.


---

14) Makefile (Kommandos)

[ ] Targets anlegen

up: docker compose up -d
down: docker compose down
logs: docker compose logs -f
migrate: docker compose exec web alembic upgrade head
seed-os: python scripts/seed_opensearch.py
seed-rss: python scripts/seed_sources.py
test: pytest -q
lint: ruff check .
fmt: black .



---

15) API-Verträge (Beispiele)

[ ] GET /api/items

{
  "count": 124,
  "items": [{
    "id": "uuid",
    "title": "Market jitters as…",
    "url": "https://…",
    "source": "Reuters",
    "published_at": "2025-09-12T14:05:00Z",
    "gematria": {"ordinal":93,"reduction":39},
    "tags": ["markets","fed"]
  }],
  "buckets": {"by_source":{"Reuters":44}}
}

[ ] GET /api/graph

{"nodes":[{"id":"uuid1","title":"...","value":93}], "edges":[{"from":"uuid1","to":"uuid2","weight":0.8}]}


DoD: Response-Validatoren + Beispiel-JSONs im Repo.


---

16) Erweiterte Analytik (V1+)

[ ] Fourier/Wavelets für Periodizität

[ ] Entropy/Surprisal Scores pro Zeitfenster

[ ] Markov-Übergänge von Werten (A→B)

[ ] Community Detection (Louvain) & Auto-Labels


DoD: Mind. 1 Analyse in /patterns sichtbar, dokumentiert.


---

17) CI (optional, empfohlen)

[ ] GitHub Actions: Lint, Test, Build

[ ] Docker Build & Push (tags: main, release-*)

[ ] Trivy Scan (Image Security)


DoD: Badge im README.


---

18) Dokumentation

[ ] README: Setup, docker compose, Seeds, Demo-URL

[ ] CONFIG.md: Quellen/Intervalle/Rules erklären

[ ] ALERTS.md: YAML-Schema & Beispiele

[ ] SECURITY.md: RBAC, Secrets, Updates

[ ] OPERATIONS.md: Backup/Restore, Rotationen



---

19) Abnahme-Checkliste (MVP)

[ ] 3+ Quellen laufen im Intervall, Items werden gespeichert & indiziert

[ ] Gematria für jedes Item (≥1 Scheme) berechnet

[ ] UI zeigt Stream, Heatmap, Graph (funktioniert mit Filtern)

[ ] 1 Alert-Regel triggert Event + Notification

[ ] Tests ≥ 85% Kern, Lint clean, Healthchecks grün

[ ] Ein-Kommando-Start: make up + make seed-rss + make migrate



---

20) Nächste Schritte (heute startklar)

1. Scaffold & Compose anlegen (Task 0).


2. DB + Alembic + Models (Task 1).


3. OS Index & Mapping (Task 2).


4. Gematria-Engine + Tests (Task 3).


5. RSS-Ingest + Celery-Beat (Task 4).


6. Minimal-API + UI Stream (Task 5 & 6).


7. Heatmap + Graph (Task 6).


8. Erste Alert-Regel (Task 7).




---

Notizen für Codex/Aktionshinweise

„Erzeuge Datei X mit Boilerplate Y“ nur, wenn nicht vorhanden.

Vor jedem größeren Schritt: Tests schreiben/erweitern.

Keine Secrets commiten; .env.example aktuell halten.

Logging: jede Pipeline-Stufe loggt source_id, count_in/out, duration_ms.

