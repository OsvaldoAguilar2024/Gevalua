from django.conf import settings


def empresa(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or tenant.schema_name == "public":
        return {"empresa": None}
    return {"empresa": tenant}


def nombre_app(request):
    return {"nombre_app": settings.NOMBRE_APP}
