"""Segundo factor para administradores y operadores, y autorización de datos personales (Ley 1581) al primer ingreso.

Segundo factor: después de la contraseña, la plataforma envía un código de un solo uso al correo (el mismo
mecanismo de las firmas). El código vive solo en la sesión, como huella. Se puede recordar el dispositivo 30 días.
"""

import secrets
import time

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.core.mail import send_mail
from django.utils.crypto import salted_hmac

VIGENCIA_SEGUNDOS = 10 * 60
ESPERA_REENVIO_SEGUNDOS = 60
MAX_INTENTOS = 5
DIAS_RECORDAR = 30
COOKIE_DISPOSITIVO = "gevalua_dispositivo"
SAL_COOKIE = "gevalua.segundo_factor.dispositivo"
CLAVE_SESION = "segundo_factor"

# Rutas que se pueden usar antes del segundo factor o de la autorización de datos.
RUTAS_LIBRES = ("/cuenta/verificar/", "/cuenta/salir/", "/cuenta/datos-personales/", "/operador/logout/",
                "/static/", "/salud/", "/sw.js", "/manifest.webmanifest", "/ingreso/firma/")


def es_publico(request):
    tenant = getattr(request, "tenant", None)
    return tenant is None or tenant.schema_name == "public"


def requiere_segundo_factor(request):
    u = request.user
    if not settings.SEGUNDO_FACTOR_OBLIGATORIO or not u.is_authenticated:
        return False
    tenant = getattr(request, "tenant", None)
    if tenant is not None and tenant.schema_name in settings.SEGUNDO_FACTOR_EXENTOS:
        return False
    return bool(u.is_staff if es_publico(request) else u.es_admin_empresa)


def _esquema(request):
    tenant = getattr(request, "tenant", None)
    return tenant.schema_name if tenant else "public"


def _huella_usuario(usuario):
    # Cambia si cambia la contraseña: un dispositivo recordado deja de valer al cambiarla.
    return salted_hmac(SAL_COOKIE, f"{usuario.pk}:{usuario.password}").hexdigest()[:20]


def verificado(request):
    datos = request.session.get(CLAVE_SESION) or {}
    if datos.get("ok") == request.user.pk:
        return True
    try:
        valor = request.get_signed_cookie(COOKIE_DISPOSITIVO, salt=SAL_COOKIE, max_age=DIAS_RECORDAR * 86400)
        d = signing.loads(valor, salt=SAL_COOKIE)
    except (KeyError, signing.BadSignature, ValueError):
        return False
    if d.get("u") == request.user.pk and d.get("s") == _esquema(request) and d.get("h") == _huella_usuario(request.user):
        marcar_verificado(request)
        return True
    return False


def marcar_verificado(request):
    request.session[CLAVE_SESION] = {"ok": request.user.pk}


def recordar_dispositivo(request, respuesta):
    valor = signing.dumps({"u": request.user.pk, "s": _esquema(request), "h": _huella_usuario(request.user)}, salt=SAL_COOKIE)
    respuesta.set_signed_cookie(
        COOKIE_DISPOSITIVO, valor, salt=SAL_COOKIE, max_age=DIAS_RECORDAR * 86400,
        secure=not settings.DEBUG, httponly=True, samesite="Lax",
    )


def enviar_codigo(request, forzar=False):
    """Envía un código nuevo, salvo que se haya enviado uno hace menos de un minuto. Devuelve True si envió."""
    ahora = time.time()
    datos = request.session.get(CLAVE_SESION) or {}
    if datos.get("usuario") == request.user.pk and ahora - datos.get("enviado", 0) < ESPERA_REENVIO_SEGUNDOS:
        return False
    if not forzar and datos.get("usuario") == request.user.pk and ahora < datos.get("expira", 0):
        return False
    codigo = f"{secrets.randbelow(10**6):06d}"
    request.session[CLAVE_SESION] = {
        "usuario": request.user.pk, "hash": make_password(codigo), "expira": ahora + VIGENCIA_SEGUNDOS,
        "enviado": ahora, "intentos": 0,
    }
    send_mail(
        f"Tu código para entrar: {codigo}",
        f"Hola {request.user.get_short_name()}:\n\nTu código para entrar a gevalua es:\n\n    {codigo}\n\n"
        f"Vence en {VIGENCIA_SEGUNDOS // 60} minutos. Si no fuiste tú, cambia tu contraseña y avisa a soporte.",
        settings.DEFAULT_FROM_EMAIL,
        [request.user.email],
    )
    return True


class ErrorCodigo(Exception):
    pass


def validar_codigo(request, codigo):
    datos = request.session.get(CLAVE_SESION) or {}
    if datos.get("usuario") != request.user.pk or "hash" not in datos:
        raise ErrorCodigo("Pide un código primero.")
    if time.time() > datos["expira"]:
        raise ErrorCodigo("El código venció. Pide uno nuevo.")
    if datos["intentos"] >= MAX_INTENTOS:
        raise ErrorCodigo("Demasiados intentos. Pide un código nuevo.")
    if not check_password((codigo or "").strip(), datos["hash"]):
        datos["intentos"] += 1
        request.session[CLAVE_SESION] = datos
        raise ErrorCodigo("Código incorrecto.")
    marcar_verificado(request)


# --- Autorización de datos personales (Ley 1581 de 2012) ---------------------------------------------------

def requiere_autorizacion_datos(request):
    u = request.user
    return (
        settings.AUTORIZACION_DATOS_OBLIGATORIA and u.is_authenticated and not es_publico(request)
        and u.acepto_tratamiento_datos is None
    )
