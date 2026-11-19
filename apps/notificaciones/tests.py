from datetime import date, timedelta

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.cuentas.models import Usuario
from apps.estructura.models import Empleado

from .models import Notificacion, Recordatorio


def persona(email, jefe=None, **kw):
    u = Usuario.objects.create_user(email, "clave-segura-123", nombre=email.split("@")[0].title(), **kw)
    return Empleado.objects.create(usuario=u, jefe=jefe)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecordatoriosTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-7"

    def setUp(self):
        self.c = TenantClient(self.tenant)
        self.jefe = persona("jefe@prueba.co", es_jefe=True)
        self.a = persona("a@prueba.co", jefe=self.jefe)
        self.b = persona("b@prueba.co", jefe=self.jefe)

    def test_jefe_programa_recordatorio_semanal(self):
        self.c.force_login(self.jefe.usuario)
        cuando = (timezone.localtime() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        r = self.c.post(reverse("recordatorios"), {
            "mensaje": "Subir el reporte semanal", "destino": "equipo", "proximo_envio": cuando,
            "repeticion": "semanal", "por_push": "on", "por_correo": "on",
        })
        self.assertEqual(r.status_code, 302)
        rec = Recordatorio.objects.get()
        rec.proximo_envio = timezone.now() - timedelta(minutes=1)
        rec.save()
        call_command("enviar_recordatorios", stdout=open("/dev/null", "w"))
        self.assertEqual(len(mail.outbox), 2)
        rec.refresh_from_db()
        self.assertTrue(rec.activo)
        self.assertGreater(rec.proximo_envio, timezone.now() + timedelta(days=6))
        # push sin claves queda registrado como no enviado; el correo sí sale
        self.assertTrue(Notificacion.objects.filter(canal="correo", enviada=True).count() == 2)

    def test_una_vez_se_desactiva(self):
        rec = Recordatorio.objects.create(creado_por=self.jefe.usuario, destino="persona", persona=self.a,
                                          mensaje="La evaluación cierra el 30", proximo_envio=timezone.now() - timedelta(minutes=1))
        call_command("enviar_recordatorios", stdout=open("/dev/null", "w"))
        rec.refresh_from_db()
        self.assertFalse(rec.activo)
        self.assertEqual([m.to for m in mail.outbox], [["a@prueba.co"]])

    def test_aviso_fin_periodo_prueba_una_sola_vez(self):
        admin = persona("th@prueba.co", es_admin_empresa=True)
        nuevo = persona("n@prueba.co", jefe=self.jefe)
        nuevo.fecha_ingreso = date.today() - timedelta(days=50)
        nuevo.fin_periodo_prueba = date.today() + timedelta(days=10)
        nuevo.save()
        call_command("enviar_recordatorios", stdout=open("/dev/null", "w"))
        destinatarios = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(destinatarios, ["jefe@prueba.co", "th@prueba.co"])
        call_command("enviar_recordatorios", stdout=open("/dev/null", "w"))
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(admin)

    def test_suscripcion_push(self):
        self.c.force_login(self.a.usuario)
        r = self.c.post(reverse("suscribir_push"), data='{"endpoint": "https://push.ejemplo/abc", "keys": {"p256dh": "x", "auth": "y"}}',
                        content_type="application/json")
        self.assertEqual(r.json(), {"ok": True})

    def test_empleado_no_programa(self):
        self.c.force_login(self.a.usuario)
        self.assertEqual(self.c.get(reverse("recordatorios")).status_code, 404)
