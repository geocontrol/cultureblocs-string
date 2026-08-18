// Pure reading of the catalogue's URL parameters. No DOM, no network.

export const TEMPLATES = ['grid', 'index', 'feature'];
export const DEFAULT_TEMPLATE = 'grid';

/* A stylesheet from another origin would let anyone craft a URL on a trusted
 * domain that restyles the page. CSS cannot execute script, but it can hide,
 * overlay and fabricate text well enough to mislead. Same-origin only costs
 * nothing: whoever copied this bundle to their own host serves their own CSS
 * from their own origin anyway. */
export function safeCssHref(raw, origin) {
  if (!raw || typeof raw !== 'string') return null;
  let base;
  try {
    base = new URL(origin);
  } catch {
    return null;
  }
  let u;
  try {
    u = new URL(raw, base);
  } catch {
    return null;
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
  if (u.origin !== base.origin) return null;
  return u.pathname + u.search;
}

export function parseParams(search, origin) {
  const q = new URLSearchParams(search || '');
  const rawActor = (q.get('actor') || '').trim();
  const rawTemplate = (q.get('template') || '').trim();
  return {
    actor: rawActor || null,
    // An unknown name must not reach a <link href>, or it becomes a path probe.
    template: TEMPLATES.includes(rawTemplate) ? rawTemplate : DEFAULT_TEMPLATE,
    cssHref: safeCssHref(q.get('css'), origin),
  };
}
