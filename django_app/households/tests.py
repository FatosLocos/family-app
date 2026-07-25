from django.test import TestCase
from django.urls import reverse

from households.models import Household, HouseholdInvite, Membership
from identity.models import User


class InviteFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.owner, role=Membership.Role.OWNER)

    def test_invited_user_joins_the_existing_household_after_signup(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("households:create_invite"), {"role": "child", "label": "Kind"})
        invite = HouseholdInvite.objects.get(household=self.household)
        # Het model bewaart alleen code_hash; de leesbare code komt uit de sessie van de maker.
        code = self.client.session[f"invite_code_{invite.id}"]
        guest = self.client_class()
        response = guest.get(reverse("households:accept_invite", args=[code]))
        self.assertRedirects(response, reverse("identity:signup"))
        response = guest.get(reverse("identity:signup"))
        self.assertContains(response, "Sluit aan bij Gezin")
        self.assertNotContains(response, 'name="household_name"')
        response = guest.post(reverse("identity:signup"), {
            "display_name": "Nieuw kind", "email": "kind@example.com", "password1": "safe-password-123", "password2": "safe-password-123",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        child = User.objects.get(email="kind@example.com")
        self.assertTrue(Membership.objects.filter(household=self.household, user=child, role="child").exists())
        invite.refresh_from_db()
        self.assertEqual(invite.accepted_by, child)

    def test_new_user_creates_an_owned_household_during_signup(self):
        response = self.client.post(reverse("identity:signup"), {
            "display_name": "Nieuwe ouder",
            "household_name": "Nieuw gezin",
            "email": "nieuw@example.com",
            "password1": "safe-password-123",
            "password2": "safe-password-123",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="nieuw@example.com")
        self.assertTrue(Membership.objects.filter(
            household__name="Nieuw gezin",
            user=user,
            role=Membership.Role.OWNER,
        ).exists())

    def test_signup_leaves_the_new_user_logged_in(self):
        # Regressietest: met twee authenticatie-backends moet login() een expliciete backend
        # krijgen, anders faalt registreren met een ValueError en rolt alles terug.
        response = self.client.post(reverse("identity:signup"), {
            "display_name": "Ingelogde ouder",
            "household_name": "Ingelogd gezin",
            "email": "ingelogd@example.com",
            "password1": "safe-password-123",
            "password2": "safe-password-123",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], reverse("today"))
        user = User.objects.get(email="ingelogd@example.com")
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user, user)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        household = Household.objects.get(name="Ingelogd gezin")
        self.assertEqual(self.client.session["active_household_id"], household.pk)

    def test_signup_renders_the_specific_field_error(self):
        response = self.client.post(reverse("identity:signup"), {
            "display_name": "Nieuwe ouder",
            "household_name": "Nieuw gezin",
            "email": "nieuw@example.com",
            "password1": "password",
            "password2": "password",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="field-error"')
        self.assertContains(response, "Dit wachtwoord is te algemeen.")
        self.assertFalse(User.objects.filter(email="nieuw@example.com").exists())

    def test_child_cannot_create_invite_or_change_a_role(self):
        child = User.objects.create_user(username="kind@example.com", email="kind@example.com", password="safe-password-123")
        child_membership = Membership.objects.create(household=self.household, user=child, role=Membership.Role.CHILD)
        self.client.force_login(child)
        self.assertEqual(self.client.post(reverse("households:create_invite"), {"role": "child"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("households:update_member_role", args=[child_membership.id]), {"role": "parent"}).status_code, 403)
