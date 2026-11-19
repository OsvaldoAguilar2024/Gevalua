import re
from types import SimpleNamespace

from django.core import mail
from django.test import override_settings
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.nucleo.models import AutorizacionDatos

from . import seguridad
from .models import Usuario

CORREO = "django.core.mail.backends.locmem.EmailBackend"


class SegundoFactorTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-1"

    def setUp(self):
        # TenantTestCase no aplica override_settings de clase: se activa en cada prueba.
        ajuste = override_settings(EMAIL_BACKEND=CORREO, SEGUNDO_FACTOR_OBLIGATORIO=True, SEGUNDO_FACTOR_EXENTOS=["demo"])
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.c = TenantClient(self.tenant)
        self.admin = Usuario.objects.create_user("admin@prueba.co", "clave-segura-123", es_admin_empresa=True)
        self.emp = Usuario.objects.create_user("emp@prueba.co", "clave-segura-123")

    def codigo(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)

    def test_admin_debe_confirmar_codigo(self):
        self.c.force_login(self.admin)
        r = self.c.get("/panel/")
        self.assertRedirects(r, "/cuenta/verificar/?next=%2Fpanel%2F", fetch_redirect_response=False)
        r = self.c.get(r["Location"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(mail.outbox[-1].to, ["admin@prueba.co"])
        # recargar la página no manda otro correo
        self.c.get("/cuenta/verificar/?next=/panel/")
        self.assertEqual(len(mail.outbox), 1)
        malo = "000000" if self.codigo() != "000000" else "111111"
        self.c.post("/cuenta/verificar/", {"codigo": malo, "next": "/panel/"})
        self.assertEqual(self.c.get("/panel/").status_code, 302)
        r = self.c.post("/cuenta/verificar/", {"codigo": self.codigo(), "next": "/panel/"})
        self.assertRedirects(r, "/panel/", fetch_redirect_response=False)
        self.assertEqual(self.c.get("/panel/").status_code, 200)

    def test_cinco_intentos_bloquean_el_codigo(self):
        self.c.force_login(self.admin)
        self.c.get("/cuenta/verificar/")
        bueno = self.codigo()
        malo = "000000" if bueno != "000000" else "111111"
        for _ in range(seguridad.MAX_INTENTOS):
            self.c.post("/cuenta/verificar/", {"codigo": malo})
        self.c.post("/cuenta/verificar/", {"codigo": bueno})
        self.assertEqual(self.c.get("/panel/").status_code, 302)

    def test_recordar_dispositivo(self):
        self.c.force_login(self.admin)
        self.c.get("/cuenta/verificar/")
        self.c.post("/cuenta/verificar/", {"codigo": self.codigo(), "recordar": "on"})
        cookie = self.c.cookies[seguridad.COOKIE_DISPOSITIVO].value
        self.c.logout()  # el cliente de pruebas borra todas las cookies al salir; el navegador conserva esta
        self.c.cookies[seguridad.COOKIE_DISPOSITIVO] = cookie
        self.c.force_login(self.admin)
        self.assertEqual(self.c.get("/panel/").status_code, 200)
        # al cambiar la contraseña el dispositivo deja de valer
        self.admin.set_password("otra-clave-segura-456")
        self.admin.save()
        self.c.logout()
        self.c.cookies[seguridad.COOKIE_DISPOSITIVO] = cookie
        self.c.force_login(self.admin)
        self.assertEqual(self.c.get("/panel/").status_code, 302)

    def test_empleado_no_necesita_segundo_factor(self):
        self.c.force_login(self.emp)
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_operador_y_empresa_demo(self):
        pub = SimpleNamespace(schema_name="public")
        demo = SimpleNamespace(schema_name="demo")
        staff = SimpleNamespace(is_authenticated=True, is_staff=True, es_admin_empresa=False)
        self.assertTrue(seguridad.requiere_segundo_factor(SimpleNamespace(user=staff, tenant=pub)))
        admin_demo = SimpleNamespace(is_authenticated=True, is_staff=False, es_admin_empresa=True)
        self.assertFalse(seguridad.requiere_segundo_factor(SimpleNamespace(user=admin_demo, tenant=demo)))


class AutorizacionDatosTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-2"

    def setUp(self):
        ajuste = override_settings(EMAIL_BACKEND=CORREO, AUTORIZACION_DATOS_OBLIGATORIA=True)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.c = TenantClient(self.tenant)
        self.emp = Usuario.objects.create_user("emp@prueba.co", "clave-segura-123")
        self.c.force_login(self.emp)

    def test_primer_ingreso_pide_autorizacion(self):
        r = self.c.get("/avisos/")
        self.assertRedirects(r, "/cuenta/datos-personales/?next=%2Favisos%2F", fetch_redirect_response=False)
        r = self.c.get(r["Location"])
        self.assertContains(r, "Ley 1581")
        self.assertContains(r, "900123456-2")
        # sin marcar la casilla no avanza
        self.c.post("/cuenta/datos-personales/", {"next": "/avisos/"})
        self.assertEqual(self.c.get("/avisos/").status_code, 302)
        r = self.c.post("/cuenta/datos-personales/", {"acepto": "si", "next": "/avisos/"})
        self.assertRedirects(r, "/avisos/", fetch_redirect_response=False)
        self.emp.refresh_from_db()
        self.assertIsNotNone(self.emp.acepto_tratamiento_datos)
        a = AutorizacionDatos.objects.get(usuario=self.emp)
        self.assertIn("Empresa de prueba", a.texto)
        self.assertEqual(self.c.get("/avisos/").status_code, 200)

    def test_no_redirige_afuera(self):
        r = self.c.post("/cuenta/datos-personales/", {"acepto": "si", "next": "https://malo.example/"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)


class OperadoresTests(TenantTestCase):
    """Cuentas de operador en el panel /operador/: el operador nuevo recibe el enlace y queda con permisos de empresas y cursos."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-2"

    def setUp(self):
        ajuste = override_settings(EMAIL_BACKEND=CORREO)
        ajuste.enable()
        self.addCleanup(ajuste.disable)

    def peticion(self, usuario, esquema="public"):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        r = RequestFactory().post("/operador/", HTTP_HOST="gevalua.oatech.com.co")
        r.user, r.tenant, r.session = usuario, SimpleNamespace(schema_name=esquema, es_publica=esquema == "public"), {}
        r._messages = FallbackStorage(r)
        return r

    def test_crear_operador_envia_enlace_y_da_permisos(self):
        from django.contrib import admin as admin_django

        from .admin import OperadorAdmin, FormularioOperador
        from .models import Operador

        jefe = Usuario.objects.create_superuser("osvaldo@oatech.com.co", "clave-segura-123")
        ma = OperadorAdmin(Operador, admin_django.site)
        req = self.peticion(jefe)
        self.assertTrue(ma.has_add_permission(req))
        self.assertFalse(ma.has_add_permission(self.peticion(jefe, "demo")))  # solo en el panel común
        form = FormularioOperador({"email": "Gio@Consultoria.co", "nombre": "Gio", "is_active": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        ma.save_model(req, obj, form, change=False)
        gio = Usuario.objects.get(email="gio@consultoria.co")
        self.assertTrue(gio.is_staff)
        self.assertFalse(gio.is_superuser)
        self.assertTrue(gio.has_perm("clientes.add_empresa"))
        self.assertTrue(gio.has_perm("cursos.change_curso"))
        self.assertFalse(gio.has_perm("clientes.delete_empresa"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("operador", mail.outbox[0].body)
        self.assertIn("gevalua.oatech.com.co/cuenta/clave/", mail.outbox[0].body)
        self.assertFalse(ma.has_add_permission(self.peticion(gio)))  # solo un superusuario administra operadores

    def test_no_se_quita_su_propio_acceso(self):
        from django.contrib import admin as admin_django

        from .admin import OperadorAdmin, FormularioOperador
        from .models import Operador

        jefe = Usuario.objects.create_superuser("osvaldo@oatech.com.co", "clave-segura-123")
        ma = OperadorAdmin(Operador, admin_django.site)
        yo = Operador.objects.get(pk=jefe.pk)
        form = FormularioOperador({"email": yo.email, "nombre": "", "is_active": ""}, instance=yo)
        self.assertTrue(form.is_valid(), form.errors)
        ma.save_model(self.peticion(jefe), form.save(commit=False), form, change=True)
        jefe.refresh_from_db()
        self.assertTrue(jefe.is_active and jefe.is_superuser)
