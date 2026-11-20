// Service worker mínimo: permite instalar la PWA y muestra una página sin conexión.
const CACHE = "gevalua-v3";
const OFFLINE = "/static/offline.html";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.add(OFFLINE)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match(OFFLINE)));
  }
});

self.addEventListener("push", (e) => {
  let datos = { titulo: "DVQ-Evalua", mensaje: "", url: "/" };
  try { datos = Object.assign(datos, e.data.json()); } catch (_) {}
  e.waitUntil(self.registration.showNotification(datos.titulo, {
    body: datos.mensaje, icon: "/static/img/icono-192.png", badge: "/static/img/icono-192.png", data: { url: datos.url },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data && e.notification.data.url ? e.notification.data.url : "/"));
});
