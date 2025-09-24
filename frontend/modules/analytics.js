const ANALYTICS_ENDPOINT = "/api/analytics/gematria";

function formatNumber(value, options = {}) {
  if (value === null || value === undefined) {
    return "-";
  }
  const formatter = Intl.NumberFormat("de-DE", options);
  return formatter.format(value);
}

function updateStatus(element, message, state = "idle") {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.dataset.state = state;
  element.hidden = !message;
}

function clearChildren(node) {
  while (node && node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

export function initAnalytics() {
  const root = document.querySelector("[data-analytics-root]");
  if (!root) {
    return;
  }

  const status = root.querySelector("[data-analytics-status]");
  const windowSelect = root.querySelector("[data-analytics-window]");
  const schemeSelect = root.querySelector("[data-analytics-scheme]");
  const rankingSelect = root.querySelector("[data-analytics-ranking]");
  const refreshButton = root.querySelector("[data-analytics-refresh]");

  const summaryCards = {
    total: root.querySelector('[data-analytic-card="total"] .stat-card__value'),
    totalMeta: root.querySelector('[data-analytic-card="total"] .stat-card__meta'),
    extrema: root.querySelector('[data-analytic-card="extrema"] .stat-card__value'),
    extremaMeta: root.querySelector('[data-analytic-card="extrema"] .stat-card__meta'),
    sources: root.querySelector('[data-analytic-card="sources"] .stat-card__value'),
    sourcesMeta: root.querySelector('[data-analytic-card="sources"] .stat-card__meta'),
    corr: root.querySelector('[data-analytic-card="correlation"] .stat-card__value'),
    corrMeta: root.querySelector('[data-analytic-card="correlation"] .stat-card__meta'),
  };

  const topList = root.querySelector("[data-analytics-top-list]");
  const sourcesTableBody = root.querySelector("[data-analytics-source-table] tbody");
  const trendList = root.querySelector("[data-analytics-trend-list]");

  let currentSchemes = [];

  async function load({ refresh = false } = {}) {
    const params = new URLSearchParams();
    const windowValue = windowSelect?.value || "24";
    params.set("window", windowValue);
    if (schemeSelect?.value) {
      params.set("scheme", schemeSelect.value);
    }
    if (rankingSelect?.value) {
      params.set("ranking", rankingSelect.value);
    }
    if (refresh) {
      params.set("refresh", "1");
    }

    updateStatus(status, "Lade Analytics...", "loading");
    try {
      const response = await fetch(`${ANALYTICS_ENDPOINT}?${params.toString()}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Fehler (${response.status})`);
      }
      const payload = await response.json();
      applyMetadata(payload.meta || {});
      renderSummary(payload);
      renderTopValues(payload.top_values || []);
      renderSources(payload.source_breakdown || []);
      renderTrend(payload.trend || []);
      updateStatus(status, "Erfolgreich aktualisiert", "success");
    } catch (err) {
      updateStatus(status, err.message || "Unbekannter Fehler", "error");
      renderSummary();
      renderTopValues([]);
      renderSources([]);
      renderTrend([]);
    }
  }

  function applyMetadata(meta) {
    if (!schemeSelect || !meta.available_schemes) {
      return;
    }
    if (currentSchemes.join(",") !== meta.available_schemes.join(",")) {
      currentSchemes = meta.available_schemes;
      clearChildren(schemeSelect);
      currentSchemes.forEach((scheme) => {
        const option = document.createElement("option");
        option.value = scheme;
        option.textContent = scheme;
        schemeSelect.appendChild(option);
      });
    }
    const currentScheme = meta.scheme || schemeSelect.value;
    if (currentScheme && schemeSelect.value !== currentScheme) {
      schemeSelect.value = currentScheme;
    }
    if (meta.window_hours && windowSelect) {
      windowSelect.value = String(meta.window_hours);
    }
    if (meta.ranking && rankingSelect) {
      rankingSelect.value = meta.ranking;
    }
  }

  function renderSummary(payload = {}) {
    const summary = payload.summary || {};
    if (summaryCards.total) {
      summaryCards.total.textContent = formatNumber(summary.total_items || 0);
    }
    if (summaryCards.totalMeta) {
      const avg = summary.avg ? formatNumber(summary.avg, { maximumFractionDigits: 2 }) : "-";
      summaryCards.totalMeta.textContent = `Summe ${formatNumber(summary.sum || 0)} · Ø ${avg}`;
    }
    if (summaryCards.extrema) {
      const min = summary.min !== null && summary.min !== undefined ? summary.min : "-";
      const max = summary.max !== null && summary.max !== undefined ? summary.max : "-";
      summaryCards.extrema.textContent = `${min} – ${max}`;
    }
    if (summaryCards.extremaMeta) {
      const perc = summary.percentiles || {};
      summaryCards.extremaMeta.textContent = `Median ${perc.p50 ?? "-"} · P90 ${perc.p90 ?? "-"} · P99 ${perc.p99 ?? "-"}`;
    }
    if (summaryCards.sources) {
      summaryCards.sources.textContent = `${formatNumber(summary.unique_sources || 0)}`;
    }
    if (summaryCards.sourcesMeta) {
      summaryCards.sourcesMeta.textContent = `Fenster ${payload.window_hours || windowSelect?.value || 24}h`;
    }
    if (summaryCards.corr) {
      const corr = payload.correlations || {};
      const titleCorr = corr.value_vs_title_length ?? "-";
      const priorityCorr = corr.value_vs_source_priority ?? "-";
      summaryCards.corr.textContent = `${priorityCorr}`;
      if (summaryCards.corrMeta) {
        summaryCards.corrMeta.textContent = `Priorität: ${priorityCorr} · Titel: ${titleCorr}`;
      }
    }
  }

  function renderTopValues(entries) {
    if (!topList) {
      return;
    }
    clearChildren(topList);
    if (!entries.length) {
      const li = document.createElement("li");
      li.className = "placeholder";
      li.textContent = "Keine Werte im Zeitraum";
      topList.appendChild(li);
      return;
    }
    entries.forEach((entry) => {
      const li = document.createElement("li");
      const header = document.createElement("div");
      header.className = "insight-headline";
      header.textContent = `Wert ${entry.value}`;
      const meta = document.createElement("small");
      meta.textContent = `${formatNumber(entry.count)} Treffer · Anteil ${(entry.share * 100).toFixed(2)}%`;
      li.appendChild(header);
      li.appendChild(meta);
      if (entry.samples && entry.samples.length) {
        const list = document.createElement("ul");
        list.className = "sample-list";
        entry.samples.forEach((sample) => {
          const item = document.createElement("li");
          item.textContent = sample.title || "(ohne Titel)";
          if (sample.source) {
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.textContent = sample.source;
            item.appendChild(badge);
          }
          list.appendChild(item);
        });
        li.appendChild(list);
      }
      topList.appendChild(li);
    });
  }

  function renderSources(entries) {
    if (!sourcesTableBody) {
      return;
    }
    clearChildren(sourcesTableBody);
    if (!entries.length) {
      const row = document.createElement("tr");
      row.className = "placeholder";
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.textContent = "Keine Quellen im Zeitraum";
      row.appendChild(cell);
      sourcesTableBody.appendChild(row);
      return;
    }
    entries.forEach((entry) => {
      const row = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = entry.name;
      const count = document.createElement("td");
      count.textContent = formatNumber(entry.count);
      const avg = document.createElement("td");
      avg.textContent = formatNumber(entry.avg, { maximumFractionDigits: 2 });
      const priority = document.createElement("td");
      priority.textContent = entry.priority !== null && entry.priority !== undefined ? String(entry.priority) : "-";
      row.appendChild(name);
      row.appendChild(count);
      row.appendChild(avg);
      row.appendChild(priority);
      sourcesTableBody.appendChild(row);
    });
  }

  function renderTrend(entries) {
    if (!trendList) {
      return;
    }
    clearChildren(trendList);
    if (!entries.length) {
      const li = document.createElement("li");
      li.className = "placeholder";
      li.textContent = "Keine Trenddaten verfügbar";
      trendList.appendChild(li);
      return;
    }
    entries.forEach((entry) => {
      const li = document.createElement("li");
      const title = document.createElement("div");
      title.className = "insight-headline";
      title.textContent = `${entry.bucket_start} → ${entry.bucket_end}`;
      const meta = document.createElement("small");
      meta.textContent = `${formatNumber(entry.count)} Items · Ø ${formatNumber(entry.avg, { maximumFractionDigits: 2 })}`;
      li.appendChild(title);
      li.appendChild(meta);
      trendList.appendChild(li);
    });
  }

  const handlers = [windowSelect, schemeSelect, rankingSelect];
  handlers.forEach((element) => {
    element?.addEventListener("change", () => load());
  });
  refreshButton?.addEventListener("click", () => load({ refresh: true }));

  load({ refresh: true });
}
