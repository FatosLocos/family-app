#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
repo_dir=$(CDPATH= cd -- "$app_dir/.." && pwd)
env_file="$app_dir/.env.local"

if [ ! -f "$env_file" ]; then
  echo "Ontbrekend $env_file." >&2
  exit 1
fi

set -a
. "$env_file"
set +a

if [ -z "${TEST_DATABASE_URL:-}" ]; then
  echo "TEST_DATABASE_URL moet naar een lokale PostgreSQL-beheerverbinding verwijzen." >&2
  exit 1
fi

python_bin="${PYTHON_BIN:-$repo_dir/.venv-django/bin/python}"
if [ ! -x "$python_bin" ]; then
  python_bin="${PYTHON_BIN:-python3}"
fi

cd "$app_dir"
DATABASE_URL="$TEST_DATABASE_URL" exec "$python_bin" manage.py test "$@"
