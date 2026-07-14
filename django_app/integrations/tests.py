import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import BankAccount, Transaction
from household.models import Task
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.models import IntegrationAppConfig, IntegrationAudit, IntegrationConnection, SyncRun
from integrations.providers import arm_hue_bridge_link, finish_hue_bridge_link, sync_bunq, sync_hue, sync_outlook
from integrations.services import save_app_config
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

    def test_sync_task_skips_a_connection_that_is_already_running(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
        )
        SyncRun.objects.create(household=self.household, connection=connection, status="running")

        with patch("integrations.tasks.sync_connection") as sync:
            result = sync_connection_task(connection.id, self.household.id)

        self.assertEqual(result, {"status": "already_running"})
        sync.assert_not_called()

    def test_hue_sync_stores_lights_as_household_entities(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            secret_encrypted=encrypt("refresh-token"),
            settings={
                "access_token": encrypt("access-token"),
                "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                "bridge_username": "bridge-user",
            },
        )
        lights = {
            "1": {
                "name": "Keuken",
                "type": "Extended color light",
                "state": {"on": True, "bri": 127, "reachable": True},
            },
            "2": {
                "name": "Hal",
                "type": "Dimmable light",
                "state": {"on": False, "bri": 80, "reachable": False},
            },
        }

        with patch("integrations.providers.requests.request", return_value=FakeResponse(lights)):
            result = sync_hue(connection)

        self.assertEqual(result, {"lights": 2})
        from home.models import HomeEntity

        kitchen = HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.1")
        self.assertEqual(kitchen.source, HomeEntity.Source.HUE)
        self.assertEqual(kitchen.connection, connection)
        self.assertEqual(kitchen.state, "on")
        self.assertEqual(kitchen.attributes["brightness"], 127)
        self.assertFalse(HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.2").is_available)

    def test_hue_bridge_confirmation_creates_the_bridge_username(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            settings={"app_id": "family-app"},
        )
        with patch(
            "integrations.providers._hue_request",
            side_effect=[{}, [{"success": {"username": "bridge-user"}}]],
        ) as hue_request:
            arm_hue_bridge_link(connection)
            finish_hue_bridge_link(connection)

        connection.refresh_from_db()
        self.assertEqual(connection.status, "needs_sync")
        self.assertEqual(connection.settings["bridge_username"], "bridge-user")
        self.assertEqual(hue_request.call_args_list[0].args[1:3], ("PUT", "/bridge/0/config"))
        self.assertEqual(hue_request.call_args_list[1].args[1:3], ("POST", "/bridge/"))


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

    def test_settings_renders_a_connection_waiting_for_authorization(self):
        IntegrationConnection.objects.create(
            household=self.household,
            user=self.owner,
            provider="outlook",
            display_name="Outlook agenda",
            status="needs_auth",
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wacht op toestemming")

    def test_parent_can_authorize_hue_without_exposing_tokens(self):
        save_app_config(
            self.household,
            "hue",
            "hue-client-id",
            "hue-client-secret",
            {"app_id": "family-app", "device_name": "Family App"},
        )
        self.client.force_login(self.owner)

        start = self.client.get(reverse("integrations:start_hue"))
        self.assertEqual(start.status_code, 302)
        params = parse_qs(urlparse(start["Location"]).query)
        self.assertEqual(params["client_id"], ["hue-client-id"])
        self.assertIn("state", params)

        token_response = FakeResponse({"access_token": "hue-access-token", "refresh_token": "hue-refresh-token", "expires_in": 3600})
        with patch("integrations.services.requests.post", return_value=token_response):
            callback = self.client.get(reverse("integrations:hue_callback"), {"code": "authorization-code", "state": params["state"][0]})

        self.assertRedirects(callback, reverse("integrations:index"))
        connection = IntegrationConnection.objects.get(household=self.household, provider=IntegrationConnection.Provider.HUE)
        self.assertEqual(connection.status, "needs_bridge_link")
        self.assertNotIn("hue-access-token", connection.settings["access_token"])
        self.assertNotIn("hue-refresh-token", connection.secret_encrypted)
        self.assertFalse(IntegrationAppConfig.objects.get(household=self.household, provider="hue").client_secret_encrypted.endswith("hue-client-secret"))

    def test_child_cannot_change_or_start_the_hue_connection(self):
        self.client.force_login(self.child)

        self.assertEqual(
            self.client.post(
                reverse("integrations:save_hue_config"),
                {"client_id": "client", "client_secret": "secret", "app_id": "family-app", "device_name": "Family App"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("integrations:start_hue")).status_code, 403)


class HouseholdDataExportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="safe-password-123")
        self.child = User.objects.create_user(username="child@example.com", email="child@example.com", password="safe-password-123")
        self.other_user = User.objects.create_user(username="other@example.com", email="other@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Eigen gezin")
        self.other_household = Household.objects.create(name="Ander gezin")
        Membership.objects.create(household=self.household, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(household=self.household, user=self.child, role=Membership.Role.CHILD)
        Membership.objects.create(household=self.other_household, user=self.other_user, role=Membership.Role.OWNER)
        Task.objects.create(household=self.household, title="Eigen taak")
        Task.objects.create(household=self.other_household, title="Andere taak")
        IntegrationConnection.objects.create(household=self.household, user=self.owner, provider="outlook", display_name="Outlook", secret_encrypted=encrypt("gevoelig-token"))

    def test_owner_can_export_only_own_household_data_without_secrets(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:export_household_data"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        payload = json.loads(response.content)
        self.assertEqual(payload["household"]["name"], "Eigen gezin")
        self.assertEqual([task["title"] for task in payload["household_data"]["tasks"]], ["Eigen taak"])
        self.assertNotIn("gevoelig-token", response.content.decode())
        self.assertNotIn("secret_encrypted", response.content.decode())

    def test_child_cannot_export_household_data(self):
        self.client.force_login(self.child)

        self.assertEqual(self.client.get(reverse("integrations:export_household_data")).status_code, 403)
