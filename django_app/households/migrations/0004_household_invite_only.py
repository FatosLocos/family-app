# Generated migration for invite_only field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('households', '0003_householdinvite_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='household',
            name='invite_only',
            field=models.BooleanField(default=False),
        ),
    ]
