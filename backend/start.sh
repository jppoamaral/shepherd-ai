#!/bin/sh
# Render's start command: migrate, load the synthetic seeds (idempotent), serve.
set -e
alembic upgrade head
python -m seeds
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
