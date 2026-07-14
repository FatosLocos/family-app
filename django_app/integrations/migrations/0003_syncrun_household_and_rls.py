from django.db import migrations, models
import django.db.models.deletion


def populate_household(apps, schema_editor):
    SyncRun = apps.get_model("integrations", "SyncRun")
    for run in SyncRun.objects.select_related("connection").all():
        run.household_id = run.connection.household_id
        run.save(update_fields=["household"])


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "integrations_syncrun" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "integrations_syncrun" FORCE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "integrations_syncrun"')
        cursor.execute("CREATE POLICY household_isolation ON \"integrations_syncrun\" USING (household_id::text = current_setting('app.household_id', true)) WITH CHECK (household_id::text = current_setting('app.household_id', true))")


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "integrations_syncrun"')
        cursor.execute('ALTER TABLE "integrations_syncrun" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("households", "0003_householdinvite_label"),
        ("integrations", "0002_enable_household_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="syncrun",
            name="household",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to="households.household"),
        ),
        migrations.RunPython(populate_household, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="syncrun",
            name="household",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="households.household"),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
