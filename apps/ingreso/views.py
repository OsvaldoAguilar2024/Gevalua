from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView

from apps.cuentas.models import Usuario
from apps.cuentas.servicios import enviar_correo_activacion
from apps.estructura.models import Empleado
from apps.nucleo.auditoria import registrar
from apps.nucleo.permisos import AdminEmpresaRequerido

from apps.firmas import servicios as firmas

from . import firma_contrato
from .forms import FormularioCargaRequisito, FormularioContratacion, FormularioProceso, ItemsPlantillaFormSet
from .models import Etapa, PlantillaRequisitos, ProcesoIngreso, RequisitoIngreso


def solo_admin(request):
    if not (request.user.is_authenticated and request.user.es_admin_empresa):
        raise Http404


class ListaProcesos(AdminEmpresaRequerido, ListView):
    template_name = "ingreso/lista.html"
    context_object_name = "procesos"

    def get_queryset(self):
        self.estado = self.request.GET.get("estado", ProcesoIngreso.Estado.EN_CURSO)
        qs = ProcesoIngreso.objects.select_related("cargo__area").prefetch_related("requisitos")
        return qs.filter(estado=self.estado) if self.estado else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(estado=self.estado, estados=ProcesoIngreso.Estado.choices)
        return ctx


class CrearProceso(AdminEmpresaRequerido, CreateView):
    model = ProcesoIngreso
    form_class = FormularioProceso
    template_name = "estructura/formulario.html"
    extra_context = {"titulo": "Nuevo proceso de ingreso"}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["volver"] = "/ingreso/"
        return ctx

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        respuesta = super().form_valid(form)
        registrar(self.request, "crear", self.object)
        return respuesta

    def get_success_url(self):
        return f"/ingreso/{self.object.pk}/"


def detalle(request, pk):
    solo_admin(request)
    proceso = get_object_or_404(ProcesoIngreso.objects.select_related("cargo__area", "empleado__usuario"), pk=pk)
    registrar(request, "consultar", proceso)
    etapas = []
    indice_actual = [v for v, _ in Etapa.choices].index(proceso.etapa)
    for i, (valor, nombre) in enumerate(Etapa.choices):
        reqs = list(proceso.requisitos_de(valor).select_related("verificado_por"))
        for r in reqs:
            if r.es_contrato and r.archivo:
                r.firma = firma_contrato.estado(r)
                r.firma["se_puede"] = firma_contrato.se_puede_firmar(r)
                r.firma["ultimo_envio"] = r.envios_firma.first()
        etapas.append({
            "valor": valor, "nombre": nombre, "requisitos": reqs,
            "actual": valor == proceso.etapa,
            "completa": i < indice_actual or proceso.estado == ProcesoIngreso.Estado.CONTRATADO and i <= indice_actual
            and all(r.cumplido for r in reqs if r.obligatorio),
        })
    return render(request, "ingreso/detalle.html", {
        "proceso": proceso, "etapas": etapas, "form_carga": FormularioCargaRequisito(),
        "form_contratar": FormularioContratacion(initial={"email": proceso.candidato_email}),
    })


def cargar_requisito(request, pk):
    solo_admin(request)
    req = get_object_or_404(RequisitoIngreso, pk=pk)
    if request.method == "POST":
        form = FormularioCargaRequisito(request.POST, request.FILES, instance=req)
        if req.es_antecedente and not req.proceso.autorizacion_verificada:
            messages.error(request, "Primero verifica la autorización de tratamiento de datos del candidato.")
        elif form.is_valid():
            req = form.save(commit=False)
            if "archivo" in request.FILES:
                req.nombre_archivo = request.FILES["archivo"].name[:255]
                req.huella_archivo = ""  # se recalcula con el archivo nuevo; las firmas del anterior dejan de valer
            req.estado = RequisitoIngreso.Estado.CARGADO
            req.cargado_por, req.cargado_en = request.user, timezone.now()
            req.verificado_por = req.verificado_en = None
            req.save()
            if req.es_contrato and req.archivo:
                firma_contrato.asegurar_huella(req)
            registrar(request, "cargar", req, detalle=req.nombre_archivo)
            messages.success(request, f"{req.nombre}: cargado. Falta verificarlo.")
        else:
            for errores in form.errors.values():
                for e in errores:
                    messages.error(request, f"{req.nombre}: {e}")
    return redirect(f"/ingreso/{req.proceso_id}/#req-{req.pk}")


