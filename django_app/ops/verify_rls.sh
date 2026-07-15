#!/bin/sh
set -eu

# Runs a transactional PostgreSQL proof without leaving test data behind.
psql_bin="${PSQL_BIN:-}"
if [ -z "$psql_bin" ]; then
  if command -v psql >/dev/null 2>&1; then
    psql_bin="$(command -v psql)"
  elif [ -x /opt/homebrew/bin/psql ]; then
    # Homebrew's PostgreSQL client is not always added to the GUI shell PATH.
    psql_bin="/opt/homebrew/bin/psql"
  else
    psql_bin="psql"
  fi
fi

rls_role="${RLS_ROLE:-}"
case "$rls_role" in
  '' ) ;;
  *[!A-Za-z0-9_]* )
    echo "Ongeldige PostgreSQL RLS_ROLE." >&2
    exit 64
    ;;
esac

if [ -n "${DATABASE_URL:-}" ]; then
  run_psql() {
    if [ -n "$rls_role" ]; then
      "$psql_bin" "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "SET ROLE \"$rls_role\"" -f -
    else
      "$psql_bin" "$DATABASE_URL" -v ON_ERROR_STOP=1
    fi
  }
else
  compose_file="${COMPOSE_FILE:-/opt/family-app/docker-compose.django.yml}"
  env_file="${ENV_FILE:-/opt/family-app/django_app/.env}"
  compose() {
    docker compose --env-file "$env_file" -f "$compose_file" "$@"
  }
  app_db_name="${APP_DB_NAME:-$(compose exec -T postgres printenv APP_DB_NAME)}"
  app_db_user="${APP_DB_USER:-$(compose exec -T postgres printenv APP_DB_USER)}"
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
  run_psql() {
    if [ -n "$rls_role" ]; then
      compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$app_db_user" -d "$app_db_name" -c "SET ROLE \"$rls_role\"" -f -
    else
      compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$app_db_user" -d "$app_db_name"
    fi
  }
fi

run_psql <<'SQL'
BEGIN;

DO $$
DECLARE
  missing text;
BEGIN
  SELECT string_agg(expected.table_name, ', ')
  INTO missing
  FROM (
    VALUES
      ('family_bulletinpost'), ('family_contact'), ('family_contactperson'), ('family_wishlist'), ('family_wishitem'), ('family_wishreservation'),
      ('household_task'), ('household_shoppinglist'), ('household_shoppingitem'), ('household_shoppingprice'), ('household_shoppingpricesnapshot'), ('household_shoppingoffer'), ('household_shoppingpriceproviderstatus'), ('household_receipt'), ('household_receiptlineitem'), ('household_mealplan'), ('household_mealingredient'), ('household_pantryitem'), ('household_routine'), ('household_weatherdata'), ('household_weatherpreference'),
      ('planning_calendarsource'), ('planning_calendarevent'), ('planning_icssubscription'),
      ('finance_bankconnection'), ('finance_bankaccount'), ('finance_transaction'), ('finance_recurringrule'), ('finance_budget'),
      ('integrations_integrationappconfig'), ('integrations_integrationconnection'), ('integrations_syncrun'), ('integrations_integrationaudit'), ('integrations_localprobe'), ('integrations_localdiscovery'),
      ('notifications_notification'),
      ('home_homeassistantconfig'), ('home_homeentity'), ('home_homeactionaudit'),
      ('home_emergencycontact'), ('home_maintenanceitem'), ('home_room'), ('home_furnishingitem'), ('home_householddocument'), ('home_energyreading'), ('home_evvehicle'), ('home_evchargingsession'),
      ('households_childprofile')
  ) AS expected(table_name)
  LEFT JOIN pg_class relation ON relation.relname = expected.table_name AND relation.relnamespace = 'public'::regnamespace
  WHERE relation.oid IS NULL OR NOT relation.relrowsecurity OR NOT relation.relforcerowsecurity;

  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'RLS ontbreekt of is niet geforceerd voor: %', missing;
  END IF;
END $$;

DO $$
DECLARE
  first_household bigint;
  second_household bigint;
  task_id bigint;
  visible_count integer;
BEGIN
  INSERT INTO households_household (name, created_at, invite_only) VALUES ('RLS controle A', now(), false) RETURNING id INTO first_household;
  INSERT INTO households_household (name, created_at, invite_only) VALUES ('RLS controle B', now(), false) RETURNING id INTO second_household;

  PERFORM set_config('app.household_id', first_household::text, false);
  INSERT INTO household_task (household_id, created_at, updated_at, title, notes, priority)
  VALUES (first_household, now(), now(), 'RLS controle', '', 2)
  RETURNING id INTO task_id;

  PERFORM set_config('app.household_id', second_household::text, false);
  SELECT count(*) INTO visible_count FROM household_task WHERE id = task_id;
  IF visible_count <> 0 THEN
    RAISE EXCEPTION 'RLS laat een taak uit een ander huishouden lezen';
  END IF;

  BEGIN
    INSERT INTO household_task (household_id, created_at, updated_at, title, notes, priority)
    VALUES (first_household, now(), now(), 'RLS mag dit blokkeren', '', 2);
    RAISE EXCEPTION 'RLS liet een write voor een ander huishouden toe';
  EXCEPTION
    WHEN insufficient_privilege THEN
      NULL;
  END;
END $$;

ROLLBACK;
SQL

echo "RLS-schema en isolatie gecontroleerd. Er zijn geen testgegevens bewaard."
