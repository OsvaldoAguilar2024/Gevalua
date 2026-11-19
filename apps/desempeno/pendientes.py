"""Lo que la vista simple muestra como pendiente para cada persona."""

from django.urls import reverse

from apps.firmas.models import Firma

from .models import Concertacion, Evaluacion, Evidencia, Periodo


def pendientes_de(usuario):
    yo = getattr(usuario, "empleado", None)
    if yo is None:
        return []
    items = []
    abiertas = Concertacion.objects.filter(periodo__estado=Periodo.Estado.ABIERTO).select_related("periodo", "empleado__usuario")
    for c in abiertas.filter(empleado=yo, estado=Concertacion.Estado.POR_ACEPTAR):
        items.append({"texto": f"Aceptar mis metas de {c.periodo}", "icono": "meta", "color": "teal", "url": reverse("concertacion", args=[c.pk])})
    for c in abiertas.filter(jefe=yo, estado=Concertacion.Estado.BORRADOR):
        items.append({"texto": f"Concertar metas con {c.empleado.usuario.get_short_name()} ({c.periodo})", "icono": "meta", "color": "teal", "url": reverse("concertacion", args=[c.pk])})
    for ev in Evidencia.objects.filter(meta__concertacion__empleado=yo, estado=Evidencia.Estado.DEVUELTA, meta__concertacion__estado=Concertacion.Estado.ACEPTADA).select_related("meta"):
        items.append({"texto": f"Corregir evidencia: {ev.meta.descripcion[:60]}", "icono": "alerta", "color": "ambar", "url": reverse("concertacion", args=[ev.meta.concertacion_id]) + f"#meta-{ev.meta_id}"})
    sin_evidencia = abiertas.filter(empleado=yo, estado=Concertacion.Estado.ACEPTADA, metas__evidencias__isnull=True).exclude(metas__tipo="oportunidad").distinct()
    for c in sin_evidencia:
        items.append({"texto": f"Subir evidencias de {c.periodo}", "icono": "archivo", "color": "azul", "url": reverse("concertacion", args=[c.pk])})
    por_revisar = Evidencia.objects.filter(meta__concertacion__jefe=yo, estado=Evidencia.Estado.PENDIENTE, meta__concertacion__estado=Concertacion.Estado.ACEPTADA)
    n = por_revisar.count()
    if n:
        items.append({"texto": f"Revisar {n} evidencia{'s' if n != 1 else ''} de tu equipo", "icono": "check", "color": "ambar", "url": reverse("equipo")})
    for c in abiertas.filter(empleado=yo, estado=Concertacion.Estado.ACEPTADA, periodo__plantilla__requiere_autoevaluacion=True).filter(
        evaluacion__autoevaluacion_enviada__isnull=True
    ):
        items.append({"texto": f"Hacer mi autoevaluación de {c.periodo}", "icono": "estrella", "color": "verde", "url": reverse("evaluacion", args=[c.pk])})
    firmadas = Firma.objects.filter(documento_tipo="evaluacion", firmante=usuario).values_list("documento_id", flat=True)
    for ev in Evaluacion.objects.filter(concertacion__empleado=yo, fecha_cierre__isnull=False).exclude(concertacion_id__in=firmadas).select_related("concertacion__periodo"):
        items.append({"texto": f"Firmar mi evaluación de {ev.concertacion.periodo}", "icono": "firma", "color": "azul", "url": reverse("evaluacion", args=[ev.concertacion_id])})
    from django.utils import timezone

    for c in abiertas.filter(jefe=yo, estado=Concertacion.Estado.ACEPTADA, periodo__fecha_fin__lte=timezone.localdate()):
        items.append({"texto": f"Evaluar a {c.empleado.usuario.get_short_name()} ({c.periodo})", "icono": "estrella", "color": "verde", "url": reverse("evaluacion", args=[c.pk])})
    from apps.entrenamientos.models import Asignacion

    for a in Asignacion.objects.filter(empleado=yo).select_related("curso"):
        if a.estado in ("pendiente", "en_curso", "atrasado"):
            limite = f" (hasta el {a.fecha_limite:%d/%m/%Y})" if a.fecha_limite else ""
            items.append({"texto": f"Hacer el curso «{a.curso.titulo}»{limite}", "icono": "entrenamientos",
                          "color": "ambar" if a.estado == "atrasado" else "teal", "url": reverse("curso_asignado", args=[a.pk])})
    return items
