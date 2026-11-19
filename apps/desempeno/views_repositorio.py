"""Repositorio básico de soportes: evidencias y evaluaciones por empleado, área, periodo y tipo, con permisos."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render

from apps.estructura.models import Area, Empleado
from apps.nucleo.auditoria import registrar

from .models import Evaluacion, Evidencia, Periodo
from .permisos import empleado_de


def alcance(usuario):
    """IDs de empleados cuyos soportes puede ver; None = todos."""
    if usuario.es_admin_empresa:
        return None
    yo = empleado_de(usuario)
    if yo is None:
        return []
    return [yo.pk] + [e.pk for e in yo.subordinados()]


def repositorio(request):
    if not request.user.is_authenticated:
        raise Http404
    ids = alcance(request.user)
    f = {k: request.GET.get(k, "").strip() for k in ("tipo", "empleado", "area", "periodo", "estado", "q")}
    tipo = f["tipo"] or "evidencia"
    if tipo == "evaluacion":
        qs = Evaluacion.objects.filter(fecha_cierre__isnull=False).select_related(
            "concertacion__empleado__usuario", "concertacion__empleado__cargo__area", "concertacion__periodo")
        campo = "concertacion__"
    else:
        qs = Evidencia.objects.select_related(
            "meta__concertacion__empleado__usuario", "meta__concertacion__empleado__cargo__area", "meta__concertacion__periodo")
        campo = "meta__concertacion__"
        if f["estado"]:
            qs = qs.filter(estado=f["estado"])
        if f["q"]:
            qs = qs.filter(Q(nombre_archivo__icontains=f["q"]) | Q(comentario__icontains=f["q"]) | Q(meta__descripcion__icontains=f["q"]))
    if ids is not None:
        qs = qs.filter(**{f"{campo}empleado_id__in": ids})
    if f["empleado"]:
        qs = qs.filter(**{f"{campo}empleado_id": f["empleado"]})
    if f["area"]:
        qs = qs.filter(**{f"{campo}empleado__cargo__area_id": f["area"]})
    if f["periodo"]:
        qs = qs.filter(**{f"{campo}periodo_id": f["periodo"]})
    pagina = Paginator(qs.order_by("-pk"), 30).get_page(request.GET.get("pagina"))
    empleados = Empleado.objects.select_related("usuario")
    if ids is not None:
        empleados = empleados.filter(pk__in=ids)
    registrar(request, "consultar_repositorio", entidad="repositorio", detalle=str({k: v for k, v in f.items() if v}))
    return render(request, "desempeno/repositorio.html", {
        "pagina": pagina, "f": f, "tipo": tipo, "empleados": empleados, "areas": Area.objects.all(),
        "periodos": Periodo.objects.all(), "estados": Evidencia.Estado.choices,
    })
