from django.urls import path

from . import views_evaluacion, views_evidencias, views_metas

urlpatterns = [
    path("plantillas/", views_metas.plantillas, name="plantillas"),
    path("plantillas/<int:pk>/", views_metas.editar_plantilla, name="editar_plantilla"),
    path("periodos/", views_metas.periodos, name="periodos"),
    path("periodos/<int:pk>/", views_metas.periodo, name="periodo"),
    path("equipo/", views_metas.equipo, name="equipo"),
    path("concertacion/<int:pk>/", views_metas.concertacion, name="concertacion"),
    path("meta/<int:pk>/evidencia/", views_evidencias.subir, name="subir_evidencia"),
    path("evidencia/<int:pk>/archivo/", views_evidencias.descargar, name="descargar_evidencia"),
    path("evidencia/<int:pk>/<str:decision>/", views_evidencias.revisar, name="revisar_evidencia"),
    path("evaluacion/<int:pk>/", views_evaluacion.evaluacion, name="evaluacion"),
    path("pdf/<str:tipo>/<int:pk>/", views_evaluacion.pdf, name="pdf_desempeno"),
    path("excel/<str:tipo>/<int:pk>/", views_evaluacion.excel_documento, name="excel_desempeno"),
    path("resultados/", views_evaluacion.resultados, name="resultados"),
]
