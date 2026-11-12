#!/bin/sh
# docker-entrypoint.sh
# Punto de entrada unificado para el contenedor ERP Django.
# IMPORTANTE: este archivo debe tener finales de línea LF (ver .gitattributes).
set -e

echo "==> [entrypoint] $(date +%T) Migraciones..."
python manage.py migrate --noinput

echo "==> [entrypoint] $(date +%T) Archivos estáticos..."
python manage.py collectstatic --noinput

echo "==> [entrypoint] $(date +%T) Verificando configuración..."
python manage.py check

echo "==> [entrypoint] $(date +%T) Verificando superusuario..."
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@email.com', '12345')"

echo "==> [entrypoint] $(date +%T) Iniciando Gunicorn en 0.0.0.0:${PORT:-8000}..."
exec gunicorn core.wsgi \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --log-file - \
    --access-logfile -