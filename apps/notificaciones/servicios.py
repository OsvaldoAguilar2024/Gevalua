"""Envío de avisos: push de la PWA cuando hay suscripción y siempre respaldo por correo."""

import json
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection

from .models import Notificacion, SuscripcionPush

log = logging.getLogger(__name__)


def url_absoluta(ruta):
    if ruta.startswith("http"):
        return ruta
    dominio = getattr(connection, "tenant", None)
    host = None
    if dominio is not None and hasattr(dominio, "domains"):
        d = dominio.domains.filter(is_primary=True).first()
        host = d.domain if d else None
    return f"https://{host}{ruta}" if host else ruta


def enviar_push(usuario, titulo, mensaje, url):
    if not settings.VAPID_PRIVATE_KEY:
        return False, "Push sin configurar (faltan las claves VAPID)."
    from pywebpush import WebPushException, webpush

    enviada, errores = False, []
    for s in SuscripcionPush.objects.filter(usuario=usuario, activa=True):
        try:
            webpush(
                subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=json.dumps({"titulo": titulo, "mensaje": mensaje, "url": url}),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUB},
                ttl=60 * 60 * 24,
            )
            enviada = True
        except WebPushException as e:
            codigo = getattr(e.response, "status_code", None)
            if codigo in (404, 410):  # el navegador dio de baja la suscripción
                s.activa = False
                s.save(update_fields=["activa"])
            errores.append(str(e)[:300])
    if not enviada and not errores:
        return False, "Sin dispositivos suscritos."
    return enviada, "; ".join(errores)


def notificar(usuario, titulo, mensaje, url="", evento="", push=True, correo=True, recordatorio=None):
    """Envía por push y por correo y deja registro de cada intento."""
    destino = url_absoluta(url) if url else ""
    if push:
        ok, error = enviar_push(usuario, titulo, mensaje, url or "/")
        Notificacion.objects.create(usuario=usuario, recordatorio=recordatorio, evento=evento, titulo=titulo,
                                    mensaje=mensaje, url=url, canal=Notificacion.Canal.PUSH, enviada=ok, error=error)
    if correo:
        cuerpo = f"Hola {usuario.get_short_name()}:\n\n{mensaje}\n" + (f"\nEntra aquí: {destino}\n" if destino else "")
        try:
            send_mail(titulo, cuerpo, settings.DEFAULT_FROM_EMAIL, [usuario.email])
            ok, error = True, ""
        except Exception as e:  # noqa: BLE001 - se registra y se sigue con los demás
            log.exception("No se pudo enviar el correo a %s", usuario.email)
            ok, error = False, str(e)[:500]
        Notificacion.objects.create(usuario=usuario, recordatorio=recordatorio, evento=evento, titulo=titulo,
                                    mensaje=mensaje, url=url, canal=Notificacion.Canal.CORREO, enviada=ok, error=error)


def ya_avisado(evento):
    return Notificacion.objects.filter(evento=evento).exists()
