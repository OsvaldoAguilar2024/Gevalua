import json

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.estructura.models import Area, Empleado
from apps.nucleo.auditoria import registrar

from .models import Notificacion, Recordatorio, SuscripcionPush


@login_required
@require_POST
def suscribir(request):
    try:
        datos = json.loads(request.body)
        endpoint, claves = datos["endpoint"], datos["keys"]
    except (ValueError, KeyError):
        return JsonResponse({"ok": False}, status=400)
    SuscripcionPush.objects.update_or_create(
        endpoint=endpoint,
        defaults={"usuario": request.user, "p256dh": claves["p256dh"], "auth": claves["auth"], "activa": True,
                  "dispositivo": request.META.get("HTTP_USER_AGENT", "")[:300]},
    )
    return JsonResponse({"ok": True})


@login_required
def avisos(request):
    lista = Notificacion.objects.filter(usuario=request.user, canal=Notificacion.Canal.CORREO)[:50]
    Notificacion.objects.filter(usuario=request.user, leida__isnull=True).update(leida=timezone.now())
    return render(request, "notificaciones/avisos.html", {"avisos": lista, "vapid": settings.VAPID_PUBLIC_KEY})


class FormularioRecordatorio(forms.ModelForm):
    class Meta:
        model = Recordatorio
        fields = ["mensaje", "destino", "persona", "area", "proximo_envio", "repeticion", "por_push", "por_correo"]
        widgets = {"proximo_envio": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        yo = getattr(usuario, "empleado", None)
        if usuario.es_admin_empresa:
            self.fields["persona"].queryset = Empleado.objects.filter(estado="activo").select_related("usuario")
        else:
            self.fields["persona"].queryset = Empleado.objects.filter(pk__in=[e.pk for e in yo.subordinados()]) if yo else Empleado.objects.none()
            self.fields["destino"].choices = [c for c in Recordatorio.Destino.choices if c[0] != "area"]
            del self.fields["area"]
        if "area" in self.fields:
            self.fields["area"].queryset = Area.objects.filter(activa=True)

    def clean(self):
        d = super().clean()
        if d.get("destino") == "persona" and not d.get("persona"):
            self.add_error("persona", "Elige a la persona.")
        if d.get("destino") == "area" and not d.get("area"):
            self.add_error("area", "Elige el área.")
        if not d.get("por_push") and not d.get("por_correo"):
            raise forms.ValidationError("Elige al menos un canal.")
        if d.get("proximo_envio") and d["proximo_envio"] < timezone.now():
            self.add_error("proximo_envio", "La fecha ya pasó.")
        return d


def _jefe_o_admin(request):
    u = request.user
    if not u.is_authenticated or not (u.es_jefe or u.es_admin_empresa):
        raise Http404


def recordatorios(request):
    _jefe_o_admin(request)
    form = FormularioRecordatorio(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.creado_por = request.user
        r.save()
        registrar(request, "crear", r)
        messages.success(request, "Recordatorio programado.")
        return redirect("recordatorios")
    lista = Recordatorio.objects.filter(creado_por=request.user).select_related("persona__usuario", "area")
    return render(request, "notificaciones/recordatorios.html", {"form": form, "recordatorios": lista})


@require_POST
def desactivar_recordatorio(request, pk):
    _jefe_o_admin(request)
    r = get_object_or_404(Recordatorio, pk=pk, creado_por=request.user)
    r.activo = False
    r.save(update_fields=["activo"])
    return redirect("recordatorios")
