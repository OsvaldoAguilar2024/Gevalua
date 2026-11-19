from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El correo es obligatorio")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            usuario.set_password(password)
        else:
            usuario.set_unusable_password()
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._crear(email, password, **extra)


class Usuario(AbstractUser):
    """Usuario que entra con su correo.

    En el esquema público son los operadores de la plataforma (is_staff).
    En el esquema de cada empresa son sus empleados, con uno o varios roles.
    Todos son empleados; los demás roles se suman.
    """

    username = None
    email = models.EmailField("correo", unique=True)
    nombre = models.CharField("nombre completo", max_length=200, blank=True)
    documento = models.CharField("documento de identidad", max_length=20, blank=True)

    es_admin_empresa = models.BooleanField(
        "administrador de la empresa", default=False,
        help_text="Gerente o talento humano: configura la empresa y gestiona ingresos.",
    )
    es_jefe = models.BooleanField(
        "jefe / evaluador", default=False,
        help_text="Tiene equipo a cargo: concerta metas, revisa evidencias y califica.",
    )
    es_consultor = models.BooleanField(
        "consultor (solo lectura)", default=False,
        help_text="Auditor o asesor: consulta y exporta lo que el administrador le habilite.",
    )
    vista_preferida = models.CharField(
        max_length=10, choices=[("simple", "Simple"), ("completa", "Completa")], default="simple"
    )
    acepto_tratamiento_datos = models.DateTimeField(
        "aceptó la política de datos (Ley 1581)", null=True, blank=True
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["nombre", "email"]

    def __str__(self):
        return self.nombre or self.email

    def get_full_name(self):
        return self.nombre or self.email

    def get_short_name(self):
        return (self.nombre or self.email).split(" ")[0]

    @property
    def roles(self):
        roles = ["Empleado"]
        if self.es_jefe:
            roles.insert(0, "Jefe")
        if self.es_admin_empresa:
            roles.insert(0, "Administrador")
        if self.es_consultor:
            roles.append("Consultor")
        return roles

    @property
    def puede_ver_vista_completa(self):
        return self.es_admin_empresa or self.es_jefe or self.es_consultor
