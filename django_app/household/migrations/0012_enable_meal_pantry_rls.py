from django.db import migrations


HOUSEHOLD_TABLES = ("household_mealingredient", "household_pantryitem")


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in HOUSEHOLD_TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" "
                "USING (household_id::text = current_setting('app.household_id', true)) "
                "WITH CHECK (household_id::text = current_setting('app.household_id', true))"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in HOUSEHOLD_TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("household", "0011_pantryitem")]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
