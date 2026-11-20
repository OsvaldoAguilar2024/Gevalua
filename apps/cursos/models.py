"""Catálogo común de entrenamientos (esquema público).

Gio Consultoría graba cada curso una sola vez y el operador lo carga en /operador/. Todas las empresas ven el mismo
catálogo; cada una guarda en su propio esquema solo sus asignaciones, intentos y certificados.
"""

import secrets

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

EXTENSIONES_VIDEO = {"mp4", "webm", "mov", "m4v"}

# Todos los certificados los firma la gerente de DVQ SAS, junto con el instructor del curso.
FIRMA_NOMBRE = "Diana Paola Varon Quintero"
FIRMA_CARGO = "Gerente"
FIRMA_ENTIDAD = "DVQ SAS"
FIRMA_NIT = "901509777-9"


def ruta_video(instancia, archivo):
    extension = archivo.rsplit(".", 1)[-1].lower() if "." in archivo else "mp4"
    return f"public/cursos/{secrets.token_urlsafe(16)}.{extension}"


def validar_video(archivo):
    extension = archivo.name.rsplit(".", 1)[-1].lower() if "." in archivo.name else ""
    if extension not in EXTENSIONES_VIDEO:
        raise ValidationError("Sube el video en MP4 (recomendado a 720p) o WebM.")


class Curso(models.Model):
    titulo = models.CharField("título", max_length=200)
    descripcion = models.TextField("descripción", blank=True)
    video = models.FileField(upload_to=ruta_video, blank=True, validators=[validar_video],
                             help_text="MP4 a 720p. Se guarda una sola copia en el bucket privado y se reproduce con URL firmada.")
    video_url = models.URLField("o enlace directo al video", blank=True,
                                help_text="Solo si el video está en otro almacenamiento privado. No uses YouTube ni Vimeo no listados.")
    duracion_minutos = models.PositiveIntegerField("duración del video (minutos)", default=0)
    horas = models.DecimalField("horas certificadas", max_digits=5, decimal_places=1, default=1)
    cargos_sugeridos = models.CharField("cargos a los que aplica", max_length=300, blank=True,
                                        help_text="Texto guía para las empresas, por ejemplo: «Todos» o «Conductores, bodega».")
    nota_minima = models.PositiveSmallIntegerField("nota mínima (%)", default=80, validators=[MinValueValidator(1), MaxValueValidator(100)])
    max_intentos = models.PositiveSmallIntegerField("intentos máximos", default=3, validators=[MinValueValidator(1)])
    preguntas_por_intento = models.PositiveSmallIntegerField(
        "preguntas por intento", null=True, blank=True, help_text="Vacío = todas. Si es menor que el banco, cada intento toma unas al azar.")
    vigencia_meses = models.PositiveSmallIntegerField("vigencia (meses)", null=True, blank=True, help_text="Vacío = no vence.")
    avance_para_examen = models.PositiveSmallIntegerField("avance del video para habilitar el examen (%)", default=90,
                                                          validators=[MaxValueValidator(100)])
    instructor = models.CharField("instructor", max_length=150, blank=True,
                                  help_text="Nombre de quien dicta el curso. Aparece en el curso y firma el certificado.")
    responsable_nombre = models.CharField("quien firma el certificado", max_length=150, default=FIRMA_NOMBRE)
    responsable_cargo = models.CharField("cargo de quien firma", max_length=150, blank=True, default=FIRMA_CARGO)
    responsable_entidad = models.CharField("empresa de quien firma", max_length=150, blank=True, default=FIRMA_ENTIDAD)
    responsable_nit = models.CharField("NIT de esa empresa", max_length=20, blank=True, default=FIRMA_NIT)
    publicado = models.BooleanField(default=False, help_text="Solo los cursos publicados aparecen a las empresas.")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["titulo"]

    def __str__(self):
        return self.titulo

    def clean(self):
        if self.publicado and not (self.video or self.video_url):
            raise ValidationError("Para publicar el curso sube el video o pon el enlace.")

    def url_video(self, segundos=4 * 3600):
        """URL firmada del video. Dura lo que dura ver el curso con pausas (por defecto 4 horas)."""
        if self.video:
            try:
                return self.video.storage.url(self.video.name, expire=segundos)
            except TypeError:  # almacenamiento local en desarrollo
                return self.video.url
        return self.video_url


class Pregunta(models.Model):
    class Tipo(models.TextChoices):
        MULTIPLE = "multiple", "Selección múltiple"
        VF = "vf", "Verdadero o falso"

    LETRAS = ["a", "b", "c", "d"]

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="preguntas")
    orden = models.PositiveIntegerField(default=0)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.MULTIPLE)
    enunciado = models.TextField()
    opcion_a = models.CharField("opción A", max_length=300, blank=True)
    opcion_b = models.CharField("opción B", max_length=300, blank=True)
    opcion_c = models.CharField("opción C", max_length=300, blank=True)
    opcion_d = models.CharField("opción D", max_length=300, blank=True)
    correcta = models.CharField(max_length=1, choices=[("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                                help_text="En verdadero o falso: A = Verdadero, B = Falso.")

    class Meta:
        verbose_name = "pregunta"
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.enunciado[:80]

    def opciones(self):
        """[(letra, texto)] de las opciones con texto."""
        if self.tipo == self.Tipo.VF:
            return [("a", "Verdadero"), ("b", "Falso")]
        return [(letra, getattr(self, f"opcion_{letra}")) for letra in self.LETRAS if getattr(self, f"opcion_{letra}")]

    def clean(self):
        if self.tipo == self.Tipo.VF:
            if self.correcta not in ("a", "b"):
                raise ValidationError({"correcta": "En verdadero o falso la respuesta es A (Verdadero) o B (Falso)."})
            return
        letras = [letra for letra, _ in self.opciones()]
        if len(letras) < 2:
            raise ValidationError("Escribe al menos dos opciones.")
        if self.correcta not in letras:
            raise ValidationError({"correcta": "La respuesta correcta debe ser una de las opciones con texto."})
