// Pure record -> model -> HTML. No DOM APIs, no network, no Shadow DOM:
// the markup below is the public contract that templates style, so the class
// names are an API and must not be renamed casually.
import { imageFrom, blobUrl, safeHref, escapeHtml } from '../cultureblocs-works.js';

export function profileModel(record, actor) {
  const v = record?.value || {};
  return {
    name: v.name || actor || '',
    bio: v.bio || '',
    disciplines: Array.isArray(v.disciplines) ? v.disciplines : [],
    based: v.based?.name || '',
    links: (Array.isArray(v.links) ? v.links : [])
      .map(l => ({ uri: safeHref(l?.uri), title: l?.title || l?.uri || 'link' }))
      .filter(l => l.uri),
  };
}

export function workModel(record, pds, did) {
  const v = record?.value || {};
  const first = Array.isArray(v.images) && v.images.length ? v.images[0] : null;
  const img = imageFrom(first);
  return {
    uri: record?.uri || '',
    title: v.title || '',
    description: v.description || '',
    completionDate: v.completionDate || '',
    referenceUrl: safeHref(v.referenceUrl),
    createdAt: v.createdAt || '',
    imageSrc: img ? blobUrl(pds, did, { ref: { $link: img.cid } }) : null,
    // No title fallback: an absent alt renders empty. A title used as alt makes
    // a screen reader announce it twice, once as the image and once as the heading.
    alt: img?.alt || '',
    width: img?.width || null,
    height: img?.height || null,
  };
}

export function renderProfile(m) {
  const meta = [m.disciplines.join(' · '), m.based].filter(Boolean).join(' · ');
  return `<header class="cb-profile">
  <h1 class="cb-profile-name">${escapeHtml(m.name)}</h1>
  ${meta ? `<p class="cb-profile-meta">${escapeHtml(meta)}</p>` : ''}
  ${m.bio ? `<p class="cb-profile-bio">${escapeHtml(m.bio)}</p>` : ''}
  ${m.links.length ? `<ul class="cb-profile-links">${m.links.map(l =>
    `<li><a href="${escapeHtml(l.uri)}" rel="noopener nofollow ugc">${escapeHtml(l.title)}</a></li>`).join('')}</ul>` : ''}
</header>`;
}

export function renderWork(m, extras = {}) {
  const dims = m.width && m.height ? ` width="${m.width}" height="${m.height}"` : '';
  const refs = Array.isArray(extras.references) && extras.references.length
    ? `<ul class="cb-work-references">${extras.references.map(r =>
        `<li>${escapeHtml(r)}</li>`).join('')}</ul>`
    : '';
  return `<article class="cb-work">
  ${m.imageSrc ? `<img class="cb-work-image" src="${escapeHtml(m.imageSrc)}" alt="${escapeHtml(m.alt)}"${dims} loading="lazy">` : ''}
  <h2 class="cb-work-title">${escapeHtml(m.title)}</h2>
  ${m.completionDate ? `<p class="cb-work-meta">${escapeHtml(m.completionDate)}</p>` : ''}
  ${m.description ? `<p class="cb-work-desc">${escapeHtml(m.description)}</p>` : ''}
  ${m.referenceUrl ? `<a class="cb-work-link" href="${escapeHtml(m.referenceUrl)}" rel="noopener nofollow ugc">View work</a>` : ''}
  ${refs}
</article>`;
}

export function renderCatalogue(profile, works, extras = {}) {
  return renderProfile(profile)
    + `<section class="cb-catalogue">`
    + works.map(w => renderWork(w, extras)).join('')
    + `</section>`;
}
