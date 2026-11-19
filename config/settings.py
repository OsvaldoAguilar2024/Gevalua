"""Configuración de gevalua.

Todo lo que cambia entre entornos se lee de variables de entorno (ver .env.example).
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def env_list(nombre, defecto=""):
    return [v.strip() for v in os.environ.get(nombre, defecto).split(",") if v.strip()]


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-inseguro-solo-local" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Falta la variable de entorno SECRET_KEY")

# Dominio base: cada empresa vive en <subdominio>.BASE_DOMAIN
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "oatech.com.co")
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")

# Dominios del espacio común (panel del operador). Se registran con `asegurar_publico`.
PUBLIC_DOMAINS = env_list("PUBLIC_DOMAINS", f"gevalua.{BASE_DOMAIN}")
if RAILWAY_PUBLIC_DOMAIN and RAILWAY_PUBLIC_DOMAIN not in PUBLIC_DOMAINS:
    PUBLIC_DOMAINS.append(RAILWAY_PUBLIC_DOMAIN)
if DEBUG:
    PUBLIC_DOMAINS += [d for d in ("localhost", "127.0.0.1") if d not in PUBLIC_DOMAINS]

ALLOWED_HOSTS = [f".{BASE_DOMAIN}", *PUBLIC_DOMAINS, *env_list("ALLOWED_HOSTS_EXTRA")]
if DEBUG:
    ALLOWED_HOSTS += [".localhost", "127.0.0.1", "testserver"]

CSRF_TRUSTED_ORIGINS = [f"https://*.{BASE_DOMAIN}"] + [f"https://{d}" for d in PUBLIC_DOMAINS]
if DEBUG:
    CSRF_TRUSTED_ORIGINS += ["http://*.localhost:8000", "http://localhost:8000"]

# --- Aplicaciones -----------------------------------------------------------
# Espacio común (esquema public): registro de empresas, operadores de la plataforma.
SHARED_APPS = [
    "django_tenants",
    "apps.clientes",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "apps.cuentas",
    "storages",
    "anymail",
]

# Espacio de cada empresa (un esquema de Postgres por empresa).
TENANT_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "apps.cuentas",
    "apps.nucleo",
    "apps.estructura",
    "apps.ingreso",
    "apps.firmas",
    "apps.desempeno",
]

INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

TENANT_MODEL = "clientes.Empresa"
TENANT_DOMAIN_MODEL = "clientes.Dominio"
PUBLIC_SCHEMA_NAME = "public"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"
ROOT_URLCONF = "config.urls"

MIDDLEWARE = [
    "apps.nucleo.middleware.SaludMiddleware",
    "apps.nucleo.middleware.EmpresaMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.nucleo.context_processors.empresa",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos ----------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="postgres://postgres@127.0.0.1:5433/gevalua",
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DATABASES["default"]["ENGINE"] = "django_tenants.postgresql_backend"
DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticación ----------------------------------------------------------
AUTH_USER_MODEL = "cuentas.Usuario"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 72  # el enlace de activación dura 3 días

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Idioma y zona horaria --------------------------------------------------
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --- Archivos ---------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Railway Storage Buckets (API S3). Si no hay bucket configurado se usa el disco local.
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_S3_BUCKET_NAME") or os.environ.get("BUCKET")
if AWS_STORAGE_BUCKET_NAME:
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("SECRET_ACCESS_KEY")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or os.environ.get("ENDPOINT")
    AWS_S3_REGION_NAME = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("REGION") or "auto"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True  # bucket privado: siempre URL firmada
    AWS_QUERYSTRING_EXPIRE = 300  # 5 minutos
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_ADDRESSING_STYLE = "virtual"
    _almacen_archivos = {"BACKEND": "storages.backends.s3.S3Storage"}
else:
    _almacen_archivos = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _almacen_archivos,
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

TAMANO_MAXIMO_SOPORTE_MB = 20

# --- Correo (Resend) --------------------------------------------------------
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", f"gevalua <no-responder@{BASE_DOMAIN}>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
if os.environ.get("RESEND_API_KEY"):
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
    ANYMAIL = {"RESEND_API_KEY": os.environ["RESEND_API_KEY"]}
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- Seguridad --------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
SECURE_REDIRECT_EXEMPT = [r"^salud/$"]
SESSION_COOKIE_AGE = 60 * 60 * 12

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
