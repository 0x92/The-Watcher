const WORKER_ENDPOINT = "/api/admin/worker-settings";
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

export function initAdmin() {
  const workerForm = document.querySelector("[data-worker-form]");
  const workerStatus = document.querySelector("[data-worker-status]");
  const sourceForm = document.querySelector("[data-source-form]");
  const sourceStatus = document.querySelector("[data-source-status]");
  const sourcesList = document.querySelector("[data-sources-list]");

  if (!workerForm && !sourceForm && !sourcesList) {
    return;
  }

  let cachedSources = [];

  async function loadWorkerSettings() {
    if (!workerForm) {
      return;
    }
    updateStatus(workerStatus, "Lade Einstellungen…", "loading");
    try {
      const resp = await fetch(WORKER_ENDPOINT, { credentials: "same-origin" });
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
      updateStatus(workerStatus, error.message || "Einstellungen konnten nicht geladen werden", "error");
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
      const resp = await fetch(WORKER_ENDPOINT, {
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

  async function loadSources() {
    if (!sourcesList) {
      return;
    }
    updateStatus(sourceStatus, "Lade Quellen…", "loading");
    try {
      const resp = await fetch(SOURCES_ENDPOINT, { credentials: "same-origin" });
      if (!resp.ok) {
        throw new Error(`Serverfehler (${resp.status})`);
      }
      const data = await resp.json();
      cachedSources = Array.isArray(data) ? data : [];
      renderSources();
      updateStatus(sourceStatus, "", "idle");
    } catch (error) {
      updateStatus(sourceStatus, error.message || "Quellen konnten nicht geladen werden", "error");
    }
  }

  function renderSources() {
    if (!sourcesList) {
      return;
    }
    if (!cachedSources.length) {
      sourcesList.innerHTML = '<p class="sources-empty">Noch keine Quellen hinterlegt.</p>';
      return;
    }

    const rows = cachedSources
      .map((source) => {
        const statusLabel = source.enabled ? "Aktiv" : "Deaktiviert";
        const toggleLabel = source.enabled ? "Deaktivieren" : "Aktivieren";
        const interval = source.interval_minutes ?? 0;
        const lastRun = source.last_run_at ? new Date(source.last_run_at).toLocaleString() : "–";
        return `
          <tr data-source-id="${source.id}">
            <td>${source.name}</td>
            <td>${source.type.toUpperCase()}</td>
            <td><a href="${source.endpoint}" target="_blank" rel="noopener">${source.endpoint}</a></td>
            <td>${interval} min</td>
            <td>${statusLabel}</td>
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
              <th>Name</th>
              <th>Typ</th>
              <th>Feed</th>
              <th>Intervall</th>
              <th>Status</th>
              <th>Letzter Lauf</th>
              <th>Aktionen</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
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

  if (sourceForm) {
    sourceForm.addEventListener("submit", createSource);
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

