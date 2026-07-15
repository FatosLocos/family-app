# Generated manually for persisted price-provider diagnostics.

import django.db.models.deletion
from django.db import migrations, models


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "household_shoppingpriceproviderstatus" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "household_shoppingpriceproviderstatus" FORCE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "household_shoppingpriceproviderstatus"')
        cursor.execute(
            "CREATE POLICY household_isolation ON \"household_shoppingpriceproviderstatus\" "
            "USING (household_id::text = current_setting('app.household_id', true)) "
            "WITH CHECK (household_id::text = current_setting('app.household_id', true))"
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "household_shoppingpriceproviderstatus"')
        cursor.execute('ALTER TABLE "household_shoppingpriceproviderstatus" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("household", "0013_shoppingoffer")]

    operations = [
        migrations.CreateModel(
            name="ShoppingPriceProviderStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.CharField(choices=[("checkjebon", "Checkjebon"), ("prijsprofeet", "PrijsProfeet")], max_length=20)),
                ("status", models.CharField(choices=[("succeeded", "Beschikbaar"), ("failed", "Niet bereikbaar")], default="succeeded", max_length=20)),
                ("detail", models.CharField(blank=True, max_length=240)),
                ("checked_at", models.DateTimeField(auto_now=True)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="households.household")),
            ],
            options={
                "ordering": ("provider",),
                "constraints": [models.UniqueConstraint(fields=("household", "provider"), name="unique_household_price_provider_status")],
            },
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
