/* Network-first with a cache fallback.
 *
 * The previous revision was cache-first with no revalidation and no activate
 * handler, which pinned every visitor to the first build they ever loaded —
 * fixes could never reach them. Offline still works (the shell is cached on
 * install and served whenever the network fails), but a reachable network
 * always wins, so a deploy takes effect on the next load.
 *
 * Bump CACHE on any shell change; activate deletes every other cache. */
const CACHE = 'easel-2';
const SHELL = ['./', './index.html', './easel.js', './oauth.js',
  './lib/store.js','./lib/records.js','./lib/image.js','./lib/rkey.js','./lib/publish.js',
  './manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(names => Promise.all(names.filter(n => n !== CACHE).map(n => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;              // never touch uploads/publishes
  if (new URL(e.request.url).origin !== location.origin) return;  // leave PDS/XRPC traffic alone
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
