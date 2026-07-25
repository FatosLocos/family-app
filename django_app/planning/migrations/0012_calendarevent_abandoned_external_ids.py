from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0011_calendarevent_target_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="abandoned_external_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
