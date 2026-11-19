from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.validators import RegexValidator
from django.db import transaction

from apps.cuentas.servicios import crear_administrador

from .models import Dominio, Empresa

validar_subdominio = RegexValidator(
    r"^[a-z][a-z0-9-]{1,40}$", "Solo minúsculas, números y guiones; debe empezar con letra."
)


class FormularioEmpresa(forms.ModelForm):
    subdominio = forms.CharField(
        validators=[validar_subdominio],
        help_text=f"La empresa entrará por <subdominio>.{settings.BASE_DOMAIN}. También es el nombre de su esquema.",
    )
    admin_email = forms.EmailField(label="Correo del primer administrador")
    admin_nombre = forms.CharField(label="Nombre del primer administrador", required=False)

    class Meta:
        model = Empresa
        fields = ["nombre", "nit", "logo", "tamano", "industria", "plan"]

    def clean_subdominio(self):
        sub = self.cleaned_data["subdominio"]
        if sub in {"public", "www", "gevalua", "admin", "operador", "api"}:
            raise forms.ValidationError("Ese subdominio está reservado.")
        if Empresa.objects.filter(schema_name=sub.replace("-", "_")).exists():
            raise forms.ValidationError("Ya existe una empresa con ese subdominio.")
        return sub


class DominioInline(admin.TabularInline):
    model = Dominio
    extra = 0


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "nit", "schema_name", "plan", "activa", "creada"]
    list_filter = ["plan", "activa", "tamano"]
    search_fields = ["nombre", "nit", "schema_name"]
    inlines = [DominioInline]

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(schema_name="public")

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = FormularioEmpresa
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["nombre", "nit", "logo", "tamano", "industria", "plan", "subdominio", "admin_email", "admin_nombre"]
        return ["nombre", "nit", "logo", "tamano", "industria", "plan", "activa", "schema_name"]

    def get_readonly_fields(self, request, obj=None):
        return ["schema_name"] if obj else []

    def get_inlines(self, request, obj):
        return [DominioInline] if obj else []

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        sub = form.cleaned_data["subdominio"]
        obj.schema_name = sub.replace("-", "_")
        with transaction.atomic():
            obj.save()  # crea el esquema y corre las migraciones de la empresa
            Dominio.objects.create(tenant=obj, domain=f"{sub}.{settings.BASE_DOMAIN}", is_primary=True)
        crear_administrador(obj, form.cleaned_data["admin_email"], form.cleaned_data.get("admin_nombre", ""))
        messages.success(
            request,
            f"Empresa creada en https://{sub}.{settings.BASE_DOMAIN}. "
            f"Se envió el enlace de activación a {form.cleaned_data['admin_email']}.",
        )


@admin.register(Dominio)
class DominioAdmin(admin.ModelAdmin):
    list_display = ["domain", "tenant", "is_primary"]
    search_fields = ["domain"]
