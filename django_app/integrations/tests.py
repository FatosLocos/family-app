import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import BankAccount, Transaction
from home.models import HomeEntity
from household.models import Task
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.local_probe import ProbeError, apply_discovery, apply_inventory, authenticate_probe, create_pairing, mark_probe_offline, pair_probe, revoke_probe
from integrations.models import IntegrationAppConfig, IntegrationAudit, IntegrationConnection, LocalDiscovery, LocalProbe, SyncRun
from integrations.providers import HueProviderError, _hue_hex_from_xy, _hue_optional_resource, _hue_supports_color, _hue_xy_from_hex, arm_hue_bridge_link, control_connected_home_entity, control_hue_light, finish_hue_bridge_link, sync_bunq, sync_google_home, sync_hue, sync_lg_thinq, sync_outlook, sync_sonos
from integrations.services import get_sonos_event_callback_token, save_app_config, save_sonos_config
from integrations.sonos_events import sonos_event_signature
from integrations.tasks import sync_connection_task
from planning.models import CalendarEvent, CalendarSource


class FakeResponse:
    def __init__(self, payload, ok=True):
        self.payload = payload
        self.ok = ok
        self.content = b"{}"

    def json(self):
        return self.payload


class LocalProbeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="probe-ouder@example.com", email="probe-ouder@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Probe gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)

    def test_pairing_is_one_time_and_token_is_required(self):
        pending, code = create_pairing(self.household)
        probe, token = pair_probe(code, "Raspberry Pi", "0.1.0")

        self.assertEqual(probe.id, pending.id)
        self.assertEqual(probe.status, "online")
        self.assertEqual(authenticate_probe(str(probe.id), token).name, "Raspberry Pi")
        with self.assertRaises(ProbeError):
            pair_probe(code, "Tweede", "0.1.0")
        revoke_probe(probe)
        with self.assertRaises(ProbeError):
            authenticate_probe(str(probe.id), token)

    def test_disconnected_probe_is_not_left_as_online(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")

        mark_probe_offline(probe)

        probe.refresh_from_db()
        self.assertEqual(probe.status, "offline")

    def test_inventory_matches_cloud_entity_and_stores_probe_origin(self):
        connection = IntegrationConnection.objects.create(household=self.household, user=self.user, provider="hue", display_name="Hue")
        cloud_entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id="hue.1.light-1",
            domain="light",
            name="Oude naam",
            attributes={"hue_light_id": "light-1", "hue_group_name": "Keuken"},
        )
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")

        count = apply_inventory(probe, [{"source": "hue", "local_key": "light:light-1", "external_id": "light-1", "domain": "light", "name": "Keuken", "state": "on", "is_available": True, "is_supported": True, "attributes": {"hue_light_id": "light-1", "brightness": 55}}])

        self.assertEqual(count, 1)
        self.assertEqual(HomeEntity.objects.filter(household=self.household, source="hue").count(), 1)
        cloud_entity.refresh_from_db()
        self.assertEqual(cloud_entity.name, "Keuken")
        self.assertEqual(cloud_entity.attributes["probe_id"], str(probe.id))
        self.assertEqual(cloud_entity.attributes["probe_name"], "Laptop")
        self.assertEqual(cloud_entity.attributes["brightness"], 55)
        self.assertEqual(cloud_entity.attributes["hue_group_name"], "Keuken")

    def test_discovery_is_read_only_and_scoped_to_probe(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        result = apply_discovery(probe, [{"key": "uuid:device-1", "name": "Printer", "kind": "UPnP", "address": "192.168.1.30", "method": "ssdp", "details": {"model": "test"}}])

        self.assertEqual(result, 1)
        device = LocalDiscovery.objects.get(probe=probe)
        self.assertEqual(device.name, "Printer")
        self.assertFalse(HomeEntity.objects.filter(household=self.household, name="Printer").exists())

    def test_parent_can_create_pairing_and_probe_can_pair_over_json_api(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("integrations:create_local_probe_pairing"))
        self.assertRedirects(response, reverse("integrations:index"))
        LocalProbe.objects.get(household=self.household, status="pairing")
        _, code = create_pairing(self.household)

        response = self.client.post(reverse("integrations:local_probe_pair"), data=json.dumps({"code": code, "name": "Test probe", "version": "0.1"}), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LocalProbe.objects.filter(household=self.household, status="online").count(), 1)
        self.assertIn("/ws/probe/", response.json()["websocket_url"])

    def test_parent_can_download_a_clean_local_probe_archive(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("integrations:download_local_probe"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        archive = ZipFile(BytesIO(b"".join(response.streaming_content)))
        self.assertIn("family-app-probe/family_app_probe/main.py", archive.namelist())
        self.assertNotIn("family-app-probe/config.json", archive.namelist())

    def test_integrations_page_shows_probe_download_and_guide(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("integrations:index"))

        self.assertContains(response, reverse("integrations:download_local_probe"))
        self.assertContains(response, 'id="local-probe-guide"')
        self.assertContains(response, "Lokale probe installeren")


class ProviderSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)

    def test_hue_empty_color_capability_still_supports_color_control(self):
        self.assertTrue(_hue_supports_color({"color": {}}))
        self.assertFalse(_hue_supports_color({}))

    def test_sonos_sync_creates_groups_and_individual_speakers(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        with patch(
            "integrations.providers.requests.request",
            side_effect=[
                FakeResponse({"households": [{"id": "household-1"}]}),
                FakeResponse({"items": [{"id": "favorite-1", "name": "Ochtendmuziek"}]}),
                FakeResponse({"groups": [{"id": "group-1", "name": "Woonkamer", "coordinatorId": "player-1", "playbackState": "PLAYBACK_STATE_PLAYING", "playerIds": ["player-1", "player-2"]}], "players": [{"id": "player-1", "name": "Woonkamer links", "capabilities": ["PLAYBACK"]}, {"id": "player-2", "name": "Woonkamer rechts", "capabilities": ["PLAYBACK"]}]}),
                FakeResponse({"volume": 31, "muted": False}),
                FakeResponse({"playbackState": "PLAYBACK_STATE_PLAYING", "availablePlaybackActions": {"canSkip": True, "canSkipBack": True, "canShuffle": True, "canRepeat": True}, "playModes": {"shuffle": False, "repeat": False}}),
                FakeResponse({"container": {"type": "music"}, "currentItem": {"track": {"name": "Testnummer", "artist": {"name": "Testartiest"}, "service": {"name": "Sonos Radio"}}}, "nextItem": {"track": {"name": "Volgend nummer"}}}),
                FakeResponse({"volume": 25, "muted": False, "fixed": False}),
                FakeResponse({"volume": 26, "muted": True, "fixed": False}),
            ],
        ):
            result = sync_sonos(connection)
        from home.models import HomeEntity

        entity = HomeEntity.objects.get(household=self.household, entity_id=f"sonos.{connection.id}.group.group-1")
        self.assertEqual(result, {"households": 1, "groups": 1, "players": 2})
        self.assertEqual(entity.source, HomeEntity.Source.SONOS)
        self.assertEqual(entity.domain, "media_player")
        self.assertEqual(entity.state, "on")
        self.assertEqual(entity.attributes["sonos_member_names"], ["Woonkamer links", "Woonkamer rechts"])
        self.assertEqual(entity.attributes["sonos_now_playing_title"], "Testnummer")
        self.assertEqual(entity.attributes["sonos_source_name"], "Sonos Radio")
        self.assertTrue(entity.attributes["sonos_can_next"])
        self.assertEqual(entity.attributes["sonos_favorites"], [{"id": "favorite-1", "name": "Ochtendmuziek"}])
        player = HomeEntity.objects.get(household=self.household, entity_id=f"sonos.{connection.id}.player.player-2")
        self.assertEqual(player.domain, "speaker")
        self.assertEqual(player.attributes["sonos_volume"], 26)
        self.assertTrue(player.attributes["sonos_muted"])

    def test_google_home_sync_creates_a_climate_entity_for_a_nest_thermostat(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.GOOGLE_HOME,
            display_name="Google Home",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(), "project_id": "project-1"},
        )
        payload = {"devices": [{"name": "enterprises/project-1/devices/device-1", "type": "sdm.devices.types.THERMOSTAT", "traits": {"sdm.devices.traits.Info": {"customName": "Thermostaat"}, "sdm.devices.traits.Temperature": {"ambientTemperatureCelsius": 20.5}, "sdm.devices.traits.ThermostatTemperatureSetpoint": {"heatCelsius": 19.0}, "sdm.devices.traits.OnOff": {"on": True}}, "parentRelations": [{"displayName": "Woonkamer"}]}]}
        with patch("integrations.providers.requests.request", return_value=FakeResponse(payload)):
            result = sync_google_home(connection)
        from home.models import HomeEntity

        entity = HomeEntity.objects.get(household=self.household, entity_id=f"google_home.{connection.id}.device-1")
        self.assertEqual(result, {"devices": 1})
        self.assertEqual(entity.source, HomeEntity.Source.GOOGLE_HOME)
        self.assertEqual(entity.domain, "climate")
        self.assertEqual(entity.attributes["google_locations"], ["Woonkamer"])

    def test_lg_thinq_sync_uses_configured_device_path(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.LG_THINQ,
            display_name="LG ThinQ",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(), "api_base_url": "https://thinq.example.test/api", "devices_path": "/v2/user/devices"},
        )
        save_app_config(self.household, "lg_thinq", "client-id", "client-secret", {"token_url": "https://thinq.example.test/oauth/token"})
        with patch("integrations.providers.requests.get", return_value=FakeResponse({"devices": [{"deviceId": "dryer-1", "alias": "Droger", "deviceType": "DRYER"}]})) as request_get:
            result = sync_lg_thinq(connection)
        from home.models import HomeEntity

        self.assertEqual(result, {"devices": 1})
        self.assertEqual(request_get.call_args.args[0], "https://thinq.example.test/api/v2/user/devices")
        self.assertEqual(HomeEntity.objects.get(household=self.household, entity_id=f"lg_thinq.{connection.id}.dryer-1").name, "Droger")

    def test_sonos_sync_subscribes_to_events_when_enabled(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        save_sonos_config(self.household, "sonos-client", "sonos-secret", True)
        with patch(
            "integrations.providers.requests.request",
            side_effect=[
                FakeResponse({"households": [{"id": "household-1"}]}),
                FakeResponse({"items": []}),
                FakeResponse({"groups": [{"id": "group-1", "name": "Woonkamer", "playbackState": "PLAYBACK_STATE_PAUSED"}]}),
                FakeResponse({}),
                FakeResponse({}),
                FakeResponse({}),
                FakeResponse({}),
                FakeResponse({}),
                FakeResponse({}),
                FakeResponse({}),
                FakeResponse({}),
            ],
        ) as request:
            sync_sonos(connection)

        self.assertEqual(request.call_count, 10)
        connection.refresh_from_db()
        self.assertEqual(connection.settings["sonos_events_status"], "active")

    def test_sonos_controls_groups_for_playback_and_players_for_volume(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        from home.models import HomeEntity

        group = HomeEntity.objects.create(household=self.household, connection=connection, source=HomeEntity.Source.SONOS, entity_id="sonos.group-1", domain="media_player", name="Woonkamer", attributes={"sonos_entity_type": "group", "sonos_household_id": "household-1", "sonos_group_id": "group-1", "sonos_favorites": [{"id": "favorite-1", "name": "Ochtendmuziek"}]})
        player = HomeEntity.objects.create(household=self.household, connection=connection, source=HomeEntity.Source.SONOS, entity_id="sonos.player-1", domain="speaker", name="Keuken", attributes={"sonos_entity_type": "player", "sonos_household_id": "household-1", "sonos_player_id": "player-1"})

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            self.assertEqual(control_connected_home_entity(group, "on"), "Sonos speelt af.")
            self.assertEqual(control_connected_home_entity(player, "set_volume", "42"), "Volume ingesteld op 42%.")
            self.assertEqual(control_connected_home_entity(group, "next"), "Volgende nummer gekozen.")
            self.assertEqual(control_connected_home_entity(group, "load_favorite", "favorite-1"), "Sonos-favoriet gestart.")
            self.assertEqual(control_connected_home_entity(group, "set_group", ["player-1"]), "Sonos-groep bijgewerkt.")

        self.assertIn("/groups/group-1/playback/play", request.call_args_list[0].args[1])
        self.assertIn("/players/player-1/playerVolume", request.call_args_list[1].args[1])
        self.assertEqual(request.call_args_list[1].kwargs["json"], {"volume": 42})
        self.assertIn("/groups/group-1/playback/skipToNextTrack", request.call_args_list[2].args[1])
        self.assertIn("/groups/group-1/favorites", request.call_args_list[3].args[1])
        self.assertEqual(request.call_args_list[3].kwargs["json"], {"favoriteId": "favorite-1", "action": "PLAY_NOW", "playOnCompletion": True})
        self.assertIn("/households/household-1/groups/createGroup", request.call_args_list[4].args[1])
        self.assertEqual(request.call_args_list[4].kwargs["json"], {"playerIds": ["player-1"], "musicContextGroupId": "group-1"})

    def test_signed_sonos_event_updates_group_and_ignores_duplicates(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
            settings={"sonos_household_id": "household-1"},
        )
        from home.models import HomeEntity

        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SONOS,
            entity_id=f"sonos.{connection.id}.group.group-1",
            domain="media_player",
            name="Woonkamer",
            state="off",
        )
        save_sonos_config(self.household, "sonos-client", "sonos-secret", True)
        callback_token = get_sonos_event_callback_token(self.household)
        headers = {
            "X-Sonos-Household-Id": "household-1",
            "X-Sonos-Event-Seq-Id": "42",
            "X-Sonos-Namespace": "playback",
            "X-Sonos-Type": "playbackStatus",
            "X-Sonos-Target-Type": "groupId",
            "X-Sonos-Target-Value": "group-1",
        }
        signature = sonos_event_signature(headers, "sonos-client", "sonos-secret")
        response = self.client.post(
            reverse("integrations:sonos_event_callback", args=[self.household.id, callback_token]),
            data=json.dumps({"playbackState": "PLAYBACK_STATE_PLAYING"}),
            content_type="application/json",
            **{f"HTTP_{key.upper().replace('-', '_')}": value for key, value in {**headers, "X-Sonos-Event-Signature": signature}.items()},
        )

        self.assertEqual(response.status_code, 200)
        entity.refresh_from_db()
        self.assertEqual(entity.state, "on")
        duplicate = self.client.post(
            reverse("integrations:sonos_event_callback", args=[self.household.id, callback_token]),
            data=json.dumps({"playbackState": "PLAYBACK_STATE_PAUSED"}),
            content_type="application/json",
            **{f"HTTP_{key.upper().replace('-', '_')}": value for key, value in {**headers, "X-Sonos-Event-Signature": signature}.items()},
        )
        self.assertEqual(duplicate.status_code, 200)
        entity.refresh_from_db()
        self.assertEqual(entity.state, "on")

    def test_sonos_metadata_event_updates_now_playing_details(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
            settings={"sonos_household_id": "household-1", "sonos_household_ids": ["household-1"]},
        )
        from home.models import HomeEntity

        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SONOS,
            entity_id=f"sonos.{connection.id}.group.group-1",
            domain="media_player",
            name="Woonkamer",
        )
        save_sonos_config(self.household, "sonos-client", "sonos-secret", True)
        callback_token = get_sonos_event_callback_token(self.household)
        headers = {
            "X-Sonos-Household-Id": "household-1",
            "X-Sonos-Event-Seq-Id": "43",
            "X-Sonos-Namespace": "playbackMetadata",
            "X-Sonos-Type": "metadataStatus",
            "X-Sonos-Target-Type": "groupId",
            "X-Sonos-Target-Value": "group-1",
        }
        signature = sonos_event_signature(headers, "sonos-client", "sonos-secret")
        response = self.client.post(
            reverse("integrations:sonos_event_callback", args=[self.household.id, callback_token]),
            data=json.dumps({"container": {"type": "linein.homeTheater", "name": "TV Audio"}}),
            content_type="application/json",
            **{f"HTTP_{key.upper().replace('-', '_')}": value for key, value in {**headers, "X-Sonos-Event-Signature": signature}.items()},
        )

        self.assertEqual(response.status_code, 200)
        entity.refresh_from_db()
        self.assertEqual(entity.attributes["sonos_now_playing_title"], "TV Audio")
        self.assertEqual(entity.attributes["sonos_source_type"], "linein.homeTheater")

    def test_sonos_event_rejects_an_invalid_signature(self):
        save_sonos_config(self.household, "sonos-client", "sonos-secret", True)
        callback_token = get_sonos_event_callback_token(self.household)
        response = self.client.post(
            reverse("integrations:sonos_event_callback", args=[self.household.id, callback_token]),
            data="{}",
            content_type="application/json",
            HTTP_X_SONOS_HOUSEHOLD_ID="household-1",
            HTTP_X_SONOS_EVENT_SEQ_ID="1",
            HTTP_X_SONOS_NAMESPACE="playback",
            HTTP_X_SONOS_TYPE="playbackStatus",
            HTTP_X_SONOS_TARGET_TYPE="groupId",
            HTTP_X_SONOS_TARGET_VALUE="group-1",
            HTTP_X_SONOS_EVENT_SIGNATURE="not-valid",
        )

        self.assertEqual(response.status_code, 403)

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

    def test_sync_task_uses_the_queued_run_created_by_the_interface(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
        )
        queued_run = SyncRun.objects.create(household=self.household, connection=connection, status="queued")

        with patch("integrations.tasks.sync_connection", return_value={"calendars": 1, "events": 2}):
            sync_connection_task(connection.id, self.household.id, queued_run.id)

        queued_run.refresh_from_db()
        self.assertEqual(queued_run.status, "succeeded")
        self.assertEqual(queued_run.detail, "{'calendars': 1, 'events': 2}")

    def test_periodic_sync_adopts_an_existing_queued_run(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
        )
        queued_run = SyncRun.objects.create(household=self.household, connection=connection, status="queued")

        with patch("integrations.tasks.sync_connection", return_value={"calendars": 1, "events": 2}):
            sync_connection_task(connection.id, self.household.id)

        queued_run.refresh_from_db()
        self.assertEqual(queued_run.status, "succeeded")
        self.assertEqual(SyncRun.objects.filter(household=self.household, connection=connection).count(), 1)

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
        lights = {"data": [
            {"id": "light-1", "on": {"on": True}, "dimming": {"brightness": 50.0}, "color": {"xy": {"x": 0.6401, "y": 0.33}}, "effects_v2": {"status": "no_effect", "effect_values": ["no_effect", "prism"]}},
            {"id": "light-2", "on": {"on": False}, "dimming": {"brightness": 31.5}},
        ]}
        devices = {"data": [
            {"metadata": {"name": "Keuken"}, "product_data": {"product_name": "Hue White and Color Ambiance", "model_id": "LCA001", "manufacturer_name": "Signify Netherlands B.V."}, "services": [{"rtype": "light", "rid": "light-1"}, {"rtype": "motion", "rid": "motion-1"}, {"rtype": "temperature", "rid": "temperature-1"}, {"rtype": "light_level", "rid": "light-level-1"}]},
            {"metadata": {"name": "Hal"}, "services": [{"rtype": "light", "rid": "light-2"}]},
        ]}

        rooms = {"data": [{"id": "room-1", "metadata": {"name": "Keuken"}, "children": [{"rid": "device-1", "rtype": "device"}]}]}
        zones = {"data": []}
        grouped_lights = {"data": [{"id": "group-1", "owner": {"rid": "room-1", "rtype": "room"}, "on": {"on": True}, "dimming": {"brightness": 50.0}, "effects_v2": {"status": "no_effect", "effect_values": ["no_effect", "prism"]}}]}
        scenes = {"data": [{"id": "scene-1", "metadata": {"name": "Koken"}, "group": {"rid": "room-1", "rtype": "room"}, "status": {"active": True}}]}
        motion = {"data": [{"id": "motion-1", "motion": {"motion": True, "motion_valid": True}}]}
        temperature = {"data": [{"id": "temperature-1", "temperature": {"temperature": 2150, "temperature_valid": True}}]}
        light_level = {"data": [{"id": "light-level-1", "light": {"light_level": 12000, "light_level_valid": True}}]}
        device_power = {"data": [{"id": "power-1", "owner": {"rid": "device-1", "rtype": "device"}, "power_state": {"battery_level": 64, "battery_state": "normal"}}]}
        connectivity = {"data": [{"id": "connectivity-1", "owner": {"rid": "device-1", "rtype": "device"}, "status": "connected"}]}
        devices["data"][0]["id"] = "device-1"

        with patch(
            "integrations.providers.requests.request",
            side_effect=[FakeResponse(lights), FakeResponse(devices), FakeResponse(rooms), FakeResponse(zones), FakeResponse(grouped_lights), FakeResponse(scenes), FakeResponse(motion), FakeResponse(temperature), FakeResponse(light_level), FakeResponse({"data": []}), FakeResponse({"data": []}), FakeResponse(device_power), FakeResponse(connectivity)],
        ) as request:
            result = sync_hue(connection)

        self.assertEqual(result, {"lights": 2, "groups": 1, "sensors": 3, "scenes": 1})
        from home.models import HomeEntity

        kitchen = HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.light-1")
        self.assertEqual(kitchen.source, HomeEntity.Source.HUE)
        self.assertEqual(kitchen.connection, connection)
        self.assertEqual(kitchen.name, "Keuken")
        self.assertEqual(kitchen.state, "on")
        self.assertEqual(kitchen.attributes["brightness"], 50.0)
        self.assertTrue(kitchen.attributes["supports_dimming"])
        self.assertTrue(kitchen.attributes["supports_effects"])
        self.assertEqual(kitchen.attributes["effect_values"], ["no_effect", "prism"])
        self.assertEqual(kitchen.attributes["hue_product_name"], "Hue White and Color Ambiance")
        self.assertEqual(kitchen.attributes["hue_model_id"], "LCA001")
        self.assertEqual(kitchen.attributes["hue_battery_level"], 64)
        self.assertEqual(kitchen.attributes["hue_connectivity"], "connected")
        self.assertTrue(HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.light-2").is_available)
        group = HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.grouped_light.group-1")
        self.assertEqual(group.name, "Keuken")
        self.assertTrue(group.attributes["supports_color"])
        self.assertEqual(group.attributes["color_hex"], "#ff0000")
        self.assertFalse(group.attributes["color_mixed"])
        self.assertTrue(group.attributes["supports_effects"])
        self.assertEqual(group.attributes["member_names"], ["Keuken"])
        motion_sensor = HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.sensor.motion.motion-1")
        self.assertEqual(motion_sensor.name, "Keuken · Beweging")
        self.assertEqual(motion_sensor.state, "Beweging")
        self.assertFalse(motion_sensor.is_supported)
        self.assertEqual(motion_sensor.attributes["hue_locations"], ["Keuken"])
        self.assertEqual(HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.sensor.temperature.temperature-1").state, "21,5 °C")
        self.assertEqual(HomeEntity.objects.get(household=self.household, entity_id=f"hue.{connection.id}.scene.scene-1").state, "active")
        self.assertEqual(request.call_args_list[0].args[1], "https://api.meethue.com/route/clip/v2/resource/light")
        self.assertEqual(request.call_args_list[1].args[1], "https://api.meethue.com/route/clip/v2/resource/device")
        self.assertEqual(request.call_args_list[0].kwargs["headers"]["hue-application-key"], "bridge-user")

    def test_missing_optional_hue_resource_does_not_fail_sync(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
        )

        with patch("integrations.providers._hue_request", side_effect=HueProviderError("Niet gevonden.", 404)):
            self.assertEqual(_hue_optional_resource(connection, "contact"), [])

    def test_hue_bridge_confirmation_creates_the_bridge_username(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            settings={},
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
        self.assertEqual(hue_request.call_args_list[0].args[1:3], ("PUT", "/route/api/0/config"))
        self.assertEqual(hue_request.call_args_list[1].args[1:3], ("POST", "/route/api"))

    def test_finishing_hue_bridge_queues_a_visible_sync_run(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            status="awaiting_bridge_link",
        )
        self.client.force_login(self.user)

        with patch("integrations.views.finish_hue_bridge_link") as finish, patch("integrations.views.sync_connection_task.delay") as delay:
            response = self.client.post(reverse("integrations:finish_hue_bridge", args=[connection.id]))

        self.assertRedirects(response, reverse("integrations:index"), fetch_redirect_response=False)
        finish.assert_called_once_with(connection)
        sync_run = SyncRun.objects.get(household=self.household, connection=connection)
        self.assertEqual(sync_run.status, "queued")
        delay.assert_called_once_with(connection.id, self.household.id, sync_run.id)

    def test_hue_light_control_uses_the_v2_resource_and_application_key(self):
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
        from home.models import HomeEntity

        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id=f"hue.{connection.id}.light-1",
            domain="light",
            name="Keuken",
            attributes={"hue_light_id": "light-1"},
        )

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            detail = control_hue_light(entity, "brightness", "42.5")

        self.assertEqual(detail, "Helderheid ingesteld op 42%.")
        self.assertEqual(request.call_args.args[1], "https://api.meethue.com/route/clip/v2/resource/light/light-1")
        self.assertEqual(request.call_args.kwargs["headers"]["hue-application-key"], "bridge-user")
        self.assertEqual(request.call_args.kwargs["json"], {"on": {"on": True}, "dimming": {"brightness": 42.5}})

    def test_hue_scene_and_color_temperature_use_v2_resources(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(), "bridge_username": "bridge-user"},
        )
        from home.models import HomeEntity

        scene = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id=f"hue.{connection.id}.scene.1",
            domain="scene",
            name="Ontspannen",
            attributes={"hue_scene_id": "scene-1", "hue_resource_type": "scene"},
        )
        light = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id=f"hue.{connection.id}.light.1",
            domain="light",
            name="Keuken",
            attributes={"hue_light_id": "light-1", "color_temperature_min": 153, "color_temperature_max": 500, "supports_color": True, "supports_effects": True, "effects_resource": "effects_v2", "effects_action_key": "action", "effect_values": ["no_effect", "prism"]},
        )
        group = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id=f"hue.{connection.id}.group.1",
            domain="group",
            name="Woonkamer",
            attributes={"hue_grouped_light_id": "group-1", "hue_resource_type": "grouped_light", "supports_color": True},
        )

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            self.assertEqual(control_hue_light(scene, "activate"), "Scène gestart.")
            self.assertEqual(control_hue_light(light, "color_temperature", "240"), "Kleurtemperatuur ingesteld.")
            self.assertEqual(control_hue_light(light, "color", "#ff0000"), "Kleur ingesteld.")
            self.assertEqual(control_hue_light(light, "effect", "prism"), "Lichteffect prism ingesteld.")
            self.assertEqual(control_hue_light(group, "color", "#00ff00"), "Kleur ingesteld.")

        self.assertEqual(request.call_args_list[0].args[1], "https://api.meethue.com/route/clip/v2/resource/scene/scene-1")
        self.assertEqual(request.call_args_list[0].kwargs["json"], {"recall": {"action": "active"}})
        self.assertEqual(request.call_args_list[1].args[1], "https://api.meethue.com/route/clip/v2/resource/light/light-1")
        self.assertEqual(request.call_args_list[1].kwargs["json"], {"on": {"on": True}, "color_temperature": {"mirek": 240}})
        self.assertEqual(request.call_args_list[2].args[1], "https://api.meethue.com/route/clip/v2/resource/light/light-1")
        self.assertEqual(request.call_args_list[2].kwargs["json"], {"on": {"on": True}, "color": {"xy": {"x": 0.6401, "y": 0.33}}})
        self.assertEqual(request.call_args_list[3].kwargs["json"], {"effects_v2": {"action": "prism"}})
        self.assertEqual(request.call_args_list[4].args[1], "https://api.meethue.com/route/clip/v2/resource/grouped_light/group-1")
        self.assertEqual(request.call_args_list[4].kwargs["json"], {"on": {"on": True}, "color": {"xy": {"x": 0.3, "y": 0.6}}})

    def test_hue_color_is_constrained_to_the_lamp_gamut(self):
        gamut = {
            "red": {"x": 0.6, "y": 0.3},
            "green": {"x": 0.3, "y": 0.6},
            "blue": {"x": 0.3, "y": 0.3},
        }

        self.assertEqual(_hue_xy_from_hex("#ff0000", gamut), {"x": 0.6, "y": 0.3})
        self.assertEqual(_hue_hex_from_xy({"x": 0.6401, "y": 0.33}, 100), "#ff0000")


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

    def test_sync_connection_returns_to_a_safe_requested_page(self):
        connection = IntegrationConnection.objects.create(household=self.household, user=self.owner, provider="hue", display_name="Philips Hue")
        self.client.force_login(self.owner)

        with patch("integrations.views.sync_connection_task.delay") as sync:
            response = self.client.post(reverse("integrations:sync_connection", args=[connection.id]), {"next": "/huis/?tab=apparaten&domain=scene"})

        self.assertRedirects(response, "/huis/?tab=apparaten&domain=scene", fetch_redirect_response=False)
        sync_run = SyncRun.objects.get(household=self.household, connection=connection)
        self.assertEqual(sync_run.status, "queued")
        sync.assert_called_once_with(connection.id, self.household.id, sync_run.id)

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

    def test_hue_help_is_available_from_settings(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:index"))

        self.assertContains(response, 'data-open-dialog="hue-help-dialog"')
        self.assertContains(response, "Philips Hue koppelen")
        self.assertContains(response, "http://testserver/instellingen/hue/callback/")

    def test_new_home_provider_guides_are_available_from_settings(self):
        save_sonos_config(self.household, "sonos-client-id", "sonos-client-secret", False)
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:index"))

        self.assertContains(response, 'data-open-dialog="sonos-help-dialog"')
        self.assertContains(response, 'data-open-dialog="google-home-help-dialog"')
        self.assertContains(response, 'data-open-dialog="lg-thinq-help-dialog"')
        self.assertContains(response, 'href="https://developer.sonos.com/"')
        self.assertContains(response, 'href="https://console.nest.google.com/device-access"')
        self.assertContains(response, 'href="https://console.cloud.google.com/apis/credentials"')
        self.assertContains(response, 'href="https://developer.lge.com/"')
        self.assertContains(response, f"http://testserver/instellingen/sonos/events/{self.household.id}/")
        self.assertContains(response, "Apparatenpad")

    def test_parent_can_save_sonos_configuration_with_events(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("integrations:save_sonos_config"),
            {"client_id": "sonos-client-id", "client_secret": "sonos-client-secret", "events_enabled": "on"},
        )

        self.assertRedirects(response, reverse("integrations:index"))
        config = IntegrationAppConfig.objects.get(household=self.household, provider="sonos")
        self.assertEqual(config.client_id, "sonos-client-id")
        self.assertTrue(config.settings["events_enabled"])
        self.assertTrue(get_sonos_event_callback_token(self.household))

    def test_parent_can_start_sonos_and_google_home_oauth(self):
        save_app_config(self.household, "sonos", "sonos-client-id", "sonos-client-secret", {})
        save_app_config(self.household, "google_home", "google-client-id", "google-client-secret", {"project_id": "project-123"})
        self.client.force_login(self.owner)

        sonos = self.client.get(reverse("integrations:start_sonos"))
        sonos_params = parse_qs(urlparse(sonos["Location"]).query)
        self.assertEqual(sonos_params["client_id"], ["sonos-client-id"])
        self.assertEqual(sonos_params["scope"], ["playback-control-all"])
        self.assertEqual(sonos_params["redirect_uri"], ["http://testserver/instellingen/sonos/callback/"])

        google_home = self.client.get(reverse("integrations:start_google_home"))
        google_url = urlparse(google_home["Location"])
        google_params = parse_qs(google_url.query)
        self.assertEqual(google_url.path, "/partnerconnections/project-123/auth")
        self.assertEqual(google_params["client_id"], ["google-client-id"])
        self.assertEqual(google_params["scope"], ["https://www.googleapis.com/auth/sdm.service"])

    def test_parent_can_start_lg_thinq_oauth_with_configured_authorize_url(self):
        save_app_config(
            self.household,
            "lg_thinq",
            "lg-client-id",
            "lg-client-secret",
            {"authorize_url": "https://thinq.example.test/oauth/authorize", "token_url": "https://thinq.example.test/oauth/token", "api_base_url": "https://thinq.example.test/api", "devices_path": "/v2/user/devices"},
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:start_lg_thinq"))
        params = parse_qs(urlparse(response["Location"]).query)

        self.assertEqual(urlparse(response["Location"]).netloc, "thinq.example.test")
        self.assertEqual(params["client_id"], ["lg-client-id"])
        self.assertEqual(params["redirect_uri"], ["http://testserver/instellingen/lg-thinq/callback/"])

    def test_parent_can_authorize_hue_without_exposing_tokens(self):
        save_app_config(
            self.household,
            "hue",
            "hue-client-id",
            "hue-client-secret",
            {"app_id": "hue-app-id", "device_name": "Family App"},
        )
        self.client.force_login(self.owner)

        start = self.client.get(reverse("integrations:start_hue"))
        self.assertEqual(start.status_code, 302)
        params = parse_qs(urlparse(start["Location"]).query)
        self.assertEqual(params["client_id"], ["hue-client-id"])
        self.assertIn("state", params)
        self.assertEqual(params["appid"], ["hue-app-id"])
        self.assertEqual(params["devicename"], ["Family App"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertIn("code_challenge", params)

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
                {"client_id": "client", "client_secret": "secret", "app_id": "hue-app-id", "device_name": "Family App"},
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
