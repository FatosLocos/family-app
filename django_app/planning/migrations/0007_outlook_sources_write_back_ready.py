from django.db import migrations


def prepare_outlook_sources(apps, schema_editor):
    """Outlook calendars used to be created with is_read_only=True hardcoded, which made
    write-back impossible forever. Clear that flag, but leave sync_local_events explicitly off
    so nothing starts pushing until a parent flips the toggle in the Agenda tab. While we are
    here, fill in the new connection FK wherever it can be derived unambiguously.
    """
    CalendarSource = apps.get_model("planning", "CalendarSource")
    IntegrationConnection = apps.get_model("integrations", "IntegrationConnection")
    Household = apps.get_model("households", "Household")
    is_postgres = schema_editor.connection.vendor == "postgresql"
    if is_postgres:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "planning_calendarsource" NO FORCE ROW LEVEL SECURITY')
            cursor.execute('ALTER TABLE "integrations_integrationconnection" NO FORCE ROW LEVEL SECURITY')
    try:
        for household in Household.objects.all():
            connections = IntegrationConnection.objects.filter(household_id=household.id, provider="outlook")
            for source in CalendarSource.objects.filter(household_id=household.id, provider="outlook"):
                updates = {"is_read_only": False, "sync_local_events": False}
                if source.connection_id is None:
                    candidates = list(connections.filter(user_id=source.owner_id) if source.owner_id else connections)
                    if len(candidates) == 1:
                        updates["connection_id"] = candidates[0].id
                CalendarSource.objects.filter(pk=source.pk).update(**updates)
    finally:
        if is_postgres:
            with schema_editor.connection.cursor() as cursor:
                cursor.execute('ALTER TABLE "planning_calendarsource" FORCE ROW LEVEL SECURITY')
                cursor.execute('ALTER TABLE "integrations_integrationconnection" FORCE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    # Writing the connection_id FK leaves a pending trigger event on planning_calendarsource
    # that would block the closing ALTER TABLE ... FORCE ROW LEVEL SECURITY in the same
    # transaction, exactly like integrations/0018_backfill_openclawtoken_user.
    atomic = False

    dependencies = [
        ("households", "0007_childprofile_rls"),
        ("planning", "0006_calendarsource_connection"),
    ]

    operations = [migrations.RunPython(prepare_outlook_sources, migrations.RunPython.noop)]
