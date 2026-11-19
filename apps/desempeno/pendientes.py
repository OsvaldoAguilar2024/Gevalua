"""Lo que la vista simple muestra como pendiente para cada persona."""

from django.urls import reverse

from .models import Concertacion, Evidencia, Periodo


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
    for ev in Evidencia.objects.filter(meta__concertacion__empleado=yo, estado=Evidencia.Estado.DEVUELTA, meta__concertacion__estado=Concertacion.Estado.ACEPTADA).select_related("meta"):
        items.append({"texto": f"Corregir evidencia: {ev.meta.descripcion[:60]}", "url": reverse("concertacion", args=[ev.meta.concertacion_id]) + f"#meta-{ev.meta_id}"})
    sin_evidencia = abiertas.filter(empleado=yo, estado=Concertacion.Estado.ACEPTADA, metas__evidencias__isnull=True).exclude(metas__tipo="oportunidad").distinct()
    for c in sin_evidencia:
        items.append({"texto": f"Subir evidencias de {c.periodo}", "url": reverse("concertacion", args=[c.pk])})
    por_revisar = Evidencia.objects.filter(meta__concertacion__jefe=yo, estado=Evidencia.Estado.PENDIENTE, meta__concertacion__estado=Concertacion.Estado.ACEPTADA)
    n = por_revisar.count()
    if n:
        items.append({"texto": f"Revisar {n} evidencia{'s' if n != 1 else ''} de tu equipo", "url": reverse("equipo")})
    return items
