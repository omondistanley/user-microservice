/* Phase 6: Service worker — cache-first static, network-first API. Version for invalidation. */
const CACHE_VERSION = 'v1';
const STATIC_CACHE = 'expense-static-' + CACHE_VERSION;
const API_CACHE = 'expense-api-' + CACHE_VERSION;

const STATIC_ASSETS = [
  '/static/css/main.css',
  '/static/js/auth.js',
  '/static/js/app.js',
  '/static/js/layout.js',
  '/static/js/settings.js',
  '/static/js/notifications.js',
  '/static/manifest.json'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(STATIC_ASSETS).catch(function () {});
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) {
            return k.startsWith('expense-') && k !== STATIC_CACHE && k !== API_CACHE;
          })
          .map(function (k) { return caches.delete(k); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf('/static/') === 0 && e.request.method === 'GET') {
    e.respondWith(
      caches.match(e.request).then(function (cached) {
        return cached || fetch(e.request).then(function (res) {
          var clone = res.clone();
          caches.open(STATIC_CACHE).then(function (cache) { cache.put(e.request, clone); });
          return res;
        });
      })
    );
    return;
  }
  if (url.pathname.indexOf('/api/') !== -1 && e.request.method === 'GET') {
    e.respondWith(
      fetch(e.request).then(function (res) {
        var clone = res.clone();
        if (res.ok) {
          caches.open(API_CACHE).then(function (cache) { cache.put(e.request, clone); });
        }
        return res;
      }).catch(function () {
        return caches.match(e.request);
      })
    );
    return;
  }
});
