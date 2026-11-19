"""Asignar cursos, armar y calificar el examen, y emitir el certificado PDF con QR de verificación."""

import random
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.estructura.models import Empleado, sumar_meses
from apps.nucleo.auditoria import registrar

from .models import Asignacion, Certificado, Intento


def empleados_para(personas=(), cargos=(), areas=()):
    """Empleados activos que resultan de elegir personas, cargos o áreas."""
    activos = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario")
    ids = {e.pk for e in personas}
    ids |= set(activos.filter(cargo__in=cargos).values_list("pk", flat=True)) if cargos else set()
    ids |= set(activos.filter(cargo__area__in=areas).values_list("pk", flat=True)) if areas else set()
    return list(activos.filter(pk__in=ids))


def asignar(request, curso, empleados, fecha_limite=None):
    """Crea las asignaciones que falten y avisa a cada persona. Devuelve cuántas creó."""
    from apps.notificaciones.servicios import notificar

    nuevas = 0
    for e in empleados:
        asig, creada = Asignacion.objects.get_or_create(
            curso=curso, empleado=e, defaults={"fecha_limite": fecha_limite, "asignada_por": request.user})
        if not creada:
            if fecha_limite and asig.fecha_limite != fecha_limite and not asig.aprobada:
                asig.fecha_limite = fecha_limite
                asig.save(update_fields=["fecha_limite"])
            continue
        nuevas += 1
        limite = f" Tienes hasta el {fecha_limite:%d/%m/%Y}." if fecha_limite else ""
        transaction.on_commit(lambda u=e.usuario, a=asig, lim=limite: notificar(
            u, f"Nuevo entrenamiento: {curso.titulo}",
            f"Te asignaron el curso «{curso.titulo}». Mira el video y presenta el examen.{lim}",
            f"/entrenamientos/{a.pk}/", f"curso_asignado:{a.pk}"))
    registrar(request, "asignar_curso", entidad="curso", detalle=f"{curso.pk} · {curso.titulo} · {nuevas} nuevas")
    return nuevas


def intento_abierto(asig):
    return asig.intentos.filter(terminado__isnull=True).first()


def iniciar_intento(asig):
    """Toma el intento abierto o arma uno nuevo: preguntas al azar y opciones barajadas."""
    abierto = intento_abierto(asig)
    if abierto:
        return abierto
    banco = list(asig.curso.preguntas.all())
    random.shuffle(banco)
    n = asig.curso.preguntas_por_intento
    if n:
        banco = banco[:n]
    preguntas = []
    for p in banco:
        letras = [letra for letra, _ in p.opciones()]
        if p.tipo != p.Tipo.VF:
            random.shuffle(letras)
        preguntas.append({"id": p.pk, "opciones": letras})
    return Intento.objects.create(asignacion=asig, preguntas=preguntas)


def preguntas_de(intento):
    """[(pregunta, [(letra, texto)])] en el orden del intento."""
    from apps.cursos.models import Pregunta

    por_id = {p.pk: p for p in Pregunta.objects.filter(pk__in=[q["id"] for q in intento.preguntas])}
    salida = []
    for q in intento.preguntas:
        p = por_id.get(q["id"])
        if p is None:
            continue
        textos = dict(p.opciones())
        salida.append((p, [(letra, textos[letra]) for letra in q["opciones"] if letra in textos]))
    return salida


def calificar(request, intento, respuestas):
    """respuestas: {id_pregunta (str): letra}. Califica sobre 100 y emite el certificado si aprueba."""
    pares = preguntas_de(intento)
    buenas = sum(1 for p, _ in pares if respuestas.get(str(p.pk)) == p.correcta)
    total = len(pares) or 1
    intento.respuestas = {str(p.pk): respuestas.get(str(p.pk), "") for p, _ in pares}
    intento.nota = (Decimal(buenas * 100) / total).quantize(Decimal("0.01"))
    intento.aprobado = intento.nota >= intento.asignacion.curso.nota_minima
    intento.terminado = timezone.now()
    intento.save()
    registrar(request, "presentar_examen", intento.asignacion, detalle=f"nota {intento.nota} · {'aprobó' if intento.aprobado else 'no aprobó'}")
    if intento.aprobado:
        return emitir_certificado(request, intento)
    return None


def qr_svg(url):
    import segno

    return segno.make(url, error="m").svg_data_uri(scale=4, border=1, dark="#1b2430")


def emitir_certificado(request, intento):
    asig = intento.asignacion
    curso, usuario = asig.curso, asig.empleado.usuario
    ahora = timezone.now()
    cert = Certificado(
        intento=intento, nombre=usuario.get_full_name(), documento=usuario.documento, curso_titulo=curso.titulo,
        horas=curso.horas, nota=intento.nota, emitido=ahora,
        responsable=", ".join(x for x in (curso.responsable_nombre, curso.responsable_cargo) if x),
        vence=sumar_meses(timezone.localdate(ahora), curso.vigencia_meses) if curso.vigencia_meses else None,
    )
    cert.save()
    cert.archivo.save(f"{cert.codigo}.pdf", ContentFile(pdf_certificado(request, cert)), save=True)
    registrar(request, "emitir_certificado", cert, detalle=cert.codigo)
    return cert


def pdf_certificado(request, cert):
    from weasyprint import HTML

    url = request.build_absolute_uri(f"/verificar/{cert.codigo}/")
    html = render_to_string("entrenamientos/certificado_pdf.html", {
        "c": cert, "empresa": request.tenant, "qr": qr_svg(url), "url_verificacion": url,
    })
    return HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
