"""Tie the programme and question tables of an invitation to their own household.

0009 gave planning_eventprogramitem and planning_eventquestion the read-only half of the
wishlist precedent: the anonymous exception in USING, a bare household check in WITH CHECK.
That keeps an anonymous visitor out, but it does not stop household B from inserting a row
that points at household A's shared invitation — the row carries B's own household_id, so the
bare check passes, and the USING exception then renders that row on A's public invitation
page. Only planning.views keeps that shut today, which is one layer short of the two this
module promises.

Both tables therefore get the ancestor rule family_wishreservation already has: the parent
invitation has to belong to the same household as the row itself, in USING as well as in
WITH CHECK. Nothing in the application changes — every insert comes from planning.views,
which sets household and invite from the same household in one go.

planning_eventguest and planning_eventanswer already carry that rule in the clause that
matters: their public exception compares every ancestor's household_id with the new row's.
"""
from django.db import migrations

HOUSEHOLD_CHECK = "household_id::text = current_setting('app.household_id', true)"


def _own_invite(table):
    return f"EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.id = invite_id AND invite.household_id = {table}.household_id)"


def _shared_invite(table):
    return f"EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.id = invite_id AND invite.is_shared AND invite.household_id = {table}.household_id)"


TABLES = ("planning_eventprogramitem", "planning_eventquestion")

# The 0009 definitions, kept here so the reverse really puts the old policy back.
PREVIOUS_CHILD_EXCEPTION = "EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.id = invite_id AND invite.is_shared)"


def apply_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            using = f"({HOUSEHOLD_CHECK} AND {_own_invite(table)}) OR {_shared_invite(table)}"
            checking = f"{HOUSEHOLD_CHECK} AND {_own_invite(table)}"
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'CREATE POLICY household_isolation ON "{table}" USING ({using}) WITH CHECK ({checking})')


def restore_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'CREATE POLICY household_isolation ON "{table}" USING ({HOUSEHOLD_CHECK} OR {PREVIOUS_CHILD_EXCEPTION}) WITH CHECK ({HOUSEHOLD_CHECK})')


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0009_event_invite_rls"),
    ]

    operations = [migrations.RunPython(apply_policies, restore_policies)]
