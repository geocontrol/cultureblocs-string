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

/* An images[] entry is an imageRef: {image: blob, alt?, aspectRatio?}.
 * The `item.image ?? item` fallback reads a bare blob too. That is not
 * migration scaffolding — this element takes an `actor` attribute and reads
 * any repository on the network, so records written to the older shape by
 * someone else stay renderable. */
export function imageFrom(item) {
  if (!item || typeof item !== 'object') return null;
  const blob = item.image || item;
  const cid = blob?.ref?.$link || blob?.cid || null;
  if (!cid) return null;
  const ar = item.aspectRatio;
  const width = Number.isInteger(ar?.width) && ar.width > 0 ? ar.width : null;
  const height = Number.isInteger(ar?.height) && ar.height > 0 ? ar.height : null;
  return {
    cid,
    alt: typeof item.alt === 'string' ? item.alt : '',
    width: width && height ? width : null,
    height: width && height ? height : null,
  };
}

export function cardModel(record) {
  const v = record?.value || {};
  const first = Array.isArray(v.images) && v.images.length ? v.images[0] : null;
  const img = imageFrom(first);
  return {
    title: v.title || '',
    description: v.description || '',
    completionDate: v.completionDate || '',
    referenceUrl: v.referenceUrl || '',
    imageCid: img?.cid || null,
    // No title fallback. An empty alt marks an image decorative and a screen
    // reader skips it; the title as alt makes it announce the title twice.
    imageAlt: img?.alt || '',
    imageWidth: img?.width || null,
    imageHeight: img?.height || null,
  };
}

export function safeHref(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return url;
    }
    return null;
  } catch {
    return null;
  }
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
  const href = safeHref(model.referenceUrl);
  root.innerHTML = `<style>${css()}</style>
    <article class="card">
      ${imgSrc ? `<img src="${escapeHtml(imgSrc)}" alt="${escapeHtml(model.imageAlt)}"${
        model.imageWidth ? ` width="${model.imageWidth}" height="${model.imageHeight}"` : ''
      }>` : ''}
      <div class="body">
        <p class="title">${escapeHtml(model.title)}</p>
        ${model.completionDate ? `<p class="meta">${escapeHtml(model.completionDate)}</p>` : ''}
        ${desc ? `<p class="desc">${escapeHtml(desc)}</p>` : ''}
        ${href ? `<a class="ref" href="${encodeURI(href)}" target="_blank" rel="noopener">View work →</a>` : ''}
      </div>
    </article>`;
}

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

/* Decide the <img src> for a rendered card.
 *
 * `imageUrl` is a convenience field for baked exports only (see fetchBaked,
 * which stamps `baked: true`) — it is never trusted from a live repo, because
 * lexicons tolerate unknown fields and a remote actor could publish their own
 * `imageUrl` on a com.cultureblocs.creative.work record. fetchLive never sets
 * `baked`, so `res.baked` gates this: only a locally-baked file, which this
 * page's own build controls, gets to pick the image URL directly. Anything
 * else falls through to a blob URL built from the record's own image cid. */
export function resolveImgSrc(rec, model, res) {
  let imgSrc = (res?.baked && rec?.value?.imageUrl) || null;
  if (!imgSrc && model.imageCid && res?.pds && res?.did) {
    imgSrc = blobUrl(res.pds, res.did, { ref: { $link: model.imageCid } });
  }
  return imgSrc;
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
    const imgSrc = resolveImgSrc(rec, model, res);
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
