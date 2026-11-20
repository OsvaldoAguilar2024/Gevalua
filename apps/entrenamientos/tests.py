import re
import shutil
import tempfile
from datetime import date

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from apps.cuentas.models import Usuario
from apps.cursos.models import Curso, Pregunta
from apps.estructura.models import Area, Cargo, Empleado

from .models import Asignacion, Certificado

MEDIA = tempfile.mkdtemp()


class EntrenamientosTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-3"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        ajuste = override_settings(MEDIA_ROOT=MEDIA, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.c = TenantClient(self.tenant)
        area = Area.objects.create(nombre="Bodega")
        self.cargo = Cargo.objects.create(area=area, nombre="Auxiliar de bodega")
        self.admin = Usuario.objects.create_user("admin@prueba.co", "clave-segura-123", es_admin_empresa=True, nombre="Ana Admin")
        Empleado.objects.create(usuario=self.admin)
        self.u1 = Usuario.objects.create_user("uno@prueba.co", "clave-segura-123", nombre="Uno Pérez", documento="111222333")
        self.e1 = Empleado.objects.create(usuario=self.u1, cargo=self.cargo)
        self.u2 = Usuario.objects.create_user("dos@prueba.co", "clave-segura-123", nombre="Dos Gómez")
        self.e2 = Empleado.objects.create(usuario=self.u2, cargo=self.cargo)
        self.curso = Curso.objects.create(titulo="Manejo seguro de montacargas", video_url="https://videos.ejemplo/m.mp4",
                                          horas=4, nota_minima=80, max_intentos=2, vigencia_meses=12, publicado=True,
                                          instructor="Carlos Instructor")
        for i in range(5):
            Pregunta.objects.create(curso=self.curso, orden=i, enunciado=f"Pregunta {i}", opcion_a="Sí", opcion_b="No",
                                    opcion_c="Tal vez", correcta="a")

    def asignar_por_cargo(self):
        self.c.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.c.post(reverse("asignar_curso", args=[self.curso.pk]), {"cargos": [self.cargo.pk], "fecha_limite": "2027-01-31"})
        self.assertEqual(r.status_code, 302)
        return Asignacion.objects.get(empleado=self.e1)

    def responder(self, asig, buenas):
        r = self.c.get(reverse("examen_curso", args=[asig.pk]))
        self.assertEqual(r.status_code, 200)
        ids = [int(x) for x in re.findall(r'name="p-(\d+)"', r.content.decode())]
        ids = list(dict.fromkeys(ids))
        datos = {f"p-{pid}": ("a" if n < buenas else "b") for n, pid in enumerate(ids)}
        return self.c.post(reverse("examen_curso", args=[asig.pk]), datos)

    def test_asignar_por_cargo_avisa_y_no_duplica(self):
        asig = self.asignar_por_cargo()
        self.assertEqual(Asignacion.objects.count(), 2)
        self.assertTrue(any("uno@prueba.co" in m.to for m in mail.outbox))
        self.asignar_por_cargo()
        self.assertEqual(Asignacion.objects.count(), 2)
        self.assertEqual(asig.fecha_limite, date(2027, 1, 31))

    def test_examen_se_habilita_con_el_video_y_certifica(self):
        asig = self.asignar_por_cargo()
        self.c.force_login(self.u1)
        self.assertContains(self.c.get("/"), "Manejo seguro de montacargas")
        r = self.c.get(reverse("examen_curso", args=[asig.pk]))
        self.assertRedirects(r, reverse("curso_asignado", args=[asig.pk]), fetch_redirect_response=False)
        self.c.post(reverse("avance_curso", args=[asig.pk]), {"pct": "95"})
        self.c.post(reverse("avance_curso", args=[asig.pk]), {"pct": "10"})  # no baja
        asig.refresh_from_db()
        self.assertEqual(asig.avance, 95)
        self.responder(asig, buenas=3)  # 60 %
        self.assertFalse(Certificado.objects.exists())
        self.responder(asig, buenas=5)  # 100 %
        cert = Certificado.objects.get()
        self.assertEqual((cert.nombre, cert.documento, cert.nota), ("Uno Pérez", "111222333", 100))
        self.assertIsNotNone(cert.vence)
        self.assertTrue(cert.archivo.read().startswith(b"%PDF"))
        # firman la gerente de DVQ SAS y el instructor del curso
        self.assertEqual((cert.responsable, cert.responsable_cargo, cert.responsable_entidad, cert.responsable_nit),
                         ("Diana Paola Varon Quintero", "Gerente", "DVQ SAS", "901509777-9"))
        self.assertEqual(cert.instructor, "Carlos Instructor")
        # verificación pública sin sesión
        r = TenantClient(self.tenant).get(reverse("verificar_certificado", args=[cert.codigo]))
        self.assertContains(r, "Certificado válido")
        self.assertContains(r, "Diana Paola Varon Quintero")
        self.assertContains(r, "Carlos Instructor")
        self.assertNotContains(r, "111222333")
        self.assertEqual(TenantClient(self.tenant).get("/verificar/NOEXISTE/").status_code, 404)

    def test_intentos_maximos_y_extra(self):
        asig = self.asignar_por_cargo()
        self.c.force_login(self.u1)
        self.c.post(reverse("avance_curso", args=[asig.pk]), {"pct": "100"})
        self.responder(asig, 0)
        self.responder(asig, 0)
        r = self.c.get(reverse("examen_curso", args=[asig.pk]))
        self.assertEqual(r.status_code, 302)  # sin intentos
        self.c.force_login(self.admin)
        self.c.post(reverse("intento_extra", args=[asig.pk]))
        asig.refresh_from_db()
        self.assertEqual(asig.intentos_restantes, 1)

    def test_otro_empleado_no_ve_ni_presenta(self):
        asig = self.asignar_por_cargo()
        self.c.force_login(self.u2)
        self.assertEqual(self.c.get(reverse("curso_asignado", args=[asig.pk])).status_code, 404)
        self.assertEqual(self.c.get(reverse("examen_curso", args=[asig.pk])).status_code, 404)
        self.assertEqual(self.c.get(reverse("catalogo_cursos")).status_code, 404)

    def test_seguimiento_y_excel(self):
        self.asignar_por_cargo()
        r = self.c.get(reverse("seguimiento_cursos"))
        self.assertContains(r, "Uno Pérez")
        r = self.c.get(reverse("seguimiento_cursos"), {"formato": "xlsx"})
        self.assertTrue(r["Content-Type"].startswith("application/vnd.openxmlformats"))
