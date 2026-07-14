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
        guest = self.client_class()
        response = guest.get(reverse("households:accept_invite", args=[invite.code]))
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

    def test_child_cannot_create_invite_or_change_a_role(self):
        child = User.objects.create_user(username="kind@example.com", email="kind@example.com", password="safe-password-123")
        child_membership = Membership.objects.create(household=self.household, user=child, role=Membership.Role.CHILD)
        self.client.force_login(child)
        self.assertEqual(self.client.post(reverse("households:create_invite"), {"role": "child"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("households:update_member_role", args=[child_membership.id]), {"role": "parent"}).status_code, 403)
