from urllib.parse import urlencode

from django.shortcuts import redirect

from . import seguridad


class SeguridadMiddleware:
    """Pide el segundo factor a administradores y operadores, y la autorización de datos al primer ingreso."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not request.path.startswith(seguridad.RUTAS_LIBRES):
            if seguridad.requiere_segundo_factor(request) and not seguridad.verificado(request):
                return redirect(f"/cuenta/verificar/?{urlencode({'next': request.get_full_path()})}")
            if seguridad.requiere_autorizacion_datos(request):
                return redirect(f"/cuenta/datos-personales/?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)
