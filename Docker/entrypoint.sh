#!/bin/sh
set -e

mkdir -p /app/uploaded_files
mkdir -p /app/staticfiles

RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-1}"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    # Prevent concurrent migrations when multiple containers start simultaneously.
    # mkdir is atomic on POSIX filesystems.
    if mkdir /tmp/migrate.lock 2>/dev/null; then
        trap 'rmdir /tmp/migrate.lock 2>/dev/null || true' EXIT INT TERM
        uv run manage.py migrate --noinput
        rmdir /tmp/migrate.lock
        trap - EXIT INT TERM
    else
        i=0
        while [ -d /tmp/migrate.lock ]; do
            sleep 1
            i=$((i + 1))
            if [ "$i" -gt 120 ]; then
                echo "Migration lock did not clear within 120 seconds; refusing to continue startup." >&2
                exit 1
            fi
        done
    fi
fi

if [ "$RUN_COLLECTSTATIC" = "1" ]; then
    uv run manage.py collectstatic --noinput --clear
fi

exec "$@"

