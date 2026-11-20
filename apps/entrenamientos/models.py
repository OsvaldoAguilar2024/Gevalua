"""Entrenamientos de cada empresa: asignaciones, avance del video, intentos del examen y certificados internos."""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.cursos.models import Curso
from apps.estructura.models import Empleado
from apps.nucleo.archivos import RutaPrivada


class Asignacion(models.Model):
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name="+")
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="entrenamientos")
    fecha_limite = models.DateField("fecha límite", null=True, blank=True)
    asignada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)
    avance = models.PositiveSmallIntegerField("avance del video (%)", default=0)
    intentos_extra = models.PositiveSmallIntegerField(default=0, help_text="Intentos adicionales que concede talento humano.")

    class Meta:
        verbose_name = "asignación de curso"
        verbose_name_plural = "asignaciones de cursos"
        ordering = ["-creada"]
        constraints = [models.UniqueConstraint(fields=["curso", "empleado"], name="un_curso_por_empleado")]

    def __str__(self):
        return f"{self.curso} · {self.empleado}"

    @property
    def intentos_terminados(self):
        return self.intentos.filter(terminado__isnull=False)

    @property
    def intentos_restantes(self):
        return max(self.curso.max_intentos + self.intentos_extra - self.intentos_terminados.count(), 0)

    @property
    def certificado(self):
        return Certificado.objects.filter(intento__asignacion=self).order_by("-emitido").first()

    @property
    def aprobada(self):
        return self.intentos.filter(aprobado=True).exists()

    @property
    def examen_habilitado(self):
        return self.avance >= self.curso.avance_para_examen and not self.aprobada and self.intentos_restantes > 0

    @property
    def estado(self):
        c = self.certificado
        if c:
            return "vencido" if c.vencido else "aprobado"
        if self.intentos_restantes == 0:
            return "sin_intentos"
        if self.fecha_limite and self.fecha_limite < timezone.localdate():
            return "atrasado"
        return "en_curso" if self.avance or self.intentos.exists() else "pendiente"


ETIQUETAS_ESTADO = {
    "aprobado": ("Aprobado", "verde"), "vencido": ("Certificado vencido", "rojo"), "sin_intentos": ("Sin intentos", "rojo"),
    "atrasado": ("Atrasado", "ambar"), "en_curso": ("En curso", "azul"), "pendiente": ("Pendiente", "ambar"),
}


class Intento(models.Model):
    asignacion = models.ForeignKey(Asignacion, on_delete=models.CASCADE, related_name="intentos")
    preguntas = models.JSONField(default=list, help_text="[{id, opciones: [letras en el orden mostrado]}]")
    respuestas = models.JSONField(default=dict)
    nota = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    aprobado = models.BooleanField(default=False)
    iniciado = models.DateTimeField(auto_now_add=True)
    terminado = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "intento de examen"
        verbose_name_plural = "intentos de examen"
        ordering = ["-iniciado"]


def codigo_verificacion():
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(10))


class Certificado(models.Model):
    """Certificado interno. Guarda los datos tal como se emitieron, para que la verificación no cambie después."""

    intento = models.OneToOneField(Intento, on_delete=models.PROTECT, related_name="certificado")
    codigo = models.CharField("código de verificación", max_length=12, unique=True, default=codigo_verificacion)
    nombre = models.CharField(max_length=200)
    documento = models.CharField(max_length=20, blank=True)
    curso_titulo = models.CharField(max_length=200)
    horas = models.DecimalField(max_digits=5, decimal_places=1)
    nota = models.DecimalField(max_digits=5, decimal_places=2)
    responsable = models.CharField(max_length=300, blank=True, help_text="Nombre de quien firma por la empresa que certifica.")
    responsable_cargo = models.CharField(max_length=150, blank=True)
    responsable_entidad = models.CharField(max_length=150, blank=True)
    responsable_nit = models.CharField(max_length=20, blank=True)
    instructor = models.CharField(max_length=150, blank=True)
    emitido = models.DateTimeField(default=timezone.now)
    vence = models.DateField(null=True, blank=True)
    archivo = models.FileField(upload_to=RutaPrivada("certificados"), blank=True)

    class Meta:
        verbose_name = "certificado"
        verbose_name_plural = "certificados"
        ordering = ["-emitido"]

    def __str__(self):
        return f"{self.curso_titulo} · {self.nombre} · {self.codigo}"

    @property
    def vencido(self):
        return bool(self.vence and self.vence < timezone.localdate())
