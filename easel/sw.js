const CACHE = 'easel-1';
const SHELL = ['./', './index.html', './easel.js', './oauth.js',
  './lib/store.js','./lib/records.js','./lib/image.js','./lib/rkey.js','./lib/publish.js',
  './manifest.webmanifest'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))));
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;         // never touch uploads/publishes
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
