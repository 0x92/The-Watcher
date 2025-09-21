# The Watcher

The Watcher ist eine modulare Plattform fuer Echtzeit-Monitoring und Analyse von Nachrichten- und Social-Media-Feeds. Sie sammelt Quellen, berechnet Gematria-Metriken, wertet Regeln aus und stellt die Ergebnisse in einer Weboberflaeche sowie ueber APIs bereit.

## Inhalt
- Ueberblick
- Systemarchitektur
- Voraussetzungen
- Konfiguration
- Schnellstart mit Docker Compose
- Lokale Entwicklung ohne Docker
- Datenfluss & Funktionen
- Benutzeroberflaeche & API
- Observability & Monitoring
- Tests & Qualitaetssicherung
- Nuetzliche Kommandos
- Standardkonten
- Lizenz

## Ueberblick
The Watcher kombiniert eine Flask-Webanwendung mit Hintergrundprozessen auf Basis von Celery. Quellen wie RSS-Feeds werden regelmaessig eingelesen, normalisiert und persistiert. Zu jedem Eintrag werden Gematria-Werte berechnet, Alerts ausgewertet und die Daten fuer Suche und Visualisierung aufbereitet.

## Systemarchitektur
- Flask-App (`wsgi.py`) mit Blueprints fuer UI, Authentifizierung und Admin-Endpunkte.
- SQLAlchemy-Modelle mit Alembic-Migrationen fuer PostgreSQL (optional SQLite lokal).
- Celery Worker und Beat fuer Ingestion, Gematria-Berechnung, Alert-Evaluierung und kuenftige Indexierungsjobs (`app/tasks`).
- Redis als Message-Broker, PostgreSQL als Primaerdatenbank, OpenSearch fuer Volltextsuche.
- Prometheus-Metriken unter `/metrics`, Health-/Readiness-Probes unter `/health` und `/ready`.
- JSON-Logging (`app/logging.py`) und optionale Sentry-Integration (`SENTRY_DSN`).
- Reverse-Proxy-Setup mit Nginx (`deploy/nginx.conf`).
- Vite-basierter Theme- und Asset-Build (`frontend/`, `app/static/dist`).

## Voraussetzungen
- Docker und Docker Compose >= 2.5 fuer das Container-Setup.
- Alternativ: Python >= 3.11, Pip und ein lokaler PostgreSQL- oder SQLite-Zugang.
- Fuer Frontend-Assets: Node.js >= 20 und npm (Vite-Build).
- Optional: Zugriff auf einen OpenSearch-Cluster (lokal via Compose enthalten).

## Konfiguration
1. Kopiere `.env.example` nach `.env` und passe die Werte an.
2. Wichtige Variablen:
   - `FLASK_ENV`: `development` oder `production`.
   - `SECRET_KEY`: sichere Zeichenkette fuer Sessions.
   - `DATABASE_URL`: z. B. `postgresql+psycopg2://gematria:gematria@postgres:5432/gematria` oder lokal `sqlite:///app.db`.
   - `OPENSEARCH_HOST`: Standard `http://opensearch:9200`.
   - `REDIS_URL`: Standard `redis://redis:6379/0`.
   - `SENTRY_DSN`: optional fuer Fehlertracking.

Optional: Fuer KI-basierte Mustererkennung koennen lokal die Zusatzpakete mit `pip install -r requirements-ml.txt` installiert werden (Sentence-Transformers, scikit-learn). Das Docker-Image installiert diese Bibliotheken bereits automatisch.

## Schnellstart mit Docker Compose
1. `.env` anlegen (siehe oben).
2. Sicherstellen, dass eine passende `Dockerfile` im Projekt liegt (Compose baut `web`, `worker` und `beat` aus dem lokalen Kontext).
3. Container starten:
   ```bash
   docker compose up --build
   ```
   oder mit Makefile: `make up`.
4. Datenbank migrieren:
   ```bash
   docker compose run --rm web alembic upgrade head
   ```
5. Beispieldaten einspielen (Seed fuer Quellen und Alerts):
   ```bash
   docker compose run --rm web python scripts/seed_sources.py
   ```
6. Optional: OpenSearch-Index initialisieren (z. B. via Python-Shell und `app.services.search.create_items_index`).
7. Die Anwendung ist ueber `http://localhost` erreichbar. Der API-Backend-Service lauscht standardmaessig auf Port 5000, Nginx publiziert Port 80.

## Lokale Entwicklung ohne Docker
1. Virtuelle Umgebung erstellen und aktivieren:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # Linux/macOS
   ```
2. Backend-Abhaengigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```
3. Frontend-Assets bauen (nur nach Aenderungen in `frontend/` erforderlich):
   ```bash
   npm install
   npm run build
   ```
