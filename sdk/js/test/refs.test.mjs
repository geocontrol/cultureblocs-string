/* The shared refs fixture suite, run against sdk/js/refs.js.
 * Other half: tests/test_fixture_parity.py. `fn` names the Python function;
 * the JS export is its camelCase twin.
 *   node --test sdk/js/test/*.test.mjs                                    */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as refs from '../refs.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const cases = JSON.parse(readFileSync(join(ROOT, 'tests/fixtures/refs-cases.json'), 'utf8'));
const camel = (name) => name.replace(/_([a-z])/g, (_, c) => c.toUpperCase());

for (const c of cases) {
  test(`refs fixture: ${c.name}`, () => {
    const fn = refs[camel(c.fn)];
    assert.equal(typeof fn, 'function', `sdk/js/refs.js has no export for ${c.fn}`);
    assert.deepEqual(fn(...c.args), c.expected);
  });
}

test('the fixture file is actually loaded', () => {
  assert.ok(cases.length >= 15, `expected the full fixture set, got ${cases.length}`);
});
