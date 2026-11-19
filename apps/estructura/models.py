from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def sumar_meses(fecha, meses):
    mes = fecha.month - 1 + meses
    anio = fecha.year + mes // 12
    mes = mes % 12 + 1
    dias_mes = [31, 29 if anio % 4 == 0 and (anio % 100 or anio % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(anio, mes, min(fecha.day, dias_mes[mes - 1]))


class Area(models.Model):
    nombre = models.CharField(max_length=150)
    area_padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subareas", verbose_name="área superior"
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "área"
        verbose_name_plural = "áreas"
        ordering = ["nombre"]
        constraints = [models.UniqueConstraint(fields=["nombre", "area_padre"], name="area_unica_por_padre")]

    def __str__(self):
        return f"{self.area_padre} / {self.nombre}" if self.area_padre_id else self.nombre

    def clean(self):
        padre = self.area_padre
        while padre is not None:
            if padre.pk == self.pk:
                raise ValidationError({"area_padre": "Un área no puede depender de sí misma."})
            padre = padre.area_padre


class Cargo(models.Model):
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="cargos", verbose_name="área")
    nombre = models.CharField(max_length=150)
    funciones = models.TextField(blank=True, help_text="Lo que dice el contrato y el manual de funciones.")
    competencias = models.TextField(blank=True, help_text="Conocimientos y competencias comportamentales del cargo.")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        ordering = ["area__nombre", "nombre"]
        constraints = [models.UniqueConstraint(fields=["area", "nombre"], name="cargo_unico_por_area")]

    def __str__(self):
        return f"{self.nombre} ({self.area.nombre})"


class Empleado(models.Model):
    class TipoContrato(models.TextChoices):
        INDEFINIDO = "indefinido", "Término indefinido"
        FIJO = "fijo", "Término fijo"
        OBRA = "obra_labor", "Obra o labor"
        APRENDIZAJE = "aprendizaje", "Aprendizaje"
        PRESTACION = "prestacion", "Prestación de servicios"

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        RETIRADO = "retirado", "Retirado"

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="empleado")
    cargo = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.PROTECT, related_name="empleados")
    jefe = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="equipo", verbose_name="jefe directo"
    )
    fecha_ingreso = models.DateField("fecha de ingreso", null=True, blank=True)
    tipo_contrato = models.CharField("tipo de contrato", max_length=20, choices=TipoContrato.choices, default=TipoContrato.INDEFINIDO)
    fin_periodo_prueba = models.DateField(
        "fin del periodo de prueba", null=True, blank=True,
        help_text="Si lo dejas vacío se calcula: 2 meses, o la quinta parte de un contrato fijo menor a un año.",
    )
    fin_contrato = models.DateField("fin del contrato", null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["usuario__nombre"]

    def __str__(self):
        return str(self.usuario)

    @property
    def area(self):
        return self.cargo.area if self.cargo_id else None

    def clean(self):
        jefe = self.jefe
        while jefe is not None:
            if jefe.pk == self.pk:
                raise ValidationError({"jefe": "Esta asignación crea un ciclo en el organigrama."})
            jefe = jefe.jefe
        if self.tipo_contrato == self.TipoContrato.FIJO and not self.fin_contrato:
            raise ValidationError({"fin_contrato": "Un contrato a término fijo necesita fecha de fin."})
        if self.fin_contrato and self.fecha_ingreso and self.fin_contrato <= self.fecha_ingreso:
            raise ValidationError({"fin_contrato": "El fin del contrato debe ser posterior al ingreso."})

    def periodo_prueba_sugerido(self):
        """Código Sustantivo del Trabajo, art. 78: máximo 2 meses; en contratos fijos de menos de un año,
        no más de la quinta parte del término pactado."""
        if not self.fecha_ingreso or self.tipo_contrato == self.TipoContrato.PRESTACION:
            return None
        fin = sumar_meses(self.fecha_ingreso, 2)
        if self.tipo_contrato == self.TipoContrato.FIJO and self.fin_contrato:
            duracion = (self.fin_contrato - self.fecha_ingreso).days
            if duracion < 365:
                fin = min(fin, self.fecha_ingreso + timedelta(days=duracion // 5))
        return fin - timedelta(days=1)

    def save(self, *args, **kwargs):
        if not self.fin_periodo_prueba:
            self.fin_periodo_prueba = self.periodo_prueba_sugerido()
        super().save(*args, **kwargs)
        if self.jefe_id and not self.jefe.usuario.es_jefe:
            self.jefe.usuario.es_jefe = True
            self.jefe.usuario.save(update_fields=["es_jefe"])

    def subordinados(self, incluir_indirectos=True):
        """Equipo directo y, en cascada, los equipos de los subordinados."""
        resultado, pendientes = [], list(self.equipo.filter(estado=self.Estado.ACTIVO).select_related("usuario", "cargo"))
        vistos = set()
        while pendientes:
            emp = pendientes.pop(0)
            if emp.pk in vistos:
                continue
            vistos.add(emp.pk)
            resultado.append(emp)
            if incluir_indirectos:
                pendientes.extend(emp.equipo.filter(estado=self.Estado.ACTIVO).select_related("usuario", "cargo"))
        return resultado
