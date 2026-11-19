from django.http import HttpResponse


class SaludMiddleware:
    """Responde /salud/ antes de resolver la empresa, para el chequeo de Railway."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/salud/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)


from django.conf import settings
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_public_schema_name, get_tenant_model


class EmpresaMiddleware(TenantMainMiddleware):
    """Elige el esquema por subdominio. Los dominios públicos (panel del operador y el dominio de Railway)
    van siempre al esquema común, aunque todavía no estén registrados en la tabla de dominios."""

    def get_tenant(self, domain_model, hostname):
        if hostname in settings.PUBLIC_DOMAINS:
            return get_tenant_model().objects.get(schema_name=get_public_schema_name())
        return super().get_tenant(domain_model, hostname)
