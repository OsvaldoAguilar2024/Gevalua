from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from apps.estructura.models import Empleado
from apps.nucleo.archivos import RutaPrivada, validar_soporte

from . import catalogo


class Periodicidad(models.TextChoices):
    SEMANAL = "semanal", "Semanal"
    MENSUAL = "mensual", "Mensual"
    TRIMESTRAL = "trimestral", "Trimestral"
    SEMESTRAL = "semestral", "Semestral"
    ANUAL = "anual", "Anual"


class TipoCriterio(models.TextChoices):
    FUNCIONES = "funciones", "Funciones y metas del cargo"
    COMPORTAMENTAL = "comportamental", "Comportamental"
    OPORTUNIDAD = "oportunidad", "Oportunidades aprovechadas"
    CUMPLIMIENTO = "cumplimiento", "Cumplimiento y disciplina"


class Plantilla(models.Model):
    nombre = models.CharField(max_length=150)
    periodicidad = models.CharField(max_length=20, choices=Periodicidad.choices)
    descripcion = models.TextField(blank=True)
    requiere_autoevaluacion = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "plantilla de evaluación"
        verbose_name_plural = "plantillas de evaluación"
        ordering = ["periodicidad", "nombre"]

    def __str__(self):
        return self.nombre

    @property
    def suma_pesos(self):
        return self.criterios.aggregate(t=Sum("peso"))["t"] or 0

    @classmethod
    def copiar_generica(cls, periodicidad):
        nombre, descripcion, criterios = catalogo.PLANTILLAS[periodicidad]
        plantilla = cls.objects.create(
            nombre=nombre, periodicidad=periodicidad, descripcion=descripcion,
            requiere_autoevaluacion=periodicidad in ("semestral", "anual"),
        )
        for i, (tipo, desc, peso, evidencia) in enumerate(criterios):
            plantilla.criterios.create(orden=i, tipo=tipo, descripcion=desc, peso=peso, evidencia_requerida=evidencia)
        return plantilla


class Criterio(models.Model):
    plantilla = models.ForeignKey(Plantilla, on_delete=models.CASCADE, related_name="criterios")
    orden = models.PositiveIntegerField(default=0)
    tipo = models.CharField(max_length=20, choices=TipoCriterio.choices)
    descripcion = models.CharField("descripción", max_length=300)
    peso = models.PositiveIntegerField("peso %", validators=[MinValueValidator(0), MaxValueValidator(100)])
    evidencia_requerida = models.CharField("evidencia", max_length=300, blank=True)

    class Meta:
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.descripcion


class Periodo(models.Model):
    class Estado(models.TextChoices):
        ABIERTO = "abierto", "Abierto"
        CERRADO = "cerrado", "Cerrado"

    nombre = models.CharField(max_length=120, help_text="Por ejemplo: Diciembre 2026, o Año 2026.")
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, related_name="periodos")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    fecha_limite = models.DateField("fecha límite de evaluación")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTO)

    class Meta:
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return self.nombre

    @property
    def periodicidad(self):
        return self.plantilla.periodicidad


class Concertacion(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "En preparación"
        POR_ACEPTAR = "por_aceptar", "Por aceptar"
        ACEPTADA = "aceptada", "Concertada"
        CERRADA = "cerrada", "Evaluada"

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="concertaciones")
    jefe = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="concertaciones_a_cargo")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="concertaciones")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.BORRADOR)
    aceptada_jefe = models.DateTimeField(null=True, blank=True)
    aceptada_empleado = models.DateTimeField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "concertación"
        verbose_name_plural = "concertaciones"
        ordering = ["-periodo__fecha_inicio", "empleado__usuario__nombre"]
        constraints = [models.UniqueConstraint(fields=["empleado", "periodo"], name="una_concertacion_por_periodo")]

    def __str__(self):
        return f"{self.empleado} · {self.periodo}"

    @property
    def titulo(self):
        return f"Concertación de metas {self.periodo} · {self.empleado}"

    @property
    def suma_pesos(self):
        return self.metas.aggregate(t=Sum("peso"))["t"] or 0

    @property
    def editable(self):
        return self.estado == self.Estado.BORRADOR

    def contenido_firmable(self):
        """Lo que se firma: si cambia algo de esto, la firma deja de corresponder."""
        return {
            "documento": "concertacion",
            "id": self.pk,
            "empleado": {"nombre": self.empleado.usuario.get_full_name(), "documento": self.empleado.usuario.documento},
            "jefe": {"nombre": self.jefe.usuario.get_full_name(), "documento": self.jefe.usuario.documento},
            "periodo": {"nombre": self.periodo.nombre, "inicio": self.periodo.fecha_inicio, "fin": self.periodo.fecha_fin},
            "metas": [
                {"tipo": m.tipo, "descripcion": m.descripcion, "indicador": m.indicador, "objetivo": m.valor_objetivo, "peso": m.peso}
                for m in self.metas.all()
            ],
        }

    def crear_metas_desde_plantilla(self):
        for c in self.periodo.plantilla.criterios.all():
            self.metas.create(
                criterio=c, orden=c.orden, tipo=c.tipo, descripcion=c.descripcion, peso=c.peso, evidencia_requerida=c.evidencia_requerida
            )


