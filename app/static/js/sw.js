// MyAudioShelf service worker: makes the site installable as an app, keeps
// artwork on the device for faster repeat visits, and shows a branded page
// while the server restarts or the visitor is offline. Pages themselves are
// never stored: each one carries a fresh security token for its forms.
const SHELL_CACHE = 'myaudioshelf-shell-v1';
const ARTWORK_CACHE = 'myaudioshelf-artwork-v1';
const ARTWORK_LIMIT = 160;
const SHELL = ['/static/icons/app-192.png'];
// Purchases, downloads and staff tools always go straight to the server.
const PASS_THROUGH = ['/media/private/', '/library/download/', '/admin', '/checkout'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  const current = [SHELL_CACHE, ARTWORK_CACHE];
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('myaudioshelf-') && !current.includes(key)).map(key => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || PASS_THROUGH.some(path => url.pathname.startsWith(path))) return;
  if (request.mode === 'navigate') {
    event.respondWith(navigate(request));
    return;
  }
  // Covers and site imagery only: audio uses byte ranges and stays with the browser.
  const artwork = request.destination === 'image' && (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/public/'));
  if (artwork) event.respondWith(artworkFirst(event, request));
});

// Show the saved copy at once, then refresh it in the background for next time.
async function artworkFirst(event, request) {
  const cache = await caches.open(ARTWORK_CACHE);
  const cached = await cache.match(request) || await caches.match(request);
  const refresh = fetch(request).then(async response => {
    if (response.ok && response.type === 'basic') {
      await cache.put(request, response.clone());
      await trimArtwork(cache);
    }
    return response;
  });
  event.waitUntil(refresh.catch(() => {}));
  return cached || refresh;
}

// Keep the newest artwork only, so the shelf never fills the device.
async function trimArtwork(cache) {
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - ARTWORK_LIMIT))) await cache.delete(key);
}

// A restarting or redeploying server answers 502/503/504 for a few seconds.
const GATEWAY_ERRORS = [502, 503, 504];
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function navigate(request) {
  try {
    let response = await fetch(request);
    if (!GATEWAY_ERRORS.includes(response.status)) return response;
    await wait(1500);
    response = await fetch(request);
    if (!GATEWAY_ERRORS.includes(response.status)) return response;
    return statusPage('restarting');
  } catch {
    return statusPage('offline');
  }
}

// A self-contained page in the site's colours; it reloads by itself once the site answers.
function statusPage(reason) {
  const offline = reason === 'offline';
  const title = offline ? 'You’re offline' : 'Back in a moment';
  const text = offline
    ? 'MyAudioShelf needs a connection to open this page. It will reload by itself as soon as you’re back online.'
    : 'MyAudioShelf is getting ready. This page will reload by itself in a few seconds.';
  const html = `<!doctype html><html lang="en" data-color-mode="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#111813"><title>${title} · MyAudioShelf</title>
<style>
*{box-sizing:border-box}
html{color-scheme:dark;--paper:#111813;--surface:#19231c;--ink:#edf0e7;--muted:#b4beb0;--line:#3b493d;--lime:#c7f000}
html[data-color-mode=light]{color-scheme:light;--paper:#f9f8f3;--surface:#fff;--ink:#20241e;--muted:#6b7065;--line:#dedfd4}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 50% 18%,rgba(199,240,0,.09),transparent 55%),var(--paper);color:var(--ink);font:15px/1.6 "Avenir Next",Avenir,"Helvetica Neue",system-ui,sans-serif}
.card{position:relative;overflow:hidden;width:100%;max-width:390px;padding:34px 30px 28px;text-align:center;background:var(--surface);border:1px solid var(--line);border-radius:22px;box-shadow:0 30px 70px -28px rgba(0,0,0,.6)}
.card:before{content:"";position:absolute;inset:0 0 auto;height:4px;background:linear-gradient(90deg,var(--lime),#7fbf00)}
img{width:64px;height:64px;border-radius:16px;box-shadow:0 10px 24px -10px rgba(0,0,0,.6)}
h1{font-size:21px;font-weight:600;letter-spacing:-.02em;margin:20px 0 8px}
p{color:var(--muted);margin:0;font-size:14px}
.bar{height:3px;border-radius:3px;background:color-mix(in srgb,var(--lime) 16%,transparent);overflow:hidden;margin:24px 0 20px}
.bar span{display:block;height:100%;width:35%;border-radius:3px;background:var(--lime);animation:slide 1.4s ease-in-out infinite}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(300%)}}
@media (prefers-reduced-motion:reduce){.bar span{animation:none;width:100%}}
button{font:inherit;font-size:14px;font-weight:700;background:var(--lime);color:#20241e;border:0;border-radius:12px;padding:11px 22px;cursor:pointer}
</style></head><body><main class="card" role="status"><img src="/static/icons/app-192.png" alt="MyAudioShelf"><h1>${title}</h1><p>${text}</p><div class="bar" aria-hidden="true"><span></span></div><button type="button" onclick="location.reload()">Try now</button></main>
<script>
try{if(localStorage.getItem('myaudioshelf-theme')==='light')document.documentElement.dataset.colorMode='light'}catch(e){}
(function(){var tries=0;function check(){tries++;fetch(location.href,{cache:'no-store'}).then(function(r){if(r.ok){location.reload()}else{setTimeout(check,Math.min(15000,3000+tries*1000))}}).catch(function(){setTimeout(check,5000)})}window.addEventListener('online',function(){location.reload()});setTimeout(check,3000)})()
</script></body></html>`;
  return new Response(html, {status: 503, headers: {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Retry-After': '5'}});
}
