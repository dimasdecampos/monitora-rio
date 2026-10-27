// Service worker (vale para todas as bacias): deixa o painel instalável e mostra a última leitura mesmo sem internet.
// Páginas e dados: rede primeiro (sempre o mais novo), cópia guardada só se a rede falhar.
// Bibliotecas (CDN) e ícones: cópia guardada primeiro (não mudam).
const VERSAO = "v4";
const CACHE = `monitor-${VERSAO}`;
const BASICO = ["./", "index.html", "bacias.json", "manifest.webmanifest", "privacidade.html", "icones/icone-192.png"];   // cada painel é guardado na primeira visita

self.addEventListener("install", ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(BASICO)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", ev => {
  ev.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

const fixo = url => /cdnjs\.cloudflare\.com|icones\//.test(url);
const mapa = url => /tile\.openstreetmap\.org/.test(url);

self.addEventListener("fetch", ev => {
  const req = ev.request;
  if (req.method !== "GET") return;
  if (fixo(req.url)) {
    ev.respondWith(caches.match(req).then(c => c || fetch(req).then(r => { const copia = r.clone(); caches.open(CACHE).then(k => k.put(req, copia)); return r; })));
    return;
  }
  if (mapa(req.url)) return;   // pedaços do mapa: direto da rede (não enche o celular)
  ev.respondWith(
    fetch(req).then(r => {
      if (r.ok) { const copia = r.clone(); caches.open(CACHE).then(k => k.put(req, copia)); }
      return r;
    }).catch(() => caches.match(req, { ignoreSearch: req.mode === "navigate" }).then(c => c || caches.match("index.html")))
  );
});

// aviso de cheia enviado pelo robô (Web Push): chega mesmo com o app fechado
self.addEventListener("push", ev => {
  let d = {};
  try { d = ev.data ? ev.data.json() : {}; } catch { d = { corpo: ev.data ? ev.data.text() : "" }; }
  ev.waitUntil(self.registration.showNotification(d.titulo || "Monitor dos Rios", {
    body: d.corpo || "", icon: "icones/icone-192.png", badge: "icones/icone-192.png",
    tag: d.tag || "monitor", renotify: true, requireInteraction: !!d.urgente,
    vibrate: d.urgente ? [400, 150, 400, 150, 800] : [200], data: { url: d.url || "./" },
  }));
});

// toque num aviso abre o painel do rio
self.addEventListener("notificationclick", ev => {
  ev.notification.close();
  const url = new URL(ev.notification.data?.url || "./", self.registration.scope).href;
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(ws => {
    const mesma = ws.find(w => w.url.split("?")[0] === url.split("?")[0]);
    return mesma ? mesma.focus() : self.clients.openWindow(url);
  }));
});
