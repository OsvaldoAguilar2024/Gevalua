import secrets

from django import forms
from django.db import transaction

from apps.cuentas.models import Usuario

from .models import Area, Cargo, Empleado


class FormularioArea(forms.ModelForm):
    class Meta:
        model = Area
        fields = ["nombre", "area_padre", "activa"]


class FormularioCargo(forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["area", "nombre", "funciones", "competencias", "activo"]
        widgets = {"funciones": forms.Textarea(attrs={"rows": 6}), "competencias": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].queryset = Area.objects.filter(activa=True)


FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class FormularioEmpleado(forms.ModelForm):
    """Crea o edita a la persona (usuario con sus roles) y su ficha de empleado en un solo paso."""

    nombre = forms.CharField(label="Nombre completo", max_length=200)
    email = forms.EmailField(label="Correo")
    documento = forms.CharField(label="Documento de identidad", max_length=20, required=False)
    es_admin_empresa = forms.BooleanField(label="Administrador de la empresa", required=False)
    es_jefe = forms.BooleanField(label="Jefe / evaluador", required=False)
    es_consultor = forms.BooleanField(label="Consultor (solo lectura)", required=False)

    class Meta:
        model = Empleado
        fields = ["cargo", "jefe", "fecha_ingreso", "tipo_contrato", "fin_periodo_prueba", "fin_contrato", "estado"]
        widgets = {"fecha_ingreso": FECHA, "fin_periodo_prueba": FECHA, "fin_contrato": FECHA}

    campos_usuario = ["nombre", "email", "documento", "es_admin_empresa", "es_jefe", "es_consultor"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        orden = self.campos_usuario + list(self.Meta.fields)
        self.order_fields(orden)
        self.fields["cargo"].queryset = Cargo.objects.filter(activo=True).select_related("area")
        jefes = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario")
        if self.instance.pk:
            jefes = jefes.exclude(pk=self.instance.pk)
            for campo in self.campos_usuario:
                self.initial[campo] = getattr(self.instance.usuario, campo)
        self.fields["jefe"].queryset = jefes

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        otros = Usuario.objects.filter(email=email)
        if self.instance.pk:
            otros = otros.exclude(pk=self.instance.usuario_id)
        if otros.exists():
            raise forms.ValidationError("Ya hay una persona con ese correo.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        empleado = super().save(commit=False)
        self.es_nuevo = empleado.pk is None
        if self.es_nuevo:
            usuario = Usuario()
            usuario.set_password(secrets.token_urlsafe(32))  # la persona crea la suya con el enlace
        else:
            usuario = empleado.usuario
        for campo in self.campos_usuario:
            setattr(usuario, campo, self.cleaned_data[campo])
        usuario.save()
        empleado.usuario = usuario
        empleado.save()
        return empleado
