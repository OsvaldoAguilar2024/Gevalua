"""A quién puede consultar cada usuario. Regla del alcance: «cualquier persona autorizada».

- Administrador: toda la empresa.
- Jefe: él mismo y su equipo en cascada.
- Consultor: lo que el administrador le habilitó (solo lectura), además de lo suyo si también es jefe.
- Empleado: solo lo suyo.
"""


def ids_visibles(usuario):
    """None = toda la empresa; si no, un conjunto de IDs de empleados."""
    if not usuario.is_authenticated:
        return set()
    if usuario.es_admin_empresa:
        return None
    ids = set()
    yo = getattr(usuario, "empleado", None)
    if yo is not None:
        ids.add(yo.pk)
        ids |= {e.pk for e in yo.subordinados()}
    if usuario.es_consultor:
        permiso = getattr(usuario, "permiso_consultor", None)
        if permiso is not None:
            habilitados = permiso.ids_empleados()
            if habilitados is None:
                return None
            ids |= habilitados
    return ids


def ids_como_consultor(usuario):
    """Solo lo habilitado por el permiso de consultor (None = toda la empresa)."""
    permiso = getattr(usuario, "permiso_consultor", None) if usuario.es_consultor else None
    if permiso is None:
        return set()
    return permiso.ids_empleados()


def puede_ver(usuario, empleado_id):
    ids = ids_visibles(usuario)
    return ids is None or empleado_id in ids
