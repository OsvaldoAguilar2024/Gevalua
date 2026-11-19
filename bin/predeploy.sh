#!/bin/sh
# Corre antes de cada despliegue en Railway: migraciones de todas las empresas y espacio común.
set -e
python manage.py migrate_schemas --noinput
python manage.py asegurar_publico
