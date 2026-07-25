from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from household.models import Task, TaskList
from households.models import Household, Membership
from identity.models import User
from travel.models import Trip, TripDocument, TripIdea, TripStop
from travel.services import ensure_trip_task_list


class TravelModuleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="safe-password-123", display_name="Ouder")
        self.child = User.objects.create_user(username="child@example.com", email="child@example.com", password="safe-password-123", display_name="Kind")
        self.outsider = User.objects.create_user(username="buren@example.com", email="buren@example.com", password="safe-password-123", display_name="Buurman")
        self.first_household = Household.objects.create(name="Eerste gezin")
        self.second_household = Household.objects.create(name="Tweede gezin")
        Membership.objects.create(user=self.owner, household=self.first_household, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.child, household=self.first_household, role=Membership.Role.CHILD)
        Membership.objects.create(user=self.outsider, household=self.second_household, role=Membership.Role.OWNER)
        self.trip = Trip.objects.create(household=self.first_household, destination="Barcelona", start_date=date(2026, 8, 1), end_date=date(2026, 8, 10))
        self.stop = TripStop.objects.create(household=self.first_household, trip=self.trip, name="Girona")
        self.document = TripDocument.objects.create(household=self.first_household, trip=self.trip, title="Vluchtbevestiging", url="https://example.com/ticket")
        self.idea = TripIdea.objects.create(household=self.first_household, trip=self.trip, text="Sagrada Familia bezoeken", author=self.owner)

    def test_travel_models_have_forced_household_rls(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS is alleen van toepassing op PostgreSQL.")

        for table in ("travel_trip", "travel_tripstop", "travel_tripdocument", "travel_tripidea"):
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
                row = cursor.fetchone()
            self.assertEqual(row, (True, True, True), table)

    def test_new_trip_gets_its_own_linked_task_list(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("travel:add_trip"), {"destination": "Ardennen", "start_date": "2026-10-01", "end_date": "2026-10-05"}, follow=True)

        self.assertEqual(response.status_code, 200)
        trip = Trip.objects.get(household=self.first_household, destination="Ardennen")
        self.assertIsNotNone(trip.task_list)
        self.assertEqual(trip.task_list.name, "Reis: Ardennen")
        self.assertEqual(trip.task_list.household, self.first_household)

    def test_trip_tasks_ride_along_in_the_normal_task_list(self):
        task_list = ensure_trip_task_list(self.trip)
        Task.objects.create(household=self.first_household, list=task_list, title="Koffers pakken")
        self.client.force_login(self.owner)

        response = self.client.get(f"{reverse('household:index')}?tab=taken")

        self.assertContains(response, "Reis: Barcelona")
        self.assertContains(response, "Koffers pakken")
        self.assertContains(response, "Hoort bij de reis naar Barcelona")

    def test_colliding_task_list_name_gets_a_numbered_suffix(self):
        ensure_trip_task_list(self.trip)
        claimed = Trip.objects.create(household=self.first_household, destination="Barcelona")

        task_list = ensure_trip_task_list(claimed)

        self.assertEqual(task_list.name, "Reis: Barcelona (2)")
        self.assertEqual(TaskList.objects.for_household(self.first_household).count(), 2)

    def test_free_task_list_with_the_same_name_is_reused_instead_of_duplicated(self):
        existing = TaskList.objects.create(household=self.first_household, name="Reis: Barcelona")

        task_list = ensure_trip_task_list(self.trip)

        self.assertEqual(task_list, existing)
        self.assertEqual(TaskList.objects.for_household(self.first_household).count(), 1)

    def test_deleting_a_trip_keeps_its_task_list(self):
        task_list = ensure_trip_task_list(self.trip)
        self.client.force_login(self.owner)

        self.client.post(reverse("travel:delete_trip", args=[self.trip.pk]))

        self.assertFalse(Trip.objects.filter(pk=self.trip.pk).exists())
        self.assertTrue(TaskList.objects.filter(pk=task_list.pk).exists())

    def test_return_date_before_departure_is_refused(self):
        self.client.force_login(self.owner)

        self.client.post(reverse("travel:add_trip"), {"destination": "IJsland", "start_date": "2026-08-10", "end_date": "2026-08-01"})

        self.assertFalse(Trip.objects.filter(destination="IJsland").exists())

    def test_document_needs_exactly_one_source(self):
        with self.assertRaises(ValidationError):
            TripDocument(household=self.first_household, trip=self.trip, title="Niets").full_clean()
        with self.assertRaises(ValidationError):
            TripDocument(household=self.first_household, trip=self.trip, title="Twee bronnen", url="https://example.com/a", dropbox_path="/Reizen/a.pdf").full_clean()

        TripDocument(household=self.first_household, trip=self.trip, title="Alleen een pad", dropbox_path="/Reizen/a.pdf").full_clean()

    def test_document_with_two_sources_is_refused_by_the_endpoint(self):
        self.client.force_login(self.owner)

        self.client.post(reverse("travel:add_document", args=[self.trip.pk]), {"title": "Twee bronnen", "url": "https://example.com/a", "dropbox_path": "/Reizen/a.pdf"})

        self.assertFalse(TripDocument.objects.filter(title="Twee bronnen").exists())

    def test_a_refused_upload_names_the_real_reason(self):
        self.client.force_login(self.owner)
        uploaded = SimpleUploadedFile("tickets.exe", b"nope", content_type="application/octet-stream")

        response = self.client.post(reverse("travel:add_document", args=[self.trip.pk]), {"title": "Tickets", "file": uploaded}, follow=True)

        self.assertContains(response, "Gebruik PDF, afbeelding of tekstbestand.")
        self.assertNotContains(response, "Kies precies één bron")
        self.assertFalse(TripDocument.objects.filter(title="Tickets").exists())

    def test_a_trip_without_a_task_list_can_be_linked_again(self):
        task_list = ensure_trip_task_list(self.trip)
        task_list.delete()
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.task_list)
        self.client.force_login(self.owner)

        overview = self.client.get(reverse("travel:index"))
        self.client.post(reverse("travel:link_task_list", args=[self.trip.pk]))

        self.assertContains(overview, "Takenlijst koppelen")
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.task_list.name, "Reis: Barcelona")

    def test_linking_a_task_list_twice_changes_nothing(self):
        task_list = ensure_trip_task_list(self.trip)
        self.client.force_login(self.owner)

        self.client.post(reverse("travel:link_task_list", args=[self.trip.pk]))

        self.trip.refresh_from_db()
        self.assertEqual(self.trip.task_list, task_list)
        self.assertEqual(TaskList.objects.for_household(self.first_household).count(), 1)

    def test_uploaded_document_is_downloadable_inside_the_household(self):
        self.client.force_login(self.owner)
        uploaded = SimpleUploadedFile("tickets.pdf", b"ticket", content_type="application/pdf")

        self.client.post(reverse("travel:add_document", args=[self.trip.pk]), {"title": "Tickets", "file": uploaded})

        document = TripDocument.objects.get(household=self.first_household, title="Tickets")
        self.assertTrue(document.file)
        self.assertEqual(self.client.get(reverse("travel:download_document", args=[document.pk])).status_code, 200)

    def test_child_can_add_an_idea_but_not_a_trip(self):
        self.client.force_login(self.child)

        idea_response = self.client.post(reverse("travel:add_idea", args=[self.trip.pk]), {"text": "Kajakken op de rivier"})
        trip_response = self.client.post(reverse("travel:add_trip"), {"destination": "Disneyland"})

        self.assertEqual(idea_response.status_code, 302)
        self.assertEqual(TripIdea.objects.get(text="Kajakken op de rivier").author, self.child)
        self.assertEqual(trip_response.status_code, 403)
        self.assertFalse(Trip.objects.filter(destination="Disneyland").exists())

    def test_index_lists_the_trip_with_its_stops_and_documents(self):
        self.client.force_login(self.owner)

        overview = self.client.get(reverse("travel:index"))
        documents = self.client.get(f"{reverse('travel:index')}?tab=documenten")
        ideas = self.client.get(f"{reverse('travel:index')}?tab=ideeen")

        self.assertContains(overview, "Barcelona")
        self.assertContains(overview, "Girona")
        self.assertContains(documents, "Vluchtbevestiging")
        self.assertContains(ideas, "Sagrada Familia bezoeken")

    def test_trip_is_found_through_the_global_search(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("search"), {"q": "Barcelona"})

        self.assertContains(response, "Barcelona")
        self.assertEqual([trip.pk for trip in response.context["trips"]], [self.trip.pk])

    def test_another_household_never_sees_a_trip_in_the_overview(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("travel:index"))

        self.assertEqual(response.context["trips"], [])
        self.assertContains(response, "Nog geen reizen vastgelegd.")

    def test_every_mutating_endpoint_is_not_found_for_another_household(self):
        self.client.force_login(self.outsider)
        endpoints = [
            ("travel:update_trip", [self.trip.pk], {"destination": "Overgenomen"}),
            ("travel:delete_trip", [self.trip.pk], {}),
            ("travel:add_stop", [self.trip.pk], {"name": "Ongewenst"}),
            ("travel:link_task_list", [self.trip.pk], {}),
            ("travel:delete_stop", [self.stop.pk], {}),
            ("travel:add_document", [self.trip.pk], {"title": "Ongewenst", "url": "https://example.com/x"}),
            ("travel:delete_document", [self.document.pk], {}),
            ("travel:add_idea", [self.trip.pk], {"text": "Ongewenst idee"}),
            ("travel:delete_idea", [self.idea.pk], {}),
        ]

        for name, args, data in endpoints:
            with self.subTest(endpoint=name):
                response = self.client.post(reverse(name, args=args), data)
                self.assertEqual(response.status_code, 404)

        self.trip.refresh_from_db()
        self.assertEqual(self.trip.destination, "Barcelona")
        self.assertIsNone(self.trip.task_list)
        self.assertTrue(TripStop.objects.filter(pk=self.stop.pk).exists())
        self.assertTrue(TripDocument.objects.filter(pk=self.document.pk).exists())
        self.assertTrue(TripIdea.objects.filter(pk=self.idea.pk).exists())
        self.assertEqual(TripStop.objects.filter(trip=self.trip).count(), 1)

    def test_downloading_a_document_of_another_household_is_not_found(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("travel:download_document", args=[self.document.pk]))

        self.assertEqual(response.status_code, 404)
