import * as store from './lib/store.js';
import { assembleWork, assembleProfile, isDrifted, projectImages } from './lib/records.js';
import { downscaleDims, renderToBlob } from './lib/image.js';
import { makeRkey } from './lib/rkey.js';
import * as oauth from './oauth.js';
import { publishWork, unpublishWork, publishProfile, fetchPublishedWorks, fetchBlob } from './lib/publish.js';
import { buildExport, parseImport, planMerge } from './lib/backup.js';
import { workFromRecord, rkeyFromUri } from './lib/records.js';

const $ = id => document.getElementById(id);
let db, current = null;      // current editing work
let pendingImages = [];      // {hash, blob, alt} staged in the editor

async function boot() {
  db = await store.openDb();
  // Only call completeLogin when we are actually returning from the auth
  // server — it throws ("no sign-in was in progress") on an ordinary load.
  if (oauth.pendingCallback()) {
    try { await oauth.completeLogin(); }
    catch (e) { console.warn('sign-in did not complete:', e.message); }
  }
  refreshWho();
  wire();
  await renderList();
}

function refreshWho() {
  const s = oauth.session();
  const signedIn = !!s?.did;
  $('who').textContent = signedIn ? `signed in: ${s.handle || s.did}` : 'not signed in';
  // The one button toggles, so its label has to follow the session — otherwise
  // it reads "Sign in" while actually signing you out.
  $('btn-signin').textContent = signedIn ? 'Sign out' : 'Sign in';
}

// A publish client for lib/publish.js: {did, pds, fetch}. Redirects to sign-in
// when there is no session, in which case it never returns.
async function requireClient() {
  const s = oauth.session();
  if (!s?.did) {
    const h = prompt('Your handle (e.g. geocontrol.bsky.social):');
    if (h) await oauth.startLogin(h);
    throw new Error('redirecting to sign in');
  }
  return { did: s.did, pds: s.pds, handle: s.handle, fetch: oauth.authedFetch };
}

function show(screen) {
  $('screen-works').classList.toggle('hidden', screen !== 'works');
  $('screen-editor').classList.toggle('hidden', screen !== 'editor');
}

async function renderList() {
  const works = (await store.listWorks(db)).sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));
  $('empty').classList.toggle('hidden', works.length > 0);
  const el = $('works'); el.innerHTML = '';
  for (const w of works) {
    let thumb = '';
    if (w.imageHashes?.[0]) {
      const rec = await store.getBlob(db, w.imageHashes[0]);
      if (rec) thumb = `<img src="${URL.createObjectURL(rec.blob)}" alt="">`;
    }
    const div = document.createElement('div');
    div.className = 'work';
    div.innerHTML = `${thumb || '<div style="height:140px;background:#f4f4f4"></div>'}
      <div class="m"><div>${escape(w.body?.title || 'Untitled')}</div>
      <span class="chip ${w.state}">${w.state}</span></div>`;
    div.onclick = () => openEditor(w.id);
    el.appendChild(div);
  }
}

