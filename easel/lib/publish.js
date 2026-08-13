import { assembleWork, canonicalJSON } from './records.js';

// `client` is supplied by easel.js from the oauth.js session:
//   { pds:  string  — the user's PDS base URL,
//     did:  string  — the signed-in repo DID,
//     fetch(url, opts) — DPoP-bound, token-refreshing fetch (oauth.authedFetch) }
// pocket/oauth.js only exposes createRecord(), so Easel's copy adds authedFetch
// to reach putRecord/deleteRecord/uploadBlob, which edit-in-place requires.
async function xrpc(client, nsid, body, { blob = false, headers = {} } = {}) {
  const r = await client.fetch(`${client.pds}/xrpc/${nsid}`, {
    method: 'POST',
    headers: blob ? headers : { 'content-type': 'application/json', ...headers },
    body: blob ? body : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${nsid} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

// Upload one Blob, return its ATProto blob ref.
async function uploadBlob(client, blob) {
  const res = await xrpc(client, 'com.atproto.repo.uploadBlob', blob,
    { blob: true, headers: { 'content-type': blob.type || 'application/octet-stream' } });
  return res.blob; // {$type:'blob', ref:{$link}, mimeType, size}
}

export async function publishWork(client, did, work, loadBlob) {
  const imageBlobRefs = [];
  for (const hash of (work.imageHashes || [])) {
    const blob = await loadBlob(hash);
    if (!blob) continue;
    if (blob.size > 2_000_000) throw new Error('image exceeds 2MB — re-save to downscale');
    imageBlobRefs.push(await uploadBlob(client, blob));
  }
  const record = assembleWork(work.body, imageBlobRefs);
  const res = await xrpc(client, 'com.atproto.repo.putRecord', {
    repo: did, collection: 'com.cultureblocs.creative.work', rkey: work.id, record,
  });
  return { uri: res.uri, cid: res.cid, canonical: canonicalJSON(record), imageBlobRefs };
}

export async function unpublishWork(client, did, work) {
  await xrpc(client, 'com.atproto.repo.deleteRecord', {
    repo: did, collection: 'com.cultureblocs.creative.work', rkey: work.id,
  });
}

/* ---------- reading back ----------
 * listRecords and getBlob are public, so these are plain GETs — no token, no
 * DPoP. Sign-in is still required upstream, but only to know whose repo to read. */

export async function fetchPublishedWorks(pds, did) {
  const out = [];
  let cursor = '';
  do {
    const url = `${pds}/xrpc/com.atproto.repo.listRecords`
      + `?repo=${encodeURIComponent(did)}`
      + `&collection=com.cultureblocs.creative.work&limit=100`
      + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '');
    const r = await fetch(url);
    if (!r.ok) throw new Error(`listRecords failed: ${r.status}`);
    const page = await r.json();
    out.push(...(page.records || []));
    cursor = page.cursor || '';
  } while (cursor);
  return out;
}

export async function fetchBlob(pds, did, cid) {
  const r = await fetch(`${pds}/xrpc/com.atproto.sync.getBlob`
    + `?did=${encodeURIComponent(did)}&cid=${encodeURIComponent(cid)}`);
  if (!r.ok) throw new Error(`getBlob ${cid} failed: ${r.status}`);
  return r.blob();
}

export async function publishProfile(client, did, profileBody) {
  const res = await xrpc(client, 'com.atproto.repo.putRecord', {
    repo: did, collection: 'com.cultureblocs.creative.profile', rkey: 'self', record: profileBody,
  });
  return { uri: res.uri, cid: res.cid };
}
