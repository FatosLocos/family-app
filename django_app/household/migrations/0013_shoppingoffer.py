# Generated manually for the separate promotion store.

import django.db.models.deletion
from django.db import migrations, models


def migrate_legacy_offers(apps, schema_editor):
    ShoppingPrice = apps.get_model("household", "ShoppingPrice")
    ShoppingOffer = apps.get_model("household", "ShoppingOffer")
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "household_shoppingprice" NO FORCE ROW LEVEL SECURITY')
    try:
        for price in ShoppingPrice.objects.filter(source="prijsprofeet", is_offer=True).iterator():
            ShoppingOffer.objects.update_or_create(
                household_id=price.household_id,
                item_id=price.item_id,
                retailer=price.retailer,
                source=price.source,
                defaults={
                    "price": price.price,
                    "matched_product_name": price.matched_product_name,
                    "offer_label": price.offer_label,
                    "regular_price": price.regular_price,
                    "offer_valid_until": price.offer_valid_until,
                    "product_url": price.product_url,
                },
            )
            price.delete()
    finally:
        if schema_editor.connection.vendor == "postgresql":
            with schema_editor.connection.cursor() as cursor:
                cursor.execute('ALTER TABLE "household_shoppingprice" FORCE ROW LEVEL SECURITY')


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "household_shoppingoffer" ENABLE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE "household_shoppingoffer" FORCE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "household_shoppingoffer"')
        cursor.execute(
            "CREATE POLICY household_isolation ON \"household_shoppingoffer\" "
            "USING (household_id::text = current_setting('app.household_id', true)) "
            "WITH CHECK (household_id::text = current_setting('app.household_id', true))"
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "household_shoppingoffer"')
        cursor.execute('ALTER TABLE "household_shoppingoffer" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("household", "0012_enable_meal_pantry_rls")]

    operations = [
        migrations.CreateModel(
            name="ShoppingOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("retailer", models.CharField(choices=[("ah", "Albert Heijn"), ("jumbo", "Jumbo"), ("lidl", "Lidl"), ("kaufland", "Kaufland")], max_length=20)),
                ("price", models.DecimalField(decimal_places=2, max_digits=8)),
                ("matched_product_name", models.CharField(blank=True, max_length=240)),
                ("offer_label", models.CharField(blank=True, max_length=160)),
                ("regular_price", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("offer_valid_until", models.DateField(blank=True, null=True)),
                ("product_url", models.URLField(blank=True)),
                ("source", models.CharField(choices=[("manual", "Handmatig"), ("checkjebon", "Checkjebon"), ("prijsprofeet", "PrijsProfeet")], default="prijsprofeet", max_length=20)),
                ("observed_at", models.DateTimeField(auto_now=True)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="households.household")),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="household.shoppingitem")),
            ],
            options={
                "ordering": ("price",),
                "constraints": [models.UniqueConstraint(fields=("item", "retailer", "source"), name="unique_offer_per_item_retailer_source")],
            },
        ),
        migrations.RunPython(migrate_legacy_offers, migrations.RunPython.noop),
        migrations.RunPython(enable_rls, disable_rls),
    ]
