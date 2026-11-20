"""Texto de la autorización de tratamiento de datos personales (Ley 1581 de 2012 y Decreto 1377 de 2013).

PROVISIONAL: Gio lo valida como abogado antes de producción. Si el texto cambia, sube VERSION_POLITICA:
cada autorización guarda la versión y el texto exacto que la persona aceptó.
"""

VERSION_POLITICA = "2026-11-dvq-evalua"

TEXTO = """Autorizo a {empresa} (NIT {nit}), como responsable, para tratar mis datos personales en la plataforma DVQ-Evalua, que actúa como encargada del tratamiento, de acuerdo con la Ley 1581 de 2012 y sus decretos reglamentarios.

Finalidades: gestionar mi ingreso y mi expediente laboral; concertar, hacer seguimiento y evaluar mi desempeño; guardar las evidencias que cargue y las firmas electrónicas que haga; asignarme entrenamientos y emitir mis certificados; enviarme avisos por correo y notificaciones; y cumplir obligaciones legales y contractuales de la relación laboral.

Datos sensibles: entiendo que no estoy obligado a autorizar el tratamiento de datos sensibles (por ejemplo, datos de salud). Los exámenes médicos, antecedentes y hojas de vida solo los consulta talento humano, y cada consulta queda registrada.

Mis derechos: conocer, actualizar y rectificar mis datos; pedir prueba de esta autorización; ser informado del uso que se les da; presentar quejas ante la Superintendencia de Industria y Comercio; revocar la autorización o pedir la supresión de los datos cuando no exista un deber legal o contractual de conservarlos; y acceder gratis a mis datos. Puedo ejercerlos ante el área de talento humano o el administrador de {empresa}.

Declaro que leí esta autorización, que la entiendo y que la acepto de forma libre, previa, expresa e informada."""


def texto_autorizacion(empresa):
    return TEXTO.format(empresa=empresa.nombre, nit=empresa.nit)
