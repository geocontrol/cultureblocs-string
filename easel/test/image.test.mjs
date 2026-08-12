import { test } from 'node:test';
import assert from 'node:assert/strict';
import { downscaleDims } from '../lib/image.js';

test('landscape scales by width', () => {
  assert.deepEqual(downscaleDims(4000, 2000, 1600), { width: 1600, height: 800 });
});

test('portrait scales by height', () => {
  assert.deepEqual(downscaleDims(2000, 4000, 1600), { width: 800, height: 1600 });
});

test('never upscales', () => {
  assert.deepEqual(downscaleDims(500, 400, 1600), { width: 500, height: 400 });
});

test('rounds to integers', () => {
  const d = downscaleDims(1000, 333, 500);
  assert.equal(Number.isInteger(d.width), true);
  assert.equal(Number.isInteger(d.height), true);
});
