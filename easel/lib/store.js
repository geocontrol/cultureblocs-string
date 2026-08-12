// IndexedDB wrapper for Easel. DB 'easel': stores 'works' (keyPath id),
// 'blobs' (keyPath hash), 'session' (keyPath k). Browser-only.
const DB = 'easel', VER = 1;

export function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('works')) db.createObjectStore('works', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('blobs')) db.createObjectStore('blobs', { keyPath: 'hash' });
      if (!db.objectStoreNames.contains('session')) db.createObjectStore('session', { keyPath: 'k' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(db, store, mode, fn) {
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    const r = fn(s);
    t.oncomplete = () => resolve(r?.result);
    t.onerror = () => reject(t.error);
  });
}

export const saveWork   = (db, w)    => tx(db, 'works',  'readwrite', s => s.put(w));
export const getWork    = (db, id)   => tx(db, 'works',  'readonly',  s => s.get(id));
export const deleteWork = (db, id)   => tx(db, 'works',  'readwrite', s => s.delete(id));
export const listWorks  = (db)       => tx(db, 'works',  'readonly',  s => s.getAll());
export const putBlob    = (db, h, b) => tx(db, 'blobs',  'readwrite', s => s.put({ hash: h, blob: b }));
export const getBlob    = (db, h)    => tx(db, 'blobs',  'readonly',  s => s.get(h));
export const setSession = (db, k, v) => tx(db, 'session','readwrite', s => s.put({ k, v }));
export const getSession = (db, k)    => tx(db, 'session','readonly',  s => s.get(k));

/* Blobs are content-addressed, so one row can back several works. Rather than
 * keep refcounts — which drift the moment a write is interrupted — derive the
 * live set from the works themselves and sweep whatever no longer appears.
 * Pure, so it is unit-tested; pruneOrphanBlobs applies it to the stores. */
export function orphanedHashes(works, storedHashes) {
  const live = new Set();
  for (const w of works) for (const h of (w?.imageHashes || [])) live.add(h);
  return storedHashes.filter(h => !live.has(h));
}

/* Delete blob rows no surviving work references. Call after removing a work
 * (or after dropping images from one). Returns the hashes it swept. */
export async function pruneOrphanBlobs(db) {
  const works = await listWorks(db);
  const stored = await tx(db, 'blobs', 'readonly', s => s.getAllKeys());
  const orphans = orphanedHashes(works, stored || []);
  for (const h of orphans) await tx(db, 'blobs', 'readwrite', s => s.delete(h));
  return orphans;
}

// sha256 hex of a Blob (content addressing for dedupe).
export async function hashBlob(blob) {
  const buf = await blob.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', buf);
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}
