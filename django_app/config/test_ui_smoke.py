from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership
from identity.models import User


class SharedShellSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ouder@example.com",
            email="ouder@example.com",
            password="safe-password-123",
            display_name="Ouder",
        )
        self.household = Household.objects.create(name="Testgezin")
        Membership.objects.create(
            household=self.household,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.client.force_login(self.user)

    def test_core_modules_use_the_shared_shell(self):
        pages = (
            ("today", {}, "Vandaag"),
            ("family:index", {}, "Gezin"),
            ("household:index", {}, "Huishouden"),
            ("planning:index", {}, "Planning"),
            ("finance:index", {}, "Geld"),
            ("home:index", {}, "Huis"),
            ("integrations:index", {}, "Instellingen"),
        )

        for name, kwargs, label in pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(name, kwargs=kwargs))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Family App")
                self.assertContains(response, "css/ux.css")
                self.assertContains(response, 'class="mobile-dock"')
                self.assertContains(response, f'aria-label="{label}"')

    def test_current_module_is_exposed_as_the_active_navigation_item(self):
        response = self.client.get(reverse("household:index"))

        self.assertContains(
            response,
            'href="/huishouden/" aria-label="Huishouden" title="Huishouden" class="is-active" aria-current="page"',
        )
