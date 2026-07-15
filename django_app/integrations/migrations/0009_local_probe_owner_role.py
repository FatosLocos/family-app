from django.db import migrations


def assign_application_role(apps, schema_editor):
    """No-op since the DB owner/app role split (ops/init-postgres.sh): DML
    grants for the app role now apply schema-wide via ALTER DEFAULT
    PRIVILEGES, in tests and production alike, so no table-specific
    ownership reassignment is needed - and it would fail anyway (the
    migrating role isn't a member of the app role)."""
    return


class Migration(migrations.Migration):
    dependencies = [("integrations", "0008_local_probe_application_owner")]

    operations = [migrations.RunPython(assign_application_role, migrations.RunPython.noop)]
