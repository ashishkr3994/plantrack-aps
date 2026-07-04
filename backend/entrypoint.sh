#!/usr/bin/env bash
# Container entrypoint. First arg selects the process type.
#   api     -> run DB migrations then serve the API (gunicorn + uvicorn workers)
#   worker  -> Celery worker
#   beat    -> Celery beat (periodic deviation scan)
#   migrate -> run migrations only, then exit
set -euo pipefail

run_migrations() {
  echo "[entrypoint] running database migrations (alembic upgrade head)…"
  alembic upgrade head
}

case "${1:-api}" in
  api)
    run_migrations
    WORKERS="${WEB_CONCURRENCY:-3}"
    echo "[entrypoint] starting API with ${WORKERS} workers…"
    exec gunicorn app.main:app \
      --worker-class uvicorn.workers.UvicornWorker \
      --workers "${WORKERS}" \
      --bind 0.0.0.0:8000 \
      --access-logfile - --error-logfile - \
      --timeout 120
    ;;
  worker)
    exec celery -A app.jobs.celery_app.celery_app worker --loglevel=info
    ;;
  beat)
    exec celery -A app.jobs.celery_app.celery_app beat --loglevel=info
    ;;
  migrate)
    run_migrations
    ;;
  *)
    echo "[entrypoint] unknown process type: $1" >&2
    exit 1
    ;;
esac