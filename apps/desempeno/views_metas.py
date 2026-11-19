"""Módulo 3: plantillas, periodos y concertación de metas."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.estructura.models import Empleado
from apps.firmas.models import Firma
from apps.firmas.servicios import firmas_de
from apps.nucleo.auditoria import registrar

from .catalogo import PLANTILLAS
from .forms import CriteriosFormSet, FormularioPeriodo, FormularioPlantilla, MetasFormSet
from .models import Concertacion, Periodo, Periodicidad, Plantilla
from .permisos import empleado_de, exigir_rol


def solo_admin(request):
    if not (request.user.is_authenticated and request.user.es_admin_empresa):
        raise Http404


def plantillas(request):
    solo_admin(request)
    if request.method == "POST" and request.POST.get("periodicidad") in PLANTILLAS:
        p = Plantilla.copiar_generica(request.POST["periodicidad"])
        registrar(request, "crear", p)
        messages.success(request, f"Se copió la plantilla genérica «{p.nombre}». Ajústala a tu empresa.")
        return redirect("editar_plantilla", p.pk)
    existentes = set(Plantilla.objects.values_list("periodicidad", flat=True))
    return render(request, "desempeno/plantillas.html", {
        "plantillas": Plantilla.objects.annotate(n=Count("criterios")),
        "genericas": [(k, v[0]) for k, v in PLANTILLAS.items() if k not in existentes],
    })


def editar_plantilla(request, pk):
    solo_admin(request)
    plantilla = get_object_or_404(Plantilla, pk=pk)
    form = FormularioPlantilla(request.POST or None, instance=plantilla)
    formset = CriteriosFormSet(request.POST or None, instance=plantilla)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
        registrar(request, "editar", plantilla)
        messages.success(request, "Plantilla guardada. Aplica a los periodos nuevos.")
        return redirect("plantillas")
    return render(request, "desempeno/plantilla.html", {"form": form, "formset": formset, "plantilla": plantilla})


def periodos(request):
    solo_admin(request)
    form = FormularioPeriodo(request.POST or None)
    if request.method == "POST" and form.is_valid():
        periodo = form.save()
        registrar(request, "crear", periodo)
        messages.success(request, f"Periodo «{periodo}» creado. Ahora genera las concertaciones.")
        return redirect("periodo", periodo.pk)
    lista = Periodo.objects.select_related("plantilla").annotate(
        n=Count("concertaciones"),
        n_aceptadas=Count("concertaciones", filter=Q(concertaciones__estado__in=["aceptada", "cerrada"])),
        n_cerradas=Count("concertaciones", filter=Q(concertaciones__estado="cerrada")),
    )
    return render(request, "desempeno/periodos.html", {"periodos": lista, "form": form, "hay_plantillas": Plantilla.objects.filter(activa=True).exists()})


def periodo(request, pk):
    solo_admin(request)
    periodo = get_object_or_404(Periodo.objects.select_related("plantilla"), pk=pk)
    if request.method == "POST" and request.POST.get("accion") == "generar":
        con_jefe = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO, jefe__isnull=False).exclude(concertaciones__periodo=periodo)
        n = 0
        with transaction.atomic():
            for emp in con_jefe.select_related("jefe"):
                c = Concertacion.objects.create(empleado=emp, jefe=emp.jefe, periodo=periodo)
                c.crear_metas_desde_plantilla()
                n += 1
        registrar(request, "generar_concertaciones", periodo, detalle=str(n))
        messages.success(request, f"Se generaron {n} concertaciones. Cada jefe ya puede ajustar las metas de su equipo.")
        return redirect("periodo", pk)
    if request.method == "POST" and request.POST.get("accion") == "cerrar":
        periodo.estado = Periodo.Estado.CERRADO
        periodo.save(update_fields=["estado"])
        registrar(request, "cerrar", periodo)
        return redirect("periodo", pk)
    sin_jefe = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO, jefe__isnull=True).select_related("usuario")
    concertaciones = periodo.concertaciones.select_related("empleado__usuario", "jefe__usuario", "empleado__cargo")
    return render(request, "desempeno/periodo.html", {"periodo": periodo, "concertaciones": concertaciones, "sin_jefe": sin_jefe})


def equipo(request):
    """Concertaciones del equipo del jefe (directo y en cascada)."""
    yo = empleado_de(request.user)
    if not request.user.is_authenticated or not (request.user.es_jefe or request.user.es_admin_empresa) or yo is None:
        raise Http404
    ids = [e.pk for e in yo.subordinados()]
    qs = (
        Concertacion.objects.filter(empleado_id__in=ids, periodo__estado=Periodo.Estado.ABIERTO)
        .select_related("empleado__usuario", "empleado__cargo", "jefe__usuario", "periodo")
        .annotate(n_pendientes=Count("metas__evidencias", filter=Q(metas__evidencias__estado="pendiente")))
    )
    return render(request, "desempeno/equipo.html", {"directas": [c for c in qs if c.jefe_id == yo.pk], "cascada": [c for c in qs if c.jefe_id != yo.pk]})


def concertacion(request, pk):
    c = get_object_or_404(Concertacion.objects.select_related("empleado__usuario", "jefe__usuario", "periodo__plantilla"), pk=pk)
    rol = exigir_rol(c, request.user)
    formset = None
    if rol == "jefe" and c.editable:
        formset = MetasFormSet(request.POST or None, instance=c, prefix="metas")
        if request.method == "POST" and request.POST.get("accion") == "guardar":
            if formset.is_valid():
                formset.save()
                registrar(request, "editar", c)
                messages.success(request, "Metas guardadas.")
                return redirect("concertacion", pk)
    if request.method == "POST" and request.POST.get("accion") == "devolver" and rol == "jefe" and c.estado == Concertacion.Estado.POR_ACEPTAR:
        c.estado, c.aceptada_jefe = Concertacion.Estado.BORRADOR, None
        c.save(update_fields=["estado", "aceptada_jefe"])
        registrar(request, "reabrir", c)
        messages.info(request, "La concertación volvió a preparación. Tu firma anterior ya no aplica: firma de nuevo al enviar.")
        return redirect("concertacion", pk)
    if rol != "empleado":
        registrar(request, "consultar", c)
    return render(request, "desempeno/concertacion.html", {
        "c": c, "rol": rol, "formset": formset, "metas": c.metas.prefetch_related("evidencias"),
        "firmas": firmas_de(Firma.Documento.CONCERTACION, c.pk),
        "puede_firmar": (rol == "jefe" and c.estado == Concertacion.Estado.BORRADOR and c.suma_pesos == 100)
        or (rol == "empleado" and c.estado == Concertacion.Estado.POR_ACEPTAR),
    })


def al_firmar_concertacion(request, c, rol):
    ahora = timezone.now()
    if rol == "jefe":
        c.estado, c.aceptada_jefe = Concertacion.Estado.POR_ACEPTAR, ahora
        mensaje = f"Firmaste y enviaste las metas a {c.empleado}. Le llegará el aviso para aceptarlas."
        from apps.notificaciones.servicios import notificar

        notificar(c.empleado.usuario, "Tienes metas por aceptar", f"{c.jefe.usuario.get_short_name()} te envió tus metas de {c.periodo}. Revísalas y fírmalas.",
                  f"/desempeno/concertacion/{c.pk}/", f"metas_enviadas:{c.pk}")
    else:
        c.estado, c.aceptada_empleado = Concertacion.Estado.ACEPTADA, ahora
        mensaje = "Firmaste tus metas. Ya puedes subir evidencias."
    c.save(update_fields=["estado", "aceptada_jefe", "aceptada_empleado"])
    return mensaje


def manejador_concertacion(request, pk):
    """Para el módulo de firmas: qué se firma, quién puede y qué pasa después."""
    c = get_object_or_404(Concertacion.objects.select_related("empleado__usuario", "jefe__usuario", "periodo"), pk=pk)
    rol = exigir_rol(c, request.user, "jefe", "empleado")
    permitido = (rol == "jefe" and c.estado == Concertacion.Estado.BORRADOR and c.suma_pesos == 100) or (
        rol == "empleado" and c.estado == Concertacion.Estado.POR_ACEPTAR
    )
    return {
        "objeto": c, "contenido": c.contenido_firmable(), "titulo": c.titulo, "permitido": permitido,
        "calidad": "Jefe" if rol == "jefe" else "Empleado", "volver": f"/desempeno/concertacion/{c.pk}/",
        "despues": lambda: al_firmar_concertacion(request, c, rol),
    }
