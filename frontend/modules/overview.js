export function initOverview() {
  const statusEl = document.querySelector('[data-overview-status]');
  const metricsRoot = document.querySelector('[data-overview]');
  if (!statusEl || !metricsRoot) {
    return;
  }

  const metricValue = (name) => metricsRoot.querySelector(`[data-metric="${name}"]`);
  const alertList = document.querySelector('[data-overview-alerts]');
  const patternList = document.querySelector('[data-overview-patterns]');

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }

  async function fetchJSON(url) {
    const response = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`Request ${url} fehlgeschlagen (${response.status})`);
    }
    return response.json();
  }

  function updateMetric(name, value) {
    const el = metricValue(name);
    if (el) {
      el.textContent = value;
    }
  }

  function renderAlertList(timeline) {
    if (!alertList) return;
    if (!timeline.length) {
      alertList.innerHTML = '<li>Keine Alerts im Zeitraum.</li>';
      return;
    }
    alertList.innerHTML = timeline
      .slice(-5)
      .reverse()
      .map((entry) => {
        const date = new Date(entry.at).toLocaleString();
        const badge = entry.severity != null ? `<span class="badge">S${entry.severity}</span>` : '';
        return `<li><div>${entry.alert} ${badge}</div><small>${date}</small></li>`;
      })
      .join('');
  }

  function renderPatterns(patterns) {
    if (!patternList) return;
    if (!patterns.length) {
      patternList.innerHTML = '<li>Keine Muster gefunden.</li>';
      return;
    }
    patternList.innerHTML = patterns
      .slice(0, 5)
      .map((pattern) => {
        const score = pattern.anomaly_score != null ? pattern.anomaly_score.toFixed(3) : '-';
        return `<li><div>${pattern.label || 'Muster'}</div><small>Score ${score}</small></li>`;
      })
      .join('');
  }

  async function loadData() {
    try {
      setStatus('loading', 'Aktualisiere Übersicht...');
      const [graph, heatmap, patterns] = await Promise.all([
        fetchJSON('/api/graph?limit=100&window=24h'),
        fetchJSON('/api/analytics/heatmap?interval=24h&value_min=0'),
        fetchJSON('/api/patterns/latest?window=24h&limit=10'),
      ]);

      const sourceCount = new Set((graph.nodes || []).filter((n) => n.kind === 'source').map((n) => n.id)).size;
      updateMetric('sources', sourceCount || 0);
      updateMetric('items', heatmap.meta?.item_count ?? 0);
      updateMetric('alerts', heatmap.meta?.event_count ?? 0);

      const topPattern = (patterns.patterns || [])[0];
      updateMetric('pattern-score', topPattern && topPattern.anomaly_score != null ? topPattern.anomaly_score.toFixed(3) : '-');

      renderAlertList(heatmap.timeline || []);
      renderPatterns(patterns.patterns || []);
      setStatus('idle', 'Live-Daten synchronisiert.');
    } catch (error) {
      console.error('overview load failed', error);
      setStatus('error', error.message || 'Übersicht konnte nicht geladen werden.');
    }
  }

  loadData();
  const interval = setInterval(loadData, 60_000);
  window.addEventListener('beforeunload', () => clearInterval(interval));
}
