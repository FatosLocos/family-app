from uuid import uuid4

from django.db import migrations, models
import django.db.models.deletion


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("integrations_localprobe", "integrations_localdiscovery"):
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cursor.execute(
                f"CREATE POLICY household_isolation ON \"{table}\" USING (household_id::text = current_setting('app.household_id', true)) WITH CHECK (household_id::text = current_setting('app.household_id', true))"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("integrations_localdiscovery", "integrations_localprobe"):
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("integrations", "0006_alter_integrationconnection_provider")]

    operations = [
        migrations.CreateModel(
            name="LocalProbe",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(default="Lokale probe", max_length=120)),
                ("token_hash", models.CharField(blank=True, max_length=255)),
                ("pairing_code_hash", models.CharField(blank=True, max_length=255)),
                ("pairing_expires_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.CharField(blank=True, max_length=80)),
                ("status", models.CharField(default="pairing", max_length=24)),
                ("adapters", models.JSONField(blank=True, default=dict)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="local_probes", to="households.household")),
            ],
            options={"ordering": ("-last_seen_at", "name")},
        ),
        migrations.CreateModel(
            name="LocalDiscovery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=300)),
                ("name", models.CharField(max_length=200)),
                ("kind", models.CharField(max_length=80)),
                ("address", models.GenericIPAddressField(blank=True, null=True)),
                ("method", models.CharField(max_length=40)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="local_discoveries", to="households.household")),
                ("probe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discoveries", to="integrations.localprobe")),
            ],
            options={"ordering": ("kind", "name")},
        ),
        migrations.AddConstraint(model_name="localdiscovery", constraint=models.UniqueConstraint(fields=("probe", "key"), name="unique_probe_discovery_key")),
        migrations.RunPython(enable_rls, disable_rls),
    ]
