import shutil
import tempfile
from datetime import date, timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.cuentas.models import Usuario
from apps.estructura.models import Area, Cargo, Empleado

from .models import Etapa, ProcesoIngreso, RequisitoIngreso

MEDIA = tempfile.mkdtemp()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MEDIA_ROOT=MEDIA)
class IngresoTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-7"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.c = TenantClient(self.tenant)
        self.admin = Usuario.objects.create_user("admin@prueba.co", "clave-segura-123", es_admin_empresa=True)
        self.c.force_login(self.admin)
        self.cargo = Cargo.objects.create(area=Area.objects.create(nombre="Operación"), nombre="Auxiliar")

    def nuevo_proceso(self):
        r = self.c.post(reverse("crear_proceso"), {
            "candidato_nombre": "Carlos Díaz", "candidato_documento": "1020304050", "cargo": self.cargo.pk,
        })
        self.assertEqual(r.status_code, 302)
        return ProcesoIngreso.objects.get()

    def cargar_y_verificar(self, req, fecha=None):
        datos = {"archivo": SimpleUploadedFile("doc.pdf", b"%PDF-1.4 prueba", content_type="application/pdf")}
        if fecha:
            datos["fecha_documento"] = fecha.isoformat()
        self.c.post(reverse("cargar_requisito", args=[req.pk]), datos)
        self.c.post(reverse("verificar_requisito", args=[req.pk, "verificar"]))
        req.refresh_from_db()
        return req

    def test_proceso_copia_lista_generica(self):
        p = self.nuevo_proceso()
        self.assertEqual(p.requisitos.filter(etapa=Etapa.SELECCION).count(), 7)
        self.assertTrue(p.requisitos.filter(tipo="antecedentes", fuente_url__startswith="https://").exists())

    def test_antecedentes_requieren_autorizacion(self):
        p = self.nuevo_proceso()
        ante = p.requisitos.filter(tipo="antecedentes").first()
        self.c.post(reverse("cargar_requisito", args=[ante.pk]), {
            "archivo": SimpleUploadedFile("a.pdf", b"%PDF"), "fecha_documento": date.today().isoformat(),
        })
        ante.refresh_from_db()
        self.assertEqual(ante.estado, RequisitoIngreso.Estado.PENDIENTE)

    def test_rechaza_tipo_de_archivo(self):
        p = self.nuevo_proceso()
        hv = p.requisitos.get(tipo="hoja_vida")
        self.c.post(reverse("cargar_requisito", args=[hv.pk]), {"archivo": SimpleUploadedFile("x.exe", b"MZ")})
        hv.refresh_from_db()
        self.assertEqual(hv.estado, RequisitoIngreso.Estado.PENDIENTE)

    def test_certificacion_bancaria_vencida_no_cuenta(self):
        p = self.nuevo_proceso()
        banc = p.requisitos.get(tipo="certificacion_bancaria")
        banc = self.cargar_y_verificar(banc, fecha=date.today() - timedelta(days=45))
        self.assertTrue(banc.vencido)
        self.assertFalse(banc.cumplido)

    def test_flujo_completo_hasta_contratar(self):
        p = self.nuevo_proceso()
        for etapa in (Etapa.SELECCION, Etapa.PRECONTRATO):
            self.assertFalse(ProcesoIngreso.objects.get(pk=p.pk).puede_avanzar)
            for req in p.requisitos.filter(etapa=etapa, obligatorio=True).order_by("orden"):
                self.cargar_y_verificar(req, fecha=date.today())
            self.c.post(reverse("avanzar_proceso", args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.etapa, Etapa.CONTRATO)
        for req in p.requisitos.filter(etapa=Etapa.CONTRATO, obligatorio=True):
            self.cargar_y_verificar(req, fecha=date.today())
        r = self.c.post(reverse("contratar", args=[p.pk]), {
            "email": "carlos@prueba.co", "fecha_ingreso": date.today().isoformat(), "tipo_contrato": "indefinido",
        })
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.estado, ProcesoIngreso.Estado.CONTRATADO)
        self.assertEqual(p.empleado.usuario.documento, "1020304050")
        self.assertEqual(p.empleado.cargo, self.cargo)

    def test_empleado_no_ve_ingresos(self):
        emp = Usuario.objects.create_user("e@prueba.co", "clave-segura-123")
        p = self.nuevo_proceso()
        self.c.force_login(emp)
        self.assertEqual(self.c.get(reverse("proceso", args=[p.pk])).status_code, 404)
        self.assertEqual(self.c.get(reverse("ingresos")).status_code, 403)

    def test_alertas_periodo_prueba(self):
        u = Usuario.objects.create_user("n@prueba.co", "clave-segura-123", nombre="Nueva Persona")
        Empleado.objects.create(usuario=u, fecha_ingreso=date.today() - timedelta(days=50))
        self.assertContains(self.c.get(reverse("alertas")), "Nueva Persona")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MEDIA_ROOT=MEDIA)
