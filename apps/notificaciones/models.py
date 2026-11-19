import calendar
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.estructura.models import Area, Empleado


class SuscripcionPush(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suscripciones_push")
    endpoint = models.URLField(max_length=600, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    dispositivo = models.CharField(max_length=300, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)


class Recordatorio(models.Model):
    class Destino(models.TextChoices):
        PERSONA = "persona", "Una persona"
        EQUIPO = "equipo", "Mi equipo directo"
        AREA = "area", "Un área"

    class Repeticion(models.TextChoices):
        UNA_VEZ = "una_vez", "Una sola vez"
        DIARIO = "diario", "Todos los días"
        SEMANAL = "semanal", "Cada semana (mismo día y hora)"
        FIN_DE_MES = "fin_de_mes", "El último día de cada mes"

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recordatorios_creados")
    destino = models.CharField(max_length=10, choices=Destino.choices, default=Destino.EQUIPO)
    persona = models.ForeignKey(Empleado, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    mensaje = models.CharField(max_length=300, help_text="Por ejemplo: subir el reporte semanal el viernes.")
    por_push = models.BooleanField("aviso en el celular", default=True)
    por_correo = models.BooleanField("correo", default=True)
    proximo_envio = models.DateTimeField("fecha y hora de envío")
    repeticion = models.CharField(max_length=12, choices=Repeticion.choices, default=Repeticion.UNA_VEZ)
    activo = models.BooleanField(default=True)
    ultimo_envio = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["proximo_envio"]

    def __str__(self):
        return self.mensaje

    def destinatarios(self):
        """Usuarios a los que llega, calculados en el momento del envío."""
        activos = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario")
        if self.destino == self.Destino.PERSONA and self.persona_id:
            qs = activos.filter(pk=self.persona_id)
        elif self.destino == self.Destino.AREA and self.area_id:
            qs = activos.filter(cargo__area_id=self.area_id)
        else:
            yo = getattr(self.creado_por, "empleado", None)
            qs = activos.filter(jefe=yo) if yo else activos.none()
        return [e.usuario for e in qs if e.usuario.is_active]

    def avanzar(self):
        """Programa el siguiente envío según la repetición (o lo desactiva)."""
        actual = timezone.localtime(self.proximo_envio)
        ahora = timezone.localtime()
        while True:
            if self.repeticion == self.Repeticion.DIARIO:
                actual += timedelta(days=1)
            elif self.repeticion == self.Repeticion.SEMANAL:
                actual += timedelta(days=7)
            elif self.repeticion == self.Repeticion.FIN_DE_MES:
                anio, mes = (actual.year + 1, 1) if actual.month == 12 else (actual.year, actual.month + 1)
                actual = actual.replace(year=anio, month=mes, day=calendar.monthrange(anio, mes)[1])
            else:
                self.activo = False
                return
            if actual > ahora:
                self.proximo_envio = actual
                return


class Notificacion(models.Model):
    class Canal(models.TextChoices):
        PUSH = "push", "Push"
        CORREO = "correo", "Correo"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    recordatorio = models.ForeignKey(Recordatorio, null=True, blank=True, on_delete=models.SET_NULL, related_name="notificaciones")
    evento = models.CharField(max_length=120, db_index=True, help_text="Origen; sirve para no repetir avisos automáticos.")
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    url = models.CharField(max_length=300, blank=True)
    canal = models.CharField(max_length=10, choices=Canal.choices)
    enviada = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    leida = models.DateTimeField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
