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
