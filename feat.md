# Gematria Crawler Overhaul Concept

## Phase 1 - Crawler Core & Logging
- [ ] Entkopple den bisherigen Scheduler in `scheduler_app.py`/`celery_app.py` und fuehre ein Worker-Registry-Modul ein, das alle laufenden Crawler-Threads mit UUID, Ziel-Feed und Status haelt.
- [ ] Lege neue DB-Tabellen `crawler_runs` (Heartbeat, Fehlerzaehler, letztes Item, Latenz) und `crawler_events` (Warnungen/Recoveries) via Alembic-Migration an; spiegle Kerninfos parallel in Redis/In-Memory fuer Live-Ansicht.
- [ ] Implementiere Health-/Online-Check pro Feed (HTTP HEAD/FETCH + Parser-Validierung) vor jedem Pull; markiere Feeds bei wiederholten Fehlern automatisch als `degraded`.
- [ ] Binde Auto-Retry & Backoff-Strategie fuer defekte Feeds ein (z.B. exponential backoff + Max-Recoveries) und schreibe Metriken in Prometheus/Statsd falls vorhanden.
- [ ] Erstelle ein zentrales Gematria-Modul `app/services/gematria/ciphers.py` mit den gelieferten Cipher-Definitionen (English, Simple, Unknown, Pythagoras, Jewish, Prime, Reverse Satanic, Clock, Reverse Clock, System9) inkl. Tests.
- [ ] Erweitere den Ingest-Pipeline-Flow: pro Headline alle Cipher-Werte berechnen, in Tabelle `gematria_values` (Item-ID, Cipher-Key, Wert) abspeichern und fuer Analytics indizieren.
- [ ] Fuege Auto-Discovery Hooks ein (z.B. Sitemap/Link-Parsing, OPML-Import); persistiere vorgeschlagene Feeds in `discovered_sources` mit Confidence-Score.

## Phase 2 - Crawler Core & Logging (Implementation)
- [ ] Registriere alle Crawler-Threads automatisch ueber `app/services/worker_state.py`: Heartbeat, Statuswechsel, Graceful Shutdown und TTL-Aufraeumjobs.
- [ ] Schreibe Laufberichte in `crawler_runs` und Stoerungen in `crawler_events` aus `celery_app.py`/`app/services/crawlers.py`; ergaenze Batch-Commit und Retention-Jobs.
- [ ] Spiegle aktuelle Worker- und Feed-Metriken parallel in Redis/In-Memory Cache inkl. TTL, damit Live-Streams/SSE stabil laufen.
- [ ] Orchestriere Health-Checks mit HTTP- und Parser-Validierung; mappe Ergebnis auf Status (`healthy`, `degraded`, `offline`) und triggere Auto-Recovery/Disable.
- [ ] Verknuepfe Gematria-Berechnung (`app/services/gematria/ciphers.py`) mit dem Ingest-Flow, persistiere Werte in `gematria_values` und indexiere fuer Analytics.
- [ ] Ergaenze Observability: strukturierte Logs, Metrics (Prom/StatsD) sowie Unit-/Integrationstests fuer Registry, Health-Checks und Gematria-Persistenz.

## Phase 3 - Worker & Source Management UI/API
- [ ] Baue API-Endpunkte `/api/crawlers` (Liste, Details, Aktionen) und `/api/crawlers/feeds` (Health, Statistiken, Auto-Discovery Queue) mit Role-Based Access.
- [ ] Implementiere eine Admin-UI-Seite `app/templates/ui/crawlers.html` + Frontend-Store (Vue/React) fuer Thread-Overview (Status, Durchsatz, letzter Run, Fehlertrend) mit Live-Updates per Websocket/SSE.
- [ ] Erstelle Source-Management-Module: Listen/Filtern, neuen Feed anlegen, bestehenden Feed deaktivieren/loeschen, manuelle Health-Pruefung triggern, Auto-Discovery-Vorschlaege annehmen.
- [ ] Fuege Bulk-Actions & Notizen fuer Quellen hinzu (z.B. Tags, Prioritaet), damit Analysten Quellen kuratieren koennen.
- [ ] Schreibe End-to-End- und API-Tests (pytest + Playwright/Cypress) fuer Source-CRUD, Health-Check-Flow und Worker-Ansicht.

## Phase 4 - Mathematische Analytics & Dashboard
- [ ] Implementiere Service `app/services/analytics/gematria_rollups.py`, der Aggregationen pro Zeitfenster (24h, 48h, 7d) ueber Headlines, Summen, Top-Werte, Korrelationen liefert.
- [ ] Stelle REST/GraphQL-Endpoints `/api/analytics/gematria` bereit mit Parametern fuer Zeitfenster, Cipher, Quelle, Ranking-Strategien.
- [ ] Aktualisiere Dashboard-UI (`app/templates/ui/dashboard.html`) mit Widgets fuer Gematria-Verteilung, Outlier Alerts, Feed-Vergleich und Drilldown auf Item-Ebene.
- [ ] Erweitere vorhandene analytische Tools (z.B. Alerts, Pattern-Discovery) um Gematria-Daten (Filter, Highlighting, Export).
- [ ] Dokumentiere neue Metriken und Analyse-Workflows in `README.md`/`docs/analytics.md` und fuege Monitoring/Alerting-Checks fuer Ausfall der Aggregationen hinzu.

## Phase 5 - Erweiterte Auto-Discovery (Optional)
- [ ] Trainiere/konfiguriere heuristische oder ML-basierte Bewertung fuer vorgeschlagene Feeds (z.B. basierend auf Domain, Update-Frequenz, historischen Treffern).
- [ ] Implementiere Workflow fuer Analysten: Vorschlaege prufen, priorisieren, in aktive Quellen uebernehmen; Logging der Entscheidungen in `discovery_reviews`.
- [ ] Fuege Scheduler-Task hinzu, der ungenutzte Vorschlaege nach Ablauf archiviert und Feeds mit niedriger Qualitaet zur Nachpruefung markiert.

## Cross-Cutting
- [ ] Update `.env.example`/Konfigs (Crawler-Thread-Count, Heartbeat-Intervalle, Auto-Discovery-Toggles, Analytics-Window-Defaults).
- [ ] Erweitere Docker/Docker-Compose-Setup um neue Services (Redis/Queue falls noetig) und stelle sicher, dass Worker-Status + Analytics in allen Umgebungen laufen.
- [ ] Schreibe Migrations-/Rollback-Plan inkl. Backfill-Skripten (`scripts/backfill_gematria.py`, `scripts/migrate_sources.py`).
- [ ] Fuehre Performance-/Load-Tests fuer Crawler + Analytics durch und dokumentiere Ergebnisse/Optimierungen.
