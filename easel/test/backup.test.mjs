import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  bytesToBase64, base64ToBytes, buildExport, parseImport, planMerge, EXPORT_TYPE,
} from '../lib/backup.js';

test('base64 round-trips arbitrary bytes', () => {
  const bytes = new Uint8Array([0, 1, 127, 128, 255, 254, 65, 0]);
  assert.deepEqual(base64ToBytes(bytesToBase64(bytes)), bytes);
});

test('base64 handles a large buffer without blowing the stack', () => {
  // String.fromCharCode(...bytes) throws on big arrays — encoding must chunk.
  const big = new Uint8Array(300_000).map((_, i) => i % 256);
  const round = base64ToBytes(bytesToBase64(big));
  assert.equal(round.length, big.length);
  assert.deepEqual(round.slice(0, 64), big.slice(0, 64));
  assert.deepEqual(round.slice(-64), big.slice(-64));
});

test('buildExport carries works and inlines blobs as base64', () => {
  const works = [{ id: 'w1', state: 'draft', body: { title: 'A' }, imageHashes: ['h1'] }];
  const blobs = [{ hash: 'h1', mimeType: 'image/jpeg', bytes: new Uint8Array([1, 2, 3]) }];
  const doc = buildExport(works, blobs, '2026-08-12T21:00:00Z');

  assert.equal(doc.$type, EXPORT_TYPE);
  assert.equal(doc.version, 1);
  assert.equal(doc.exportedAt, '2026-08-12T21:00:00Z');
  assert.deepEqual(doc.works, works);
  assert.equal(doc.blobs.h1.mimeType, 'image/jpeg');
  assert.equal(doc.blobs.h1.data, bytesToBase64(new Uint8Array([1, 2, 3])));
});

test('export survives a JSON round trip back into parseImport', () => {
  const works = [{ id: 'w1', state: 'draft', body: { title: 'A' }, imageHashes: ['h1'] }];
  const blobs = [{ hash: 'h1', mimeType: 'image/png', bytes: new Uint8Array([9, 8, 7, 0, 255]) }];
  const doc = JSON.parse(JSON.stringify(buildExport(works, blobs, '2026-08-12T21:00:00Z')));
  const parsed = parseImport(doc);

  assert.deepEqual(parsed.works, works);
  assert.equal(parsed.blobs.length, 1);
  assert.equal(parsed.blobs[0].hash, 'h1');
  assert.equal(parsed.blobs[0].mimeType, 'image/png');
  assert.deepEqual(parsed.blobs[0].bytes, new Uint8Array([9, 8, 7, 0, 255]));
});

test('parseImport rejects a document that is not an Easel export', () => {
  assert.throws(() => parseImport({ $type: 'something.else', version: 1, works: [] }), /not an Easel export/i);
});

test('parseImport rejects an unsupported version', () => {
  assert.throws(() => parseImport({ $type: EXPORT_TYPE, version: 99, works: [] }), /version/i);
});

test('parseImport rejects a document with no works array', () => {
  assert.throws(() => parseImport({ $type: EXPORT_TYPE, version: 1 }), /works/i);
});

test('parseImport tolerates an export with no blobs', () => {
  const parsed = parseImport({ $type: EXPORT_TYPE, version: 1, works: [{ id: 'w1' }] });
  assert.equal(parsed.works.length, 1);
  assert.deepEqual(parsed.blobs, []);
});

test('planMerge adds new works and skips ids already present', () => {
  const incoming = [{ id: 'new' }, { id: 'dupe' }];
  const { toAdd, skipped } = planMerge(['dupe', 'other'], incoming);
  assert.deepEqual(toAdd.map(w => w.id), ['new']);
  assert.deepEqual(skipped, ['dupe']);
});

test('planMerge is non-destructive when everything already exists', () => {
  const { toAdd, skipped } = planMerge(['a', 'b'], [{ id: 'a' }, { id: 'b' }]);
  assert.deepEqual(toAdd, []);
  assert.deepEqual(skipped, ['a', 'b']);
});
