"""Módulo 7: entrenamientos grabados, examen y certificado PDF verificable."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cursos.models import Curso
from apps.estructura.forms import FECHA
from apps.estructura.models import Area, Cargo, Empleado
from apps.nucleo import excel
from apps.nucleo.auditoria import registrar

from . import servicios
from .models import ETIQUETAS_ESTADO, Asignacion, Certificado


def solo_admin(request):
    if not (request.user.is_authenticated and request.user.es_admin_empresa):
        raise Http404


def puede_ver(usuario, asig):
    """El empleado, talento humano y sus jefes (en cascada) ven la asignación y el certificado."""
    if usuario.es_admin_empresa or asig.empleado.usuario_id == usuario.pk:
        return True
    yo = getattr(usuario, "empleado", None)
    jefe, vistos = asig.empleado.jefe, set()
    while yo is not None and jefe is not None and jefe.pk not in vistos:
        if jefe.pk == yo.pk:
            return True
        vistos.add(jefe.pk)
        jefe = jefe.jefe
    return False


def con_etiqueta(asignaciones):
    for a in asignaciones:
        a.etiqueta, a.color = ETIQUETAS_ESTADO[a.estado]
    return asignaciones


@login_required
def mis_cursos(request):
    yo = getattr(request.user, "empleado", None)
    asignaciones = con_etiqueta(list(Asignacion.objects.filter(empleado=yo).select_related("curso"))) if yo else []
    return render(request, "entrenamientos/mis_cursos.html", {"asignaciones": asignaciones})


@login_required
def curso(request, pk):
    asig = get_object_or_404(Asignacion.objects.select_related("curso", "empleado__usuario"), pk=pk)
    if not puede_ver(request.user, asig):
        raise Http404
    propio = asig.empleado.usuario_id == request.user.pk
    con_etiqueta([asig])
    return render(request, "entrenamientos/curso.html", {
        "a": asig, "c": asig.curso, "propio": propio, "video": asig.curso.url_video() if propio else "",
        "intentos": asig.intentos_terminados, "certificado": asig.certificado,
    })


@login_required
@require_POST
def avance(request, pk):
    """El reproductor reporta el mayor porcentaje visto. Solo sube, nunca baja."""
    asig = get_object_or_404(Asignacion, pk=pk, empleado__usuario=request.user)
    try:
        pct = max(0, min(100, int(float(request.POST.get("pct", 0)))))
    except ValueError:
        pct = 0
    if pct > asig.avance:
        asig.avance = pct
        asig.save(update_fields=["avance"])
    return JsonResponse({"avance": asig.avance, "examen": asig.examen_habilitado})


@login_required
def examen(request, pk):
    asig = get_object_or_404(Asignacion.objects.select_related("curso"), pk=pk, empleado__usuario=request.user)
    abierto = servicios.intento_abierto(asig)
    if not abierto and not asig.examen_habilitado:
        if asig.aprobada:
            messages.info(request, "Ya aprobaste este curso.")
        elif asig.intentos_restantes == 0:
            messages.error(request, "Usaste todos los intentos. Habla con talento humano.")
        else:
            messages.info(request, f"El examen se habilita al ver el {asig.curso.avance_para_examen} % del video.")
        return redirect("curso_asignado", pk)
    intento = servicios.iniciar_intento(asig)
    if request.method == "POST":
        respuestas = {k[2:]: v for k, v in request.POST.items() if k.startswith("p-")}
        cert = servicios.calificar(request, intento, respuestas)
        if cert:
            messages.success(request, f"¡Aprobaste con {intento.nota:.0f} %! Tu certificado está listo.")
        else:
            restantes = asig.intentos_restantes
            messages.error(request, f"Sacaste {intento.nota:.0f} % y la nota mínima es {asig.curso.nota_minima} %. "
                                    + (f"Te quedan {restantes} intento{'s' if restantes != 1 else ''}." if restantes else "No te quedan intentos."))
        return redirect("curso_asignado", pk)
    return render(request, "entrenamientos/examen.html", {
        "a": asig, "c": asig.curso, "preguntas": servicios.preguntas_de(intento),
        "numero": asig.intentos_terminados.count() + 1,
    })


@login_required
def certificado_pdf(request, codigo):
    cert = get_object_or_404(Certificado.objects.select_related("intento__asignacion__empleado"), codigo=codigo)
    if not puede_ver(request.user, cert.intento.asignacion):
        raise Http404
    registrar(request, "descargar", cert, detalle=cert.codigo)
    if not cert.archivo:
        from django.core.files.base import ContentFile

        cert.archivo.save(f"{cert.codigo}.pdf", ContentFile(servicios.pdf_certificado(request, cert)), save=True)
    return redirect(cert.archivo.url)  # URL firmada que vence en 5 minutos


def verificar(request, codigo):
    """Página pública a la que lleva el QR del certificado."""
    cert = Certificado.objects.filter(codigo=codigo.strip().upper()).first()
    return render(request, "entrenamientos/verificar.html", {"cert": cert, "codigo": codigo, "empresa": request.tenant},
                  status=200 if cert else 404)


# --- Talento humano: catálogo, asignación y seguimiento -----------------------------------------------------

class FormularioAsignar(forms.Form):
    personas = forms.ModelMultipleChoiceField(queryset=Empleado.objects.none(), required=False,
                                              widget=forms.SelectMultiple(attrs={"size": 6}))
    cargos = forms.ModelMultipleChoiceField(queryset=Cargo.objects.none(), required=False,
                                            widget=forms.SelectMultiple(attrs={"size": 4}))
    areas = forms.ModelMultipleChoiceField(label="Áreas", queryset=Area.objects.none(), required=False,
                                           widget=forms.SelectMultiple(attrs={"size": 4}))
    fecha_limite = forms.DateField(label="Fecha límite", required=False, widget=FECHA)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["personas"].queryset = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario")
        self.fields["cargos"].queryset = Cargo.objects.filter(activo=True).select_related("area")
        self.fields["areas"].queryset = Area.objects.all()

    def clean(self):
        d = super().clean()
        if not (d.get("personas") or d.get("cargos") or d.get("areas")):
            raise forms.ValidationError("Elige al menos una persona, un cargo o un área.")
        return d


def catalogo(request):
    solo_admin(request)
    cursos = Curso.objects.filter(publicado=True).annotate(n_preguntas=Count("preguntas"))
    asignados = dict(Asignacion.objects.values("curso_id").annotate(n=Count("pk")).values_list("curso_id", "n"))
    aprobados = dict(Asignacion.objects.filter(intentos__aprobado=True).values("curso_id")
                     .annotate(n=Count("pk", distinct=True)).values_list("curso_id", "n"))
    for c in cursos:
        c.asignados, c.aprobados = asignados.get(c.pk, 0), aprobados.get(c.pk, 0)
    return render(request, "entrenamientos/catalogo.html", {"cursos": cursos})


def asignar(request, pk):
    solo_admin(request)
    curso = get_object_or_404(Curso, pk=pk, publicado=True)
    form = FormularioAsignar(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        empleados = servicios.empleados_para(d["personas"], d["cargos"], d["areas"])
        n = servicios.asignar(request, curso, empleados, d["fecha_limite"])
        messages.success(request, f"Curso asignado a {n} persona{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''}. Les avisamos por correo.")
        return redirect(f"/entrenamientos/seguimiento/?curso={curso.pk}")
    return render(request, "entrenamientos/asignar.html", {"c": curso, "form": form})


def seguimiento(request):
    solo_admin(request)
    qs = Asignacion.objects.select_related("curso", "empleado__usuario", "empleado__cargo__area").prefetch_related("intentos")
    f = {k: request.GET.get(k, "").strip() for k in ("curso", "area", "estado", "q")}
    if f["curso"]:
        qs = qs.filter(curso_id=f["curso"])
    if f["area"]:
        qs = qs.filter(empleado__cargo__area_id=f["area"])
    if f["q"]:
        qs = qs.filter(Q(empleado__usuario__nombre__icontains=f["q"]) | Q(empleado__usuario__email__icontains=f["q"]))
    filas = con_etiqueta(list(qs))
    if f["estado"]:
        filas = [a for a in filas if a.estado == f["estado"]]
    if request.GET.get("formato") == "xlsx":
        registrar(request, "exportar_excel", entidad="entrenamientos", detalle=str({k: v for k, v in f.items() if v}))
        datos = []
        for a in filas:
            cert = a.certificado
            mejor = max((i.nota for i in a.intentos.all() if i.nota is not None), default=None)
            datos.append([a.empleado.usuario.get_full_name(), a.empleado.usuario.documento,
                          a.empleado.cargo.area.nombre if a.empleado.cargo_id else "", a.curso.titulo, a.etiqueta, a.avance,
                          a.intentos_terminados.count(), mejor, a.fecha_limite, cert.codigo if cert else "",
                          cert.emitido if cert else None, cert.vence if cert else None])
        return excel.respuesta("entrenamientos", [("Entrenamientos", [
            "Persona", "Documento", "Área", "Curso", "Estado", "Avance video %", "Intentos", "Mejor nota", "Fecha límite",
            "Certificado", "Emitido", "Vence"], datos)])
    registrar(request, "consultar", entidad="entrenamientos", detalle=str({k: v for k, v in f.items() if v}))
    return render(request, "entrenamientos/seguimiento.html", {
        "filas": filas, "f": f, "cursos": Curso.objects.filter(publicado=True), "areas": Area.objects.all(),
        "estados": [(k, v[0]) for k, v in ETIQUETAS_ESTADO.items()],
    })


@require_POST
def dar_intento(request, pk):
    """Talento humano concede un intento extra a quien agotó los suyos."""
    solo_admin(request)
    asig = get_object_or_404(Asignacion, pk=pk)
    if asig.intentos_restantes == 0 and not asig.aprobada:
        asig.intentos_extra += 1
        asig.save(update_fields=["intentos_extra"])
        registrar(request, "conceder_intento", asig, detalle=f"intentos extra: {asig.intentos_extra}")
        messages.success(request, f"{asig.empleado} tiene un intento más.")
    return redirect("/entrenamientos/seguimiento/")
