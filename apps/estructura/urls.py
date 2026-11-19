from django.urls import path

from . import views

urlpatterns = [
    path("", views.Estructura.as_view(), name="estructura"),
    path("areas/nueva/", views.CrearArea.as_view(), name="crear_area"),
    path("areas/<int:pk>/", views.EditarArea.as_view(), name="editar_area"),
    path("cargos/nuevo/", views.CrearCargo.as_view(), name="crear_cargo"),
    path("cargos/<int:pk>/", views.EditarCargo.as_view(), name="editar_cargo"),
    path("personas/", views.ListaEmpleados.as_view(), name="empleados"),
    path("personas/nueva/", views.CrearEmpleado.as_view(), name="crear_empleado"),
    path("personas/<int:pk>/", views.EditarEmpleado.as_view(), name="editar_empleado"),
    path("personas/<int:pk>/reenviar/", views.reenviar_activacion, name="reenviar_activacion"),
    path("organigrama/", views.Organigrama.as_view(), name="organigrama"),
]
