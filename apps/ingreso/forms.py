from django import forms

from apps.estructura.forms import FECHA
from apps.estructura.models import Cargo, Empleado

from .models import ItemPlantilla, ProcesoIngreso, RequisitoIngreso


class FormularioProceso(forms.ModelForm):
    class Meta:
        model = ProcesoIngreso
        fields = ["candidato_nombre", "candidato_documento", "candidato_email", "candidato_telefono", "cargo", "observaciones"]
        widgets = {"observaciones": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cargo"].queryset = Cargo.objects.filter(activo=True).select_related("area")


class FormularioCargaRequisito(forms.ModelForm):
    class Meta:
        model = RequisitoIngreso
        fields = ["archivo", "fecha_documento", "observacion"]
        widgets = {"fecha_documento": FECHA, "observacion": forms.Textarea(attrs={"rows": 2})}
        labels = {"observacion": "Nota (opcional)"}

    def clean(self):
        datos = super().clean()
        if not datos.get("archivo") and not self.instance.archivo and not datos.get("observacion"):
            raise forms.ValidationError("Adjunta el documento o escribe una nota (por ejemplo, el resultado de la entrevista).")
        if self.instance.vigencia_dias and not datos.get("fecha_documento"):
            self.add_error("fecha_documento", "Este documento vence: indica su fecha de expedición.")
        return datos


class FormularioContratacion(forms.Form):
    email = forms.EmailField(label="Correo de la persona", help_text="Le llega el enlace para crear su contraseña.")
    jefe = forms.ModelChoiceField(queryset=Empleado.objects.none(), required=False, label="Jefe directo")
    fecha_ingreso = forms.DateField(widget=FECHA, label="Fecha de ingreso")
    tipo_contrato = forms.ChoiceField(choices=Empleado.TipoContrato.choices, label="Tipo de contrato")
    fin_contrato = forms.DateField(widget=FECHA, required=False, label="Fin del contrato")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["jefe"].queryset = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario")

    def clean(self):
        datos = super().clean()
        from apps.cuentas.models import Usuario

        if datos.get("email") and Usuario.objects.filter(email=datos["email"].lower()).exists():
            self.add_error("email", "Ya hay una persona con ese correo.")
        if datos.get("tipo_contrato") == Empleado.TipoContrato.FIJO and not datos.get("fin_contrato"):
            self.add_error("fin_contrato", "Un contrato a término fijo necesita fecha de fin.")
        return datos


ItemsPlantillaFormSet = forms.inlineformset_factory(
    parent_model=ItemPlantilla._meta.get_field("plantilla").related_model,
    model=ItemPlantilla,
    fields=["orden", "etapa", "tipo", "nombre", "obligatorio", "vigencia_dias", "fuente_url"],
    extra=2,
    can_delete=True,
)
