import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.clientes.models import Dominio, Empresa
from apps.cuentas.models import Usuario
from apps.cuentas.servicios import crear_usuario_y_activar


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
        # Primer operador de la plataforma: se crea una sola vez y recibe su enlace por correo.
        email = os.environ.get("OPERADOR_EMAIL", "").strip().lower()
        if email and not Usuario.objects.filter(email=email).exists():
            crear_usuario_y_activar(publico, email, is_staff=True, is_superuser=True)
            self.stdout.write(f"Operador creado: se envió el enlace de activación a {email}")
        self.stdout.write(self.style.SUCCESS("Espacio común listo."))
