import { test } from 'node:test';
import assert from 'node:assert/strict';
import { beadBody, makeDedupeKey } from '../lib/records.js';

const NOW = '2026-10-16T14:30:00Z';

test('beadBody builds a valid-shaped bead against a stand', () => {
  const b = beadBody({ note: 'The Hicks weaving is enormous.',
                       standUri: 'spine://records/s1',
                       standLabel: 'Alison Jacques' }, NOW);
  assert.equal(b.$type, 'com.cultureblocs.bead');
  assert.equal(b.kind, 'visit');
  assert.equal(b.createdAt, NOW);
  assert.equal(b.note, 'The Hicks weaving is enormous.');
  assert.deepEqual(b.subject, { uri: 'spine://records/s1' });
});

test('beadBody omits an empty note rather than publishing a blank one', () => {
  const b = beadBody({ note: '   ', standUri: 'spine://records/s1' }, NOW);
  assert.equal('note' in b, false);
});

test('beadBody works with no stand attached', () => {
  const b = beadBody({ note: 'Queue is enormous.' }, NOW);
  assert.equal('subject' in b, false);
  assert.equal(b.note, 'Queue is enormous.');
});

test('beadBody never collects geo or provenance', () => {
  // Rounds is used in public and must not quietly record where someone stood.
  const b = beadBody({ note: 'x', standUri: 'spine://records/s1' }, NOW);
  assert.equal('geo' in b, false);
  assert.equal('provenance' in b, false);
});

test('beadBody carries the fair tag so notes are findable', () => {
  const b = beadBody({ note: 'x', fairSlug: 'frieze-london-2026' }, NOW);
  assert.ok(b.tags.includes('fair:frieze-london-2026'));
});

test('makeDedupeKey uses the rounds namespace, matching Pocket\'s discipline', () => {
  assert.equal(makeDedupeKey('8f2c-1a'), 'rounds:8f2c-1a');
});

test('makeDedupeKey is stable for the same id', () => {
  assert.equal(makeDedupeKey('abc'), makeDedupeKey('abc'));
  assert.notEqual(makeDedupeKey('abc'), makeDedupeKey('abd'));
});
