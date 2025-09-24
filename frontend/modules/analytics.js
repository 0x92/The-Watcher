import { createProfileStore } from './profileStore.js';

const ANALYTICS_ENDPOINT = "/api/analytics/gematria";
const PROFILE_STORAGE_KEY = 'watcher:analytics-filters:v1';

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
  const filterForm = root.querySelector("[data-analytics-filter-form]");
  const filterReset = root.querySelector("[data-analytics-filter-reset]");
  const windowSelect = root.querySelector("[data-analytics-window]");
  const schemeSelect = root.querySelector("[data-analytics-scheme]");
  const rankingSelect = root.querySelector("[data-analytics-ranking]");
  const refreshButton = root.querySelector("[data-analytics-refresh]");

  const profileControls = root.querySelector("[data-analytics-profile-controls]");
  const profileSelect = root.querySelector("[data-analytics-profile-select]");
  const profileNameInput = root.querySelector("[data-analytics-profile-name]");
  const profileSaveButton = root.querySelector("[data-analytics-profile-save]");
  const profileUpdateButton = root.querySelector("[data-analytics-profile-update]");
  const profileDeleteButton = root.querySelector("[data-analytics-profile-delete]");
  const savedLabel = profileControls?.dataset.profileSavedLabel || "Saved";
  const deleteConfirm = profileControls?.dataset.profileDeleteConfirm || "Delete profile?";
  const defaultProfileLabel = profileSelect?.dataset.defaultLabel || "";

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

  const profileStore = createProfileStore(PROFILE_STORAGE_KEY);
  let profileData = profileStore.getAll ? profileStore.getAll() : {};

  let currentSchemes = [];
  let currentFilters = captureFilters();

  function captureFilters() {
    return {
      window: windowSelect?.value || "24",
      scheme: schemeSelect?.value || "",
      ranking: rankingSelect?.value || "top",
    };
  }

  function applyFilters(filters = {}) {
    if (windowSelect && filters.window !== undefined) {
      windowSelect.value = String(filters.window);
    }
    if (schemeSelect && filters.scheme !== undefined) {
      schemeSelect.value = filters.scheme;
    }
    if (rankingSelect && filters.ranking !== undefined) {
      rankingSelect.value = filters.ranking;
    }
    currentFilters = captureFilters();
  }

  function populateProfiles(selectedName = "") {
    if (!profileSelect) {
      return;
    }
    const label = defaultProfileLabel || profileSelect.dataset.defaultLabel || "";
    profileSelect.innerHTML = "";
    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = label || "-";
    profileSelect.appendChild(defaultOption);
    Object.keys(profileData || {})
      .sort((a, b) => a.localeCompare(b))
      .forEach((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        if (name === selectedName) {
          option.selected = true;
        }
        profileSelect.appendChild(option);
      });
  }

  profileStore.subscribe?.((next) => {
    profileData = next;
    populateProfiles(profileSelect?.value || "");
  });

  function load({ refresh = false } = {}) {
    currentFilters = captureFilters();
    const params = new URLSearchParams();
    params.set("window", currentFilters.window);
    if (currentFilters.scheme) {
      params.set("scheme", currentFilters.scheme);
    }
    if (currentFilters.ranking) {
      params.set("ranking", currentFilters.ranking);
    }
    if (refresh) {
      params.set("refresh", "1");
    }

    updateStatus(status, status?.dataset.labelLoading || "Lade Analytics...", "loading");
    fetch(`${ANALYTICS_ENDPOINT}?${params.toString()}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then((response) => {
        if (!response.ok) {
          return response.json().then((error) => {
            throw new Error(error.error || `Fehler (${response.status})`);
          });
        }
        return response.json();
      })
      .then((payload) => {
        applyMetadata(payload.meta || {});
        renderSummary(payload);
        renderTopValues(payload.top_values || []);
        renderSources(payload.source_breakdown || []);
        renderTrend(payload.trend || []);
        updateStatus(status, status?.dataset.labelSuccess || "Erfolgreich aktualisiert", "success");
      })
      .catch((error) => {
        updateStatus(status, error.message || status?.dataset.labelError || "Unbekannter Fehler", "error");
        renderSummary();
        renderTopValues([]);
        renderSources([]);
        renderTrend([]);
      });
  }

  function applyMetadata(meta) {
    if (schemeSelect && Array.isArray(meta.available_schemes)) {
      const serialized = meta.available_schemes.join(",");
      if (currentSchemes.join(",") !== serialized) {
        currentSchemes = meta.available_schemes.slice();
        clearChildren(schemeSelect);
        currentSchemes.forEach((scheme) => {
          const option = document.createElement("option");
          option.value = scheme;
          option.textContent = scheme;
          schemeSelect.appendChild(option);
        });
      }
    }
    if (meta.scheme && schemeSelect) {
      schemeSelect.value = meta.scheme;
    }
    if (meta.window_hours && windowSelect) {
      windowSelect.value = String(meta.window_hours);
    }
    if (meta.ranking && rankingSelect) {
      rankingSelect.value = meta.ranking;
    }
    currentFilters = captureFilters();
  }

  function renderSummary(payload = {}) {
    const summary = payload.summary || {};
    if (summaryCards.total) {
      summaryCards.total.textContent = formatNumber(summary.total_items || 0);
    }
    if (summaryCards.totalMeta) {
      const avg = summary.avg ? formatNumber(summary.avg, { maximumFractionDigits: 2 }) : "-";
      summaryCards.totalMeta.textContent = `${formatNumber(summary.sum || 0)} • ${avg}`;
    }
    if (summaryCards.extrema) {
      const min = summary.min ?? "-";
      const max = summary.max ?? "-";
      summaryCards.extrema.textContent = `${min} / ${max}`;
    }
    if (summaryCards.extremaMeta) {
      const perc = summary.percentiles || {};
      summaryCards.extremaMeta.textContent = `Median ${perc.p50 ?? "-"} • P90 ${perc.p90 ?? "-"} • P99 ${perc.p99 ?? "-"}`;
    }
    if (summaryCards.sources) {
      summaryCards.sources.textContent = `${formatNumber(summary.unique_sources || 0)}`;
    }
    if (summaryCards.sourcesMeta) {
      summaryCards.sourcesMeta.textContent = `Fenster ${payload.window_hours || currentFilters.window || 24}h`;
    }
    if (summaryCards.corr) {
      const corr = payload.correlations || {};
      const titleCorr = corr.value_vs_title_length ?? "-";
      const priorityCorr = corr.value_vs_source_priority ?? "-";
      summaryCards.corr.textContent = `${priorityCorr}`;
      if (summaryCards.corrMeta) {
        summaryCards.corrMeta.textContent = `Priorität: ${priorityCorr} • Titel: ${titleCorr}`;
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
      li.textContent = topList.dataset.emptyLabel || "Keine Werte im Zeitraum";
      topList.appendChild(li);
      return;
    }
    entries.forEach((entry) => {
      const li = document.createElement("li");
      const header = document.createElement("div");
      header.className = "insight-headline";
      header.textContent = `Wert ${entry.value}`;
      const meta = document.createElement("small");
      const share = entry.share !== undefined ? `${(entry.share * 100).toFixed(2)}%` : "-";
      meta.textContent = `${formatNumber(entry.count)} Treffer • Anteil ${share}`;
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
      cell.textContent = sourcesTableBody.dataset.emptyLabel || "Keine Quellen im Zeitraum";
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
      li.textContent = trendList.dataset.emptyLabel || "Keine Trenddaten verfügbar";
      trendList.appendChild(li);
      return;
    }
    entries.forEach((entry) => {
      const li = document.createElement("li");
      const title = document.createElement("div");
      title.className = "insight-headline";
      title.textContent = `${entry.bucket_start} – ${entry.bucket_end}`;
      const meta = document.createElement("small");
      meta.textContent = `${formatNumber(entry.count)} Items • Ø ${formatNumber(entry.avg, { maximumFractionDigits: 2 })}`;
      li.appendChild(title);
      li.appendChild(meta);
      trendList.appendChild(li);
    });
  }

  if (filterForm) {
    filterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      currentFilters = captureFilters();
      load();
    });
  }

  if (filterReset) {
    filterReset.addEventListener("click", () => {
      filterForm?.reset();
      profileSelect && (profileSelect.value = "");
      profileNameInput && (profileNameInput.value = "");
      applyFilters({ window: "24", ranking: "top" });
      load();
    });
  }

  [windowSelect, schemeSelect, rankingSelect].forEach((element) => {
    element?.addEventListener("change", () => {
      currentFilters = captureFilters();
      load();
    });
  });

  refreshButton?.addEventListener("click", () => load({ refresh: true }));

  profileSelect?.addEventListener("change", () => {
    const selectedName = profileSelect.value;
    if (!selectedName) {
      profileNameInput && (profileNameInput.value = "");
      return;
    }
    const profile = profileStore.get ? profileStore.get(selectedName) : profileData[selectedName];
    if (profile) {
      applyFilters(profile);
      profileNameInput && (profileNameInput.value = selectedName);
      load();
    }
  });

  profileSaveButton?.addEventListener("click", () => {
    if (!filterForm) {
      return;
    }
    const name = (profileNameInput?.value || "").trim();
    if (!name) {
      profileNameInput?.focus();
      profileNameInput?.classList.add("input--highlight");
      setTimeout(() => profileNameInput?.classList.remove("input--highlight"), 600);
      return;
    }
    const filters = captureFilters();
    profileStore.save ? profileStore.save(name, filters) : (profileData[name] = filters);
    populateProfiles(name);
    profileSelect && (profileSelect.value = name);
    updateStatus(status, `${savedLabel}: ${name}`, "success");
  });

  profileUpdateButton?.addEventListener("click", () => {
    const selectedName = (profileSelect && profileSelect.value) || (profileNameInput && profileNameInput.value.trim()) || "";
    if (!selectedName) {
      profileSaveButton?.click();
      return;
    }
    const filters = captureFilters();
    profileStore.save ? profileStore.save(selectedName, filters) : (profileData[selectedName] = filters);
    populateProfiles(selectedName);
    profileSelect && (profileSelect.value = selectedName);
    profileNameInput && (profileNameInput.value = selectedName);
    updateStatus(status, `${savedLabel}: ${selectedName}`, "success");
  });

  profileDeleteButton?.addEventListener("click", () => {
    const selectedName = profileSelect ? profileSelect.value : "";
    const confirmMessage = deleteConfirm + (selectedName ? ` ${selectedName}` : "");
    if (!window.confirm(confirmMessage)) {
      return;
    }
    if (selectedName) {
      profileStore.remove ? profileStore.remove(selectedName) : delete profileData[selectedName];
    } else {
      profileStore.clear ? profileStore.clear() : (profileData = {});
    }
    populateProfiles("");
    if (profileSelect) {
      profileSelect.value = "";
    }
    if (profileNameInput) {
      profileNameInput.value = "";
    }
    filterForm?.reset();
    currentFilters = captureFilters();
    load();
  });

  populateProfiles(profileSelect?.value || "");
  load({ refresh: true });
}
