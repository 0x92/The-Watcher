# New Features Backlog

## 1. Real-Time Relationship Graph Explorer
- Vision: Zeige Zusammenhaenge zwischen Quellen, Items, Tags, Alerts und Gematria-Werten als interaktives Netzwerk, um Muster und Cluster sofort sichtbar zu machen.
- Impact: Analysten erkennen neue Storylines und Alert-Haeufungen schneller; erleichtert Root-Cause-Analysen.
- Offene Fragen: Welche Schwellenwerte fuer Edge-Gewichte? Wie viele Knoten gleichzeitig rendern?
- Tasks fuer Codex:
  - [x] Backend: Neuer Endpoint `/api/graph` in `app/blueprints/api` der ein JSON mit Knoten (Sources, Tags, Alerts) und Kanten (gemeinsame Items, Gematria-Treffer) liefert.
  - [x] Service: Aggregations-Helper `build_graph(session)` in `app/services/analytics/graph.py` (neu) der Daten aus den Modellen `Source`, `Item`, `Gematria`, `Alert`, `Event` zieht.
  - [x] Frontend: Vue- oder Vanilla-JS-Modul unter `app/static/js/graph.js`, das Cytoscape nutzt, Filter (Zeitfenster, Rolle) anbietet und Auto-Refresh liefert.
  - [x] UI: Update `app/templates/ui/graph.html` um Filter-Controls, Legende und Export-Button (PNG/JSON) einzubauen.
  - [x] Tests: API-Response Snapshot-Test (`tests/test_api_graph.py`) und Service-Unit-Test mit Fake-Daten.

## 2. KI-gestuetzte Pattern-Discovery Pipeline
- Vision: Nutze Embeddings + Clustering, um thematische Muster und Anomalien in Echtzeit zu markieren.
- Impact: Verbesserte Alert-Qualitaet, automatische Entdeckung neuer Themen, Ranking fuer Analysten.
- Offene Fragen: Sentence-Transformers lokal betreiben oder ueber API? Wie oft Re-Training?
- Tasks fuer Codex:
  - [x] Dependencies: Optionales Extra-Requirements-File `requirements-ml.txt` (sentence-transformers, scikit-learn) + Lazy-Import in `app/services/nlp`.
  - [x] Service: Modul `app/services/nlp/patterns.py` mit Funktionen `embed_items(items)` und `cluster_embeddings(...)`.
  - [x] Task: Scheduler-Job `discover_patterns` in `app/tasks/ingest.py` oder eigenem Modul, der neue Items batchweise analysiert und Ergebnisse in Tabelle `patterns` (neue Migration) speichert.
  - [x] API/UI: Endpoint `/api/patterns/latest` + neue Seite `app/templates/ui/patterns.html` mit Topics-Liste, Keyphrases, Anomaly-Scores.
  - [x] Eval: CLI-Skript `scripts/eval_patterns.py` zum manuellen Review + pytest mit Fake-Embeddings.

## 3. Adaptive Heatmap & Timeline Dashboard
- Vision: Kombiniere Heatmap (Quelle x Zeit) mit Timeline-Marker fuer Alerts, Highlight von Peaks, Drilldown per Klick.
- Impact: Spotte zeitliche Muster und Korrelationen zwischen Quellen, Alerts und Gematria-Werten.
- Offene Fragen: Benoetigte Granularitaet (5 min, 1 h)? Welche Aggregationen vorkalkulieren?
- Tasks fuer Codex:
  - [x] Aggregator: Service `app/services/analytics/heatmap.py` der Buckets per SQL/Session liefert; optional Materialized View Migration.
  - [x] API: Neues Blueprint-Route `/api/analytics/heatmap` mit Query-Parametern `interval`, `source`, `value_min`.
  - [x] Frontend: Erweiterung von `app/templates/ui/heatmap.html` + JS unter `app/static/js/heatmap.js` (ECharts) fuer kombinierte Heatmap + Timeline + Hover-Details.
  - [x] Websocket/Server-Sent-Events fuer Near-Real-Time Updates (Blueprint `app/blueprints/ui` via `/stream/analytics/heatmap`).
  - [x] Tests: Integrationstest fuer API (`tests/test_api_heatmap.py`) + Service-Unit-Test (`tests/services/test_heatmap_analytics.py`).

## 4. Alert Rule Builder UI
- Vision: No-Code Editor, um Alert-Regeln als YAML zu erstellen und zu testen.
- Impact: Ermoeglicht Analysten Alerts ohne Entwickler; reduziert Fehlkonfigurationen.
- Offene Fragen: Validierung live oder per Backend? Draft-Status speichern?
- Tasks fuer Codex:
  - [ ] Backend: CRUD-API `/api/alerts` erweitern (GET/POST/PUT/PATCH) mit Schema-Validation ueber Pydantic Models.
  - [ ] Frontend: Neues Template `app/templates/ui/alert_builder.html` + React-lite oder Stimulus Controller fuer Form Wizard (Quellenwahl, Gematria-Filter, Zeitfenster).
  - [ ] YAML Preview: Live-Rendering per JS (Monaco Editor) + Backend-Validation Endpoint `/api/alerts/validate`.
  - [ ] Permissions: Rolle `analyst` darf Drafts anlegen, `admin` finalisiert (Update `app/security.py`).
  - [ ] Tests: API Contract Tests mit `pytest` + Cypress/Playwright Szenarien fuer UI-Fluss.

## 5. Polished UI Theme & Design System
- Vision: Modernisiere die Oberflaeche mit einem konsistenten Design-System, Dark/Light-Theme, responsiven Komponenten.
- Impact: Bessere Usability, geringere kognitive Last, mehr Akzeptanz bei Stakeholdern.
- Offene Fragen: CSS-Framework (Tailwind, DaisyUI, Chakra) oder Custom? Brand-Guidelines?
- Tasks fuer Codex:
  - [x] Build-Pipeline: Einfuehrung von Vite oder esbuild fuer bundling von CSS/JS (neues `package.json`, Scripts, optional Docker-Stage).
  - [x] Styles: Refaktor `app/static/css` zu modularen Komponenten (Buttons, Cards, Panels) + Utility-Klassen.
  - [x] Layout: Update `app/templates/base.html` mit Navigationsleiste, Breadcrumbs, Toasts, Theme-Toggle.
  - [x] Accessibility: ARIA-Labels, Tastatur-Navigation fuer alle neuen Komponenten, Lighthouse-Audit-Hinweise.
  - [ ] Visual Regression: Storybook oder Chromatic Setup dokumentieren; fallback automatischer Screenshot-Test Workflow.

