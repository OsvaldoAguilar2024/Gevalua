"""Cuentas de operador de la plataforma en el panel /operador/ (esquema público).

Solo un superusuario las administra. El operador nuevo recibe un enlace para crear su contraseña; nadie se la inventa.
"""

import secrets

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import Permission

from .models import Operador


# Lo que puede hacer un operador que no es superusuario: crear y editar empresas y sus dominios, y cargar cursos.
PERMISOS_OPERADOR = [
    ("clientes", "empresa"), ("clientes", "dominio"), ("cursos", "curso"), ("cursos", "pregunta"),
]


def dar_permisos_operador(usuario):
    permisos = Permission.objects.none()
    for app, modelo in PERMISOS_OPERADOR:
        permisos |= Permission.objects.filter(content_type__app_label=app, content_type__model=modelo,
                                              codename__regex=r"^(add|change|view)_")
    usuario.user_permissions.add(*permisos)


def enviar_activacion_operador(request, usuario):
    """Envía al operador el enlace para crear su contraseña en el dominio del panel."""
    formulario = PasswordResetForm({"email": usuario.email})
    formulario.is_valid()
    formulario.save(
        domain_override=request.get_host(),
        use_https=request.is_secure() or not settings.DEBUG,
        subject_template_name="registration/correo_activacion_asunto.txt",
        email_template_name="registration/correo_activacion.txt",
        extra_email_context={"empresa": request.tenant},
    )


class FormularioOperador(forms.ModelForm):
    class Meta:
        model = Operador
        fields = ["email", "nombre", "is_superuser", "is_active"]
        labels = {"is_superuser": "Puede administrar otros operadores", "is_active": "Activo"}
        help_texts = {
            "is_superuser": "Déjelo sin marcar para un operador que solo crea empresas y carga cursos.",
            "is_active": "Desmárquelo para quitarle el acceso sin borrar la cuenta.",
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    form = FormularioOperador
    list_display = ["email", "nombre", "is_superuser", "is_active", "last_login"]
    list_filter = ["is_active", "is_superuser"]
    search_fields = ["email", "nombre"]
    readonly_fields = ["last_login", "date_joined"]
    actions = ["reenviar_enlace"]

    def get_fields(self, request, obj=None):
        campos = ["email", "nombre", "is_superuser", "is_active"]
        return campos + (["last_login", "date_joined"] if obj else [])

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_staff=True)

    def _solo_superusuario(self, request):
        return request.user.is_active and request.user.is_superuser and getattr(request, "tenant", None) is not None \
            and request.tenant.schema_name == "public"

    def has_module_permission(self, request):
        return self._solo_superusuario(request)

    def has_view_permission(self, request, obj=None):
        return self._solo_superusuario(request)

    def has_add_permission(self, request):
        return self._solo_superusuario(request)

    def has_change_permission(self, request, obj=None):
        return self._solo_superusuario(request)

    def has_delete_permission(self, request, obj=None):
        return False  # se desactiva, no se borra (queda la auditoría)

    def save_model(self, request, obj, form, change):
        if change and obj.pk == request.user.pk and (not obj.is_active or not obj.is_superuser):
            messages.error(request, "No puede quitarse a sí mismo el acceso ni el permiso de administrar operadores.")
            obj.is_active, obj.is_superuser = True, True
        obj.is_staff = True
        if not change:
            obj.set_password(secrets.token_urlsafe(32))  # el operador crea la suya con el enlace
        super().save_model(request, obj, form, change)
        dar_permisos_operador(obj)
        if not change:
            enviar_activacion_operador(request, obj)
            messages.success(request, f"Se envió a {obj.email} el enlace para crear su contraseña. Al entrar se le pedirá el código por correo.")

    @admin.action(description="Reenviar el enlace para crear la contraseña")
    def reenviar_enlace(self, request, queryset):
        for usuario in queryset:
            enviar_activacion_operador(request, usuario)
        messages.success(request, f"Enlace reenviado a {queryset.count()} operador(es).")
