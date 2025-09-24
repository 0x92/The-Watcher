const storeCache = new Map();

function readFromStorage(key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }
    return parsed;
  } catch (error) {
    console.warn('Failed to parse profile store', { key, error });
    return {};
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function createProfileStore(storageKey) {
  if (storeCache.has(storageKey)) {
    return storeCache.get(storageKey);
  }

  let state = readFromStorage(storageKey);
  const listeners = new Set();

  function persist(next) {
    state = next;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(state));
    } catch (error) {
      console.warn('Failed to persist profile store', { storageKey, error });
    }
    listeners.forEach((listener) => {
      try {
        listener(clone(state));
      } catch (listenerError) {
        console.warn('Profile store listener failed', listenerError);
      }
    });
  }

  function getAll() {
    return clone(state);
  }

  function get(name) {
    return clone(state[name]);
  }

  function save(name, value) {
    if (!name) {
      return;
    }
    const next = { ...state, [name]: value };
    persist(next);
  }

  function replaceAll(next) {
    if (!next || typeof next !== 'object') {
      next = {};
    }
    persist({ ...next });
  }

  function remove(name) {
    if (!name) {
      return;
    }
    if (!(name in state)) {
      return;
    }
    const next = { ...state };
    delete next[name];
    persist(next);
  }

  function clear() {
    persist({});
  }

  function subscribe(listener) {
    if (typeof listener !== 'function') {
      return () => {};
    }
    listeners.add(listener);
    listener(clone(state));
    return () => listeners.delete(listener);
  }

  function handleStorage(event) {
    if (event.storageArea !== window.localStorage) {
      return;
    }
    if (event.key && event.key !== storageKey) {
      return;
    }
    state = readFromStorage(storageKey);
    listeners.forEach((listener) => {
      try {
        listener(clone(state));
      } catch (listenerError) {
        console.warn('Profile store listener failed', listenerError);
      }
    });
  }

  window.addEventListener('storage', handleStorage);

  const api = {
    getAll,
    get,
    save,
    replaceAll,
    remove,
    clear,
    subscribe,
  };

  storeCache.set(storageKey, api);
  return api;
}
