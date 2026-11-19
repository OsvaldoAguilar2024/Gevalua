"""Firma electrónica propia: código de un solo uso por correo, con huella del documento y evidencias.

El texto de aceptación es provisional: Gio lo valida como abogado antes de producción.
"""

import hashlib
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone

from apps.nucleo.auditoria import ip_de, registrar

from .models import CodigoFirma, Firma

VIGENCIA_CODIGO = timedelta(minutes=10)
MAX_INTENTOS = 5

TEXTO_ACEPTACION = (
    "Declaro que leí el documento «{titulo}», que estoy de acuerdo con su contenido y que lo firmo electrónicamente "
    "con el código de un solo uso enviado a mi correo {email}. Acepto que esta firma tiene la misma validez que mi "
    "firma manuscrita, de acuerdo con la Ley 527 de 1999 y el Decreto 2364 de 2012."
)


class ErrorFirma(Exception):
    pass


def huella(contenido):
    """SHA-256 de una representación canónica del documento (dict o texto)."""
    if not isinstance(contenido, (str, bytes)):
        contenido = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str)
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    return hashlib.sha256(contenido).hexdigest()


def enviar_codigo(request, documento_tipo, documento_id, contenido, titulo):
    usuario = request.user
    codigo = f"{secrets.randbelow(10**6):06d}"
    CodigoFirma.objects.filter(usuario=usuario, documento_tipo=documento_tipo, documento_id=documento_id, usado=False).update(usado=True)
    registro = CodigoFirma.objects.create(
        usuario=usuario, documento_tipo=documento_tipo, documento_id=documento_id,
        huella_documento=huella(contenido), codigo_hash=make_password(codigo),
        expira=timezone.now() + VIGENCIA_CODIGO,
    )
    send_mail(
        f"Tu código para firmar: {codigo}",
        f"Hola {usuario.get_short_name()}:\n\nTu código para firmar «{titulo}» es:\n\n    {codigo}\n\n"
        f"Vence en {int(VIGENCIA_CODIGO.total_seconds() // 60)} minutos. Si no estás firmando nada, ignora este correo.",
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
    )
    registrar(request, "enviar_codigo_firma", entidad=documento_tipo, detalle=f"documento {documento_id}")
    return registro


def firmar(request, documento_tipo, documento_id, contenido, titulo, codigo, calidad):
    usuario = request.user
    registro = (
        CodigoFirma.objects.filter(usuario=usuario, documento_tipo=documento_tipo, documento_id=documento_id, usado=False)
        .order_by("-creado").first()
    )
    if registro is None:
        raise ErrorFirma("Pide un código primero.")
    if registro.expira < timezone.now():
        raise ErrorFirma("El código venció. Pide uno nuevo.")
    if registro.intentos >= MAX_INTENTOS:
        raise ErrorFirma("Demasiados intentos. Pide un código nuevo.")
    if registro.huella_documento != huella(contenido):
        raise ErrorFirma("El documento cambió después de pedir el código. Revísalo y pide un código nuevo.")
    if not check_password((codigo or "").strip(), registro.codigo_hash):
        registro.intentos += 1
        registro.save(update_fields=["intentos"])
        raise ErrorFirma("Código incorrecto.")
    registro.usado = True
    registro.save(update_fields=["usado"])
    firma = Firma.objects.create(
        documento_tipo=documento_tipo, documento_id=documento_id, firmante=usuario,
        firmante_nombre=usuario.get_full_name(), firmante_documento=usuario.documento, firmante_email=usuario.email,
        calidad=calidad, huella_documento=registro.huella_documento,
        texto_aceptacion=TEXTO_ACEPTACION.format(titulo=titulo, email=usuario.email),
        ip=ip_de(request), agente=request.META.get("HTTP_USER_AGENT", "")[:300], codigo_ref=registro,
    )
    registrar(request, "firmar", firma, entidad=documento_tipo, detalle=f"documento {documento_id} · {firma.huella_documento}")
    return firma


def firmas_de(documento_tipo, documento_id):
    return Firma.objects.filter(documento_tipo=documento_tipo, documento_id=documento_id).select_related("firmante")
