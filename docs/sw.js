// Service Worker for TSGH Security Schedule PWA
// Strictly adheres to Zero-Cache policy for real-time security data

const CACHE_NAME = 'tsgh-pwa-shell-v20260905-v2';

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

// Network-only strategy for all API, dynamic schedule, and version handshake data (Strictly zero mobile cache)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Never cache API, dynamic schedule requests, json data files, or handshake endpoints
  if (
    url.pathname.startsWith('/api/') || 
    url.pathname.startsWith('/pwa') || 
    url.pathname.includes('/data/') || 
    url.pathname.includes('schedule') || 
    url.pathname.includes('version') ||
    url.pathname.endsWith('.json')
  ) {
    event.respondWith(
      fetch(event.request, {
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache'
        }
      })
    );
    return;
  }

  // Fallback direct network fetch
  event.respondWith(fetch(event.request));
});
