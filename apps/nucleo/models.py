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
