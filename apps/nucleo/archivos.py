"""Reglas comunes para los archivos que suben los usuarios (soportes, requisitos, evidencias)."""

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils.deconstruct import deconstructible

EXTENSIONES_PERMITIDAS = {"pdf", "jpg", "jpeg", "png", "webp", "heic", "doc", "docx", "xls", "xlsx"}


@deconstructible
class RutaPrivada:
    """upload_to: empresa_<esquema>/<carpeta>/<nombre aleatorio>.<ext>, para que no se puedan adivinar."""

    def __init__(self, carpeta):
        self.carpeta = carpeta

    def __call__(self, instancia, nombre):
        extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else "bin"
        return f"empresa_{connection.schema_name}/{self.carpeta}/{secrets.token_urlsafe(16)}.{extension}"

    def __eq__(self, otro):
        return isinstance(otro, RutaPrivada) and otro.carpeta == self.carpeta


def validar_soporte(archivo):
    extension = archivo.name.rsplit(".", 1)[-1].lower() if "." in archivo.name else ""
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValidationError("Solo se aceptan PDF, imágenes, Word y Excel.")
    limite = settings.TAMANO_MAXIMO_SOPORTE_MB * 1024 * 1024
    if archivo.size > limite:
        raise ValidationError(f"El archivo supera {settings.TAMANO_MAXIMO_SOPORTE_MB} MB.")