function escape(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function openEditor(id) {
  current = id ? await store.getWork(db, id) : {
    id: makeRkey(), state: 'draft', body: {}, imageHashes: [],
    createdAt: new Date().toISOString(),
  };
  pendingImages = [];
  const b = current.body || {};
  $('f-title').value = b.title || '';
  $('f-desc').value = b.description || '';
  $('f-date').value = b.completionDate || '';
  $('f-ref').value = b.referenceUrl || '';
  $('f-links').value = (b.links || []).map(l => l.title ? `${l.title} | ${l.uri}` : l.uri).join('\n');
  $('f-tags').value = (b.tags || []).join(', ');
  $('btn-unpublish').classList.toggle('hidden', current.state === 'draft');
  await renderThumbs();
  $('editor-status').textContent = current.state === 'edited' ? 'Edited since publish.' : '';
  show('editor');
}

/* Read the alt text currently typed into the editor's thumbnail inputs,
 * keyed by content hash. saveLocal and harvestTypedAlt both need this same
 * DOM read, so it lives in one place. */
function readAltFromDom() {
  const altByHash = {};
  for (const input of document.querySelectorAll('#thumbs .alt-in')) {
    altByHash[input.dataset.hash] = input.value.trim();
  }
  return altByHash;
}

/* renderThumbs() wipes and rebuilds #thumbs from stored metadata. Anything
 * the user typed since the last save lives only in the DOM until then, so it
 * has to be folded back into pendingImages / current.imageMeta before that
 * wipe — otherwise attaching another file (onFiles calls renderThumbs too)
 * silently discards it. Hashes not recognised as belonging to the current
 * work (e.g. leftover DOM from a previously open work) are ignored. */
function harvestTypedAlt() {
  const altByHash = readAltFromDom();
  for (const p of pendingImages) {
    if (p.hash in altByHash) p.alt = altByHash[p.hash];
  }
  if (!current) return;
  current.imageMeta = current.imageMeta || {};
  for (const hash of (current.imageHashes || [])) {
    if (hash in altByHash) {
      current.imageMeta[hash] = { ...(current.imageMeta[hash] || {}), alt: altByHash[hash] };
    }
  }
}

async function renderThumbs() {
  harvestTypedAlt();
  const el = $('thumbs'); el.innerHTML = '';
  const hashes = [...(current.imageHashes || []), ...pendingImages.map(p => p.hash)];
  for (const h of hashes) {
    const staged = pendingImages.find(p => p.hash === h);
    const blob = staged ? staged.blob : (await store.getBlob(db, h))?.blob;
    if (!blob) continue;
    const meta = staged || (current.imageMeta || {})[h] || {};

    const fig = document.createElement('figure');
    fig.className = 'thumb';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(blob);
    img.alt = '';                       // the editor's own preview is decorative
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'alt-in';
    input.placeholder = 'Describe this image';
    input.maxLength = 2000;
    input.value = meta.alt || '';
    input.dataset.hash = h;
    fig.append(img, input);
    el.appendChild(fig);
  }
}

function parseLinks(text) {
  return text.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
    const [a, b] = l.split('|').map(s => s.trim());
    return b ? { title: a, uri: b } : { uri: a };
  });
}

async function onFiles(ev) {
  for (const file of ev.target.files) {
    const bitmap = await createImageBitmap(file);
    const dims = downscaleDims(bitmap.width, bitmap.height, 1600);
    const blob = await renderToBlob(bitmap, dims, { watermark: $('f-watermark').checked ? 'geekyoto.com' : null });
    const hash = await store.hashBlob(blob);
    if (![...(current.imageHashes || []), ...pendingImages.map(p => p.hash)].includes(hash))
      pendingImages.push({ hash, blob, alt: '', width: dims.width, height: dims.height });
  }
  ev.target.value = '';
  await renderThumbs();
}

async function saveLocal() {
  if (!$('f-title').value.trim()) { $('editor-status').textContent = 'Title is required.'; return; }
  // Alt text lives in the DOM until save; read it back before the inputs go away.
  const altByHash = readAltFromDom();
  current.imageMeta = current.imageMeta || {};
  for (const p of pendingImages) {
    await store.putBlob(db, p.hash, p.blob);
    current.imageHashes.push(p.hash);
    current.imageMeta[p.hash] = { width: p.width, height: p.height };
  }
  pendingImages = [];
  for (const hash of current.imageHashes) {
    const meta = current.imageMeta[hash] || {};
    if (hash in altByHash) meta.alt = altByHash[hash];
    current.imageMeta[hash] = meta;
  }
  current.body = {
    title: $('f-title').value.trim(),
    description: $('f-desc').value.trim(),
    completionDate: $('f-date').value.trim(),
    referenceUrl: $('f-ref').value.trim(),
    links: parseLinks($('f-links').value),
    tags: $('f-tags').value.split(',').map(t => t.trim()).filter(Boolean),
    createdAt: current.createdAt,
  };
  current.updatedAt = new Date().toISOString();
  // drift: if published and body changed, mark edited
  if (current.state === 'published' && current.publishedCanonical &&
      isDrifted(current.publishedCanonical, assembleWork(current.body, projectImages(current))))
    current.state = 'edited';
  await store.saveWork(db, current);
  $('editor-status').textContent = 'Saved locally.';
  await renderList();
}

