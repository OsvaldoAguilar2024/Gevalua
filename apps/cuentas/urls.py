from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    path("entrar/", views.Entrar.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("verificar/", views.verificar, name="segundo_factor"),
    path("datos-personales/", views.datos_personales, name="datos_personales"),
    path(
        "recuperar/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/recuperar.html",
            email_template_name="registration/correo_clave.txt",
            subject_template_name="registration/correo_clave_asunto.txt",
            extra_email_context={"nombre_app": settings.NOMBRE_APP},
            success_url=reverse_lazy("recuperar_enviado"),
        ),
        name="recuperar",
    ),
    path(
        "recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/recuperar_enviado.html"),
        name="recuperar_enviado",
    ),
    path(
        "clave/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/nueva_clave.html",
            success_url=reverse_lazy("clave_lista"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "clave/lista/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/clave_lista.html"),
        name="clave_lista",
    ),
]
