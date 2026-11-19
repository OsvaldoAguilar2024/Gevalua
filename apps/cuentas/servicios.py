"""Alta de usuarios dentro del esquema de una empresa."""

import secrets

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django_tenants.utils import tenant_context

from .models import Usuario


def dominio_principal(empresa):
    dominio = empresa.domains.filter(is_primary=True).first() or empresa.domains.first()
    return dominio.domain if dominio else f"{empresa.schema_name}.{settings.BASE_DOMAIN}"


def enviar_correo_activacion(empresa, usuario):
    """Envía el enlace para que el usuario cree su contraseña."""
    formulario = PasswordResetForm({"email": usuario.email})
    formulario.is_valid()
    formulario.save(
        domain_override=dominio_principal(empresa),
        use_https=not settings.DEBUG,
        subject_template_name="registration/correo_activacion_asunto.txt",
        email_template_name="registration/correo_activacion.txt",
        extra_email_context={"empresa": empresa},
    )


def crear_administrador(empresa, email, nombre="", enviar_correo=True):
    """Crea (o promueve) el primer administrador de una empresa en su esquema."""
    with tenant_context(empresa):
        usuario, creado = Usuario.objects.get_or_create(
            email=email.strip().lower(), defaults={"nombre": nombre}
        )
        if creado:
            # Clave aleatoria que nadie conoce: el usuario crea la suya con el enlace del correo.
            usuario.set_password(secrets.token_urlsafe(32))
        usuario.es_admin_empresa = True
        usuario.es_jefe = True
        usuario.save()
        if enviar_correo:
            enviar_correo_activacion(empresa, usuario)
    return usuario
