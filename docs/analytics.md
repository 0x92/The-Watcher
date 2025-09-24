# Gematria Analytics Dashboard

Dieses Dokument erläutert die neue Auswertungs-Schicht für Gematria-Daten.

## Rollup-Service
- Modul: `app/services/analytics/gematria_rollups.py`
- Aggregiert Headlines je Fenster (`24h`, `48h`, `168h`) und Cipher.
- Kennzahlen: Items, Summe, Ø-Wert, Min/Max, Perzentile, Trends, Quellenverteilung, Korrelationen.
- Persistiert in `gematria_rollups` (Scope = global oder `source:<id>`). Standard-TTL: 15 Minuten (`GEMATRIA_ROLLUP_TTL`).
- `refresh_rollups_job()` aktualisiert Rollups für alle Schemen; Scheduler läuft alle 15 Minuten (`refresh_gematria_rollups`).

## API
- Basis: `/api/analytics`
- `GET /gematria`: Parameter `window` (z.B. `24` oder `24h`), `scheme`, `ranking` (`top|sources|trend`), `source_id`, `refresh=1`.
- `POST /gematria/rebuild`: optional `windows`, `schemes`, `sources` zur manuellen Aktualisierung (nur Admin).
- Antwort enthält aggregierte Daten plus Metadaten (`available_schemes`, `available_windows`).

## Dashboard
- Route: `/analytics` (Rolle: Analyst/Admin).
- Template: `app/templates/ui/dashboard.html`.
- Frontend-Logik: `frontend/modules/analytics.js` lädt API, aktualisiert Stat-Karten, Top-Werte, Quellen-Tabelle und Trendliste.
- CSS-Ergänzungen in `frontend/styles/components.css`.

## Backfill
- Script: `scripts/backfill_gematria.py`
- CLI: `python scripts/backfill_gematria.py --windows 24,48,168 --schemes simple,prime --sources global,12`
- Nutzt `refresh_rollups` und legt Standardwerte an, falls Tabelle leer ist.

## Konfiguration
- Neue Tabelle laut Migration `1d0d8c36f2fd_add_gematria_rollups.py` und Schema `database-schema.sql`.
- Optionale Env-Variablen:
  - `GEMATRIA_ROLLUP_TTL` (Sekunden, Standard 900)
  - `WORKER_*` (bereits vorhanden) für Scheduler.

## Tests
- `tests/services/test_gematria_rollups.py` prüft Aggregation, Perzentile und Persistenz.
- `tests/test_api_analytics.py` validiert Endpoints inkl. Berechtigungen.
- `tests/test_ui.py` deckt neues Dashboard und Rollenrechte ab.

