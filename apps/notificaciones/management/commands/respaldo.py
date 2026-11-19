"""Respaldo nocturno: volcado de Postgres (todas las empresas) y copia de los archivos nuevos a un bucket aparte.

Guarda 30 diarios y 12 mensuales. El volcado se cifra con RESPALDO_CLAVE (Fernet) si está definida.
"""

import gzip
import os
import subprocess
import tempfile

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

DIARIOS, MENSUALES = 30, 12


def cliente(access, secret, endpoint):
    return boto3.client("s3", aws_access_key_id=access, aws_secret_access_key=secret, endpoint_url=endpoint,
                        region_name=getattr(settings, "AWS_S3_REGION_NAME", "auto"))


class Command(BaseCommand):
    help = "Respalda la base de datos y los archivos en el bucket de respaldos."

    def handle(self, *args, **o):
        if not settings.RESPALDO_BUCKET:
            raise CommandError("Falta RESPALDO_BUCKET (y sus credenciales).")
        destino = cliente(settings.RESPALDO_ACCESS_KEY_ID, settings.RESPALDO_SECRET_ACCESS_KEY, settings.RESPALDO_ENDPOINT)
        ahora = timezone.localtime()
        self.respaldar_base(destino, ahora)
        self.podar(destino, ahora)
        if getattr(settings, "AWS_STORAGE_BUCKET_NAME", None):
            self.copiar_archivos(destino)
        self.stdout.write(self.style.SUCCESS("Respaldo terminado."))

    def respaldar_base(self, destino, ahora):
        url = os.environ["DATABASE_URL"]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "base.sql.gz")
            volcado = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", url], check=True, capture_output=True).stdout
            datos = gzip.compress(volcado)
            sufijo = ".sql.gz"
            if settings.RESPALDO_CLAVE:
                from cryptography.fernet import Fernet

                datos = Fernet(settings.RESPALDO_CLAVE.encode()).encrypt(datos)
                sufijo += ".fernet"
            with open(ruta, "wb") as f:
                f.write(datos)
            clave = f"base/diario/{ahora:%Y-%m-%d}{sufijo}"
            destino.upload_file(ruta, settings.RESPALDO_BUCKET, clave)
            if ahora.day == 1:
                destino.upload_file(ruta, settings.RESPALDO_BUCKET, f"base/mensual/{ahora:%Y-%m}{sufijo}")
        self.stdout.write(f"Base respaldada: {clave} ({len(datos) // 1024} KB)")

    def podar(self, destino, ahora):
        for prefijo, conservar in (("base/diario/", DIARIOS), ("base/mensual/", MENSUALES)):
            objetos = destino.list_objects_v2(Bucket=settings.RESPALDO_BUCKET, Prefix=prefijo).get("Contents", [])
            for obj in sorted(objetos, key=lambda x: x["Key"])[:-conservar]:
                destino.delete_object(Bucket=settings.RESPALDO_BUCKET, Key=obj["Key"])

    def copiar_archivos(self, destino):
        origen = cliente(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY, settings.AWS_S3_ENDPOINT_URL)
        existentes = set()
        for pagina in destino.get_paginator("list_objects_v2").paginate(Bucket=settings.RESPALDO_BUCKET, Prefix="archivos/"):
            existentes.update(o["Key"][len("archivos/"):] for o in pagina.get("Contents", []))
        nuevos = 0
        for pagina in origen.get_paginator("list_objects_v2").paginate(Bucket=settings.AWS_STORAGE_BUCKET_NAME):
            for obj in pagina.get("Contents", []):
                if obj["Key"] in existentes:
                    continue
                cuerpo = origen.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=obj["Key"])["Body"].read()
                destino.put_object(Bucket=settings.RESPALDO_BUCKET, Key=f"archivos/{obj['Key']}", Body=cuerpo)
                nuevos += 1
        self.stdout.write(f"Archivos nuevos copiados: {nuevos}")
