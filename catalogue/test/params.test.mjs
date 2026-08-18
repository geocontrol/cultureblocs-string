import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseParams, safeCssHref } from '../lib/params.js';

const ORIGIN = 'https://www.cultureblocs.com';

test('parseParams reads actor and defaults the template to grid', () => {
  const p = parseParams('?actor=geocontrol.bsky.social', ORIGIN);
  assert.equal(p.actor, 'geocontrol.bsky.social');
  assert.equal(p.template, 'grid');
  assert.equal(p.cssHref, null);
});

test('parseParams accepts a DID as the actor', () => {
  const p = parseParams('?actor=did:plc:abc123', ORIGIN);
  assert.equal(p.actor, 'did:plc:abc123');
});

test('parseParams returns a null actor when absent', () => {
  assert.equal(parseParams('', ORIGIN).actor, null);
  assert.equal(parseParams('?actor=', ORIGIN).actor, null);
  assert.equal(parseParams('?actor=%20%20', ORIGIN).actor, null);
});

test('parseParams only allows known template names', () => {
  assert.equal(parseParams('?actor=a&template=index', ORIGIN).template, 'index');
  assert.equal(parseParams('?actor=a&template=feature', ORIGIN).template, 'feature');
  // An unknown name must fall back rather than emit a broken <link> path.
  assert.equal(parseParams('?actor=a&template=../../etc/passwd', ORIGIN).template, 'grid');
  assert.equal(parseParams('?actor=a&template=nope', ORIGIN).template, 'grid');
});

test('safeCssHref accepts a same-origin relative path', () => {
  assert.equal(safeCssHref('mine.css', ORIGIN), '/mine.css');
  assert.equal(safeCssHref('/themes/mine.css', ORIGIN), '/themes/mine.css');
});

test('safeCssHref rejects cross-origin stylesheets', () => {
  assert.equal(safeCssHref('https://evil.example/x.css', ORIGIN), null);
  assert.equal(safeCssHref('//evil.example/x.css', ORIGIN), null);
  assert.equal(safeCssHref('http://www.cultureblocs.com/x.css', ORIGIN), null); // scheme differs
});

test('safeCssHref rejects non-http schemes', () => {
  assert.equal(safeCssHref('javascript:alert(1)', ORIGIN), null);
  assert.equal(safeCssHref('data:text/css,body{}', ORIGIN), null);
});

test('safeCssHref returns null for junk rather than throwing', () => {
  assert.equal(safeCssHref('', ORIGIN), null);
  assert.equal(safeCssHref(null, ORIGIN), null);
});

test('parseParams carries a valid css through and drops an invalid one', () => {
  assert.equal(parseParams('?actor=a&css=/t.css', ORIGIN).cssHref, '/t.css');
  assert.equal(parseParams('?actor=a&css=https://evil.example/t.css', ORIGIN).cssHref, null);
});
