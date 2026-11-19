# gevalua

Plataforma web para concertar metas con cada empleado, recoger las evidencias de su cumplimiento y evaluarlo (semanal, mensual, trimestral, semestral y anual), con ingreso y expediente digital del empleado. Pensada para empresas pequeñas y medianas en Colombia.

La fuente de verdad del producto es el documento *Plataforma de evaluación de desempeño: alcance del producto*.

## Arquitectura

| Pieza | Decisión |
|---|---|
| Aplicación | Django 5.2 con plantillas, un solo frontend responsivo mobile-first, instalable como PWA |
| Separación por empresa | `django-tenants`: un esquema de Postgres por empresa, elegido por subdominio (`cliente.g.oatech.com.co`) |
| Base de datos | Postgres en Railway |
| Archivos | Railway Storage Buckets (API S3, `django-storages`), bucket privado y URL firmada de 5 minutos |
| Correo | Resend con `django-anymail` |
| Panel del operador | Admin de Django en el dominio público, ruta `/operador/` |
| Despliegue | Docker en Railway (`railway.json`) |

### Espacios

- **Espacio común** (esquema `public`): registro de empresas (nombre, NIT, logo, plan), sus dominios y los operadores de la plataforma. Se entra por los dominios de `PUBLIC_DOMAINS` y por el dominio de Railway.
- **Espacio de cada empresa** (un esquema por empresa): usuarios, roles y, en la fase 1, estructura, ingresos, metas, evidencias y evaluaciones.

### Roles

Todos son empleados; los demás roles se suman en el mismo usuario.

| Rol | Campo | Ve |
|---|---|---|
| Administrador de la empresa | `es_admin_empresa` | Todo lo de su empresa, vista completa |
| Jefe / evaluador | `es_jefe` | Su equipo, vista completa para el equipo |
| Empleado | (todos) | Solo lo suyo, vista simple |
| Consultor | `es_consultor` | Lo que el administrador le habilite, solo lectura |
| Operador de la plataforma | `is_staff` en el esquema público | Panel `/operador/` para crear empresas |

## Desarrollo local

Requisitos: Python 3.13 y Postgres 16.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y ajusta DATABASE_URL
export $(grep -v '^#' .env | xargs)
python manage.py migrate_schemas
python manage.py asegurar_publico
python manage.py createsuperuser          # operador de la plataforma
python manage.py crear_empresa --nombre "Piloto SAS" --nit 900123456-7 \
  --subdominio piloto --admin-email gerente@piloto.co --dominio-extra piloto.localhost
python manage.py runserver
```

- Panel del operador: http://localhost:8000/operador/
- Empresa piloto: http://piloto.localhost:8000/ (el enlace de activación sale en la consola)

Pruebas: `python manage.py test`

## Crear una empresa piloto

Desde el panel del operador (`/operador/` → Empresas → Agregar): nombre, NIT, logo, subdominio y correo del primer administrador. La plataforma crea el esquema, registra `subdominio.g.oatech.com.co` y envía al administrador el enlace para crear su contraseña.

También por consola: `python manage.py crear_empresa --help`.

## Despliegue en Railway

El servicio se construye con el `Dockerfile` (en Railway, la configuración del servicio fija Dockerfile, pre-deploy `sh bin/predeploy.sh` y chequeo `/salud/`; `railway.json` queda como referencia). Antes de cada despliegue corre `migrate_schemas` (todas las empresas) y `asegurar_publico`. El chequeo de salud es `/salud/`.

Variables del servicio web:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | cadena aleatoria larga |
| `BASE_DOMAIN` | `g.oatech.com.co` (cada empresa en `<subdominio>.g.oatech.com.co`) |
| `PUBLIC_DOMAINS` | `gevalua.oatech.com.co` |
| `RESEND_API_KEY` | clave de Resend (la pone el dueño en Railway) |
| `DEFAULT_FROM_EMAIL` | `gevalua <no-responder@oatech.com.co>` |
| `AWS_S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL`, `AWS_DEFAULT_REGION` | referencias a las variables del bucket de Railway |

Variables opcionales de seguridad (por defecto encendidas):

| Variable | Valor por defecto | Para qué |
|---|---|---|
| `SEGUNDO_FACTOR_OBLIGATORIO` | `true` | Código por correo después de la contraseña para administradores de empresa y operadores |
| `SEGUNDO_FACTOR_EXENTOS` | `demo` | Esquemas sin segundo factor (la Empresa Demo usa correos que no existen) |
| `AUTORIZACION_DATOS_OBLIGATORIA` | `true` | Pantalla de autorización de datos personales (Ley 1581) al primer ingreso |

DNS: un registro comodín `*.g.oatech.com.co` hacia Railway evita registrar cada empresa por separado y no toca los demás subdominios de `oatech.com.co`. El panel queda en `gevalua.oatech.com.co`. Si cambia `BASE_DOMAIN`, `asegurar_publico` mueve los dominios de las empresas al nuevo patrón en el siguiente despliegue.

Nunca se guardan claves en el repositorio.

## Fases

- **Fase 0** (este código): base con esquemas, empresas piloto con nombre, NIT y logo, login por roles, vista simple y completa, PWA instalable, despliegue en Railway.
- **Fase 1**: empresa y estructura, ingreso y expediente con consulta de antecedentes asistida, concertación de metas, evidencias, revisión del jefe, evaluación mensual y anual, firma electrónica propia, repositorio básico, notificaciones push y correo, recordatorios, exportar a PDF y respaldos.
