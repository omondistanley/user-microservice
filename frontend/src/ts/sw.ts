/* Service worker: no caching for /static/* so CSS/JS UI updates load immediately.
   API GET requests stay network-first with cache only as offline fallback.
   Build: npm run build:js (outputs static/sw.js). */
/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

const CACHE_VERSION = 'v4';
const API_CACHE = 'expense-api-' + CACHE_VERSION;

self.addEventListener('install', function (e: ExtendableEvent) {
    e.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function (e: ExtendableEvent) {
    e.waitUntil(
        caches
            .keys()
            .then(function (keys) {
                return Promise.all(
                    keys
                        .filter(function (k) {
                            return k.startsWith('expense-');
                        })
                        .map(function (k) {
                            return caches.delete(k);
                        })
                );
            })
            .then(function () {
                return self.clients.claim();
            })
    );
});

self.addEventListener('fetch', function (e: FetchEvent) {
    const url = new URL(e.request.url);
    if (url.origin !== self.location.origin) return;

    if (url.pathname.indexOf('/static/') === 0 && e.request.method === 'GET') {
        e.respondWith(fetch(e.request));
        return;
    }

    if (url.pathname.indexOf('/api/') !== -1 && e.request.method === 'GET') {
        e.respondWith(
            fetch(e.request)
                .then(function (res) {
                    const clone = res.clone();
                    if (res.ok) {
                        caches.open(API_CACHE).then(function (cache) {
                            cache.put(e.request, clone);
                        });
                    }
                    return res;
                })
                .catch(function () {
                    return caches.match(e.request);
                })
        );
        return;
    }
});

export {};
