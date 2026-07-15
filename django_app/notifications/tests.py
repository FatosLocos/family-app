from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from household.models import Task
from finance.models import RecurringRule
from households.models import Household, Membership
from identity.models import User
from notifications.models import Notification
from notifications.tasks import refresh_household_notifications
from planning.models import CalendarEvent


class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.OWNER)
        Task.objects.create(household=self.household, title="Bel huisarts", due_at=timezone.now() - timedelta(hours=2))
        Task.objects.create(household=self.household, title="Vuilnis buiten", due_at=timezone.now() + timedelta(hours=2))
        CalendarEvent.objects.create(household=self.household, title="Ophalen", starts_at=timezone.now() + timedelta(hours=3), ends_at=timezone.now() + timedelta(hours=4))
        self.client.force_login(self.user)

    def test_background_job_generates_deduplicated_daily_signals(self):
        RecurringRule.objects.create(household=self.household, fingerprint="insurance", merchant="Verzekering", direction="expense", expected_amount="20.00", last_seen_at=timezone.localdate() - timedelta(days=28), cadence_days=30)
        refresh_household_notifications()
        refresh_household_notifications()
        self.assertEqual(Notification.objects.filter(household=self.household).count(), 4)
        self.assertTrue(Notification.objects.filter(household=self.household, kind="warning").exists())
        self.assertTrue(Notification.objects.filter(household=self.household, title="Taak binnenkort", body="Vuilnis buiten").exists())
        self.assertTrue(Notification.objects.filter(household=self.household, title="Afschrijving binnenkort", body__startswith="Verzekering").exists())

    def test_notification_can_be_marked_as_read(self):
        notification = Notification.objects.create(household=self.household, title="Test", dedupe_key="test")
        response = self.client.post(reverse("notifications:mark_read", args=[notification.id]), {"next": reverse("today")})
        self.assertRedirects(response, reverse("today"))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_notification_inbox_shows_only_the_active_household_and_unread_filter(self):
        unread = Notification.objects.create(household=self.household, title="Nieuwe melding", dedupe_key="unread")
        read = Notification.objects.create(household=self.household, title="Oude melding", dedupe_key="read", read_at=timezone.now())
        other_household = Household.objects.create(name="Ander gezin")
        Notification.objects.create(household=other_household, title="Privé", dedupe_key="private")

        response = self.client.get(reverse("notifications:index"))

        self.assertContains(response, unread.title)
        self.assertNotContains(response, read.title)
        self.assertNotContains(response, "Privé")
        response = self.client.get(f"{reverse('notifications:index')}?filter=alles")
        self.assertContains(response, read.title)
        self.assertNotContains(response, "Privé")

    def test_mark_all_read_only_marks_the_active_household(self):
        notification = Notification.objects.create(household=self.household, title="Test", dedupe_key="test-all")
        other_household = Household.objects.create(name="Ander gezin")
        private = Notification.objects.create(household=other_household, title="Privé", dedupe_key="private-all")

        response = self.client.post(reverse("notifications:mark_all_read"), {"next": reverse("notifications:index")})

        self.assertRedirects(response, reverse("notifications:index"))
        notification.refresh_from_db()
        private.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertIsNone(private.read_at)
