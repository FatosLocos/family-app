# Generated migration for calendar write support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0004_calendareventsearch"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="sync_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("synced", "Synced"),
                    ("conflict", "Conflict"),
                    ("error", "Error"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="calendarevent",
            name="last_sync_error",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="calendarevent",
            name="remote_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="calendarsource",
            name="write_access_token",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="calendarsource",
            name="caldav_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="calendarsource",
            name="caldav_username",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="calendarsource",
            name="sync_local_events",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="calendarevent",
            name="source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="events",
                to="planning.calendarsource",
            ),
        ),
        migrations.AlterModelOptions(
            name="calendarsource",
            options={"verbose_name_plural": "Calendar sources"},
        ),
        migrations.AddIndex(
            model_name="calendarevent",
            index=models.Index(fields=["source", "external_id"], name="planning_ca_source_external_idx"),
        ),
        migrations.AlterField(
            model_name="calendarsource",
            name="provider",
            field=models.CharField(
                choices=[
                    ("local", "Lokaal"),
                    ("outlook", "Outlook"),
                    ("ics", "ICS"),
                    ("google_calendar", "Google Calendar"),
                    ("caldav", "CalDAV"),
                ],
                max_length=16,
            ),
        ),
    ]
