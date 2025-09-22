const PAGE_SIZE = 25;
const STREAM_BATCH_SIZE = 20;
const MAX_ITEMS = 120;

function formatRelative(date) {
  const diff = Date.now() - date.getTime();
  if (Number.isNaN(diff)) {
    return '';
  }
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) {
    return 'gerade eben';
  }
  if (diff < hour) {
    const value = Math.round(diff / minute);
    return `${value} Min.`;
  }
  if (diff < day) {
    const value = Math.round(diff / hour);
    return `${value} Std.`;
  }
  const value = Math.round(diff / day);
  return `${value} Tg.`;
}

function resolveRange(value) {
  if (!value) {
    return null;
  }
  const now = Date.now();
  if (value.endsWith('h') && Number.isFinite(Number.parseInt(value, 10))) {
    const hours = Number.parseInt(value, 10);
    return new Date(now - hours * 60 * 60 * 1000).toISOString();
  }
  if (value.endsWith('d') && Number.isFinite(Number.parseInt(value, 10))) {
    const days = Number.parseInt(value, 10);
    return new Date(now - days * 24 * 60 * 60 * 1000).toISOString();
  }
  return null;
}

function buildParams(form) {
  const formData = new FormData(form);
  const params = new URLSearchParams();
  const range = formData.get('range');
  const since = resolveRange(typeof range === 'string' ? range : '');
  if (since) {
    params.set('from', since);
  }
  for (const [key, value] of formData.entries()) {
    if (!value || key === 'range') {
      continue;
    }
    params.set(key, value);
  }
  params.set('page', '1');
  params.set('size', String(PAGE_SIZE));
  return params;
}

function updateCounter(counterEl, count) {
  if (!counterEl) {
    return;
  }
  counterEl.textContent = `${count} ${count === 1 ? 'Eintrag' : 'Einträge'}`;
}

function setStatus(el, state, message) {
  if (!el) {
    return;
  }
  el.dataset.state = state;
  el.textContent = message;
}

function createItemNode(item) {
  const li = document.createElement('li');
  li.className = 'feed-item';
  li.dataset.itemId = String(item.id || '');

  const fetchedAt = item.fetched_at ? new Date(item.fetched_at) : null;

  const meta = document.createElement('div');
  meta.className = 'feed-item__meta';

  const source = document.createElement('span');
  source.className = 'feed-item__source';
  source.textContent = item.source || 'Quelle unbekannt';
  meta.appendChild(source);

  if (item.lang) {
    const lang = document.createElement('span');
    lang.className = 'feed-item__lang';
    lang.textContent = item.lang;
    meta.appendChild(lang);
  }

  if (fetchedAt) {
    const time = document.createElement('span');
    time.className = 'feed-item__time';
    time.dataset.fetchedAt = fetchedAt.toISOString();
    time.textContent = formatRelative(fetchedAt);
    time.title = fetchedAt.toLocaleString();
    meta.appendChild(time);
  }

  li.appendChild(meta);

  const title = document.createElement('h3');
  title.className = 'feed-item__title';
  const link = document.createElement('a');
  link.href = item.url || '#';
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = item.title || item.url || 'Unbenanntes Item';
  title.appendChild(link);
  li.appendChild(title);

  if (item.published_at) {
    const published = document.createElement('div');
    published.className = 'feed-item__time';
    const publishedDate = new Date(item.published_at);
    published.dataset.publishedAt = publishedDate.toISOString();
    published.textContent = `Publiziert ${formatRelative(publishedDate)}`;
    published.title = publishedDate.toLocaleString();
    li.appendChild(published);
  }

  if (item.gematria && typeof item.gematria === 'object') {
    const entries = Object.entries(item.gematria);
    if (entries.length) {
      entries.sort((a, b) => a[0].localeCompare(b[0]));
      const list = document.createElement('ul');
      list.className = 'feed-item__gematria';
      for (const [scheme, value] of entries) {
        const badge = document.createElement('li');
        badge.textContent = `${scheme}: ${value}`;
        list.appendChild(badge);
      }
      li.appendChild(list);
    }
  }

  return li;
}

function refreshRelativeTimes(list) {
  const times = list.querySelectorAll('.feed-item__time[data-fetched-at]');
  times.forEach((node) => {
    const iso = node.dataset.fetchedAt;
    if (!iso) return;
    const date = new Date(iso);
    node.textContent = formatRelative(date);
  });
  const publishedNodes = list.querySelectorAll('.feed-item__time[data-published-at]');
  publishedNodes.forEach((node) => {
    const iso = node.dataset.publishedAt;
    if (!iso) return;
    const date = new Date(iso);
    node.textContent = `Publiziert ${formatRelative(date)}`;
  });
}

