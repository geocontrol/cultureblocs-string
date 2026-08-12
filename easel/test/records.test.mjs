import { test } from 'node:test';
import assert from 'node:assert/strict';
import { assembleWork, assembleProfile, canonicalJSON, isDrifted } from '../lib/records.js';

test('assembleWork includes only present fields + $type + images', () => {
  const body = assembleWork({
    title: 'Untitled #1',
    description: '',
    completionDate: '2024',
    referenceUrl: 'https://x.example',
    links: [{ uri: 'https://y.example', title: 'press' }],
    tags: ['ink'],
    externalIds: [],
    createdAt: '2026-08-12T10:00:00Z',
  }, [{ $type: 'blob', ref: { $link: 'bafkreiA' }, mimeType: 'image/jpeg', size: 100 }]);

  assert.equal(body.$type, 'com.cultureblocs.creative.work');
  assert.equal(body.title, 'Untitled #1');
  assert.equal('description' in body, false);          // empty omitted
  assert.equal(body.completionDate, '2024');
  assert.equal(body.referenceUrl, 'https://x.example');
  assert.deepEqual(body.tags, ['ink']);
  assert.equal('externalIds' in body, false);          // empty array omitted
  assert.equal(body.images.length, 1);
  assert.equal(body.images[0].ref.$link, 'bafkreiA');
});

test('assembleProfile builds a self profile', () => {
  const body = assembleProfile({ name: 'Mark', bio: '', disciplines: ['code'], links: [], createdAt: '2026-08-12T10:00:00Z' });
  assert.equal(body.$type, 'com.cultureblocs.creative.profile');
  assert.equal(body.name, 'Mark');
  assert.equal('bio' in body, false);
  assert.deepEqual(body.disciplines, ['code']);
});

test('canonicalJSON is key-order stable', () => {
  assert.equal(canonicalJSON({ b: 1, a: 2 }), canonicalJSON({ a: 2, b: 1 }));
});

test('isDrifted detects a changed body', () => {
  const published = canonicalJSON({ $type: 'x', title: 'a' });
  assert.equal(isDrifted(published, { $type: 'x', title: 'a' }), false);
  assert.equal(isDrifted(published, { $type: 'x', title: 'b' }), true);
});
