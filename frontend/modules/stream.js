const ESCAPE_MAP = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeHTML(value) {
  if (value == null) {
    return '';
  }
  return String(value).replace(/[&<>"']/g, (char) => ESCAPE_MAP[char] || char);
}

function formatDate(value) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function buildQuery(filters) {
  const params = new URLSearchParams();
  params.set('limit', String(filters.limit));
  if (filters.sources.length) {
    params.set('sources', filters.sources.join(','));
  }
  if (filters.since) {
    params.set('since', filters.since);
  }
  return params;
}

function normalizeLimit(value) {
  const num = Number(value);
  if (Number.isNaN(num) || num <= 0) {
    return 50;
  }
  return Math.max(1, Math.min(num, 200));
}

function normalizeRefresh(value) {
  const num = Number(value);
  if (Number.isNaN(num) || num < 0) {
    return 0;
  }
  return Math.min(num, 300);
}

function tagLabel(tag) {
  if (!tag) {
    return '';
  }
  const label = escapeHTML(tag.label || 'Tag');
  if (tag.weight == null) {
    return label;
  }
  const weight = Number(tag.weight);
  if (Number.isNaN(weight)) {
    return label;
  }
  return `${label} (${weight.toFixed(2)})`;
}

function buildGematriaList(gematria) {
  if (!gematria) {
    return '';
  }
  const entries = Object.entries(gematria);
  if (!entries.length) {
    return '';
  }
  const sorted = entries
    .map(([scheme, value]) => [scheme, Number(value)])
    .filter(([, value]) => !Number.isNaN(value))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);
  if (!sorted.length) {
    return '';
  }
  const parts = sorted.map(
    ([scheme, value]) => `<span>${escapeHTML(scheme)}: <strong>${value}</strong></span>`,
  );
  return `<div class="feed-gematria">${parts.join('')}</div>`;
}

export function initStream() {
  const form = document.getElementById('stream-filters');
  const statusEl = document.querySelector('[data-stream-status]');
  const listEl = document.querySelector('[data-stream-list]');
  const metaEl = document.querySelector('[data-stream-meta]');
  const reloadButton = document.getElementById('stream-reload');
  const liveRegion = document.querySelector('[data-stream-region]');

  if (!form || !statusEl || !listEl || !metaEl || !reloadButton) {
    return;
  }

  let eventSource = null;

  function setBusy(isBusy) {
    if (liveRegion) {
      liveRegion.setAttribute('aria-busy', isBusy ? 'true' : 'false');
    }
  }

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }

  function getFilters() {
    const data = new FormData(form);
    const sources = (data.get('sources') || '')
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
    const limit = normalizeLimit(data.get('limit'));
    const refresh = normalizeRefresh(data.get('refresh'));
    const sinceRaw = data.get('since');
    const since = sinceRaw ? String(sinceRaw) : '';
    return { sources, limit, refresh, since };
  }

  function renderMeta(meta = {}) {
    const count = meta.count ?? 0;
    const updated = meta.latest_fetched_at ? formatDate(meta.latest_fetched_at) : '-';
    const since = meta.since ? formatDate(meta.since) : '';
    const sources = Array.isArray(meta.sources) && meta.sources.length
      ? meta.sources.join(', ')
      : '-';

    const entries = [
      ['Items', count],
      ['Aktualisiert', updated],
      ['Quellen', sources],
    ];
    if (since) {
      entries.push(['Seit', since]);
    }

    metaEl.innerHTML = entries
      .map(([label, value]) => `<dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd>`)
      .join('');
  }

  function renderItems(items = []) {
    if (!Array.isArray(items) || !items.length) {
      listEl.innerHTML = '<li class="empty-state">Keine Items gefunden.</li>';
      return;
    }

    const html = items
      .map((item) => {
        const title = escapeHTML(item.title || 'Ohne Titel');
        const source = item.source ? `<span class="feed-item-source">${escapeHTML(item.source)}</span>` : '';
        const link = item.url
          ? `<a href="${escapeHTML(item.url)}" target="_blank" rel="noopener">${title}</a>`
          : `<span>${title}</span>`;
        const published = item.published_at ? formatDate(item.published_at) : '-';
        const fetched = item.fetched_at ? formatDate(item.fetched_at) : '-';
        const lang = item.lang ? `Sprache: ${escapeHTML(item.lang)}` : '';
        const author = item.author ? `Autor: ${escapeHTML(item.author)}` : '';
        const tags = Array.isArray(item.tags)
          ? item.tags.map((tag) => `<li>${tagLabel(tag)}</li>`).join('')
          : '';
        const tagsBlock = tags ? `<ul class="feed-tags">${tags}</ul>` : '';
        const gematriaBlock = buildGematriaList(item.gematria);

        const metaParts = [`Eingelesen: ${fetched}`, `Publiziert: ${published}`];
        if (lang) metaParts.push(lang);
        if (author) metaParts.push(author);

        return `
          <li class="feed-item">
            <div class="feed-item-header">
              <h2 class="feed-item-title">${link}</h2>
              ${source}
            </div>
            <div class="feed-item-meta">${metaParts.map(escapeHTML).join(' · ')}</div>
            ${gematriaBlock}
            ${tagsBlock}
          </li>
        `;
      })
      .join('');

    listEl.innerHTML = html;
  }

  function applyPayload(payload) {
    const items = payload?.items || [];
    renderItems(items);
    renderMeta(payload?.meta || {});
    const total = payload?.meta?.count ?? items.length;
    setStatus('idle', `Live-Daten aktualisiert (${total} Items)`);
    setBusy(false);
  }

  async function loadOnce() {
    const filters = getFilters();
    const params = buildQuery(filters);
    setStatus('loading', 'Lade Items...');
    setBusy(true);
    const response = await fetch(`/api/items?${params.toString()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
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
    params.set('refresh', String(filters.refresh));
    eventSource = new EventSource(`/stream/items?${params.toString()}`);
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.error) {
          setStatus('error', payload.error);
          setBusy(false);
          return;
        }
        applyPayload(payload);
      } catch (error) {
        console.error('Stream parse failed', error);
        setStatus('error', 'Stream-Daten konnten nicht verarbeitet werden.');
        setBusy(false);
      }
    };
    eventSource.onerror = () => {
      setStatus('error', 'Stream unterbrochen');
      setBusy(false);
      closeEventSource();
    };
  }

  function refreshData() {
    loadOnce()
      .then((filters) => {
        startEventSource(filters);
      })
      .catch((error) => {
        console.error('Stream fetch failed', error);
        setStatus('error', error.message || 'Unbekannter Fehler');
        setBusy(false);
        closeEventSource();
      });
  }

  form.addEventListener('change', (event) => {
    if (
      event.target.matches("input[name='sources']") ||
      event.target.matches("select[name='limit']") ||
      event.target.matches("select[name='refresh']") ||
      event.target.matches("input[name='since']")
    ) {
      refreshData();
    }
  });

  reloadButton.addEventListener('click', () => {
    refreshData();
  });

  window.addEventListener('beforeunload', () => {
    closeEventSource();
  });

  refreshData();
}

