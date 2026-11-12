// Jarvis Mobile Companion Service Worker
const CACHE_NAME = "jarvis-mobile-v2";
const APP_SHELL = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png"
];
// Shell assets are served network-first so a new deploy is never stale.
const SHELL_FILES = ["index.html", "style.css", "app.js", "manifest.webmanifest"];

function isShellAsset(url) {
  // A directory URL ("/mobile/" or "/mobile/?login=success") is index.html.
  if (url.pathname.endsWith("/")) return true;
  const file = url.pathname.split("/").pop();
  return SHELL_FILES.includes(file);
}

// Query strings (e.g. ?login=success) must not create cache variants of
// shell assets: the cache key for a shell asset is its bare path.
function cacheKeyFor(request) {
  const url = new URL(request.url);
  if (isShellAsset(url)) return url.origin + url.pathname;
  return request.url;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // One bad asset must not fail the whole install: cache each asset
      // individually and keep whatever succeeds.
      Promise.allSettled(APP_SHELL.map((asset) => cache.add(asset)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Only GET requests are cacheable; let everything else pass through.
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);

  // Network-only for API calls and health checks to ensure live agent operations
  if (url.pathname.startsWith("/api") || url.pathname.startsWith("/health")) {
    event.respondWith(fetch(event.request));
    return;
  }

  const cacheKey = cacheKeyFor(event.request);

  if (isShellAsset(url)) {
    // Network-first for the shell: a new deploy must reach the user at
    // once, not after the old cache expires. Falls back to cache offline.
    event.respondWith(
      fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.ok) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(cacheKey, responseToCache);
          });
        }
        return networkResponse;
      }).catch(async () => {
        const cached = await caches.match(cacheKey, { ignoreSearch: true });
        if (cached) return cached;
        // Offline with nothing cached for this asset: fall back to the
        // cached app shell so the PWA still opens instead of erroring.
        if (event.request.mode === "navigate") {
          const shell = await caches.match("./index.html", { ignoreSearch: true })
            || await caches.match("./", { ignoreSearch: true });
          if (shell) return shell;
        }
        return new Response("Offline", { status: 504 });
      })
    );
    return;
  }

  // Stale-while-revalidate for static UI assets (icons, manifest).
  event.respondWith(
    caches.match(cacheKey, { ignoreSearch: true }).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(cacheKey, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse || new Response("Offline", { status: 504 }));

      return cachedResponse || fetchPromise;
    })
  );
});
