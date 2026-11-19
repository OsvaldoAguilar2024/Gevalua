"""Recordatorios automáticos que salen de las fechas de cada empresa. Cada uno se envía una sola vez."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Usuario
from apps.desempeno.models import Concertacion, Evaluacion, Periodo
from apps.estructura.models import Empleado

from .servicios import notificar, ya_avisado


def enviar_automaticos():
    hoy = timezone.localdate()
    n = 0
    admins = list(Usuario.objects.filter(es_admin_empresa=True, is_active=True))

    # Fin del periodo de prueba (15 días antes) y fin de contrato (30 días antes): a talento humano y al jefe.
    activos = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario", "jefe__usuario")
    for e in activos.filter(fin_periodo_prueba__gte=hoy, fin_periodo_prueba__lte=hoy + timedelta(days=15)):
        evento = f"auto:prueba:{e.pk}:{e.fin_periodo_prueba}"
        if not ya_avisado(evento):
            for u in {*admins, *( [e.jefe.usuario] if e.jefe else [])}:
                notificar(u, "Fin de periodo de prueba", f"El periodo de prueba de {e} termina el {e.fin_periodo_prueba:%d/%m/%Y}.", reverse("alertas"), evento)
                n += 1
    for e in activos.filter(fin_contrato__gte=hoy, fin_contrato__lte=hoy + timedelta(days=30)):
        evento = f"auto:contrato:{e.pk}:{e.fin_contrato}"
        if not ya_avisado(evento):
            for u in {*admins, *( [e.jefe.usuario] if e.jefe else [])}:
                notificar(u, "Fin de contrato", f"El contrato de {e} termina el {e.fin_contrato:%d/%m/%Y}.", reverse("alertas"), evento)
                n += 1

    abiertas = Concertacion.objects.filter(periodo__estado=Periodo.Estado.ABIERTO).select_related("periodo", "empleado__usuario", "jefe__usuario")
    # Metas por aceptar hace más de 2 días.
    for c in abiertas.filter(estado=Concertacion.Estado.POR_ACEPTAR, aceptada_jefe__lte=timezone.now() - timedelta(days=2)):
        evento = f"auto:aceptar:{c.pk}"
        if not ya_avisado(evento):
            notificar(c.empleado.usuario, "Tienes metas por aceptar", f"Tus metas de {c.periodo} esperan tu firma.", reverse("concertacion", args=[c.pk]), evento)
            n += 1
    # Fin del periodo en 3 días: evidencias pendientes.
    for c in abiertas.filter(estado=Concertacion.Estado.ACEPTADA, periodo__fecha_fin=hoy + timedelta(days=3)):
        evento = f"auto:evidencias:{c.pk}"
        if not ya_avisado(evento):
            notificar(c.empleado.usuario, "Sube tus evidencias", f"El periodo {c.periodo} termina el {c.periodo.fecha_fin:%d/%m/%Y}. Revisa que tus soportes estén cargados.", reverse("concertacion", args=[c.pk]), evento)
            n += 1
    # Evaluación por vencer: a los jefes, 3 días antes de la fecha límite.
    for c in abiertas.filter(estado=Concertacion.Estado.ACEPTADA, periodo__fecha_limite=hoy + timedelta(days=3)):
        evento = f"auto:evaluar:{c.pk}"
        if not ya_avisado(evento):
            notificar(c.jefe.usuario, "Evaluación por vencer", f"La evaluación de {c.empleado} ({c.periodo}) vence el {c.periodo.fecha_limite:%d/%m/%Y}.", reverse("evaluacion", args=[c.pk]), evento)
            n += 1
    # Evaluación cerrada sin firma del empleado (aviso a los 2 días).
    for ev in Evaluacion.objects.filter(fecha_cierre__lte=timezone.now() - timedelta(days=2), concertacion__estado=Concertacion.Estado.CERRADA).select_related("concertacion__empleado__usuario", "concertacion__periodo"):
        evento = f"auto:firmar_eval:{ev.pk}"
        if not ya_avisado(evento):
            from apps.firmas.models import Firma

            if not Firma.objects.filter(documento_tipo="evaluacion", documento_id=ev.concertacion_id, firmante=ev.concertacion.empleado.usuario).exists():
                notificar(ev.concertacion.empleado.usuario, "Firma pendiente", f"Tu evaluación de {ev.concertacion.periodo} espera tu firma.", reverse("evaluacion", args=[ev.concertacion_id]), evento)
                n += 1
    return n
