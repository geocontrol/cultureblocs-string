import * as store from './lib/store.js';
import { assembleWork, assembleProfile, isDrifted } from './lib/records.js';
import { downscaleDims, renderToBlob } from './lib/image.js';
import { makeRkey } from './lib/rkey.js';
import * as oauth from './oauth.js';
import { publishWork, unpublishWork, publishProfile } from './lib/publish.js';

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
  $('who').textContent = s?.did ? `signed in: ${s.handle || s.did}` : 'not signed in';
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

async function renderThumbs() {
  const el = $('thumbs'); el.innerHTML = '';
  const hashes = [...(current.imageHashes || []), ...pendingImages.map(p => p.hash)];
  for (const h of hashes) {
    const staged = pendingImages.find(p => p.hash === h);
    const blob = staged ? staged.blob : (await store.getBlob(db, h))?.blob;
    if (blob) { const img = document.createElement('img'); img.src = URL.createObjectURL(blob); el.appendChild(img); }
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
      pendingImages.push({ hash, blob, alt: '' });
  }
  ev.target.value = '';
  await renderThumbs();
}

async function saveLocal() {
  if (!$('f-title').value.trim()) { $('editor-status').textContent = 'Title is required.'; return; }
  for (const p of pendingImages) { await store.putBlob(db, p.hash, p.blob); current.imageHashes.push(p.hash); }
  pendingImages = [];
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
      isDrifted(current.publishedCanonical, assembleWork(current.body, current.publishedImages || [])))
    current.state = 'edited';
  await store.saveWork(db, current);
  $('editor-status').textContent = 'Saved locally.';
  await renderList();
}

function wire() {
  $('btn-new').onclick = () => openEditor(null);
  $('btn-back').onclick = async () => { show('works'); await renderList(); };
  $('f-files').onchange = onFiles;
  $('btn-save').onclick = saveLocal;
  $('btn-delete').onclick = async () => { if (current?.id) await store.deleteWork(db, current.id); show('works'); await renderList(); };
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
