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

    def firmar_como(self, usuario, conc, tipo="concertacion"):
        self.c.force_login(usuario)
        url = reverse("firmar", args=[tipo, conc.pk])
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


import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Evidencia

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class EvidenciasTests(ConcertacionTests):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def concertada(self):
        conc = Concertacion.objects.get(empleado=self.emp)
        self.firmar_como(self.jefe.usuario, conc)
        self.firmar_como(self.emp.usuario, conc)
        return conc

    def test_subir_revisar_devolver(self):
        conc = self.concertada()
        meta = conc.metas.first()
        self.c.force_login(self.emp.usuario)
        self.c.post(reverse("subir_evidencia", args=[meta.pk]), {
            "archivo": SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff", content_type="image/jpeg"), "comentario": "Reporte",
        })
        ev = Evidencia.objects.get()
        self.assertTrue(ev.archivo.name.startswith(f"empresa_{self.tenant.schema_name}/evidencias/"))
        # el jefe ve el pendiente en su inicio
        self.c.force_login(self.jefe.usuario)
        self.assertContains(self.c.get(reverse("inicio")), "Revisar 1 evidencia")
        # devolver exige comentario
        self.c.post(reverse("revisar_evidencia", args=[ev.pk, "devolver"]), {"comentario_jefe": ""})
        ev.refresh_from_db()
        self.assertEqual(ev.estado, Evidencia.Estado.PENDIENTE)
        self.c.post(reverse("revisar_evidencia", args=[ev.pk, "devolver"]), {"comentario_jefe": "Falta la firma del cliente"})
        ev.refresh_from_db()
        self.assertEqual(ev.estado, Evidencia.Estado.DEVUELTA)
        self.c.force_login(self.emp.usuario)
        self.assertContains(self.c.get(reverse("inicio")), "Corregir evidencia")

    def test_empleado_no_aprueba_lo_suyo_y_ajeno_no_descarga(self):
        conc = self.concertada()
        meta = conc.metas.first()
        self.c.force_login(self.emp.usuario)
        self.c.post(reverse("subir_evidencia", args=[meta.pk]), {"archivo": SimpleUploadedFile("a.pdf", b"%PDF")})
        ev = Evidencia.objects.get()
        self.assertEqual(self.c.post(reverse("revisar_evidencia", args=[ev.pk, "aprobar"])).status_code, 404)
        otro = persona("otro2@prueba.co")
        self.c.force_login(otro.usuario)
        self.assertEqual(self.c.get(reverse("descargar_evidencia", args=[ev.pk])).status_code, 404)

    def test_no_sube_antes_de_concertar(self):
        conc = Concertacion.objects.get(empleado=self.emp)
        self.c.force_login(self.emp.usuario)
        self.c.post(reverse("subir_evidencia", args=[conc.metas.first().pk]), {"enlace": "https://ejemplo.co/x"})
        self.assertFalse(Evidencia.objects.exists())


from decimal import Decimal

from .models import AccionMejora, Calificacion, Evaluacion


class CalculoNotaTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = "Empresa de prueba"
        tenant.nit = "900123456-9"

    def preparar(self, notas):
        jefe = persona("j@x.co")
        emp = persona("e@x.co", jefe=jefe)
        plantilla = Plantilla.copiar_generica("mensual")  # 60, 15, 15 y 10 de bono
        periodo = Periodo.objects.create(nombre="P", plantilla=plantilla, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31), fecha_limite=date(2026, 2, 5))
        c = Concertacion.objects.create(empleado=emp, jefe=jefe, periodo=periodo)
        c.crear_metas_desde_plantilla()
        for m, n in zip(c.metas.all(), notas):
            Calificacion.objects.create(meta=m, nota_jefe=n)
        return Evaluacion.objects.create(concertacion=c)

    def test_sin_oportunidades_se_reescala(self):
        ev = self.preparar([4, 4, 4, None])
        self.assertEqual(ev.calcular(), Decimal("4.00"))

    def test_bono_suma(self):
        ev = self.preparar([4, 4, 4, 5])
        self.assertEqual(ev.calcular(), Decimal("4.10"))

    def test_bono_bajo_no_resta(self):
        ev = self.preparar([4, 4, 4, 1])
        self.assertEqual(ev.calcular(), Decimal("4.00"))

    def test_niveles(self):
        from .catalogo import nivel_de

        self.assertEqual(nivel_de(Decimal("4.5")), "Sobresaliente")
        self.assertEqual(nivel_de(Decimal("4.49")), "Satisfactorio")
        self.assertEqual(nivel_de(Decimal("2.5")), "En mejora")
        self.assertEqual(nivel_de(Decimal("2.4")), "Insatisfactorio")


