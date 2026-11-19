"""Crea la Empresa Demo con datos de ejemplo para mostrar la plataforma.

Los usuarios de demo entran con la contraseña de la variable DEMO_CLAVE (nunca se escribe en el código).
Es idempotente: si la empresa ya existe, no hace nada (usa --reiniciar para borrarla y crearla de nuevo).
"""

import os
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.clientes.models import Dominio, Empresa

SUB = "demo"


# Los correos de demo no dependen del dominio de entrada, para no cambiar los usuarios existentes.
CORREO_DEMO = "demo.oatech.com.co"


class Command(BaseCommand):
    help = "Crea la Empresa Demo (demo.<BASE_DOMAIN>) con datos de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument("--reiniciar", action="store_true", help="borra la Empresa Demo y la crea de nuevo")

    def handle(self, *args, **o):
        existente = Empresa.objects.filter(schema_name=SUB).first()
        if existente and not o["reiniciar"]:
            self.stdout.write("La Empresa Demo ya existe; no se cambia nada.")
            return
        clave = os.environ.get("DEMO_CLAVE", "")
        if len(clave) < 10:
            raise CommandError("Define DEMO_CLAVE (mínimo 10 caracteres) para crear los usuarios de demo.")
        if existente:
            existente.auto_drop_schema = True
            existente.delete(force_drop=True)
        empresa = Empresa(schema_name=SUB, nombre="Empresa Demo", nit="000000000", industria="Comercio y servicios", tamano="pequena")
        empresa.save()
        Dominio.objects.create(tenant=empresa, domain=f"{SUB}.{settings.BASE_DOMAIN}", is_primary=True)
        with tenant_context(empresa):
            Datos(clave).crear()
        connection.set_schema_to_public()
        self.stdout.write(self.style.SUCCESS(f"Empresa Demo lista en https://{SUB}.{settings.BASE_DOMAIN}"))


