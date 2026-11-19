from datetime import date

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.cuentas.models import Usuario
from apps.nucleo.models import Auditoria

from .models import Area, Cargo, Empleado


def persona(email, jefe=None, **kw):
    u = Usuario.objects.create_user(email, "clave-segura-123", nombre=email.split("@")[0].title())
    return Empleado.objects.create(usuario=u, jefe=jefe, **kw)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EstructuraTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-7"

    def setUp(self):
        self.c = TenantClient(self.tenant)
        self.admin = Usuario.objects.create_user("admin@prueba.co", "clave-segura-123", es_admin_empresa=True)
        self.area = Area.objects.create(nombre="Comercial")
        self.cargo = Cargo.objects.create(area=self.area, nombre="Vendedor")

    def test_periodo_prueba_indefinido_dos_meses(self):
        e = persona("a@prueba.co", fecha_ingreso=date(2026, 1, 15))
        self.assertEqual(e.fin_periodo_prueba, date(2026, 3, 14))

    def test_periodo_prueba_fijo_corto_quinta_parte(self):
        e = persona("b@prueba.co", fecha_ingreso=date(2026, 1, 1), tipo_contrato="fijo", fin_contrato=date(2026, 4, 1))
        # 90 días de contrato -> 18 días de prueba
        self.assertEqual(e.fin_periodo_prueba, date(2026, 1, 18))

    def test_asignar_jefe_marca_rol(self):
        jefe = persona("jefe@prueba.co")
        persona("emp@prueba.co", jefe=jefe)
        jefe.usuario.refresh_from_db()
        self.assertTrue(jefe.usuario.es_jefe)

    def test_cascada_y_ciclos(self):
        gerente = persona("g@prueba.co")
        jefe = persona("j@prueba.co", jefe=gerente)
        emp = persona("e@prueba.co", jefe=jefe)
        self.assertEqual([x.pk for x in gerente.subordinados()], [jefe.pk, emp.pk])
        self.assertEqual([x.pk for x in gerente.subordinados(incluir_indirectos=False)], [jefe.pk])
        gerente.jefe = emp
        with self.assertRaises(ValidationError):
            gerente.full_clean()

    def test_solo_admin_entra_a_estructura(self):
        emp = persona("e@prueba.co")
        self.c.force_login(emp.usuario)
        self.assertEqual(self.c.get(reverse("estructura")).status_code, 403)
        self.c.force_login(self.admin)
        self.assertContains(self.c.get(reverse("estructura")), "Comercial")

    def test_crear_persona_envia_activacion_y_audita(self):
        self.c.force_login(self.admin)
        r = self.c.post(reverse("crear_empleado"), {
            "nombre": "Laura Gómez", "email": "Laura@Prueba.co", "documento": "123",
            "cargo": self.cargo.pk, "tipo_contrato": "indefinido", "estado": "activo",
            "fecha_ingreso": "2026-11-01",
        })
        self.assertEqual(r.status_code, 302)
        e = Empleado.objects.get(usuario__email="laura@prueba.co")
        self.assertEqual(e.cargo, self.cargo)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Auditoria.objects.filter(accion="crear", entidad_id=str(e.pk)).exists())
        # la persona puede activar su cuenta con el enlace
        self.assertTrue(e.usuario.has_usable_password())

    def test_correo_repetido(self):
        persona("laura@prueba.co")
        self.c.force_login(self.admin)
        r = self.c.post(reverse("crear_empleado"), {
            "nombre": "Otro", "email": "laura@prueba.co", "tipo_contrato": "indefinido", "estado": "activo",
        })
        self.assertContains(r, "Ya hay una persona con ese correo")

    def test_primer_admin_sin_ficha_se_completa_y_puede_ser_jefe(self):
        self.c.force_login(self.admin)
        r = self.c.get(reverse("empleados"))
        self.assertContains(r, "todavía no tiene ficha")
        inicial = self.c.get(reverse("crear_empleado") + "?email=admin@prueba.co").context["form"].initial
        self.assertTrue(inicial["es_admin_empresa"])  # el formulario trae sus roles marcados
        r = self.c.post(reverse("crear_empleado"), {
            "nombre": "Martha Salazar", "email": "admin@prueba.co", "es_admin_empresa": "on", "es_jefe": "on",
            "cargo": self.cargo.pk, "tipo_contrato": "indefinido", "estado": "activo",
        })
        self.assertEqual(r.status_code, 302)
        e = Empleado.objects.get(usuario=self.admin)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("clave-segura-123"))  # conserva su contraseña
        self.assertEqual(len(mail.outbox), 0)  # no se le manda otro enlace
        self.assertNotContains(self.c.get(reverse("empleados")), "todavía no tiene ficha")
        form = self.c.get(reverse("crear_empleado")).context["form"]
        self.assertIn(e, form.fields["jefe"].queryset)

    def test_admin_no_se_quita_su_propio_rol(self):
        self.c.force_login(self.admin)
        r = self.c.post(reverse("crear_empleado"), {
            "nombre": "Martha", "email": "admin@prueba.co", "cargo": self.cargo.pk, "tipo_contrato": "indefinido", "estado": "activo",
        })
        self.assertContains(r, "No puedes quitarte a ti mismo el rol de administrador")
        self.assertFalse(Empleado.objects.filter(usuario=self.admin).exists())

    def test_jefe_ve_solo_su_equipo(self):
        jefe = persona("jefe@prueba.co")
        persona("mio@prueba.co", jefe=jefe)
        persona("ajeno@prueba.co")
        jefe.usuario.refresh_from_db()
        self.c.force_login(jefe.usuario)
        r = self.c.get(reverse("organigrama"))
        self.assertContains(r, "Mio")
        self.assertNotContains(r, "Ajeno")
