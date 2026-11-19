// Suscripción a avisos push de la PWA.
(function () {
  const boton = document.getElementById("activar-push");
  const caja = document.getElementById("caja-push");
  if (!boton || !("serviceWorker" in navigator) || !("PushManager" in window)) return;
  const aBytes = (b64) => {
    const relleno = "=".repeat((4 - (b64.length % 4)) % 4);
    const crudo = atob((b64 + relleno).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from([...crudo].map((c) => c.charCodeAt(0)));
  };
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
  navigator.serviceWorker.ready.then(async (reg) => {
    const actual = await reg.pushManager.getSubscription();
    if (actual && Notification.permission === "granted") return;
    caja.hidden = false;
    boton.addEventListener("click", async () => {
      const permiso = await Notification.requestPermission();
      if (permiso !== "granted") { boton.textContent = "Permiso negado: recibirás los avisos por correo"; return; }
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: aBytes(boton.dataset.vapid) });
      await fetch("/avisos/suscribir/", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify(sub) });
      caja.innerHTML = "<p>Listo, los avisos llegarán a este dispositivo.</p>";
    });
  });
})();