class Meta(models.Model):
    concertacion = models.ForeignKey(Concertacion, on_delete=models.CASCADE, related_name="metas")
    criterio = models.ForeignKey(Criterio, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    orden = models.PositiveIntegerField(default=0)
    tipo = models.CharField(max_length=20, choices=TipoCriterio.choices)
    descripcion = models.CharField("meta o actividad", max_length=300)
    indicador = models.CharField(max_length=200, blank=True, help_text="Cómo se mide: ventas, citas agendadas, reportes a tiempo…")
    valor_objetivo = models.CharField("objetivo", max_length=100, blank=True)
    peso = models.PositiveIntegerField("peso %", validators=[MaxValueValidator(100)])
    evidencia_requerida = models.CharField("evidencia esperada", max_length=300, blank=True)

    class Meta:
        verbose_name = "meta"
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.descripcion

    @property
    def es_bono(self):
        return self.tipo == TipoCriterio.OPORTUNIDAD


class Evidencia(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Por revisar"
        APROBADA = "aprobada", "Aprobada"
        DEVUELTA = "devuelta", "Devuelta"

    meta = models.ForeignKey(Meta, on_delete=models.CASCADE, related_name="evidencias")
    archivo = models.FileField(upload_to=RutaPrivada("evidencias"), blank=True, validators=[validar_soporte])
    nombre_archivo = models.CharField(max_length=255, blank=True)
    enlace = models.URLField(blank=True)
    comentario = models.TextField(blank=True)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    comentario_jefe = models.TextField(blank=True)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "evidencia"
        ordering = ["-fecha"]

    def __str__(self):
        return self.nombre_archivo or self.enlace or f"Evidencia {self.pk}"

    @property
    def a_tiempo(self):
        return timezone.localtime(self.fecha).date() <= self.meta.concertacion.periodo.fecha_limite


class Calificacion(models.Model):
    meta = models.OneToOneField(Meta, on_delete=models.CASCADE, related_name="calificacion")
    autoevaluacion = models.PositiveSmallIntegerField(null=True, blank=True, choices=catalogo.OPCIONES_ESCALA)
    nota_jefe = models.PositiveSmallIntegerField(null=True, blank=True, choices=catalogo.OPCIONES_ESCALA)
    comentario = models.TextField(blank=True)
    comentario_empleado = models.TextField(blank=True)


class Evaluacion(models.Model):
    class Recomendacion(models.TextChoices):
        CONTINUIDAD = "continuidad", "Continuidad"
        PLAN_MEJORA = "plan_mejora", "Plan de mejora"
        ASESOR = "asesor", "Revisión con asesor jurídico"

    concertacion = models.OneToOneField(Concertacion, on_delete=models.CASCADE, related_name="evaluacion")
    nota_final = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    nivel = models.CharField(max_length=30, blank=True)
    observaciones = models.TextField(blank=True)
    fortalezas = models.TextField(blank=True)
    aspectos_mejorar = models.TextField("aspectos a mejorar", blank=True)
    plan_siguiente = models.TextField("plan para el siguiente periodo", blank=True)
    recomendacion = models.CharField(max_length=20, choices=Recomendacion.choices, blank=True)
    autoevaluacion_enviada = models.DateTimeField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "evaluación"
        verbose_name_plural = "evaluaciones"

    def __str__(self):
        return f"Evaluación {self.concertacion}"

    @property
    def cerrada(self):
        return self.fecha_cierre is not None

    def calcular(self):
        """Promedio ponderado por pesos. Las oportunidades son un bono: si no hay o restarían, se reescala sin ellas."""
        metas = list(self.concertacion.metas.select_related("calificacion"))
        base = [(m.peso, m.calificacion.nota_jefe) for m in metas if not m.es_bono and hasattr(m, "calificacion") and m.calificacion.nota_jefe]
        bono = [(m.peso, m.calificacion.nota_jefe) for m in metas if m.es_bono and hasattr(m, "calificacion") and m.calificacion.nota_jefe]
        peso_base = sum(p for p, _ in base)
        if not peso_base:
            return None
        sin_bono = Decimal(sum(p * n for p, n in base)) / Decimal(peso_base)
        nota = sin_bono
        if bono:
            con_bono = Decimal(sum(p * n for p, n in base + bono)) / Decimal(peso_base + sum(p for p, _ in bono))
            nota = max(sin_bono, con_bono)
        return min(nota, Decimal(5)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AccionMejora(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CUMPLIDA = "cumplida", "Cumplida"
        INCUMPLIDA = "incumplida", "Incumplida"

    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="acciones")
    meta = models.ForeignKey(Meta, null=True, blank=True, on_delete=models.SET_NULL, related_name="acciones_mejora")
    descripcion = models.TextField("acción de mejora")
    responsable = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="acciones_mejora")
    fecha_compromiso = models.DateField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)

    class Meta:
        verbose_name = "acción de mejora"
        verbose_name_plural = "acciones de mejora"
        ordering = ["fecha_compromiso"]
