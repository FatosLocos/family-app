#!/bin/sh
set -eu

# One-time transition for an EXISTING database created under the old
# single-role model (the app role owned everything) to the new owner/app
# split (ops/init-postgres.sh). Safe to run more than once: CREATE ROLE
# IF NOT EXISTS-style guards make it idempotent. Rehearsed against a
# disposable local database that mimicked production before use here -
# see SECURITY.md for the full design.

: "${APP_DB_NAME:?APP_DB_NAME is required}"
: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_OWNER:=${APP_DB_USER}_owner}"

compose_file="${COMPOSE_FILE:-/opt/family-app/docker-compose.django.yml}"
env_file="${ENV_FILE:-/opt/family-app/django_app/.env}"
compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

echo "Overgang naar owner/app-rolscheiding voor database '$APP_DB_NAME'."
echo "Maak eerst een back-up (ops/backup.sh) als dat nog niet is gedaan voor dit onderhoudsmoment."
printf "Typ OVERGANG om door te gaan: "
read answer
[ "$answer" = "OVERGANG" ] || exit 0

compose exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$APP_DB_OWNER') THEN
    CREATE ROLE $APP_DB_OWNER NOLOGIN;
  END IF;
END
\$\$;
SQL

compose exec -T postgres psql -U postgres -d "$APP_DB_NAME" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
DECLARE
  item record;
  owner_name text := '$APP_DB_OWNER';
  app_name text := '$APP_DB_USER';
BEGIN
  EXECUTE format('ALTER DATABASE %I OWNER TO %I', '$APP_DB_NAME', owner_name);
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
      EXECUTE format('GRANT SELECT ON TABLE %I.%I TO %I', item.nspname, item.relname, app_name);
    END IF;
  END LOOP;

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

  FOR item IN
    SELECT namespace.nspname, object.proname
    FROM pg_proc object
    JOIN pg_namespace namespace ON namespace.oid = object.pronamespace
    WHERE namespace.nspname = 'public'
  LOOP
    EXECUTE format('ALTER FUNCTION %I.%I OWNER TO %I', item.nspname, item.proname, owner_name);
  END LOOP;

  -- The app role was the schema/database owner before this transition, so it
  -- may carry a stale explicit ACL entry (e.g. "family_app=UC/...") that
  -- ALTER ... OWNER TO does not clean up - only the ownership field changes,
  -- not pre-existing grants to the old owner. Strip everything and re-grant
  -- exactly what the app role needs, so no residual CREATE/DDL right survives.
  EXECUTE format('REVOKE ALL ON SCHEMA public FROM %I', app_name);
  EXECUTE format('REVOKE ALL ON DATABASE %I FROM %I', '$APP_DB_NAME', app_name);
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', '$APP_DB_NAME', app_name);
  EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_name);
  EXECUTE format('ALTER DEFAULT PRIVILEGES FOR USER %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', owner_name, app_name);
  EXECUTE format('ALTER DEFAULT PRIVILEGES FOR USER %I IN SCHEMA public GRANT USAGE ON SEQUENCES TO %I', owner_name, app_name);
END
\$\$;
SQL

echo "Overgang voltooid. $APP_DB_OWNER bezit nu schema/tabellen; $APP_DB_USER heeft alleen DML."
