"""Rutas del espacio común (panel del operador de la plataforma)."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.nucleo import views

admin.site.site_header = "gevalua · Operador de la plataforma"
admin.site.site_title = "gevalua"
admin.site.index_title = "Empresas y soporte"

urlpatterns = [
    path("", views.portada_publica, name="portada_publica"),
    path("operador/", admin.site.urls),
    path("inicio/", RedirectView.as_view(url="/operador/"), name="inicio"),
    path("cuenta/", include("apps.cuentas.urls")),
]
