#!/bin/sh
# docker-entrypoint.sh
# Punto de entrada unificado para el contenedor ERP Django.
# IMPORTANTE: este archivo debe tener finales de línea LF (ver .gitattributes).
set -e

# ── W16 (cambio 1): si se recibe un comando, ejecutarlo tal cual ─────
# Ej.: docker-compose `command: celery -A core worker ...` o el
# "Docker Command" de un Background Worker en Render.
# Sin argumentos → flujo normal del servicio web (migrar + gunicorn).
if [ "$#" -gt 0 ]; then
    echo "==> [entrypoint] $(date +%T) Ejecutando comando: $*"
    exec "$@"
fi

echo "==> [entrypoint] $(date +%T) Migraciones..."
python manage.py migrate --noinput

echo "==> [entrypoint] $(date +%T) Archivos estáticos..."
python manage.py collectstatic --noinput

echo "==> [entrypoint] $(date +%T) Verificando configuración..."
python manage.py check

echo "==> [entrypoint] $(date +%T) Verificando superusuario..."
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@email.com', '12345')"

# ── W16 (cambio 2): worker de Celery embebido (opción gratuita) ──────
# Render Free no ofrece Background Workers: el worker corre en segundo
# plano dentro del mismo contenedor que Gunicorn.
#   --pool=solo                       → un solo proceso (cabe en 512 MB)
#   --without-gossip/mingle/heartbeat → menos conexiones al Key Value Free
# Se activa con CELERY_EMBEDDED_WORKER=1 y requiere REDIS_URL.
if [ "${CELERY_EMBEDDED_WORKER:-0}" = "1" ] && [ -n "${REDIS_URL:-}" ]; then
    echo "==> [entrypoint] $(date +%T) Iniciando worker de Celery embebido (cola erp_django)..."
    celery -A core worker \
        --loglevel=info \
        --queues=erp_django \
        --pool=solo \
        --without-gossip --without-mingle --without-heartbeat &
else
    echo "==> [entrypoint] $(date +%T) Worker de Celery embebido DESACTIVADO."
fi

echo "==> [entrypoint] $(date +%T) Iniciando Gunicorn en 0.0.0.0:${PORT:-8000}..."
exec gunicorn core.wsgi \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --timeout 120 \
    --log-file - \
    --access-logfile -