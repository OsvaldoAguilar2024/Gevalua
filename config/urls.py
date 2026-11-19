"""Rutas del espacio de cada empresa (cliente.oatech.com.co)."""

from django.urls import include, path

from apps.nucleo import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("cuenta/", include("apps.cuentas.urls")),
    path("estructura/", include("apps.estructura.urls")),
]
