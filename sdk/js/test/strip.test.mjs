/* The shared strip fixture suite, run against sdk/js/strip.js.
 * Other half: tests/test_fixture_parity.py. These decide what leaves the
 * machine, so they are the tests to be most suspicious of.
 *   node --test sdk/js/test/                                              */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripBead, stripStrand, stripPublic, stripRef, canonicalJSON, contentHash } from '../strip.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const cases = JSON.parse(readFileSync(join(ROOT, 'tests/fixtures/strip-cases.json'), 'utf8'));

for (const c of cases) {
  test(`strip fixture: ${c.name}`, () => {
    let got;
    if (c.fn === 'bead') got = stripBead(c.body, { images: c.images ?? null });
    else if (c.fn === 'strand') got = stripStrand(c.body, 'items' in c ? c.items : []);
    else if (c.fn === 'public') got = stripPublic(c.body);
    else if (c.fn === 'ref') got = stripRef(c.body);
    else assert.fail(`unknown strip fn: ${c.fn}`);
    assert.deepEqual(got, c.expected);
  });
}

test('the fixture file is actually loaded', () => {
  assert.ok(cases.length >= 10, `expected the full fixture set, got ${cases.length}`);
});

/* The same blunt backstop the Python side runs: whatever the allow lists say,
 * these keys must never appear in a published bead or strand. */
test('no private key survives into any published bead or strand', () => {
  const forbidden = new Set(['geo', 'provenance', 'media', 'mintId', 'device', 'dedupeKey']);
  const walk = (node, path) => {
    if (Array.isArray(node)) node.forEach((v, i) => walk(v, `${path}[${i}]`));
    else if (node && typeof node === 'object') {
      for (const [k, v] of Object.entries(node)) {
        assert.ok(!forbidden.has(k), `${path}.${k} leaked into a published body`);
        walk(v, `${path}.${k}`);
      }
    }
  };
  for (const c of cases) {
    if (c.fn === 'public') continue;     // public-by-intent records keep their location
    walk(c.expected, c.name);
  }
});

test('a body with no $type is refused rather than publishing an undefined type', () => {
  assert.throws(() => stripBead({ createdAt: '2026-08-15T21:04:00Z', kind: 'note' }),
    /no \$type/);
});

test('canonicalJSON sorts keys at every depth', () => {
  assert.equal(canonicalJSON({ b: 1, a: { d: 2, c: [{ f: 3, e: 4 }] } }),
    '{"a":{"c":[{"e":4,"f":3}],"d":2},"b":1}');
});

test('contentHash matches publisher.content_hash for a known body', async () => {
  // Cross-checked against Python:
  //   hashlib.sha256(json.dumps({"a":2,"b":1}, sort_keys=True,
  //                             separators=(",",":")).encode()).hexdigest()
  assert.equal(await contentHash({ b: 1, a: 2 }),
    'd3626ac30a87e6f7a6428233b3c68299976865fa5508e4267c5415c76af7a772');
});
