from django.http import HttpResponse


class SaludMiddleware:
    """Responde /salud/ antes de resolver la empresa, para el chequeo de Railway."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/salud/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
