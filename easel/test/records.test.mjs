import { test } from 'node:test';
import assert from 'node:assert/strict';
import { assembleWork, assembleProfile, canonicalJSON, isDrifted, toImageRef, projectImages, workFromRecord } from '../lib/records.js';

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

const BLOB = { $type: 'blob', ref: { $link: 'bafkreiA' }, mimeType: 'image/jpeg', size: 100 };

test('toImageRef wraps a blob and carries alt + dimensions', () => {
  const ref = toImageRef(BLOB, { alt: 'ink on paper', width: 1600, height: 1067 });
  assert.deepEqual(ref, {
    image: BLOB,
    alt: 'ink on paper',
    aspectRatio: { width: 1600, height: 1067 },
  });
});

test('toImageRef omits blank alt rather than publishing an empty string', () => {
  assert.deepEqual(toImageRef(BLOB, { alt: '   ' }), { image: BLOB });
  assert.deepEqual(toImageRef(BLOB, {}), { image: BLOB });
});

test('toImageRef omits a half-specified or zero aspect ratio', () => {
  assert.equal('aspectRatio' in toImageRef(BLOB, { width: 1600 }), false);
  assert.equal('aspectRatio' in toImageRef(BLOB, { width: 0, height: 10 }), false);
});

test('assembleWork emits imageRefs under images', () => {
  const body = assembleWork(
    { title: 'W', createdAt: '2026-08-15T10:00:00Z' },
    [toImageRef(BLOB, { alt: 'a', width: 4, height: 3 })]);
  assert.equal(body.images.length, 1);
  assert.equal(body.images[0].image.ref.$link, 'bafkreiA');
  assert.equal(body.images[0].alt, 'a');
});

test('workFromRecord restores alt and dimensions into imageMeta', () => {
  const rec = {
    uri: 'at://did:plc:x/com.cultureblocs.creative.work/abc123',
    cid: 'bafycid',
    value: {
      title: 'W', createdAt: '2026-08-15T10:00:00Z',
      images: [{ image: BLOB, alt: 'restored alt', aspectRatio: { width: 8, height: 6 } }],
    },
  };
  const w = workFromRecord(rec, ['hash1'], '2026-08-15T11:00:00Z');
  assert.equal(w.id, 'abc123');
  assert.deepEqual(w.imageMeta, { hash1: { alt: 'restored alt', width: 8, height: 6 } });
});

test('workFromRecord tolerates a legacy bare-blob record', () => {
  const rec = {
    uri: 'at://did:plc:x/com.cultureblocs.creative.work/legacy1',
    cid: 'bafycid',
    value: { title: 'W', createdAt: '2026-08-15T10:00:00Z', images: [BLOB] },
  };
  const w = workFromRecord(rec, ['hash1'], '2026-08-15T11:00:00Z');
  assert.deepEqual(w.imageMeta, { hash1: {} });
});

test('projectImages rebuilds imageRefs from published blobs + current metadata', () => {
  const work = {
    imageHashes: ['hash1'],
    imageMeta: { hash1: { alt: 'edited alt', width: 4, height: 3 } },
    publishedImages: [{ image: BLOB, alt: 'original alt' }],
  };
  assert.deepEqual(projectImages(work), [{
    image: BLOB,
    alt: 'edited alt',
    aspectRatio: { width: 4, height: 3 },
  }]);
});

test('an alt-only edit is visible as drift', () => {
  const published = [toImageRef(BLOB, { alt: 'original alt' })];
  const body = { title: 'W', createdAt: '2026-08-15T10:00:00Z' };
  const publishedCanonical = canonicalJSON(assembleWork(body, published));

  const unchanged = { imageHashes: ['h'], imageMeta: { h: { alt: 'original alt' } },
                      publishedImages: published };
  assert.equal(isDrifted(publishedCanonical, assembleWork(body, projectImages(unchanged))),
    false, 'nothing changed — must not read as drifted');

  const altEdited = { imageHashes: ['h'], imageMeta: { h: { alt: 'a better description' } },
                      publishedImages: published };
  assert.equal(isDrifted(publishedCanonical, assembleWork(body, projectImages(altEdited))),
    true, 'an alt-only edit must mark the work edited since publish');
});

test('an image added since the last publish is visible as drift', () => {
  const published = [toImageRef(BLOB, { alt: 'first image' })];
  const body = { title: 'W', createdAt: '2026-08-15T10:00:00Z' };
  const publishedCanonical = canonicalJSON(assembleWork(body, published));

  const withNewImage = {
    imageHashes: ['h1', 'h2'],
    imageMeta: { h1: { alt: 'first image' }, h2: { alt: 'second image' } },
    publishedImages: published,
  };
  assert.equal(
    isDrifted(publishedCanonical, assembleWork(body, projectImages(withNewImage))),
    true,
    'a hash with no matching published entry must not be silently dropped');
});

test('projectImages reports no drift when nothing has changed', () => {
  const published = [toImageRef(BLOB, { alt: 'first image' })];
  const body = { title: 'W', createdAt: '2026-08-15T10:00:00Z' };
  const publishedCanonical = canonicalJSON(assembleWork(body, published));

  const unchanged = {
    imageHashes: ['h1'],
    imageMeta: { h1: { alt: 'first image' } },
    publishedImages: published,
  };
  assert.equal(
    isDrifted(publishedCanonical, assembleWork(body, projectImages(unchanged))),
    false,
    'no edits and no new images — must not read as drifted');
});

test('projectImages returns only real imageRefs when every hash is published', () => {
  const work = {
    imageHashes: ['hash1'],
    imageMeta: { hash1: { alt: 'edited alt', width: 4, height: 3 } },
    publishedImages: [{ image: BLOB, alt: 'original alt' }],
  };
  const result = projectImages(work);
  assert.equal(result.length, 1);
  assert.equal('unpublished' in result[0], false);
  assert.deepEqual(result, [{
    image: BLOB,
    alt: 'edited alt',
    aspectRatio: { width: 4, height: 3 },
  }]);
});
