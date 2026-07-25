from django.db import migrations


HOUSEHOLD_CHECK = "household_id::text = current_setting('app.household_id', true)"
SHARED_USING = {
    "family_wishlist": f"{HOUSEHOLD_CHECK} OR is_shared",
    "family_wishitem": f"{HOUSEHOLD_CHECK} OR EXISTS (SELECT 1 FROM family_wishlist list WHERE list.id = wishlist_id AND list.is_shared)",
}


def reapply_policies(apps, schema_editor):
    """Re-create the public share policies clobbered by integrations.0002.

    Migration integrations.0002_enable_household_rls recreates household_isolation
    on family_wishlist and family_wishitem without depending on family.0005, so on a
    fresh database it runs last and replaces the read clause with the plain tenant
    check. This migration depends on both branches and therefore always wins.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, using in SHARED_USING.items():
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING ({using}) WITH CHECK ({HOUSEHOLD_CHECK})"
            )


def restore_plain_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in SHARED_USING:
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING ({HOUSEHOLD_CHECK}) WITH CHECK ({HOUSEHOLD_CHECK})"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0006_wishitem_category"),
        ("integrations", "0002_enable_household_rls"),
    ]

    operations = [migrations.RunPython(reapply_policies, restore_plain_policies)]
