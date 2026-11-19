from django.conf import settings
from django.db import models


class CodigoFirma(models.Model):
    """Código de un solo uso enviado al correo del firmante. Se guarda solo su huella."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    documento_tipo = models.CharField(max_length=30)
    documento_id = models.PositiveBigIntegerField()
    huella_documento = models.CharField(max_length=64)
    codigo_hash = models.CharField(max_length=128)
    creado = models.DateTimeField(auto_now_add=True)
    expira = models.DateTimeField()
    intentos = models.PositiveSmallIntegerField(default=0)
    usado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creado"]


class Firma(models.Model):
    """Firma electrónica propia (Ley 527 de 1999, Decreto 2364 de 2012): código por correo con evidencias."""

    class Documento(models.TextChoices):
        CONCERTACION = "concertacion", "Concertación de metas"
        EVALUACION = "evaluacion", "Evaluación de desempeño"
        CONTRATO = "contrato", "Contrato"
        DOTACION = "dotacion", "Entrega de dotación"

    documento_tipo = models.CharField(max_length=30, choices=Documento.choices)
    documento_id = models.PositiveBigIntegerField()
    firmante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="firmas")
    firmante_nombre = models.CharField(max_length=200)
    firmante_documento = models.CharField(max_length=20, blank=True)
    firmante_email = models.EmailField()
    calidad = models.CharField("firma como", max_length=40)
    metodo = models.CharField(max_length=30, default="codigo_correo")
    huella_documento = models.CharField("hash SHA-256 del documento", max_length=64)
    texto_aceptacion = models.TextField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    agente = models.CharField("navegador", max_length=300, blank=True)
    codigo_ref = models.ForeignKey(CodigoFirma, null=True, on_delete=models.SET_NULL, related_name="+")
    proveedor_ref = models.CharField(max_length=120, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "firma"
        verbose_name_plural = "firmas"
        ordering = ["fecha"]
        indexes = [models.Index(fields=["documento_tipo", "documento_id"])]

    def __str__(self):
        return f"{self.firmante_nombre} firmó {self.get_documento_tipo_display()} {self.documento_id} el {self.fecha:%d/%m/%Y %H:%M}"
