# Crawler & Source Management Guide

Dieses Dokument beschreibt die wichtigsten Workflows im neuen Crawler-Control-Center.

## Live-Status & Worker-Steuerung
- Dashboard: `/admin/crawlers` rendert `app/templates/ui/crawlers.html` und streamt Daten per SSE (`/api/crawlers/stream`).
- Zusammenfassung: Stat-Karten zeigen aktive Quellen, Run-KPIs, durchschnittliche Laufzeiten sowie Auto-Discovery-Metriken.
- Worker bedienen: Die Worker-Liste nutzt `/api/crawlers/<worker>/control` zum Starten, Stoppen oder Neustarten einzelner Jobs. Fehlermeldungen werden inline angezeigt.

## Quellen verwalten
- Filter: Suchfeld, Typ- und Statusfilter sowie Tag-Matching greifen auf `/api/crawlers/feeds` mit Query-Parametern (`q`, `type`, `enabled`, `tags`) zu.
- Detail-Sidebar: Klick auf eine Quelle blendet Metriken (letzte Runs, Health-Status, Notizen) ein.
- CRUD: Neue Quellen sendet das Formular an `POST /api/crawlers/feeds`; Updates erfolgen über Inline-Buttons (Enable/Disable, Health-Check, Delete) oder das Bulk-Panel (`/api/crawlers/feeds/bulk`).
- Health Checks: Manuelle Prüfungen nutzen `POST /api/crawlers/feeds/<id>/actions/health-check` und aktualisieren den Status (`healthy`, `degraded`, `manual_check_pending`).

## Auto-Discovery & Priorisierung
- Neue Feeds aus Ingest-Läufen landen deaktiviert mit `auto_discovered=true` und erscheinen separat in der Liste.
- Analysten können Prioritäten, Tags und Notizen setzen, damit Scheduler & Analytics Quellen besser gewichten.

## Konfiguration & Defaults
- Worker-Defaults (Intervall, Max-Läufe) pflegt der Admin über das Settings-Frontend (`/admin/settings`), gespeichert in `worker.scrape` (`app/services/settings.py`).
- Optionaler Redis-Cache wird über `REDIS_URL` in `.env` aktiviert, um Live-Metriken auch nach Worker-Restarts bereitzustellen.
- Beispielkonfigurationen finden sich in `.env.example`; Beispielquellen werden über `scripts/seed_sources.py` mit Priorität, Tags und Notizen bestückt.

## Tests & Qualitätssicherung
- API-Abdeckung: `tests/test_api_crawlers.py` prüft Filter, CRUD, Health-Checks und Worker-Fehlerpfade.
- Service-Logik: Zusätzliche Unit-Tests messen `app/services/crawlers.py` und `app/services/worker_state.py` (In-Memory-Tracker & Statusaggregation).
- Für End-to-End-Prüfungen empfiehlt sich eine Playwright-/Cypress-Suite, die UI-Flows (Filter, Bulk-Aktionen, SSE-Updates) gegen ein Staging-System ausführt.
