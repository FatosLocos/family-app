from django.db import migrations, models

# Mark every notification that already existed as "already handled" so
# activating OpenClaw push doesn't suddenly flood WhatsApp with weeks of
# backlog — only notifications created after this point are eligible.


def backfill_delivered(apps, schema_editor):
    is_postgres = schema_editor.connection.vendor == "postgresql"
    if not is_postgres:
        Notification = apps.get_model("notifications", "Notification")
        Notification.objects.filter(delivered_to_openclaw_at__isnull=True).update(delivered_to_openclaw_at=models.F("created_at"))
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "notifications_notification" NO FORCE ROW LEVEL SECURITY')
    try:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('UPDATE "notifications_notification" SET delivered_to_openclaw_at = created_at WHERE delivered_to_openclaw_at IS NULL')
    finally:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "notifications_notification" FORCE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0004_notification_delivered_to_openclaw_at"),
    ]

    operations = [migrations.RunPython(backfill_delivered, migrations.RunPython.noop)]
