/* The privacy strip — what leaves the machine when a record publishes.
 *
 * A port of string/app/strip.py, the canonical copy the String's publisher,
 * scripts/promote.py and scripts/export_public.py all use, so a client that
 * publishes directly (Pocket, Easel, Loom) and the String cannot disagree
 * about what is private. tests/fixtures/strip-cases.json is run by both
 * languages so they keep agreeing.
 *
 * Allow lists all the way down: a field not named here does not publish, at
 * any depth, so a new lexicon field stays private until someone decides
 * otherwise and adds a fixture saying so. Geo, provenance, device ids,
 * mintIds, local media refs and resolver bookkeeping never leave. A person
 * ref — or a ref of any type other than work, event, venue or concept —
 * publishes only with a DID or an external identifier: a bare name may be a
 * private individual. A `did` or `creatorDid` that does not match the DID
 * pattern counts as absent and does not publish.
 *
 * CANONICAL COPY. Apps carry copies; copy outward from here.
 */

const ANNOTATION = 'com.cultureblocs.annotation';
const ROLES = ['subject', 'mention'];
const NON_PERSON_TYPES = ['work', 'event', 'venue', 'concept'];
const BEAD_KEEP = ['createdAt', 'kind', 'note'];
const STRAND_KEEP = ['createdAt', 'title', 'narrative', 'day'];

/* Local-only machinery on an otherwise public-by-intent record. `provenance`
 * is device and app internals; `media` points at files on the author's own
 * String, which no stranger can resolve. */
const LOCAL_ONLY = ['provenance', 'media'];

/* ATProto DID syntax — the same pattern as sdk/js/lexicon.js and
 * string/app/lexicon.py DID_RE. Kept here, not imported, because apps copy
 * this file on its own. */
const DID_RE = /^did:[a-z0-9]+:[a-zA-Z0-9._:%-]+$/;

const isObject = (v) => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v) => typeof v === 'string' && v !== '';
const list = (v) => (Array.isArray(v) ? v : []);
const did = (v) => typeof v === 'string' && DID_RE.test(v);

function pick(d, keys) {
  const out = {};
  for (const k of keys) if (str(d[k])) out[k] = d[k];
  return out;
}

/* Drop a creatorDid that pick kept but that is not a DID. */
function dropBadCreatorDid(out) {
  if ('creatorDid' in out && !did(out.creatorDid)) delete out.creatorDid;
  return out;
}

function requireType(body) {
  if (!body || typeof body['$type'] !== 'string') {
    throw new Error('record body has no $type');   // Python raises KeyError here
  }
  return body['$type'];
}

/* linkRefs: uri and title only. */
export const stripLinks = (links) =>
  list(links).filter((l) => isObject(l) && str(l.uri)).map((l) => pick(l, ['uri', 'title']));

export const stripTags = (tags) => list(tags).filter(str);

/* externalIds: scheme, id and uri; entries without scheme and id are dropped. */
export const stripExternalIds = (ids) =>
  list(ids).filter((e) => isObject(e) && str(e.scheme) && str(e.id))
    .map((e) => pick(e, ['scheme', 'id', 'uri']));

/* The public form of one #ref, or null if it must not publish. `anchored` is
 * false for presentation refs, which have no text to anchor into. */
export function stripRef(ref, anchored = true) {
  if (!isObject(ref) || !str(ref.type)) return null;
  const descriptor = ref.descriptor;
  if (!isObject(descriptor) || !str(descriptor.label)) return null;
  const out = {
    type: ref.type,
    role: ROLES.includes(ref.role) ? ref.role : 'mention',
    descriptor: dropBadCreatorDid(pick(descriptor, ['label', 'creator', 'creatorDid', 'date'])),
  };
  if (did(ref.did)) out.did = ref.did;
  const ids = stripExternalIds(ref.externalIds);
  if (ids.length) out.externalIds = ids;
  if (!NON_PERSON_TYPES.includes(ref.type) && !('did' in out) && !ids.length) return null; // unknown types fail closed
  const index = ref.index;
  if (anchored && isObject(index) && Number.isInteger(index.byteStart) && Number.isInteger(index.byteEnd)) {
    out.index = { byteStart: index.byteStart, byteEnd: index.byteEnd };
  }
  return out;
}

