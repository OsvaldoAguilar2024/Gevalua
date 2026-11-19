from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.estructura.models import Cargo, Empleado
from apps.nucleo.archivos import RutaPrivada, validar_soporte

from . import catalogo


class Etapa(models.TextChoices):
    SELECCION = "seleccion", "Selección"
    PRECONTRATO = "precontrato", "Precontrato"
    CONTRATO = "contrato", "Contrato"
    POSCONTRATO = "poscontrato", "Poscontrato"


ORDEN_ETAPAS = [e.value for e in Etapa]


class TipoRequisito(models.TextChoices):
    AUTORIZACION = "autorizacion_datos", "Autorización de datos"
    HOJA_VIDA = "hoja_vida", "Hoja de vida"
    ANTECEDENTES = "antecedentes", "Antecedentes"
    ENTREVISTA = "entrevista", "Entrevista"
    EXAMEN = "examen_medico", "Examen médico"
    REFERENCIAS = "referencias", "Referencias"
    CONTRATO = "contrato", "Contrato"
    BANCARIA = "certificacion_bancaria", "Certificación bancaria"
    AFILIACION = "afiliacion", "Afiliación"
    DOTACION = "dotacion", "Equipos y dotación"
    OTRO = "otro", "Otro"


class PlantillaRequisitos(models.Model):
    """Lista de requisitos por etapa. Sin cargo es la lista general de la empresa."""

    nombre = models.CharField(max_length=150)
    cargo = models.OneToOneField(Cargo, null=True, blank=True, on_delete=models.CASCADE, related_name="plantilla_requisitos")

    class Meta:
        verbose_name = "plantilla de requisitos"
        verbose_name_plural = "plantillas de requisitos"

    def __str__(self):
        return self.nombre

    @classmethod
    def general(cls):
        plantilla, creada = cls.objects.get_or_create(cargo=None, defaults={"nombre": "Requisitos generales"})
        if creada:
            for i, (etapa, tipo, nombre, obligatorio, vigencia, fuente) in enumerate(catalogo.REQUISITOS_GENERICOS):
                plantilla.items.create(
                    orden=i, etapa=etapa, tipo=tipo, nombre=nombre, obligatorio=obligatorio,
                    vigencia_dias=vigencia, fuente_url=catalogo.FUENTES[fuente][1] if fuente else "",
                )
        return plantilla

    @classmethod
    def para_cargo(cls, cargo):
        if cargo is not None:
            propia = cls.objects.filter(cargo=cargo).first()
            if propia:
                return propia
        return cls.general()


class ItemPlantilla(models.Model):
    plantilla = models.ForeignKey(PlantillaRequisitos, on_delete=models.CASCADE, related_name="items")
    orden = models.PositiveIntegerField(default=0)
    etapa = models.CharField(max_length=20, choices=Etapa.choices)
    tipo = models.CharField(max_length=30, choices=TipoRequisito.choices, default=TipoRequisito.OTRO)
    nombre = models.CharField(max_length=200)
    obligatorio = models.BooleanField(default=True)
    vigencia_dias = models.PositiveIntegerField(
        "vigencia (días)", null=True, blank=True, help_text="Días que vale el documento desde su fecha. Vacío = no vence."
    )
    fuente_url = models.URLField("página oficial de consulta", blank=True)

    class Meta:
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.nombre


