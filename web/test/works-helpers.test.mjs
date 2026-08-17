import { test } from 'node:test';
import assert from 'node:assert/strict';
import { latest, blobUrl, cardModel, safeHref, imageFrom, escapeHtml, resolveImgSrc } from '../cultureblocs-works.js';

test('latest sorts by createdAt desc and applies limit', () => {
  const recs = [
    { value: { createdAt: '2024-01-01T00:00:00Z', title: 'old' } },
    { value: { createdAt: '2026-05-01T00:00:00Z', title: 'new' } },
    { value: { createdAt: '2025-01-01T00:00:00Z', title: 'mid' } },
  ];
  const out = latest(recs, 1);
  assert.equal(out.length, 1);
  assert.equal(out[0].value.title, 'new');
});

test('blobUrl builds a getBlob URL from a blob ref', () => {
  const ref = { $type: 'blob', ref: { $link: 'bafkreiabc' }, mimeType: 'image/png', size: 10 };
  const url = blobUrl('https://pds.example', 'did:plc:xyz', ref);
  assert.equal(
    url,
    'https://pds.example/xrpc/com.atproto.sync.getBlob?did=did%3Aplc%3Axyz&cid=bafkreiabc'
  );
});

test('cardModel extracts display fields and first image cid', () => {
  const rec = { value: {
    title: 'Untitled #1',
    description: 'a study',
    completionDate: '2024',
    referenceUrl: 'https://example.com/w1',
    images: [{ $type: 'blob', ref: { $link: 'bafkreifirst' }, mimeType: 'image/png', size: 1 }],
  }};
  const m = cardModel(rec);
  assert.equal(m.title, 'Untitled #1');
  assert.equal(m.description, 'a study');
  assert.equal(m.completionDate, '2024');
  assert.equal(m.referenceUrl, 'https://example.com/w1');
  assert.equal(m.imageCid, 'bafkreifirst');
});

test('cardModel tolerates a work with no image', () => {
  const m = cardModel({ value: { title: 'text only' } });
  assert.equal(m.imageCid, null);
});

test('safeHref allows http(s) schemes and rejects dangerous schemes', () => {
  assert.equal(safeHref('https://example.com/w'), 'https://example.com/w');
  assert.equal(safeHref('http://example.com'), 'http://example.com');
  assert.equal(safeHref('javascript:alert(1)'), null);
  assert.equal(safeHref('ftp://example.com'), null);
  assert.equal(safeHref(''), null);
  assert.equal(safeHref(undefined), null);
});

test('imageFrom reads the blob out of an imageRef', () => {
  const m = imageFrom({
    image: { $type: 'blob', ref: { $link: 'bafkreiA' }, mimeType: 'image/jpeg', size: 1 },
    alt: 'A gasholder at dusk.',
    aspectRatio: { width: 1600, height: 1067 },
  });
  assert.equal(m.cid, 'bafkreiA');
  assert.equal(m.alt, 'A gasholder at dusk.');
  assert.equal(m.width, 1600);
  assert.equal(m.height, 1067);
});

test('imageFrom tolerates a legacy bare blob from a stranger repo', () => {
  const m = imageFrom({ $type: 'blob', ref: { $link: 'bafkreiOld' }, mimeType: 'image/png', size: 1 });
  assert.equal(m.cid, 'bafkreiOld');
  assert.equal(m.alt, '');
  assert.equal(m.width, null);
});

test('imageFrom returns null when there is no cid', () => {
  assert.equal(imageFrom(null), null);
  assert.equal(imageFrom({ alt: 'no image here' }), null);
});

test('cardModel never substitutes the title for missing alt text', () => {
  const m = cardModel({ value: {
    title: 'Reality Towards Enemy',
    images: [{ image: { ref: { $link: 'bafkreiA' } } }],
  }});
  assert.equal(m.imageCid, 'bafkreiA');
  assert.equal(m.imageAlt, '', 'an absent alt must render as empty, not as the title');
});

test('cardModel carries alt and dimensions through', () => {
  const m = cardModel({ value: {
    title: 'Untitled',
    images: [{ image: { ref: { $link: 'bafkreiB' } }, alt: 'ink on paper',
               aspectRatio: { width: 800, height: 600 } }],
  }});
  assert.equal(m.imageAlt, 'ink on paper');
  assert.equal(m.imageWidth, 800);
  assert.equal(m.imageHeight, 600);
});

// C1 — XSS: a hostile imageUrl on a live (non-baked) record must never reach
// the <img src> attribute, and even where imageUrl IS honoured (baked mode),
// the value written into the template must be HTML-escaped.

test('escapeHtml neutralises an attribute-breakout payload', () => {
  const hostile = 'x" onerror="alert(1)';
  const escaped = escapeHtml(hostile);
  assert.equal(escaped.includes('"'), false, 'no raw double-quote must survive escaping');
  assert.equal(escaped, 'x&quot; onerror=&quot;alert(1)');
});

test('resolveImgSrc ignores a hostile imageUrl from a live (non-baked) record', () => {
  const hostileRec = { value: { imageUrl: 'x" onerror="alert(1)' } };
  const model = { imageCid: null };
  const res = { baked: false, pds: 'https://pds.example', did: 'did:plc:xyz' };
  assert.equal(resolveImgSrc(hostileRec, model, res), null,
    'a live record must never get to choose the image src directly');
});

test('resolveImgSrc honours imageUrl only for baked results, never live ones', () => {
  const rec = { value: { imageUrl: '/img/thumb.jpg' } };
  const model = { imageCid: null };
  assert.equal(resolveImgSrc(rec, model, { baked: true }), '/img/thumb.jpg');
  assert.equal(resolveImgSrc(rec, model, { baked: false }), null);
  assert.equal(resolveImgSrc(rec, model, {}), null);
});

test('resolveImgSrc falls back to a blob URL built from the record cid when not baked', () => {
  const rec = { value: { imageUrl: 'x" onerror="alert(1)' } };
  const model = { imageCid: 'bafkreiSafe' };
  const res = { baked: false, pds: 'https://pds.example', did: 'did:plc:xyz' };
  const src = resolveImgSrc(rec, model, res);
  assert.equal(src, 'https://pds.example/xrpc/com.atproto.sync.getBlob?did=did%3Aplc%3Axyz&cid=bafkreiSafe');
});

test('a hostile imageUrl from a live record cannot produce an unescaped <img> attribute end-to-end', () => {
  // Simulate the two-part fix together: gating (resolveImgSrc) then escaping
  // (escapeHtml, as renderCard applies it) — the combination is what the
  // finding requires; either half alone is insufficient.
  const hostileRec = { value: { imageUrl: 'x" onerror="alert(1)' } };
  const model = { imageCid: null, imageAlt: '' };
  const liveRes = { baked: false, pds: 'https://pds.example', did: 'did:plc:xyz' };
  const imgSrc = resolveImgSrc(hostileRec, model, liveRes);
  assert.equal(imgSrc, null, 'gated out before it ever reaches the template');

  // Even if a hostile value DID reach the template (baked mode), escaping
  // must still hold as the second line of defence.
  const bakedImgSrc = resolveImgSrc(hostileRec, model, { baked: true });
  const attr = `<img src="${escapeHtml(bakedImgSrc)}" alt="">`;
  assert.equal(attr.includes('" onerror="'), false,
    'no raw quote must let onerror break out of the src attribute');
  assert.equal(attr, '<img src="x&quot; onerror=&quot;alert(1)" alt="">');
});
