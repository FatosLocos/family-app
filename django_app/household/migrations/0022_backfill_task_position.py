from django.db import migrations


def backfill_task_position(apps, schema_editor):
    """Seed the new drag-order field from the old auto-sort so existing tasks keep their visible order."""
    Task = apps.get_model("household", "Task")
    Household = apps.get_model("households", "Household")
    is_postgres = schema_editor.connection.vendor == "postgresql"
    if is_postgres:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "household_task" NO FORCE ROW LEVEL SECURITY')
    try:
        for household in Household.objects.all():
            tasks = Task.objects.filter(household_id=household.id).order_by("completed_at", "due_at", "-priority", "created_at")
            for index, task in enumerate(tasks):
                Task.objects.filter(pk=task.pk).update(position=index)
    finally:
        if is_postgres:
            with schema_editor.connection.cursor() as cursor:
                cursor.execute('ALTER TABLE "household_task" FORCE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("household", "0021_tasklist_rls"),
        ("households", "0007_childprofile_rls"),
    ]

    operations = [migrations.RunPython(backfill_task_position, migrations.RunPython.noop)]
