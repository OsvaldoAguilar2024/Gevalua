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
        self.mover_al_dominio_base(publico)
        # Primer operador de la plataforma: se crea una sola vez y recibe su enlace por correo.
        email = os.environ.get("OPERADOR_EMAIL", "").strip().lower()
        if email and not Usuario.objects.filter(email=email).exists():
            crear_usuario_y_activar(publico, email, is_staff=True, is_superuser=True)
            self.stdout.write(f"Operador creado: se envió el enlace de activación a {email}")
        self.stdout.write(self.style.SUCCESS("Espacio común listo."))

    def mover_al_dominio_base(self, publico):
        """Si cambia BASE_DOMAIN, cada empresa pasa a <subdominio>.BASE_DOMAIN y se quita el dominio viejo."""
        sufijo = f".{settings.BASE_DOMAIN}"
        for d in Dominio.objects.filter(is_primary=True).exclude(tenant=publico).select_related("tenant"):
            if d.domain.endswith((sufijo, ".localhost")) or d.domain in settings.PUBLIC_DOMAINS:
                continue
            nuevo = f"{d.domain.split('.')[0]}{sufijo}"
            viejo = d.domain
            d.domain = nuevo
            d.save(update_fields=["domain"])
            self.stdout.write(f"Dominio de {d.tenant.nombre}: {viejo} -> {nuevo}")
