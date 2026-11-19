"""Exportación a Excel (.xlsx) con openpyxl: una o varias hojas con encabezado, filtros y anchos ajustados."""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _valor(v):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return timezone.localtime(v).replace(tzinfo=None) if timezone.is_aware(v) else v
    if isinstance(v, (int, float, date, str)):
        return v
    return str(v)


def libro(hojas, titulo=""):
    """hojas: lista de (nombre, encabezados, filas). Devuelve los bytes del .xlsx."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    negrita = Font(bold=True, color="FFFFFF")
    fondo = PatternFill("solid", fgColor="2F59BB")
    for nombre, encabezados, filas in hojas:
        ws = wb.create_sheet(nombre[:31] or "Hoja")
        inicio = 1
        if titulo:
            ws.cell(row=1, column=1, value=titulo).font = Font(bold=True, size=12)
            inicio = 3
        for col, enc in enumerate(encabezados, 1):
            c = ws.cell(row=inicio, column=col, value=enc)
            c.font, c.fill, c.alignment = negrita, fondo, Alignment(vertical="center", wrap_text=True)
        anchos = [len(str(e)) for e in encabezados]
        n = 0
        for n, fila in enumerate(filas, 1):
            for col, v in enumerate(fila, 1):
                v = _valor(v)
                c = ws.cell(row=inicio + n, column=col, value=v)
                if isinstance(v, datetime):
                    c.number_format = "dd/mm/yyyy hh:mm"
                elif isinstance(v, date):
                    c.number_format = "dd/mm/yyyy"
                if col <= len(anchos):
                    anchos[col - 1] = max(anchos[col - 1], min(len(str(v)), 60))
        for col, ancho in enumerate(anchos, 1):
            ws.column_dimensions[get_column_letter(col)].width = ancho + 2
        ws.freeze_panes = ws.cell(row=inicio + 1, column=1)
        if encabezados:
            ws.auto_filter.ref = f"A{inicio}:{get_column_letter(len(encabezados))}{inicio + max(n, 1)}"
    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()


def respuesta(nombre, hojas, titulo=""):
    r = HttpResponse(libro(hojas, titulo), content_type=TIPO_XLSX)
    r["Content-Disposition"] = f'attachment; filename="{slugify(nombre) or "exportacion"}.xlsx"'
    return r
