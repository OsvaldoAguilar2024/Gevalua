from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.clientes.models import Dominio, Empresa
from apps.cuentas.servicios import crear_administrador


class Command(BaseCommand):
    help = "Crea una empresa piloto: esquema propio, subdominio y primer administrador."

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True)
        parser.add_argument("--nit", required=True)
        parser.add_argument("--subdominio", required=True, help=f"queda como <subdominio>.{settings.BASE_DOMAIN}")
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--admin-nombre", default="")
        parser.add_argument("--logo", help="ruta a la imagen del logo")
        parser.add_argument("--dominio-extra", action="append", default=[], help="dominio adicional (p. ej. para pruebas locales)")
        parser.add_argument("--sin-correo", action="store_true", help="no enviar el correo de activación")

    def handle(self, *args, **o):
        sub = o["subdominio"].strip().lower()
        esquema = sub.replace("-", "_")
        if Empresa.objects.filter(schema_name=esquema).exists():
            raise CommandError(f"Ya existe una empresa con el subdominio {sub}")

        empresa = Empresa(schema_name=esquema, nombre=o["nombre"], nit=o["nit"])
        if o["logo"]:
            ruta = Path(o["logo"])
            if not ruta.exists():
                raise CommandError(f"No encuentro el logo en {ruta}")
            with ruta.open("rb") as f:
                empresa.logo.save(ruta.name, File(f), save=False)
        empresa.full_clean(exclude=["logo"])
        with transaction.atomic():
            empresa.save()
            Dominio.objects.create(tenant=empresa, domain=f"{sub}.{settings.BASE_DOMAIN}", is_primary=True)
            for extra in o["dominio_extra"]:
                Dominio.objects.create(tenant=empresa, domain=extra, is_primary=False)

        crear_administrador(empresa, o["admin_email"], o["admin_nombre"], enviar_correo=not o["sin_correo"])
        self.stdout.write(self.style.SUCCESS(f"Empresa {empresa.nombre} lista en https://{sub}.{settings.BASE_DOMAIN}"))
