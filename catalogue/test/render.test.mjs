import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  profileModel, workModel, renderProfile, renderWork, renderCatalogue,
} from '../lib/render.js';

const PDS = 'https://pds.example';
const DID = 'did:plc:abc';
const BLOB = { $type: 'blob', ref: { $link: 'bafkreiA' }, mimeType: 'image/jpeg', size: 10 };

const WORK = { uri: `at://${DID}/com.cultureblocs.creative.work/w1`, value: {
  title: 'Reality Towards Enemy',
  description: 'ink on paper',
  completionDate: '2024',
  referenceUrl: 'https://example.com/w1',
  createdAt: '2026-01-01T00:00:00Z',
  images: [{ image: BLOB, alt: 'A charcoal study of a gasholder', aspectRatio: { width: 1600, height: 1067 } }],
}};

test('workModel carries alt and dimensions from the imageRef', () => {
  const m = workModel(WORK, PDS, DID);
  assert.equal(m.title, 'Reality Towards Enemy');
  assert.equal(m.alt, 'A charcoal study of a gasholder');
  assert.equal(m.width, 1600);
  assert.equal(m.height, 1067);
  assert.match(m.imageSrc, /getBlob\?did=did%3Aplc%3Aabc&cid=bafkreiA/);
});

test('workModel tolerates a legacy bare-blob work', () => {
  const legacy = { uri: 'at://x/y/z', value: { title: 'Old', createdAt: '2024-01-01T00:00:00Z', images: [BLOB] } };
  const m = workModel(legacy, PDS, DID);
  assert.match(m.imageSrc, /cid=bafkreiA/);
  assert.equal(m.alt, '');
});

test('workModel handles a work with no image at all', () => {
  const m = workModel({ uri: 'at://x/y/z', value: { title: 'Text only', createdAt: '2024-01-01T00:00:00Z' } }, PDS, DID);
  assert.equal(m.imageSrc, null);
  assert.equal(m.title, 'Text only');
});

test('renderWork emits the semantic class contract', () => {
  const html = renderWork(workModel(WORK, PDS, DID));
  for (const cls of ['cb-work', 'cb-work-image', 'cb-work-title', 'cb-work-meta', 'cb-work-desc', 'cb-work-link']) {
    assert.ok(html.includes(cls), `missing ${cls}`);
  }
  assert.ok(html.includes('width="1600"'), 'dimensions reserve layout space');
  assert.ok(html.includes('alt="A charcoal study of a gasholder"'));
});

test('renderWork omits the image element entirely when there is none', () => {
  const html = renderWork(workModel({ uri: 'at://x/y/z', value: { title: 'T', createdAt: '2024-01-01T00:00:00Z' } }, PDS, DID));
  assert.ok(!html.includes('cb-work-image'));
  assert.ok(html.includes('cb-work-title'));
});

test('renderWork escapes hostile text', () => {
  const nasty = { uri: 'at://x/y/z', value: {
    title: '<script>alert(1)</script>', createdAt: '2024-01-01T00:00:00Z',
    images: [{ image: BLOB, alt: '" onerror="alert(1)' }],
  }};
  const html = renderWork(workModel(nasty, PDS, DID));
  assert.ok(!html.includes('<script>'), 'title must be escaped');
  assert.ok(!html.includes('onerror="alert'), 'alt must be escaped');
});

test('renderWork marks the outbound reference link nofollow ugc, not just noopener', () => {
  // Any actor's works.uri/referenceUrl is a stranger's URL rendered on the
  // trusted cultureblocs.com domain. noopener alone protects the opener
  // window but says nothing about search-engine trust or that the link is
  // user-generated content, not editorial endorsement.
  const html = renderWork(workModel(WORK, PDS, DID));
  assert.match(html, /class="cb-work-link" href="[^"]*" rel="noopener nofollow ugc"/);
});

test('renderProfile marks outbound profile links nofollow ugc, not just noopener', () => {
  const html = renderProfile(profileModel({ value: {
    name: 'Mark', links: [{ uri: 'https://example.com', title: 'site' }],
  }}, 'a.example'));
  assert.match(html, /rel="noopener nofollow ugc"/);
});

test('renderWork drops a non-http referenceUrl', () => {
  const bad = { uri: 'at://x/y/z', value: {
    title: 'T', createdAt: '2024-01-01T00:00:00Z', referenceUrl: 'javascript:alert(1)' }};
  assert.ok(!renderWork(workModel(bad, PDS, DID)).includes('javascript:'));
});

test('extras.references is absent in v1 and emits no block', () => {
  const html = renderWork(workModel(WORK, PDS, DID), {});
  assert.ok(!html.includes('cb-work-references'));
});

test('extras.references renders when supplied', () => {
  const html = renderWork(workModel(WORK, PDS, DID), { references: ['Seen at Camden Arts Centre'] });
  assert.ok(html.includes('cb-work-references'));
  assert.ok(html.includes('Camden Arts Centre'));
});

test('profileModel falls back to the actor when there is no profile record', () => {
  const m = profileModel(null, 'geocontrol.bsky.social');
  assert.equal(m.name, 'geocontrol.bsky.social');
  assert.equal(m.bio, '');
});

test('profileModel reads name, bio, disciplines and based', () => {
  const m = profileModel({ value: {
    name: 'Mark Simpkins', bio: 'Artist and technologist',
    disciplines: ['drawing', 'code'], based: { name: 'London' },
    links: [{ uri: 'https://example.com', title: 'site' }],
  }}, 'geocontrol.bsky.social');
  assert.equal(m.name, 'Mark Simpkins');
  assert.deepEqual(m.disciplines, ['drawing', 'code']);
  assert.equal(m.based, 'London');
  assert.equal(m.links.length, 1);
});

test('the bundle hardcodes no actor', async () => {
  // The actor must be a runtime input, never a build-time constant — that is
  // what makes cultureblocs.com, an artist's own domain and a gallery roster
  // the same artefact. A stray handle in the source would quietly break that.
  const { readFile, readdir } = await import('node:fs/promises');
  const files = ['lib/params.js', 'lib/render.js', 'lib/atproto.js', 'catalogue.js'];
  for (const f of files) {
    let src;
    try { src = await readFile(new URL(`../${f}`, import.meta.url), 'utf8'); }
    catch { continue; }   // catalogue.js arrives in a later task
    assert.ok(!/\bdid:plc:[a-z0-9]{16,}/.test(src), `${f} hardcodes a DID`);
    assert.ok(!/geocontrol|bsky\.social/.test(src), `${f} hardcodes a handle`);
  }
});

test('the baked fixture renders deterministically', async () => {
  const { readFile } = await import('node:fs/promises');
  const raw = await readFile(new URL('../catalogue.sample.json', import.meta.url), 'utf8');
  const fixture = JSON.parse(raw);
  const html = renderCatalogue(
    profileModel(fixture.profile, 'fixture.example'),
    fixture.works.map(w => workModel(w, PDS, DID)));
  assert.ok(html.includes('Fixture Creator'));
  assert.ok(html.includes('First Fixture Work'));
  assert.ok(html.includes('Second Fixture Work'));
  assert.equal(html.split('class="cb-work"').length - 1, fixture.works.length);
});

test('renderCatalogue emits one cb-work per work', () => {
  const html = renderCatalogue(
    profileModel(null, 'a.example'),
    [workModel(WORK, PDS, DID), workModel(WORK, PDS, DID)]);
  assert.equal(html.split('class="cb-work"').length - 1, 2);
  assert.ok(html.includes('cb-catalogue'));
  assert.ok(html.includes('cb-profile'));
});
