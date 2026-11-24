# core/settings_prod.py
"""Configuración de producción — Render.com.

Hereda settings.py y sobreescribe lo necesario para producción.

Variables de entorno requeridas en Render (Environment):
    DJANGO_SETTINGS_MODULE  → core.settings_prod
    SECRET_KEY              → clave aleatoria de >= 50 caracteres
    DATABASE_URL            → URL de PostgreSQL (Internal Database URL de Render)
    SENDGRID_API_KEY        → API key de SendGrid con permiso Mail Send
    DEFAULT_FROM_EMAIL      → remitente verificado en SendGrid
Opcionales:
    ALLOWED_HOSTS           → dominios extra separados por coma
    DB_SSL_REQUIRE          → "False" solo para pruebas locales sin SSL
"""
import os

import dj_database_url

from .settings import *  # noqa: F401,F403  (hereda la configuración base)

# ── SEGURIDAD BÁSICA ───────────────────────────────────────────────────────
DEBUG = False
SECRET_KEY = os.environ['SECRET_KEY']   # falla a propósito si no existe

# ── HOSTS PERMITIDOS ───────────────────────────────────────────────────────
_render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
_extra_hosts = os.environ.get('ALLOWED_HOSTS', '').split(',')

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
ALLOWED_HOSTS += [h.strip() for h in _extra_hosts if h.strip()]

# ── BASE DE DATOS: PostgreSQL vía DATABASE_URL ─────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=os.environ.get('DB_SSL_REQUIRE', 'True') == 'True',
    )
}

# ── CSRF: dominios de confianza ────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = []
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_render_host}')
CSRF_TRUSTED_ORIGINS += [
    f'https://{h.strip()}' for h in _extra_hosts
    if h.strip() and not h.strip().startswith(('http://', 'https://'))
]

# ── HEADERS HTTP SEGUROS ───────────────────────────────────────────────────
# Render termina el SSL en su proxy. Sin SECURE_PROXY_SSL_HEADER,
# SECURE_SSL_REDIRECT provoca un bucle infinito de redirecciones.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000    # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

# ── ARCHIVOS ESTÁTICOS ─────────────────────────────────────────────────────
# Django 4.2+: solo STORAGES (no definir STATICFILES_STORAGE ni DEFAULT_FILE_STORAGE).
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

# ── LOGGING ────────────────────────────────────────────────────────────────
# CAMBIO: las apps del ERP registran INFO para ver el flujo de pago en Render.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[%(levelname)s] %(name)s: %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'catalogo': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'ventas': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django.security': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# ── CORREO (W17): SendGrid vía django-anymail ─────────────────────────────
# SENDGRID_API_KEY viene de settings.py. Si existe, usa SendGrid.
if SENDGRID_API_KEY:
    EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'

# ── ALMACENAMIENTO DE ARCHIVOS MEDIA (S3, opcional) ────────────────────────
# Solo se activa si AWS_STORAGE_BUCKET_NAME está definido en Render.
_bucket = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')

if _bucket:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    AWS_STORAGE_BUCKET_NAME = _bucket
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    MEDIA_URL = f'https://{_bucket}.s3.amazonaws.com/'