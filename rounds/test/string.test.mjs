import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LINEUP_TYPES, fetchStands } from '../lib/string.js';

test('stands are read from place.lineup and the older venue.lineup, once each', async () => {
  const asked = [];
  globalThis.fetch = async (url) => {
    asked.push(url);
    const type = new URL(url).searchParams.get('type');
    const rows = type === 'com.cultureblocs.place.lineup'
      ? [{ id: 'new1' }, { id: 'both' }]
      : { records: [{ id: 'old1' }, { id: 'both' }] };
    return { ok: true, json: async () => rows };
  };
  const got = await fetchStands('http://string.test/', 'tok');
  assert.deepEqual(LINEUP_TYPES, ['com.cultureblocs.place.lineup', 'com.cultureblocs.venue.lineup']);
  assert.equal(asked.length, 2);
  assert.ok(asked.every((u) => u.startsWith('http://string.test/records?type=')));
  assert.deepEqual(got.map((r) => r.id), ['new1', 'both', 'old1']);
});

test('an unreachable String still fails loudly enough for the caller to catch', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
  await assert.rejects(fetchStands('http://string.test', ''), /503/);
});
