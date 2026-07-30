#!/bin/sh
set -eu

PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc
export PROMETHEUS_MULTIPROC_DIR

mkdir -p /tmp/prometheus-multiproc
find /tmp/prometheus-multiproc -maxdepth 1 -type f -name '*.db' -delete

exec gunicorn app.main:app \
    --config /app/deploy/gunicorn.conf.py \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-3}" \
    --bind 0.0.0.0:8000 \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile -
