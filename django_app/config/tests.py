import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.db import DatabaseError, connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config import views
from family.models import Contact, ContactPerson
from home.models import HomeEntity
from household.models import MealPlan, Routine, Task
from households.models import Household, Membership
from identity.models import User


class HouseholdRlsPolicyTests(TestCase):
    """Every domain model with a direct household key must enforce RLS."""

    # These two tables establish an active household in middleware or resolve a
    # one-time invite before that scope exists. They are guarded by user/code
    # authorization rather than a household-id database setting.
    BOOTSTRAP_SCOPE_TABLES = {"households_membership", "households_householdinvite"}

    def test_all_household_scoped_models_have_forced_postgres_rls(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS is alleen van toepassing op PostgreSQL.")

        scoped_tables = sorted(
            {
                model._meta.db_table
                for model in apps.get_models()
                if not model._meta.auto_created
                and any(field.name == "household" for field in model._meta.fields)
                and model._meta.db_table not in self.BOOTSTRAP_SCOPE_TABLES
            }
        )
        for table in scoped_tables:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.relrowsecurity, c.relforcerowsecurity,
                           EXISTS(
                               SELECT 1 FROM pg_policies p
                               WHERE p.schemaname = current_schema()
                                 AND p.tablename = %s
                                 AND p.policyname = 'household_isolation'
                           )
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema() AND c.relname = %s
                    """,
                    [table, table],
                )
                policy = cursor.fetchone()
            self.assertEqual(policy, (True, True, True), table)

    def test_vps_rls_verification_covers_every_household_scoped_table(self):
        script = (Path(__file__).resolve().parents[1] / "ops" / "verify_rls.sh").read_text()
        scoped_tables = {
            model._meta.db_table
            for model in apps.get_models()
            if not model._meta.auto_created
            and any(field.name == "household" for field in model._meta.fields)
            and model._meta.db_table not in self.BOOTSTRAP_SCOPE_TABLES
        }

        missing = sorted(table for table in scoped_tables if f"('{table}')" not in script)

        self.assertEqual(missing, [], f"VPS RLS-verificatie mist: {', '.join(missing)}")


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
        HomeEntity.objects.create(household=self.household, entity_id="device.thermostaat", domain="climate", name="Thermostaat woonkamer", state="ready")
        HomeEntity.objects.create(household=self.other_household, entity_id="device.private", domain="climate", name="Thermostaat privé", state="ready")
        self.client.force_login(self.user)

    def test_search_only_returns_active_household_records(self):
        response = self.client.get(reverse("search"), {"q": "tandarts"})
        self.assertContains(response, "Tandarts bellen")
        self.assertNotContains(response, "Tandarts privé")

    def test_search_includes_only_active_household_devices(self):
        response = self.client.get(reverse("search"), {"q": "thermostaat"})

        self.assertContains(response, "Thermostaat woonkamer")
        self.assertNotContains(response, "Thermostaat privé")

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

    def test_offline_page_is_public_and_has_no_household_content(self):
        self.client.logout()

        response = self.client.get(reverse("offline"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Family App is tijdelijk offline.")
        self.assertNotContains(response, "mobile-dock")

    def test_service_worker_has_application_scope(self):
        response = self.client.get(reverse("service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, 'const OFFLINE_URL = "/offline/"')
        self.assertContains(response, 'const CACHE_NAME = "family-app-static-v7"')
        self.assertContains(response, 'caches.delete(key)')

    def test_authenticated_pages_reject_embedding_in_a_frame(self):
        response = self.client.get(reverse("today"))

        self.assertEqual(response["X-Frame-Options"], "DENY")

    @patch("config.views.timezone.localdate", return_value=date(2026, 7, 14))
    def test_today_shows_upcoming_birthdays_from_the_active_household(self, _localdate):
        contact = Contact.objects.create(household=self.household, name="Familie Jansen")
        ContactPerson.objects.create(household=self.household, contact=contact, name="Morgen", birth_date=date(2000, 7, 15))
        other_contact = Contact.objects.create(household=self.other_household, name="Andere familie")
        ContactPerson.objects.create(household=self.other_household, contact=other_contact, name="Privé verjaardag", birth_date=date(2000, 7, 15))

        response = self.client.get(reverse("today"))

        self.assertContains(response, "Verjaardagen")
        self.assertContains(response, "Morgen")
        self.assertContains(response, "wordt 26")
        self.assertNotContains(response, "Privé verjaardag")

    def test_today_shows_due_routines_and_planned_meals(self):
        MealPlan.objects.create(household=self.household, title="Pasta", planned_for=timezone.localdate())
        routine = Routine.objects.create(household=self.household, title="Afval buiten", next_due_on=timezone.localdate())

        response = self.client.get(reverse("today"))

        self.assertContains(response, "Vandaag thuis")
        self.assertContains(response, "Vanavond: Pasta")
        self.assertContains(response, routine.title)
        self.assertContains(response, reverse("household:complete_routine", args=[routine.id]))

    def test_today_can_toggle_a_task_without_leaving_the_dashboard(self):
        task = Task.objects.create(household=self.household, title="Afval buiten")

        response = self.client.get(reverse("today"))

        self.assertContains(response, f'hx-target="#today-task-{task.id}"')
        response = self.client.post(
            reverse("household:toggle_task", args=[task.id]),
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET=f"today-task-{task.id}",
        )
        self.assertContains(response, f'id="today-task-{task.id}"')
        self.assertContains(response, "is-complete")
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
