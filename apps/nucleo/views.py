from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control


def portada_publica(request):
    return render(request, "publico/portada.html")


@login_required
def inicio(request):
    """Vista simple: solo lo pendiente del usuario."""
    from apps.desempeno.pendientes import pendientes_de

    pendientes = pendientes_de(request.user)
    return render(request, "nucleo/inicio.html", {"pendientes": pendientes})


@login_required
def panel(request):
    """Vista completa para talento humano, jefes y consultores."""
    if not request.user.puede_ver_vista_completa:
        raise PermissionDenied
    from .tablero import datos_panel

    return render(request, "nucleo/panel.html", datos_panel(request.user))


@cache_control(max_age=3600)
def manifest(request):
    empresa = request.tenant
    return JsonResponse(
        {
            "name": f"{empresa.nombre} · gevalua",
            "short_name": empresa.nombre[:12],
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#2f59bb",
            "lang": "es-CO",
            "icons": [
                {"src": static("img/icono-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": static("img/icono-512.png"), "sizes": "512x512", "type": "image/png"},
                {"src": static("img/icono-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        },
        content_type="application/manifest+json",
    )


def service_worker(request):
    return render(request, "nucleo/sw.js", content_type="application/javascript")
