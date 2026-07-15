# Generated manually for OCR-recognised receipt product rows.

import django.db.models.deletion
from django.db import migrations, models


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "household_receiptlineitem" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "household_receiptlineitem" FORCE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "household_receiptlineitem"')
        cursor.execute(
            "CREATE POLICY household_isolation ON \"household_receiptlineitem\" "
            "USING (household_id::text = current_setting('app.household_id', true)) "
            "WITH CHECK (household_id::text = current_setting('app.household_id', true))"
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "household_receiptlineitem"')
        cursor.execute('ALTER TABLE "household_receiptlineitem" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("household", "0014_shoppingpriceproviderstatus")]

    operations = [
        migrations.CreateModel(
            name="ReceiptLineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=240)),
                ("quantity", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("unit_price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("total_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("raw_line", models.CharField(blank=True, max_length=500)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="households.household")),
                ("receipt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="line_items", to="household.receipt")),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
