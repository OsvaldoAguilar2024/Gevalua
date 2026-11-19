from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListaProcesos.as_view(), name="ingresos"),
    path("nuevo/", views.CrearProceso.as_view(), name="crear_proceso"),
    path("plantilla/", views.plantilla, name="plantilla_requisitos"),
    path("alertas/", views.Alertas.as_view(), name="alertas"),
    path("<int:pk>/", views.detalle, name="proceso"),
    path("<int:pk>/avanzar/", views.avanzar, name="avanzar_proceso"),
    path("<int:pk>/contratar/", views.contratar, name="contratar"),
    path("<int:pk>/descartar/", views.descartar, name="descartar_proceso"),
    path("requisito/<int:pk>/cargar/", views.cargar_requisito, name="cargar_requisito"),
    path("requisito/<int:pk>/enviar-a-firma/", views.enviar_a_firma, name="enviar_a_firma"),
    path("firma/<str:token>/", views.firma_candidato, name="firma_candidato"),
    path("firma/<str:token>/archivo/", views.archivo_candidato, name="archivo_candidato"),
    path("requisito/<int:pk>/archivo/", views.descargar_requisito, name="descargar_requisito"),
    path("requisito/<int:pk>/<str:decision>/", views.verificar_requisito, name="verificar_requisito"),
]
