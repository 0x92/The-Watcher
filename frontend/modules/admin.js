const WORKER_SETTINGS_ENDPOINT = "/api/admin/worker-settings";
const WORKERS_ENDPOINT = "/api/admin/workers";
const SOURCES_ENDPOINT = "/api/admin/sources";

function updateStatus(element, message, state = "idle") {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.dataset.state = state;
  element.hidden = !message;
}

function parseNumber(input) {
  const value = Number.parseInt(input, 10);
  return Number.isNaN(value) ? undefined : value;
}

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTimestamp(value) {
  if (!value) {
    return "Stand: –";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Stand: –";
  }
  return `Stand: ${parsed.toLocaleString()}`;
}

function formatDate(value) {
  if (!value) {
    return "–";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "–";
  }
  return parsed.toLocaleString();
}

function renderTaskGroup(label, tasks) {
  if (!Array.isArray(tasks) || tasks.length === 0) {
    return `<div class="worker-task-group"><h3>${label}</h3><p class="worker-task-empty">Keine Einträge.</p></div>`;
  }

  const items = tasks
    .map((task) => {
      const name = escapeHtml(task.name || "Unbekannte Aufgabe");
      const id = task.id ? ` <span class="worker-task-id">#${escapeHtml(task.id)}</span>` : "";
      const metaParts = [];
      if (task.eta) {
        metaParts.push(`ETA ${escapeHtml(task.eta)}`);
      }
      if (task.queue) {
        metaParts.push(`Queue ${escapeHtml(task.queue)}`);
      }
      if (typeof task.runtime === "number" && !Number.isNaN(task.runtime)) {
        metaParts.push(`${task.runtime.toFixed(1)}s`);
      }
      const meta = metaParts.length
        ? `<div class="worker-task-meta">${metaParts.join(" • ")}</div>`
        : "";
      const payloadParts = [];
      if (task.args) {
        payloadParts.push(`<code>${escapeHtml(task.args)}</code>`);
      }
      if (task.kwargs && task.kwargs !== "{}") {
        payloadParts.push(`<code>${escapeHtml(task.kwargs)}</code>`);
      }
      const payload = payloadParts.length
        ? `<div class="worker-task-payload">${payloadParts.join(" ")}</div>`
        : "";
      return `<li><div class="worker-task-head">${name}${id}</div>${meta}${payload}</li>`;
    })
    .join("");

  return `<div class="worker-task-group"><h3>${label}</h3><ul class="worker-task-list">${items}</ul></div>`;
}

