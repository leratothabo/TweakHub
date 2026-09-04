#!/bin/sh
# Shared entrypoint for both the `api` and `worker` docker-compose
# services (same image, infrastructure/docker/Dockerfile.api — only the
# command differs). With no arguments, this is the API: run pending
# Alembic migrations (fails loudly — set -e — rather than starting
# against a stale schema) then start uvicorn. With arguments (the worker
# service passes `rq worker ...`), just exec those directly — migrations
# only ever run from the API container, never racing a worker that
# started at the same time.
set -e

if [ "$#" -eq 0 ]; then
    echo "==> Running database migrations"
    alembic upgrade head

    echo "==> Starting API"
    exec uvicorn main:app --host 0.0.0.0 --port 3001
else
    echo "==> Starting: $*"
    exec "$@"
fi
