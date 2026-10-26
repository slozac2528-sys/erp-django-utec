# core/settings_prod.py
"""Configuración de producción — Render.com.

Hereda settings.py y sobreescribe lo necesario para producción.

Variables de entorno requeridas en Render (Environment):
    DJANGO_SETTINGS_MODULE  → core.settings_prod
    SECRET_KEY              → clave aleatoria de >= 50 caracteres
    DATABASE_URL            → URL de PostgreSQL (Internal Database URL de Render)
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
# Render inyecta RENDER_EXTERNAL_HOSTNAME automáticamente.
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
SECURE_PROXY_SSL_HEADER        = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT            = True
SECURE_HSTS_SECONDS            = 31536000    # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD            = True
SESSION_COOKIE_SECURE          = True
CSRF_COOKIE_SECURE             = True
X_FRAME_OPTIONS                = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF    = True
SECURE_REFERRER_POLICY         = 'same-origin'

# ── ARCHIVOS ESTÁTICOS ─────────────────────────────────────────────────────
# Django 4.2+: solo STORAGES. NO definir STATICFILES_STORAGE ni
# DEFAULT_FILE_STORAGE (son mutuamente excluyentes con STORAGES).
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

# ── LOGGING: solo WARNING y superiores ─────────────────────────────────────
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
        'django.security': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}