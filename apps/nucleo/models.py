from django.conf import settings
from django.db import models


class Auditoria(models.Model):
    """Quién hizo qué y cuándo. Cada consulta y cambio de datos personales queda aquí (Ley 1581)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    accion = models.CharField(max_length=40)
    entidad = models.CharField(max_length=60)
    entidad_id = models.CharField(max_length=40, blank=True)
    detalle = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "auditoría"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.usuario} {self.accion} {self.entidad} {self.entidad_id}"


class AutorizacionDatos(models.Model):
    """Evidencia de la autorización de tratamiento de datos personales (Ley 1581 de 2012): qué texto, cuándo y desde dónde."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="autorizaciones_datos")
    version = models.CharField(max_length=40)
    texto = models.TextField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    agente = models.CharField("navegador", max_length=300, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "autorización de datos personales"
        verbose_name_plural = "autorizaciones de datos personales"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.usuario} autorizó ({self.version}) el {self.fecha:%d/%m/%Y %H:%M}"