@override_settings(MEDIA_ROOT=MEDIA)
class EvaluacionFlujoTests(EvidenciasTests):
    def test_cierre_con_firma_y_pdf(self):
        conc = self.concertada()
        self.c.force_login(self.jefe.usuario)
        metas = list(conc.metas.all())
        datos = {"accion": "calificar"}
        for m in metas:
            datos[f"nota-{m.pk}"] = "2" if m == metas[0] else "4"
        self.c.post(reverse("evaluacion", args=[conc.pk]), datos)
        # nota 2 exige acción de mejora: aún no se puede firmar
        r = self.c.get(reverse("evaluacion", args=[conc.pk]))
        self.assertContains(r, "registra una acción de mejora")
        self.c.post(reverse("evaluacion", args=[conc.pk]), {
            "accion": "accion_mejora", "meta": metas[0].pk, "descripcion": "Plan de visitas semanal", "fecha_compromiso": "2027-02-01",
        })
        self.assertEqual(AccionMejora.objects.count(), 1)
        self.firmar_como(self.jefe.usuario, conc, "evaluacion")
        conc.refresh_from_db()
        self.assertEqual(conc.estado, Concertacion.Estado.CERRADA)
        ev = conc.evaluacion
        self.assertIsNotNone(ev.fecha_cierre)
        self.assertEqual(ev.nivel, "En mejora")  # (2*60 + 4*15 + 4*15) / 90 = 2.67 sin bono; con bono (240+40)/100 = 2.8
        # el empleado firma su evaluación
        self.firmar_como(self.emp.usuario, conc, "evaluacion")
        self.assertEqual(Firma.objects.filter(documento_tipo="evaluacion", documento_id=conc.pk).count(), 2)
        # PDF
        r = self.c.get(reverse("pdf_desempeno", args=["evaluacion", conc.pk]))
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        # resultados en cascada para el gerente
        self.c.force_login(self.gerente.usuario)
        r = self.c.get(reverse("resultados"))
        self.assertContains(r, str(ev.nota_final).replace(".", ","))


@override_settings(MEDIA_ROOT=MEDIA)
class ExcelTests(EvidenciasTests):
    """Exportación a Excel donde hay PDF: evaluación, concertación, resultados y repositorio."""

    def leer(self, r):
        from io import BytesIO

        from openpyxl import load_workbook

        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("application/vnd.openxmlformats"))
        self.assertIn(".xlsx", r["Content-Disposition"])
        return load_workbook(BytesIO(r.content))

    def test_excel_de_evaluacion_resultados_y_repositorio(self):
        conc = self.concertada()
        self.c.force_login(self.jefe.usuario)
        metas = list(conc.metas.all())
        datos = {"accion": "calificar", **{f"nota-{m.pk}": "4" for m in metas}}
        self.c.post(reverse("evaluacion", args=[conc.pk]), datos)
        self.firmar_como(self.jefe.usuario, conc, "evaluacion")
        self.c.force_login(self.jefe.usuario)
        wb = self.leer(self.c.get(reverse("excel_desempeno", args=["evaluacion", conc.pk])))
        self.assertEqual(wb.sheetnames, ["Resumen", "Metas", "Acciones de mejora", "Firmas"])
        textos = [c.value for fila in wb["Metas"].iter_rows() for c in fila]
        self.assertIn(metas[0].descripcion, textos)
        self.assertEqual(wb["Firmas"].max_row, 4)  # título, espacio, encabezado y la firma del jefe
        wb = self.leer(self.c.get(reverse("excel_desempeno", args=["concertacion", conc.pk])))
        self.assertIn("Metas", wb.sheetnames)
        self.c.force_login(self.gerente.usuario)
        wb = self.leer(self.c.get(reverse("resultados"), {"formato": "xlsx"}))
        nombres = [c.value for c in wb["Por persona"]["A"]]
        self.assertIn(self.emp.usuario.get_full_name(), nombres)
        wb = self.leer(self.c.get(reverse("repositorio"), {"tipo": "evaluacion", "formato": "xlsx"}))
        self.assertIn(self.emp.usuario.get_full_name(), [c.value for c in wb["Evaluaciones"]["A"]])

    def test_empleado_ajeno_no_descarga_excel(self):
        conc = self.concertada()
        from apps.cuentas.models import Usuario

        otro = Usuario.objects.create_user("otro@prueba.co", "clave-segura-123")
        self.c.force_login(otro)
        self.assertEqual(self.c.get(reverse("excel_desempeno", args=["evaluacion", conc.pk])).status_code, 404)
        self.assertEqual(self.c.get(reverse("resultados"), {"formato": "xlsx"}).status_code, 404)
