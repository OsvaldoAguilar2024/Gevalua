from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.cuentas.models import Usuario
from apps.cuentas.servicios import enviar_correo_activacion
from apps.nucleo.auditoria import registrar
from apps.nucleo.permisos import AdminEmpresaRequerido, JefeRequerido

from .forms import FormularioArea, FormularioCargo, FormularioEmpleado
from .models import Area, Cargo, Empleado, PermisoConsultor


class FormularioGenericoMixin:
    template_name = "estructura/formulario.html"
    titulo = ""
    volver = reverse_lazy("estructura")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo if not getattr(self, "object", None) else f"Editar {self.object}"
        ctx["volver"] = self.volver
        return ctx

    def form_valid(self, form):
        nuevo = form.instance.pk is None
        respuesta = super().form_valid(form)
        registrar(self.request, "crear" if nuevo else "editar", self.object)
        messages.success(self.request, "Guardado.")
        return respuesta


class Estructura(AdminEmpresaRequerido, TemplateView):
    template_name = "estructura/inicio.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["areas"] = Area.objects.annotate(n_cargos=Count("cargos")).select_related("area_padre")
        ctx["cargos"] = Cargo.objects.select_related("area").annotate(
            n_empleados=Count("empleados", filter=Q(empleados__estado=Empleado.Estado.ACTIVO))
        )
        return ctx


class CrearArea(AdminEmpresaRequerido, FormularioGenericoMixin, CreateView):
    model = Area
    form_class = FormularioArea
    titulo = "Nueva área"
    success_url = reverse_lazy("estructura")


class EditarArea(AdminEmpresaRequerido, FormularioGenericoMixin, UpdateView):
    model = Area
    form_class = FormularioArea
    success_url = reverse_lazy("estructura")


class CrearCargo(AdminEmpresaRequerido, FormularioGenericoMixin, CreateView):
    model = Cargo
    form_class = FormularioCargo
    titulo = "Nuevo cargo"
    success_url = reverse_lazy("estructura")


class EditarCargo(AdminEmpresaRequerido, FormularioGenericoMixin, UpdateView):
    model = Cargo
    form_class = FormularioCargo
    success_url = reverse_lazy("estructura")


class ListaEmpleados(AdminEmpresaRequerido, ListView):
    template_name = "estructura/empleados.html"
    context_object_name = "empleados"

    def get_queryset(self):
        qs = Empleado.objects.select_related("usuario", "cargo__area", "jefe__usuario")
        self.estado = self.request.GET.get("estado", Empleado.Estado.ACTIVO)
        if self.estado:
            qs = qs.filter(estado=self.estado)
        self.area = self.request.GET.get("area", "")
        if self.area:
            qs = qs.filter(cargo__area_id=self.area)
        self.q = self.request.GET.get("q", "").strip()
        if self.q:
            qs = qs.filter(
                Q(usuario__nombre__icontains=self.q) | Q(usuario__email__icontains=self.q) | Q(usuario__documento__icontains=self.q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(areas=Area.objects.all(), estado=self.estado, area=self.area, q=self.q, estados=Empleado.Estado.choices)
        return ctx


class CrearEmpleado(AdminEmpresaRequerido, FormularioGenericoMixin, CreateView):
    model = Empleado
    form_class = FormularioEmpleado
    titulo = "Nueva persona"
    volver = reverse_lazy("empleados")
    success_url = reverse_lazy("empleados")

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        enviar_correo_activacion(self.request.tenant, self.object.usuario)
        messages.info(self.request, f"Se envió a {self.object.usuario.email} el enlace para crear su contraseña.")
        return respuesta


class EditarEmpleado(AdminEmpresaRequerido, FormularioGenericoMixin, UpdateView):
    template_name = "estructura/empleado_form.html"
    model = Empleado
    form_class = FormularioEmpleado
    volver = reverse_lazy("empleados")
    success_url = reverse_lazy("empleados")


def reenviar_activacion(request, pk):
    if not (request.user.is_authenticated and request.user.es_admin_empresa) or request.method != "POST":
        return redirect("empleados")
    empleado = get_object_or_404(Empleado, pk=pk)
    enviar_correo_activacion(request.tenant, empleado.usuario)
    registrar(request, "reenviar_activacion", empleado)
    messages.info(request, f"Enlace reenviado a {empleado.usuario.email}.")
    return redirect(reverse("editar_empleado", args=[pk]))


class Organigrama(JefeRequerido, TemplateView):
    template_name = "estructura/organigrama.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        activos = list(Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario", "cargo"))
        hijos = {}
        for e in activos:
            hijos.setdefault(e.jefe_id, []).append(e)

        def arbol(jefe_id, nivel=0, vistos=None):
            vistos = vistos or set()
            filas = []
            for e in sorted(hijos.get(jefe_id, []), key=lambda x: str(x)):
                if e.pk in vistos:
                    continue
                vistos.add(e.pk)
                filas.append({"empleado": e, "nivel": nivel, "n_equipo": len(hijos.get(e.pk, []))})
                filas.extend(arbol(e.pk, nivel + 1, vistos))
            return filas

        if self.request.user.es_admin_empresa:
            ctx["filas"] = arbol(None)
        else:
            yo = getattr(self.request.user, "empleado", None)
            ctx["filas"] = ([{"empleado": yo, "nivel": 0, "n_equipo": len(hijos.get(yo.pk, []))}] + arbol(yo.pk, 1)) if yo else []
        return ctx


# --- Consultores: qué puede consultar cada uno (solo lectura) ----------------------------------------------

class FormularioPermisoConsultor(forms.ModelForm):
    class Meta:
        model = PermisoConsultor
        fields = ["toda_la_empresa", "areas", "empleados"]
        widgets = {"areas": forms.CheckboxSelectMultiple, "empleados": forms.SelectMultiple(attrs={"size": 8})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empleados"].queryset = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO).select_related("usuario")
        self.fields["empleados"].help_text = "Mantén presionado Ctrl o ⌘ para elegir varias."


def consultores(request):
    if not (request.user.is_authenticated and request.user.es_admin_empresa):
        raise Http404
    filas = []
    for u in Usuario.objects.filter(es_consultor=True, is_active=True):
        p = getattr(u, "permiso_consultor", None)
        if p is None:
            resumen = "Nada habilitado"
        elif p.toda_la_empresa:
            resumen = "Toda la empresa"
        else:
            partes = [str(a) for a in p.areas.all()] + [str(e) for e in p.empleados.select_related("usuario")]
            resumen = ", ".join(partes) or "Nada habilitado"
        filas.append({"u": u, "resumen": resumen})
    return render(request, "estructura/consultores.html", {"filas": filas})


def permiso_consultor(request, pk):
    if not (request.user.is_authenticated and request.user.es_admin_empresa):
        raise Http404
    usuario = get_object_or_404(Usuario, pk=pk, es_consultor=True)
    permiso, _ = PermisoConsultor.objects.get_or_create(usuario=usuario)
    form = FormularioPermisoConsultor(request.POST or None, instance=permiso)
    if request.method == "POST" and form.is_valid():
        form.save()
        registrar(request, "editar", permiso, detalle=f"consultor {usuario.email}")
        messages.success(request, f"Permisos de {usuario} guardados.")
        return redirect("consultores")
    return render(request, "estructura/formulario.html", {
        "form": form, "titulo": f"Qué puede consultar {usuario}", "volver": "/estructura/consultores/",
    })