def verificar_requisito(request, pk, decision):
    solo_admin(request)
    req = get_object_or_404(RequisitoIngreso, pk=pk)
    if decision not in ("verificar", "rechazar"):
        raise Http404
    if request.method == "POST" and req.estado in (RequisitoIngreso.Estado.CARGADO, RequisitoIngreso.Estado.VERIFICADO):
        if decision == "verificar":
            req.estado = RequisitoIngreso.Estado.VERIFICADO
            req.verificado_por, req.verificado_en = request.user, timezone.now()
        else:
            req.estado = RequisitoIngreso.Estado.RECHAZADO
            req.observacion = (request.POST.get("motivo") or req.observacion)[:1000]
            req.verificado_por, req.verificado_en = request.user, timezone.now()
        req.save()
        registrar(request, decision, req)
    return redirect(f"/ingreso/{req.proceso_id}/#req-{req.pk}")


def enviar_a_firma(request, pk):
    """Envía al candidato el enlace para firmar el contrato."""
    solo_admin(request)
    req = get_object_or_404(RequisitoIngreso.objects.select_related("proceso__cargo"), pk=pk)
    if request.method == "POST":
        if not firma_contrato.se_puede_firmar(req):
            messages.error(request, "Carga el contrato antes de enviarlo a firma.")
        elif not req.proceso.candidato_email:
            messages.error(request, "Falta el correo del candidato en el proceso.")
        elif firma_contrato.estado(req)["candidato"]:
            messages.info(request, "El candidato ya firmó este contrato.")
        else:
            firma_contrato.enviar_enlace(request, req)
            messages.success(request, f"Enviamos el contrato a {req.proceso.candidato_email} para que lo firme.")
    return redirect(f"/ingreso/{req.proceso_id}/#req-{req.pk}")


def firma_candidato(request, token):
    """Página pública (sin cuenta) donde el candidato lee y firma su contrato desde el enlace de su correo."""
    envio = firma_contrato.envio_por_token(token)
    req = envio.requisito
    if not envio.vigente or not firma_contrato.se_puede_firmar(req):
        return render(request, "ingreso/firma_candidato.html", {"invalido": True, "empresa": request.tenant}, status=410)
    firmante = firma_contrato.firmante_candidato(envio)
    ya_firmo = firma_contrato.estado(req)["candidato"]
    titulo = firma_contrato.titulo(req)
    if request.method == "POST" and not ya_firmo and request.POST.get("accion") == "firmar":
        try:
            firmas.firmar(request, firma_contrato.TIPO, req.pk, firma_contrato.contenido(req), titulo,
                          firma_contrato.CALIDAD_CANDIDATO, firmante,
                          acepto=bool(request.POST.get("acepto")), huella_vista=request.POST.get("huella"))
        except firmas.ErrorFirma as e:
            messages.error(request, str(e))
            return redirect(request.path)
        firma_contrato.completar_si_firmado(request, req)
        messages.success(request, "Firmaste tu contrato. Gracias.")
        return redirect(request.path)
    return render(request, "ingreso/firma_candidato.html", {
        "req": req, "titulo": titulo, "ya_firmo": ya_firmo, "token": token, "empresa": request.tenant,
        "huella": firmas.huella(firma_contrato.contenido(req)), "texto": firmas.texto_aceptacion(titulo, firmante),
    })


def archivo_candidato(request, token):
    envio = firma_contrato.envio_por_token(token)
    if not envio.vigente or not envio.requisito.archivo:
        raise Http404
    registrar(request, "descargar", envio.requisito, detalle=f"candidato por enlace · {envio.enviado_a}")
    return redirect(envio.requisito.archivo.url)  # URL firmada que vence en 5 minutos


def descargar_requisito(request, pk):
    solo_admin(request)
    req = get_object_or_404(RequisitoIngreso, pk=pk)
    if not req.archivo:
        raise Http404
    registrar(request, "descargar", req, detalle=req.nombre_archivo)
    return redirect(req.archivo.url)  # URL firmada que vence en 5 minutos


def avanzar(request, pk):
    solo_admin(request)
    proceso = get_object_or_404(ProcesoIngreso, pk=pk)
    if request.method == "POST":
        if proceso.etapa == Etapa.CONTRATO and not proceso.empleado_id:
            messages.error(request, "Para pasar a poscontrato primero registra la contratación.")
        elif proceso.puede_avanzar:
            proceso.etapa = proceso.siguiente_etapa
            proceso.save(update_fields=["etapa"])
            registrar(request, "avanzar", proceso, detalle=proceso.etapa)
            messages.success(request, f"El proceso pasó a {proceso.get_etapa_display().lower()}.")
        else:
            messages.error(request, "Faltan requisitos obligatorios por verificar en esta etapa.")
    return redirect(f"/ingreso/{pk}/")


