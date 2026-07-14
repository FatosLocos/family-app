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

compose_file="${COMPOSE_FILE:-/opt/family-app/docker-compose.django.yml}"
env_file="${ENV_FILE:-/opt/family-app/django_app/.env}"
compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}
app_db_name="${APP_DB_NAME:-$(compose exec -T postgres printenv APP_DB_NAME)}"
app_db_user="${APP_DB_USER:-$(compose exec -T postgres printenv APP_DB_USER)}"
media_file="${backup_file%.dump}.media.tar"

case "$app_db_name" in
  ''|*[!A-Za-z0-9_]* )
    echo "Ongeldige PostgreSQL-databasenaam." >&2
    exit 64
    ;;
esac
case "$app_db_user" in
  ''|*[!A-Za-z0-9_]* )
    echo "Ongeldige PostgreSQL-appgebruiker." >&2
    exit 64
    ;;
esac
echo "Herstel wist de huidige Family App-database en laadt: $backup_file"
printf "Typ HERSTEL om door te gaan: "
read answer
[ "$answer" = "HERSTEL" ] || exit 0

compose exec -T postgres pg_restore -U postgres -d "$app_db_name" --clean --if-exists --no-owner < "$backup_file"

# A superuser restore owns restored objects unless ownership is reassigned. The
# application role must own its tables so Django can operate while RLS remains enforced.
compose exec -T postgres psql -U postgres -d "$app_db_name" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
DECLARE
  item record;
  owner_name text := '$app_db_user';
BEGIN
  EXECUTE format('ALTER SCHEMA public OWNER TO %I', owner_name);

  FOR item IN
    SELECT namespace.nspname, object.relname, object.relkind
    FROM pg_class object
    JOIN pg_namespace namespace ON namespace.oid = object.relnamespace
    WHERE namespace.nspname = 'public'
      AND object.relkind IN ('r', 'p', 'v', 'm')
  LOOP
    EXECUTE format(
      'ALTER %s %I.%I OWNER TO %I',
      CASE item.relkind
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE 'TABLE'
      END,
      item.nspname,
      item.relname,
      owner_name
    );
  END LOOP;
END
\$\$;
SQL

if [ -f "$media_file" ]; then
  compose exec -T web \
    sh -c 'mkdir -p /app/media && find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -m --no-same-owner --no-same-permissions -C /app/media -xf -' < "$media_file"
fi