class Datos:
    def __init__(self, clave):
        self.clave = clave
        self.hoy = timezone.localdate()

    @transaction.atomic
    def crear(self):
        from apps.cuentas.models import Usuario
        from apps.estructura.models import Area, Cargo, Empleado

        U = Usuario
        dominio = CORREO_DEMO

        def usuario(local, nombre, doc, **roles):
            u = U(email=f"{local}@{dominio}", nombre=nombre, documento=doc, acepto_tratamiento_datos=timezone.now(), **roles)
            u.set_password(self.clave)
            u.save()
            return u

        gerencia = Area.objects.create(nombre="Gerencia")
        comercial = Area.objects.create(nombre="Comercial")
        admin_area = Area.objects.create(nombre="Administrativa y contable")
        operacion = Area.objects.create(nombre="Operación")
        c_gerente = Cargo.objects.create(area=gerencia, nombre="Gerente general", funciones="Dirigir la empresa, aprobar presupuestos y velar por el cumplimiento de metas.", competencias="Liderazgo, planeación, negociación.")
        c_th = Cargo.objects.create(area=admin_area, nombre="Coordinadora de talento humano", funciones="Selección, contratación, afiliaciones, nómina y bienestar.", competencias="Organización, confidencialidad, servicio.")
        c_jcom = Cargo.objects.create(area=comercial, nombre="Jefe comercial", funciones="Liderar el equipo de ventas y cumplir el presupuesto mensual.", competencias="Liderazgo, negociación, orientación al logro.")
        c_asesor = Cargo.objects.create(area=comercial, nombre="Asesor comercial", funciones="Visitar clientes, cotizar y cerrar ventas; registrar cada visita.", competencias="Comunicación, persistencia, servicio al cliente.")
        c_cont = Cargo.objects.create(area=admin_area, nombre="Auxiliar contable", funciones="Causación, conciliaciones bancarias y presentación de impuestos a tiempo.", competencias="Precisión, manejo de Excel, ética.")
        c_jop = Cargo.objects.create(area=operacion, nombre="Jefe de operación", funciones="Programar despachos, controlar inventario y seguridad en bodega.", competencias="Planeación, liderazgo, seguridad.")
        c_aux = Cargo.objects.create(area=operacion, nombre="Auxiliar de bodega", funciones="Alistar pedidos, recibir mercancía y mantener el orden de la bodega.", competencias="Responsabilidad, trabajo en equipo.")

        ingreso = self.hoy - timedelta(days=400)
        gerente = Empleado.objects.create(usuario=usuario("gerente", "Andrea Morales", "52100200", es_admin_empresa=True, es_jefe=True), cargo=c_gerente, fecha_ingreso=ingreso)
        th = Empleado.objects.create(usuario=usuario("talento", "Carolina Rincón", "1015200300", es_admin_empresa=True), cargo=c_th, jefe=gerente, fecha_ingreso=ingreso)
        jcom = Empleado.objects.create(usuario=usuario("jefe", "Julián Pardo", "80300400", es_jefe=True), cargo=c_jcom, jefe=gerente, fecha_ingreso=ingreso)
        jop = Empleado.objects.create(usuario=usuario("operacion", "Mauricio Vega", "79400500", es_jefe=True), cargo=c_jop, jefe=gerente, fecha_ingreso=ingreso)
        laura = Empleado.objects.create(usuario=usuario("empleado", "Laura Gómez", "1020500600"), cargo=c_asesor, jefe=jcom, fecha_ingreso=ingreso)
        pedro = Empleado.objects.create(usuario=usuario("pedro", "Pedro Ruiz", "1030600700"), cargo=c_asesor, jefe=jcom, fecha_ingreso=self.hoy - timedelta(days=200), tipo_contrato="fijo", fin_contrato=self.hoy + timedelta(days=20))
        diana = Empleado.objects.create(usuario=usuario("diana", "Diana Castro", "1040700800"), cargo=c_cont, jefe=th, fecha_ingreso=ingreso)
        nuevo = Empleado.objects.create(usuario=usuario("camilo", "Camilo Torres", "1050800900"), cargo=c_aux, jefe=jop, fecha_ingreso=self.hoy - timedelta(days=50))
        usuario("consultor", "Asesor externo (consultor)", "", es_consultor=True)
        self.empleados = dict(gerente=gerente, th=th, jcom=jcom, jop=jop, laura=laura, pedro=pedro, diana=diana, nuevo=nuevo)
        self.ingresos(c_asesor, c_aux, th.usuario)
        self.desempeno()

    def ingresos(self, c_asesor, c_aux, quien):
        from apps.ingreso.models import Etapa, ProcesoIngreso

        def avanzar_hasta(p, etapa, completar_actual=False):
            orden = [e.value for e in Etapa]
            for r in p.requisitos.all():
                if orden.index(r.etapa) < orden.index(etapa) or (completar_actual and r.etapa == etapa):
                    r.estado = "verificado" if r.obligatorio else "pendiente"
                    r.observacion = "Documento revisado (demo)." if r.obligatorio else ""
                    r.fecha_documento = self.hoy - timedelta(days=5) if r.vigencia_dias else None
                    r.verificado_por, r.verificado_en = quien, timezone.now()
                    r.save()
            p.etapa = etapa
            p.save(update_fields=["etapa"])

        p1 = ProcesoIngreso.objects.create(candidato_nombre="Sofía Herrera", candidato_documento="1060900100", candidato_email="sofia@correo.co", cargo=c_asesor, creado_por=quien)
        r = p1.requisitos.get(tipo="autorizacion_datos")
        r.estado, r.observacion, r.verificado_por, r.verificado_en = "verificado", "Autorización firmada (demo).", quien, timezone.now()
        r.save()
        hv = p1.requisitos.get(tipo="hoja_vida")
        hv.estado, hv.observacion = "cargado", "Hoja de vida recibida por correo (demo)."
        hv.save()
        p2 = ProcesoIngreso.objects.create(candidato_nombre="Andrés Molina", candidato_documento="1070100200", cargo=c_aux, creado_por=quien)
        avanzar_hasta(p2, Etapa.CONTRATO)
        banc = p2.requisitos.get(tipo="certificacion_bancaria")
        banc.estado, banc.fecha_documento, banc.observacion = "verificado", self.hoy - timedelta(days=35), "Certificación vencida: pedir una nueva (demo)."
        banc.save()
        p3 = ProcesoIngreso.objects.create(candidato_nombre="Camilo Torres", candidato_documento="1050800900", cargo=c_aux, creado_por=quien)
        avanzar_hasta(p3, Etapa.POSCONTRATO)
        p3.estado, p3.empleado = "contratado", self.empleados["nuevo"]
        p3.save()

    def desempeno(self):
        from apps.desempeno.models import AccionMejora, Calificacion, Concertacion, Evaluacion, Evidencia, Periodo, Plantilla
        from apps.firmas.models import Firma
        from apps.firmas.servicios import TEXTO_ACEPTACION, huella

        mensual = Plantilla.copiar_generica("mensual")
        Plantilla.copiar_generica("anual")
        e = self.empleados
        equipo = [e["th"], e["jcom"], e["jop"], e["laura"], e["pedro"], e["diana"], e["nuevo"]]
        primero_mes = self.hoy.replace(day=1)
        fin_anterior = primero_mes - timedelta(days=1)
        inicio_anterior = fin_anterior.replace(day=1)
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        siguiente = (primero_mes + timedelta(days=32)).replace(day=1)
        anterior = Periodo.objects.create(nombre=f"{meses[inicio_anterior.month - 1].capitalize()} {inicio_anterior.year}", plantilla=mensual,
                                          fecha_inicio=inicio_anterior, fecha_fin=fin_anterior, fecha_limite=fin_anterior + timedelta(days=5))
        actual = Periodo.objects.create(nombre=f"{meses[primero_mes.month - 1].capitalize()} {primero_mes.year}", plantilla=mensual,
                                        fecha_inicio=primero_mes, fecha_fin=siguiente - timedelta(days=1), fecha_limite=siguiente + timedelta(days=4))

        metas_por_cargo = {
            "Asesor comercial": ("Ventas del mes", "Ventas facturadas (COP)", "$45.000.000"),
            "Jefe comercial": ("Presupuesto comercial del equipo", "Cumplimiento del presupuesto", "100 %"),
            "Auxiliar contable": ("Impuestos y conciliaciones a tiempo", "Declaraciones presentadas a tiempo", "100 %"),
            "Coordinadora de talento humano": ("Afiliaciones y nómina sin errores", "Novedades procesadas a tiempo", "100 %"),
            "Jefe de operación": ("Despachos a tiempo", "Pedidos despachados en 24 h", "95 %"),
            "Auxiliar de bodega": ("Alistamiento sin errores", "Pedidos alistados sin devolución", "98 %"),
        }
        notas_anteriores = {"th": [4, 4, 5, 0], "jcom": [4, 4, 4, 5], "jop": [3, 4, 4, 0], "laura": [5, 4, 4, 5], "pedro": [2, 3, 3, 0], "diana": [4, 5, 4, 0], "nuevo": [4, 4, 3, 0]}

        def firmar(doc_tipo, c, usuario, calidad, contenido, titulo):
            Firma.objects.create(documento_tipo=doc_tipo, documento_id=c.pk, firmante=usuario, firmante_nombre=usuario.get_full_name(),
                                 firmante_documento=usuario.documento, firmante_email=usuario.email, calidad=calidad,
                                 huella_documento=huella(contenido), texto_aceptacion=TEXTO_ACEPTACION.format(titulo=titulo, email=usuario.email),
                                 ip="127.0.0.1", agente="Datos de demo", proveedor_ref="demo")

        def concertar(periodo, emp, firmar_ambos=True):
            c = Concertacion.objects.create(empleado=emp, jefe=emp.jefe, periodo=periodo)
            c.crear_metas_desde_plantilla()
            desc, ind, obj = metas_por_cargo[emp.cargo.nombre]
            m = c.metas.order_by("orden").first()
            m.descripcion, m.indicador, m.valor_objetivo = desc, ind, obj
            m.save()
            if firmar_ambos:
                c.estado, c.aceptada_jefe, c.aceptada_empleado = Concertacion.Estado.ACEPTADA, timezone.now(), timezone.now()
                c.save()
                contenido = c.contenido_firmable()
                firmar("concertacion", c, emp.jefe.usuario, "Jefe", contenido, c.titulo)
                firmar("concertacion", c, emp.usuario, "Empleado", contenido, c.titulo)
            return c

        clave_por_emp = {v.pk: k for k, v in e.items()}
        for emp in equipo:
            c = concertar(anterior, emp)
            notas = notas_anteriores[clave_por_emp[emp.pk]]
            for meta, nota in zip(c.metas.order_by("orden"), notas):
                Evidencia.objects.create(meta=meta, subida_por=emp.usuario, comentario=f"Soporte de {meta.descripcion.lower()} (demo).",
                                         enlace="https://ejemplo.com/reporte-demo.pdf", estado="aprobada", revisada_por=emp.jefe.usuario, revisada_en=timezone.now())
                Calificacion.objects.create(meta=meta, nota_jefe=nota or None, autoevaluacion=min(5, (nota or 3) + (1 if nota and nota < 4 else 0)) if nota else None,
                                            comentario="Cumplió con soportes completos." if nota and nota >= 4 else ("Debe mejorar el seguimiento." if nota else ""))
            ev = Evaluacion.objects.create(concertacion=c, fortalezas="Compromiso y buena relación con el equipo.",
                                           aspectos_mejorar="Entregar los reportes semanales a tiempo." if clave_por_emp[emp.pk] == "pedro" else "",
                                           recomendacion="plan_mejora" if clave_por_emp[emp.pk] == "pedro" else "continuidad")
            if clave_por_emp[emp.pk] == "pedro":
                AccionMejora.objects.create(evaluacion=ev, meta=c.metas.order_by("orden").first(), responsable=emp,
                                            descripcion="Agenda semanal de visitas con seguimiento del jefe cada lunes.", fecha_compromiso=self.hoy + timedelta(days=30))
            nota = ev.calcular()
            from apps.desempeno.catalogo import nivel_de

            ev.nota_final, ev.nivel, ev.fecha_cierre = nota, nivel_de(nota), timezone.now() - timedelta(days=3)
            ev.save()
            c.estado = Concertacion.Estado.CERRADA
            c.save(update_fields=["estado"])
            from apps.desempeno.views_evaluacion import contenido_evaluacion

            contenido = contenido_evaluacion(c, ev)
            firmar("evaluacion", c, emp.jefe.usuario, "Jefe", contenido, f"Evaluación {c.periodo} · {emp}")
            if clave_por_emp[emp.pk] != "laura":  # Laura tiene su firma pendiente, para mostrar el flujo
                firmar("evaluacion", c, emp.usuario, "Empleado", contenido, f"Evaluación {c.periodo} · {emp}")
        # El periodo anterior queda abierto para que Laura vea su firma pendiente en la vista simple.

        # Periodo actual: concertaciones en distintos estados.
        for emp in equipo:
            clave = clave_por_emp[emp.pk]
            if clave == "laura":
                c = concertar(actual, emp, firmar_ambos=False)
                c.estado, c.aceptada_jefe = Concertacion.Estado.POR_ACEPTAR, timezone.now()
                c.save()
                firmar("concertacion", c, emp.jefe.usuario, "Jefe", c.contenido_firmable(), c.titulo)
            elif clave == "nuevo":
                concertar(actual, emp, firmar_ambos=False)  # en preparación por su jefe
            else:
                c = concertar(actual, emp)
                metas = list(c.metas.order_by("orden"))
                Evidencia.objects.create(meta=metas[0], subida_por=emp.usuario, comentario="Avance de la primera quincena (demo).",
                                         enlace="https://ejemplo.com/avance-demo.xlsx", estado="aprobada", revisada_por=emp.jefe.usuario, revisada_en=timezone.now())
                if clave == "pedro":
                    Evidencia.objects.create(meta=metas[2], subida_por=emp.usuario, comentario="Reporte semanal.", estado="devuelta",
                                             comentario_jefe="Falta el reporte de la semana 2.", revisada_por=emp.jefe.usuario, revisada_en=timezone.now())
                if clave in ("diana", "th"):
                    Evidencia.objects.create(meta=metas[1], subida_por=emp.usuario, comentario="Conciliación bancaria del mes (demo).", estado="pendiente")
