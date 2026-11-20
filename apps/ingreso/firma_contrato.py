"""Firma electrónica del contrato dentro del ingreso.

Usa el mismo mecanismo que concertaciones y evaluaciones (aceptación expresa sin código de confirmación,
huella SHA-256 y evidencias). Firman dos personas:

- El candidato, que todavía no tiene cuenta: recibe un enlace en su correo, abre el contrato y lo firma ahí.
- El empleador: un administrador de la empresa firma desde el proceso con su propia cuenta.

Cuando las dos firmas corresponden al archivo vigente, el requisito queda verificado solo.
"""

import hashlib
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.firmas.models import Firma
from apps.firmas.servicios import Firmante, firmas_de, huella
from apps.nucleo.auditoria import registrar

from .models import EnvioFirmaContrato, ProcesoIngreso, RequisitoIngreso

TIPO = Firma.Documento.CONTRATO
CALIDAD_CANDIDATO = "Trabajador"
CALIDAD_EMPLEADOR = "Empleador"


def huella_archivo(archivo):
    sha = hashlib.sha256()
    with archivo.open("rb") as f:
        for bloque in iter(lambda: f.read(64 * 1024), b""):
            sha.update(bloque)
    return sha.hexdigest()


def asegurar_huella(req):
    if req.archivo and not req.huella_archivo:
        req.huella_archivo = huella_archivo(req.archivo)
        req.save(update_fields=["huella_archivo"])
    return req.huella_archivo


def contenido(req):
    """Lo que se firma: el archivo exacto (por su huella) y a quién se contrata."""
    p = req.proceso
    return {
        "documento": "contrato", "requisito": req.pk, "proceso": p.pk,
        "candidato": {"nombre": p.candidato_nombre, "documento": p.candidato_documento},
        "cargo": p.cargo.nombre, "archivo": req.nombre_archivo, "archivo_sha256": asegurar_huella(req),
    }


def titulo(req):
    return f"Contrato de {req.proceso.candidato_nombre} · {req.proceso.cargo.nombre}"


def estado(req):
    """Firmas que valen para el archivo actual: {'candidato': Firma|None, 'empleador': Firma|None}."""
    if not req.archivo:
        return {"candidato": None, "empleador": None}
    vigente = huella(contenido(req))
    firmas = [f for f in firmas_de(TIPO, req.pk) if f.huella_documento == vigente]
    return {
        "candidato": next((f for f in firmas if f.calidad == CALIDAD_CANDIDATO), None),
        "empleador": next((f for f in firmas if f.calidad == CALIDAD_EMPLEADOR), None),
    }


def completar_si_firmado(request, req):
    e = estado(req)
    if e["candidato"] and e["empleador"] and req.estado != RequisitoIngreso.Estado.VERIFICADO:
        req.estado = RequisitoIngreso.Estado.VERIFICADO
        req.verificado_por, req.verificado_en = e["empleador"].firmante, timezone.now()
        req.save(update_fields=["estado", "verificado_por", "verificado_en"])
        registrar(request, "verificar", req, detalle="contrato firmado por las dos partes")
        return True
    return False


def se_puede_firmar(req):
    return (
        req.es_contrato and bool(req.archivo) and req.proceso.estado == ProcesoIngreso.Estado.EN_CURSO
        and req.estado in (RequisitoIngreso.Estado.CARGADO, RequisitoIngreso.Estado.VERIFICADO)
    )


# --- Candidato: enlace por correo -------------------------------------------------------------------------

def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def enviar_enlace(request, req):
    token = secrets.token_urlsafe(32)
    p = req.proceso
    EnvioFirmaContrato.objects.create(
        requisito=req, token_hash=_hash_token(token), enviado_a=p.candidato_email,
        huella_archivo=asegurar_huella(req), enviado_por=request.user,
        expira=timezone.now() + EnvioFirmaContrato.VIGENCIA,
    )
    enlace = request.build_absolute_uri(f"/ingreso/firma/{token}/")
    dias = EnvioFirmaContrato.VIGENCIA.days
    send_mail(
        f"{request.tenant.nombre}: firma tu contrato",
        f"Hola {p.candidato_nombre.split(' ')[0]}:\n\n{request.tenant.nombre} te envía tu contrato para el cargo "
        f"{p.cargo.nombre}. Ábrelo, léelo y fírmalo electrónicamente en este enlace:\n\n{enlace}\n\n"
        f"Al firmar te enviaremos un código a este mismo correo. El enlace vence en {dias} días.\n"
        "Si no esperabas este correo, ignóralo.",
        settings.DEFAULT_FROM_EMAIL,
        [p.candidato_email],
    )
    registrar(request, "enviar_a_firma", req, detalle=p.candidato_email)


def envio_por_token(token):
    envio = get_object_or_404(
        EnvioFirmaContrato.objects.select_related("requisito__proceso__cargo"), token_hash=_hash_token(token)
    )
    return envio


def firmante_candidato(envio):
    p = envio.requisito.proceso
    return Firmante(nombre=p.candidato_nombre, email=envio.enviado_a, documento=p.candidato_documento)


# --- Empleador: firma con su cuenta (pantalla común de firmas) --------------------------------------------

def manejador_contrato(request, pk):
    req = get_object_or_404(RequisitoIngreso.objects.select_related("proceso__cargo"), pk=pk)
    if not request.user.es_admin_empresa or not req.es_contrato:
        from django.http import Http404

        raise Http404
    volver = f"/ingreso/{req.proceso_id}/#req-{req.pk}"
    permitido = se_puede_firmar(req) and estado(req)["empleador"] is None

    def despues():
        if completar_si_firmado(request, req):
            return "Firmaste el contrato por la empresa. Ya firmaron las dos partes: el requisito quedó verificado."
        return "Firmaste el contrato por la empresa. Falta la firma del candidato."

    return {
        "objeto": req, "contenido": contenido(req), "titulo": titulo(req), "permitido": permitido,
        "calidad": CALIDAD_EMPLEADOR, "volver": volver, "despues": despues,
        "archivo_url": f"/ingreso/requisito/{req.pk}/archivo/",
    }
