/* The shared lexicon fixture suite, run against sdk/js/lexicon.js.
 * The other half lives in tests/test_fixture_parity.py — same cases, same
 * expected problems, so the two validators cannot drift apart.
 *   node --test sdk/js/test/                                              */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LexiconRegistry, codePointLength } from '../lexicon.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

function readLexicons(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...readLexicons(path));
    else if (entry.endsWith('.json')) out.push(JSON.parse(readFileSync(path, 'utf8')));
  }
  return out;
}

const registry = new LexiconRegistry().load(readLexicons(join(ROOT, 'lexicons')));
const cases = JSON.parse(readFileSync(join(ROOT, 'tests/fixtures/lexicon-cases.json'), 'utf8'));

for (const c of cases) {
  test(`lexicon fixture: ${c.name}`, () => {
    assert.deepEqual(registry.validateRecord(c.nsid, c.body), c.problems);
  });
}

test('the fixture file is actually loaded (a silent empty suite would prove nothing)', () => {
  assert.ok(cases.length >= 20, `expected the full fixture set, got ${cases.length}`);
});

test('every record lexicon the String knows about is loaded here too', () => {
  const types = registry.recordTypes();
  for (const nsid of ['com.cultureblocs.bead', 'com.cultureblocs.strand',
                      'com.cultureblocs.annotation', 'com.cultureblocs.creative.work',
                      'community.lexicon.calendar.event']) {
    assert.ok(types.includes(nsid), `missing record type ${nsid}`);
  }
});

test('maxGraphemes counts code points, matching Python len()', () => {
  assert.equal(codePointLength('🎭🎭🎭'), 3);
  assert.equal('🎭🎭🎭'.length, 6);        // the naive count this guards against
});

test('load() accepts a single doc, an array, or a keyed object', () => {
  const doc = { id: 'x.test', defs: { main: { type: 'record', record: { type: 'object' } } } };
  assert.deepEqual(new LexiconRegistry().load(doc).recordTypes(), ['x.test']);
  assert.deepEqual(new LexiconRegistry().load([doc]).recordTypes(), ['x.test']);
  assert.deepEqual(new LexiconRegistry().load({ anyKey: doc }).recordTypes(), ['x.test']);
});