class ProcesoIngreso(models.Model):
    class Estado(models.TextChoices):
        EN_CURSO = "en_curso", "En curso"
        CONTRATADO = "contratado", "Contratado"
        DESCARTADO = "descartado", "Descartado"

    candidato_nombre = models.CharField("nombre del candidato", max_length=200)
    candidato_documento = models.CharField("documento", max_length=20)
    candidato_email = models.EmailField("correo", blank=True)
    candidato_telefono = models.CharField("teléfono", max_length=30, blank=True)
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="procesos_ingreso")
    etapa = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.SELECCION)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.EN_CURSO)
    empleado = models.OneToOneField(Empleado, null=True, blank=True, on_delete=models.SET_NULL, related_name="proceso_ingreso")
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "proceso de ingreso"
        verbose_name_plural = "procesos de ingreso"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.candidato_nombre} · {self.cargo.nombre}"

    def save(self, *args, **kwargs):
        nuevo = self.pk is None
        super().save(*args, **kwargs)
        if nuevo:
            plantilla = PlantillaRequisitos.para_cargo(self.cargo)
            RequisitoIngreso.objects.bulk_create(
                RequisitoIngreso(
                    proceso=self, orden=i.orden, etapa=i.etapa, tipo=i.tipo, nombre=i.nombre,
                    obligatorio=i.obligatorio, vigencia_dias=i.vigencia_dias, fuente_url=i.fuente_url,
                )
                for i in plantilla.items.all()
            )

    def requisitos_de(self, etapa):
        return self.requisitos.filter(etapa=etapa)

    def faltantes(self, etapa=None):
        """Requisitos obligatorios aún no verificados (o vencidos) de la etapa."""
        etapa = etapa or self.etapa
        return [r for r in self.requisitos_de(etapa).filter(obligatorio=True) if not r.cumplido]

    @property
    def autorizacion_verificada(self):
        return self.requisitos.filter(tipo=TipoRequisito.AUTORIZACION, estado=RequisitoIngreso.Estado.VERIFICADO).exists()

    @property
    def siguiente_etapa(self):
        i = ORDEN_ETAPAS.index(self.etapa)
        return ORDEN_ETAPAS[i + 1] if i + 1 < len(ORDEN_ETAPAS) else None

    @property
    def puede_avanzar(self):
        return self.estado == self.Estado.EN_CURSO and self.siguiente_etapa and not self.faltantes()

    @property
    def avance(self):
        total = self.requisitos.filter(obligatorio=True).count()
        if not total:
            return 100
        hechos = sum(1 for r in self.requisitos.filter(obligatorio=True) if r.cumplido)
        return round(hechos * 100 / total)


class RequisitoIngreso(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CARGADO = "cargado", "Por verificar"
        VERIFICADO = "verificado", "Verificado"
        RECHAZADO = "rechazado", "Rechazado"

    proceso = models.ForeignKey(ProcesoIngreso, on_delete=models.CASCADE, related_name="requisitos")
    orden = models.PositiveIntegerField(default=0)
    etapa = models.CharField(max_length=20, choices=Etapa.choices)
    tipo = models.CharField(max_length=30, choices=TipoRequisito.choices)
    nombre = models.CharField(max_length=200)
    obligatorio = models.BooleanField(default=True)
    vigencia_dias = models.PositiveIntegerField(null=True, blank=True)
    fuente_url = models.URLField(blank=True)
    archivo = models.FileField(upload_to=RutaPrivada("ingreso"), blank=True, validators=[validar_soporte])
    nombre_archivo = models.CharField(max_length=255, blank=True)
    fecha_documento = models.DateField("fecha del documento", null=True, blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    observacion = models.TextField(blank=True)
    cargado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cargado_en = models.DateTimeField(null=True, blank=True)
    verificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    verificado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "requisito de ingreso"
        verbose_name_plural = "requisitos de ingreso"
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.nombre

    @property
    def vence(self):
        if self.vigencia_dias and self.fecha_documento:
            return self.fecha_documento + timedelta(days=self.vigencia_dias)
        return None

    @property
    def vencido(self):
        return bool(self.vence and self.vence < timezone.localdate())

    @property
    def cumplido(self):
        return self.estado == self.Estado.VERIFICADO and not self.vencido

    @property
    def es_antecedente(self):
        return self.tipo == TipoRequisito.ANTECEDENTES

    @property
    def es_sensible(self):
        """Hojas de vida, exámenes médicos y antecedentes: solo los ve talento humano."""
        return self.tipo in {TipoRequisito.HOJA_VIDA, TipoRequisito.EXAMEN, TipoRequisito.ANTECEDENTES}
