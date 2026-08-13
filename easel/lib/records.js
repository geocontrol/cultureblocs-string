// Pure assembly of creative.work / creative.profile record bodies + drift.
function present(v) {
  if (v == null) return false;
  if (typeof v === 'string') return v.trim() !== '';
  if (Array.isArray(v)) return v.length > 0;
  return true;
}
function put(obj, key, val) { if (present(val)) obj[key] = val; }

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
  return {
    id: rkeyFromUri(record.uri),
    state: 'published',
    body,
    imageHashes,
    createdAt: v.createdAt,
    updatedAt: now,
    publishedUri: record.uri,
    publishedCid: record.cid,
    publishedImages,
    publishedCanonical: canonicalJSON(assembleWork(body, publishedImages)),
  };
}
