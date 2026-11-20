from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

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
    if request.method == "POST" and request.POST.get("accion") == "firmar":
        try:
            servicios.firmar(request, tipo, pk, m["contenido"], m["titulo"], m["calidad"], m.get("firmante"),
                             acepto=bool(request.POST.get("acepto")), huella_vista=request.POST.get("huella"))
        except servicios.ErrorFirma as e:
            messages.error(request, str(e))
            return redirect(request.path)
        messages.success(request, m["despues"]())
        return redirect(m["volver"])
    firmante = m.get("firmante") or servicios.Firmante.de_usuario(request.user)
    return render(request, "firmas/firmar.html", {
        "m": m, "huella": servicios.huella(m["contenido"]),
        "texto": servicios.texto_aceptacion(m["titulo"], firmante),
    })
