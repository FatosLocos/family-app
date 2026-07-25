from django.db import migrations, models

import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0001_initial"),
        ("planning", "0005_calendar_write_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarsource",
            name="connection",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="calendar_sources",
                to="integrations.integrationconnection",
            ),
        ),
    ]
