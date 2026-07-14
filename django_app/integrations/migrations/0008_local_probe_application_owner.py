from django.db import migrations


def assign_application_owner(apps, schema_editor):
    """Keep new probe tables usable by the restricted Django database role."""
    if schema_editor.connection.vendor != "postgresql":
        return

    application_user = schema_editor.connection.settings_dict.get("USER")
    if not application_user:
        return

    quoted_user = schema_editor.connection.ops.quote_name(application_user)
    with schema_editor.connection.cursor() as cursor:
        for table in ("integrations_localprobe", "integrations_localdiscovery"):
            cursor.execute(f'ALTER TABLE "{table}" OWNER TO {quoted_user}')


class Migration(migrations.Migration):
    dependencies = [("integrations", "0007_localprobe_localdiscovery")]

    operations = [migrations.RunPython(assign_application_owner, migrations.RunPython.noop)]
