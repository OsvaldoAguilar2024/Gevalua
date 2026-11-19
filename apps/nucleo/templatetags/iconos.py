"""Íconos de línea propios (SVG en línea) y avatares con iniciales."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

TRAZOS = {
    "inicio": "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    "panel": "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z",
    "estructura": "M9 3h6v4H9zM3 17h6v4H3zM15 17h6v4h-6zM12 7v5M6 17v-5h12v5",
    "ingreso": "M15 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM19 8v6M16 11h6",
    "periodos": "M4 6a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v14H4zM4 10h16M8 3v4M16 3v4",
    "equipo": "M16 20v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 20v-1a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
    "resultados": "M4 20V11M10 20V5M16 20v-6M21 20H3",
    "repositorio": "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
    "recordatorios": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
    "avisos": "M6 9a6 6 0 1 1 12 0c0 6 3 8 3 8H3s3-2 3-8M10.3 21a1.9 1.9 0 0 0 3.4 0",
    "salir": "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
    "menu": "M3 6h18M3 12h18M3 18h18",
    "check": "M20 6 9 17l-5-5",
    "alerta": "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
    "archivo": "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6",
    "meta": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
    "flecha": "M9 18l6-6-6-6",
    "estrella": "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z",
    "firma": "M3 17c3 0 4-6 6-6s1 6 4 6 3-3 5-3M3 21h18",
}


@register.simple_tag
def icono(nombre, clase="icono"):
    trazo = TRAZOS.get(nombre, TRAZOS["flecha"])
    return format_html(
        '<svg class="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{}"/></svg>',
        clase, mark_safe(trazo),
    )


@register.filter
def iniciales(texto):
    partes = [p for p in str(texto or "").replace("@", " ").split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


@register.filter
def tono(texto):
    """Color estable del avatar según el nombre (1 a 5)."""
    return sum(map(ord, str(texto or ""))) % 5 + 1
