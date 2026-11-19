import secrets

from django.core.validators import RegexValidator
from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


def ruta_logo(instancia, archivo):
    extension = archivo.rsplit(".", 1)[-1].lower() if "." in archivo else "png"
    return f"public/logos/{secrets.token_hex(12)}.{extension}"


class Empresa(TenantMixin):
    """Una empresa cliente. Cada una tiene su propio esquema de Postgres."""

    class Tamano(models.TextChoices):
        PEQUENA = "pequena", "Pequeña (hasta 49)"
        MEDIANA = "mediana", "Mediana (50 a 100)"
        GRANDE = "grande", "Más de 100"

    class Plan(models.TextChoices):
        PILOTO = "piloto", "Piloto"
        ESTANDAR = "estandar", "Estándar"

    nombre = models.CharField(max_length=200)
    nit = models.CharField(
        "NIT",
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[0-9]{5,15}(-[0-9])?$", "Escribe el NIT con números y dígito de verificación, por ejemplo 900123456-7")],
    )
    logo = models.ImageField(upload_to=ruta_logo, blank=True)
    tamano = models.CharField("tamaño", max_length=20, choices=Tamano.choices, default=Tamano.PEQUENA)
    industria = models.CharField(max_length=120, blank=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.PILOTO)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)

    auto_create_schema = True
    auto_drop_schema = False  # nunca borrar los datos de una empresa por accidente

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def es_publica(self):
        return self.schema_name == "public"


class Dominio(DomainMixin):
    class Meta:
        verbose_name = "dominio"
        verbose_name_plural = "dominios"

    def __str__(self):
        return self.domain
