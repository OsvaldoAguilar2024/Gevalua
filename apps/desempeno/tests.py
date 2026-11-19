import re
from datetime import date

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.cuentas.models import Usuario
from apps.estructura.models import Empleado
from apps.firmas.models import Firma

from .models import Concertacion, Periodo, Plantilla


def persona(email, jefe=None, **kw):
    u = Usuario.objects.create_user(email, "clave-segura-123", nombre=email.split("@")[0].title(), **kw)
    return Empleado.objects.create(usuario=u, jefe=jefe)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ConcertacionTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-7"

    def setUp(self):
        self.c = TenantClient(self.tenant)
        self.gerente = persona("gerente@prueba.co", es_admin_empresa=True)
        self.jefe = persona("jefe@prueba.co", jefe=self.gerente)
        self.emp = persona("emp@prueba.co", jefe=self.jefe)
        self.jefe.usuario.refresh_from_db()
        self.c.force_login(self.gerente.usuario)
        self.c.post(reverse("plantillas"), {"periodicidad": "mensual"})
        self.plantilla = Plantilla.objects.get()
        self.c.post(reverse("periodos"), {
            "plantilla": self.plantilla.pk, "nombre": "Diciembre 2026",
            "fecha_inicio": "2026-12-01", "fecha_fin": "2026-12-31", "fecha_limite": "2027-01-05",
        })
        self.periodo = Periodo.objects.get()
        self.c.post(reverse("periodo", args=[self.periodo.pk]), {"accion": "generar"})

    def firmar_como(self, usuario, conc):
        self.c.force_login(usuario)
        url = reverse("firmar", args=["concertacion", conc.pk])
        mail.outbox.clear()
        self.c.post(url, {"accion": "enviar_codigo"})
        codigo = re.search(r"\b(\d{6})\b", mail.outbox[0].subject).group(1)
        return self.c.post(url, {"accion": "firmar", "codigo": codigo})

    def test_plantilla_generica_suma_100(self):
        self.assertEqual(self.plantilla.suma_pesos, 100)
        self.assertEqual(self.plantilla.criterios.filter(tipo="oportunidad").count(), 1)

    def test_genera_concertaciones_para_quienes_tienen_jefe(self):
        self.assertEqual(Concertacion.objects.count(), 2)  # jefe y empleado; el gerente no tiene jefe
        conc = Concertacion.objects.get(empleado=self.emp)
        self.assertEqual(conc.jefe, self.jefe)
        self.assertEqual(conc.metas.count(), 4)

    def test_flujo_firma_jefe_y_empleado(self):
        conc = Concertacion.objects.get(empleado=self.emp)
        # el empleado aún no puede firmar
        self.c.force_login(self.emp.usuario)
        self.assertNotContains(self.c.get(reverse("concertacion", args=[conc.pk])), "Aceptar y firmar")
        self.firmar_como(self.jefe.usuario, conc)
        conc.refresh_from_db()
        self.assertEqual(conc.estado, Concertacion.Estado.POR_ACEPTAR)
        self.firmar_como(self.emp.usuario, conc)
        conc.refresh_from_db()
        self.assertEqual(conc.estado, Concertacion.Estado.ACEPTADA)
        firmas = Firma.objects.filter(documento_tipo="concertacion", documento_id=conc.pk)
        self.assertEqual(firmas.count(), 2)
        self.assertEqual(len({f.huella_documento for f in firmas}), 1)

    def test_codigo_incorrecto_no_firma(self):
        conc = Concertacion.objects.get(empleado=self.emp)
        self.c.force_login(self.jefe.usuario)
        url = reverse("firmar", args=["concertacion", conc.pk])
        self.c.post(url, {"accion": "enviar_codigo"})
        self.c.post(url, {"accion": "firmar", "codigo": "000000" if "000000" not in mail.outbox[-1].subject else "111111"})
        conc.refresh_from_db()
        self.assertEqual(conc.estado, Concertacion.Estado.BORRADOR)

    def test_cambiar_metas_invalida_codigo(self):
        conc = Concertacion.objects.get(empleado=self.emp)
        self.c.force_login(self.jefe.usuario)
        url = reverse("firmar", args=["concertacion", conc.pk])
        self.c.post(url, {"accion": "enviar_codigo"})
        codigo = re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)
        meta = conc.metas.first()
        meta.descripcion = "Otra cosa"
        meta.save()
        self.c.post(url, {"accion": "firmar", "codigo": codigo})
        conc.refresh_from_db()
        self.assertEqual(conc.estado, Concertacion.Estado.BORRADOR)

    def test_ajeno_no_ve_concertacion(self):
        otro = persona("otro@prueba.co")
        conc = Concertacion.objects.get(empleado=self.emp)
        self.c.force_login(otro.usuario)
        self.assertEqual(self.c.get(reverse("concertacion", args=[conc.pk])).status_code, 404)
        # el gerente la ve en cascada
        self.c.force_login(self.gerente.usuario)
        self.assertEqual(self.c.get(reverse("concertacion", args=[conc.pk])).status_code, 200)

    def test_jefe_edita_pesos_deben_sumar_100(self):
        conc = Concertacion.objects.get(empleado=self.emp)
        self.c.force_login(self.jefe.usuario)
        metas = list(conc.metas.all())
        datos = {"accion": "guardar", "metas-TOTAL_FORMS": str(len(metas)), "metas-INITIAL_FORMS": str(len(metas)),
                 "metas-MIN_NUM_FORMS": "0", "metas-MAX_NUM_FORMS": "1000"}
        for i, m in enumerate(metas):
            datos.update({f"metas-{i}-id": m.pk, f"metas-{i}-tipo": m.tipo, f"metas-{i}-descripcion": m.descripcion,
                          f"metas-{i}-peso": 50, f"metas-{i}-indicador": "", f"metas-{i}-valor_objetivo": "",
                          f"metas-{i}-evidencia_requerida": ""})
        r = self.c.post(reverse("concertacion", args=[conc.pk]), datos)
        self.assertContains(r, "deben sumar 100")
