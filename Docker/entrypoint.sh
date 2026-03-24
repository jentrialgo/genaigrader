#!/bin/sh
set -e

mkdir -p /app/uploaded_files
mkdir -p /app/staticfiles

uv run manage.py migrate --noinput
uv run manage.py collectstatic --noinput

exec "$@"

