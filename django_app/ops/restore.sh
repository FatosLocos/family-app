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
app_db_owner="${APP_DB_OWNER:-${app_db_user}_owner}"
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

# Restore owns objects via superuser. Reassign ownership to owner role (DDL authority).
# Grant app role DML-only permissions (SELECT/INSERT/UPDATE/DELETE, no DDL, no ALTER RLS).
compose exec -T postgres psql -U postgres -d "$app_db_name" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
DECLARE
  item record;
  owner_name text := '$app_db_owner';
  app_name text := '$app_db_user';
BEGIN
  -- Reassign schema to owner role
  EXECUTE format('ALTER SCHEMA public OWNER TO %I', owner_name);

  -- Iterate restored objects and reassign ownership
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

    -- Grant app role DML permissions (no DDL)
    IF item.relkind IN ('r', 'p', 'm') THEN
      EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON %s %I.%I TO %I',
        CASE item.relkind
          WHEN 'm' THEN 'MATERIALIZED VIEW'
          ELSE 'TABLE'
        END,
        item.nspname,
        item.relname,
        app_name
      );
    ELSIF item.relkind = 'v' THEN
      EXECUTE format('GRANT SELECT ON VIEW %I.%I TO %I', item.nspname, item.relname, app_name);
    END IF;
  END LOOP;

  -- Grant app role usage on sequences
  FOR item IN
    SELECT namespace.nspname, object.relname
    FROM pg_class object
    JOIN pg_namespace namespace ON namespace.oid = object.relnamespace
    WHERE namespace.nspname = 'public'
      AND object.relkind = 'S'
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO %I', item.nspname, item.relname, owner_name);
    EXECUTE format('GRANT USAGE ON SEQUENCE %I.%I TO %I', item.nspname, item.relname, app_name);
  END LOOP;

  -- Reassign functions/procedures to owner role
  FOR item IN
    SELECT namespace.nspname, object.proname
    FROM pg_proc object
    JOIN pg_namespace namespace ON namespace.oid = object.pronamespace
    WHERE namespace.nspname = 'public'
  LOOP
    EXECUTE format('ALTER FUNCTION %I.%I OWNER TO %I', item.nspname, item.proname, owner_name);
  END LOOP;

END
\$\$;
SQL

if [ -f "$media_file" ]; then
  compose exec -T web \
    sh -c 'mkdir -p /app/media && find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -m --no-same-owner --no-same-permissions -C /app/media -xf -' < "$media_file"
fi
