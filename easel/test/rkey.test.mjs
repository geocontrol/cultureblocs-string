import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isValidRkey, makeRkey } from '../lib/rkey.js';

test('isValidRkey accepts allowed keys and rejects bad ones', () => {
  assert.equal(isValidRkey('3kabc12xy'), true);
  assert.equal(isValidRkey('self'), true);
  assert.equal(isValidRkey(''), false);
  assert.equal(isValidRkey('has space'), false);
  assert.equal(isValidRkey('has/slash'), false);
  assert.equal(isValidRkey('a'.repeat(513)), false);
});

test('makeRkey produces valid, unique-ish keys', () => {
  const a = makeRkey();
  const b = makeRkey();
  assert.equal(isValidRkey(a), true);
  assert.equal(isValidRkey(b), true);
  assert.notEqual(a, b);
});
