"""Módulo 5: autoevaluación, calificación del jefe, acciones de mejora, cierre con firma, PDF y resultados en cascada."""

from decimal import Decimal

from django import forms
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from apps.estructura.forms import FECHA
from apps.estructura.models import Area, Empleado
from apps.firmas.models import Firma
from apps.firmas.servicios import firmas_de
from apps.nucleo.auditoria import registrar

from . import catalogo
from .models import AccionMejora, Calificacion, Concertacion, Evaluacion, Evidencia, Periodo
from .permisos import empleado_de, exigir_rol

PESO_PROPIO_EN_CASCADA = Decimal("0.5")  # el resultado de un jefe: 50 % el suyo, 50 % el promedio de su equipo


class FormularioCierre(forms.ModelForm):
    class Meta:
        model = Evaluacion
        fields = ["fortalezas", "aspectos_mejorar", "plan_siguiente", "recomendacion", "observaciones"]
        widgets = {f: forms.Textarea(attrs={"rows": 2}) for f in ["fortalezas", "aspectos_mejorar", "plan_siguiente", "observaciones"]}


class FormularioAccion(forms.ModelForm):
    class Meta:
        model = AccionMejora
        fields = ["meta", "descripcion", "fecha_compromiso"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2}), "fecha_compromiso": FECHA}

    def __init__(self, *args, concertacion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["meta"].queryset = concertacion.metas.all()
        self.fields["meta"].required = False


def obtener(pk):
    c = get_object_or_404(Concertacion.objects.select_related("empleado__usuario", "empleado__cargo", "jefe__usuario", "periodo__plantilla"), pk=pk)
    evaluacion, _ = Evaluacion.objects.get_or_create(concertacion=c)
    return c, evaluacion


def problemas_para_cerrar(c, ev):
    problemas = []
    metas = list(c.metas.select_related("calificacion").prefetch_related("evidencias", "acciones_mejora"))
    for m in metas:
        cal = getattr(m, "calificacion", None)
        if not m.es_bono and not (cal and cal.nota_jefe):
            problemas.append(f"Falta calificar: {m.descripcion}")
        if cal and cal.nota_jefe and cal.nota_jefe < catalogo.UMBRAL_ACCION_MEJORA and not m.acciones_mejora.exists():
            problemas.append(f"Nota menor a {catalogo.UMBRAL_ACCION_MEJORA}: registra una acción de mejora para «{m.descripcion}»")
    if Evidencia.objects.filter(meta__concertacion=c, estado__in=[Evidencia.Estado.PENDIENTE, Evidencia.Estado.DEVUELTA]).exists():
        problemas.append("Hay evidencias por revisar o devueltas: solo con soportes aprobados se cierra la evaluación.")
    if c.periodo.plantilla.requiere_autoevaluacion and not ev.autoevaluacion_enviada:
        problemas.append("Falta la autoevaluación del empleado.")
    return problemas


def evaluacion(request, pk):
    c, ev = obtener(pk)
    rol = exigir_rol(c, request.user)
    if c.estado not in (Concertacion.Estado.ACEPTADA, Concertacion.Estado.CERRADA):
        messages.info(request, "La evaluación se habilita cuando las metas están concertadas.")
        return redirect("concertacion", pk)
    metas = list(c.metas.select_related("calificacion").prefetch_related("evidencias", "acciones_mejora"))
    for m in metas:
        if not hasattr(m, "calificacion"):
            m.calificacion = Calificacion.objects.create(meta=m)
    abierta = not ev.cerrada
    form_cierre = FormularioCierre(request.POST or None, instance=ev) if rol == "jefe" and abierta else None
    form_accion = FormularioAccion(concertacion=c) if rol == "jefe" and abierta else None

    if request.method == "POST" and abierta:
        accion = request.POST.get("accion")
        if accion == "autoevaluacion" and rol == "empleado" and not ev.autoevaluacion_enviada:
            for m in metas:
                valor = request.POST.get(f"auto-{m.pk}")
                m.calificacion.autoevaluacion = int(valor) if valor in {"1", "2", "3", "4", "5"} else None
                m.calificacion.comentario_empleado = request.POST.get(f"auto-com-{m.pk}", "")[:2000]
                m.calificacion.save()
            if request.POST.get("enviar"):
                ev.autoevaluacion_enviada = timezone.now()
                ev.save(update_fields=["autoevaluacion_enviada"])
                messages.success(request, "Autoevaluación enviada a tu jefe.")
            else:
                messages.success(request, "Autoevaluación guardada. Envíala cuando termines.")
            registrar(request, "autoevaluar", ev)
            return redirect("evaluacion", pk)
        if accion == "calificar" and rol == "jefe":
            for m in metas:
                valor = request.POST.get(f"nota-{m.pk}")
                m.calificacion.nota_jefe = int(valor) if valor in {"1", "2", "3", "4", "5"} else None
                m.calificacion.comentario = request.POST.get(f"com-{m.pk}", "")[:2000]
                m.calificacion.save()
            if form_cierre.is_valid():
                form_cierre.save()
            nota = ev.calcular()
            ev.nota_final, ev.nivel = nota, catalogo.nivel_de(nota) if nota is not None else ""
            ev.save(update_fields=["nota_final", "nivel"])
            registrar(request, "calificar", ev)
            messages.success(request, "Calificación guardada.")
            return redirect("evaluacion", pk)
        if accion == "accion_mejora" and rol == "jefe":
            form_accion = FormularioAccion(request.POST, concertacion=c)
            if form_accion.is_valid():
                a = form_accion.save(commit=False)
                a.evaluacion, a.responsable = ev, c.empleado
                a.save()
                registrar(request, "crear", a)
                return redirect("evaluacion", pk)

    firmas = list(firmas_de(Firma.Documento.EVALUACION, c.pk))
    return render(request, "desempeno/evaluacion.html", {
        "c": c, "ev": ev, "rol": rol, "metas": metas, "escala": catalogo.ESCALA, "abierta": abierta,
        "form_cierre": form_cierre, "form_accion": form_accion, "acciones": ev.acciones.select_related("meta"),
        "problemas": problemas_para_cerrar(c, ev) if rol == "jefe" and abierta else [],
        "nota_previa": ev.calcular(), "firmas": firmas,
        "empleado_firmo": any(f.firmante_id == c.empleado.usuario_id for f in firmas),
        "umbral": catalogo.UMBRAL_ACCION_MEJORA,
    })


def contenido_evaluacion(c, ev):
    nota = ev.calcular()
    return {
        "documento": "evaluacion", "id": c.pk, "periodo": c.periodo.nombre,
        "empleado": {"nombre": c.empleado.usuario.get_full_name(), "documento": c.empleado.usuario.documento},
        "jefe": c.jefe.usuario.get_full_name(),
        "metas": [
            {"descripcion": m.descripcion, "peso": m.peso, "auto": getattr(m, "calificacion", None) and m.calificacion.autoevaluacion,
             "nota": getattr(m, "calificacion", None) and m.calificacion.nota_jefe}
            for m in c.metas.select_related("calificacion")
        ],
        "nota_final": nota, "nivel": catalogo.nivel_de(nota) if nota is not None else "",
        "fortalezas": ev.fortalezas, "aspectos_mejorar": ev.aspectos_mejorar, "plan": ev.plan_siguiente,
        "recomendacion": ev.recomendacion, "observaciones": ev.observaciones,
        "acciones": [{"descripcion": a.descripcion, "fecha": a.fecha_compromiso} for a in ev.acciones.all()],
    }


def manejador_evaluacion(request, pk):
    c, ev = obtener(pk)
    rol = exigir_rol(c, request.user, "jefe", "empleado")
    if rol == "jefe":
        permitido = not ev.cerrada and not problemas_para_cerrar(c, ev)
    else:
        permitido = ev.cerrada and not Firma.objects.filter(documento_tipo="evaluacion", documento_id=c.pk, firmante=request.user).exists()

    def despues():
        if rol == "jefe":
            nota = ev.calcular()
            ev.nota_final, ev.nivel, ev.fecha_cierre = nota, catalogo.nivel_de(nota), timezone.now()
            ev.save(update_fields=["nota_final", "nivel", "fecha_cierre"])
            c.estado = Concertacion.Estado.CERRADA
            c.save(update_fields=["estado"])
            from apps.notificaciones.servicios import notificar

            notificar(c.empleado.usuario, "Tu evaluación está lista", f"Tu jefe cerró tu evaluación de {c.periodo}. Revísala y fírmala.",
                      f"/desempeno/evaluacion/{c.pk}/", f"evaluacion_cerrada:{c.pk}")
            return f"Evaluación cerrada: {ev.nota_final} · {ev.nivel}. {c.empleado.usuario.get_short_name()} la verá para firmar."
        return "Firmaste tu evaluación."

    return {
        "objeto": c, "contenido": contenido_evaluacion(c, ev), "titulo": f"Evaluación {c.periodo} · {c.empleado}",
        "permitido": permitido, "calidad": "Jefe" if rol == "jefe" else "Empleado",
        "volver": f"/desempeno/evaluacion/{c.pk}/", "despues": despues,
    }


def pdf(request, tipo, pk):
    """PDF de la concertación o de la evaluación, con el anexo de firmas."""
    c, ev = obtener(pk)
    exigir_rol(c, request.user)
    if tipo not in ("concertacion", "evaluacion"):
        raise Http404
    from weasyprint import HTML

    html = render_to_string("desempeno/pdf.html", {
        "c": c, "ev": ev, "tipo": tipo, "empresa": request.tenant,
        "metas": c.metas.select_related("calificacion").prefetch_related("evidencias"),
        "firmas": firmas_de(tipo, c.pk), "acciones": ev.acciones.all(), "generado": timezone.now(),
    }, request=request)
    registrar(request, "exportar_pdf", c, detalle=tipo)
    contenido = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    nombre = f"{tipo}-{c.periodo.nombre}-{c.empleado.usuario.get_full_name()}".replace(" ", "_")
    respuesta["Content-Disposition"] = f'inline; filename="{nombre}.pdf"'
    return respuesta


def resultados(request):
    """Resultados por persona, equipo y área. El resultado de un jefe combina el suyo con el de su equipo."""
    u = request.user
    if not u.is_authenticated or not (u.es_admin_empresa or u.es_jefe or u.es_consultor):
        raise Http404
    periodos = Periodo.objects.select_related("plantilla")
    if request.GET.get("periodo"):
        periodo = periodos.filter(pk=request.GET.get("periodo")).first()
    else:  # por defecto, el periodo más reciente que ya tiene evaluaciones cerradas
        periodo = periodos.filter(concertaciones__evaluacion__fecha_cierre__isnull=False).distinct().first() or periodos.first()
    if periodo is None:
        return render(request, "desempeno/resultados.html", {"periodos": periodos})
    notas = {
        ev.concertacion.empleado_id: ev.nota_final
        for ev in Evaluacion.objects.filter(concertacion__periodo=periodo, fecha_cierre__isnull=False).select_related("concertacion")
    }
    activos = list(Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario", "cargo__area"))
    hijos = {}
    for e in activos:
        hijos.setdefault(e.jefe_id, []).append(e)
    memo = {}

    def cascada(e, pila=()):
        if e.pk in memo:
            return memo[e.pk]
        if e.pk in pila:
            return None
        equipo = [x for x in (cascada(h, pila + (e.pk,)) for h in hijos.get(e.pk, [])) if x is not None]
        propia = notas.get(e.pk)
        prom = sum(equipo) / len(equipo) if equipo else None
        if propia is not None and prom is not None:
            r = (propia * PESO_PROPIO_EN_CASCADA + prom * (1 - PESO_PROPIO_EN_CASCADA)).quantize(Decimal("0.01"))
        else:
            r = propia if propia is not None else (prom.quantize(Decimal("0.01")) if prom is not None else None)
        memo[e.pk] = r
        return r

    if u.es_admin_empresa or u.es_consultor:
        visibles = activos
    else:
        yo = empleado_de(u)
        visibles = [yo] + yo.subordinados() if yo else []
    filas = []
    for e in visibles:
        r = cascada(e)
        filas.append({"e": e, "propia": notas.get(e.pk), "cascada": r, "equipo": len(hijos.get(e.pk, [])),
                      "nivel": catalogo.nivel_de(r) if r is not None else ""})
    por_area = {}
    for f in filas:
        if f["propia"] is not None and f["e"].cargo_id:
            por_area.setdefault(f["e"].cargo.area, []).append(f["propia"])
    areas = [{"area": a, "promedio": (sum(v) / len(v)).quantize(Decimal("0.01")), "n": len(v)} for a, v in sorted(por_area.items(), key=lambda x: x[0].nombre)]
    registrar(request, "consultar_resultados", periodo)
    return render(request, "desempeno/resultados.html", {"periodos": periodos, "periodo": periodo, "filas": filas, "areas": areas})
