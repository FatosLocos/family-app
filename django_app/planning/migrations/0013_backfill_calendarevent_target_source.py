from django.db import migrations, models

# Before 0011 every locally created event was pushed to the one calendar the household had
# write-back switched on for (planning.models.CalendarSource.write_back_target). That choice now
# lives per event in target_source, so an event that keeps NULL here would quietly stop being
# written back: the push task no longer finds it and the pull skips it because it is PENDING,
# leaving the appointment frozen in both directions. This hands every existing local event the
# calendar it was already being pushed to.

WRITE_BACK_PROVIDERS = ("outlook", "google_calendar", "caldav")
TABLES = ("planning_calendarevent", "planning_calendarsource")


def _accepts_local_events(source):
    """The credential half of CalendarSource.accepts_local_events, on the historical model."""
    if source.provider == "outlook":
        return source.connection_id is not None and bool(source.external_id)
    if source.provider == "caldav":
        return bool(source.caldav_url and source.write_access_token)
    return bool(source.write_access_token)


def _write_back_target(CalendarSource, household_id):
    candidates = CalendarSource.objects.filter(
        household_id=household_id, is_enabled=True, is_read_only=False, sync_local_events=True, provider__in=WRITE_BACK_PROVIDERS
    ).order_by("pk")
    for source in candidates:
        if _accepts_local_events(source):
            return source
    return None


def backfill_target_source(apps, schema_editor):
    CalendarEvent = apps.get_model("planning", "CalendarEvent")
    CalendarSource = apps.get_model("planning", "CalendarSource")
    is_postgres = schema_editor.connection.vendor == "postgresql"
    if is_postgres:
        # Row level security is forced on these tables, so even the owner running this migration
        # would see nothing without lifting it for the duration of the backfill.
        with schema_editor.connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
    try:
        local_events = CalendarEvent.objects.filter(target_source__isnull=True).filter(
            models.Q(source__isnull=True) | models.Q(source__provider="local")
        )
        for household_id in sorted(set(local_events.values_list("household_id", flat=True))):
            target = _write_back_target(CalendarSource, household_id)
            if target is None:
                continue
            local_events.filter(household_id=household_id).update(target_source=target)
    finally:
        if is_postgres:
            with schema_editor.connection.cursor() as cursor:
                for table in TABLES:
                    cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0012_calendarevent_abandoned_external_ids"),
    ]

    operations = [migrations.RunPython(backfill_target_source, migrations.RunPython.noop)]
