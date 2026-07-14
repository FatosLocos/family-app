from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import BankAccount, Transaction
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.models import IntegrationAudit, IntegrationConnection
from integrations.providers import sync_bunq, sync_outlook
from integrations.tasks import sync_connection_task
from planning.models import CalendarEvent, CalendarSource


class FakeResponse:
    def __init__(self, payload, ok=True):
        self.payload = payload
        self.ok = ok
        self.content = b"{}"

    def json(self):
        return self.payload


class ProviderSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)

    def test_outlook_sync_creates_enabled_source_and_timezone_aware_event(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )

        def outlook_get(url, **_kwargs):
            if url.endswith("me/calendars?$select=id,name"):
                return FakeResponse({"value": [{"id": "calendar-1", "name": "Gezin"}]})
            return FakeResponse({"value": [{"id": "event-1", "subject": "Sport", "start": {"dateTime": "2026-07-13T09:00:00"}, "end": {"dateTime": "2026-07-13T10:00:00"}, "isAllDay": False, "location": {"displayName": "Hal"}}]})

        with patch("integrations.providers.requests.get", side_effect=outlook_get):
            result = sync_outlook(connection)

        self.assertEqual(result, {"calendars": 1, "events": 1})
        source = CalendarSource.objects.get(household=self.household, external_id="calendar-1")
        event = CalendarEvent.objects.get(household=self.household, external_id="event-1")
        self.assertEqual(source.name, "Gezin")
        self.assertTrue(timezone.is_aware(event.starts_at))
        self.assertEqual(event.location, "Hal")

    def test_bunq_sync_falls_back_to_user_endpoint_and_discovers_multiple_accounts(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="bunq",
            display_name="bunq",
            secret_encrypted=encrypt("bunq-oauth-token"),
            settings={"environment": "sandbox"},
        )
        calls = []

        def bunq_response(url, method, _token, _private_key, body=None):
            calls.append(url)
            if url.endswith("/installation"):
                return {"Response": [{"Token": {"token": "installation"}}]}
            if url.endswith("/device-server"):
                return {"Response": []}
            if url.endswith("/session-server"):
                return {"Response": [{"Token": {"token": "session"}}]}
            if url.endswith("/user"):
                return {"Response": [{"UserPerson": {"id": 42}}]}
            if "/payment?" in url:
                if "/1/" in url:
                    return {"Response": [{"Payment": {"id": 10, "created": "2026-07-13 09:00:00", "description": "Boodschappen", "amount": {"value": "-12.34", "currency": "EUR"}, "counterparty_alias": {"display_name": "Winkel"}}}]}
                return {"Response": []}
            if url.endswith("/monetary-account?count=200"):
                return {"Response": [{"MonetaryAccountBank": {"id": 1, "description": "Hoofdrekening", "alias": [{"type": "IBAN", "value": "NL00BUNQ0000000001"}], "balance": {"value": "10.00", "currency": "EUR"}}}]}
            if url.endswith("/monetary-account-savings?count=200"):
                return {"Response": [{"MonetaryAccountSavings": {"id": 2, "description": "Spaarrekening", "balance": {"value": "50.00", "currency": "EUR"}}}]}
            return {"Response": []}

        with patch("integrations.providers._bunq_request", side_effect=bunq_response):
            result = sync_bunq(connection)
            repeated_result = sync_bunq(connection)

        self.assertTrue(any(url.endswith("/user") for url in calls))
        self.assertEqual(result, {"accounts": 2, "new_transactions": 1})
        self.assertEqual(repeated_result, {"accounts": 2, "new_transactions": 0})
        self.assertEqual(BankAccount.objects.filter(household=self.household).count(), 2)
        self.assertEqual(Transaction.objects.filter(household=self.household).count(), 1)

    def test_sync_task_records_a_non_sensitive_audit_event(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
        )
        with patch("integrations.tasks.sync_connection", return_value={"calendars": 1, "events": 2}):
            sync_connection_task(connection.id, self.household.id)
        audit = IntegrationAudit.objects.get(household=self.household, connection=connection)
        self.assertEqual(audit.action, IntegrationAudit.Action.SYNC_SUCCEEDED)
        self.assertNotIn("token", audit.detail.lower())


class SettingsAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="safe-password-123", display_name="Eigenaar")
        self.child = User.objects.create_user(username="child@example.com", email="child@example.com", password="safe-password-123", display_name="Kind")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(household=self.household, user=self.child, role=Membership.Role.CHILD)

    def test_child_can_edit_own_profile_but_cannot_manage_household_or_connections(self):
        self.client.force_login(self.child)
        response = self.client.get(reverse("integrations:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Een ouder beheert")
        self.assertNotContains(response, "Outlook agenda")
        self.client.post(reverse("integrations:save_profile"), {"display_name": "Nieuw kind"})
        self.child.refresh_from_db()
        self.assertEqual(self.child.display_name, "Nieuw kind")
        self.assertEqual(self.client.post(reverse("integrations:save_household"), {"name": "Ander gezin"}).status_code, 403)

    def test_owner_can_rename_household(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("integrations:save_household"), {"name": "Familie Voorbeeld"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.household.refresh_from_db()
        self.assertEqual(self.household.name, "Familie Voorbeeld")

    def test_parent_can_disconnect_outlook_and_keep_an_audit_record(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.owner,
            provider="outlook",
            display_name="Werkagenda",
            secret_encrypted=encrypt("refresh-token"),
        )
        source = CalendarSource.objects.create(
            household=self.household,
            owner=self.owner,
            provider="outlook",
            external_id="agenda-1",
            name="Werk",
            is_read_only=True,
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("integrations:disconnect_connection", args=[connection.id]))
        self.assertRedirects(response, reverse("integrations:index"))
        self.assertFalse(IntegrationConnection.objects.filter(pk=connection.id).exists())
        self.assertFalse(CalendarSource.objects.filter(pk=source.id).exists())
        audit = IntegrationAudit.objects.get(household=self.household, action=IntegrationAudit.Action.DISCONNECTED)
        self.assertIsNone(audit.connection)
        self.assertEqual(audit.provider, "outlook")
