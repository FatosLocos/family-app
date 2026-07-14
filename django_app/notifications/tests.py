from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from household.models import Task
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
        CalendarEvent.objects.create(household=self.household, title="Ophalen", starts_at=timezone.now() + timedelta(hours=3), ends_at=timezone.now() + timedelta(hours=4))
        self.client.force_login(self.user)

    def test_background_job_generates_deduplicated_daily_signals(self):
        refresh_household_notifications()
        refresh_household_notifications()
        self.assertEqual(Notification.objects.filter(household=self.household).count(), 2)
        self.assertTrue(Notification.objects.filter(household=self.household, kind="warning").exists())

    def test_notification_can_be_marked_as_read(self):
        notification = Notification.objects.create(household=self.household, title="Test", dedupe_key="test")
        response = self.client.post(reverse("notifications:mark_read", args=[notification.id]), {"next": reverse("today")})
        self.assertRedirects(response, reverse("today"))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
