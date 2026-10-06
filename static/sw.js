// Service worker: lets the app open offline. Data is kept by the page itself (IndexedDB) and synced when online.
const SHELL = "cof-shell-v2", IMG = "cof-img-v1", FONT = "cof-fonts-v1";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (![SHELL, IMG, FONT].includes(k)) await caches.delete(k);
  await self.clients.claim();
  try { const res = await fetch("/", { credentials: "same-origin" }); if (res.ok && !res.redirected) (await caches.open(SHELL)).put("/", res); } catch (e) {}
})()));
async function nav(req) {
  try {
    const res = await fetch(req);
    if (res.ok && !res.redirected && new URL(req.url).pathname === "/") (await caches.open(SHELL)).put("/", res.clone());
    return res;
  } catch (err) {
    return (await caches.match("/")) || new Response("<h1>You are offline</h1><p>Open the app once while online to use it offline.</p>", { status: 503, headers: { "Content-Type": "text/html" } });
  }
}
async function cacheFirst(req, name) {
  const c = await caches.open(name), hit = await c.match(req);
  if (hit) return hit;
  try { const res = await fetch(req); if (res.ok || res.type === "opaque") c.put(req, res.clone()); return res; }
  catch (e) { return Response.error(); }
}
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET") return;
  if (r.mode === "navigate" || (u.origin === location.origin && u.pathname === "/")) return e.respondWith(nav(r));
  if (u.origin === location.origin && u.pathname.startsWith("/api/img/")) return e.respondWith(cacheFirst(r, IMG));
  if (u.origin === location.origin && u.pathname.startsWith("/icons/")) return e.respondWith(cacheFirst(r, SHELL));
  if (u.hostname === "fonts.googleapis.com" || u.hostname === "fonts.gstatic.com") return e.respondWith(cacheFirst(r, FONT));
});
