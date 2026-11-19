from .models import Auditoria


def ip_de(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (reenviada.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def registrar(request, accion, objeto=None, detalle="", entidad=None):
    usuario = request.user if request and request.user.is_authenticated else None
    Auditoria.objects.create(
        usuario=usuario,
        accion=accion,
        entidad=entidad or (objeto._meta.verbose_name if objeto is not None else ""),
        entidad_id=str(objeto.pk) if objeto is not None and objeto.pk else "",
        detalle=detalle[:2000],
        ip=ip_de(request) if request else None,
    )
