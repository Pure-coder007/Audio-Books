#!/usr/bin/env sh
set -eu

# Migrate the actual runtime database, including SQLite on a mounted disk.
python -m flask --app wsgi db upgrade
exec gunicorn wsgi:app --bind "0.0.0.0:${PORT:-10000}" --workers 1 --timeout 120