export const stripRefs = (refs) => list(refs).map((r) => stripRef(r)).filter((r) => r !== null);

export function stripPresentation(presentation) {
  if (!isObject(presentation)) return null;
  const out = pick(presentation, ['format']);
  for (const key of ['venueRef', 'eventRef']) {
    const ref = stripRef(presentation[key], false);
    if (ref !== null) out[key] = ref;
  }
  return Object.keys(out).length ? out : null;
}

/* Deprecated #workRef on annotations: identifiers and descriptors, never `image`. */
export function stripWorkRef(work) {
  if (!isObject(work)) return null;
  const out = dropBadCreatorDid(
    pick(work, ['title', 'creator', 'date', 'wikidata', 'linkedArt', 'creatorDid']));
  const acc = work.accession;
  if (isObject(acc) && str(acc.institution) && str(acc.id)) out.accession = pick(acc, ['institution', 'id']);
  return out;
}

function common(body, out) {
  const tags = stripTags(body.tags);
  if (tags.length) out.tags = tags;
  const links = stripLinks(body.links);
  if (links.length) out.links = links;
  const refs = stripRefs(body.refs);
  if (refs.length) out.refs = refs;
  return out;
}

/* A bead or annotation, as it publishes inside a strand.
 *
 * `subject` is reduced to its name and nothing else: the whole point is that
 * "Tate Modern" publishes while the coordinates that would place you in it
 * do not. A subject with no name drops entirely rather than publishing an
 * empty husk. `images` are imageRefs the caller has already uploaded. */
export function stripBead(body, { images = null } = {}) {
  const out = { $type: requireType(body) };
  for (const k of BEAD_KEEP) if (str(body[k])) out[k] = body[k];
  if (isObject(body.subject) && str(body.subject.name)) out.subject = { name: body.subject.name };
  if (body.$type === ANNOTATION) {
    const work = stripWorkRef(body.work);
    if (work !== null) out.work = work;
  }
  const presentation = stripPresentation(body.presentation);
  if (presentation !== null) out.presentation = presentation;
  common(body, out);
  if (images && images.length) out.images = images;
  return out;
}

/* A strand. `items` are the at:// refs of the beads already published above
 * it — never the local spine:// uris, which is why they are passed in rather
 * than copied from the body. A target that bundles items inline (the static
 * export) passes null, and the field is omitted. */
export function stripStrand(body, items) {
  const out = { $type: requireType(body) };
  for (const k of STRAND_KEEP) if (str(body[k])) out[k] = body[k];
  if (isObject(body.place) && str(body.place.name)) out.place = { name: body.place.name };
  common(body, out);
  if (items !== null && items !== undefined) out.items = items;
  return out;
}

/* Records that are public by intent — creative claims, venue listings,
 * calendar events. These are written to be read by strangers, so the body
 * publishes as authored, minus the local-only machinery.
 *
 * Note the asymmetry with stripBead: this is a DENY list, so a field added
 * to one of those lexicons publishes automatically. That is deliberate for
 * records whose purpose is to be read, and wrong for a diary bead — hence
 * the allow lists above. A venue's address and coordinates are the point of
 * the record and stay. */
export function stripPublic(body) {
  const out = {};
  for (const [k, v] of Object.entries(body)) {
    if (!LOCAL_ONLY.includes(k)) out[k] = v;
  }
  return out;
}

/* The hash the String stores as publishedHash, and the shape Easel calls
 * canonicalJSON. Sorted keys, no whitespace — byte-identical to Python's
 * json.dumps(obj, sort_keys=True, separators=(",", ":")). */
export function canonicalJSON(obj) {
  return JSON.stringify(sortKeys(obj));
}

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    const out = {};
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k]);
    return out;
  }
  return v;
}

/* sha256 hex of the canonical form. Matches publisher.content_hash.
 * Async because WebCrypto is; Node's webcrypto satisfies the same call. */
export async function contentHash(obj) {
  const bytes = new TextEncoder().encode(canonicalJSON(obj));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}
