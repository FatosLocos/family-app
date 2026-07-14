#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Gebruik: $0 /pad/naar/family-app-backup.dump" >&2
  exit 64
fi

backup_file="$1"
if [ ! -f "$backup_file" ]; then
  echo "Back-upbestand niet gevonden: $backup_file" >&2
  exit 66
fi

media_file="${backup_file%.dump}.media.tar"
if [ ! -f "$media_file" ]; then
  echo "Bijbehorend media-archief ontbreekt: $media_file" >&2
  exit 66
fi

compose_file="${COMPOSE_FILE:-/opt/family-app/docker-compose.django.yml}"
env_file="${ENV_FILE:-/opt/family-app/django_app/.env}"
compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}
app_db_name="${APP_DB_NAME:-$(compose exec -T postgres printenv APP_DB_NAME)}"
case "$app_db_name" in
  ''|*[!A-Za-z0-9_]* )
    echo "Ongeldige PostgreSQL-databasenaam." >&2
    exit 64
    ;;
esac
check_database="${app_db_name}_restore_check_$(date +%s)"
cleanup() {
  compose exec -T postgres dropdb -U postgres --if-exists "$check_database" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

# Validate the media archive on the host before creating a temporary database.
tar -tf "$media_file" >/dev/null
compose exec -T postgres createdb -U postgres "$check_database"
compose exec -T postgres pg_restore -U postgres -d "$check_database" --no-owner < "$backup_file"

migration_count="$(compose exec -T postgres psql -U postgres -d "$check_database" -Atqc 'SELECT count(*) FROM django_migrations;')"
case "$migration_count" in
  ''|0|*[!0-9]* )
    echo "Herstelvalidatie faalde: django_migrations ontbreekt of is leeg." >&2
    exit 1
    ;;
esac

echo "Back-up en media zijn hersteld in tijdelijke controle-database $check_database (${migration_count} migraties)."
