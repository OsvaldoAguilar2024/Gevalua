from django.apps import AppConfig


class IngresoConfig(AppConfig):
    name = "apps.ingreso"
    verbose_name = "Ingreso y expediente"

    def ready(self):
        from apps.firmas.views import registrar_manejador

        from .firma_contrato import manejador_contrato

        registrar_manejador("contrato", manejador_contrato)
