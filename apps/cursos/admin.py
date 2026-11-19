from django.contrib import admin

from .models import Curso, Pregunta


class PreguntaEnLinea(admin.StackedInline):
    model = Pregunta
    extra = 1
    fields = [("orden", "tipo", "correcta"), "enunciado", ("opcion_a", "opcion_b"), ("opcion_c", "opcion_d")]


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ["titulo", "horas", "nota_minima", "max_intentos", "vigencia_meses", "num_preguntas", "publicado"]
    list_filter = ["publicado"]
    search_fields = ["titulo"]
    inlines = [PreguntaEnLinea]
    fieldsets = [
        (None, {"fields": ["titulo", "descripcion", "cargos_sugeridos", "publicado"]}),
        ("Video", {"fields": ["video", "video_url", "duracion_minutos", "avance_para_examen"]}),
        ("Examen y certificado", {"fields": [("nota_minima", "max_intentos", "preguntas_por_intento"), ("horas", "vigencia_meses"),
                                             ("responsable_nombre", "responsable_cargo")]}),
    ]

    @admin.display(description="preguntas")
    def num_preguntas(self, obj):
        return obj.preguntas.count()
