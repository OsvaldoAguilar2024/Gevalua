from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.cuentas.models import Usuario
from apps.cuentas.servicios import crear_administrador


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccesoPorRolesTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-7"

    def setUp(self):
        self.c = TenantClient(self.tenant)
        self.empleado = Usuario.objects.create_user("empleado@prueba.co", "clave-segura-123", nombre="Ana Pérez")
        self.jefe = Usuario.objects.create_user("jefe@prueba.co", "clave-segura-123", es_jefe=True)

    def test_inicio_pide_login(self):
        r = self.c.get(reverse("inicio"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r["Location"])

    def test_login_con_correo(self):
        r = self.c.post(reverse("login"), {"username": "EMPLEADO@prueba.co", "password": "clave-segura-123"})
        self.assertEqual(r.status_code, 302)
        r = self.c.get(reverse("inicio"))
        self.assertContains(r, "Hola, Ana")
        self.assertNotContains(r, "Ir al panel")

    def test_empleado_no_ve_panel(self):
        self.c.force_login(self.empleado)
        self.assertEqual(self.c.get(reverse("panel")).status_code, 403)

    def test_jefe_ve_panel(self):
        self.c.force_login(self.jefe)
        r = self.c.get(reverse("panel"))
        self.assertContains(r, "Mi equipo")

    def test_manifest_pwa(self):
        r = self.c.get(reverse("manifest"))
        self.assertEqual(r.json()["display"], "standalone")
        self.assertIn("Empresa de prueba", r.json()["name"])

    def test_crear_administrador_envia_activacion(self):
        admin = crear_administrador(self.tenant, "gerente@prueba.co", "Gerente")
        self.assertTrue(admin.es_admin_empresa)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/cuenta/clave/", mail.outbox[0].body)

    def test_salud(self):
        self.assertEqual(self.c.get("/salud/").content, b"ok")


class DominioPublicoTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-8"

    def test_dominio_publico_sin_registrar_abre_portada(self):
        from django.db import connection
        from django.test import Client

        from apps.clientes.models import Empresa

        connection.set_schema_to_public()
        Empresa.objects.get_or_create(schema_name="public", defaults={"nombre": "op", "nit": "000000000-0"})
        with self.settings(PUBLIC_DOMAINS=["web-prueba.up.railway.app"], ALLOWED_HOSTS=["*"]):
            r = Client(HTTP_HOST="web-prueba.up.railway.app").get("/")
        self.assertContains(r, "DVQ-Evalua")