/* Pull works already published to this account's repo into the local library.
 * Deliberate, never automatic on sign-in: it writes to local storage, and the
 * result should not surprise anyone. Works already here are skipped, so local
 * edits — published or not — are never overwritten. */
async function restoreFromRepo() {
  const status = $('library-status');
  try {
    const s = oauth.session();
    if (!s?.did) { status.textContent = 'Sign in first — Easel needs to know whose repo to read.'; return; }

    status.textContent = 'Looking for published works…';
    const records = await fetchPublishedWorks(s.pds, s.did);
    if (!records.length) { status.textContent = 'No published works found in your repo.'; return; }

    const existing = (await store.listWorks(db)).map(w => w.id);
    const fresh = records.filter(r => !existing.includes(rkeyFromUri(r.uri)));
    const skipped = records.length - fresh.length;
    if (!fresh.length) {
      status.textContent = `Nothing to restore — all ${records.length} published work(s) are already here.`;
      return;
    }

    const now = new Date().toISOString();
    let restored = 0, imagesMissing = 0;
    for (const rec of fresh) {
      status.textContent = `Restoring ${restored + 1} of ${fresh.length}…`;
      const hashes = [];
      for (const img of (rec.value?.images || [])) {
        const blobRef = img?.image || img;          // imageRef, or a legacy bare blob
        const cid = blobRef?.ref?.$link || blobRef?.cid;
        if (!cid) continue;
        try {
          const blob = await fetchBlob(s.pds, s.did, cid);
          const hash = await store.hashBlob(blob);
          await store.putBlob(db, hash, blob);
          hashes.push(hash);
        } catch (e) { imagesMissing++; }   // keep the work; it just lacks that image
      }
      await store.saveWork(db, workFromRecord(rec, hashes, now));
      restored++;
    }

    await renderList();
    status.textContent = `Restored ${restored} work(s)`
      + (skipped ? `; skipped ${skipped} already here` : '')
      + (imagesMissing ? `; ${imagesMissing} image(s) could not be fetched` : '') + '.';
  } catch (e) {
    status.textContent = 'Restore failed: ' + e.message;
  }
}

