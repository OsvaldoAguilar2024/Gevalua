from django.urls import path

from . import views_metas

urlpatterns = [
    path("plantillas/", views_metas.plantillas, name="plantillas"),
    path("plantillas/<int:pk>/", views_metas.editar_plantilla, name="editar_plantilla"),
    path("periodos/", views_metas.periodos, name="periodos"),
    path("periodos/<int:pk>/", views_metas.periodo, name="periodo"),
    path("equipo/", views_metas.equipo, name="equipo"),
    path("concertacion/<int:pk>/", views_metas.concertacion, name="concertacion"),
]
