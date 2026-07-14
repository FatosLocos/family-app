import json
from unittest.mock import patch

from django.db import DatabaseError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from config import views
from household.models import Task
from households.models import Household, Membership
from identity.models import User


class HouseholdSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123")
        self.other_user = User.objects.create_user(username="ander@example.com", email="ander@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Eigen gezin")
        self.other_household = Household.objects.create(name="Ander gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(household=self.other_household, user=self.other_user, role=Membership.Role.OWNER)
        Task.objects.create(household=self.household, title="Tandarts bellen")
        Task.objects.create(household=self.other_household, title="Tandarts privé")
        self.client.force_login(self.user)

    def test_search_only_returns_active_household_records(self):
        response = self.client.get(reverse("search"), {"q": "tandarts"})
        self.assertContains(response, "Tandarts bellen")
        self.assertNotContains(response, "Tandarts privé")

    def test_short_search_returns_hint_in_htmx_partial(self):
        response = self.client.get(reverse("search"), {"q": "t"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Typ minimaal twee letters")

    def test_healthcheck_reports_database_failure(self):
        request = RequestFactory().get(reverse("healthz"))
        with patch("config.views.connection.cursor", side_effect=DatabaseError("database unavailable")):
            response = views.healthz(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["status"], "unavailable")

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_healthcheck_stays_available_for_internal_readiness_probe(self):
        health = self.client.get(reverse("healthz"), secure=False)
        homepage = self.client.get(reverse("today"), secure=False)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(homepage.status_code, 301)