4. `.env` anlegen und `DATABASE_URL=sqlite:///app.db` setzen (oder eigenen Postgres verwenden).
5. Datenbank vorbereiten: `alembic upgrade head`.
6. Seed-Skript ausfuehren: `python scripts/seed_sources.py`.
7. Entwicklungsserver starten: `flask --app wsgi run --debug` oder `python wsgi.py`.
8. Celery-Worker starten: `celery -A celery_app.celery worker --loglevel=INFO`.
9. Optional Celery-Beat fuer periodische Tasks: `celery -A celery_app.celery beat --loglevel=INFO`.

## Datenfluss & Funktionen
- Quellen (`app.models.Source`) definieren Intervall, Endpunkt und Authentifizierung.
- Der Task `run_source` zieht Feeds (via `app.services.ingest.fetch`), dedupliziert Eintraege und speichert `Item`-Datensaetze.
- `compute_gematria_for_item` berechnet Gematria-Werte (`app.services.gematria`) und legt sie im Modell `Gematria` ab.
- Alerts werden ueber YAML-Regeln in `Alert.rule_yaml` definiert. `evaluate_alerts` prueft Bedingungen (z. B. Werte, Quellen, Zeitfenster) und erstellt `Event`-Eintraege.
- Indexierung in OpenSearch ist vorbereitet (`app/services/search`), ein konkreter Task kann ueber `index_item_to_opensearch` ergaenzt werden.
- Die Pattern-Pipeline (`discover_patterns`) bettet neue Items, clustert sie via `app/services/nlp/patterns.py` und persistiert Ergebnisse in `patterns` (API `/api/patterns/latest`, UI `/patterns`).

## Benutzeroberflaeche & API
- UI-Blueprint (`app/blueprints/ui`) liefert HTML-Seiten fuer Ueberblick, Stream, Heatmap, Graph und Alerts.
- Kopfbereich bietet Navigationsleiste, Breadcrumbs und Theme-Toggle (Light/Dark).
- Heatmap Dashboard: `/heatmap` nutzt `/api/analytics/heatmap` und den SSE-Stream `/stream/analytics/heatmap` fuer kombinierte Heatmap & Timeline.
- Authentifizierungsendpunkte (`/auth/login`, `/auth/logout`) erwarten JSON (`{"email", "password"}`).
- Administrativer Check unter `/admin/panel` erfordert eingeloggten Nutzer mit Rolle `admin`.
- Offentliche Health-Checks: `/health` und `/ready`.
- Pattern-Explorer: /patterns nutzt den Endpoint /api/patterns/latest fuer KI-basierte Cluster.

## Observability & Monitoring
- Prometheus-kompatible Metriken unter `/metrics` (HTTP-Requests, Latenzen, Celery-Metriken).
- Logging im JSON-Format (stdout). Geeignet fuer zentrale Log-Aggregation.
- Optionaler Sentry-Hook via `SENTRY_DSN` fuer Web- und Worker-Prozesse.

## Tests & Qualitaetssicherung
- Tests ausfuehren: `pytest` oder `make test`.
- Code-Qualitaet: `pre-commit run --all-files`, `ruff`, `black`, `mypy` (Konfiguration vorhanden).
- Coverage-Bericht: `pytest --cov`.

## Nuetzliche Kommandos
- `make install`: installiert Python-Abhaengigkeiten.
- `make up` / `make down`: startet bzw. stoppt das Compose-Setup.
- `make migrate`: fuehrt Alembic-Migrationen innerhalb des Web-Containers aus.
- `make seed-rss`: fuehrt das Seed-Skript im Container aus.
- `make logs service=worker`: folgt den Logs eines Dienstes.
- `docker build -t the-watcher .`: baut das Produktionsimage mit Frontend-Assets.
- `npm run build`: erzeugt das gebuendelte Design-System unter `app/static/dist`.
- `npm run dev`: optionaler Vite-Dev-Server fuer schnelle UI-Iterationen.
- `python scripts/eval_patterns.py --window 24h --limit 10`: zeigt erkannte Muster im Terminal.

## Standardkonten
Die Demo verwendet In-Memory-Benutzer (siehe `app/security.py`):
- Admin: `admin@example.com` / `adminpass`
- Analyst: `analyst@example.com` / `analystpass`
- Viewer: `viewer@example.com` / `viewerpass`

## Lizenz
Veroeffentlicht unter der MIT-Lizenz (siehe `LICENSE`).














