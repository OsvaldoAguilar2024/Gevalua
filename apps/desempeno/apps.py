from django.apps import AppConfig


class DesempenoConfig(AppConfig):
    name = "apps.desempeno"
    verbose_name = "Metas, evidencias y evaluación"

    def ready(self):
        from apps.firmas.views import registrar_manejador

        from .views_metas import manejador_concertacion

        registrar_manejador("concertacion", manejador_concertacion)
