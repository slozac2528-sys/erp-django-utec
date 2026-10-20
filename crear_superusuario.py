"""Crea o actualiza el superusuario del ERP a partir de variables de entorno.

Es idempotente: se puede ejecutar en cada deploy sin romper nada.
  - Si el usuario NO existe  -> lo crea.
  - Si el usuario YA existe  -> le restablece contraseña y permisos
                                (is_staff, is_superuser, is_active).

Variables de entorno (se configuran en el Dashboard de Render, NUNCA en Git):
    DJANGO_SUPERUSER_USERNAME   (obligatoria)
    DJANGO_SUPERUSER_PASSWORD   (obligatoria)
    DJANGO_SUPERUSER_EMAIL      (opcional)

Uso:
    python crear_superusuario.py
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()

if not username or not password:
    # No se aborta el deploy: solo se avisa en los logs.
    print('[SUPERUSER] OMITIDO: faltan DJANGO_SUPERUSER_USERNAME '
          'y/o DJANGO_SUPERUSER_PASSWORD en las variables de entorno.')
    sys.exit(0)

User = get_user_model()
usuario, creado = User.objects.get_or_create(
    username=username,
    defaults={'email': email},
)

usuario.is_staff = True
usuario.is_superuser = True
usuario.is_active = True
if email:
    usuario.email = email
usuario.set_password(password)
usuario.save()

accion = 'CREADO' if creado else 'ACTUALIZADO (contraseña y permisos)'
print(f"[SUPERUSER] Usuario '{username}' {accion}.")
