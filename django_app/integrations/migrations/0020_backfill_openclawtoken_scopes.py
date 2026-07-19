import json

from django.db import migrations

# Scopes matching every MCP capability that existed before scopes did, so
# this migration is a no-op in behavior: nothing that already worked stops
# working. Narrowing scopes per-token is a UI feature added afterwards.
DEFAULT_SCOPES = ["vandaag:read", "taken:write", "boodschappen:read", "boodschappen:write"]


def backfill_scopes(apps, schema_editor):
    is_postgres = schema_editor.connection.vendor == "postgresql"
    if not is_postgres:
        OpenClawToken = apps.get_model("integrations", "OpenClawToken")
        OpenClawToken.objects.filter(scopes=[]).update(scopes=DEFAULT_SCOPES)
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "integrations_openclawtoken" NO FORCE ROW LEVEL SECURITY')
    try:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                'UPDATE "integrations_openclawtoken" SET scopes = %s::jsonb WHERE scopes = \'[]\'::jsonb',
                [json.dumps(DEFAULT_SCOPES)],
            )
    finally:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "integrations_openclawtoken" FORCE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0019_openclawtoken_scopes"),
    ]

    operations = [migrations.RunPython(backfill_scopes, migrations.RunPython.noop)]
