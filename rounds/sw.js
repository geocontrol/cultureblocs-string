// Cache the shell so Rounds opens in a hall with no connection. Bump CACHE
// whenever a shell file changes, or browsers will serve the old one.
const CACHE = 'rounds-4';
const SHELL = ['./', './index.html', './rounds.js', './lib/plan.js',
               './lib/records.js', './lib/store.js', './lib/string.js',
               './manifest.webmanifest'];

self.addEventListener('install', e => {
  // Take over as soon as the new shell is cached. Without this a new worker
  // waits for every tab running the old one to close, so a user who merely
  // reloads keeps the previous build — which for this app meant keeping a
  // version that could lose a note.
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const ks = await caches.keys();
    await Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();   // control open pages immediately, not just future ones
  })());
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Never cache String traffic: stale stands are worse than none, and the
  // queue must reach a live String or stay queued.
  if (url.port === '8100' || url.pathname.startsWith('/records')) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
