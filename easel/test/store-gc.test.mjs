import { test } from 'node:test';
import assert from 'node:assert/strict';
import { orphanedHashes } from '../lib/store.js';

test('a hash no work references is orphaned', () => {
  const works = [{ id: 'a', imageHashes: ['keep'] }];
  assert.deepEqual(orphanedHashes(works, ['keep', 'gone']), ['gone']);
});

test('a hash shared by another work is kept', () => {
  // the shared case: blobs are content-addressed, so two works can point at
  // one blob row. Deleting one work must not take the other's image with it.
  const works = [{ id: 'b', imageHashes: ['shared'] }];
  assert.deepEqual(orphanedHashes(works, ['shared']), []);
});

test('every hash is orphaned when no works remain', () => {
  assert.deepEqual(orphanedHashes([], ['x', 'y']).sort(), ['x', 'y']);
});

test('nothing is orphaned when no blobs are stored', () => {
  assert.deepEqual(orphanedHashes([{ id: 'a', imageHashes: ['x'] }], []), []);
});

test('works without imageHashes are tolerated', () => {
  const works = [{ id: 'a' }, { id: 'b', imageHashes: null }, { id: 'c', imageHashes: ['keep'] }];
  assert.deepEqual(orphanedHashes(works, ['keep', 'gone']), ['gone']);
});

test('a work referencing the same hash twice still keeps it', () => {
  const works = [{ id: 'a', imageHashes: ['dup', 'dup'] }];
  assert.deepEqual(orphanedHashes(works, ['dup']), []);
});
