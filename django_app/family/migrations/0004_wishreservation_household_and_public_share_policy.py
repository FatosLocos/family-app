import django.db.models.deletion
from django.db import migrations, models


def populate_household(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "family_wishreservation" NO FORCE ROW LEVEL SECURITY')
            try:
                cursor.execute(
                    "UPDATE family_wishreservation reservation "
                    "SET household_id = item.household_id "
                    "FROM family_wishitem item WHERE item.id = reservation.item_id"
                )
            finally:
                cursor.execute('ALTER TABLE "family_wishreservation" FORCE ROW LEVEL SECURITY')
        return
    WishReservation = apps.get_model("family", "WishReservation")
    for reservation in WishReservation.objects.select_related("item").all():
        reservation.household_id = reservation.item.household_id
        reservation.save(update_fields=["household"])


def apply_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    policies = {
        "family_wishlist": "household_id::text = current_setting('app.household_id', true) OR is_shared",
        "family_wishitem": "household_id::text = current_setting('app.household_id', true) OR EXISTS (SELECT 1 FROM family_wishlist list WHERE list.id = wishlist_id AND list.is_shared)",
        "family_wishreservation": "household_id::text = current_setting('app.household_id', true) OR EXISTS (SELECT 1 FROM family_wishitem item JOIN family_wishlist list ON list.id = item.wishlist_id WHERE item.id = item_id AND list.is_shared AND item.household_id = family_wishreservation.household_id AND list.household_id = family_wishreservation.household_id)",
    }
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "family_wishreservation" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "family_wishreservation" FORCE ROW LEVEL SECURITY')
        for table, using in policies.items():
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING ({using}) WITH CHECK ({using})"
            )


def restore_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("family_wishlist", "family_wishitem"):
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING (household_id::text = current_setting('app.household_id', true)) WITH CHECK (household_id::text = current_setting('app.household_id', true))"
            )
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "family_wishreservation"')
        cursor.execute('ALTER TABLE "family_wishreservation" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0003_alter_wishlist_share_token_wishreservation"),
        ("households", "0003_householdinvite_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="wishreservation",
            name="household",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to="households.household"),
        ),
        migrations.RunPython(populate_household, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="wishreservation",
            name="household",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="households.household"),
        ),
        migrations.RunPython(apply_policies, restore_policies),
    ]
