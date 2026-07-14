#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
repo_dir=$(CDPATH= cd -- "$app_dir/.." && pwd)
env_file="$app_dir/.env.local"

if [ ! -f "$env_file" ]; then
  echo "Ontbrekend $env_file. Kopieer de lokale PostgreSQL-gegevens uit .env.example." >&2
  exit 1
fi

set -a
. "$env_file"
set +a

python_bin="${PYTHON_BIN:-$repo_dir/.venv-django/bin/python}"
if [ ! -x "$python_bin" ]; then
  python_bin="${PYTHON_BIN:-python3}"
fi

cd "$app_dir"
"$python_bin" manage.py migrate --noinput
exec "$python_bin" manage.py runserver "${@:-8000}"
