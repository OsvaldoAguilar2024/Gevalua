def empresa(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or tenant.schema_name == "public":
        return {"empresa": None}
    return {"empresa": tenant}
