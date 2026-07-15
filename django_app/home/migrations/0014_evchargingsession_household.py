import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_household(apps, schema_editor):
    EVVehicle = apps.get_model("home", "EVVehicle")
    EVChargingSession = apps.get_model("home", "EVChargingSession")
    EVChargingSession.objects.filter(household__isnull=True).update(
        household_id=Subquery(EVVehicle.objects.filter(pk=OuterRef("vehicle_id")).values("household_id")[:1])
    )


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "home_evchargingsession" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "home_evchargingsession" FORCE ROW LEVEL SECURITY')
        cursor.execute('CREATE POLICY household_isolation ON "home_evchargingsession" USING (household_id::text = current_setting(\'app.household_id\', true)) WITH CHECK (household_id::text = current_setting(\'app.household_id\', true))')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "home_evchargingsession"')
        cursor.execute('ALTER TABLE "home_evchargingsession" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0013_energy_ev_rls"),
        ("households", "0006_invite_code_hashing"),
    ]

    operations = [
        migrations.AddField(
            model_name="evchargingsession",
            name="household",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ev_charging_sessions", to="households.household"),
        ),
        migrations.RunPython(backfill_household, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="evchargingsession",
            name="household",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ev_charging_sessions", to="households.household"),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