export function initAdmin() {
  const workerForm = document.querySelector("[data-worker-form]");
  const workerStatus = document.querySelector("[data-worker-status]");
  const workerOverviewStatus = document.querySelector("[data-worker-overview-status]");
  const workersList = document.querySelector("[data-workers-list]");
  const workerUpdated = document.querySelector("[data-worker-updated]");
  const workerRefresh = document.querySelector("[data-worker-refresh]");
  const sourceForm = document.querySelector("[data-source-form]");
  const sourceStatus = document.querySelector("[data-source-status]");
  const sourcesList = document.querySelector("[data-sources-list]");
  const sourceStats = document.querySelector("[data-source-stats]");
  const sourceFilterForm = document.querySelector("[data-source-filter-form]");
  const sourceFilterReset = document.querySelector("[data-source-filter-reset]");
  const sourceRefresh = document.querySelector("[data-source-refresh]");

  if (
    !workerForm &&
    !sourceForm &&
    !sourcesList &&
    !workersList &&
    !sourceFilterForm &&
    !sourceStats
  ) {
    return;
  }

  let cachedSources = [];
  let cachedWorkers = [];
  let workerMeta = { updatedAt: null, status: "idle", message: "" };
  let sourceMeta = { meta: {}, filters: {} };
  let sourceFilters = { query: "", type: "all", status: "all" };

  async function loadWorkerSettings() {
    if (!workerForm) {
      return;
    }
    updateStatus(workerStatus, "Lade Einstellungen…", "loading");
    try {
      const resp = await fetch(WORKER_SETTINGS_ENDPOINT, { credentials: "same-origin" });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      const data = await resp.json();
      workerForm.elements.scrape_enabled.checked = Boolean(data.scrape_enabled);
      workerForm.elements.default_interval_minutes.value = data.default_interval_minutes ?? 15;
      workerForm.elements.max_sources_per_cycle.value = data.max_sources_per_cycle ?? 0;
      if (sourceForm && sourceForm.elements.interval_minutes.value === "") {
        sourceForm.elements.interval_minutes.placeholder = data.default_interval_minutes ?? "";
      }
      updateStatus(workerStatus, "", "idle");
    } catch (error) {
      updateStatus(
        workerStatus,
        error.message || "Einstellungen konnten nicht geladen werden",
        "error",
      );
    }
  }

  async function saveWorkerSettings(event) {
    event.preventDefault();
    if (!workerForm) {
      return;
    }
    updateStatus(workerStatus, "Speichere…", "loading");
    const payload = {
      scrape_enabled: workerForm.elements.scrape_enabled.checked,
      default_interval_minutes: parseNumber(workerForm.elements.default_interval_minutes.value),
      max_sources_per_cycle: parseNumber(workerForm.elements.max_sources_per_cycle.value),
    };

    try {
      const resp = await fetch(WORKER_SETTINGS_ENDPOINT, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      await resp.json();
      updateStatus(workerStatus, "Einstellungen gespeichert", "success");
    } catch (error) {
      updateStatus(workerStatus, error.message || "Speichern fehlgeschlagen", "error");
    }
  }

  async function loadWorkers() {
    if (!workersList) {
      return;
    }
    updateStatus(workerOverviewStatus, "Lade Worker…", "loading");
    try {
      const resp = await fetch(WORKERS_ENDPOINT, { credentials: "same-origin" });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      const data = await resp.json();
      cachedWorkers = Array.isArray(data.workers) ? data.workers : [];
      workerMeta = {
        updatedAt: data.updated_at || null,
        status: data.status || "ok",
        message: data.message || "",
      };
      renderWorkers();
      if (workerUpdated) {
        workerUpdated.textContent = formatTimestamp(workerMeta.updatedAt);
      }
      const state = workerMeta.status === "ok" ? "idle" : "error";
      updateStatus(workerOverviewStatus, workerMeta.message || "", state);
    } catch (error) {
      updateStatus(workerOverviewStatus, error.message || "Worker konnten nicht geladen werden", "error");
      if (workerUpdated) {
        workerUpdated.textContent = formatTimestamp(null);
      }
      cachedWorkers = [];
      renderWorkers();
    }
  }

  function renderWorkers() {
    if (!workersList) {
      return;
    }
    if (!cachedWorkers.length) {
      workersList.innerHTML = '<p class="workers-empty">Keine Worker gefunden.</p>';
      return;
    }

    const sorted = [...cachedWorkers].sort((a, b) => {
      const left = String(a.name || a.id || "");
      const right = String(b.name || b.id || "");
      return left.localeCompare(right, "de-DE");
    });

    const cards = sorted
      .map((worker) => {
        const name = worker.name || worker.id || "Unbekannter Worker";
        const statusLabel = worker.online ? "Online" : "Offline";
        const statusClass = worker.online
          ? "worker-status worker-status--online"
          : "worker-status worker-status--offline";
        const current = Number.isFinite(worker.active_processes)
          ? worker.active_processes
          : 0;
        const configured = Number.isFinite(worker.configured_processes)
          ? worker.configured_processes
          : null;
        const processes = configured !== null ? `${current} / ${configured}` : `${current}`;
        const queueLabel = Array.isArray(worker.queues) && worker.queues.length
          ? worker.queues.map((queue) => escapeHtml(queue)).join(", ")
          : "–";
        const activeCount = Array.isArray(worker.active_tasks) ? worker.active_tasks.length : 0;
        const reservedCount = Array.isArray(worker.reserved_tasks) ? worker.reserved_tasks.length : 0;
        const scheduledCount = Array.isArray(worker.scheduled_tasks)
          ? worker.scheduled_tasks.length
          : 0;
        const canControl = Boolean(worker.online);
        const startDisabled = !canControl || (configured !== null ? current >= configured : current > 0);
        const stopDisabled = !canControl || current <= 0;
        const restartDisabled = !canControl;
        const totalTasks = Number.isFinite(worker.total_tasks) ? worker.total_tasks : null;
        const metaParts = [];
        if (worker.pid) {
          metaParts.push(`PID ${escapeHtml(worker.pid)}`);
        }
        if (totalTasks !== null) {
          metaParts.push(`${totalTasks} Aufgaben insgesamt`);
        }
        const meta = metaParts.length ? `<span>${metaParts.join(" • ")}</span>` : "";

        return `
          <article class="worker-card" data-worker-card data-worker-name="${escapeHtml(
            worker.id || name,
          )}">
            <header class="worker-card__header">
              <div>
                <h3>${escapeHtml(name)}</h3>
                <p class="worker-card__meta">
                  <span class="${statusClass}">${statusLabel}</span>
                  ${meta}
                </p>
              </div>
              <div class="worker-card__actions">
                <button type="button" class="button" data-worker-command="start" ${
                  startDisabled ? "disabled" : ""
                }>Starten</button>
                <button type="button" class="button" data-worker-command="restart" ${
                  restartDisabled ? "disabled" : ""
                }>Neustarten</button>
                <button type="button" class="button" data-worker-command="stop" ${
                  stopDisabled ? "disabled" : ""
                }>Stoppen</button>
              </div>
            </header>
            <dl class="worker-card__stats">
              <div><dt>Status</dt><dd>${statusLabel}</dd></div>
              <div><dt>Prozesse</dt><dd>${escapeHtml(processes)}</dd></div>
              <div><dt>Queues</dt><dd>${queueLabel}</dd></div>
              <div><dt>Aktiv</dt><dd>${activeCount}</dd></div>
              <div><dt>Reserviert</dt><dd>${reservedCount}</dd></div>
              <div><dt>Geplant</dt><dd>${scheduledCount}</dd></div>
            </dl>
            ${renderTaskGroup("Aktive Tasks", worker.active_tasks)}
            ${renderTaskGroup("Geplante Tasks", worker.scheduled_tasks)}
          </article>
        `;
      })
      .join("");

    workersList.innerHTML = cards;
  }

  async function sendWorkerCommand(workerName, action, triggerButton) {
    if (!workerName || !action) {
      return;
    }
    if (triggerButton) {
      triggerButton.disabled = true;
    }
    updateStatus(workerOverviewStatus, `Sende ${action}…`, "loading");
    try {
      const resp = await fetch(`${WORKERS_ENDPOINT}/${encodeURIComponent(workerName)}/control`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || `Serverfehler (${resp.status})`);
      }
      await loadWorkers();
      updateStatus(workerOverviewStatus, data.message || "Befehl ausgeführt", "success");
    } catch (error) {
      updateStatus(workerOverviewStatus, error.message || "Befehl fehlgeschlagen", "error");
    } finally {
      if (triggerButton) {
        triggerButton.disabled = false;
      }
    }
  }

  function buildSourceQueryString() {
    const params = new URLSearchParams();
    if (sourceFilters.query) {
      params.set("q", sourceFilters.query);
    }
    if (sourceFilters.type && sourceFilters.type !== "all") {
      params.set("type", sourceFilters.type);
    }
    if (sourceFilters.status && sourceFilters.status !== "all") {
      params.set("enabled", sourceFilters.status === "active" ? "true" : "false");
    }
    return params.toString();
  }

  function syncSourceFilterForm() {
    if (!sourceFilterForm) {
      return;
    }
    if (sourceFilterForm.elements.query) {
      sourceFilterForm.elements.query.value = sourceFilters.query || "";
    }
    if (sourceFilterForm.elements.type) {
      sourceFilterForm.elements.type.value = sourceFilters.type || "all";
    }
    if (sourceFilterForm.elements.status) {
      sourceFilterForm.elements.status.value = sourceFilters.status || "all";
    }
  }

  async function loadSources() {
    if (!sourcesList) {
      return;
    }
    updateStatus(sourceStatus, "Lade Quellen…", "loading");
    try {
      const query = buildSourceQueryString();
      const url = query ? `${SOURCES_ENDPOINT}?${query}` : SOURCES_ENDPOINT;
      const resp = await fetch(url, { credentials: "same-origin" });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      const data = await resp.json();
      cachedSources = Array.isArray(data.sources) ? data.sources : [];
      sourceMeta = {
        meta: data.meta || {},
        filters: data.filters || {},
      };

      if (data.filters) {
        const nextFilters = {
          query: data.filters.query || "",
          type:
            Array.isArray(data.filters.types) && data.filters.types.length
              ? data.filters.types[0]
              : "all",
          status:
            data.filters.enabled === true
              ? "active"
              : data.filters.enabled === false
                ? "inactive"
                : "all",
        };
        sourceFilters = nextFilters;
        syncSourceFilterForm();
      }

      renderSources();
      renderSourceStats();

      const meta = sourceMeta.meta || {};
      if (meta.filters_applied && !cachedSources.length && (meta.total_sources_all || 0) > 0) {
        updateStatus(
          sourceStatus,
          `Keine Quellen für die aktuellen Filter gefunden (Gesamt: ${meta.total_sources_all}).`,
          "idle",
        );
      } else {
        updateStatus(sourceStatus, "", "idle");
      }
    } catch (error) {
      updateStatus(sourceStatus, error.message || "Quellen konnten nicht geladen werden", "error");
    }
  }

  function renderSources() {
    if (!sourcesList) {
      return;
    }
    const meta = sourceMeta.meta || {};
    if (!cachedSources.length) {
      const totalAll = meta.total_sources_all || 0;
      const message = meta.filters_applied && totalAll > 0
        ? "Keine Quellen passend zu den aktuellen Filtern."
        : "Noch keine Quellen hinterlegt.";
      sourcesList.innerHTML = `<p class="sources-empty">${message}</p>`;
      return;
    }

    const rows = cachedSources
      .map((source) => {
        const statusLabel = source.enabled ? "Aktiv" : "Deaktiviert";
        const statusClass = source.enabled
          ? "source-status source-status--active"
          : "source-status source-status--inactive";
        const toggleLabel = source.enabled ? "Deaktivieren" : "Aktivieren";
        const interval = source.interval_minutes ?? 0;
        const intervalLabel = interval > 0 ? `${interval} min` : "Standard";
        const stats = source.stats || {};
        const totalItems = Number.isFinite(stats.total_items) ? stats.total_items : 0;
        const latest = stats.latest_item || {};
        const latestTitle = latest.title ? escapeHtml(latest.title) : "–";
        const latestLink = latest.url
          ? `<a href="${escapeHtml(latest.url)}" target="_blank" rel="noopener">${latestTitle}</a>`
          : latestTitle;
        const latestMetaParts = [];
        if (latest.published_at) {
          latestMetaParts.push(`Publiziert ${escapeHtml(formatDate(latest.published_at))}`);
        } else if (latest.fetched_at) {
          latestMetaParts.push(`Gefunden ${escapeHtml(formatDate(latest.fetched_at))}`);
        }
        const latestMeta = latestMetaParts.length
          ? `<span class="source-latest__meta">${latestMetaParts.join(" • ")}</span>`
          : "";
        const lastRun = formatDate(source.last_run_at);
        return `
          <tr data-source-id="${source.id}">
            <td>
              <div class="source-name">${escapeHtml(source.name)}</div>
              <div class="source-meta">
                <span class="${statusClass}">${statusLabel}</span>
                <span class="source-type">${escapeHtml(source.type.toUpperCase())}</span>
              </div>
            </td>
            <td class="source-url"><a href="${escapeHtml(source.endpoint)}" target="_blank" rel="noopener">${escapeHtml(
              source.endpoint,
            )}</a></td>
            <td>${intervalLabel}</td>
            <td>${totalItems}</td>
            <td class="source-latest">
              <span class="source-latest__title">${latestLink}</span>
              ${latestMeta}
            </td>
            <td>${lastRun}</td>
            <td class="actions">
              <button type="button" class="button" data-action="toggle" data-id="${source.id}">${toggleLabel}</button>
              <button type="button" class="button" data-action="delete" data-id="${source.id}">Entfernen</button>
            </td>
          </tr>
        `;
      })
      .join("");

    sourcesList.innerHTML = `
      <div class="table-wrapper">
        <table class="sources-table">
          <thead>
            <tr>
              <th>Quelle</th>
              <th>Feed</th>
              <th>Intervall</th>
              <th>Items</th>
              <th>Letzter Artikel</th>
              <th>Zuletzt ausgeführt</th>
              <th>Aktionen</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderSourceStats() {
    if (!sourceStats) {
      return;
    }

    const meta = sourceMeta.meta || {};
    const total = Number.isFinite(meta.total_sources) ? meta.total_sources : cachedSources.length;
    const active = Number.isFinite(meta.active_sources)
      ? meta.active_sources
      : cachedSources.filter((source) => source.enabled).length;
    const inactive = Number.isFinite(meta.inactive_sources)
      ? meta.inactive_sources
      : total - active;
    const totalAll = Number.isFinite(meta.total_sources_all) ? meta.total_sources_all : total;
    const totalItems = Number.isFinite(meta.total_items)
      ? meta.total_items
      : cachedSources.reduce((sum, source) => sum + (source.stats?.total_items ?? 0), 0);
    const typeBreakdown = meta.type_breakdown || {};
    const lastRunAt = meta.last_run_at ? formatDate(meta.last_run_at) : "–";

    const typesMarkup = Object.keys(typeBreakdown).length
      ? `<ul class="source-type-list">${Object.entries(typeBreakdown)
          .map(
            ([type, count]) =>
              `<li><span>${escapeHtml(String(type).toUpperCase())}</span><strong>${count}</strong></li>`,
          )
          .join("")}</ul>`
      : '<p class="source-type-empty">Keine Typen gefunden.</p>';

    const totalMeta = totalAll > total ? ` • Gesamt: ${totalAll}` : "";

    sourceStats.innerHTML = `
      <article class="stat-card">
        <h3>Gesamtquellen</h3>
        <p class="stat-card__value">${total}</p>
        <p class="stat-card__meta">Aktiv: ${active} • Inaktiv: ${inactive}${totalMeta}</p>
      </article>
      <article class="stat-card">
        <h3>Gesamt-Items</h3>
        <p class="stat-card__value">${totalItems}</p>
        <p class="stat-card__meta">Letzter Lauf: ${lastRunAt}</p>
      </article>
      <article class="stat-card stat-card--types">
        <h3>Quellen-Typen</h3>
        ${typesMarkup}
      </article>
    `;
  }

  async function createSource(event) {
    event.preventDefault();
    if (!sourceForm) {
      return;
    }
    updateStatus(sourceStatus, "Speichere Quelle…", "loading");
    const payload = {
      name: sourceForm.elements.name.value,
      type: sourceForm.elements.type.value,
      endpoint: sourceForm.elements.endpoint.value,
      enabled: sourceForm.elements.enabled.checked,
    };
    const interval = parseNumber(sourceForm.elements.interval_minutes.value);
    if (interval !== undefined) {
      payload.interval_minutes = interval;
    }

    try {
      const resp = await fetch(SOURCES_ENDPOINT, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      await resp.json();
      sourceForm.reset();
      updateStatus(sourceStatus, "Quelle gespeichert", "success");
      await loadSources();
    } catch (error) {
      updateStatus(sourceStatus, error.message || "Quelle konnte nicht gespeichert werden", "error");
    }
  }

  async function toggleSource(sourceId) {
    const source = cachedSources.find((entry) => entry.id === sourceId);
    if (!source) {
      return;
    }
    updateStatus(sourceStatus, "Aktualisiere Quelle…", "loading");
    try {
      const resp = await fetch(`${SOURCES_ENDPOINT}/${sourceId}`, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      await resp.json();
      updateStatus(sourceStatus, "Quelle aktualisiert", "success");
      await loadSources();
    } catch (error) {
      updateStatus(sourceStatus, error.message || "Aktualisierung fehlgeschlagen", "error");
    }
  }

  async function deleteSource(sourceId) {
    updateStatus(sourceStatus, "Lösche Quelle…", "loading");
    try {
      const resp = await fetch(`${SOURCES_ENDPOINT}/${sourceId}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      updateStatus(sourceStatus, "Quelle entfernt", "success");
      await loadSources();
    } catch (error) {
      updateStatus(sourceStatus, error.message || "Quelle konnte nicht entfernt werden", "error");
    }
  }

  if (workerForm) {
    workerForm.addEventListener("submit", saveWorkerSettings);
    loadWorkerSettings();
  }

  if (workersList) {
    workersList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-worker-command]");
      if (!button) {
        return;
      }
      const card = button.closest("[data-worker-card]");
      if (!card) {
        return;
      }
      const workerName = card.dataset.workerName;
      const action = button.dataset.workerCommand;
      sendWorkerCommand(workerName, action, button);
    });
    loadWorkers();
  }

  if (workerRefresh) {
    workerRefresh.addEventListener("click", () => {
      loadWorkers();
    });
  }

  if (workerUpdated) {
    workerUpdated.textContent = formatTimestamp(workerMeta.updatedAt);
  }

  if (sourceFilterForm) {
    syncSourceFilterForm();
    sourceFilterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      sourceFilters = {
        query: sourceFilterForm.elements.query
          ? sourceFilterForm.elements.query.value.trim()
          : "",
        type: sourceFilterForm.elements.type
          ? sourceFilterForm.elements.type.value || "all"
          : "all",
        status: sourceFilterForm.elements.status
          ? sourceFilterForm.elements.status.value || "all"
          : "all",
      };
      loadSources();
    });
  }

  if (sourceFilterReset) {
    sourceFilterReset.addEventListener("click", () => {
      sourceFilters = { query: "", type: "all", status: "all" };
      if (sourceFilterForm) {
        sourceFilterForm.reset();
        syncSourceFilterForm();
      }
      loadSources();
    });
  }

  if (sourceForm) {
    sourceForm.addEventListener("submit", createSource);
  }

  if (sourceRefresh) {
    sourceRefresh.addEventListener("click", () => {
      loadSources();
    });
  }

  if (sourcesList) {
    sourcesList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) {
        return;
      }
      const sourceId = Number.parseInt(button.dataset.id, 10);
      if (Number.isNaN(sourceId)) {
        return;
      }
      if (button.dataset.action === "toggle") {
        toggleSource(sourceId);
      } else if (button.dataset.action === "delete") {
        deleteSource(sourceId);
      }
    });
    loadSources();
  }
}