class FirmaContratoTests(TenantTestCase):
    """Firma electrónica del contrato: el candidato por enlace en su correo y la empresa con su cuenta."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-8"

    def setUp(self):
        import re

        self.re = re
        self.c = TenantClient(self.tenant)
        self.admin = Usuario.objects.create_user("admin@prueba.co", "clave-segura-123", es_admin_empresa=True, nombre="Ana Gerente")
        self.c.force_login(self.admin)
        cargo = Cargo.objects.create(area=Area.objects.create(nombre="Operación"), nombre="Auxiliar")
        self.p = ProcesoIngreso.objects.create(
            candidato_nombre="Carlos Díaz", candidato_documento="1020304050", candidato_email="carlos@correo.co",
            cargo=cargo, etapa=Etapa.CONTRATO,
        )
        self.req = self.p.requisitos.get(tipo="contrato")
        self.c.post(reverse("cargar_requisito", args=[self.req.pk]), {
            "archivo": SimpleUploadedFile("contrato.pdf", b"%PDF-1.4 contrato", content_type="application/pdf"),
        })
        self.req.refresh_from_db()

    def enlace_candidato(self):
        mail.outbox.clear()
        self.c.post(reverse("enviar_a_firma", args=[self.req.pk]))
        self.assertEqual(mail.outbox[0].to, ["carlos@correo.co"])
        return self.re.search(r"https?://[^/]+(/ingreso/firma/[^/\s]+/)", mail.outbox[0].body).group(1)

    def firma_candidato(self, ruta):
        anonimo = TenantClient(self.tenant)
        self.assertEqual(anonimo.get(ruta).status_code, 200)
        huella = anonimo.get(ruta).context["huella"]
        anonimo.post(ruta, {"accion": "firmar", "acepto": "1", "huella": huella})
        return anonimo

    def firma_empresa(self):
        ruta = reverse("firmar", args=["contrato", self.req.pk])
        huella = self.c.get(ruta).context["huella"]
        self.c.post(ruta, {"accion": "firmar", "acepto": "1", "huella": huella})

    def test_las_dos_firmas_verifican_el_requisito(self):
        from apps.firmas.models import Firma

        self.assertTrue(self.req.huella_archivo)
        self.firma_candidato(self.enlace_candidato())
        self.req.refresh_from_db()
        self.assertEqual(self.req.estado, RequisitoIngreso.Estado.CARGADO)
        f = Firma.objects.get(documento_tipo="contrato", calidad="Trabajador")
        self.assertIsNone(f.firmante)
        self.assertEqual((f.firmante_documento, f.firmante_email), ("1020304050", "carlos@correo.co"))
        self.firma_empresa()
        self.req.refresh_from_db()
        self.assertEqual(self.req.estado, RequisitoIngreso.Estado.VERIFICADO)
        self.assertEqual(self.req.verificado_por, self.admin)
        self.assertContains(self.c.get(reverse("proceso", args=[self.p.pk])), "Firmó", count=2)

    def test_sin_aceptar_no_firma(self):
        from apps.firmas.models import Firma

        ruta = self.enlace_candidato()
        anonimo = TenantClient(self.tenant)
        anonimo.post(ruta, {"accion": "firmar", "huella": anonimo.get(ruta).context["huella"]})
        self.assertFalse(Firma.objects.filter(documento_tipo="contrato").exists())

    def test_cambiar_el_contrato_invalida_enlace_y_firmas(self):
        ruta = self.enlace_candidato()
        self.firma_empresa()
        self.c.post(reverse("cargar_requisito", args=[self.req.pk]), {
            "archivo": SimpleUploadedFile("contrato-v2.pdf", b"%PDF-1.4 otro contrato", content_type="application/pdf"),
        })
        self.assertEqual(TenantClient(self.tenant).get(ruta).status_code, 410)
        self.req.refresh_from_db()
        from .firma_contrato import estado

        self.assertIsNone(estado(self.req)["empleador"])

    def test_token_inventado_no_existe(self):
        self.assertEqual(TenantClient(self.tenant).get("/ingreso/firma/inventado/").status_code, 404)