@transaction.atomic
def contratar(request, pk):
    solo_admin(request)
    proceso = get_object_or_404(ProcesoIngreso, pk=pk)
    if request.method != "POST" or proceso.etapa != Etapa.CONTRATO or proceso.empleado_id:
        return redirect(f"/ingreso/{pk}/")
    if proceso.faltantes():
        messages.error(request, "Faltan requisitos obligatorios del contrato por verificar.")
        return redirect(f"/ingreso/{pk}/")
    form = FormularioContratacion(request.POST)
    if not form.is_valid():
        for errores in form.errors.values():
            for e in errores:
                messages.error(request, e)
        return redirect(f"/ingreso/{pk}/#contratar")
    d = form.cleaned_data
    usuario = Usuario(email=d["email"].lower(), nombre=proceso.candidato_nombre, documento=proceso.candidato_documento)
    import secrets

    usuario.set_password(secrets.token_urlsafe(32))
    usuario.save()
    empleado = Empleado(
        usuario=usuario, cargo=proceso.cargo, jefe=d["jefe"], fecha_ingreso=d["fecha_ingreso"],
        tipo_contrato=d["tipo_contrato"], fin_contrato=d["fin_contrato"],
    )
    empleado.full_clean(exclude=["usuario"])
    empleado.save()
    proceso.empleado, proceso.estado, proceso.etapa = empleado, ProcesoIngreso.Estado.CONTRATADO, Etapa.POSCONTRATO
    proceso.save(update_fields=["empleado", "estado", "etapa"])
    registrar(request, "contratar", proceso, detalle=f"empleado {empleado.pk}")
    transaction.on_commit(lambda: enviar_correo_activacion(request.tenant, usuario))
    messages.success(request, f"{usuario} quedó registrado como empleado. Le enviamos el enlace para entrar.")
    return redirect(f"/ingreso/{pk}/")


def descartar(request, pk):
    solo_admin(request)
    proceso = get_object_or_404(ProcesoIngreso, pk=pk, estado=ProcesoIngreso.Estado.EN_CURSO)
    if request.method == "POST":
        proceso.estado = ProcesoIngreso.Estado.DESCARTADO
        proceso.save(update_fields=["estado"])
        registrar(request, "descartar", proceso)
    return redirect("/ingreso/")


def plantilla(request):
    solo_admin(request)
    plantilla = PlantillaRequisitos.general()
    formset = ItemsPlantillaFormSet(request.POST or None, instance=plantilla)
    if request.method == "POST" and formset.is_valid():
        formset.save()
        registrar(request, "editar", plantilla)
        messages.success(request, "Lista de requisitos guardada. Aplica a los procesos nuevos.")
        return redirect("/ingreso/plantilla/")
    return render(request, "ingreso/plantilla.html", {"formset": formset, "plantilla": plantilla})


class Alertas(AdminEmpresaRequerido, TemplateView):
    """Fin de periodo de prueba, fin de contrato y documentos de ingreso vencidos o por vencer."""

    template_name = "ingreso/alertas.html"
    DIAS = 30

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        limite = hoy + timedelta(days=self.DIAS)
        activos = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario", "cargo")
        ctx["prueba"] = activos.filter(fin_periodo_prueba__gte=hoy, fin_periodo_prueba__lte=limite).order_by("fin_periodo_prueba")
        ctx["contratos"] = activos.filter(fin_contrato__gte=hoy - timedelta(days=7), fin_contrato__lte=limite).order_by("fin_contrato")
        reqs = RequisitoIngreso.objects.filter(
            proceso__estado=ProcesoIngreso.Estado.EN_CURSO, vigencia_dias__isnull=False, fecha_documento__isnull=False,
            estado__in=[RequisitoIngreso.Estado.CARGADO, RequisitoIngreso.Estado.VERIFICADO],
        ).select_related("proceso")
        ctx["documentos"] = sorted((r for r in reqs if r.vence <= limite), key=lambda r: r.vence)
        ctx.update(hoy=hoy, dias=self.DIAS)
        return ctx
