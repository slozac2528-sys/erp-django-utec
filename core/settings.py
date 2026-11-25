# core/settings.py
import sys
from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Variables de entorno ──────────────────────────────────────────────────
env = environ.Env(DEBUG=(bool, True))
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default='dev-key-insegura-solo-para-desarrollo')
DEBUG = env.bool('DEBUG', default=True)

# Render define RENDER_EXTERNAL_HOSTNAME automáticamente
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])
_render_host = env('RENDER_EXTERNAL_HOSTNAME', default=None)
if _render_host:
    ALLOWED_HOSTS.append(_render_host)

CSRF_TRUSTED_ORIGINS = []
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_render_host}')

# Render termina HTTPS en un proxy; Django necesita saberlo
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = False  # Render ya redirige a HTTPS

# ── Apps ──────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',   # debe ir ANTES de staticfiles
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Terceros
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'anymail',
    # Apps del ERP
    'clientes',
    'proveedores',
    'productos',
    'ventas',
    'reportes',
    'configuracion',
    'catalogo',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'core.urls'

# ── Templates ─────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'catalogo.context_processors.carrito_info',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ── Base de datos ─────────────────────────────────────────────────────────
# En producción, settings_prod.py sobrescribe esto con DATABASE_URL.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Internacionalización ──────────────────────────────────────────────────
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

# ── Archivos estáticos ────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

if DEBUG or 'test' in sys.argv:
    _static_backend = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    _static_backend = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': _static_backend},
}

# ── Archivos media ────────────────────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Autenticación ─────────────────────────────────────────────────────────
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/productos/'
LOGOUT_REDIRECT_URL = '/'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ── Allauth (desarrollo académico) ────────────────────────────────────────
ACCOUNT_LOGIN_METHODS = {'username'}
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_SESSION_REMEMBER = True

SITE_ID = 1

# ── DRF ───────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Stripe ────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='sk_test_placeholder')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', default='pk_test_placeholder')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='whsec_placeholder')

# ── Jazzmin ───────────────────────────────────────────────────────────────
JAZZMIN_SETTINGS = {
    'site_title': 'ERP Django',
    'site_header': 'ERP UTEC Celaya',
    'site_brand': 'ERP Django',
    'welcome_sign': 'Bienvenido al Sistema ERP · UTEC Celaya',
    'copyright': 'MC. Román Fernando López González · UTEC Celaya',
    'site_icon': None,
    'site_logo': None,
    'use_google_fonts_cdn': False,
    'search_model': ['clientes.Cliente', 'productos.Producto'],
    'topmenu_links': [
        {'name': 'Inicio ERP', 'url': '/', 'new_window': False},
        {'name': 'Productos', 'url': '/productos/'},
        {'name': 'Clientes', 'url': '/clientes/'},
        {'name': 'Ventas', 'url': '/ventas/'},
    ],
    'usermenu_links': [
        {'name': 'Ver ERP', 'url': '/', 'new_window': False},
    ],
    'order_with_respect_to': [
        'clientes', 'proveedores', 'productos',
        'ventas', 'configuracion', 'auth',
    ],
    'icons': {
        'auth': 'fas fa-users-cog',
        'auth.user': 'fas fa-user',
        'auth.Group': 'fas fa-users',
        'clientes.Cliente': 'fas fa-user-tie',
        'proveedores.Proveedor': 'fas fa-truck',
        'productos.Categoria': 'fas fa-tags',
        'productos.Producto': 'fas fa-box',
        'ventas.Venta': 'fas fa-file-invoice-dollar',
        'ventas.DetalleVenta': 'fas fa-list',
        'ventas.Pedido': 'fas fa-shopping-cart',
        'configuracion.ConfiguracionERP': 'fas fa-cogs',
    },
    'default_icon_parents': 'fas fa-folder',
    'default_icon_children': 'fas fa-circle',
    'related_modal_active': True,
    'show_sidebar': True,
    'navigation_expanded': True,
    'hide_apps': [],
    'hide_models': [],
    'changeform_format': 'horizontal_tabs',
    'language_chooser': False,
}