export function initStream() {
  const root = document.querySelector('[data-stream-feed]');
  const list = document.querySelector('[data-stream-list]');
  const form = document.querySelector('[data-stream-filter]');
  const statusEl = document.querySelector('[data-stream-status]');
  const counterEl = document.querySelector('[data-stream-counter]');

  if (!root || !list || !form || !statusEl) {
    return;
  }

  const seenIds = new Set();
  let eventSource = null;
  let currentCursor = null;
  let refreshTimer = null;

  function stopStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function renderItems(items, { replace = false, prepend = false } = {}) {
    if (!Array.isArray(items)) {
      return;
    }
    if (replace) {
      seenIds.clear();
      list.innerHTML = '';
      currentCursor = null;
    }
    if (!items.length) {
      list.setAttribute('aria-busy', 'false');
      if (!list.children.length) {
        list.innerHTML = '<li class="empty-state">Keine Einträge gefunden.</li>';
      }
      return;
    }
    if (list.querySelector('.empty-state')) {
      list.innerHTML = '';
    }

    const insertItems = prepend ? [...items].reverse() : items;

    for (const item of insertItems) {
      if (!item || typeof item.id === 'undefined') {
        continue;
      }
      if (seenIds.has(item.id)) {
        continue;
      }
      const node = createItemNode(item);
      if (prepend) {
        list.prepend(node);
      } else {
        list.append(node);
      }
      seenIds.add(item.id);
    }

    while (list.children.length > MAX_ITEMS) {
      const last = list.lastElementChild;
      if (!last) {
        break;
      }
      const id = Number.parseInt(last.dataset.itemId || '', 10);
      if (!Number.isNaN(id)) {
        seenIds.delete(id);
      }
      list.removeChild(last);
    }

    list.setAttribute('aria-busy', 'false');
    updateCounter(counterEl, seenIds.size);
  }

  async function loadInitial(params) {
    const url = new URL('/api/items', window.location.origin);
    url.search = params.toString();
    list.setAttribute('aria-busy', 'true');
    const response = await fetch(url.toString(), {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) {
      let message = `Request ${url.pathname} fehlgeschlagen (${response.status})`;
      try {
        const errorPayload = await response.json();
        if (errorPayload && typeof errorPayload.error === 'string') {
          message = errorPayload.error;
        }
      } catch (err) {
        console.warn('Could not parse error payload', err);
      }
      throw new Error(message);
    }
    const data = await response.json();
    const items = Array.isArray(data.items) ? data.items : [];
    renderItems(items, { replace: true });
    currentCursor = items.reduce((max, item) => (item && item.id > max ? item.id : max), currentCursor || 0);
    updateCounter(counterEl, seenIds.size);
    return data;
  }

  function startStream(params) {
    stopStream();
    const streamParams = new URLSearchParams(params);
    streamParams.set('limit', String(STREAM_BATCH_SIZE));
    if (currentCursor) {
      streamParams.set('after_id', String(currentCursor));
    }
    const url = `/stream/live?${streamParams.toString()}`;
    eventSource = new EventSource(url);
    eventSource.onopen = () => {
      setStatus(statusEl, 'idle', 'Live-Verbindung aktiv.');
    };
    eventSource.onerror = () => {
      setStatus(statusEl, 'loading', 'Verbindung unterbrochen, versuche erneut...');
    };
    eventSource.onmessage = (event) => {
      if (!event.data) {
        return;
      }
      try {
        const payload = JSON.parse(event.data);
        const items = Array.isArray(payload.items) ? payload.items : [];
        if (!items.length) {
          return;
        }
        renderItems(items, { prepend: true });
        const highest = items.reduce((max, item) => (item && item.id > max ? item.id : max), 0);
        const cursorValue = typeof payload.cursor === 'number' ? payload.cursor : 0;
        currentCursor = Math.max(currentCursor || 0, highest, cursorValue);
      } catch (err) {
        console.error('stream payload parse failed', err);
      }
    };
  }

  async function applyFilters() {
    try {
      stopStream();
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      setStatus(statusEl, 'loading', 'Aktualisiere Live-Feed...');
      const params = buildParams(form);
      params.set('size', String(PAGE_SIZE));
      const data = await loadInitial(params);
      const count = Array.isArray(data.items) ? data.items.length : 0;
      if (!count) {
        setStatus(statusEl, 'idle', 'Keine Items im Zeitraum gefunden.');
      } else {
        setStatus(statusEl, 'idle', 'Live-Daten synchronisiert.');
      }
      startStream(params);
      refreshTimer = window.setInterval(() => refreshRelativeTimes(list), 60_000);
      refreshRelativeTimes(list);
    } catch (error) {
      console.error('stream load failed', error);
      setStatus(statusEl, 'error', error.message || 'Live-Feed konnte nicht geladen werden.');
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    applyFilters();
  });

  form.addEventListener('reset', () => {
    window.setTimeout(() => {
      applyFilters();
    }, 0);
  });

  applyFilters();

  window.addEventListener('beforeunload', () => {
    stopStream();
    if (refreshTimer) {
      clearInterval(refreshTimer);
    }
  });

  root.addEventListener('mouseleave', () => refreshRelativeTimes(list));
}
