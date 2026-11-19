from django.urls import path

from . import views

urlpatterns = [
    path("", views.avisos, name="avisos"),
    path("suscribir/", views.suscribir, name="suscribir_push"),
    path("recordatorios/", views.recordatorios, name="recordatorios"),
    path("recordatorios/<int:pk>/desactivar/", views.desactivar_recordatorio, name="desactivar_recordatorio"),
]
