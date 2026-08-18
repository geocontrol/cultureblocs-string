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

export async function resolveActor(actor, { fetchFn = fetch } = {}) {
  let did = actor;
  if (!actor.startsWith('did:')) {
    try {
      const r = await getJson(fetchFn,
        `${BSKY}/xrpc/com.atproto.identity.resolveHandle?handle=${encodeURIComponent(actor)}`);
      did = r.did;
    } catch {
      throw new Error(`could not resolve the handle "${actor}"`);
    }
  }
  let doc;
  if (did.startsWith('did:web:')) {
    doc = await getJson(fetchFn, `https://${did.slice('did:web:'.length)}/.well-known/did.json`);
  } else {
    doc = await getJson(fetchFn, `${PLC}/${encodeURIComponent(did)}`);
  }
  const pds = pdsFromDoc(doc);
  if (!pds) throw new Error(`no PDS found for ${did}`);
  return { did, pds };
}

/* Every page, not just the first. A catalogue silently truncated at 100 works
 * is worse than one that fails, because nobody notices the missing half. */
export async function fetchAllWorks(pds, did, { fetchFn = fetch } = {}) {
  const out = [];
  let cursor = '';
  let seen = null;
  for (let page = 0; page < MAX_PAGES; page++) {
    const url = `${pds}/xrpc/com.atproto.repo.listRecords`
      + `?repo=${encodeURIComponent(did)}&collection=${WORK_NSID}&limit=${PAGE_LIMIT}`
      + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '');
    const body = await getJson(fetchFn, url);
    out.push(...(body.records || []));
    const next = body.cursor || '';
    if (!next || next === seen) break;
    seen = next;
    cursor = next;
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
  } catch {
    return null;
  }
}
