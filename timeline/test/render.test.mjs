/* Runs the timeline's inline script against a stub DOM and renders a day.
 * The page has no build step and no module boundary, so a renamed function
 * with a stale caller only fails at runtime in the browser — this is the
 * cheapest place to catch that.
 *   node --test timeline/test/*.test.mjs                                   */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const page = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'index.html'), 'utf8');
const script = [...page.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join('\n');

// Any element, any property, any call: enough for top-level wiring to run.
const stub = () => new Proxy(function () {}, {
  get: (_, k) => (k === Symbol.toPrimitive ? () => '' : k === 'value' ? '2026-09-03' : stub()),
  apply: () => stub(),
  set: () => true,
});

function loadPage() {
  const ctx = { console, localStorage: {}, location: { search: '' }, setTimeout, URLSearchParams,
    fetch: async () => ({ ok: true, json: async () => ({}) }) };
  ctx.document = stub();
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(`${script}\n;globalThis.__page = { S, render };`, ctx);
  return ctx.__page;
}

const bead = (over) => ({ id: 'a', type: 'com.cultureblocs.bead', sourceApp: 'pocket',
  createdAt: '2026-09-03T06:30:04Z', state: 'kept', body: { kind: 'visit', note: 'x' }, ...over });

for (const [name, rec] of [
  ['a kept bead', bead()],
  ['a proposal', bead({ sourceApp: 'scrobbler', state: 'proposal', body: { kind: 'listen', note: 'x' } })],
  ['a pre-state record', bead({ state: undefined })],
]) {
  test(`render() draws a day holding ${name}`, () => {
    const { S, render } = loadPage();
    S.records = [rec];
    S.strands = [];
    S.byId = { [rec.id]: rec };
    assert.doesNotThrow(() => render());
  });
}
