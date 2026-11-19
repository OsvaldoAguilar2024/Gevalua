"""Lista genérica de requisitos de ingreso. Cada empresa la copia y la ajusta."""

# Fuentes oficiales para la consulta asistida de antecedentes. Las direcciones cambian sin aviso:
# se guardan en cada requisito y el administrador las puede corregir.
FUENTES = {
    "procuraduria": ("Procuraduría (disciplinarios)", "https://www.procuraduria.gov.co/Pages/Generacion-de-antecedentes.aspx"),
    "contraloria": ("Contraloría (fiscales)", "https://www.contraloria.gov.co/web/guest/persona-natural"),
    "policia": ("Policía (judiciales)", "https://antecedentes.policia.gov.co:7005/WebJudicial/"),
    "rnmc": ("Registro Nacional de Medidas Correctivas", "https://srvcnpc.policia.gov.co/PSC/frm_cnp_consulta.aspx"),
}

# (etapa, tipo, nombre, obligatorio, vigencia_dias, fuente)
REQUISITOS_GENERICOS = [
    ("seleccion", "autorizacion_datos", "Autorización de tratamiento de datos (Ley 1581)", True, None, ""),
    ("seleccion", "hoja_vida", "Hoja de vida", True, None, ""),
    ("seleccion", "antecedentes", "Antecedentes disciplinarios", True, 90, "procuraduria"),
    ("seleccion", "antecedentes", "Antecedentes fiscales", True, 90, "contraloria"),
    ("seleccion", "antecedentes", "Antecedentes judiciales", True, 90, "policia"),
    ("seleccion", "antecedentes", "Medidas correctivas", True, 90, "rnmc"),
    ("seleccion", "entrevista", "Entrevista", True, None, ""),
    ("precontrato", "examen_medico", "Examen médico de ingreso", True, None, ""),
    ("precontrato", "referencias", "Verificación de referencias", False, None, ""),
    ("contrato", "contrato", "Contrato firmado", True, None, ""),
    ("contrato", "certificacion_bancaria", "Certificación bancaria (máximo 30 días)", True, 30, ""),
    ("contrato", "afiliacion", "Afiliación a EPS", True, None, ""),
    ("contrato", "afiliacion", "Afiliación a pensión", True, None, ""),
    ("contrato", "afiliacion", "Afiliación a ARL", True, None, ""),
    ("contrato", "afiliacion", "Afiliación a caja de compensación", True, None, ""),
    ("contrato", "otro", "Vacunas o visas (si el cargo lo exige)", False, None, ""),
    ("poscontrato", "dotacion", "Entrega de equipos", False, None, ""),
    ("poscontrato", "dotacion", "Entrega de dotación", False, None, ""),
]
