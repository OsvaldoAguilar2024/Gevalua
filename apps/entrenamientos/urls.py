from django.urls import path

from . import views

urlpatterns = [
    path("", views.mis_cursos, name="mis_cursos"),
    path("catalogo/", views.catalogo, name="catalogo_cursos"),
    path("catalogo/<int:pk>/asignar/", views.asignar, name="asignar_curso"),
    path("seguimiento/", views.seguimiento, name="seguimiento_cursos"),
    path("<int:pk>/", views.curso, name="curso_asignado"),
    path("<int:pk>/avance/", views.avance, name="avance_curso"),
    path("<int:pk>/examen/", views.examen, name="examen_curso"),
    path("<int:pk>/intento-extra/", views.dar_intento, name="intento_extra"),
    path("certificado/<str:codigo>/", views.certificado_pdf, name="certificado_pdf"),
]
