/**
 * public/sw.js
 *
 * Offline-shell service worker for TweakHub's PWA install. Deliberately
 * scoped: it does NOT try to make tool processing work offline (every
 * tool call is a real request to the API — there's nothing meaningful to
 * cache or replay there, and pretending otherwise would be dishonest
 * about what this app can do without a connection). What it does cache:
 *
 * - The static app shell (manifest, icons, offline fallback page) —
 *   precached on install so the branded chrome is available immediately.
 * - Next.js's fingerprinted build assets under /_next/static/ —
 *   cache-first, since a fingerprinted URL never changes content, so
 *   there's no staleness risk.
 * - Page navigations — network-first with a cache fallback, so a
 *   previously-visited page still opens (from cache) when offline;
 *   falls back further to /offline.html when nothing cached matches.
 *
 * Never intercepts non-GET requests or cross-origin requests (the API
 * calls to NEXT_PUBLIC_API_URL, which is a different origin in every
 * real deployment) — those always go straight to the network.
 */

const CACHE_VERSION = "tweakhub-shell-v1";
const SHELL_URLS = ["/", "/manifest.json", "/icon-192.png", "/icon-512.png", "/favicon.ico", "/offline.html"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function isNextStaticAsset(url) {
  return url.pathname.startsWith("/_next/static/");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only ever handle same-origin GETs — API calls (a different origin in
  // every real deployment) and any mutating request pass straight through
  // untouched.
  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          return cached || (await caches.match("/")) || (await caches.match("/offline.html"));
        })
    );
    return;
  }

  if (isNextStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            const copy = response.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
            return response;
          })
      )
    );
    return;
  }

  if (SHELL_URLS.includes(url.pathname)) {
    // Stale-while-revalidate: serve the cached copy immediately if there
    // is one, but always refresh it in the background so an icon/manifest
    // update ships on the next load rather than being stuck forever.
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request).then((response) => {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
          return response;
        });
        return cached || network;
      })
    );
  }
});
