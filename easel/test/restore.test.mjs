import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rkeyFromUri, workFromRecord, isDrifted, assembleWork } from '../lib/records.js';

const REC = {
  uri: 'at://did:plc:abc/com.cultureblocs.creative.work/jox7cmxrmd7cbo4u',
  cid: 'bafyrei-cid',
  value: {
    $type: 'com.cultureblocs.creative.work',
    title: 'Reality Towards Enemy',
    description: 'a study',
    completionDate: '2025',
    referenceUrl: 'https://example.com/w',
    tags: ['ink'],
    createdAt: '2026-08-12T20:47:13.011Z',
    images: [{ $type: 'blob', ref: { $link: 'bafkrei-img' }, mimeType: 'image/jpeg', size: 100 }],
  },
};

test('rkeyFromUri takes the record key off an at:// uri', () => {
  assert.equal(rkeyFromUri(REC.uri), 'jox7cmxrmd7cbo4u');
});

test('workFromRecord rebuilds the local shape, keyed by the real rkey', () => {
  const w = workFromRecord(REC, ['hash1'], '2026-08-13T09:00:00Z');
  assert.equal(w.id, 'jox7cmxrmd7cbo4u');   // the rkey, so edit-in-place still works
  assert.equal(w.state, 'published');
  assert.equal(w.body.title, 'Reality Towards Enemy');
  assert.equal(w.body.description, 'a study');
  assert.equal(w.body.completionDate, '2025');
  assert.equal(w.body.referenceUrl, 'https://example.com/w');
  assert.deepEqual(w.body.tags, ['ink']);
  assert.equal(w.body.createdAt, '2026-08-12T20:47:13.011Z');
  assert.deepEqual(w.imageHashes, ['hash1']);
  assert.equal(w.publishedUri, REC.uri);
  assert.equal(w.publishedCid, REC.cid);
  assert.deepEqual(w.publishedImages, REC.value.images);
});

test('a freshly restored work does not read as edited', () => {
  // If publishedCanonical did not match what assembleWork produces from the
  // restored body, every pulled work would show "Edited since publish" and a
  // republish would churn the repo for no reason.
  const w = workFromRecord(REC, ['hash1'], '2026-08-13T09:00:00Z');
  const current = assembleWork(w.body, w.publishedImages);
  assert.equal(isDrifted(w.publishedCanonical, current), false);
});

test('editing a restored work then does read as drifted', () => {
  const w = workFromRecord(REC, ['hash1'], '2026-08-13T09:00:00Z');
  const edited = assembleWork({ ...w.body, title: 'Renamed' }, w.publishedImages);
  assert.equal(isDrifted(w.publishedCanonical, edited), true);
});

test('workFromRecord handles a record with no images', () => {
  const bare = { uri: 'at://did:plc:abc/com.cultureblocs.creative.work/xyz', cid: 'c',
    value: { $type: 'com.cultureblocs.creative.work', title: 'Text only', createdAt: '2026-01-01T00:00:00Z' } };
  const w = workFromRecord(bare, [], '2026-08-13T09:00:00Z');
  assert.deepEqual(w.imageHashes, []);
  assert.deepEqual(w.publishedImages, []);
  assert.equal(isDrifted(w.publishedCanonical, assembleWork(w.body, [])), false);
});

test('workFromRecord preserves links when present', () => {
  const rec = { ...REC, value: { ...REC.value, links: [{ uri: 'https://p.example', title: 'press' }] } };
  const w = workFromRecord(rec, ['hash1'], '2026-08-13T09:00:00Z');
  assert.deepEqual(w.body.links, [{ uri: 'https://p.example', title: 'press' }]);
  assert.equal(isDrifted(w.publishedCanonical, assembleWork(w.body, w.publishedImages)), false);
});
