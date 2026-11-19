"""Rutas del espacio de cada empresa (cliente.g.oatech.com.co)."""

from django.urls import include, path

from apps.entrenamientos.views import verificar as verificar_certificado
from apps.nucleo import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("cuenta/", include("apps.cuentas.urls")),
    path("estructura/", include("apps.estructura.urls")),
    path("ingreso/", include("apps.ingreso.urls")),
    path("desempeno/", include("apps.desempeno.urls")),
    path("firmar/", include("apps.firmas.urls")),
    path("avisos/", include("apps.notificaciones.urls")),
    path("repositorio/", include("apps.desempeno.urls_repositorio")),
    path("entrenamientos/", include("apps.entrenamientos.urls")),
    path("verificar/<str:codigo>/", verificar_certificado, name="verificar_certificado"),
]
