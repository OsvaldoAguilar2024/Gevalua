"""Indicadores del panel: la empresa entera para administradores y consultores, el equipo para los jefes."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.desempeno import catalogo
from apps.desempeno.models import Concertacion, Evaluacion, Evidencia, Periodo
from apps.estructura.models import Empleado

COLOR_NIVEL = {"Sobresaliente": "verde", "Satisfactorio": "azul", "En mejora": "ambar", "Insatisfactorio": "rojo"}


def datos_panel(usuario):
    from apps.estructura.alcance import ids_como_consultor

    yo = getattr(usuario, "empleado", None)
    activos = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO)
    habilitados = ids_como_consultor(usuario) if usuario.es_consultor and not usuario.es_admin_empresa else set()
    ve_todo = usuario.es_admin_empresa or habilitados is None
    if ve_todo:
        ids = list(activos.values_list("pk", flat=True))
    else:
        ids = list(({e.pk for e in yo.subordinados()} if yo else set()) | habilitados)

    periodo = (
        Periodo.objects.filter(concertaciones__evaluacion__fecha_cierre__isnull=False).distinct().first()
        or Periodo.objects.first()
    )
    conc = Concertacion.objects.filter(empleado_id__in=ids, periodo=periodo) if periodo else Concertacion.objects.none()
    total = conc.count()
    concertadas = conc.filter(estado__in=[Concertacion.Estado.ACEPTADA, Concertacion.Estado.CERRADA]).count()
    evaluadas = conc.filter(estado=Concertacion.Estado.CERRADA).count()

    cerradas = list(
        Evaluacion.objects.filter(concertacion__in=conc, fecha_cierre__isnull=False, nota_final__isnull=False)
        .select_related("concertacion__empleado__usuario", "concertacion__empleado__cargo__area")
    )
    notas = [float(e.nota_final) for e in cerradas]
    promedio = round(sum(notas) / len(notas), 2) if notas else None

    niveles = []
    for _, nombre in catalogo.RESULTADOS:
        n = sum(1 for x in notas if catalogo.nivel_de(x) == nombre)
        niveles.append({"nombre": nombre, "n": n, "pct": round(100 * n / len(notas)) if notas else 0, "color": COLOR_NIVEL[nombre]})

    por_area = {}
    for e in cerradas:
        area = e.concertacion.empleado.area
        por_area.setdefault(area.nombre if area else "Sin área", []).append(float(e.nota_final))
    areas = sorted(
        ({"nombre": k, "nota": round(sum(v) / len(v), 2), "pct": round(sum(v) / len(v) / 5 * 100), "n": len(v)} for k, v in por_area.items()),
        key=lambda a: -a["nota"],
    )

    recientes = (
        Evaluacion.objects.filter(concertacion__empleado_id__in=ids, fecha_cierre__isnull=False)
        .select_related("concertacion__empleado__usuario", "concertacion__empleado__cargo", "concertacion__periodo")
        .order_by("-fecha_cierre")[:6]
    )
    for r in recientes:
        r.color = COLOR_NIVEL.get(r.nivel, "azul")

    hoy = timezone.localdate()
    pronto = hoy + timedelta(days=30)
    alertas = []
    if ve_todo:
        for e in activos.filter(Q(fin_periodo_prueba__range=(hoy, pronto)) | Q(fin_contrato__range=(hoy, pronto))).select_related("usuario"):
            if e.fin_periodo_prueba and hoy <= e.fin_periodo_prueba <= pronto:
                alertas.append({"quien": e.usuario.get_full_name() or e.usuario.email, "que": "Termina periodo de prueba", "fecha": e.fin_periodo_prueba})
            if e.fin_contrato and hoy <= e.fin_contrato <= pronto:
                alertas.append({"quien": e.usuario.get_full_name() or e.usuario.email, "que": "Termina contrato", "fecha": e.fin_contrato})
        alertas.sort(key=lambda a: a["fecha"])

    ingresos = 0
    if usuario.es_admin_empresa:
        from apps.ingreso.models import ProcesoIngreso

        ingresos = ProcesoIngreso.objects.filter(estado=ProcesoIngreso.Estado.EN_CURSO).count()

    return {
        "ve_todo": ve_todo,
        "personas": len(ids),
        "periodo": periodo,
        "total": total,
        "concertadas": concertadas,
        "pct_concertadas": round(100 * concertadas / total) if total else 0,
        "evaluadas": evaluadas,
        "pct_evaluadas": round(100 * evaluadas / total) if total else 0,
        "por_revisar": Evidencia.objects.filter(estado=Evidencia.Estado.PENDIENTE, meta__concertacion__empleado_id__in=ids).count(),
        "promedio": promedio,
        "pct_promedio": round(promedio / 5 * 100) if promedio else 0,
        "nivel_promedio": catalogo.nivel_de(promedio) if promedio else "",
        "niveles": niveles,
        "areas": areas,
        "recientes": recientes,
        "alertas": alertas[:6],
        "ingresos": ingresos,
    }
