import { test } from 'node:test';
import assert from 'node:assert/strict';
import { imageModel, beadImages, blocksHtml, esc, narrativeHtml } from '../cultureblocs-strands.js';

test('imageModel reads an imageRef', () => {
  const m = imageModel({
    image: { $type: 'blob', ref: { $link: 'bafkreiA' }, mimeType: 'image/jpeg', size: 1 },
    alt: 'The bar at closing time.',
    aspectRatio: { width: 1200, height: 900 },
  });
  assert.equal(m.cid, 'bafkreiA');
  assert.equal(m.alt, 'The bar at closing time.');
  assert.equal(m.width, 1200);
  assert.equal(m.height, 900);
});

test('imageModel tolerates a legacy bare blob', () => {
  const m = imageModel({ $type: 'blob', ref: { $link: 'bafkreiOld' }, mimeType: 'image/png', size: 1 });
  assert.equal(m.cid, 'bafkreiOld');
  assert.equal(m.alt, '');
  assert.equal(m.width, null);
});

test('imageModel returns null without a cid', () => {
  assert.equal(imageModel(undefined), null);
  assert.equal(imageModel({ alt: 'orphan' }), null);
});

test('beadImages prefers images and falls back to legacy photos', () => {
  assert.equal(beadImages({ images: [{ image: {} }] }).length, 1);
  assert.equal(beadImages({ photos: [{ ref: { $link: 'x' } }] }).length, 1);
  assert.deepEqual(beadImages({}), []);
});

test('beadImages ignores photos when images is present', () => {
  const out = beadImages({ images: [{ image: { ref: { $link: 'new' } } }],
                           photos: [{ ref: { $link: 'old' } }] });
  assert.equal(out.length, 1);
  assert.equal(imageModel(out[0]).cid, 'new');
});

/* blocksHtml — the shared plain-text formatter for bead notes and strand
 * narratives. Structure lives in newlines, because the lexicon's text is a
 * plain string with no markup and refs anchor into it by byte range. */

const count = (haystack, needle) => haystack.split(needle).length - 1;

/* The narrative of the strand published on 2026-09-15 ("Liminal Explorations"),
 * which rendered as one undifferentiated run of text on the geekyoto homepage. */
const PUBLISHED_NARRATIVE = [
  'Tales of liminal space and time are most definitely part of my reading and watching this year.',
  '',
  'I think over the year so far :',
  '* Rewatched Sapphire & Steel online',
  "* Saw Rose of Nevada, Enys Man and Bait, Mark Jenkin's Cornish Trilogy",
  '* Saw Exit 8',
  "* Rewatched a lot of Kane's Backrooms youtube videos",
  "* Watched the A24 release of Kane's The Backrooms film",
  '* Watched a couple of old Twighlight Zone episodes, Little Girl Lost',
  '* Wathced The Children of the Stones (its all on Youtube)',
  '* Rewatched episodes of The Prisoner (because why not)',
  '* Read some more Christopher Priest (Airside) and M John Harrison',
  '',
  'I dont think liminality is going to end over the coming months either',
].join('\n');

test('blocksHtml renders nothing for empty text', () => {
  assert.equal(blocksHtml(''), '');
  assert.equal(blocksHtml(null), '');
  assert.equal(blocksHtml(undefined), '');
});

test('blocksHtml splits paragraphs on a blank line', () => {
  const html = blocksHtml('First paragraph.\n\nSecond paragraph.');
  assert.equal(html, '<p>First paragraph.</p><p>Second paragraph.</p>');
});

test('blocksHtml turns a run of asterisk bullets into a list', () => {
  const html = blocksHtml('* one\n* two\n* three');
  assert.equal(html, '<ul class="bullets"><li>one</li><li>two</li><li>three</li></ul>');
});

test('blocksHtml accepts hyphen bullets', () => {
  const html = blocksHtml('- one\n- two');
  assert.equal(html, '<ul class="bullets"><li>one</li><li>two</li></ul>');
});

test('blocksHtml keeps a lead-in line as a paragraph before its bullets', () => {
  const html = blocksHtml('Here is the list:\n* one\n* two');
  assert.equal(html, '<p>Here is the list:</p><ul class="bullets"><li>one</li><li>two</li></ul>');
});

test('blocksHtml resumes prose after a bullet run in the same block', () => {
  const html = blocksHtml('* one\nand then this');
  assert.equal(html, '<ul class="bullets"><li>one</li></ul><p>and then this</p>');
});

test('blocksHtml renders the published strand narrative as three paragraphs and a nine-item list', () => {
  const html = blocksHtml(PUBLISHED_NARRATIVE);
  assert.equal(count(html, '<p>'), 3, 'opening paragraph, the bullet lead-in, and the closing line');
  assert.equal(count(html, '<ul class="bullets">'), 1);
  assert.equal(count(html, '<li>'), 9);
  assert.match(html, /<p>I think over the year so far :<\/p><ul class="bullets">/);
  assert.ok(!html.includes('<li>* '), 'the bullet marker is not repeated inside the item');
});

test('blocksHtml still renders a timed tracklist', () => {
  const html = blocksHtml('20:01 First Track\n20:05 Second Track\n20:11 Third Track');
  assert.match(html, /^<ul class="tracks">/);
  assert.equal(count(html, '<span class="tt">'), 3);
  assert.ok(!html.includes('class="bullets"'));
});

test('blocksHtml escapes markup once', () => {
  const html = blocksHtml('* Sapphire & Steel\n* <script>alert(1)</script>');
  assert.match(html, /<li>Sapphire &amp; Steel<\/li>/);
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('&amp;amp;'));
});

test('esc escapes the four HTML-significant characters and tolerates empty input', () => {
  assert.equal(esc('a & b < c > d "e"'), 'a &amp; b &lt; c &gt; d &quot;e&quot;');
  assert.equal(esc(''), '');
  assert.equal(esc(null), '');
});

test('narrativeHtml wraps the blocks in a div, because a <p> cannot contain them', () => {
  const html = narrativeHtml({ narrative: 'Lead in:\n* one\n* two' });
  assert.match(html, /^<div class="narrative">/);
  assert.match(html, /<\/div>$/);
  assert.ok(!html.startsWith('<p class="narrative">'),
    'a <p class="narrative"> would make the nested <p> and <ul> invalid markup');
  assert.match(html, /<p>Lead in:<\/p><ul class="bullets">/);
});

test('narrativeHtml renders nothing when a strand has no narrative', () => {
  assert.equal(narrativeHtml({}), '');
  assert.equal(narrativeHtml({ narrative: '' }), '');
  assert.equal(narrativeHtml(null), '');
});
