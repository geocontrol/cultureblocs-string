// Cache the shell so Rounds opens in a hall with no connection. Bump CACHE
// whenever a shell file changes, or browsers will serve the old one.
const CACHE = 'rounds-2';
const SHELL = ['./', './index.html', './rounds.js', './lib/plan.js',
               './lib/records.js', './lib/store.js', './lib/string.js',
               './manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Never cache String traffic: stale stands are worse than none, and the
  // queue must reach a live String or stay queued.
  if (url.port === '8100' || url.pathname.startsWith('/records')) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
