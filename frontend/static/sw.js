"use strict";
const CACHE_VERSION = "v4";
const API_CACHE = "expense-api-" + CACHE_VERSION;
self.addEventListener("install", function(e) {
  e.waitUntil(self.skipWaiting());
});
self.addEventListener("activate", function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) {
          return k.startsWith("expense-");
        }).map(function(k) {
          return caches.delete(k);
        })
      );
    }).then(function() {
      return self.clients.claim();
    })
  );
});
self.addEventListener("fetch", function(e) {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/static/") === 0 && e.request.method === "GET") {
    e.respondWith(fetch(e.request));
    return;
  }
  if (url.pathname.indexOf("/api/") !== -1 && e.request.method === "GET") {
    e.respondWith(
      fetch(e.request).then(function(res) {
        const clone = res.clone();
        if (res.ok) {
          caches.open(API_CACHE).then(function(cache) {
            cache.put(e.request, clone);
          });
        }
        return res;
      }).catch(function() {
        return caches.match(e.request);
      })
    );
    return;
  }
});
export {};
