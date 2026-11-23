import os
from django.contrib.auth import get_user_model

Usuario = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
password = os.environ['DJANGO_SUPERUSER_PASSWORD']

user, created = Usuario.objects.get_or_create(
    username=username,
    defaults={'email': email},
)
user.email = email
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.set_password(password)
user.save()

print('[superusuario]', 'creado' if created else 'actualizado', username)