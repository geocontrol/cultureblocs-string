// IndexedDB for Rounds. DB 'rounds': 'kv' (plan, cached stands, settings)
// and 'queue' (beads awaiting a reachable String). Browser-only.
const DB = 'rounds', VER = 1;

export function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv', { keyPath: 'k' });
      if (!db.objectStoreNames.contains('queue')) db.createObjectStore('queue', { keyPath: 'dedupeKey' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(db, store, mode, fn) {
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const r = fn(t.objectStore(store));
    t.oncomplete = () => resolve(r?.result);
    t.onerror = () => reject(t.error);
  });
}

const get = (db, k) => tx(db, 'kv', 'readonly', s => s.get(k)).then(r => r?.v);
const put = (db, k, v) => tx(db, 'kv', 'readwrite', s => s.put({ k, v }));

export const getPlan      = db => get(db, 'plan').then(p => p || {});
export const savePlan     = (db, plan) => put(db, 'plan', plan);
export const cacheStands  = (db, stands) => put(db, 'stands', stands);
export const cachedStands = db => get(db, 'stands').then(s => s || []);
export const getSettings  = db => get(db, 'settings').then(s => s || {});
export const saveSettings = (db, s) => put(db, 'settings', s);

export const queueBead    = (db, rec) => tx(db, 'queue', 'readwrite', s => s.put(rec));
export const queuedBeads  = db => tx(db, 'queue', 'readonly', s => s.getAll());
export async function clearQueued(db, keys) {
  for (const k of keys) await tx(db, 'queue', 'readwrite', s => s.delete(k));
}
