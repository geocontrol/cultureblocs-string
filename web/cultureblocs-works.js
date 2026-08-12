// <cultureblocs-works actor="handle-or-did" limit="1"> — renders a creator's
// latest published com.cultureblocs.creative.work records. Dependency-free.
// Baked mode: <cultureblocs-works src="/path/works.json">.

const BSKY = 'https://public.api.bsky.app';
const PLC = 'https://plc.directory';

export function latest(records, limit = 1) {
  const sorted = [...records].sort((a, b) =>
    String(b.value?.createdAt || '').localeCompare(String(a.value?.createdAt || '')));
  return sorted.slice(0, Math.max(0, limit));
}

export function blobUrl(pdsBase, did, blobRef) {
  const cid = blobRef?.ref?.$link || blobRef?.cid;
  if (!cid) return null;
  return `${pdsBase}/xrpc/com.atproto.sync.getBlob`
    + `?did=${encodeURIComponent(did)}&cid=${encodeURIComponent(cid)}`;
}

export function cardModel(record) {
  const v = record?.value || {};
  const img = Array.isArray(v.images) && v.images.length ? v.images[0] : null;
  return {
    title: v.title || '',
    description: v.description || '',
    completionDate: v.completionDate || '',
    referenceUrl: v.referenceUrl || '',
    imageCid: img?.ref?.$link || img?.cid || null,
    imageAlt: img?.alt || v.title || '',
  };
}

async function resolveDid(actor) {
  if (actor.startsWith('did:')) return actor;
  const r = await fetch(`${BSKY}/xrpc/com.atproto.identity.resolveHandle?handle=${encodeURIComponent(actor)}`);
  if (!r.ok) throw new Error('resolveHandle failed');
  return (await r.json()).did;
}

async function resolvePds(did) {
  if (did.startsWith('did:web:')) {
    const host = did.slice('did:web:'.length);
    const r = await fetch(`https://${host}/.well-known/did.json`);
    return pdsFromDoc(await r.json());
  }
  const r = await fetch(`${PLC}/${encodeURIComponent(did)}`);
  return pdsFromDoc(await r.json());
}

function pdsFromDoc(doc) {
  const svc = (doc.service || []).find(s => s.id?.endsWith('#atproto_pds'));
  return svc?.serviceEndpoint;
}

async function fetchLive(actor, pdsOverride, limit) {
  const did = await resolveDid(actor);
  const pds = pdsOverride || await resolvePds(did);
  const url = `${pds}/xrpc/com.atproto.repo.listRecords`
    + `?repo=${encodeURIComponent(did)}&collection=com.cultureblocs.creative.work&limit=50`;
  const r = await fetch(url);
  if (!r.ok) throw new Error('listRecords failed');
  const records = (await r.json()).records || [];
  return { did, pds, works: latest(records, limit) };
}

async function fetchBaked(src, limit) {
  const r = await fetch(src);
  const doc = await r.json();
  // baked file carries pre-resolved image URLs; see works.sample.json
  return { did: null, pds: null, works: latest(doc.works || [], limit), baked: true };
}

function css() {
  return `
  :host{display:block;font-family:inherit;color:var(--cb-ink,#111)}
  .card{border:1px solid var(--cb-line,#e5e5e5);border-radius:12px;overflow:hidden;max-width:var(--cb-width,520px)}
  .card img{display:block;width:100%;height:auto;background:var(--cb-mute,#f4f4f4)}
  .body{padding:12px 14px}
  .title{font-weight:600;margin:0 0 4px}
  .meta{font-size:.85em;color:var(--cb-mute-ink,#666);margin:0 0 8px}
  .desc{margin:0 0 8px;line-height:1.4}
  a.ref{color:var(--cb-accent,#b5482e);text-decoration:none}
  `;
}

function renderCard(root, model, imgSrc) {
  const desc = model.description.length > 240
    ? model.description.slice(0, 240) + '…' : model.description;
  root.innerHTML = `<style>${css()}</style>
    <article class="card">
      ${imgSrc ? `<img src="${imgSrc}" alt="${escapeHtml(model.imageAlt)}">` : ''}
      <div class="body">
        <p class="title">${escapeHtml(model.title)}</p>
        ${model.completionDate ? `<p class="meta">${escapeHtml(model.completionDate)}</p>` : ''}
        ${desc ? `<p class="desc">${escapeHtml(desc)}</p>` : ''}
        ${model.referenceUrl ? `<a class="ref" href="${encodeURI(model.referenceUrl)}" target="_blank" rel="noopener">View work →</a>` : ''}
      </div>
    </article>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

async function run(el, root) {
  const limit = parseInt(el.getAttribute('limit') || '1', 10);
  const src = el.getAttribute('src');
  const actor = el.getAttribute('actor');
  const pds = el.getAttribute('pds');
  try {
    const res = src ? await fetchBaked(src, limit) : await fetchLive(actor, pds, limit);
    if (!res.works.length) { root.innerHTML = ''; return; }
    const rec = res.works[0];
    const model = cardModel(rec);
    let imgSrc = rec.value?.imageUrl || null;               // baked convenience
    if (!imgSrc && model.imageCid && res.pds && res.did) {
      imgSrc = blobUrl(res.pds, res.did, { ref: { $link: model.imageCid } });
    }
    renderCard(root, model, imgSrc);
  } catch (e) {
    root.innerHTML = '';  // fail silently on public pages
  }
}

if (typeof customElements !== 'undefined' && typeof HTMLElement !== 'undefined') {
  class CultureblocsWorks extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      run(this, root);
    }
  }
  if (!customElements.get('cultureblocs-works')) {
    customElements.define('cultureblocs-works', CultureblocsWorks);
  }
}
