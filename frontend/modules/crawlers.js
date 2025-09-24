const OVERVIEW_ENDPOINT = "/api/crawlers";
const OVERVIEW_STREAM_ENDPOINT = "/api/crawlers/stream";
const FEEDS_ENDPOINT = "/api/crawlers/feeds";
const FEED_BULK_ENDPOINT = "/api/crawlers/feeds/bulk";
const WORKER_CONTROL_ENDPOINT = (worker) => `/api/crawlers/${worker}/control`;
const HEALTH_CHECK_ENDPOINT = (id) => `/api/crawlers/feeds/${id}/actions/health-check`;
const PROFILE_STORAGE_KEY = 'watcher:crawler-filters:v1';

function updateStatus(element, message, state = "idle") {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.dataset.state = state;
  element.hidden = !message;
}

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "–";
  }
  const number = Number(value);
  return Number.isNaN(number) ? String(value) : number.toLocaleString();
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

function el(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) {
    node.className = options.className;
  }
  if (options.text) {
    node.textContent = options.text;
  }
  if (options.html) {
    node.innerHTML = options.html;
  }
  if (options.attrs) {
    Object.entries(options.attrs).forEach(([key, value]) => {
      if (value === undefined || value === null) {
        return;
      }
      node.setAttribute(key, String(value));
    });
  }
  return node;
}

