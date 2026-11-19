from django.conf import settings
from django.core.management.base import BaseCommand

from apps.clientes.models import Dominio, Empresa


class Command(BaseCommand):
    help = "Crea el espacio común (esquema public) y registra sus dominios. Es seguro correrlo en cada despliegue."

    def handle(self, *args, **opciones):
        publico, creado = Empresa.objects.get_or_create(
            schema_name="public",
            defaults={"nombre": "gevalua (operador)", "nit": "000000000-0"},
        )
        if creado:
            self.stdout.write("Espacio común creado.")
        for i, dominio in enumerate(settings.PUBLIC_DOMAINS):
            _, nuevo = Dominio.objects.get_or_create(
                domain=dominio, defaults={"tenant": publico, "is_primary": i == 0}
            )
            if nuevo:
                self.stdout.write(f"Dominio público registrado: {dominio}")
        self.stdout.write(self.style.SUCCESS("Espacio común listo."))
