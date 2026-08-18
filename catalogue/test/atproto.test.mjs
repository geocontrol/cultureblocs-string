import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveActor, fetchAllWorks, fetchProfile } from '../lib/atproto.js';

function stub(routes) {
  return async (url) => {
    for (const [match, body] of routes) {
      if (url.includes(match)) {
        return { ok: true, status: 200, json: async () => body };
      }
    }
    return { ok: false, status: 404, json: async () => ({}), text: async () => 'not found' };
  };
}

const PLC_DOC = { service: [{ id: '#atproto_pds', type: 'AtprotoPersonalDataServer', serviceEndpoint: 'https://pds.example' }] };

test('resolveActor resolves a handle through resolveHandle and plc.directory', async () => {
  const fetchFn = stub([
    ['resolveHandle', { did: 'did:plc:abc' }],
    ['plc.directory', PLC_DOC],
  ]);
  assert.deepEqual(await resolveActor('geocontrol.bsky.social', { fetchFn }),
    { did: 'did:plc:abc', pds: 'https://pds.example' });
});

test('resolveActor skips resolveHandle when given a DID', async () => {
  let calledResolve = false;
  const fetchFn = async (url) => {
    if (url.includes('resolveHandle')) { calledResolve = true; }
    return { ok: true, status: 200, json: async () => PLC_DOC };
  };
  const out = await resolveActor('did:plc:abc', { fetchFn });
  assert.equal(out.did, 'did:plc:abc');
  assert.equal(calledResolve, false, 'a DID needs no handle resolution');
});

test('resolveActor throws a named error when the handle does not resolve', async () => {
  const fetchFn = async () => ({ ok: false, status: 400, json: async () => ({}), text: async () => 'bad handle' });
  await assert.rejects(() => resolveActor('nope.invalid', { fetchFn }), /nope\.invalid/);
});

test('fetchAllWorks follows the cursor until it is exhausted', async () => {
  const pages = [
    { records: [{ uri: 'at://x/1' }, { uri: 'at://x/2' }], cursor: 'c1' },
    { records: [{ uri: 'at://x/3' }], cursor: 'c2' },
    { records: [], cursor: undefined },
  ];
  let i = 0;
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => pages[i++] });
  const out = await fetchAllWorks('https://pds.example', 'did:plc:abc', { fetchFn });
  assert.equal(out.length, 3, 'all pages collected, not just the first');
});

test('fetchAllWorks stops when a page repeats its cursor', async () => {
  // A PDS that returns the same cursor forever must not spin the browser.
  const fetchFn = async () => ({ ok: true, status: 200,
    json: async () => ({ records: [{ uri: 'at://x/1' }], cursor: 'same' }) });
  const out = await fetchAllWorks('https://pds.example', 'did:plc:abc', { fetchFn });
  assert.ok(out.length < 500, 'must terminate rather than loop forever');
});

test('fetchAllWorks sorts newest first', async () => {
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => ({ records: [
    { uri: 'a', value: { createdAt: '2024-01-01T00:00:00Z' } },
    { uri: 'b', value: { createdAt: '2026-01-01T00:00:00Z' } },
    { uri: 'c', value: { createdAt: '2025-01-01T00:00:00Z' } },
  ] }) });
  const out = await fetchAllWorks('https://pds.example', 'did:plc:abc', { fetchFn });
  assert.deepEqual(out.map(r => r.uri), ['b', 'c', 'a']);
});

test('fetchAllWorks threads each cursor into the next request', async () => {
  const seenUrls = [];
  const pages = [
    { records: [{ uri: 'at://x/1' }], cursor: 'c1' },
    { records: [{ uri: 'at://x/2' }], cursor: 'c2' },
    { records: [{ uri: 'at://x/3' }] },
  ];
  let i = 0;
  const fetchFn = async (url) => {
    seenUrls.push(url);
    return { ok: true, status: 200, json: async () => pages[i++] };
  };
  const out = await fetchAllWorks('https://pds.example', 'did:plc:abc', { fetchFn });
  assert.equal(out.length, 3);
  assert.ok(!seenUrls[0].includes('cursor='), 'first request carries no cursor');
  assert.ok(seenUrls[1].includes('cursor=c1'), 'second request must carry the first cursor');
  assert.ok(seenUrls[2].includes('cursor=c2'), 'third request must carry the second cursor');
});

test('fetchAllWorks throws rather than silently truncating when the repo exceeds the page cap', async () => {
  // A cap that exits quietly at 5,000 works would do exactly what the
  // function's own "silently truncated at 100" comment condemns, just two
  // orders of magnitude later. It must throw, not return a partial array.
  let i = 0;
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => ({
    records: [{ uri: `at://x/${i}` }], cursor: `c${i++}` }) });
  await assert.rejects(() => fetchAllWorks('https://pds.example', 'did:plc:abc', { fetchFn }),
    /more than \d+ works/);
});

test('fetchProfile returns null when there is no profile record', async () => {
  const fetchFn = async () => ({ ok: false, status: 404, json: async () => ({}), text: async () => 'nope' });
  assert.equal(await fetchProfile('https://pds.example', 'did:plc:abc', { fetchFn }), null);
});

test('fetchProfile returns null for a 400 RecordNotFound response', async () => {
  // Some PDS implementations answer a missing record with 400 RecordNotFound
  // rather than 404 — that must also read as "no profile", not a fault.
  const fetchFn = async () => ({ ok: false, status: 400, json: async () => ({}), text: async () => 'RecordNotFound' });
  assert.equal(await fetchProfile('https://pds.example', 'did:plc:abc', { fetchFn }), null);
});

test('fetchProfile propagates a real fault instead of disguising it as no profile', async () => {
  const fetchFn = async () => ({ ok: false, status: 500, json: async () => ({}), text: async () => 'internal error' });
  await assert.rejects(() => fetchProfile('https://pds.example', 'did:plc:abc', { fetchFn }), /500/);
});

test('fetchProfile returns the record when present', async () => {
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => ({ value: { name: 'Mark' } }) });
  const rec = await fetchProfile('https://pds.example', 'did:plc:abc', { fetchFn });
  assert.equal(rec.value.name, 'Mark');
});

test('resolveActor rejects a non-http(s) serviceEndpoint in the DID document', async () => {
  // A DID document is third-party data (did:web is served by whatever host the
  // DID names; a PLC entry is whatever its operator published), and its
  // serviceEndpoint is later interpolated into an image URL by blobUrl(). A
  // hostile or broken document naming a non-http scheme must not resolve.
  const HOSTILE_DOC = { service: [{ id: '#atproto_pds', type: 'AtprotoPersonalDataServer', serviceEndpoint: 'javascript:alert(1)' }] };
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => HOSTILE_DOC });
  await assert.rejects(() => resolveActor('did:plc:abc', { fetchFn }), /no PDS found/);
});