export function initCrawlers() {
  const overviewStatus = document.querySelector("[data-crawler-overview-status]");
  const summaryContainer = document.querySelector("[data-crawler-summary]");
  const windowInput = document.querySelector("[data-crawler-window]");
  const refreshButton = document.querySelector("[data-crawler-refresh]");

  const workerStatus = document.querySelector("[data-worker-status]");
  const workerRefresh = document.querySelector("[data-worker-refresh]");
  const workersList = document.querySelector("[data-workers-list]");

  const feedStatus = document.querySelector("[data-feed-status]");
  const feedRefresh = document.querySelector("[data-feed-refresh]");
  const feedList = document.querySelector("[data-feed-list]");
  const feedFilterForm = document.querySelector("[data-feed-filter-form]");
  const feedFilterReset = document.querySelector("[data-feed-filter-reset]");
  const feedCreateForm = document.querySelector("[data-feed-create-form]");
  const feedBulkForm = document.querySelector("[data-feed-bulk-form]");
  const profileControls = document.querySelector(".profile-controls");
  const profileSelect = document.querySelector("[data-feed-profile-select]");
  const profileNameInput = document.querySelector("[data-feed-profile-name]");
  const profileSaveButton = document.querySelector("[data-feed-profile-save]");
  const profileUpdateButton = document.querySelector("[data-feed-profile-update]");
  const profileDeleteButton = document.querySelector("[data-feed-profile-delete]");
  const deleteConfirmMessage = profileControls?.dataset.profileDeleteConfirm || 'Delete profile?';

  if (!summaryContainer || !workersList || !feedList) {
    return;
  }

  function readProfiles() {
    try {
      const raw = localStorage.getItem(PROFILE_STORAGE_KEY);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw);
      if (typeof parsed !== 'object' || parsed === null) {
        return {};
      }
      return parsed;
    } catch (error) {
      console.warn('Failed to parse crawler profiles', error);
      return {};
    }
  }

  function persistProfiles(store) {
    try {
      profileStore = store;
      localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(store));
    } catch (error) {
      console.warn('Failed to persist crawler profiles', error);
    }
  }

  let profileStore = readProfiles();

  function populateProfiles(selectedName = '') {
    if (!profileSelect) {
      return;
    }
    const defaultLabel = profileSelect.dataset.defaultLabel || (profileSelect.options[0] && profileSelect.options[0].textContent) || '';
    profileSelect.innerHTML = '';
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = defaultLabel || '�';
    profileSelect.appendChild(defaultOption);
    Object.keys(profileStore)
      .sort((a, b) => a.localeCompare(b))
      .forEach((name) => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        if (name === selectedName) {
          option.selected = true;
        }
        profileSelect.appendChild(option);
      });
  }

  function captureFilters() {
    if (!feedFilterForm) {
      return { ...currentFilters };
    }
    const formData = new FormData(feedFilterForm);
    return {
      query: (formData.get('query') || '').toString().trim(),
      type: (formData.get('type') || '').toString(),
      enabled: (formData.get('enabled') || '').toString(),
      tags: (formData.get('tags') || '').toString().trim(),
      include_runs: formData.get('include_runs') === '1' || formData.get('include_runs') === 'on',
    };
  }

  function applyProfileFilters(filters) {
    if (!feedFilterForm || !filters) {
      return;
    }
    const entries = [
      ['query', filters.query || ''],
      ['type', filters.type || ''],
      ['enabled', filters.enabled || ''],
      ['tags', filters.tags || ''],
    ];
    entries.forEach(([name, value]) => {
      const input = feedFilterForm.querySelector(`[name="${name}"]`);
      if (input) {
        input.value = value;
      }
    });
    const includeRunsField = feedFilterForm.querySelector('[name="include_runs"]');
    if (includeRunsField) {
      includeRunsField.checked = Boolean(filters.include_runs);
    }
    currentFilters = captureFilters();
  }

  populateProfiles();
  currentFilters = captureFilters();

  let eventSource = null;
  let pollTimer = null;
  let currentWindowHours = Number(windowInput ? windowInput.value : 24) || 24;
  let currentFilters = {
    query: "",
    type: "",
    enabled: "",
    tags: "",
    include_runs: false,
  };

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function stopStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function schedulePolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      loadOverview();
    }, 8000);
  }

  function renderSummary(payload) {
    const sources = payload.sources || {};
    const runs = payload.runs || {};
    const discoveries = payload.discoveries || {};

    const summaryCards = summaryContainer.querySelectorAll(".stat-card");
    if (summaryCards.length >= 4) {
      summaryCards[0].querySelector(".stat-card__value").textContent = formatNumber(sources.total);
      summaryCards[0].querySelector(".stat-card__meta").textContent = `Aktiv ${formatNumber(sources.active)} • Degradiert ${formatNumber(sources.degraded)}`;

      summaryCards[1].querySelector(".stat-card__value").textContent = formatNumber(runs.total);
      summaryCards[1].querySelector(".stat-card__meta").textContent = `Fehler ${formatNumber(runs.failed)} • Items ${formatNumber(runs.items_processed)}`;

      summaryCards[2].querySelector(".stat-card__value").textContent = runs.avg_duration_ms === null || runs.avg_duration_ms === undefined
        ? "–"
        : `${Math.round(runs.avg_duration_ms)} ms`;
      summaryCards[2].querySelector(".stat-card__meta").textContent = `Fenster ${runs.window_hours || currentWindowHours} h`;

      summaryCards[3].querySelector(".stat-card__value").textContent = formatNumber(discoveries.pending);
      summaryCards[3].querySelector(".stat-card__meta").textContent = `Veröffentlicht ${formatNumber(discoveries.approved)}`;
    }

    if (overviewStatus) {
      const timestamp = payload.updated_at ? formatDate(payload.updated_at) : "–";
      updateStatus(overviewStatus, `Stand: ${timestamp}`, "success");
    }
  }

  function renderWorkers(snapshot) {
    if (!workersList) {
      return;
    }
    workersList.innerHTML = "";
    const workers = (snapshot && Array.isArray(snapshot.workers)) ? snapshot.workers : [];
    if (workers.length === 0) {
      workersList.appendChild(el("p", { className: "workers-empty", text: "Keine Worker registriert." }));
      return;
    }

    workers.forEach((worker) => {
      const card = el("article", { className: "worker-card", attrs: { "data-worker-card": "", "data-worker-name": worker.id || worker.name || "scheduler" } });
      const header = el("header", { className: "worker-card__header" });
      const title = el("div", { className: "worker-card__title" });
      const name = worker.name || worker.id || "Unbekannt";
      const status = worker.status || (worker.online ? "online" : "offline");
      title.appendChild(el("h3", { text: name }));
      title.appendChild(el("p", { className: "worker-status", text: status }));
      header.appendChild(title);

      const actions = el("div", { className: "worker-card__actions" });
      [
        { label: "Start", action: "start" },
        { label: "Stop", action: "stop" },
        { label: "Restart", action: "restart" },
      ].forEach(({ label, action }) => {
        const button = el("button", {
          className: "button subtle",
          text: label,
          attrs: {
            type: "button",
            "data-worker-command": action,
          },
        });
        actions.appendChild(button);
      });
      header.appendChild(actions);
      card.appendChild(header);

      const meta = el("div", { className: "worker-meta" });
      meta.appendChild(el("p", { text: `Queue: ${formatNumber(worker.queued_jobs)}` }));
      meta.appendChild(el("p", { text: `Aktive Jobs: ${formatNumber(worker.active_jobs)}` }));
      if (worker.max_workers !== undefined) {
        meta.appendChild(el("p", { text: `Max Threads: ${formatNumber(worker.max_workers)}` }));
      }
      card.appendChild(meta);

      if (Array.isArray(worker.jobs) && worker.jobs.length > 0) {
        const jobList = el("div", { className: "worker-jobs" });
        worker.jobs.forEach((job) => {
          const jobCard = el("article", { className: "worker-job" });
          jobCard.appendChild(el("h4", { text: job.name || "Job" }));
          const jobMeta = [
            job.interval_seconds ? `Intervall: ${job.interval_seconds}s` : null,
            job.next_run_at ? `Nächster Run: ${formatDate(job.next_run_at)}` : null,
            job.last_run_at ? `Letzter Run: ${formatDate(job.last_run_at)}` : null,
            job.last_duration_seconds ? `Dauer: ${job.last_duration_seconds.toFixed(2)}s` : null,
            job.total_runs !== undefined ? `Runs: ${job.total_runs}` : null,
            job.running ? "Status: läuft" : job.enabled ? "Status: bereit" : "Status: deaktiviert",
          ].filter(Boolean);
          jobCard.appendChild(el("p", { className: "worker-job__meta", text: jobMeta.join(" • ") }));
          if (job.error) {
            jobCard.appendChild(el("p", { className: "worker-job__error", text: job.error }));
          }
          const jobActions = el("div", { className: "worker-job__actions" });
          [
            { label: "Aktivieren", action: "start" },
            { label: "Deaktivieren", action: "stop" },
            { label: "Triggern", action: "restart" },
          ].forEach(({ label, action }) => {
            const button = el("button", {
              className: "button mini",
              text: label,
              attrs: {
                type: "button",
                "data-worker-command": action,
                "data-worker-job": job.name || "",
              },
            });
            jobActions.appendChild(button);
          });
          jobCard.appendChild(jobActions);
          jobList.appendChild(jobCard);
        });
        card.appendChild(jobList);
      }

      workersList.appendChild(card);
    });
  }

  function renderFeeds(feeds) {
    feedList.innerHTML = "";
    if (!Array.isArray(feeds) || feeds.length === 0) {
      feedList.appendChild(el("p", { className: "sources-empty", text: "Keine Quellen gefunden." }));
      return;
    }

    feeds.forEach((feed) => {
      const item = el("article", { className: "source-card", attrs: { "data-feed-id": feed.id } });

      const header = el("header", { className: "source-card__header" });
      const title = el("div", { className: "source-card__title" });
      title.appendChild(el("input", {
        attrs: {
          type: "checkbox",
          "data-feed-select": "",
          value: feed.id,
        },
      }));
      title.appendChild(el("h3", { text: feed.name }));
      const statusBadge = el("span", {
        className: feed.enabled ? "badge badge--success" : "badge badge--muted",
        text: feed.enabled ? "Aktiv" : "Inaktiv",
      });
      title.appendChild(statusBadge);
      header.appendChild(title);

      const headerActions = el("div", { className: "source-card__actions" });
      const toggleButton = el("button", {
        className: "button subtle",
        text: feed.enabled ? "Deaktivieren" : "Aktivieren",
        attrs: {
          type: "button",
          "data-action": "toggle",
          "data-id": feed.id,
          "data-enabled": feed.enabled ? "1" : "0",
        },
      });
      const healthButton = el("button", {
        className: "button subtle",
        text: "Health Check",
        attrs: {
          type: "button",
          "data-action": "health",
          "data-id": feed.id,
        },
      });
      const deleteButton = el("button", {
        className: "button subtle danger",
        text: "Löschen",
        attrs: {
          type: "button",
          "data-action": "delete",
          "data-id": feed.id,
        },
      });
      headerActions.appendChild(toggleButton);
      headerActions.appendChild(healthButton);
      headerActions.appendChild(deleteButton);
      header.appendChild(headerActions);
      item.appendChild(header);

      const meta = el("div", { className: "source-card__meta" });
      meta.appendChild(el("p", { text: `Typ: ${feed.type.toUpperCase()} • Priorität: ${formatNumber(feed.priority)}` }));
      meta.appendChild(el("p", { text: feed.endpoint }));
      const stats = feed.stats || {};
      meta.appendChild(el("p", {
        text: `Items: ${formatNumber(stats.total_items)} • Letzter Fetch: ${formatDate(stats.last_fetched_at)} • Letzte Publikation: ${formatDate(stats.last_published_at)}`,
      }));
      const health = feed.health || {};
      meta.appendChild(el("p", {
        className: health.status === "degraded" ? "source-health source-health--warning" : "source-health",
        text: `Status: ${health.status || "unbekannt"} • Fehler: ${formatNumber(health.consecutive_failures)} • Letzter Check: ${formatDate(health.last_checked_at)}`,
      }));
      if (health.last_error) {
        meta.appendChild(el("p", { className: "source-error", text: health.last_error }));
      }
      if (Array.isArray(feed.tags) && feed.tags.length) {
        meta.appendChild(el("p", { className: "source-tags", text: `Tags: ${feed.tags.join(", ")}` }));
      }
      if (feed.notes) {
        meta.appendChild(el("p", { className: "source-notes", text: `Notiz: ${feed.notes}` }));
      }
      item.appendChild(meta);

      const editForm = el("form", { className: "feed-edit", attrs: { "data-feed-edit": feed.id } });
      editForm.innerHTML = `
        <div class="form-row">
          <label class="form-control">
            <span>Priorität</span>
            <input type="number" name="priority" min="0" step="1" value="${feed.priority ?? 0}">
          </label>
          <label class="form-control">
            <span>Tags</span>
            <input type="text" name="tags" value="${(feed.tags || []).join(', ')}" placeholder="tag1, tag2">
          </label>
        </div>
        <label class="form-control">
          <span>Notizen</span>
          <textarea name="notes" rows="2">${feed.notes || ""}</textarea>
        </label>
        <div class="form-actions">
          <button type="submit" class="button mini">Speichern</button>
        </div>
      `;
      editForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const formData = new FormData(editForm);
        const body = {
          priority: Number.parseInt(formData.get("priority"), 10),
          tags: (formData.get("tags") || "").split(",").map((tag) => tag.trim()).filter(Boolean),
          notes: formData.get("notes"),
        };
        updateFeed(feed.id, body);
      });
      item.appendChild(editForm);

      if (Array.isArray(feed.runs) && feed.runs.length) {
        const runsList = el("details", { className: "feed-runs" });
        runsList.appendChild(el("summary", { text: `Letzte Runs (${feed.runs.length})` }));
        const runItems = el("ul", { className: "feed-runs__list" });
        feed.runs.forEach((run) => {
          runItems.appendChild(el("li", {
            text: `${formatDate(run.started_at)} • Status: ${run.status || "-"} • Items: ${formatNumber(run.items_fetched)}`,
          }));
        });
        runsList.appendChild(runItems);
        item.appendChild(runsList);
      }

      feedList.appendChild(item);
    });
  }

  function getFilters() {
    currentFilters = captureFilters();
    return { ...currentFilters };
  }

  async function loadOverview({ silent = false } = {}) {
    if (!silent) {
      updateStatus(overviewStatus, "Lade Übersicht...", "loading");
    }
    try {
      const query = new URLSearchParams({ window_hours: String(currentWindowHours) });
      const response = await fetch(`${OVERVIEW_ENDPOINT}?${query.toString()}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`Serverfehler (${response.status})`);
      }
      const payload = await response.json();
      renderSummary(payload);
      renderWorkers(payload.workers);
      updateStatus(overviewStatus, `Stand: ${formatDate(payload.updated_at)}`, "success");
    } catch (error) {
      console.error("loadOverview failed", error);
      updateStatus(overviewStatus, error.message || "Übersicht konnte nicht geladen werden", "error");
    }
  }

  function startStream() {
    stopStream();
    stopPolling();

    const params = new URLSearchParams({
      window_hours: String(currentWindowHours),
      refresh: "5",
    });
    try {
      eventSource = new EventSource(`${OVERVIEW_STREAM_ENDPOINT}?${params.toString()}`, { withCredentials: true });
      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          renderSummary(payload);
          renderWorkers(payload.workers);
        } catch (parseError) {
          console.error("SSE parse error", parseError);
        }
      };
      eventSource.onerror = () => {
        updateStatus(overviewStatus, "Live-Stream getrennt – wechsle auf Polling", "error");
        stopStream();
        schedulePolling();
      };
    } catch (error) {
      console.warn("EventSource not supported", error);
      schedulePolling();
    }
  }

  async function loadFeeds({ silent = false } = {}) {
    const filters = getFilters();
    const params = new URLSearchParams();
    if (filters.query) {
      params.set("q", filters.query);
    }
    if (filters.type) {
      params.set("type", filters.type);
    }
    if (filters.enabled) {
      params.set("enabled", filters.enabled);
    }
    if (filters.tags) {
      params.set("tags", filters.tags);
    }
    if (filters.include_runs) {
      params.set("include_runs", "1");
    }

    if (!silent) {
      updateStatus(feedStatus, "Lade Quellen...", "loading");
    }

    try {
      const response = await fetch(`${FEEDS_ENDPOINT}?${params.toString()}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`Serverfehler (${response.status})`);
      }
      const payload = await response.json();
      renderFeeds(payload.sources || []);
      updateStatus(feedStatus, `Gefundene Quellen: ${formatNumber(payload.meta?.total_sources ?? 0)}`, "success");
    } catch (error) {
      console.error("loadFeeds failed", error);
      updateStatus(feedStatus, error.message || "Quellen konnten nicht geladen werden", "error");
    }
  }

  async function createFeed(formData) {
    updateStatus(feedStatus, "Quelle wird erstellt...", "loading");
    try {
      const payload = Object.fromEntries(formData.entries());
      if (payload.priority !== undefined) {
        payload.priority = Number.parseInt(payload.priority, 10);
      }
      if (payload.tags) {
        payload.tags = String(payload.tags)
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean);
      }
      payload.enabled = formData.get("enabled") !== null;

      const response = await fetch(FEEDS_ENDPOINT, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload.error || `Serverfehler (${response.status})`);
      }
      updateStatus(feedStatus, "Quelle erstellt", "success");
      feedCreateForm.reset();
      loadFeeds({ silent: true });
    } catch (error) {
      updateStatus(feedStatus, error.message || "Quelle konnte nicht erstellt werden", "error");
    }
  }

  async function updateFeed(id, payload) {
    updateStatus(feedStatus, "Änderungen werden gespeichert...", "loading");
    try {
      const response = await fetch(FEEDS_ENDPOINT + `/${id}`, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload.error || `Serverfehler (${response.status})`);
      }
      updateStatus(feedStatus, "Quelle aktualisiert", "success");
      loadFeeds({ silent: true });
    } catch (error) {
      updateStatus(feedStatus, error.message || "Änderungen konnten nicht gespeichert werden", "error");
    }
  }

  async function toggleFeed(id, enabled) {
    return updateFeed(id, { enabled: !enabled });
  }

  async function removeFeed(id) {
    updateStatus(feedStatus, "Lösche Quelle...", "loading");
    try {
      const response = await fetch(FEEDS_ENDPOINT + `/${id}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Serverfehler (${response.status})`);
      }
      updateStatus(feedStatus, "Quelle gelöscht", "success");
      loadFeeds({ silent: true });
    } catch (error) {
      updateStatus(feedStatus, error.message || "Quelle konnte nicht gelöscht werden", "error");
    }
  }

  async function healthCheckFeed(id) {
    updateStatus(feedStatus, "Health Check wird angestoßen...", "loading");
    try {
      const response = await fetch(HEALTH_CHECK_ENDPOINT(id), {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Serverfehler (${response.status})`);
      }
      updateStatus(feedStatus, "Health Check gestartet", "success");
      loadFeeds({ silent: true });
    } catch (error) {
      updateStatus(feedStatus, error.message || "Health Check fehlgeschlagen", "error");
    }
  }

  async function bulkAction(formData) {
    const selected = Array.from(feedList.querySelectorAll("[data-feed-select]:checked"))
      .map((input) => Number.parseInt(input.value, 10))
      .filter((id) => !Number.isNaN(id));

    if (selected.length === 0) {
      updateStatus(feedStatus, "Bitte mindestens eine Quelle auswählen", "error");
      return;
    }

    const action = formData.get("action");
    if (!action) {
      updateStatus(feedStatus, "Bitte eine Aktion wählen", "error");
      return;
    }

    const payload = {
      ids: selected,
      action,
    };

    const value = formData.get("value");
    if (value && action === "set_priority") {
      payload.payload = { priority: Number.parseInt(value, 10) };
    } else if (value && action === "set_tags") {
      payload.payload = {
        tags: String(value)
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      };
    } else if (action === "set_notes") {
      payload.payload = { notes: value || "" };
    }

    updateStatus(feedStatus, "Bulk-Aktion wird ausgeführt...", "loading");
    try {
      const response = await fetch(FEED_BULK_ENDPOINT, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload.error || `Serverfehler (${response.status})`);
      }
      updateStatus(feedStatus, "Bulk-Aktion erfolgreich", "success");
      feedBulkForm.reset();
      loadFeeds({ silent: true });
    } catch (error) {
      updateStatus(feedStatus, error.message || "Bulk-Aktion fehlgeschlagen", "error");
    }
  }

  async function controlWorker(event) {
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
    const jobName = button.dataset.workerJob;

    if (!workerName || !action) {
      return;
    }

    updateStatus(workerStatus, `Sende Befehl ${action}...`, "loading");
    try {
      const targetName = jobName || workerName;
      const response = await fetch(WORKER_CONTROL_ENDPOINT(targetName), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ action }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || `Serverfehler (${response.status})`);
      }
      updateStatus(workerStatus, "Befehl ausgeführt", "success");
      loadOverview({ silent: true });
    } catch (error) {
      updateStatus(workerStatus, error.message || "Worker-Befehl fehlgeschlagen", "error");
    }
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", () => {
      loadOverview();
    });
  }

  if (windowInput) {
    windowInput.addEventListener("change", () => {
      currentWindowHours = coerce_int(windowInput.value, 24, { minimum: 1, maximum: 168 });
      startStream();
      loadOverview({ silent: true });
    });
  }

  if (workerRefresh) {
    workerRefresh.addEventListener("click", () => {
      loadOverview();
    });
  }

  workersList.addEventListener("click", controlWorker);

  if (feedRefresh) {
    feedRefresh.addEventListener("click", () => loadFeeds());
  }

  if (feedFilterForm) {
    feedFilterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      loadFeeds();
    });
  }

  if (feedFilterReset) {
    feedFilterReset.addEventListener("click", () => {
      if (feedFilterForm) {
        feedFilterForm.reset();
      }
      if (profileSelect) {
        profileSelect.value = "";
      }
      if (profileNameInput) {
        profileNameInput.value = "";
      }
      currentFilters = captureFilters();
      loadFeeds();
    });
  }

  if (feedCreateForm) {
    feedCreateForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(feedCreateForm);
      createFeed(formData);
    });
  }

  const savedLabel = profileControls?.dataset.profileSavedLabel || 'Saved';

  if (profileSelect) {
    populateProfiles(profileSelect.value || '');
    profileSelect.addEventListener('change', () => {
      const selectedName = profileSelect.value;
      if (!selectedName) {
        if (profileNameInput) {
          profileNameInput.value = '';
        }
        if (feedFilterForm) {
          feedFilterForm.reset();
        }
        currentFilters = captureFilters();
        loadFeeds();
        return;
      }
      const profile = profileStore[selectedName];
      if (profile) {
        applyProfileFilters(profile);
        if (profileNameInput) {
          profileNameInput.value = selectedName;
        }
        loadFeeds();
      }
    });
  }

  if (profileSaveButton) {
    profileSaveButton.addEventListener('click', () => {
      if (!feedFilterForm) {
        return;
      }
      const name = (profileNameInput?.value || '').trim();
      if (!name) {
        profileNameInput?.focus();
        profileNameInput?.classList.add('input--highlight');
        setTimeout(() => profileNameInput?.classList.remove('input--highlight'), 600);
        return;
      }
      profileStore[name] = captureFilters();
      persistProfiles(profileStore);
      populateProfiles(name);
      if (profileSelect) {
        profileSelect.value = name;
      }
      updateStatus(feedStatus, `${savedLabel}: ${name}`, 'success');
    });
  }

  if (profileUpdateButton) {
    profileUpdateButton.addEventListener('click', () => {
      if (!feedFilterForm) {
        return;
      }
      const selectedName = (profileSelect && profileSelect.value) || (profileNameInput && profileNameInput.value.trim()) || '';
      if (!selectedName) {
        profileSaveButton?.click();
        return;
      }
      profileStore[selectedName] = captureFilters();
      persistProfiles(profileStore);
      populateProfiles(selectedName);
      if (profileSelect) {
        profileSelect.value = selectedName;
      }
      if (profileNameInput) {
        profileNameInput.value = selectedName;
      }
      updateStatus(feedStatus, `${savedLabel}: ${selectedName}`, 'success');
    });
  }

  if (profileDeleteButton) {
    profileDeleteButton.addEventListener('click', () => {
      const selectedName = profileSelect ? profileSelect.value : '';
      const confirmMessage = deleteConfirmMessage + (selectedName ? ` ${selectedName}` : '');
      if (!window.confirm(confirmMessage)) {
        return;
      }
      if (selectedName) {
        delete profileStore[selectedName];
      } else {
        profileStore = {};
      }
      persistProfiles(profileStore);
      populateProfiles('');
      if (profileSelect) {
        profileSelect.value = '';
      }
      if (profileNameInput) {
        profileNameInput.value = '';
      }
      if (feedFilterForm) {
        feedFilterForm.reset();
      }
      currentFilters = captureFilters();
      loadFeeds();
    });
  }

  if (feedBulkForm) {
    feedBulkForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(feedBulkForm);
      bulkAction(formData);
    });
  }

  feedList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) {
      return;
    }
    const id = Number.parseInt(button.dataset.id, 10);
    if (Number.isNaN(id)) {
      return;
    }
    const action = button.dataset.action;
    if (action === "toggle") {
      const enabled = button.dataset.enabled === "1";
      toggleFeed(id, enabled);
    } else if (action === "delete") {
      if (confirm("Quelle wirklich löschen?")) {
        removeFeed(id);
      }
    } else if (action === "health") {
      healthCheckFeed(id);
    }
  });

  startStream();
  loadOverview({ silent: true });
  loadFeeds();
}

function coerce_int(value, fallback, { minimum = Number.MIN_SAFE_INTEGER, maximum = Number.MAX_SAFE_INTEGER } = {}) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.min(Math.max(parsed, minimum), maximum);
}
