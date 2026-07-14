from django.db import migrations


def refine_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    household_check = "household_id::text = current_setting('app.household_id', true)"
    policies = {
        "family_wishlist": (f"{household_check} OR is_shared", household_check),
        "family_wishitem": (f"{household_check} OR EXISTS (SELECT 1 FROM family_wishlist list WHERE list.id = wishlist_id AND list.is_shared)", household_check),
        "family_wishreservation": (f"{household_check} OR EXISTS (SELECT 1 FROM family_wishitem item JOIN family_wishlist list ON list.id = item.wishlist_id WHERE item.id = item_id AND list.is_shared AND item.household_id = family_wishreservation.household_id AND list.household_id = family_wishreservation.household_id)", f"{household_check} OR EXISTS (SELECT 1 FROM family_wishitem item JOIN family_wishlist list ON list.id = item.wishlist_id WHERE item.id = item_id AND list.is_shared AND item.household_id = family_wishreservation.household_id AND list.household_id = family_wishreservation.household_id)"),
    }
    with schema_editor.connection.cursor() as cursor:
        for table, (using, checking) in policies.items():
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING ({using}) WITH CHECK ({checking})"
            )


class Migration(migrations.Migration):
    dependencies = [("family", "0004_wishreservation_household_and_public_share_policy")]

    operations = [migrations.RunPython(refine_policies, migrations.RunPython.noop)]
