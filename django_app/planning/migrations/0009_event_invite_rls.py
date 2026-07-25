"""Row level security for the event invitation tables, including the anonymous exception.

Follows the public wishlist precedent in family/migrations/0004 and 0005 to the letter.

USING versus WITH CHECK is the security boundary:

* planning_eventinvite, planning_eventprogramitem, planning_eventquestion,
  planning_eventvenue and planning_calendarevent are publicly READABLE for a shared
  invitation — their USING gets an "OR <shared descent>" clause, but their WITH CHECK stays
  the bare household check. An anonymous visitor may read, never write.
* planning_eventguest and planning_eventanswer are the only tables an anonymous visitor may
  INSERT into, so their WITH CHECK carries the same exception. Every ancestor in that
  exception additionally has to match the new row's household_id
  (AND <parent>.household_id = <table>.household_id), exactly like family_wishreservation:
  without it a visitor could smuggle in an arbitrary household_id and land a row inside
  someone else's tenant.
* family_wishlist and family_wishitem are deliberately NOT widened. An invitation may link a
  wishlist, but the wishlist's own is_shared exception stays the only way it becomes publicly
  readable; planning.views._public_wishlist_of therefore refuses to show a wishlist that the
  owner has not shared, instead of the invitation loosening someone else's policy.

The share token itself never appears in a policy: authorisation is the unguessable token in
Python, the database only proves containment. Two independent layers.
"""
from django.db import migrations

HOUSEHOLD_CHECK = "household_id::text = current_setting('app.household_id', true)"

SHARED_INVITE_OF_EVENT = "EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.event_id = planning_calendarevent.id AND invite.is_shared)"
SHARED_INVITE_OF_CHILD = "EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.id = invite_id AND invite.is_shared)"
SHARED_INVITE_OF_VENUE = "EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.venue_id = planning_eventvenue.id AND invite.is_shared)"
# Anonymous writes: the invitation must be shared AND own the household the new row claims.
GUEST_PUBLIC = "EXISTS (SELECT 1 FROM planning_eventinvite invite WHERE invite.id = invite_id AND invite.is_shared AND invite.household_id = planning_eventguest.household_id)"
ANSWER_PUBLIC = (
    "EXISTS (SELECT 1 FROM planning_eventguest guest JOIN planning_eventinvite invite ON invite.id = guest.invite_id "
    "WHERE guest.id = planning_eventanswer.guest_id AND invite.is_shared "
    "AND guest.household_id = planning_eventanswer.household_id AND invite.household_id = planning_eventanswer.household_id "
    "AND EXISTS (SELECT 1 FROM planning_eventquestion question WHERE question.id = planning_eventanswer.question_id "
    "AND question.invite_id = guest.invite_id AND question.household_id = planning_eventanswer.household_id))"
)

# table -> (USING, WITH CHECK)
POLICIES = {
    "planning_eventvenue": (f"{HOUSEHOLD_CHECK} OR {SHARED_INVITE_OF_VENUE}", HOUSEHOLD_CHECK),
    "planning_eventinvite": (f"{HOUSEHOLD_CHECK} OR is_shared", HOUSEHOLD_CHECK),
    "planning_eventprogramitem": (f"{HOUSEHOLD_CHECK} OR {SHARED_INVITE_OF_CHILD}", HOUSEHOLD_CHECK),
    "planning_eventquestion": (f"{HOUSEHOLD_CHECK} OR {SHARED_INVITE_OF_CHILD}", HOUSEHOLD_CHECK),
    "planning_eventguest": (f"{HOUSEHOLD_CHECK} OR {GUEST_PUBLIC}", f"{HOUSEHOLD_CHECK} OR {GUEST_PUBLIC}"),
    "planning_eventanswer": (f"{HOUSEHOLD_CHECK} OR {ANSWER_PUBLIC}", f"{HOUSEHOLD_CHECK} OR {ANSWER_PUBLIC}"),
    # Already RLS-enabled; only its policy is widened so a shared invitation can show the
    # event's own title and time to a visitor who is not logged in.
    "planning_calendarevent": (f"{HOUSEHOLD_CHECK} OR {SHARED_INVITE_OF_EVENT}", HOUSEHOLD_CHECK),
}

NEW_TABLES = ("planning_eventvenue", "planning_eventinvite", "planning_eventprogramitem", "planning_eventquestion", "planning_eventguest", "planning_eventanswer")


def apply_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in NEW_TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        for table, (using, checking) in POLICIES.items():
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'CREATE POLICY household_isolation ON "{table}" USING ({using}) WITH CHECK ({checking})')


def restore_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in NEW_TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS household_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS household_isolation ON "planning_calendarevent"')
        cursor.execute(f'CREATE POLICY household_isolation ON "planning_calendarevent" USING ({HOUSEHOLD_CHECK}) WITH CHECK ({HOUSEHOLD_CHECK})')


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0008_event_invite"),
    ]

    operations = [migrations.RunPython(apply_policies, restore_policies)]
