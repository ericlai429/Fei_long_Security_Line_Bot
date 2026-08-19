// Service Worker for TSGH Security Schedule PWA
// Strictly adheres to Zero-Cache policy for real-time security data

const CACHE_NAME = 'tsgh-pwa-shell-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Clear all old caches
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.map((key) => caches.delete(key)));
    }).then(() => self.clients.claim())
  );
});

// Network-only strategy for all API and schedule data
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Never cache API or dynamic schedule requests
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/pwa')) {
    event.respondWith(
      fetch(event.request, {
        cache: 'no-store'
      })
    );
    return;
  }

  // Fallback direct network fetch
  event.respondWith(fetch(event.request));
});
