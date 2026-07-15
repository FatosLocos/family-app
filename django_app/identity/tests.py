from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from identity.models import User


class PasswordResetTests(TestCase):
    def test_valid_reset_link_changes_password_once(self):
        user = User.objects.create_user(
            username="ouder@example.com",
            email="ouder@example.com",
            password="BestaandWachtwoord!2026",
            display_name="Ouder",
        )
        url = reverse("identity:password_reset_confirm", args=[
            urlsafe_base64_encode(force_bytes(user.pk)),
            default_token_generator.make_token(user),
        ])

        response = self.client.get(url, follow=True)
        self.assertContains(response, "Nieuw wachtwoord")
        response = self.client.post(response.request["PATH_INFO"], {
            "new_password1": "NieuweReset!2026",
            "new_password2": "NieuweReset!2026",
        }, follow=True)

        self.assertRedirects(response, reverse("identity:login"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("NieuweReset!2026"))
