// Pure assembly of creative.work / creative.profile record bodies + drift.
function present(v) {
  if (v == null) return false;
  if (typeof v === 'string') return v.trim() !== '';
  if (Array.isArray(v)) return v.length > 0;
  return true;
}
function put(obj, key, val) { if (present(val)) obj[key] = val; }

/* Wrap an uploaded blob ref as a com.cultureblocs.defs#imageRef.
 * `meta` is what the editor captured when the image was staged:
 * {alt, width, height}. Blank alt is omitted rather than published as "" —
 * an empty alt is a positive claim that an image is decorative, which is not
 * the same as never having been asked. */
export function toImageRef(blobRef, meta = {}) {
  const ref = { image: blobRef };
  if (typeof meta.alt === 'string' && meta.alt.trim()) ref.alt = meta.alt.trim();
  const w = meta.width, h = meta.height;
  if (Number.isInteger(w) && Number.isInteger(h) && w > 0 && h > 0) {
    ref.aspectRatio = { width: w, height: h };
  }
  return ref;
}

/* What this work's images WOULD publish as, right now.
 *
 * Drift compares the stored publishedCanonical against assembleWork(body, …).
 * Alt text and dimensions are not in `body` — they live in `imageMeta` — so
 * feeding the already-published images back in would hide an alt-only edit and
 * the work would never show as edited. Rebuilding from the published blob refs
 * plus current metadata makes every editable field count. */
export function projectImages(work) {
  const published = work.publishedImages || [];
  return (work.imageHashes || []).map((hash, i) => {
    const entry = published[i];
    if (!entry) return null;
    const blobRef = entry.image || entry;      // imageRef, or a legacy bare blob
    return toImageRef(blobRef, (work.imageMeta || {})[hash] || {});
  }).filter(Boolean);
}

export function assembleWork(f, imageBlobRefs = []) {
  const body = { $type: 'com.cultureblocs.creative.work', title: f.title, createdAt: f.createdAt };
  put(body, 'description', f.description);
  put(body, 'completionDate', f.completionDate);
  put(body, 'referenceUrl', f.referenceUrl);
  put(body, 'links', f.links);
  put(body, 'tags', f.tags);
  put(body, 'externalIds', f.externalIds);
  if (present(imageBlobRefs)) body.images = imageBlobRefs;
  return body;
}

export function assembleProfile(f) {
  const body = { $type: 'com.cultureblocs.creative.profile', name: f.name, createdAt: f.createdAt };
  put(body, 'bio', f.bio);
  put(body, 'disciplines', f.disciplines);
  put(body, 'based', f.based);
  put(body, 'links', f.links);
  put(body, 'externalIds', f.externalIds);
  return body;
}

export function canonicalJSON(obj) {
  return JSON.stringify(sortKeys(obj));
}
function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    return Object.keys(v).sort().reduce((o, k) => { o[k] = sortKeys(v[k]); return o; }, {});
  }
  return v;
}

export function isDrifted(publishedCanonical, currentBody) {
  return publishedCanonical !== canonicalJSON(currentBody);
}

/* ---------- restoring published works onto a new device ---------- */

export function rkeyFromUri(uri) {
  return String(uri || '').split('/').pop();
}

/* Turn a record fetched from the repo back into the local work shape.
 * The rkey becomes the local id, so editing a restored work still updates the
 * same record rather than creating a duplicate.
 *
 * imageHashes are the sha256s of the downloaded blobs (the local blob store is
 * content-addressed), so they are computed by the caller and passed in.
 *
 * publishedCanonical is derived from assembleWork rather than from the raw
 * record: it has to agree with what a later save would produce, or the work
 * would read as edited the moment it lands. Any field assembleWork does not
 * emit is therefore not round-tripped. */
export function workFromRecord(record, imageHashes, now) {
  const v = record?.value || {};
  const body = {
    title: v.title || '',
    description: v.description || '',
    completionDate: v.completionDate || '',
    referenceUrl: v.referenceUrl || '',
    links: v.links || [],
    tags: v.tags || [],
    createdAt: v.createdAt,
  };
  const publishedImages = v.images || [];
  /* Rebuild the editor-side metadata map from what was published, keyed by the
   * caller's content hashes (same order as publishedImages). A legacy bare-blob
   * record yields empty metadata rather than failing the restore. */
  const imageMeta = {};
  (imageHashes || []).forEach((hash, i) => {
    const entry = publishedImages[i] || {};
    const meta = {};
    if (typeof entry.alt === 'string' && entry.alt) meta.alt = entry.alt;
    const ar = entry.aspectRatio;
    if (Number.isInteger(ar?.width) && Number.isInteger(ar?.height)) {
      meta.width = ar.width; meta.height = ar.height;
    }
    imageMeta[hash] = meta;
  });
  return {
    id: rkeyFromUri(record.uri),
    state: 'published',
    body,
    imageHashes,
    imageMeta,
    createdAt: v.createdAt,
    updatedAt: now,
    publishedUri: record.uri,
    publishedCid: record.cid,
    publishedImages,
    publishedCanonical: canonicalJSON(assembleWork(body, publishedImages)),
  };
}
