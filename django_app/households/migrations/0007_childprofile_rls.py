from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "households_childprofile" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "households_childprofile" FORCE ROW LEVEL SECURITY')
        cursor.execute('CREATE POLICY household_isolation ON "households_childprofile" USING (household_id::text = current_setting(\'app.household_id\', true)) WITH CHECK (household_id::text = current_setting(\'app.household_id\', true))')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "households_childprofile"')
        cursor.execute('ALTER TABLE "households_childprofile" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("households", "0006_invite_code_hashing"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
