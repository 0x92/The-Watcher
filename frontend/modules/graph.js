export function initGraph() {
  const cytoscapeLib = window.cytoscape;
  if (!cytoscapeLib) {
    console.warn("Cytoscape not available – skipping graph init");
    return;
  }

  const form = document.getElementById("graph-filters");
  const container = document.getElementById("graph");
  const statusEl = document.querySelector("#graph-summary .status-message");
  const statsEl = document.querySelector("#graph-summary .graph-stats");
  const refreshSelect = document.getElementById("graph-refresh");
  const reloadButton = document.getElementById("graph-reload");
  const exportPngButton = document.getElementById("graph-export-png");
  const exportJsonButton = document.getElementById("graph-export-json");

  if (!form || !container || !statusEl || !statsEl) {
    return;
  }

  let cy = createGraph(container);
  let refreshTimer = null;
  let lastData = null;
  let isLoading = false;

  function createGraph(target) {
    return cytoscapeLib({
      container: target,
      wheelSensitivity: 0.2,
      maxZoom: 3,
      minZoom: 0.2,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "12px",
            "text-wrap": "wrap",
            "text-max-width": "120px",
            color: "#0f172a",
            "background-color": "#2563eb",
            width: "mapData(value, 0, 50, 24, 96)",
            height: "mapData(value, 0, 50, 24, 96)",
            "border-width": 2,
            "border-color": "#1e293b",
          },
        },
        {
          selector: "node[kind = 'tag']",
          style: {
            "background-color": "#22c55e",
            "border-color": "#166534",
          },
        },
        {
          selector: "node[kind = 'alert']",
          style: {
            "background-color": "#f97316",
            "border-color": "#c2410c",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 4,
            "border-color": "#0ea5e9",
            "shadow-blur": 16,
            "shadow-color": "#38bdf8",
            "shadow-opacity": 0.6,
          },
        },
        {
          selector: "edge",
          style: {
            width: "mapData(weight, 0, 20, 1, 6)",
            "line-color": "#94a3b8",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#94a3b8",
            opacity: 0.8,
          },
        },
        {
          selector: "edge[kind = 'source_tag']",
          style: {
            "line-color": "#38bdf8",
            "target-arrow-color": "#38bdf8",
          },
        },
        {
          selector: "edge[kind = 'source_alert']",
          style: {
            "line-color": "#facc15",
            "target-arrow-color": "#facc15",
          },
        },
      ],
    });
  }

  function getFilters() {
    const data = new FormData(form);
    const roles = [];
    form.querySelectorAll("input[name='role']").forEach((input) => {
      if (input.checked) {
        roles.push(input.value);
      }
    });
    const limitValue = Math.max(1, Math.min(Number(data.get("limit")) || 50, 200));
    return {
      window: data.get("window") || "24h",
      limit: limitValue,
      roles,
      refresh: Number(data.get("refresh")) || 0,
    };
  }

  function buildQuery(filters) {
    const params = new URLSearchParams();
    if (filters.window) {
      params.set("window", filters.window);
    }
    params.set("limit", String(filters.limit));
    filters.roles.forEach((role) => params.append("role", role));
    return params.toString();
  }

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }

  function updateStats(data) {
    const timestamp = new Date();
    const counts = {
      nodes: data.nodes.length,
      edges: data.edges.length,
      sources: data.nodes.filter((node) => node.kind === "source").length,
      tags: data.nodes.filter((node) => node.kind === "tag").length,
      alerts: data.nodes.filter((node) => node.kind === "alert").length,
    };
    statsEl.innerHTML = `
      <div><strong>Knoten:</strong> ${counts.nodes}</div>
      <div><strong>Kanten:</strong> ${counts.edges}</div>
      <div><strong>Quellen:</strong> ${counts.sources}</div>
      <div><strong>Tags:</strong> ${counts.tags}</div>
      <div><strong>Alerts:</strong> ${counts.alerts}</div>
      <div><small>Stand: ${timestamp.toLocaleTimeString()}</small></div>
    `;
  }

  async function loadGraph() {
    if (isLoading) {
      return;
    }
    const filters = getFilters();
    setStatus("loading", "Lade Graph...");
    isLoading = true;
    try {
      const query = buildQuery(filters);
      const response = await fetch(`/api/graph?${query}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Server antwortete mit ${response.status}`);
      }
      const payload = await response.json();
      lastData = payload;
      renderGraph(payload);
      updateStats(payload);
      setStatus("idle", "Aktualisiert.");
    } catch (error) {
      console.error("Graph fetch failed", error);
      setStatus("error", error && error.message ? error.message : "Unbekannter Fehler");
    } finally {
      isLoading = false;
    }
  }

  function renderGraph(data) {
    const elements = [];
    data.nodes.forEach((node) => {
      elements.push({
        data: {
          id: node.id,
          label: node.label,
          kind: node.kind,
          value: node.value,
          meta: node.meta || {},
        },
      });
    });
    data.edges.forEach((edge) => {
      elements.push({
        data: {
          id: `${edge.source}->${edge.target}:${edge.kind}`,
          source: edge.source,
          target: edge.target,
          weight: edge.weight,
          kind: edge.kind,
          meta: edge.meta || {},
        },
      });
    });

    cy.elements().remove();
    cy.add(elements);

    const layout = cy.layout({
      name: "cose",
      animate: false,
      padding: 30,
      fit: true,
      randomize: elements.length > 150,
    });
    layout.run();
  }

  function scheduleRefresh(seconds) {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    if (seconds > 0) {
      refreshTimer = setInterval(() => {
        if (!document.hidden) {
          loadGraph();
        }
      }, seconds * 1000);
    }
  }

  function handleRefreshChange() {
    const filters = getFilters();
    scheduleRefresh(filters.refresh);
  }

  function download(name, url) {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  function exportPng() {
    if (!cy) {
      return;
    }
    const dataUrl = cy.png({ scale: 2, bg: "#ffffff" });
    download(`graph-${Date.now()}.png`, dataUrl);
  }

  function exportJson() {
    if (!lastData) {
      setStatus("error", "Keine Daten zum Exportieren verfuegbar.");
      return;
    }
    const blob = new Blob([JSON.stringify(lastData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    download(`graph-${Date.now()}.json`, url);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function bindEvents() {
    form.addEventListener("change", (event) => {
      const target = event.target;
      if (
        target.matches("input[name='role']") ||
        target.matches("select[name='window']") ||
        target.matches("input[name='limit']")
      ) {
        loadGraph();
      }
      if (target === refreshSelect) {
        handleRefreshChange();
      }
    });

    reloadButton?.addEventListener("click", () => {
      loadGraph();
    });

    exportPngButton?.addEventListener("click", () => {
      exportPng();
    });

    exportJsonButton?.addEventListener("click", () => {
      exportJson();
    });

    cy.on("tap", "node", (event) => {
      const nodeData = event.target.data();
      const message = `${nodeData.label} (${nodeData.kind}) - Wert ${nodeData.value}`;
      setStatus("info", message);
    });

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        if (refreshTimer) {
          clearInterval(refreshTimer);
          refreshTimer = null;
        }
      } else {
        handleRefreshChange();
        loadGraph();
      }
    });
  }

  bindEvents();
  handleRefreshChange();
  loadGraph();
}
