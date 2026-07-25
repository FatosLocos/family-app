from django.db import migrations, models

import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0010_event_invite_child_containment"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="target_source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="targeted_events",
                to="planning.calendarsource",
            ),
        ),
    ]
