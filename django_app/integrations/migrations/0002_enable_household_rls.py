from django.db import migrations


TABLES = [
    "family_bulletinpost", "family_contact", "family_contactperson", "family_wishlist", "family_wishitem",
    "household_task", "household_shoppinglist", "household_shoppingitem", "household_mealplan", "household_routine",
    "planning_calendarsource", "planning_calendarevent", "planning_icssubscription",
    "finance_bankconnection", "finance_bankaccount", "finance_transaction", "finance_recurringrule", "finance_budget",
    "integrations_integrationappconfig", "integrations_integrationconnection", "notifications_notification",
]


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING (household_id::text = current_setting('app.household_id', true)) WITH CHECK (household_id::text = current_setting('app.household_id', true))"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"), ("family", "0002_initial"), ("finance", "0002_initial"),
        ("household", "0003_initial"), ("planning", "0001_initial"), ("notifications", "0001_initial"),
    ]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
