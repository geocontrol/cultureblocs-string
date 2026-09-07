/* The privacy strip — what leaves the machine when a record publishes.
 *
 * A faithful port of string/app/publisher.py's strip_bead / strip_strand /
 * strip_public, so a client that publishes directly (Pocket, Easel, Loom)
 * and the String's server-side publisher cannot disagree about what is
 * private. They agreed by inspection before; tests/fixtures/strip-cases.json
 * is run by both languages so they keep agreeing.
 *
 * The rule, in one line: geo, provenance, device ids, mintIds and local media
 * refs never leave. Place NAMES, notes, tags, links, works, kinds and times do.
 *
 * CANONICAL COPY. Apps carry copies; copy outward from here.
 */

/* Fields of a bead or annotation that survive publication, in the order the
 * Python writes them — canonical JSON sorts keys anyway, but keeping the
 * order identical makes the two implementations diff cleanly by eye. */
const BEAD_KEEP = ['createdAt', 'kind', 'note', 'tags', 'links', 'work'];
const STRAND_KEEP = ['createdAt', 'title', 'narrative', 'day', 'links'];

/* Local-only machinery on an otherwise public-by-intent record. `provenance`
 * is device and app internals; `media` points at files on the author's own
 * String, which no stranger can resolve. */
const LOCAL_ONLY = ['provenance', 'media'];

function requireType(body) {
  if (!body || typeof body['$type'] !== 'string') {
    throw new Error('record body has no $type');   // Python raises KeyError here
  }
  return body['$type'];
}

/* A bead or annotation, as it publishes inside a strand.
 *
 * `subject` is reduced to its name and nothing else: the whole point is that
 * "Tate Modern" publishes while the coordinates that would place you in it
 * do not. A subject with no name drops entirely rather than publishing an
 * empty husk. */
export function stripBead(body, { images = null } = {}) {
  const out = { $type: requireType(body) };
  for (const k of BEAD_KEEP) if (k in body) out[k] = body[k];
  const subj = body.subject;
  if (subj && typeof subj === 'object' && !Array.isArray(subj) && subj.name) {
    out.subject = { name: subj.name };
  }
  if (images && images.length) out.images = images;
  return out;
}

/* A strand. `items` are the at:// refs of the beads already published above
 * it — never the local spine:// uris, which is why they are passed in rather
 * than copied from the body. */
export function stripStrand(body, items) {
  const out = { $type: requireType(body) };
  for (const k of STRAND_KEEP) if (k in body) out[k] = body[k];
  const place = body.place;
  if (place && typeof place === 'object' && !Array.isArray(place) && place.name) {
    out.place = { name: place.name };
  }
  out.items = items;
  return out;
}

/* Records that are public by intent — creative claims, venue listings,
 * calendar events. These are written to be read by strangers, so the body
 * publishes as authored, minus the local-only machinery.
 *
 * Note the asymmetry with stripBead: this is a DENY list, so a field added
 * to one of those lexicons publishes automatically. That is deliberate for
 * records whose purpose is to be read, and wrong for a diary bead — hence
 * the allow list above. A venue's address and coordinates are the point of
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
