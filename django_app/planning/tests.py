from datetime import datetime, time, timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from family.models import WishItem, WishList
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.models import IntegrationConnection
from planning.models import CalendarEvent, CalendarSource, EventGuest, EventInvite, EventProgramItem, EventQuestion, EventVenue, IcsSubscription
from planning.ics import parse_ics
from planning.tasks import sync_ics_subscriptions, sync_pending_events_to_remote


class PlanningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(user=self.user, household=self.household, role=Membership.Role.PARENT)
        self.client.force_login(self.user)

    def test_local_event_is_created_for_active_household(self):
        start = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        response = self.client.post(reverse("planning:add_event"), {"title": "Sport", "starts_at": start.strftime("%Y-%m-%dT%H:%M"), "ends_at": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CalendarEvent.objects.filter(household=self.household, title="Sport").exists())

    def test_ics_parser_reads_an_all_day_event(self):
        events = parse_ics(b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:test-event\r\nSUMMARY:Verjaardag\r\nDTSTART;VALUE=DATE:20260812\r\nDTEND;VALUE=DATE:20260813\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        self.assertEqual(events[0]["title"], "Verjaardag")
        self.assertTrue(events[0]["is_all_day"])

    def test_parent_can_disable_a_calendar_source(self):
        source = CalendarSource.objects.create(household=self.household, provider="outlook", name="Werk", is_read_only=True)
        response = self.client.post(reverse("planning:toggle_source", args=[source.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        source.refresh_from_db()
        self.assertFalse(source.is_enabled)

    def test_local_event_can_be_updated_and_deleted(self):
        start = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        source = CalendarSource.objects.create(household=self.household, provider="local", name="Gezinsagenda")
        event = CalendarEvent.objects.create(household=self.household, source=source, title="Oud", starts_at=start, ends_at=start + timedelta(hours=1))
        response = self.client.post(reverse("planning:update_event", args=[event.pk]), {
            "title": "Nieuw", "starts_at": start.strftime("%Y-%m-%dT%H:%M"), "ends_at": (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"), "location": "Thuis", "notes": "Bijgewerkt",
        })
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "Nieuw")
        self.assertEqual(event.location, "Thuis")
        self.client.post(reverse("planning:delete_event", args=[event.pk]))
        self.assertFalse(CalendarEvent.objects.filter(pk=event.pk).exists())

    def test_external_event_stays_read_only(self):
        start = timezone.now().replace(second=0, microsecond=0)
        source = CalendarSource.objects.create(household=self.household, provider="ics", name="Feestdagen", is_read_only=True)
        event = CalendarEvent.objects.create(household=self.household, source=source, title="Extern", starts_at=start, ends_at=start + timedelta(hours=1))
        response = self.client.post(reverse("planning:update_event", args=[event.pk]), {
            "title": "Niet toegestaan", "starts_at": start.strftime("%Y-%m-%dT%H:%M"), "ends_at": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("planning:delete_event", args=[event.pk]))
        self.assertEqual(response.status_code, 404)
        event.refresh_from_db()
        self.assertEqual(event.title, "Extern")

    def test_local_event_edit_overlay_is_rendered(self):
        start = timezone.now().replace(second=0, microsecond=0)
        event = CalendarEvent.objects.create(household=self.household, title="Gezinsafspraak", starts_at=start, ends_at=start + timedelta(hours=1))
        response = self.client.get(reverse("planning:index"), {"view": "week", "date": start.date().isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'event-edit-{event.pk}')
        self.assertContains(response, 'data-event-detail-edit')

    def test_ics_sync_is_idempotent_for_repeated_background_runs(self):
        source = CalendarSource.objects.create(household=self.household, provider="ics", name="Feestdagen", is_read_only=True)
        IcsSubscription.objects.create(household=self.household, source=source, name="Feestdagen", url="https://calendar.example.test/feesten.ics")
        response = Mock()
        response.content = b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:feest-1\r\nSUMMARY:Feestdag\r\nDTSTART;VALUE=DATE:20261225\r\nDTEND;VALUE=DATE:20261226\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        response.raise_for_status.return_value = None

        with patch("planning.tasks.requests.get", return_value=response):
            sync_ics_subscriptions()
            sync_ics_subscriptions()

        self.assertEqual(CalendarEvent.objects.filter(household=self.household, source=source, external_id="feest-1").count(), 1)
        source.refresh_from_db()
        self.assertIsNotNone(source.last_sync_at)


class FakeGraphResponse:
    """Minimal stand-in for a requests.Response from Microsoft Graph."""

    def __init__(self, payload, ok=True, status_code=200):
        self.payload = payload
        self.ok = ok
        self.content = b"{}"
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return self.payload


class OutlookCalendarWriteBackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Eerste gezin")
        Membership.objects.create(user=self.user, household=self.household, role=Membership.Role.PARENT)
        self.client.force_login(self.user)
        self.connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        self.source = CalendarSource.objects.create(
            household=self.household,
            provider=CalendarSource.Provider.OUTLOOK,
            name="Werkagenda",
            external_id="calendar-1",
            connection=self.connection,
            is_read_only=False,
            sync_local_events=True,
        )
        self.start = timezone.now().replace(second=0, microsecond=0)

    def _event(self, **overrides):
        fields = {"household": self.household, "source": self.source, "title": "Tandarts", "starts_at": self.start, "ends_at": self.start + timedelta(hours=1)}
        fields.update(overrides)
        return CalendarEvent.objects.create(**fields)

    def test_pending_event_is_created_in_outlook_and_marked_synced(self):
        event = self._event(location="Praktijk", notes="Halfjaarlijkse controle")
        calls = []

        def graph_request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("json")))
            return FakeGraphResponse({"id": "graph-event-1"}, status_code=201)

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        self.assertEqual(len(calls), 1)
        method, url, body = calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://graph.microsoft.com/v1.0/me/calendars/calendar-1/events")
        self.assertEqual(body["subject"], "Tandarts")
        self.assertEqual(body["location"], {"displayName": "Praktijk"})
        self.assertEqual(body["body"], {"contentType": "Text", "content": "Halfjaarlijkse controle"})
        # _outlook_headers sends no timezone Prefer, so the body has to carry it.
        self.assertEqual(body["start"]["timeZone"], "Europe/Amsterdam")
        self.assertEqual(body["end"]["timeZone"], "Europe/Amsterdam")

        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.SYNCED)
        self.assertEqual(event.external_id, "graph-event-1")
        self.assertEqual(event.last_sync_error, "")
        self.assertIsNotNone(event.remote_updated_at)

    def test_an_event_added_in_the_agenda_tab_is_created_in_outlook(self):
        """The whole point of issue #45: add_event files every new event under the local
        "Gezinsagenda", so the push task has to pick those up too or nothing ever leaves the app.
        """
        local_start = timezone.localtime(self.start)
        calls = []

        def graph_request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("json")))
            return FakeGraphResponse({"id": "graph-event-7"}, status_code=201)

        response = self.client.post(reverse("planning:add_event"), {
            "title": "Tandarts", "starts_at": local_start.strftime("%Y-%m-%dT%H:%M"), "ends_at": (local_start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        })

        self.assertEqual(response.status_code, 302)
        event = CalendarEvent.objects.get(household=self.household, title="Tandarts")
        self.assertEqual(event.source.provider, CalendarSource.Provider.LOCAL)
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.PENDING)

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        self.assertEqual([(method, url) for method, url, _ in calls], [("POST", "https://graph.microsoft.com/v1.0/me/calendars/calendar-1/events")])
        self.assertEqual(calls[0][2]["subject"], "Tandarts")
        event = CalendarEvent.objects.get(pk=event.pk)
        self.assertEqual(event.external_id, "graph-event-7")
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.SYNCED)
        # It stays on the family calendar, so the app keeps letting a parent edit and delete it.
        self.assertEqual(event.source.provider, CalendarSource.Provider.LOCAL)

    def test_a_local_event_is_not_pushed_while_write_back_is_off(self):
        self.source.sync_local_events = False
        self.source.is_read_only = True
        self.source.save(update_fields=["sync_local_events", "is_read_only", "updated_at"])
        local_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda")
        event = CalendarEvent.objects.create(household=self.household, source=local_source, title="Tandarts", starts_at=self.start, ends_at=self.start + timedelta(hours=1))

        with patch("integrations.providers.requests.request") as graph_request:
            sync_pending_events_to_remote()

        graph_request.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.PENDING)

    def test_deleting_a_pushed_event_warns_that_outlook_still_has_it(self):
        local_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda")
        event = CalendarEvent.objects.create(household=self.household, source=local_source, external_id="graph-event-1", title="Tandarts", starts_at=self.start, ends_at=self.start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.SYNCED)

        response = self.client.post(reverse("planning:delete_event", args=[event.pk]), follow=True)

        self.assertContains(response, "staat ook in Werkagenda")
        self.assertFalse(CalendarEvent.objects.filter(pk=event.pk).exists())

    def test_a_multi_day_all_day_event_keeps_its_last_day_in_outlook(self):
        starts_at = timezone.make_aware(datetime.combine(datetime(2026, 8, 1).date(), time.min))
        ends_at = timezone.make_aware(datetime.combine(datetime(2026, 8, 3).date(), time(23, 59)))
        self._event(title="Kamperen", is_all_day=True, starts_at=starts_at, ends_at=ends_at)
        calls = []

        def graph_request(method, url, **kwargs):
            calls.append(kwargs.get("json"))
            return FakeGraphResponse({"id": "graph-event-8"}, status_code=201)

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        # Graph reads the end of an all-day event as exclusive, so 1 t/m 3 augustus ends on the 4th.
        self.assertEqual(calls[0]["start"]["dateTime"], "2026-08-01T00:00:00")
        self.assertEqual(calls[0]["end"]["dateTime"], "2026-08-04T00:00:00")
        self.assertTrue(calls[0]["isAllDay"])

    def test_an_all_day_event_pulled_from_outlook_keeps_its_exclusive_end(self):
        starts_at = timezone.make_aware(datetime.combine(datetime(2026, 8, 1).date(), time.min))
        ends_at = timezone.make_aware(datetime.combine(datetime(2026, 8, 2).date(), time.min))
        self._event(title="Vrije dag", is_all_day=True, starts_at=starts_at, ends_at=ends_at, external_id="graph-event-9")
        calls = []

        def graph_request(method, url, **kwargs):
            calls.append(kwargs.get("json"))
            return FakeGraphResponse({"id": "graph-event-9"})

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        self.assertEqual(calls[0]["end"]["dateTime"], "2026-08-02T00:00:00")

    def test_an_update_without_notes_leaves_the_outlook_description_alone(self):
        """The pull only fills notes from the remote body when the remote changed, so an empty
        notes field is not proof that Outlook has no description — never overwrite it with "".
        """
        self._event(external_id="graph-event-1", notes="")
        calls = []

        def graph_request(method, url, **kwargs):
            calls.append(kwargs.get("json"))
            return FakeGraphResponse({"id": "graph-event-1"})

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        self.assertNotIn("body", calls[0])

    def test_known_event_is_patched_instead_of_created(self):
        self._event(external_id="graph-event-1")
        calls = []

        def graph_request(method, url, **kwargs):
            calls.append((method, url))
            return FakeGraphResponse({"id": "graph-event-1"})

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        self.assertEqual(calls, [("PATCH", "https://graph.microsoft.com/v1.0/me/events/graph-event-1")])

    def test_source_without_write_back_is_skipped(self):
        self.source.sync_local_events = False
        self.source.save(update_fields=["sync_local_events", "updated_at"])
        event = self._event()

        with patch("integrations.providers.requests.request") as graph_request:
            sync_pending_events_to_remote()

        graph_request.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.PENDING)

    def test_source_without_connection_is_skipped(self):
        self.source.connection = None
        self.source.save(update_fields=["connection", "updated_at"])
        event = self._event()

        with patch("integrations.providers.requests.request") as graph_request:
            sync_pending_events_to_remote()

        graph_request.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.PENDING)

    def test_event_pulled_from_outlook_is_not_pushed_straight_back(self):
        self._event(external_id="graph-event-1", sync_status=CalendarEvent.SyncStatus.SYNCED, remote_updated_at=timezone.now())

        with patch("integrations.providers.requests.request") as graph_request:
            sync_pending_events_to_remote()

        graph_request.assert_not_called()

    def test_failed_push_records_the_error_on_the_event_and_in_the_agenda(self):
        event = self._event()

        with patch("integrations.providers.requests.request", return_value=FakeGraphResponse({"error": {"message": "Access is denied."}}, ok=False, status_code=403)):
            sync_pending_events_to_remote()

        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.ERROR)
        self.assertIn("Access is denied.", event.last_sync_error)

        response = self.client.get(reverse("planning:index"), {"view": "week", "date": self.start.date().isoformat()})
        self.assertContains(response, "Laatste fout")

    def test_a_failed_push_bumps_updated_at_so_the_newest_error_is_the_one_shown(self):
        event = self._event()
        before = CalendarEvent.objects.get(pk=event.pk).updated_at

        with patch("integrations.providers.requests.request", return_value=FakeGraphResponse({"error": {"message": "Access is denied."}}, ok=False, status_code=403)):
            sync_pending_events_to_remote()

        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.ERROR)
        self.assertGreater(event.updated_at, before)

    def test_local_edit_puts_a_synced_event_back_on_pending(self):
        local_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda")
        event = CalendarEvent.objects.create(household=self.household, source=local_source, title="Oud", starts_at=self.start, ends_at=self.start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.SYNCED, last_sync_error="oude fout")
        local_start = timezone.localtime(self.start)

        response = self.client.post(reverse("planning:update_event", args=[event.pk]), {
            "title": "Nieuw", "starts_at": local_start.strftime("%Y-%m-%dT%H:%M"), "ends_at": (local_start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        })

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "Nieuw")
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.PENDING)
        self.assertEqual(event.last_sync_error, "")

    def test_parent_can_switch_write_back_off_and_on(self):
        response = self.client.post(reverse("planning:toggle_source_write_back", args=[self.source.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertFalse(self.source.sync_local_events)
        self.assertTrue(self.source.is_read_only)

        self.client.post(reverse("planning:toggle_source_write_back", args=[self.source.pk]))

        self.source.refresh_from_db()
        self.assertTrue(self.source.sync_local_events)
        self.assertFalse(self.source.is_read_only)

    def test_only_one_calendar_can_receive_the_write_back(self):
        second_source = CalendarSource.objects.create(
            household=self.household, provider=CalendarSource.Provider.OUTLOOK, name="Privéagenda", external_id="calendar-2",
            connection=self.connection, is_read_only=True, sync_local_events=False,
        )

        response = self.client.post(reverse("planning:toggle_source_write_back", args=[second_source.pk]), follow=True)

        self.assertContains(response, "maar één tegelijk")
        second_source.refresh_from_db()
        self.source.refresh_from_db()
        self.assertTrue(second_source.sync_local_events)
        self.assertFalse(self.source.sync_local_events)
        self.assertTrue(self.source.is_read_only)

    def test_write_back_toggle_is_refused_for_an_ics_source(self):
        ics_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.ICS, name="Feestdagen", is_read_only=True, sync_local_events=False)

        response = self.client.post(reverse("planning:toggle_source_write_back", args=[ics_source.pk]), follow=True)

        self.assertContains(response, "kan geen afspraken ontvangen")
        ics_source.refresh_from_db()
        self.assertFalse(ics_source.sync_local_events)
        self.assertTrue(ics_source.is_read_only)

    def test_write_back_toggle_of_another_household_is_not_found(self):
        other_household = Household.objects.create(name="Tweede gezin")
        other_source = CalendarSource.objects.create(household=other_household, provider=CalendarSource.Provider.OUTLOOK, name="Andermans agenda", sync_local_events=False, is_read_only=True)

        response = self.client.post(reverse("planning:toggle_source_write_back", args=[other_source.pk]))

        self.assertEqual(response.status_code, 404)
        other_source.refresh_from_db()
        self.assertFalse(other_source.sync_local_events)
        self.assertTrue(other_source.is_read_only)

    def test_agenda_tab_labels_the_source_and_its_write_back_state(self):
        self._event()

        response = self.client.get(reverse("planning:index"), {"view": "week", "date": self.start.date().isoformat()})

        self.assertContains(response, "Werkagenda")
        self.assertContains(response, "Terugsturen aan")

    def test_agenda_tab_does_not_claim_write_back_without_an_outlook_connection(self):
        self.connection.delete()
        self._event()

        response = self.client.get(reverse("planning:index"), {"view": "week", "date": self.start.date().isoformat()})

        self.assertNotContains(response, "Terugsturen aan")
        self.assertContains(response, "Terugsturen wacht op koppeling")


class EventInviteTests(TestCase):
    """The public invitation: sharing, RSVP and the boundaries between two households."""

    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Eerste gezin")
        Membership.objects.create(user=self.user, household=self.household, role=Membership.Role.OWNER)
        self.other_user = User.objects.create_user(username="buur@example.com", email="buur@example.com", password="safe-password-123", display_name="Buur")
        self.other_household = Household.objects.create(name="Tweede gezin")
        Membership.objects.create(user=self.other_user, household=self.other_household, role=Membership.Role.PARENT)
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=7)
        self.event = CalendarEvent.objects.create(household=self.household, title="Verjaardag Sanne", starts_at=self.start, ends_at=self.start + timedelta(hours=3))
        self.client.force_login(self.user)

    def _shared_invite(self, **fields):
        invite = EventInvite.objects.create(household=self.household, event=self.event, is_shared=True, share_token="deel-token-verjaardag", intro="Kom je ook?", **fields)
        return invite

    def _other_event(self):
        return CalendarEvent.objects.create(household=self.other_household, title="Andermans feest", starts_at=self.start, ends_at=self.start + timedelta(hours=1))

    # --- organisator ---------------------------------------------------------------

    def test_sharing_creates_an_invite_with_a_token_and_a_public_url(self):
        response = self.client.post(reverse("planning:toggle_event_share", args=[self.event.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        invite = EventInvite.objects.get(event=self.event)
        self.assertTrue(invite.is_shared)
        self.assertTrue(invite.share_token)
        self.assertEqual(invite.household_id, self.household.id)

        agenda = self.client.get(reverse("planning:index"), {"view": "day", "date": timezone.localtime(self.start).date().isoformat()})
        self.assertContains(agenda, invite.share_token)
        self.assertContains(agenda, f"invite-{self.event.pk}")

    def test_unsharing_keeps_the_same_token_when_it_is_switched_back_on(self):
        self.client.post(reverse("planning:toggle_event_share", args=[self.event.pk]))
        first_token = EventInvite.objects.get(event=self.event).share_token

        self.client.post(reverse("planning:toggle_event_share", args=[self.event.pk]))
        self.client.post(reverse("planning:toggle_event_share", args=[self.event.pk]))

        self.assertEqual(EventInvite.objects.get(event=self.event).share_token, first_token)

    def test_invite_details_program_questions_and_venue_can_be_managed(self):
        venue = EventVenue.objects.create(household=self.household, name="Speeltuin De Bron", address="Dorpsstraat 1", city="Bunnik")
        wishlist = WishList.objects.create(household=self.household, owner=self.user, title="Wensen van Sanne")

        self.client.post(reverse("planning:update_event_invite", args=[self.event.pk]), {"intro": "Sanne wordt 8!", "venue": venue.pk, "wishlist": wishlist.pk})
        self.client.post(reverse("planning:add_event_program_item", args=[self.event.pk]), {"starts_at": "14:00", "description": "Taart eten", "sort_order": 1})
        self.client.post(reverse("planning:add_event_question", args=[self.event.pk]), {"label": "Eet je mee?", "kind": "yesno", "is_required": "on", "sort_order": 1})

        invite = EventInvite.objects.get(event=self.event)
        self.assertEqual(invite.intro, "Sanne wordt 8!")
        self.assertEqual(invite.venue_id, venue.pk)
        self.assertEqual(invite.wishlist_id, wishlist.pk)
        self.assertEqual(invite.program_items.get().description, "Taart eten")
        self.assertTrue(invite.questions.get().is_required)

    def test_a_venue_is_created_once_per_household(self):
        self.client.post(reverse("planning:add_event_venue"), {"name": "Speeltuin De Bron", "address": "Dorpsstraat 1", "postal_code": "3981 AA", "city": "Bunnik"})
        response = self.client.post(reverse("planning:add_event_venue"), {"name": "Speeltuin De Bron"}, follow=True)

        self.assertContains(response, "bestaat al een locatie")
        self.assertEqual(EventVenue.objects.for_household(self.household).count(), 1)

    def test_program_item_and_question_can_be_deleted(self):
        invite = self._shared_invite()
        item = EventProgramItem.objects.create(household=self.household, invite=invite, description="Taart eten")
        question = EventQuestion.objects.create(household=self.household, invite=invite, label="Eet je mee?")

        self.client.post(reverse("planning:delete_event_program_item", args=[item.pk]))
        self.client.post(reverse("planning:delete_event_question", args=[question.pk]))

        self.assertFalse(EventProgramItem.objects.filter(pk=item.pk).exists())
        self.assertFalse(EventQuestion.objects.filter(pk=question.pk).exists())

    # --- publieke pagina -----------------------------------------------------------

    def test_anonymous_visitor_sees_a_shared_invitation(self):
        invite = self._shared_invite()
        venue = EventVenue.objects.create(household=self.household, name="Speeltuin De Bron", city="Bunnik")
        invite.venue = venue
        invite.save(update_fields=["venue", "updated_at"])
        EventProgramItem.objects.create(household=self.household, invite=invite, starts_at="14:00", description="Taart eten")
        EventQuestion.objects.create(household=self.household, invite=invite, label="Eet je mee?", kind=EventQuestion.Kind.YESNO)
        self.client.logout()

        response = self.client.get(reverse("planning:public_event_invite", args=[invite.share_token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verjaardag Sanne")
        self.assertContains(response, "Speeltuin De Bron")
        self.assertContains(response, "Taart eten")
        self.assertContains(response, "Eet je mee?")

    def test_unshared_or_unknown_token_is_not_found(self):
        invite = EventInvite.objects.create(household=self.household, event=self.event, is_shared=False, share_token="stille-token")
        self.client.logout()

        self.assertEqual(self.client.get(reverse("planning:public_event_invite", args=[invite.share_token])).status_code, 404)
        self.assertEqual(self.client.get(reverse("planning:public_event_invite", args=["bestaat-niet"])).status_code, 404)

    def test_turning_sharing_off_makes_the_public_url_disappear_immediately(self):
        invite = self._shared_invite()
        self.assertEqual(self.client.get(reverse("planning:public_event_invite", args=[invite.share_token])).status_code, 200)

        self.client.post(reverse("planning:toggle_event_share", args=[self.event.pk]))
        self.client.logout()

        self.assertEqual(self.client.get(reverse("planning:public_event_invite", args=[invite.share_token])).status_code, 404)

    def test_public_page_never_leaks_another_household(self):
        invite = self._shared_invite()
        other_event = self._other_event()
        other_invite = EventInvite.objects.create(household=self.other_household, event=other_event, is_shared=True, share_token="andermans-token", intro="Geheim feest")
        EventProgramItem.objects.create(household=self.other_household, invite=other_invite, description="Andermans programma")
        EventGuest.objects.create(household=self.other_household, invite=other_invite, name="Andermans gast")
        self.client.logout()

        response = self.client.get(reverse("planning:public_event_invite", args=[invite.share_token]))

        self.assertNotContains(response, "Andermans feest")
        self.assertNotContains(response, "Andermans programma")
        self.assertNotContains(response, "Andermans gast")

    def test_public_page_does_not_show_the_names_of_other_guests(self):
        invite = self._shared_invite()
        EventGuest.objects.create(household=self.household, invite=invite, name="Buurvrouw Tineke", rsvp=EventGuest.Rsvp.YES, party_size=2)
        self.client.logout()

        response = self.client.get(reverse("planning:public_event_invite", args=[invite.share_token]))

        self.assertNotContains(response, "Buurvrouw Tineke")
        self.assertContains(response, "al 2 mensen aangemeld")

    def test_linked_wishlist_is_only_shown_when_that_wishlist_is_itself_shared(self):
        wishlist = WishList.objects.create(household=self.household, owner=self.user, title="Wensen van Sanne")
        WishItem.objects.create(household=self.household, wishlist=wishlist, title="Skateboard")
        invite = self._shared_invite(wishlist=wishlist)
        self.client.logout()

        response = self.client.get(reverse("planning:public_event_invite", args=[invite.share_token]))
        self.assertNotContains(response, "Skateboard")

        wishlist.is_shared = True
        wishlist.share_token = "wenslijst-token"
        wishlist.save(update_fields=["is_shared", "share_token", "updated_at"])

        response = self.client.get(reverse("planning:public_event_invite", args=[invite.share_token]))
        self.assertContains(response, "Skateboard")

    # --- anoniem aanmelden ---------------------------------------------------------

    def test_anonymous_rsvp_creates_a_guest_in_the_inviting_household(self):
        invite = self._shared_invite()
        question = EventQuestion.objects.create(household=self.household, invite=invite, label="Eet je mee?", kind=EventQuestion.Kind.YESNO, is_required=True)
        self.client.logout()

        response = self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {
            "name": "Oma Riet", "rsvp": "yes", "party_size": "2", "note": "Ik neem taart mee", f"vraag-{question.pk}": "ja",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        guest = EventGuest.objects.get(invite=invite)
        self.assertEqual(guest.name, "Oma Riet")
        self.assertEqual(guest.household_id, self.household.id)
        self.assertEqual(guest.party_size, 2)
        answer = guest.answers.get()
        self.assertEqual(answer.value, "ja")
        self.assertEqual(answer.household_id, self.household.id)

    def test_rsvp_refuses_a_missing_required_answer_and_a_wrong_answer_kind(self):
        invite = self._shared_invite()
        required = EventQuestion.objects.create(household=self.household, invite=invite, label="Eet je mee?", kind=EventQuestion.Kind.YESNO, is_required=True)
        number = EventQuestion.objects.create(household=self.household, invite=invite, label="Hoeveel broers en zussen?", kind=EventQuestion.Kind.NUMBER)
        self.client.logout()

        response = self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {"name": "Oma Riet", "rsvp": "yes"}, follow=True)
        self.assertContains(response, "is verplicht")

        response = self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {
            "name": "Oma Riet", "rsvp": "yes", f"vraag-{required.pk}": "ja", f"vraag-{number.pk}": "veel",
        }, follow=True)
        self.assertContains(response, "verwacht een aantal")

        self.assertFalse(EventGuest.objects.filter(invite=invite).exists())

    def test_rsvp_refuses_a_missing_name_or_an_unknown_answer(self):
        invite = self._shared_invite()
        self.client.logout()

        self.assertContains(self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {"rsvp": "yes"}, follow=True), "Vul je naam in")
        self.assertContains(self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {"name": "Oma Riet", "rsvp": "vast-wel"}, follow=True), "Geef aan of je komt")
        self.assertFalse(EventGuest.objects.filter(invite=invite).exists())

    def test_rsvp_is_closed_after_the_deadline(self):
        invite = self._shared_invite(rsvp_deadline=timezone.now() - timedelta(hours=1))
        self.client.logout()

        response = self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {"name": "Oma Riet", "rsvp": "yes"}, follow=True)

        self.assertContains(response, "aanmeldtermijn")
        self.assertFalse(EventGuest.objects.filter(invite=invite).exists())

    def test_rsvp_on_an_unshared_invitation_is_not_found(self):
        invite = EventInvite.objects.create(household=self.household, event=self.event, is_shared=False, share_token="stille-token")
        self.client.logout()

        response = self.client.post(reverse("planning:rsvp_event", args=[invite.share_token]), {"name": "Oma Riet", "rsvp": "yes"})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(EventGuest.objects.filter(invite=invite).exists())

    # --- cross-household -----------------------------------------------------------

    def test_every_organiser_endpoint_of_another_household_is_not_found(self):
        other_event = self._other_event()
        other_invite = EventInvite.objects.create(household=self.other_household, event=other_event, is_shared=False, intro="Geheim feest")
        other_item = EventProgramItem.objects.create(household=self.other_household, invite=other_invite, description="Andermans programma")
        other_question = EventQuestion.objects.create(household=self.other_household, invite=other_invite, label="Andermans vraag")

        for url, data in (
            (reverse("planning:update_event_invite", args=[other_event.pk]), {"intro": "Gekaapt"}),
            (reverse("planning:toggle_event_share", args=[other_event.pk]), {}),
            (reverse("planning:add_event_program_item", args=[other_event.pk]), {"description": "Gekaapt"}),
            (reverse("planning:add_event_question", args=[other_event.pk]), {"label": "Gekaapt", "kind": "text"}),
            (reverse("planning:delete_event_program_item", args=[other_item.pk]), {}),
            (reverse("planning:delete_event_question", args=[other_question.pk]), {}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data).status_code, 404)

        other_invite.refresh_from_db()
        self.assertEqual(other_invite.intro, "Geheim feest")
        self.assertFalse(other_invite.is_shared)
        self.assertTrue(EventProgramItem.objects.filter(pk=other_item.pk).exists())
        self.assertTrue(EventQuestion.objects.filter(pk=other_question.pk).exists())
        self.assertEqual(EventProgramItem.objects.filter(invite=other_invite).count(), 1)
        self.assertEqual(EventQuestion.objects.filter(invite=other_invite).count(), 1)
