# Generated manually for conservative receipt-to-shopping matching.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("household", "0015_receiptlineitem")]

    operations = [
        migrations.AddField(
            model_name="receiptlineitem",
            name="shopping_item",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="receipt_line_items", to="household.shoppingitem"),
        ),
    ]
