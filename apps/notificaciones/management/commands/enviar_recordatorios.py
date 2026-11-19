from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import get_tenant_model, tenant_context

from apps.notificaciones.automaticos import enviar_automaticos
from apps.notificaciones.models import Recordatorio
from apps.notificaciones.servicios import notificar


class Command(BaseCommand):
    help = "Envía los recordatorios que tocan en todas las empresas. Lo corre el servicio cron de Railway cada pocos minutos."

    def handle(self, *args, **o):
        total = 0
        for empresa in get_tenant_model().objects.exclude(schema_name="public").filter(activa=True):
            with tenant_context(empresa):
                for r in Recordatorio.objects.filter(activo=True, proximo_envio__lte=timezone.now()).select_related("creado_por"):
                    autor = r.creado_por.get_short_name()
                    for u in r.destinatarios():
                        notificar(u, f"Recordatorio de {autor}", r.mensaje, "/", f"recordatorio:{r.pk}", push=r.por_push, correo=r.por_correo, recordatorio=r)
                        total += 1
                    r.ultimo_envio = timezone.now()
                    r.avanzar()
                    r.save(update_fields=["ultimo_envio", "proximo_envio", "activo"])
                total += enviar_automaticos()
        self.stdout.write(f"Avisos enviados: {total}")
