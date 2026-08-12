/* Export / import of the whole local library as one JSON file.
 *
 * Easel keeps everything in the browser, so without this a cleared profile
 * takes every unpublished draft with it. Images are inlined as base64 — that
 * costs about a third in size, but keeps a backup to a single file the user
 * can see, copy and store anywhere, with no dependency on a zip writer.
 *
 * Pure by design: the browser glue in easel.js reads blobs and hands bytes in,
 * so all of the format logic is unit-tested. */

export const EXPORT_TYPE = 'com.cultureblocs.easel.export';
export const EXPORT_VERSION = 1;

/* btoa needs a binary string, and String.fromCharCode(...bytes) throws once the
 * array is large enough to overflow the argument stack — so chunk it. */
export function bytesToBase64(bytes) {
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

export function base64ToBytes(b64) {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/* works: the stored work records, verbatim.
 * blobs: [{hash, mimeType, bytes}] for every image those works reference. */
export function buildExport(works, blobs, exportedAt) {
  const doc = {
    $type: EXPORT_TYPE,
    version: EXPORT_VERSION,
    exportedAt,
    works,
    blobs: {},
  };
  for (const b of blobs) {
    doc.blobs[b.hash] = { mimeType: b.mimeType || 'application/octet-stream', data: bytesToBase64(b.bytes) };
  }
  return doc;
}

export function parseImport(doc) {
  if (!doc || doc.$type !== EXPORT_TYPE) throw new Error('not an Easel export file');
  if (doc.version !== EXPORT_VERSION) throw new Error(`unsupported export version: ${doc.version}`);
  if (!Array.isArray(doc.works)) throw new Error('export has no works array');
  const blobs = Object.entries(doc.blobs || {}).map(([hash, b]) => ({
    hash, mimeType: b.mimeType || 'application/octet-stream', bytes: base64ToBytes(b.data),
  }));
  return { works: doc.works, blobs };
}

/* Importing must never silently overwrite work already in this browser, so an
 * id that is already present is reported rather than replaced. */
export function planMerge(existingIds, incomingWorks) {
  const have = new Set(existingIds);
  const toAdd = [], skipped = [];
  for (const w of incomingWorks) (have.has(w.id) ? skipped : toAdd).push(have.has(w.id) ? w.id : w);
  return { toAdd, skipped };
}