async function exportLibrary() {
  const status = $('library-status');
  try {
    status.textContent = 'Preparing export…';
    const works = await store.listWorks(db);
    if (!works.length) { status.textContent = 'Nothing to export yet.'; return; }

    // Only the images the works actually reference — never stray rows.
    const wanted = [...new Set(works.flatMap(w => w.imageHashes || []))];
    const blobs = [];
    for (const hash of wanted) {
      const rec = await store.getBlob(db, hash);
      if (!rec?.blob) continue;
      blobs.push({
        hash,
        mimeType: rec.blob.type,
        bytes: new Uint8Array(await rec.blob.arrayBuffer()),
      });
    }

    const now = new Date();
    const doc = buildExport(works, blobs, now.toISOString());
    const file = new Blob([JSON.stringify(doc)], { type: 'application/json' });
    const url = URL.createObjectURL(file);
    const a = document.createElement('a');
    a.href = url;
    a.download = `easel-backup-${now.toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);

    const mb = (file.size / 1048576).toFixed(1);
    status.textContent = `Exported ${works.length} work(s) and ${blobs.length} image(s) — ${mb} MB.`;
  } catch (e) {
    status.textContent = 'Export failed: ' + e.message;
  }
}

async function importLibrary(file) {
  const status = $('library-status');
  try {
    status.textContent = 'Reading…';
    const doc = JSON.parse(await file.text());
    const { works, blobs } = parseImport(doc);

    const existing = (await store.listWorks(db)).map(w => w.id);
    const { toAdd, skipped } = planMerge(existing, works);

    // Blobs are content-addressed, so writing them all is safe and idempotent.
    for (const b of blobs) {
      await store.putBlob(db, b.hash, new Blob([b.bytes], { type: b.mimeType }));
    }
    for (const w of toAdd) await store.saveWork(db, w);

    await renderList();
    status.textContent = `Imported ${toAdd.length} work(s)`
      + (skipped.length ? `; skipped ${skipped.length} already here.` : '.');
  } catch (e) {
    status.textContent = 'Import failed: ' + e.message;
  }
}

function wire() {
  $('btn-new').onclick = () => openEditor(null);
  $('btn-restore').onclick = restoreFromRepo;
  $('btn-export').onclick = exportLibrary;
  $('btn-import').onclick = () => $('f-import').click();
  $('f-import').onchange = async ev => {
    const file = ev.target.files[0];
    ev.target.value = '';
    if (file) await importLibrary(file);
  };
  $('btn-back').onclick = async () => { show('works'); await renderList(); };
  $('f-files').onchange = onFiles;
  $('btn-save').onclick = saveLocal;
  $('btn-delete').onclick = async () => {
    if (current?.id) {
      await store.deleteWork(db, current.id);
      // The work is gone; sweep any image blob nothing references any more,
      // or local storage grows forever. Shared blobs survive the sweep.
      await store.pruneOrphanBlobs(db);
    }
    show('works');
    await renderList();
  };
  $('btn-signin').onclick = async () => {
    const s = oauth.session();
    if (s?.did) { await oauth.signOut(); refreshWho(); return; }
    const h = prompt('Your handle (e.g. geocontrol.bsky.social):');
    if (h) await oauth.startLogin(h);
  };

  $('btn-publish').onclick = async () => {
    try {
      const client = await requireClient();
      if (!current?.body?.title) { $('editor-status').textContent = 'Save the work first.'; return; }
      if (!confirm(`Publish "${current.body.title}" to ${client.handle || client.did}? This is public.`)) return;
      $('editor-status').textContent = 'Publishing…';
      const res = await publishWork(client, client.did, current,
        h => store.getBlob(db, h).then(r => r?.blob));
      current.state = 'published';
      current.publishedUri = res.uri; current.publishedCid = res.cid;
      current.publishedCanonical = res.canonical; current.publishedImages = res.imageBlobRefs;
      current.updatedAt = new Date().toISOString();
      await store.saveWork(db, current);
      $('btn-unpublish').classList.remove('hidden');
      $('editor-status').textContent = 'Published.';
      await renderList();
    } catch (e) { $('editor-status').textContent = 'Publish failed: ' + e.message; }
  };

  $('btn-unpublish').onclick = async () => {
    try {
      const client = await requireClient();
      if (!confirm('Delete the public record? Your local copy stays.')) return;
      await unpublishWork(client, client.did, current);
      current.state = 'draft';
      delete current.publishedUri; delete current.publishedCid;
      delete current.publishedCanonical; delete current.publishedImages;
      current.updatedAt = new Date().toISOString();
      await store.saveWork(db, current);
      $('btn-unpublish').classList.add('hidden');
      $('editor-status').textContent = 'Unpublished.';
      await renderList();
    } catch (e) { $('editor-status').textContent = 'Unpublish failed: ' + e.message; }
  };

  $('btn-profile').onclick = async () => {
    try {
      const client = await requireClient();
      const name = prompt('Display name:'); if (!name) return;
      const bio = prompt('Bio (optional):') || '';
      const disciplines = (prompt('Disciplines, comma separated (optional):') || '')
        .split(',').map(x => x.trim()).filter(Boolean);
      const body = assembleProfile({ name, bio, disciplines, createdAt: new Date().toISOString() });
      await publishProfile(client, client.did, body);
      alert('Profile published.');
    } catch (e) { alert('Profile publish failed: ' + e.message); }
  };
}

boot();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
