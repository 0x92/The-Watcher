export function initPatterns() {
  const form = document.getElementById("patterns-filters");
  const list = document.getElementById("patterns-list");
  const statusEl = document.querySelector("#patterns-container .status-message");
  const reloadButton = document.getElementById("patterns-reload");

  if (!form || !list || !statusEl || !reloadButton) {
    return;
  }

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }

  function getFilters() {
    const data = new FormData(form);
    const windowValue = data.get("window") || "24h";
    const limit = Math.max(1, Math.min(Number(data.get("limit")) || 10, 50));
    return { window: windowValue, limit };
  }

  function buildQuery(filters) {
    const params = new URLSearchParams();
    params.set("window", filters.window);
    params.set("limit", String(filters.limit));
    return params.toString();
  }

  function renderPatterns(patterns) {
    list.innerHTML = "";
    if (!patterns.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "Keine Muster gefunden.";
      list.appendChild(empty);
      return;
    }

    patterns.forEach((pattern) => {
      const card = document.createElement("article");
      card.className = "pattern-card";

      const title = document.createElement("h2");
      title.textContent = pattern.label || "Unbenanntes Muster";
      card.appendChild(title);

      const meta = document.createElement("p");
      meta.className = "pattern-meta";
      const created = new Date(pattern.created_at);
      const score = typeof pattern.anomaly_score === "number" ? pattern.anomaly_score.toFixed(3) : "-";
      const size = pattern.meta?.size ?? pattern.item_ids?.length ?? 0;
      meta.textContent = `Anomalie-Score: ${score} • Größe: ${size} • ${created.toLocaleString()}`;
      card.appendChild(meta);

      const terms = document.createElement("ul");
      terms.className = "pattern-terms";
      (pattern.top_terms || []).forEach((term) => {
        const li = document.createElement("li");
        li.textContent = term;
        terms.appendChild(li);
      });
      card.appendChild(terms);

      if (pattern.item_ids?.length) {
        const count = document.createElement("p");
        count.className = "pattern-items";
        count.textContent = `Beobachtete Items: ${pattern.item_ids.join(", ")}`;
        card.appendChild(count);
      }

      list.appendChild(card);
    });
  }

  async function loadPatterns() {
    const filters = getFilters();
    setStatus("loading", "Lade Muster...");

    try {
      const query = buildQuery(filters);
      const response = await fetch(`/api/patterns/latest?${query}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Server antwortete mit ${response.status}`);
      }
      const payload = await response.json();
      renderPatterns(payload.patterns || []);
      const count = payload.meta?.count ?? payload.patterns?.length ?? 0;
      setStatus("idle", `Aktualisiert (${count}).`);
    } catch (error) {
      console.error("Pattern fetch failed", error);
      setStatus("error", error && error.message ? error.message : "Unbekannter Fehler");
    }
  }

  form.addEventListener("change", (event) => {
    if (
      event.target.matches("select[name='window']") ||
      event.target.matches("input[name='limit']")
    ) {
      loadPatterns();
    }
  });

  reloadButton.addEventListener("click", () => {
    loadPatterns();
  });

  loadPatterns();
}
