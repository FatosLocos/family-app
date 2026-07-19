from django.db import migrations


def backfill_token_user(apps, schema_editor):
    """Existing tokens predate per-user tokens — attribute them to the household owner."""
    OpenClawToken = apps.get_model("integrations", "OpenClawToken")
    Household = apps.get_model("households", "Household")
    Membership = apps.get_model("households", "Membership")
    is_postgres = schema_editor.connection.vendor == "postgresql"
    if is_postgres:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "integrations_openclawtoken" NO FORCE ROW LEVEL SECURITY')
            cursor.execute('ALTER TABLE "households_membership" NO FORCE ROW LEVEL SECURITY')
    try:
        for household in Household.objects.all():
            tokens = OpenClawToken.objects.filter(household_id=household.id, user_id__isnull=True)
            if not tokens.exists():
                continue
            membership = (
                Membership.objects.filter(household_id=household.id, role="owner").first()
                or Membership.objects.filter(household_id=household.id, role="parent").first()
            )
            if membership:
                tokens.update(user_id=membership.user_id)
    finally:
        if is_postgres:
            with schema_editor.connection.cursor() as cursor:
                cursor.execute('ALTER TABLE "integrations_openclawtoken" FORCE ROW LEVEL SECURITY')
                cursor.execute('ALTER TABLE "households_membership" FORCE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    # Updating the FK column (user_id) leaves a pending trigger event on
    # integrations_openclawtoken that blocks the closing ALTER TABLE ...
    # FORCE ROW LEVEL SECURITY if both run in the same transaction.
    atomic = False

    dependencies = [
        ("integrations", "0017_openclawactionlog_user_openclawtoken_user"),
    ]

    operations = [migrations.RunPython(backfill_token_user, migrations.RunPython.noop)]