JAZZMIN_UI_TWEAKS = {
    'navbar_small_text': False,
    'footer_small_text': False,
    'body_small_text': False,
    'brand_small_text': False,
    'brand_colour': 'navbar-dark',
    'accent': 'accent-navy',
    'navbar': 'navbar-dark',
    'no_navbar_border': False,
    'navbar_fixed': False,
    'layout_boxed': False,
    'footer_fixed': False,
    'sidebar_fixed': False,
    'sidebar': 'sidebar-dark-navy',
    'sidebar_nav_small_text': False,
    'sidebar_disable_expand': False,
    'sidebar_nav_child_indent': True,
    'sidebar_nav_compact_style': False,
    'sidebar_nav_legacy_style': False,
    'sidebar_nav_flat_style': False,
    'theme': 'darkly',
    'button_classes': {
        'primary': 'btn-primary',
        'secondary': 'btn-secondary',
        'info': 'btn-info',
        'warning': 'btn-warning',
        'danger': 'btn-danger',
        'success': 'btn-success',
    },
}

# ── Redis / Celery ────────────────────────────────────────────────────────
# REDIS_URL definida  → tareas en cola (requiere worker de Celery corriendo).
# REDIS_URL vacía     → modo EAGER: .delay() ejecuta en el mismo proceso.
# CELERY_TASK_ALWAYS_EAGER puede forzarse desde el entorno (p. ej. en Render
# sin worker): CELERY_TASK_ALWAYS_EAGER=True
REDIS_URL = env('REDIS_URL', default='')

CELERY_BROKER_URL = REDIS_URL or 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL or 'cache+memory://'
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_TASK_ALWAYS_EAGER', default=not REDIS_URL)

CELERY_RESULT_EXPIRES = 3600
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_SOFT_TIME_LIMIT = 300
CELERY_TASK_TIME_LIMIT = 360
CELERY_TASK_DEFAULT_QUEUE = 'erp_django'
CELERY_TASK_EAGER_PROPAGATES = True

CELERY_BEAT_SCHEDULE = {
    'verificar-stock-bajo-cada-hora': {
        'task': 'ventas.verificar_stock_bajo',
        'schedule': timedelta(hours=1),
        'args': (5,),
        'options': {'queue': 'erp_django'},
    },
    'reporte-ventas-diario-8am': {
        'task': 'ventas.reporte_ventas_diario',
        'schedule': crontab(hour=8, minute=0),
        'options': {'queue': 'erp_django'},
    },
}
CELERY_BEAT_TIMEZONE = TIME_ZONE

# ── Correo electrónico ────────────────────────────────────────────────────
# Con SENDGRID_API_KEY  → SendGrid vía django-anymail.
# Sin SENDGRID_API_KEY  → consola (los correos solo aparecen en los logs).
# EMAIL_BACKEND puede sobrescribirse desde el entorno.
SENDGRID_API_KEY = env('SENDGRID_API_KEY', default='')

if SENDGRID_API_KEY:
    _email_backend_default = 'anymail.backends.sendgrid.EmailBackend'
else:
    _email_backend_default = 'django.core.mail.backends.console.EmailBackend'

EMAIL_BACKEND = env('EMAIL_BACKEND', default=_email_backend_default)

ANYMAIL = {
    'SENDGRID_API_KEY': SENDGRID_API_KEY,
}

# Remitente: debe coincidir con un Sender verificado en SendGrid
DEFAULT_FROM_EMAIL = env(
    'DEFAULT_FROM_EMAIL',
    default='ERP Django <noreply@erp-django.com>',
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_SUBJECT_PREFIX = '[ERP Django] '

ADMINS = [
    ('Admin ERP', env('ADMIN_EMAIL', default='admin@erp-django.com')),
]

# Destinatarios del reporte diario de ventas (separados por coma en el entorno)
REPORTE_VENTAS_DESTINATARIOS = env.list(
    'REPORTE_VENTAS_DESTINATARIOS',
    default=[env('ADMIN_EMAIL', default='admin@erp-django.com')],
)

# URL pública para los enlaces de correos (las tareas Celery no tienen request)
SITE_URL = env(
    'SITE_URL',
    default=env('RENDER_EXTERNAL_URL', default='http://127.0.0.1:8000'),
).rstrip('/')