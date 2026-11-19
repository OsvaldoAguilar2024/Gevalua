from django.http import Http404


def empleado_de(usuario):
    return getattr(usuario, "empleado", None)


def rol_en(concertacion, usuario):
    """'empleado', 'jefe', 'superior' (jefe en cascada), 'admin', 'consultor' (solo lectura) o None."""
    yo = empleado_de(usuario)
    if yo is not None:
        if concertacion.empleado_id == yo.pk:
            return "empleado"
        if concertacion.jefe_id == yo.pk:
            return "jefe"
        jefe = concertacion.jefe
        vistos = set()
        while jefe is not None and jefe.pk not in vistos:
            vistos.add(jefe.pk)
            if jefe.jefe_id == yo.pk:
                return "superior"
            jefe = jefe.jefe
    if usuario.es_admin_empresa:
        return "admin"
    if usuario.es_consultor:
        from apps.estructura.alcance import ids_como_consultor

        ids = ids_como_consultor(usuario)
        if ids is None or concertacion.empleado_id in ids:
            return "consultor"  # solo lectura: las acciones exigen 'jefe' o 'empleado'
    return None


def exigir_rol(concertacion, usuario, *roles):
    rol = rol_en(concertacion, usuario)
    if rol is None or (roles and rol not in roles):
        raise Http404
    return rol
