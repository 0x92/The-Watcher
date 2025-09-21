export function initHeatmap() {
  const form = document.getElementById("heatmap-filters");
  const heatmapDom = document.getElementById("heatmap-chart");
  const timelineDom = document.getElementById("timeline-chart");
  const statusEl = document.querySelector("#heatmap-dashboard .status-message");
  const statsContainer = document.querySelector("#heatmap-meta .heatmap-stats");
  const reloadButton = document.getElementById("heatmap-reload");

  if (!form || !heatmapDom || !timelineDom || !statusEl || !statsContainer || !reloadButton) {
    return;
  }

  const heatmapChart = window.echarts?.init(heatmapDom);
  const timelineChart = window.echarts?.init(timelineDom);
  if (!heatmapChart || !timelineChart) {
    console.warn("ECharts not available – skipping heatmap init");
    return;
  }

  let eventSource = null;

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }

  function getFilters() {
    const data = new FormData(form);
    const interval = data.get("interval") || "24h";
    const valueMin = Math.max(0, Number(data.get("value_min")) || 0);
    const refresh = Number(data.get("refresh")) || 0;
    const sources = (data.get("sources") || "")
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    return {
      interval,
      valueMin,
      refresh,
      sources,
    };
  }

  function buildQuery(filters) {
    const params = new URLSearchParams();
    params.set("interval", filters.interval);
    params.set("value_min", String(filters.valueMin));
    if (filters.sources.length) {
      params.set("sources", filters.sources.join(","));
    }
    return params;
  }

  function renderStats(meta) {
    const entries = [
      ["Buckets", meta.bucket_count ?? "-"],
      ["Bucket-Minuten", meta.bucket_minutes ?? "-"],
      ["Items", meta.item_count ?? 0],
      ["Alerts", meta.event_count ?? 0],
    ];
    if (meta.source_totals) {
      Object.entries(meta.source_totals)
        .slice(0, 8)
        .forEach(([source, count]) => entries.push([source, count]));
    }
    statsContainer.innerHTML = entries
      .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
      .join("");
  }

  function renderHeatmap(data) {
    const buckets = data.buckets || [];
    const sources = data.series ? data.series.map((series) => series.source) : [];

    if (!buckets.length || !sources.length) {
      heatmapChart.clear();
      heatmapChart.setOption({
        title: { text: "Keine Daten im ausgewählten Zeitraum", left: "center", textStyle: { color: "#64748b" } },
      });
      return;
    }

    const bucketLabels = buckets.map((iso) => new Date(iso).toLocaleString());

    const heatmapData = [];
    let maxCount = 0;
    data.series.forEach((series, yIndex) => {
      series.counts.forEach((count, xIndex) => {
        heatmapData.push([xIndex, yIndex, count]);
        if (count > maxCount) {
          maxCount = count;
        }
      });
    });

    heatmapChart.setOption({
      tooltip: {
        position: "top",
        formatter: (params) => {
          const value = params.data[2];
          if (!value) {
            return "Keine Ereignisse";
          }
          return `${sources[params.data[1]]}<br>${bucketLabels[params.data[0]]}<br>Events: ${value}`;
        },
      },
      grid: {
        left: 90,
        right: 20,
        top: 20,
        bottom: 60,
      },
      xAxis: {
        type: "category",
        data: bucketLabels,
        axisLabel: { rotate: -45, color: "#475569" },
      },
      yAxis: {
        type: "category",
        data: sources,
        axisLabel: { color: "#475569" },
      },
      visualMap: {
        min: 0,
        max: Math.max(1, maxCount),
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 10,
      },
      series: [
        {
          name: "Events",
          type: "heatmap",
          data: heatmapData,
          label: {
            show: true,
            color: "#0f172a",
            formatter: (params) => (params.data[2] ? String(params.data[2]) : ""),
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(0, 0, 0, 0.5)",
            },
          },
        },
      ],
    });
  }

  function renderTimeline(data) {
    const points = (data.timeline || []).map((entry) => ({
      value: [entry.at, entry.severity || 0],
      alert: entry.alert,
      severity: entry.severity || 0,
    }));

    if (!points.length) {
      timelineChart.clear();
      timelineChart.setOption({
        title: { text: "Keine Alerts", left: "center", textStyle: { color: "#64748b" } },
      });
      return;
    }

    const maxSeverity = Math.max(...points.map((point) => point.severity), 1);

    timelineChart.setOption({
      tooltip: {
        trigger: "item",
        formatter: (params) => {
          const date = new Date(params.value[0]);
          return `${params.data.alert}<br>${date.toLocaleString()}<br>Severity: ${params.data.severity}`;
        },
      },
      xAxis: {
        type: "time",
        axisLabel: { color: "#475569" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: Math.max(maxSeverity, 1),
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      series: [
        {
          type: "scatter",
          data: points,
          symbolSize: (val) => 10 + (val[1] || 0) * 4,
          itemStyle: {
            color: "#f97316",
          },
        },
      ],
    });
  }

  function applyPayload(payload) {
    renderHeatmap(payload);
    renderTimeline(payload);
    renderStats(payload.meta || {});
    setStatus("idle", `Aktualisiert (${payload.meta?.item_count ?? 0} Items)`);
  }

  async function loadOnce() {
    const filters = getFilters();
    const params = buildQuery(filters);
    setStatus("loading", "Lade Daten...");
    const response = await fetch(`/api/analytics/heatmap?${params.toString()}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Server antwortete mit ${response.status}`);
    }
    const payload = await response.json();
    applyPayload(payload);
    return filters;
  }

  function closeEventSource() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function startEventSource(filters) {
    closeEventSource();
    if (!filters.refresh) {
      return;
    }
    const params = buildQuery(filters);
    params.set("refresh", String(filters.refresh));
    eventSource = new EventSource(`/stream/analytics/heatmap?${params.toString()}`);
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.error) {
          setStatus("error", payload.error);
          return;
        }
        applyPayload(payload);
      } catch (error) {
        console.error("SSE parse failed", error);
      }
    };
    eventSource.onerror = () => {
      setStatus("error", "Stream unterbrochen");
      closeEventSource();
    };
  }

  function refreshData() {
    loadOnce()
      .then((filters) => {
        startEventSource(filters);
      })
      .catch((error) => {
        console.error("Heatmap fetch failed", error);
        setStatus("error", error.message || "Unbekannter Fehler");
      });
  }

  form.addEventListener("change", (event) => {
    if (
      event.target.matches("select[name='interval']") ||
      event.target.matches("input[name='value_min']") ||
      event.target.matches("select[name='refresh']") ||
      event.target.matches("input[name='sources']")
    ) {
      refreshData();
    }
  });

  reloadButton.addEventListener("click", () => {
    refreshData();
  });

  window.addEventListener("beforeunload", () => {
    closeEventSource();
  });

  refreshData();
}
