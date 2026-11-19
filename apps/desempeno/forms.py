from django import forms

from apps.estructura.forms import FECHA

from .models import Concertacion, Criterio, Meta, Periodo, Plantilla


class FormularioPlantilla(forms.ModelForm):
    class Meta:
        model = Plantilla
        fields = ["nombre", "descripcion", "requiere_autoevaluacion", "activa"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}


class FormSetPesos(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        total = sum(
            f.cleaned_data.get("peso") or 0 for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE")
        )
        if total != 100:
            raise forms.ValidationError(f"Los pesos deben sumar 100 %. Ahora suman {total} %.")


CriteriosFormSet = forms.inlineformset_factory(
    Plantilla, Criterio, formset=FormSetPesos,
    fields=["orden", "tipo", "descripcion", "peso", "evidencia_requerida"], extra=1, can_delete=True,
)

MetasFormSet = forms.inlineformset_factory(
    Concertacion, Meta, formset=FormSetPesos,
    fields=["tipo", "descripcion", "indicador", "valor_objetivo", "peso", "evidencia_requerida"], extra=1, can_delete=True,
    widgets={"descripcion": forms.Textarea(attrs={"rows": 2})},
)


class FormularioPeriodo(forms.ModelForm):
    class Meta:
        model = Periodo
        fields = ["plantilla", "nombre", "fecha_inicio", "fecha_fin", "fecha_limite"]
        widgets = {"fecha_inicio": FECHA, "fecha_fin": FECHA, "fecha_limite": FECHA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].queryset = Plantilla.objects.filter(activa=True)

    def clean(self):
        d = super().clean()
        if d.get("fecha_inicio") and d.get("fecha_fin") and d["fecha_fin"] < d["fecha_inicio"]:
            self.add_error("fecha_fin", "Debe ser posterior al inicio.")
        if d.get("fecha_fin") and d.get("fecha_limite") and d["fecha_limite"] < d["fecha_fin"]:
            self.add_error("fecha_limite", "La fecha límite de evaluación va después del fin del periodo.")
        return d


class FormularioCodigo(forms.Form):
    codigo = forms.CharField(label="Código de 6 dígitos", max_length=6, min_length=6,
                             widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "pattern": "[0-9]*"}))
