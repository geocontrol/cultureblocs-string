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
 * plus current metadata makes every editable field count.
 *
 * Pairing is by content hash, via `work.publishedImageHashes` — a array
 * parallel to `work.publishedImages` recording which local hash (if any)
 * produced each published entry. `publishWork` (publish.js) builds it
 * alongside the upload, and `workFromRecord` (restore) builds it by matching
 * fetched blobs back to the record's image entries — so a skipped upload
 * (publish.js's `if (!blob) continue`) or a failed restore fetch
 * (easel.js's restoreFromRepo) never desynchronises the two arrays, even
 * though neither is positionally aligned to the other any more.
 *
 * Works saved before this change have no `publishedImageHashes`. For those,
 * this falls back to the old imageHashes[i] <-> publishedImages[i] index
 * pairing, which carries the original caveat: it's correct only because
 * imageHashes is append-only and Easel has no reorder or delete-image UI,
 * AND because — before this fix — every publish/restore kept the two arrays
 * aligned by position. A legacy work that already suffered the position-drift
 * bug (a skipped restore/publish image) keeps whatever mismatch it already
 * had; the fallback does not retroactively repair it.
 *
 * A hash with no matching published entry (an image added since the last
 * publish) is not dropped: this projection is drift-only — it is compared
 * against publishedCanonical, never published (publishWork builds its own
 * images array from real uploads, in publish.js) — so it's safe to emit a
 * marker that could never appear in a real imageRef. That guarantees the
 * projection differs from anything previously published, so the new image
 * shows up as drift instead of vanishing. */
export function projectImages(work) {
  const published = work.publishedImages || [];
  const byHash = Array.isArray(work.publishedImageHashes) ? work.publishedImageHashes : null;
  return (work.imageHashes || []).map((hash, i) => {
    const idx = byHash ? byHash.indexOf(hash) : i;
    const entry = idx >= 0 ? published[idx] : undefined;
    const meta = (work.imageMeta || {})[hash] || {};
    if (!entry) return { unpublished: hash };
    const blobRef = entry.image || entry;      // imageRef, or a legacy bare blob
    return toImageRef(blobRef, meta);
  });
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
 * `imagePairs` is `[{hash, entry}]` — the sha256 of each downloaded blob
 * (the local blob store is content-addressed) paired with the exact
 * `rec.value.images[]` entry it came from. The caller (restoreFromRepo)
 * builds this by walking the record's images in order and only emitting a
 * pair for the ones it actually fetched; an image whose blob 404s is simply
 * absent from `imagePairs`; it must NOT be assumed to align by position with
 * whatever did get fetched, or one image's alt text ends up attached to a
 * different image (see records.js's projectImages doc comment).
 *
 * publishedCanonical is derived from assembleWork rather than from the raw
 * record: it has to agree with what a later save would produce, or the work
 * would read as edited the moment it lands. Any field assembleWork does not
 * emit is therefore not round-tripped. */
export function workFromRecord(record, imagePairs, now) {
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
  const pairs = imagePairs || [];
  const imageHashes = pairs.map(p => p.hash);

  /* Rebuild the editor-side metadata map from what was published, keyed by
   * content hash rather than position. A legacy bare-blob entry (no `.image`,
   * `.alt` or `.aspectRatio`) yields empty metadata rather than failing the
   * restore. */
  const imageMeta = {};
  for (const { hash, entry } of pairs) {
    const meta = {};
    if (typeof entry?.alt === 'string' && entry.alt) meta.alt = entry.alt;
    const ar = entry?.aspectRatio;
    if (Number.isInteger(ar?.width) && Number.isInteger(ar?.height)) {
      meta.width = ar.width; meta.height = ar.height;
    }
    imageMeta[hash] = meta;
  }

  /* publishedImageHashes mirrors publishedImages position-for-position: index
   * i holds the local hash that produced publishedImages[i], or null where
   * nothing was fetched for that entry (matched by object identity against
   * `pairs`, since each pair's `entry` is the very object taken from
   * `rec.value.images`). projectImages then looks a hash up by value, never
   * by position, so a hole here just means "not available locally". */
  const hashByEntry = new Map(pairs.map(p => [p.entry, p.hash]));
  const publishedImageHashes = publishedImages.map(img => hashByEntry.get(img) ?? null);

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
    publishedImageHashes,
    publishedCanonical: canonicalJSON(assembleWork(body, publishedImages)),
  };
}
