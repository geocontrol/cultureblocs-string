import { test } from 'node:test';
import assert from 'node:assert/strict';
import { latest, blobUrl, cardModel, safeHref } from '../cultureblocs-works.js';

test('latest sorts by createdAt desc and applies limit', () => {
  const recs = [
    { value: { createdAt: '2024-01-01T00:00:00Z', title: 'old' } },
    { value: { createdAt: '2026-05-01T00:00:00Z', title: 'new' } },
    { value: { createdAt: '2025-01-01T00:00:00Z', title: 'mid' } },
  ];
  const out = latest(recs, 1);
  assert.equal(out.length, 1);
  assert.equal(out[0].value.title, 'new');
});

test('blobUrl builds a getBlob URL from a blob ref', () => {
  const ref = { $type: 'blob', ref: { $link: 'bafkreiabc' }, mimeType: 'image/png', size: 10 };
  const url = blobUrl('https://pds.example', 'did:plc:xyz', ref);
  assert.equal(
    url,
    'https://pds.example/xrpc/com.atproto.sync.getBlob?did=did%3Aplc%3Axyz&cid=bafkreiabc'
  );
});

test('cardModel extracts display fields and first image cid', () => {
  const rec = { value: {
    title: 'Untitled #1',
    description: 'a study',
    completionDate: '2024',
    referenceUrl: 'https://example.com/w1',
    images: [{ $type: 'blob', ref: { $link: 'bafkreifirst' }, mimeType: 'image/png', size: 1 }],
  }};
  const m = cardModel(rec);
  assert.equal(m.title, 'Untitled #1');
  assert.equal(m.description, 'a study');
  assert.equal(m.completionDate, '2024');
  assert.equal(m.referenceUrl, 'https://example.com/w1');
  assert.equal(m.imageCid, 'bafkreifirst');
});

test('cardModel tolerates a work with no image', () => {
  const m = cardModel({ value: { title: 'text only' } });
  assert.equal(m.imageCid, null);
});

test('safeHref allows http(s) schemes and rejects dangerous schemes', () => {
  assert.equal(safeHref('https://example.com/w'), 'https://example.com/w');
  assert.equal(safeHref('http://example.com'), 'http://example.com');
  assert.equal(safeHref('javascript:alert(1)'), null);
  assert.equal(safeHref('ftp://example.com'), null);
  assert.equal(safeHref(''), null);
  assert.equal(safeHref(undefined), null);
});
