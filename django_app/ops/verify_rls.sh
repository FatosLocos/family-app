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
      ('household_task'), ('household_tasknote'), ('household_tasklist'), ('household_tasklistsync'), ('household_shoppinglist'), ('household_shoppingitem'), ('household_shoppingprice'), ('household_shoppingpricesnapshot'), ('household_shoppingoffer'), ('household_shoppingpriceproviderstatus'), ('household_receipt'), ('household_receiptlineitem'), ('household_mealplan'), ('household_mealingredient'), ('household_pantryitem'), ('household_routine'), ('household_weatherdata'), ('household_weatherpreference'),
      ('planning_calendarsource'), ('planning_calendarevent'), ('planning_icssubscription'), ('planning_eventvenue'), ('planning_eventinvite'), ('planning_eventprogramitem'), ('planning_eventquestion'), ('planning_eventguest'), ('planning_eventanswer'),
      ('finance_bankconnection'), ('finance_bankaccount'), ('finance_transaction'), ('finance_recurringrule'), ('finance_budget'),
      ('integrations_integrationappconfig'), ('integrations_integrationconnection'), ('integrations_syncrun'), ('integrations_integrationaudit'), ('integrations_localprobe'), ('integrations_localdiscovery'), ('integrations_openclawtoken'), ('integrations_openclawactionlog'), ('integrations_openclawnotificationpreference'),
      ('notifications_notification'),
      ('home_homeassistantconfig'), ('home_homeentity'), ('home_homeactionaudit'),
      ('home_emergencycontact'), ('home_maintenanceitem'), ('home_room'), ('home_furnishingitem'), ('home_householddocument'), ('home_energyreading'), ('home_evvehicle'), ('home_evchargingsession'),
      ('travel_trip'), ('travel_tripstop'), ('travel_tripdocument'), ('travel_tripidea'),
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
  broken text;
BEGIN
  -- De publieke wenslijst en de publieke evenement-uitnodiging mogen anoniem gelezen worden
  -- (is_shared in USING) maar nooit anoniem geschreven (WITH CHECK blijft de kale
  -- huishoudencheck). Alleen family_wishreservation, planning_eventguest en
  -- planning_eventanswer mogen dat wel, en die staan daarom niet in deze lijst.
  SELECT string_agg(expected.table_name, ', ')
  INTO broken
  FROM (
    VALUES
      ('family_wishlist'), ('family_wishitem'),
      ('planning_calendarevent'), ('planning_eventinvite'), ('planning_eventprogramitem'), ('planning_eventquestion'), ('planning_eventvenue')
  ) AS expected(table_name)
  LEFT JOIN pg_policies policy
    ON policy.schemaname = 'public'
   AND policy.tablename = expected.table_name
   AND policy.policyname = 'household_isolation'
  WHERE policy.qual IS NULL
     OR policy.qual NOT LIKE '%is_shared%'
     OR policy.with_check IS NULL
     OR policy.with_check LIKE '%is_shared%';

  IF broken IS NOT NULL THEN
    RAISE EXCEPTION 'Publieke deelpolicy klopt niet voor: % (USING moet is_shared bevatten, WITH CHECK niet)', broken;
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
  INSERT INTO household_task (household_id, created_at, updated_at, title, notes, priority, position, completion_reason, created_by_agent, source_label, source_url, external_provider, external_id)
  VALUES (first_household, now(), now(), 'RLS controle', '', 2, 0, '', false, '', '', '', '')
  RETURNING id INTO task_id;

  PERFORM set_config('app.household_id', second_household::text, false);
  SELECT count(*) INTO visible_count FROM household_task WHERE id = task_id;
  IF visible_count <> 0 THEN
    RAISE EXCEPTION 'RLS laat een taak uit een ander huishouden lezen';
  END IF;

  BEGIN
    INSERT INTO household_task (household_id, created_at, updated_at, title, notes, priority, position, completion_reason, created_by_agent, source_label, source_url, external_provider, external_id)
    VALUES (first_household, now(), now(), 'RLS mag dit blokkeren', '', 2, 0, '', false, '', '', '', '');
    RAISE EXCEPTION 'RLS liet een write voor een ander huishouden toe';
  EXCEPTION
    WHEN insufficient_privilege THEN
      NULL;
  END;
END $$;

