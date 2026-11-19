"""Plantillas genéricas de evaluación y escala común, según el documento de alcance."""

ESCALA = [
    (5, "Supera lo esperado", "Cumple más del 110 % de la meta o aporta algo adicional con evidencia"),
    (4, "Cumple plenamente", "Cumple entre 95 % y 110 %, con soportes completos y a tiempo"),
    (3, "Cumple parcialmente", "Cumple entre 75 % y 94 %, o con soportes incompletos o tardíos"),
    (2, "Por debajo de lo esperado", "Cumple entre 50 % y 74 %; requiere acción de mejora"),
    (1, "No cumple", "Menos del 50 % o sin evidencia; requiere acción de mejora obligatoria"),
]
OPCIONES_ESCALA = [(v, f"{v} · {n}") for v, n, _ in ESCALA]

# Por debajo de esta nota en un criterio, la plataforma exige una acción de mejora.
UMBRAL_ACCION_MEJORA = 3

RESULTADOS = [
    (4.5, "Sobresaliente"),
    (3.5, "Satisfactorio"),
    (2.5, "En mejora"),
    (0, "Insatisfactorio"),
]


def nivel_de(nota):
    for minimo, nombre in RESULTADOS:
        if nota >= minimo:
            return nombre
    return RESULTADOS[-1][1]


# (tipo, descripción, peso, evidencia)
PLANTILLAS = {
    "semanal": ("Semanal: chequeo de actividades", "Saber si las tareas de la semana se hicieron. Se responde en menos de 5 minutos.", [
        ("funciones", "Actividades de la semana realizadas (sí, no, parcial)", 60, "Reporte semanal o soporte de cada actividad"),
        ("cumplimiento", "Reporte y evidencias entregados a tiempo", 25, "Fecha de carga"),
        ("cumplimiento", "Bloqueos o novedades reportados", 15, "Comentario"),
    ]),
    "mensual": ("Mensual: seguimiento de metas", "Medir el avance de las metas del mes y dar retroalimentación.", [
        ("funciones", "Cumplimiento de metas del mes (indicadores)", 60, "Informe, reportes del sistema, documentos"),
        ("funciones", "Calidad del trabajo entregado", 15, "Visto bueno del jefe"),
        ("cumplimiento", "Cumplimiento de formatos, horarios y reportes semanales", 15, "Registro de entregas"),
        ("oportunidad", "Oportunidades aprovechadas (bono)", 10, "Soporte del negocio o logro"),
    ]),
    "trimestral": ("Trimestral: resultados y comportamiento", "Consolidar los tres meses y revisar competencias comportamentales.", [
        ("funciones", "Consolidado de metas del trimestre", 50, "Evaluaciones mensuales"),
        ("comportamental", "Trabajo en equipo y relación con el jefe", 15, "Observación del jefe"),
        ("comportamental", "Comunicación y actitud de servicio", 10, "Observación del jefe, quejas o felicitaciones"),
        ("cumplimiento", "Cumplimiento y disciplina", 15, "Registro del trimestre"),
        ("oportunidad", "Oportunidades aprovechadas (bono)", 10, "Soportes"),
    ]),
    "semestral": ("Semestral: desarrollo y plan de mejora", "Revisar el avance frente a las acciones de mejora y las necesidades de formación.", [
        ("funciones", "Consolidado de metas del semestre", 45, "Evaluaciones trimestrales"),
        ("comportamental", "Competencias comportamentales", 20, "Autoevaluación y evaluación del jefe"),
        ("cumplimiento", "Cierre de acciones de mejora pendientes", 15, "Estado de cada acción"),
        ("cumplimiento", "Cursos y certificaciones requeridos completados", 10, "Certificados de la plataforma"),
        ("oportunidad", "Oportunidades aprovechadas (bono)", 10, "Soportes"),
    ]),
    "anual": ("Anual: evaluación integral de desempeño", "Evaluación formal que alimenta decisiones de continuidad, ascenso o plan de mejora. Incluye autoevaluación y la firma de ambos.", [
        ("funciones", "Cumplimiento de metas del año", 45, "Evaluaciones del año"),
        ("funciones", "Competencias del cargo (conocimiento, calidad, iniciativa)", 15, "Observación y soportes"),
        ("comportamental", "Competencias comportamentales", 15, "Autoevaluación y jefe"),
        ("cumplimiento", "Cumplimiento del reglamento interno y disciplina", 10, "Registro anual"),
        ("cumplimiento", "Formación completada", 5, "Certificados"),
        ("oportunidad", "Oportunidades y aportes extraordinarios (bono)", 10, "Soportes"),
    ]),
}
