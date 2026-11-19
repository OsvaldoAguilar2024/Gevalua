"""Módulo 4: evidencias por meta y revisión del jefe."""

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from apps.notificaciones.servicios import notificar
from apps.nucleo.auditoria import registrar

from .models import Concertacion, Evidencia, Meta
from .permisos import exigir_rol


class FormularioEvidencia(forms.ModelForm):
    class Meta:
        model = Evidencia
        fields = ["archivo", "enlace", "comentario"]

    def clean(self):
        d = super().clean()
        if not d.get("archivo") and not d.get("enlace") and not d.get("comentario"):
            raise forms.ValidationError("Adjunta una foto o archivo, pega un enlace o escribe un comentario.")
        return d


def subir(request, pk):
    meta = get_object_or_404(Meta.objects.select_related("concertacion__empleado", "concertacion__jefe"), pk=pk)
    c = meta.concertacion
    exigir_rol(c, request.user, "empleado")
    volver = f"/desempeno/concertacion/{c.pk}/#meta-{meta.pk}"
    if request.method != "POST":
        return redirect(volver)
    if c.estado != Concertacion.Estado.ACEPTADA:
        messages.error(request, "Solo se suben evidencias a metas concertadas y sin evaluar.")
        return redirect(volver)
    form = FormularioEvidencia(request.POST, request.FILES)
    if form.is_valid():
        ev = form.save(commit=False)
        ev.meta, ev.subida_por = meta, request.user
        if "archivo" in request.FILES:
            ev.nombre_archivo = request.FILES["archivo"].name[:255]
        ev.save()
        registrar(request, "subir", ev, detalle=ev.nombre_archivo or ev.enlace)
        notificar(c.jefe.usuario, "Nueva evidencia por revisar", f"{c.empleado.usuario.get_short_name()} subió una evidencia: {meta.descripcion[:80]}",
                  f"/desempeno/concertacion/{c.pk}/#meta-{meta.pk}", f"evidencia_subida:{ev.pk}", correo=False)
        messages.success(request, "Evidencia enviada a tu jefe.")
    else:
        for errores in form.errors.values():
            for e in errores:
                messages.error(request, e)
    return redirect(volver)


def revisar(request, pk, decision):
    ev = get_object_or_404(Evidencia.objects.select_related("meta__concertacion__jefe"), pk=pk)
    c = ev.meta.concertacion
    exigir_rol(c, request.user, "jefe")
    if decision not in ("aprobar", "devolver") or request.method != "POST" or c.estado == Concertacion.Estado.CERRADA:
        raise Http404
    comentario = request.POST.get("comentario_jefe", "").strip()[:2000]
    if decision == "devolver" and not comentario:
        messages.error(request, "Para devolver una evidencia escribe qué hay que corregir.")
        return redirect(f"/desempeno/concertacion/{c.pk}/#ev-{ev.pk}")
    ev.estado = Evidencia.Estado.APROBADA if decision == "aprobar" else Evidencia.Estado.DEVUELTA
    ev.comentario_jefe, ev.revisada_por, ev.revisada_en = comentario, request.user, timezone.now()
    ev.save(update_fields=["estado", "comentario_jefe", "revisada_por", "revisada_en"])
    registrar(request, decision, ev)
    if decision == "devolver":
        notificar(c.empleado.usuario, "Evidencia devuelta", f"Tu jefe devolvió una evidencia de «{ev.meta.descripcion[:80]}»: {comentario}",
                  f"/desempeno/concertacion/{c.pk}/#meta-{ev.meta_id}", f"evidencia_devuelta:{ev.pk}")
    return redirect(f"/desempeno/concertacion/{c.pk}/#meta-{ev.meta_id}")


def descargar(request, pk):
    ev = get_object_or_404(Evidencia.objects.select_related("meta__concertacion"), pk=pk)
    exigir_rol(ev.meta.concertacion, request.user)
    if not ev.archivo:
        raise Http404
    registrar(request, "descargar", ev, detalle=ev.nombre_archivo)
    return redirect(ev.archivo.url)
