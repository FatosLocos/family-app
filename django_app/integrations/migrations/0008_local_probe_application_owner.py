from django.db import migrations


def assign_application_owner(apps, schema_editor):
    """No-op since the DB owner/app role split (ops/init-postgres.sh): a
    dedicated owner role now owns every table via ALTER DEFAULT PRIVILEGES,
    and the app role gets DML grants automatically - no per-table ownership
    reassignment needed, and migrations run as the owner role so this would
    fail (it can't grant ownership to a role it isn't a member of)."""
    return


class Migration(migrations.Migration):
    dependencies = [("integrations", "0007_localprobe_localdiscovery")]

    operations = [migrations.RunPython(assign_application_owner, migrations.RunPython.noop)]
