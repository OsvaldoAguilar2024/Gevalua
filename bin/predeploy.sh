#!/bin/sh
# Corre antes de cada despliegue en Railway: migraciones de todas las empresas y espacio común.
set -e
python manage.py migrate_schemas --noinput
python manage.py asegurar_publico
# Empresa Demo: solo si DEMO_CLAVE está definida. No hace nada si ya existe.
if [ -n "$DEMO_CLAVE" ]; then
  python manage.py cargar_demo || echo "Aviso: no se pudo crear la Empresa Demo; el despliegue sigue."
fi
