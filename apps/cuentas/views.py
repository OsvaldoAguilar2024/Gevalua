from django import forms
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from . import seguridad
from .forms import FormularioEntrada


class Entrar(auth_views.LoginView):
    template_name = "registration/entrar.html"
    authentication_form = FormularioEntrada
    redirect_authenticated_user = True


def _siguiente(request, defecto="/"):
    destino = request.POST.get("next") or request.GET.get("next") or defecto
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return defecto
    return destino


class FormularioCodigoEntrada(forms.Form):
    codigo = forms.CharField(
        label="Código de 6 dígitos", max_length=6, min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True, "pattern": "[0-9]*"}),
    )
    recordar = forms.BooleanField(label=f"Recordar este dispositivo {seguridad.DIAS_RECORDAR} días", required=False)


@login_required
def verificar(request):
    """Segundo factor: código de un solo uso enviado al correo."""
    siguiente = _siguiente(request, "/operador/" if seguridad.es_publico(request) else "/")
    if not seguridad.requiere_segundo_factor(request) or seguridad.verificado(request):
        return redirect(siguiente)
    form = FormularioCodigoEntrada(request.POST or None)
    if request.method == "POST" and request.POST.get("accion") == "reenviar":
        if seguridad.enviar_codigo(request, forzar=True):
            messages.info(request, f"Te enviamos un código nuevo a {request.user.email}.")
        else:
            messages.info(request, "Espera un minuto antes de pedir otro código.")
        return redirect(f"{request.path}?next={siguiente}")
    if request.method == "POST" and form.is_valid():
        try:
            seguridad.validar_codigo(request, form.cleaned_data["codigo"])
        except seguridad.ErrorCodigo as e:
            messages.error(request, str(e))
            return redirect(f"{request.path}?next={siguiente}")
        if not seguridad.es_publico(request):
            from apps.nucleo.auditoria import registrar

            registrar(request, "segundo_factor", entidad="sesión", detalle="código por correo")
        respuesta = redirect(siguiente)
        if form.cleaned_data["recordar"]:
            seguridad.recordar_dispositivo(request, respuesta)
        return respuesta
    if request.method == "GET" and seguridad.enviar_codigo(request):
        messages.info(request, f"Te enviamos un código a {request.user.email}. Vence en 10 minutos.")
    return render(request, "registration/segundo_factor.html", {"form": form, "next": siguiente})


@login_required
def datos_personales(request):
    """Autorización de tratamiento de datos personales (Ley 1581 de 2012) al primer ingreso."""
    if seguridad.es_publico(request):
        raise Http404
    from apps.nucleo.auditoria import ip_de, registrar
    from apps.nucleo.models import AutorizacionDatos
    from apps.nucleo.politica import VERSION_POLITICA, texto_autorizacion

    siguiente = _siguiente(request)
    if request.user.acepto_tratamiento_datos:
        return redirect(siguiente)
    texto = texto_autorizacion(request.tenant)
    if request.method == "POST":
        if request.POST.get("acepto") == "si":
            ahora = timezone.now()
            AutorizacionDatos.objects.create(
                usuario=request.user, version=VERSION_POLITICA, texto=texto, ip=ip_de(request),
                agente=request.META.get("HTTP_USER_AGENT", "")[:300],
            )
            request.user.acepto_tratamiento_datos = ahora
            request.user.save(update_fields=["acepto_tratamiento_datos"])
            registrar(request, "autorizar_datos", request.user, detalle=VERSION_POLITICA)
            return redirect(siguiente)
        messages.error(request, "Para usar la plataforma necesitamos tu autorización. Marca la casilla para continuar.")
    return render(request, "registration/datos_personales.html", {"texto": texto, "next": siguiente})
