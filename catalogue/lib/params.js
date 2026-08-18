// Pure reading of the catalogue's URL parameters. No DOM, no network.

export const TEMPLATES = ['grid', 'index', 'feature'];
export const DEFAULT_TEMPLATE = 'grid';

/* A stylesheet from another origin would let anyone craft a URL on a trusted
 * domain that restyles the page. CSS cannot execute script, but it can hide,
 * overlay and fabricate text well enough to mislead. Same-origin only costs
 * nothing: whoever copied this bundle to their own host serves their own CSS
 * from their own origin anyway.
 *
 * `pageUrl` must be the page's own URL (e.g. window.location.href), not just
 * its origin: a relative `?css=mine.css` has to resolve against the page's
 * own directory, the same way a plain <link href="mine.css"> would. Resolving
 * against the origin root instead breaks exactly the self-hosters this
 * feature exists for — a bundle copied to example.com/art/ would look for
 * /mine.css instead of /art/mine.css. The same-origin guard is unaffected:
 * it still compares the resolved URL's origin against pageUrl's origin. */
export function safeCssHref(raw, pageUrl) {
  if (!raw || typeof raw !== 'string') return null;
  let base;
  try {
    base = new URL(pageUrl);
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

export function parseParams(search, pageUrl) {
  const q = new URLSearchParams(search || '');
  const rawActor = (q.get('actor') || '').trim();
  const rawTemplate = (q.get('template') || '').trim();
  return {
    actor: rawActor || null,
    // An unknown name must not reach a <link href>, or it becomes a path probe.
    template: TEMPLATES.includes(rawTemplate) ? rawTemplate : DEFAULT_TEMPLATE,
    cssHref: safeCssHref(q.get('css'), pageUrl),
  };
}
