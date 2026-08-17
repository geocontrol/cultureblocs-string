import { test } from 'node:test';
import assert from 'node:assert/strict';
import { imageModel, beadImages } from '../cultureblocs-strands.js';

test('imageModel reads an imageRef', () => {
  const m = imageModel({
    image: { $type: 'blob', ref: { $link: 'bafkreiA' }, mimeType: 'image/jpeg', size: 1 },
    alt: 'The bar at closing time.',
    aspectRatio: { width: 1200, height: 900 },
  });
  assert.equal(m.cid, 'bafkreiA');
  assert.equal(m.alt, 'The bar at closing time.');
  assert.equal(m.width, 1200);
  assert.equal(m.height, 900);
});

test('imageModel tolerates a legacy bare blob', () => {
  const m = imageModel({ $type: 'blob', ref: { $link: 'bafkreiOld' }, mimeType: 'image/png', size: 1 });
  assert.equal(m.cid, 'bafkreiOld');
  assert.equal(m.alt, '');
  assert.equal(m.width, null);
});

test('imageModel returns null without a cid', () => {
  assert.equal(imageModel(undefined), null);
  assert.equal(imageModel({ alt: 'orphan' }), null);
});

test('beadImages prefers images and falls back to legacy photos', () => {
  assert.equal(beadImages({ images: [{ image: {} }] }).length, 1);
  assert.equal(beadImages({ photos: [{ ref: { $link: 'x' } }] }).length, 1);
  assert.deepEqual(beadImages({}), []);
});

test('beadImages ignores photos when images is present', () => {
  const out = beadImages({ images: [{ image: { ref: { $link: 'new' } } }],
                           photos: [{ ref: { $link: 'old' } }] });
  assert.equal(out.length, 1);
  assert.equal(imageModel(out[0]).cid, 'new');
});
