#!/bin/sh
# Corre antes de cada despliegue en Railway: migraciones de todas las empresas y espacio común.
set -e
python manage.py migrate_schemas --noinput
python manage.py asegurar_publico
# Empresa Demo: solo si DEMO_CLAVE está definida. No hace nada si ya existe.
# DEMO_REINICIAR=1 borra y vuelve a crear la demo (quitar la variable después).
if [ -n "$DEMO_CLAVE" ]; then
  if [ "$DEMO_REINICIAR" = "1" ]; then OPCION_DEMO="--reiniciar"; else OPCION_DEMO=""; fi
  python manage.py cargar_demo $OPCION_DEMO || echo "Aviso: no se pudo crear la Empresa Demo; el despliegue sigue."
fi