DO $$
DECLARE
  -- Bewijs voor de publieke evenement-uitnodiging: anoniem (geen app.household_id) mag een
  -- gedeelde uitnodiging lezen en zich aanmelden, maar niets anders schrijven en nooit een
  -- eigen household_id meesmokkelen.
  invite_household bigint;
  other_household bigint;
  event_id bigint;
  invite_id bigint;
  question_id bigint;
  guest_id bigint;
  visible_count integer;
BEGIN
  INSERT INTO households_household (name, created_at, invite_only) VALUES ('RLS uitnodiging A', now(), false) RETURNING id INTO invite_household;
  INSERT INTO households_household (name, created_at, invite_only) VALUES ('RLS uitnodiging B', now(), false) RETURNING id INTO other_household;

  PERFORM set_config('app.household_id', invite_household::text, false);
  INSERT INTO planning_calendarevent (household_id, created_at, updated_at, external_id, title, starts_at, ends_at, is_all_day, location, notes, sync_status, last_sync_error)
  VALUES (invite_household, now(), now(), '', 'RLS uitnodiging', now(), now(), false, '', '', 'pending', '') RETURNING id INTO event_id;
  INSERT INTO planning_eventinvite (household_id, created_at, updated_at, event_id, is_shared, share_token, intro)
  VALUES (invite_household, now(), now(), event_id, true, 'rls-controle-token', '') RETURNING id INTO invite_id;
  INSERT INTO planning_eventquestion (household_id, created_at, updated_at, invite_id, label, kind, is_required, sort_order)
  VALUES (invite_household, now(), now(), invite_id, 'Eet je mee?', 'yesno', false, 0) RETURNING id INTO question_id;

  PERFORM set_config('app.household_id', '', false);
  SELECT count(*) INTO visible_count FROM planning_eventinvite WHERE id = invite_id;
  IF visible_count <> 1 THEN RAISE EXCEPTION 'Een gedeelde uitnodiging is niet anoniem leesbaar'; END IF;
  SELECT count(*) INTO visible_count FROM planning_calendarevent WHERE id = event_id;
  IF visible_count <> 1 THEN RAISE EXCEPTION 'Het evenement van een gedeelde uitnodiging is niet anoniem leesbaar'; END IF;

  INSERT INTO planning_eventguest (household_id, created_at, updated_at, invite_id, name, rsvp, party_size, note)
  VALUES (invite_household, now(), now(), invite_id, 'RLS gast', 'yes', 1, '') RETURNING id INTO guest_id;
  INSERT INTO planning_eventanswer (household_id, created_at, updated_at, guest_id, question_id, value)
  VALUES (invite_household, now(), now(), guest_id, question_id, 'ja');

  BEGIN
    INSERT INTO planning_eventguest (household_id, created_at, updated_at, invite_id, name, rsvp, party_size, note)
    VALUES (other_household, now(), now(), invite_id, 'RLS smokkelaar', 'yes', 1, '');
    RAISE EXCEPTION 'Een anonieme aanmelding kon een vreemd household_id meesmokkelen';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    INSERT INTO planning_eventanswer (household_id, created_at, updated_at, guest_id, question_id, value)
    VALUES (other_household, now(), now(), guest_id, question_id, 'ja');
    RAISE EXCEPTION 'Een anoniem antwoord kon een vreemd household_id meesmokkelen';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    INSERT INTO planning_eventprogramitem (household_id, created_at, updated_at, invite_id, starts_at, description, sort_order)
    VALUES (invite_household, now(), now(), invite_id, '14:00', 'RLS mag dit blokkeren', 0);
    RAISE EXCEPTION 'Een anonieme bezoeker kon het programma van een uitnodiging schrijven';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  PERFORM set_config('app.household_id', invite_household::text, false);
  UPDATE planning_eventinvite SET is_shared = false WHERE id = invite_id;
  PERFORM set_config('app.household_id', '', false);
  SELECT count(*) INTO visible_count FROM planning_eventinvite WHERE id = invite_id;
  IF visible_count <> 0 THEN RAISE EXCEPTION 'Een niet-gedeelde uitnodiging blijft anoniem leesbaar'; END IF;
  SELECT count(*) INTO visible_count FROM planning_calendarevent WHERE id = event_id;
  IF visible_count <> 0 THEN RAISE EXCEPTION 'Het evenement van een niet-gedeelde uitnodiging blijft anoniem leesbaar'; END IF;
END $$;

ROLLBACK;
SQL

echo "RLS-schema en isolatie gecontroleerd. Er zijn geen testgegevens bewaard."
