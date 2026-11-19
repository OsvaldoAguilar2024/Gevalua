"""Lo que la vista simple muestra como pendiente para cada persona."""

from django.urls import reverse

from .models import Concertacion, Periodo


def pendientes_de(usuario):
    yo = getattr(usuario, "empleado", None)
    if yo is None:
        return []
    items = []
    abiertas = Concertacion.objects.filter(periodo__estado=Periodo.Estado.ABIERTO).select_related("periodo", "empleado__usuario")
    for c in abiertas.filter(empleado=yo, estado=Concertacion.Estado.POR_ACEPTAR):
        items.append({"texto": f"Aceptar mis metas de {c.periodo}", "url": reverse("concertacion", args=[c.pk])})
    for c in abiertas.filter(jefe=yo, estado=Concertacion.Estado.BORRADOR):
        items.append({"texto": f"Concertar metas con {c.empleado.usuario.get_short_name()} ({c.periodo})", "url": reverse("concertacion", args=[c.pk])})
    return items
