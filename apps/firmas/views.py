from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from apps.desempeno.forms import FormularioCodigo

from . import servicios

# tipo de documento -> función que devuelve qué se firma, si se permite y qué pasa después
MANEJADORES = {}


def registrar_manejador(tipo, funcion):
    MANEJADORES[tipo] = funcion


def _manejador(request, tipo, pk):
    if not request.user.is_authenticated or tipo not in MANEJADORES:
        raise Http404
    return MANEJADORES[tipo](request, pk)


def firmar(request, tipo, pk):
    m = _manejador(request, tipo, pk)
    if not m["permitido"]:
        messages.error(request, "Este documento no está listo para tu firma.")
        return redirect(m["volver"])
    form = FormularioCodigo(request.POST or None)
    if request.method == "POST" and request.POST.get("accion") == "enviar_codigo":
        servicios.enviar_codigo(request, tipo, pk, m["contenido"], m["titulo"])
        messages.info(request, f"Te enviamos un código a {request.user.email}. Vence en 10 minutos.")
        return redirect(request.path)
    if request.method == "POST" and request.POST.get("accion") == "firmar" and form.is_valid():
        try:
            servicios.firmar(request, tipo, pk, m["contenido"], m["titulo"], form.cleaned_data["codigo"], m["calidad"])
        except servicios.ErrorFirma as e:
            messages.error(request, str(e))
            return redirect(request.path)
        messages.success(request, m["despues"]())
        return redirect(m["volver"])
    return render(request, "firmas/firmar.html", {
        "m": m, "form": form,
        "texto": servicios.TEXTO_ACEPTACION.format(titulo=m["titulo"], email=request.user.email),
    })
