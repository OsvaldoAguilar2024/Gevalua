from django import forms
from django.contrib.auth.forms import AuthenticationForm


class FormularioEntrada(AuthenticationForm):
    username = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email", "inputmode": "email"}),
    )
    password = forms.CharField(
        label="Contraseña", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
