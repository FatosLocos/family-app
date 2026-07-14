from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from households.models import Household, Membership
from identity.models import User
from planning.models import CalendarEvent, CalendarSource, IcsSubscription
from planning.ics import parse_ics
from planning.tasks import sync_ics_subscriptions


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
