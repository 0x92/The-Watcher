# Verbesserungs-Backlog

## UI/UX Verbesserungen
- [ ] Konsolidierte Filterleiste mit gespeicherten Suchprofilen im Dashboard und Crawler-Admin.
- [ ] Dark-/Light-Theme synchronisieren und Optionsdialog für Schriftgröße & Kontrast anbieten.
- [ ] Interaktive Rollup-Charts (Sparkline + Tooltip) in `frontend/modules/analytics.js` ergänzen.
- [ ] Mehrsprachige UI-Labels in `app/templates` zentralisieren und Übersetzungsdatei erstellen.
- [ ] Accessibility-Audit durchführen (Tab-Reihenfolge, ARIA-Rollen, Screenreader-Tests dokumentieren).

## Backend, Daten & Infrastruktur
- [ ] Rollup-Inkrementals (statt Full-Scan) über Delta-Batches in `gematria_rollups` implementieren.
- [ ] Redis-Konfiguration hardenen (TLS, Auth, Namespaces) und Monitoring-Alerts hinzufügen.
- [ ] Async Fetcher in `app/services/crawlers.py` vorbereiten (httpx + Timeout/Retry pro Feed).
- [ ] Kontextbasierte Rate-Limits in `app/__init__.py` nach Benutzerrolle differenzieren.
- [ ] Backpressure & Queue-Metriken für Scheduler (`scheduler_app.py`) nach Prometheus exportieren.

## Neue Features & Experimente
- [ ] Abweichungs-Alerts (z.B. ungewöhnliche Gematria-Spitzen) via `app/services/alerts` modellieren.
- [ ] Ähnliche Headlines clustern und im Analytics-Dashboard als Drilldown anzeigen.
- [ ] Auto-Discovery-Scoring mit ML/Heuristik (Domain-Vertrauen, Frequenz, Nutzerfeedback) erweitern.
- [ ] Export/Share-Funktionen für Analytics-Reports (CSV/JSON, Webhook).
- [ ] Mobile-optimierte Ansicht (responsive Breakpoints) für Stream & Dashboard implementieren.
