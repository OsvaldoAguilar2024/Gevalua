"""Firma electrónica propia y local: aceptación expresa del firmante, con huella del documento y evidencias.

Acordado con Gio (noviembre de 2026): la firma queda local y sin código de confirmación por correo.

El texto de aceptación es provisional: Gio lo valida como abogado antes de producción.
"""

import hashlib
import json
from dataclasses import dataclass

from apps.nucleo.auditoria import ip_de, registrar

from .models import Firma

TEXTO_ACEPTACION = (
    "Declaro que leí el documento «{titulo}», que estoy de acuerdo con su contenido y que lo firmo electrónicamente "
    "al marcar esta casilla y pulsar «Firmar» {medio}. Acepto que esta firma tiene la misma validez que mi "
    "firma manuscrita, de acuerdo con la Ley 527 de 1999 y el Decreto 2364 de 2012."
)


def texto_aceptacion(titulo, firmante):
    if firmante.usuario is not None:
        medio = f"desde mi sesión personal ({firmante.email})"
    else:
        medio = f"desde el enlace personal enviado a mi correo {firmante.email}"
    return TEXTO_ACEPTACION.format(titulo=titulo, medio=medio)


class ErrorFirma(Exception):
    pass


@dataclass
class Firmante:
    """Quién firma. `usuario` es None cuando firma alguien sin cuenta (el candidato firma su contrato por enlace)."""

    nombre: str
    email: str
    documento: str = ""
    usuario: object = None

    @classmethod
    def de_usuario(cls, usuario):
        return cls(nombre=usuario.get_full_name(), email=usuario.email, documento=usuario.documento, usuario=usuario)

    @property
    def nombre_corto(self):
        return (self.nombre or self.email).split(" ")[0]

    def filtro(self):
        return {"usuario": self.usuario} if self.usuario is not None else {"usuario__isnull": True, "email": self.email}


def huella(contenido):
    """SHA-256 de una representación canónica del documento (dict o texto)."""
    if not isinstance(contenido, (str, bytes)):
        contenido = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str)
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    return hashlib.sha256(contenido).hexdigest()


def firmar(request, documento_tipo, documento_id, contenido, titulo, calidad, firmante=None, acepto=False, huella_vista=None):
    """Firma local sin código de confirmación: basta la aceptación expresa del firmante en su sesión (o en su enlace).

    `huella_vista` es la huella del documento que el firmante tenía en pantalla; si el documento cambió mientras
    lo leía, no se firma.
    """
    firmante = firmante or Firmante.de_usuario(request.user)
    if not acepto:
        raise ErrorFirma("Marca la casilla de aceptación para firmar.")
    vigente = huella(contenido)
    if huella_vista is not None and huella_vista != vigente:
        raise ErrorFirma("El documento cambió mientras lo leías. Revísalo de nuevo antes de firmar.")
    firma = Firma.objects.create(
        documento_tipo=documento_tipo, documento_id=documento_id, firmante=firmante.usuario,
        firmante_nombre=firmante.nombre, firmante_documento=firmante.documento, firmante_email=firmante.email,
        calidad=calidad, metodo="aceptacion_local", huella_documento=vigente,
        texto_aceptacion=texto_aceptacion(titulo, firmante),
        ip=ip_de(request), agente=request.META.get("HTTP_USER_AGENT", "")[:300],
    )
    registrar(request, "firmar", firma, entidad=documento_tipo,
              detalle=f"documento {documento_id} · {firmante.email} · {firma.huella_documento}")
    return firma


def firmas_de(documento_tipo, documento_id):
    return Firma.objects.filter(documento_tipo=documento_tipo, documento_id=documento_id).select_related("firmante")
