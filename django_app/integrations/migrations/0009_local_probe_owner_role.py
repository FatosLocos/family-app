import os

from django.db import migrations


def assign_application_role(apps, schema_editor):
    """Tests migrate with an admin role; runtime still uses the restricted role."""
    if schema_editor.connection.vendor != "postgresql":
        return

    application_role = os.environ.get("APP_DB_USER", "family_app")
    quoted_role = schema_editor.connection.ops.quote_name(application_role)
    with schema_editor.connection.cursor() as cursor:
        for table in ("integrations_localprobe", "integrations_localdiscovery"):
            cursor.execute(f'ALTER TABLE "{table}" OWNER TO {quoted_role}')


class Migration(migrations.Migration):
    dependencies = [("integrations", "0008_local_probe_application_owner")]

    operations = [migrations.RunPython(assign_application_role, migrations.RunPython.noop)]
