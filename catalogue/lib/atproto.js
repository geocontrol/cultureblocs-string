// Public ATProto reads. No auth, no tokens: everything here is world-readable.
// fetchFn is injectable so paging can be tested without a network.

const BSKY = 'https://public.api.bsky.app';
const PLC = 'https://plc.directory';
const WORK_NSID = 'com.cultureblocs.creative.work';
const PROFILE_NSID = 'com.cultureblocs.creative.profile';
const PAGE_LIMIT = 100;
const MAX_PAGES = 50;   // 5,000 works; a stuck cursor must not spin the browser

async function getJson(fetchFn, url) {
  const r = await fetchFn(url);
  if (!r.ok) {
    const detail = typeof r.text === 'function' ? await r.text() : '';
    const err = new Error(`${url} failed: ${r.status} ${detail}`.trim());
    err.status = r.status;
    throw err;
  }
  return r.json();
}

function pdsFromDoc(doc) {
  const svc = (doc?.service || []).find(s =>
    s?.id?.endsWith('#atproto_pds') || s?.type === 'AtprotoPersonalDataServer');
  const endpoint = svc?.serviceEndpoint || null;
  if (!endpoint) return null;
  // A DID document is third-party data: a did:web document is served by
  // whatever host the DID names, and a PLC entry is whatever its operator
  // published. Either can name any serviceEndpoint at all, including a
  // non-http one — and that string later gets interpolated into blob URLs
  // (see blobUrl in cultureblocs-works.js). Reject anything but http(s).
  try {
    const scheme = new URL(endpoint).protocol;
    if (scheme !== 'http:' && scheme !== 'https:') return null;
  } catch {
    return null;
  }
  return endpoint;
}

// A genuine 4xx answer means the actor really doesn't resolve; the visitor's
// handle (or DID) is wrong and the friendly, spelling-focused message is the
// right one. Anything else — a fetch rejection (offline, DNS failure; no
// .status at all) or a 5xx — is a transport-adjacent fault that has nothing
// to do with what the visitor typed, and must reach the caller unchanged so
// it lands on the generic "could not load, try again" path instead. The
// synthetic error keeps `.status` in the 4xx range purely so callers can
// route on it the same way as any other resolution failure below.
function notResolved(actor, status) {
  const err = new Error(`could not resolve the handle "${actor}"`);
  err.status = status;
  return err;
}

export async function resolveActor(actor, { fetchFn = fetch } = {}) {
  let did = actor;
  if (!actor.startsWith('did:')) {
    let r;
    try {
      r = await getJson(fetchFn,
        `${BSKY}/xrpc/com.atproto.identity.resolveHandle?handle=${encodeURIComponent(actor)}`);
    } catch (e) {
      if (e.status >= 400 && e.status < 500) throw notResolved(actor, e.status);
      throw e;
    }
    did = r.did;
    // A 200 with a missing/malformed did is not a network problem, but it is
    // also not something later code can act on: did.startsWith below would
    // throw a confusing "Cannot read properties of undefined" instead of the
    // same friendly message a bad handle already gets.
    if (typeof did !== 'string' || !did) throw notResolved(actor, 400);
  }
  let doc;
  try {
    if (did.startsWith('did:web:')) {
      doc = await getJson(fetchFn, `https://${did.slice('did:web:'.length)}/.well-known/did.json`);
    } else {
      doc = await getJson(fetchFn, `${PLC}/${encodeURIComponent(did)}`);
    }
  } catch (e) {
    // Same reasoning as above: a 502 from plc.directory (or a did:web host)
    // is not evidence the handle/DID is wrong.
    if (e.status >= 400 && e.status < 500) throw notResolved(actor, e.status);
    throw e;
  }
  const pds = pdsFromDoc(doc);
  if (!pds) throw new Error(`no PDS found for ${did}`);
  return { did, pds };
}

/* Every page, not just the first. A catalogue silently truncated at 100 works
 * is worse than one that fails, because nobody notices the missing half. That
 * is also why hitting MAX_PAGES throws instead of returning a partial array:
 * a plain array is indistinguishable from "this is everything," so a cap that
 * exits quietly would do, two orders of magnitude later, exactly what this
 * comment condemns at 100. */
export async function fetchAllWorks(pds, did, { fetchFn = fetch } = {}) {
  const out = [];
  let cursor = '';
  let seen = null;
  let page;
  for (page = 0; page < MAX_PAGES; page++) {
    const url = `${pds}/xrpc/com.atproto.repo.listRecords`
      + `?repo=${encodeURIComponent(did)}&collection=${WORK_NSID}&limit=${PAGE_LIMIT}`
      + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '');
    const body = await getJson(fetchFn, url);
    const next = body.cursor || '';
    // Detect a repeated cursor before accumulating this page's records, not
    // after — otherwise a stuck PDS yields one page of duplicates.
    if (next && next === seen) break;
    out.push(...(body.records || []));
    if (!next) break;
    seen = next;
    cursor = next;
  }
  if (page === MAX_PAGES) {
    throw new Error(
      `this repository has more than ${MAX_PAGES * PAGE_LIMIT} works; ` +
      `the catalogue cannot show them all`);
  }
  return out.sort((a, b) =>
    String(b.value?.createdAt || '').localeCompare(String(a.value?.createdAt || '')));
}

/* A creator may never have written a profile. That is not an error: the
 * catalogue is about the works, and the handle stands in for the name. */
export async function fetchProfile(pds, did, { fetchFn = fetch } = {}) {
  const url = `${pds}/xrpc/com.atproto.repo.getRecord`
    + `?repo=${encodeURIComponent(did)}&collection=${PROFILE_NSID}&rkey=self`;
  try {
    return await getJson(fetchFn, url);
  } catch (e) {
    // A creator may simply never have written a profile — that is normal, and the
    // catalogue falls back to the handle. Anything else is a real fault and must
    // not be disguised as an empty profile.
    if (e.status === 404 || e.status === 400) return null;
    throw e;
  }
}
