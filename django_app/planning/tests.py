from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.models import IntegrationConnection
from planning.models import CalendarEvent, CalendarSource, IcsSubscription
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
