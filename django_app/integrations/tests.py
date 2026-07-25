import base64
import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import MagicMock, call, patch
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import BankAccount, Transaction
from home.models import HomeActionAudit, HomeEntity
from household.models import TASK_NOTE_MAX_LENGTH, Task, TaskList, TaskListSync, TaskNote
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.home_connect_events import listen_home_connect_events_once, parse_sse_events
from integrations.local_probe import ProbeError, apply_discovery, apply_inventory, authenticate_probe, create_pairing, expire_stale_probes, mark_probe_offline, mark_probe_seen, pair_probe, record_probe_command_result, revoke_probe, send_probe_command, send_probe_system_command
from integrations.openclaw_api import create_token
from integrations.models import IntegrationAppConfig, IntegrationAudit, IntegrationConnection, LocalDiscovery, LocalProbe, SyncRun
from integrations.providers import HueProviderError, ProviderError, _home_connect_appliance_meta, _home_connect_display_name, _home_connect_label, _home_connect_program_forecasts, _home_connect_start_status, _hue_hex_from_xy, _hue_optional_resource, _hue_supports_color, _hue_xy_from_hex, arm_hue_bridge_link, control_connected_home_entity, control_hue_light, finish_hue_bridge_link, google_home_thermostat_attributes, start_google_home_live_stream, sync_bunq, sync_google_home, sync_home_connect, sync_hue, sync_lg_thinq, sync_outlook, sync_smartcar, sync_sonos, sync_spotify, sync_task_list_link
from integrations.services import get_sonos_event_callback_token, save_app_config, save_sonos_config
from integrations.sonos_events import sonos_event_signature
from integrations.tasks import sync_active_connections, sync_connection_task, sync_home_connect_connections
from notifications.models import Notification
from planning.models import CalendarEvent, CalendarSource
from planning.tasks import sync_pending_events_to_remote
from travel.models import Trip, TripDocument, TripIdea, TripStop
from travel.services import ensure_trip_task_list


class FakeResponse:
    def __init__(self, payload, ok=True, status_code=None):
        self.payload = payload
        self.ok = ok
        self.content = b"{}"
        self.status_code = status_code if status_code is not None else (200 if ok else 400)
        self.headers = {}

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

    def test_stale_probe_is_marked_offline_and_local_entities_are_unavailable(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.SONOS,
            entity_id=f"probe.{probe.id}.sonos.group:woonkamer",
            domain="speaker",
            name="Woonkamer",
            is_available=True,
            attributes={"probe_id": str(probe.id), "probe_local_key": "group:woonkamer"},
        )
        probe.last_seen_at = timezone.now() - timedelta(minutes=3)
        probe.save(update_fields=["last_seen_at"])

        expired = expire_stale_probes(self.household)

        self.assertEqual([item.id for item in expired], [probe.id])
        probe.refresh_from_db()
        entity.refresh_from_db()
        self.assertEqual(probe.status, "offline")
        self.assertFalse(entity.is_available)

    def test_stale_probe_keeps_cloud_entity_available_but_removes_local_route(self):
        connection = IntegrationConnection.objects.create(household=self.household, user=self.user, provider="hue", display_name="Hue")
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id="hue.woonkamer",
            domain="light",
            name="Woonkamer",
            is_available=True,
            attributes={"hue_light_id": "woonkamer", "probe_id": str(probe.id), "probe_local_key": "light:woonkamer"},
        )
        probe.last_seen_at = timezone.now() - timedelta(minutes=3)
        probe.save(update_fields=["last_seen_at"])

        expire_stale_probes(self.household)

        entity.refresh_from_db()
        self.assertTrue(entity.is_available)
        self.assertEqual(entity.attributes, {"hue_light_id": "woonkamer"})

    def test_stale_probe_cannot_receive_new_commands(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id=f"probe.{probe.id}.hue.light-1",
            domain="light",
            name="Keuken",
            attributes={"probe_id": str(probe.id), "probe_local_key": "light:light-1"},
        )
        probe.last_seen_at = timezone.now() - timedelta(minutes=3)
        probe.save(update_fields=["last_seen_at"])

        with self.assertRaisesMessage(ProbeError, "niet verbonden"):
            send_probe_command(probe, entity, "on")

        probe.refresh_from_db()
        self.assertEqual(probe.status, "offline")

    def test_partial_heartbeat_preserves_other_adapter_statuses(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")

        mark_probe_seen(
            probe,
            "0.1.0",
            {"hue": {"status": "active", "entities": 8}, "sonos": {"status": "active", "entities": 1}},
            replace_adapters=True,
        )
        mark_probe_seen(probe, "0.1.0", {"sonos": {"status": "active", "entities": 2}})

        probe.refresh_from_db()
        self.assertEqual(probe.adapters["hue"]["entities"], 8)
        self.assertEqual(probe.adapters["sonos"]["entities"], 2)

    def test_local_command_has_an_id_and_reports_its_confirmed_result(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="probe.test.hue.light-1",
            domain="light",
            name="Keuken",
            attributes={"probe_id": str(probe.id), "probe_local_key": "light:light-1"},
        )

        class Layer:
            def __init__(self):
                self.calls = []

            async def group_send(self, group, payload):
                self.calls.append((group, payload))

        layer = Layer()
        with patch("integrations.local_probe.get_channel_layer", return_value=layer):
            command_id = send_probe_command(probe, entity, "on")

        self.assertTrue(command_id)
        self.assertEqual(layer.calls[0][0], f"local-probe-{probe.id}")
        self.assertEqual(layer.calls[0][1]["payload"]["command_id"], command_id)
        self.assertEqual(layer.calls[0][1]["payload"]["entity"]["id"], entity.id)
        with patch("home.realtime.broadcast_home_control_result") as broadcast:
            record_probe_command_result(probe, False, "Lamp reageert niet.", command_id=command_id, entity_id=str(entity.id), action="on")

        audit = HomeActionAudit.objects.get(entity=entity, action="on")
        self.assertFalse(audit.succeeded)
        self.assertEqual(audit.detail, "Lamp reageert niet.")
        broadcast.assert_called_once_with(entity, command_id=command_id, succeeded=False, error="Lamp reageert niet.")

    def test_local_hue_bridge_command_has_no_entity_but_is_scoped_to_the_probe(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")

        class Layer:
            def __init__(self):
                self.calls = []

            async def group_send(self, group, payload):
                self.calls.append((group, payload))

        layer = Layer()
        with patch("integrations.local_probe.get_channel_layer", return_value=layer):
            command_id = send_probe_system_command(probe, "link_hue_bridge", {"bridge": "http://192.168.1.30"})

        payload = layer.calls[0][1]["payload"]
        self.assertEqual(layer.calls[0][0], f"local-probe-{probe.id}")
        self.assertEqual(payload["command_id"], command_id)
        self.assertEqual(payload["action"], "link_hue_bridge")
        self.assertEqual(payload["entity"], {})
        self.assertEqual(payload["value"], {"bridge": "http://192.168.1.30"})

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

    def test_inventory_accepts_read_only_nest_protect_entities(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Woonkamer probe", "0.2.0")

        count = apply_inventory(probe, [{"source": "nest_protect", "local_key": "topaz.device-1", "external_id": "protect-1", "domain": "safety", "name": "Hal", "state": "normal", "is_available": True, "is_supported": False, "attributes": {"nest_protect_id": "topaz.device-1", "nest_co_status": 0}}])

        self.assertEqual(count, 1)
        entity = HomeEntity.objects.get(household=self.household, source=HomeEntity.Source.NEST_PROTECT)
        self.assertEqual(entity.name, "Hal")
        self.assertFalse(entity.is_supported)
        self.assertEqual(entity.attributes["probe_name"], "Woonkamer probe")

    def test_discovery_is_read_only_and_scoped_to_probe(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        result = apply_discovery(probe, [{"key": "uuid:device-1", "name": "Printer", "kind": "UPnP", "address": "192.168.1.30", "method": "ssdp", "details": {"model": "test"}}])

        self.assertEqual(result, 1)
        device = LocalDiscovery.objects.get(probe=probe)
        self.assertEqual(device.name, "Printer")

    def test_discovery_collapses_multiple_protocol_advertisements_for_one_device(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")

        result = apply_discovery(
            probe,
            [
                {
                    "key": "mdns:airplay:tv",
                    "name": "Woonkamer TV",
                    "kind": "airplay",
                    "address": "192.168.1.20",
                    "method": "mdns",
                    "details": {"properties": {"deviceid": "AA:BB:CC:DD"}},
                },
                {
                    "key": "mdns:googlecast:tv",
                    "name": "Woonkamer TV",
                    "kind": "googlecast",
                    "address": "192.168.1.20",
                    "method": "mdns",
                    "details": {"location": "http://192.168.1.20:8008/description.xml"},
                },
            ],
        )

        self.assertEqual(result, 1)
        self.assertEqual(LocalDiscovery.objects.filter(probe=probe).count(), 1)
        self.assertFalse(HomeEntity.objects.filter(household=self.household, name="Printer").exists())

    def test_integrations_page_prioritizes_actionable_discoveries_over_generic_bluetooth(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        apply_discovery(
            probe,
            [
                {
                    "key": "ble:unknown",
                    "name": "Bluetooth LE-apparaat",
                    "kind": "Bluetooth LE",
                    "method": "bluetooth_le",
                    "details": {"suggested_integration": "Bluetooth LE"},
                },
                {
                    "key": "tv:living-room",
                    "name": "Woonkamer TV",
                    "kind": "Android TV",
                    "address": "192.168.1.20",
                    "method": "ssdp",
                    "details": {"suggested_integration": "Google Cast / Android TV"},
                },
            ],
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("integrations:index"))

        self.assertEqual(response.context["local_discoveries"][0].name, "Woonkamer TV")

    def test_rotating_bluetooth_addresses_do_not_create_duplicate_discoveries(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        first = {
            "key": "ble:airpods:first",
            "name": "AirPods Pro van Fatih",
            "kind": "Bluetooth LE",
            "method": "bluetooth_le",
            "details": {
                "bluetooth_address": "AA:AA:AA:AA:AA:01",
                "manufacturer_ids": ["76"],
                "suggested_integration": "Bluetooth LE",
            },
        }
        second = {
            **first,
            "key": "ble:airpods:rotated",
            "details": {**first["details"], "bluetooth_address": "BB:BB:BB:BB:BB:02"},
        }

        apply_discovery(probe, [first])
        apply_discovery(probe, [second])

        discoveries = LocalDiscovery.objects.filter(probe=probe)
        self.assertEqual(discoveries.count(), 1)
        self.assertEqual(discoveries.get().name, "AirPods Pro van Fatih")

    def test_integrations_page_shows_one_discovery_when_two_probes_see_the_same_device(self):
        _, code = create_pairing(self.household)
        first_probe, _ = pair_probe(code, "Laptop", "0.1.0")
        _, code = create_pairing(self.household)
        second_probe, _ = pair_probe(code, "Raspberry Pi", "0.1.0")
        discovery = {
            "name": "Woonkamer TV",
            "kind": "Android TV",
            "address": "192.168.1.20",
            "method": "ssdp",
            "details": {"suggested_integration": "Google Cast / Android TV"},
        }
        apply_discovery(first_probe, [{**discovery, "key": "tv:first"}])
        apply_discovery(second_probe, [{**discovery, "key": "tv:second"}])
        self.client.force_login(self.user)

        response = self.client.get(reverse("integrations:index"))

        names = [item.name for item in response.context["local_discoveries"]]
        self.assertEqual(names.count("Woonkamer TV"), 1)

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
        self.assertIn("family-app-probe/family_app_probe/nest_protect.py", archive.namelist())
        self.assertIn("family-app-probe/family_app_probe/philips_tv.py", archive.namelist())
        self.assertIn("ha-philipsjs==3.2.5", archive.read("family-app-probe/requirements.txt").decode())
        self.assertIn("philips-tv-link", archive.read("family-app-probe/family_app_probe/main.py").decode())
        self.assertNotIn("family-app-probe/config.json", archive.namelist())

    def test_integrations_page_shows_probe_download_and_guide(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("integrations:index"))

        self.assertContains(response, reverse("integrations:download_local_probe"))
        self.assertContains(response, 'id="local-probe-guide"')
        self.assertContains(response, "Lokale probe installeren")

    def test_probe_guide_uses_the_discovered_hue_bridge_address(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        apply_discovery(
            probe,
            [
                {
                    "key": "hue:bridge",
                    "name": "Hue Bridge",
                    "kind": "Philips Hue",
                    "address": "192.168.1.30",
                    "method": "ssdp",
                    "details": {"suggested_integration": "Philips Hue"},
                }
            ],
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("integrations:index"))

        self.assertContains(response, "https://192.168.1.30")

    def test_parent_can_request_local_hue_bridge_link(self):
        _, code = create_pairing(self.household)
        probe, _ = pair_probe(code, "Laptop", "0.1.0")
        apply_discovery(
            probe,
            [{"key": "hue:bridge", "name": "Hue Bridge", "kind": "Philips Hue", "address": "192.168.1.30", "method": "ssdp", "details": {"suggested_integration": "Philips Hue"}}],
        )
        bridge = LocalDiscovery.objects.get(probe=probe)
        self.client.force_login(self.user)

        with patch("integrations.views.send_probe_system_command") as send:
            response = self.client.post(reverse("integrations:link_local_hue_bridge", args=[probe.id, bridge.id]))

        self.assertRedirects(response, reverse("integrations:index"))
        send.assert_called_once_with(probe, "link_hue_bridge", {"bridge": "http://192.168.1.30"})


class ProviderSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)

    def test_home_connect_is_queued_by_its_own_faster_sync_task(self):
        home_connect = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            status="configured",
        )
        sonos = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
            status="configured",
        )

        with patch("integrations.tasks.sync_connection_task.delay") as delay:
            sync_active_connections()
            delay.assert_called_once_with(sonos.id, self.household.id)
            delay.reset_mock()
            sync_home_connect_connections()
            delay.assert_called_once_with(home_connect.id, self.household.id)

    def test_hue_empty_color_capability_still_supports_color_control(self):
        self.assertTrue(_hue_supports_color({"color": {}}))
        self.assertFalse(_hue_supports_color({}))

    def test_home_connect_uses_a_clear_domain_and_icon_per_appliance_type(self):
        self.assertEqual(_home_connect_appliance_meta("Dishwasher"), ("dishwasher", "dishwasher"))
        self.assertEqual(_home_connect_appliance_meta("ConsumerProducts.CoffeeMaker"), ("coffee_maker", "coffee"))
        self.assertEqual(_home_connect_appliance_meta("Refrigeration.FridgeFreezer"), ("refrigerator", "refrigerator"))

    def test_home_connect_display_name_prefers_brand_and_type_over_account_label(self):
        self.assertEqual(
            _home_connect_display_name({"name": "Fatih", "brand": "Siemens"}, "dishwasher"),
            ("Siemens vaatwasser", "Fatih"),
        )

    def test_home_connect_program_labels_are_user_friendly_in_dutch(self):
        self.assertEqual(_home_connect_label("Dishcare.Dishwasher.Program.Eco50"), "Eco 50 °C")
        self.assertEqual(_home_connect_label("Dishcare.Dishwasher.Program.Kurz60"), "Kort 60 °C")

    def test_home_connect_start_requires_ready_remote_and_no_local_control(self):
        appliance = {"connected": True}
        ready_status = {
            "BSH.Common.Status.RemoteControlActive": True,
            "BSH.Common.Status.RemoteControlStartAllowed": True,
            "BSH.Common.Status.LocalControlActive": False,
            "BSH.Common.Status.OperationState": "BSH.Common.EnumType.OperationState.Ready",
        }
        self.assertEqual(_home_connect_start_status(appliance, ready_status), (True, "Klaar om een programma te starten."))

        local_status = {**ready_status, "BSH.Common.Status.LocalControlActive": True}
        self.assertEqual(_home_connect_start_status(appliance, local_status), (False, "Het apparaat wordt lokaal bediend."))

    def test_home_connect_selected_program_forecasts_are_extracted(self):
        forecasts = _home_connect_program_forecasts(
            {
                "options": [
                    {"key": "BSH.Common.Option.EnergyForecast", "value": 47},
                    {"key": "BSH.Common.Option.WaterForecast", "value": 43.4},
                    {"key": "Dishcare.Dishwasher.Option.HalfLoad", "value": False},
                ]
            }
        )
        self.assertEqual(forecasts, {"energy": 47, "water": 43})

    def test_home_connect_sse_parser_handles_status_and_keep_alive_events(self):
        events = list(
            parse_sse_events(
                [
                    "event: KEEP-ALIVE",
                    "",
                    "event: STATUS",
                    "id: dishwasher-1",
                    'data: {"key":"BSH.Common.Status.OperationState","value":"BSH.Common.EnumType.OperationState.Run"}',
                    "",
                ]
            )
        )

        self.assertEqual(events, [{"event": "STATUS", "id": "dishwasher-1", "data": {"key": "BSH.Common.Status.OperationState", "value": "BSH.Common.EnumType.OperationState.Run"}}])

    def test_home_connect_event_stream_triggers_a_confirmed_resync(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )

        class StreamResponse:
            ok = True

            @staticmethod
            def iter_lines(**_kwargs):
                return iter(["event: STATUS", "id: dishwasher-1", 'data: {"key":"BSH.Common.Status.OperationState"}', ""])

            @staticmethod
            def close():
                return None

        with patch("integrations.home_connect_events.requests.get", return_value=StreamResponse()), patch("integrations.home_connect_events.sync_home_connect") as sync:
            result = listen_home_connect_events_once(connection)

        self.assertEqual(result, {"events": 1})
        sync.assert_called_once_with(connection)
        connection.refresh_from_db()
        self.assertEqual(connection.settings["home_connect_events_status"], "active")
        self.assertTrue(connection.settings["home_connect_events_last_at"])

    def test_home_connect_event_stream_records_a_timestamped_appliance_event(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id=f"home_connect.{connection.id}.dishwasher-1",
            domain="dishwasher",
            name="Siemens vaatwasser",
            attributes={"home_connect_id": "dishwasher-1"},
        )

        class StreamResponse:
            ok = True

            @staticmethod
            def iter_lines(**_kwargs):
                return iter(["event: EVENT", "id: dishwasher-1", 'data: {"key":"Dishcare.Dishwasher.Event.SaltLack"}', ""])

            @staticmethod
            def close():
                return None

        with patch("integrations.home_connect_events.requests.get", return_value=StreamResponse()), patch("integrations.home_connect_events.sync_home_connect"):
            listen_home_connect_events_once(connection)

        entity.refresh_from_db()
        self.assertEqual(entity.attributes["home_connect_last_event"], "Zout bijvullen")
        self.assertTrue(entity.attributes["home_connect_last_event_at"])

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

    def test_spotify_sync_creates_connect_devices_and_active_playback(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SPOTIFY,
            display_name="Spotify Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        with patch(
            "integrations.providers.requests.request",
            side_effect=[
                FakeResponse({"devices": [{"id": "speaker-1", "name": "Woonkamer", "type": "Speaker", "is_active": True, "is_restricted": False, "volume_percent": 24}]}),
                FakeResponse({"is_playing": True, "device": {"id": "speaker-1"}, "item": {"name": "Testnummer", "duration_ms": 180000, "artists": [{"name": "Testartiest"}], "album": {"name": "Testalbum", "images": [{"url": "https://image.test/cover.jpg"}]}}, "progress_ms": 12000, "shuffle_state": False, "repeat_state": "off"}),
                FakeResponse({"items": [{"name": "Ochtend", "uri": "spotify:playlist:test", "images": [{"url": "https://image.test/playlist.jpg"}]}]}),
            ],
        ):
            result = sync_spotify(connection)

        entity = HomeEntity.objects.get(household=self.household, entity_id=f"spotify.{connection.id}.speaker-1")
        self.assertEqual(result, {"devices": 1})
        self.assertEqual(entity.source, HomeEntity.Source.SPOTIFY)
        self.assertEqual(entity.state, "on")
        self.assertEqual(entity.attributes["spotify_track_name"], "Testnummer")
        self.assertEqual(entity.attributes["spotify_volume"], 24)
        self.assertEqual(entity.attributes["spotify_playlists"][0]["uri"], "spotify:playlist:test")

    def test_home_connect_sync_creates_a_dishwasher_with_program_status(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        with patch(
            "integrations.providers.requests.request",
            side_effect=[
                FakeResponse({"data": {"homeappliances": [{"haId": "dishwasher-1", "name": "Siemens vaatwasser", "type": "Dishwasher", "brand": "Siemens", "connected": True, "enumber": "SN000"}]}}),
                FakeResponse({"data": {"status": [{"key": "BSH.Common.Status.OperationState", "value": "BSH.Common.EnumType.OperationState.Run"}, {"key": "BSH.Common.Option.RemainingProgramTime", "value": 2100}, {"key": "BSH.Common.Option.ProgramProgress", "value": 42.4}, {"key": "BSH.Common.Status.DoorState", "value": "BSH.Common.EnumType.DoorState.Closed"}, {"key": "BSH.Common.Status.RemoteControlStartAllowed", "value": True}]}}),
                FakeResponse({"data": {"active": {"key": "Dishcare.Dishwasher.Program.Eco50"}}}),
                FakeResponse({"data": {"programs": [{"key": "Dishcare.Dishwasher.Program.Eco50"}]}}),
                FakeResponse({"data": {"key": "Dishcare.Dishwasher.Program.Eco50", "options": [{"key": "BSH.Common.Option.EnergyForecast", "value": 47}, {"key": "BSH.Common.Option.WaterForecast", "value": 43}]}}),
                FakeResponse({"data": {"commands": [{"key": "BSH.Common.Command.PauseProgram"}, {"key": "BSH.Common.Command.ResumeProgram"}, {"key": "BSH.Common.Command.StopProgram"}]}}),
            ],
        ):
            result = sync_home_connect(connection)

        entity = HomeEntity.objects.get(household=self.household, entity_id=f"home_connect.{connection.id}.dishwasher-1")
        self.assertEqual(result, {"devices": 1})
        self.assertEqual(entity.source, HomeEntity.Source.HOME_CONNECT)
        self.assertEqual(entity.domain, "dishwasher")
        self.assertEqual(entity.state, "running")
        self.assertEqual(entity.attributes["home_connect_operation"], "Bezig")
        self.assertEqual(entity.attributes["home_connect_program"], "Eco 50 °C")
        self.assertEqual(entity.attributes["home_connect_remaining_seconds"], 2100)
        self.assertEqual(entity.attributes["home_connect_remaining_label"], "35 min")
        self.assertEqual(entity.attributes["home_connect_program_progress"], 42)
        self.assertEqual(entity.attributes["home_connect_door_label"], "Deur gesloten")
        self.assertTrue(entity.attributes["home_connect_remote_start"])
        self.assertTrue(entity.attributes["home_connect_can_stop"])
        self.assertFalse(entity.attributes["home_connect_can_select_program"])
        self.assertEqual(entity.attributes["home_connect_programs"][0]["key"], "Dishcare.Dishwasher.Program.Eco50")
        self.assertEqual(entity.attributes["home_connect_selected_program"], "Eco 50 °C")
        self.assertEqual(entity.attributes["home_connect_program_forecasts"], {"energy": 47, "water": 43})

    def test_home_connect_starts_only_an_available_program(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id=f"home_connect.{connection.id}.dishwasher-1",
            domain="dishwasher",
            name="Siemens vaatwasser",
            attributes={
                "home_connect_id": "dishwasher-1",
                "home_connect_remote_start": True,
                "home_connect_programs": [
                    {
                        "key": "Dishcare.Dishwasher.Program.Eco50",
                        "label": "Eco50",
                        "options": [{"key": "BSH.Common.Option.IntensivZone", "value": True, "label": "IntensivZone"}],
                    }
                ],
            },
        )

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            result = control_connected_home_entity(entity, "start_program", "Dishcare.Dishwasher.Program.Eco50")

        self.assertEqual(result, "Programma gestart.")
        self.assertEqual(request.call_args.args[0], "PUT")
        self.assertTrue(request.call_args.args[1].endswith("/homeappliances/dishwasher-1/programs/active"))
        self.assertEqual(
            request.call_args.kwargs["json"],
            {"data": {"key": "Dishcare.Dishwasher.Program.Eco50", "options": [{"key": "BSH.Common.Option.IntensivZone", "value": True}]}},
        )
        with self.assertRaisesRegex(ProviderError, "Kies een programma"):
            control_connected_home_entity(entity, "start_program", "Dishcare.Dishwasher.Program.Auto2")

    def test_home_connect_stops_an_active_program_via_its_program_endpoint(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id=f"home_connect.{connection.id}.dishwasher-1",
            domain="dishwasher",
            name="Siemens vaatwasser",
            attributes={"home_connect_id": "dishwasher-1", "home_connect_can_stop": True},
        )

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            result = control_connected_home_entity(entity, "stop_program")

        self.assertEqual(result, "Programma gestopt.")
        self.assertEqual(request.call_args.args[0], "DELETE")
        self.assertTrue(request.call_args.args[1].endswith("/programs/active"))

    def test_home_connect_can_select_an_available_program_without_starting_it(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id=f"home_connect.{connection.id}.dishwasher-1",
            domain="dishwasher",
            name="Siemens vaatwasser",
            attributes={
                "home_connect_id": "dishwasher-1",
                "home_connect_can_select_program": True,
                "home_connect_programs": [{"key": "Dishcare.Dishwasher.Program.Eco50", "label": "Eco50", "options": []}],
            },
        )

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            result = control_connected_home_entity(entity, "select_program", "Dishcare.Dishwasher.Program.Eco50")

        self.assertEqual(result, "Programma geselecteerd; het apparaat start niet automatisch.")
        self.assertEqual(request.call_args.args[0], "PUT")
        self.assertTrue(request.call_args.args[1].endswith("/homeappliances/dishwasher-1/programs/selected"))
        self.assertEqual(request.call_args.kwargs["json"], {"data": {"key": "Dishcare.Dishwasher.Program.Eco50"}})

    def test_home_connect_creates_one_notification_for_finished_program_and_maintenance_event(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id=f"home_connect.{connection.id}.dishwasher-1",
            domain="dishwasher",
            name="Siemens vaatwasser",
            state="running",
            attributes={"home_connect_events": {}},
        )
        responses = [
            FakeResponse({"data": [{"haId": "dishwasher-1", "name": "Siemens vaatwasser", "type": "Dishwasher", "brand": "Siemens", "connected": True}]}),
            FakeResponse({"data": [{"key": "BSH.Common.Status.OperationState", "value": "BSH.Common.EnumType.OperationState.Finished"}, {"key": "Dishcare.Dishwasher.Event.SaltLack", "value": "BSH.Common.EnumType.EventStatus.Present"}]}),
            FakeResponse({"data": {"key": "Dishcare.Dishwasher.Program.Eco50"}}),
            FakeResponse({"data": []}),
            FakeResponse({"data": []}),
            FakeResponse({"data": {}}),
        ]
        with patch("integrations.providers.requests.request", side_effect=responses):
            sync_home_connect(connection)

        self.assertTrue(Notification.objects.filter(household=self.household, title="Siemens vaatwasser is klaar").exists())
        self.assertTrue(Notification.objects.filter(household=self.household, body="Zout bijvullen").exists())

    def test_spotify_uses_the_right_payload_for_contexts_and_tracks(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SPOTIFY,
            display_name="Spotify Connect",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SPOTIFY,
            entity_id=f"spotify.{connection.id}.speaker-1",
            domain="media_player",
            name="Woonkamer",
            attributes={"spotify_device_id": "speaker-1"},
        )
        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            control_connected_home_entity(entity, "play_context", "spotify:album:album-1")
            self.assertEqual(request.call_args.kwargs["json"], {"context_uri": "spotify:album:album-1"})
            control_connected_home_entity(entity, "play_context", "spotify:track:track-1")
            self.assertEqual(request.call_args.kwargs["json"], {"uris": ["spotify:track:track-1"]})
            control_connected_home_entity(entity, "queue_uri", "spotify:track:track-2")
            self.assertEqual(request.call_args.kwargs["params"]["uri"], "spotify:track:track-2")
        with self.assertRaisesRegex(ProviderError, "geldige Spotify-track"):
            control_connected_home_entity(entity, "queue_uri", "spotify:playlist:not-a-track")

    def test_smartcar_sync_stores_vehicle_signals(self):
        IntegrationAppConfig.objects.create(household=self.household, provider="smartcar", client_id="client-id", client_secret_encrypted=encrypt("client-secret"))
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SMARTCAR,
            display_name="Smartcar",
            settings={"smartcar_user_id": "user-1", "access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        with patch(
            "integrations.providers.requests.request",
            side_effect=[
                FakeResponse({"data": [{"id": "connection-1", "relationships": {"vehicle": {"data": {"id": "vehicle-1", "type": "vehicle"}}}}]}),
                FakeResponse({"data": {"attributes": {"make": "Volvo", "model": "EX30", "year": 2025}}}),
                FakeResponse({"data": [{"attributes": {"code": "odometer", "name": "Odometer", "body": {"value": 1234, "unit": "km"}}}], "included": {"vehicle": {"attributes": {"make": "Volvo", "model": "EX30", "year": 2025}}}}),
            ],
        ):
            result = sync_smartcar(connection)

        entity = HomeEntity.objects.get(household=self.household, entity_id=f"smartcar.{connection.id}.vehicle-1")
        self.assertEqual(result, {"vehicles": 1})
        self.assertEqual(entity.name, "Volvo EX30 2025")
        self.assertEqual(entity.attributes["smartcar_readings"], [{"label": "Odometer", "value": "1234", "unit": "km"}])

    def test_smartcar_rejects_remote_control_without_vehicle_authorization(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.SMARTCAR,
            display_name="Smartcar",
            settings={"smartcar_user_id": "user-1"},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SMARTCAR,
            entity_id=f"smartcar.{connection.id}.vehicle-1",
            domain="vehicle",
            name="Voorbeeldauto",
            attributes={"smartcar_vehicle_id": "vehicle-1", "smartcar_can_lock": False, "smartcar_can_unlock": False},
        )

        with self.assertRaisesRegex(ProviderError, "niet voor dit voertuig geautoriseerd"):
            control_connected_home_entity(entity, "unlock")

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

    def test_google_home_sync_keeps_all_thermostat_traits_and_controls_them(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.GOOGLE_HOME,
            display_name="Google Home",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(), "project_id": "project-1"},
        )
        traits = {
            "sdm.devices.traits.Info": {"customName": "Woonkamer"},
            "sdm.devices.traits.Connectivity": {"status": "ONLINE"},
            "sdm.devices.traits.Temperature": {"ambientTemperatureCelsius": 20.5},
            "sdm.devices.traits.Humidity": {"ambientHumidityPercent": 47},
            "sdm.devices.traits.Settings": {"temperatureScale": "CELSIUS"},
            "sdm.devices.traits.ThermostatMode": {"mode": "HEATCOOL", "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"]},
            "sdm.devices.traits.ThermostatEco": {"mode": "OFF", "availableModes": ["MANUAL_ECO", "OFF"]},
            "sdm.devices.traits.ThermostatHvac": {"status": "HEATING"},
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {"heatCelsius": 19, "coolCelsius": 23},
            "sdm.devices.traits.Fan": {"timerMode": "OFF"},
        }
        with patch("integrations.providers.requests.request", return_value=FakeResponse({"devices": [{"name": "enterprises/project-1/devices/device-1", "type": "sdm.devices.types.THERMOSTAT", "traits": traits}]})):
            sync_google_home(connection)
        entity = HomeEntity.objects.get(household=self.household, entity_id=f"google_home.{connection.id}.device-1")
        self.assertEqual(entity.state, "heating")
        self.assertEqual(entity.attributes["humidity"], 47)
        self.assertEqual(entity.attributes["thermostat_mode"], "HEATCOOL")
        self.assertTrue(entity.attributes["supports_fan_timer"])

        with patch("integrations.providers.requests.request", return_value=FakeResponse({})) as request:
            control_connected_home_entity(entity, "set_temperature_range", {"heat": "20", "cool": "24"})
            control_connected_home_entity(entity, "set_thermostat_mode", "HEAT")
            control_connected_home_entity(entity, "set_eco_mode", "MANUAL_ECO")
            control_connected_home_entity(entity, "set_fan_timer", "1800")

        payloads = [call.kwargs["json"] for call in request.call_args_list]
        self.assertIn({"command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetRange", "params": {"heatCelsius": 20.0, "coolCelsius": 24.0}}, payloads)
        self.assertIn({"command": "sdm.devices.commands.ThermostatMode.SetMode", "params": {"mode": "HEAT"}}, payloads)
        self.assertIn({"command": "sdm.devices.commands.ThermostatEco.SetMode", "params": {"mode": "MANUAL_ECO"}}, payloads)
        self.assertIn({"command": "sdm.devices.commands.Fan.SetTimer", "params": {"timerMode": "ON", "duration": "1800s"}}, payloads)

    def test_google_home_off_thermostat_still_supports_target_temperature(self):
        attributes = google_home_thermostat_attributes(
            {
                "sdm.devices.traits.Temperature": {"ambientTemperatureCelsius": 25.209991},
                "sdm.devices.traits.ThermostatMode": {"mode": "OFF", "availableModes": ["HEAT", "OFF"]},
                "sdm.devices.traits.ThermostatTemperatureSetpoint": {},
            }
        )

        self.assertEqual(attributes["current_temperature"], 25.2)
        self.assertTrue(attributes["supports_temperature"])
        self.assertIsNone(attributes["temperature"])

    def test_google_home_pubsub_event_updates_thermostat_without_full_sync(self):
        from integrations.google_home_events import poll_google_home_events

        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.GOOGLE_HOME,
            display_name="Google Home",
            settings={"project_id": "project-1"},
            status="configured",
        )
        IntegrationAppConfig.objects.create(
            household=self.household,
            provider="google_home",
            settings={"events_enabled": True, "pubsub_subscription": "projects/cloud-project/subscriptions/family-nest", "pubsub_service_account_json": encrypt('{"private_key":"not-used"}')},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.GOOGLE_HOME,
            entity_id="google_home.1.device-1",
            domain="climate",
            name="Woonkamer",
            attributes={"google_resource_name": "enterprises/project-1/devices/device-1", "google_traits": {"sdm.devices.traits.Temperature": {"ambientTemperatureCelsius": 20}}},
        )
        event = {"eventId": "event-1", "timestamp": "2026-07-14T18:00:00Z", "resourceUpdate": {"name": "enterprises/project-1/devices/device-1", "traits": {"sdm.devices.traits.Temperature": {"ambientTemperatureCelsius": 21.5}, "sdm.devices.traits.ThermostatHvac": {"status": "HEATING"}}, "events": {"sdm.devices.events.CameraMotion.Motion": {"eventId": "camera-event"}}}}
        raw = base64.b64encode(json.dumps(event).encode()).decode()
        with patch("integrations.google_home_events._service_account_token", return_value="pubsub-token"), patch("integrations.google_home_events._pull", return_value=[{"ackId": "ack-1", "message": {"data": raw}}]), patch("integrations.google_home_events._acknowledge") as acknowledge:
            result = poll_google_home_events(connection)

        entity.refresh_from_db()
        self.assertEqual(result, {"status": "active", "events": 1})
        self.assertEqual(entity.attributes["current_temperature"], 21.5)
        self.assertEqual(entity.state, "active")
        self.assertEqual(entity.attributes["google_last_event"], "Beweging gedetecteerd")
        acknowledge.assert_called_once_with("projects/cloud-project/subscriptions/family-nest", "pubsub-token", ["ack-1"])

    def test_google_doorbell_live_stream_uses_internal_mjpeg_relay(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.GOOGLE_HOME,
            display_name="Google Home",
            status="connected",
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.GOOGLE_HOME,
            entity_id="google_home.1.doorbell-1",
            domain="camera",
            name="Voordeur",
            attributes={
                "google_resource_name": "enterprises/project-1/devices/doorbell-1",
                "camera_stream_protocols": ["RTSP"],
            },
        )
        payload = {"results": {"streamUrls": {"rtspUrl": "rtsps://temporary-stream.example/live"}, "expiresAt": "2026-07-14T21:00:00Z"}}

        with patch("integrations.providers._google_home_request", return_value=payload), patch("integrations.providers.requests.put", return_value=FakeResponse({})) as relay:
            result = start_google_home_live_stream(entity)

        self.assertEqual(result["stream_name"], "family-app-live-mjpeg")
        self.assertEqual(relay.call_count, 2)
        self.assertEqual(relay.call_args_list[0].kwargs["params"]["name"], "family-app-live")
        self.assertEqual(relay.call_args_list[1].kwargs["params"]["src"], "ffmpeg:family-app-live#video=mjpeg")

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

        # sync_outlook goes through _request_with_retry, which calls requests.request - patching
        # requests.get here used to let the call escape to the real Graph endpoint.
        def outlook_request(_method, url, **_kwargs):
            if url.endswith("me/calendars?$select=id,name"):
                return FakeResponse({"value": [{"id": "calendar-1", "name": "Gezin"}]})
            return FakeResponse({"value": [{"id": "event-1", "subject": "Sport", "start": {"dateTime": "2026-07-13T09:00:00"}, "end": {"dateTime": "2026-07-13T10:00:00"}, "isAllDay": False, "location": {"displayName": "Hal"}, "body": {"contentType": "text", "content": "Meenemen: sporttas"}}]})

        with patch("integrations.providers.requests.request", side_effect=outlook_request):
            result = sync_outlook(connection)

        self.assertEqual(result, {"calendars": 1, "events": 1})
        source = CalendarSource.objects.get(household=self.household, external_id="calendar-1")
        event = CalendarEvent.objects.get(household=self.household, external_id="event-1")
        self.assertEqual(source.name, "Gezin")
        self.assertTrue(timezone.is_aware(event.starts_at))
        self.assertEqual(event.location, "Hal")
        # Writable, linked to the connection that produced it, but not pushing anything yet.
        self.assertFalse(source.is_read_only)
        self.assertFalse(source.sync_local_events)
        self.assertEqual(source.connection_id, connection.pk)
        # A freshly pulled event must never look like an unsent local change.
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.SYNCED)
        self.assertIsNotNone(event.remote_updated_at)
        self.assertEqual(event.notes, "Meenemen: sporttas")

    def _outlook_calendar_connection(self):
        return IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )

    def _outlook_calendar_pull(self):
        def outlook_request(_method, url, **_kwargs):
            if url.endswith("me/calendars?$select=id,name"):
                return FakeResponse({"value": [{"id": "calendar-1", "name": "Werkagenda"}]})
            return FakeResponse({"value": [{"id": "event-1", "subject": "Sport", "start": {"dateTime": "2026-07-13T09:00:00"}, "end": {"dateTime": "2026-07-13T10:00:00"}, "isAllDay": False, "location": {"displayName": "Hal"}, "body": {"contentType": "text", "content": "Van Outlook"}}]})

        return outlook_request

    def test_outlook_sync_never_duplicates_or_overwrites_a_locally_created_event(self):
        connection = self._outlook_calendar_connection()
        source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.OUTLOOK, name="Werkagenda", external_id="calendar-1", connection=connection, is_read_only=False, sync_local_events=True)
        local_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda")
        start = timezone.now()
        # This is what a local event looks like right after the push task created it in Outlook:
        # it keeps the family calendar as its source but carries the Graph id.
        pushed = CalendarEvent.objects.create(household=self.household, source=local_source, external_id="event-1", title="Tandarts", starts_at=start, ends_at=start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.PENDING, notes="Halfjaarlijkse controle")

        with patch("integrations.providers.requests.request", side_effect=self._outlook_calendar_pull()):
            sync_outlook(connection)

        self.assertEqual(CalendarEvent.objects.filter(household=self.household, external_id="event-1").count(), 1)
        pushed.refresh_from_db()
        # The edit has not been sent yet, so the pull may not throw it away either.
        self.assertEqual(pushed.title, "Tandarts")
        self.assertEqual(pushed.notes, "Halfjaarlijkse controle")
        self.assertEqual(pushed.sync_status, CalendarEvent.SyncStatus.PENDING)
        self.assertEqual(pushed.source_id, local_source.pk)
        self.assertEqual(source.events.count(), 0)

    def test_outlook_sync_keeps_a_failed_push_visible_instead_of_clearing_it(self):
        connection = self._outlook_calendar_connection()
        source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.OUTLOOK, name="Werkagenda", external_id="calendar-1", connection=connection, is_read_only=False, sync_local_events=True)
        start = timezone.now()
        event = CalendarEvent.objects.create(household=self.household, source=source, external_id="event-1", title="Teamoverleg", starts_at=start, ends_at=start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.ERROR, last_sync_error="Access is denied.")

        with patch("integrations.providers.requests.request", side_effect=self._outlook_calendar_pull()):
            sync_outlook(connection)

        event.refresh_from_db()
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.ERROR)
        self.assertEqual(event.last_sync_error, "Access is denied.")
        self.assertEqual(event.title, "Teamoverleg")

    def test_outlook_sync_skips_a_remote_event_that_is_older_than_the_last_sync(self):
        connection = self._outlook_calendar_connection()
        source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.OUTLOOK, name="Werkagenda", external_id="calendar-1", connection=connection)
        start = timezone.now()
        event = CalendarEvent.objects.create(household=self.household, source=source, external_id="event-1", title="Al bijgewerkt", starts_at=start, ends_at=start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.SYNCED, remote_updated_at=timezone.now())

        def outlook_request(_method, url, **_kwargs):
            if url.endswith("me/calendars?$select=id,name"):
                return FakeResponse({"value": [{"id": "calendar-1", "name": "Werkagenda"}]})
            return FakeResponse({"value": [{"id": "event-1", "subject": "Sport", "start": {"dateTime": "2026-07-13T09:00:00"}, "end": {"dateTime": "2026-07-13T10:00:00"}, "isAllDay": False, "lastModifiedDateTime": "2020-01-01T10:00:00Z"}]})

        with patch("integrations.providers.requests.request", side_effect=outlook_request):
            result = sync_outlook(connection)

        self.assertEqual(result, {"calendars": 1, "events": 1})
        event.refresh_from_db()
        self.assertEqual(event.title, "Al bijgewerkt")

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

    def test_spotify_start_requests_the_playback_and_playlist_scopes(self):
        save_app_config(self.household, "spotify", "spotify-client", "spotify-secret", {})
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:start_spotify"))

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        scopes = set(query["scope"][0].split())
        self.assertEqual(query["client_id"], ["spotify-client"])
        self.assertTrue({"user-read-playback-state", "user-modify-playback-state", "playlist-read-private"}.issubset(scopes))
        self.assertIn("state", query)

    def test_smartcar_start_uses_the_dashboard_vehicle_access_configuration(self):
        save_app_config(self.household, "smartcar", "api-client", "smartcar-secret", {"connect_client_id": "connect-client", "country": "NL", "allow_remote_controls": True})
        self.client.force_login(self.owner)

        response = self.client.get(reverse("integrations:start_smartcar"))

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query["client_id"], ["connect-client"])
        self.assertEqual(query["country"], ["NL"])
        self.assertNotIn("scope", query)

    def test_smartcar_callback_persists_the_authorized_user_and_queues_a_sync(self):
        save_app_config(self.household, "smartcar", "api-client", "smartcar-secret", {"connect_client_id": "connect-client", "country": "NL"})
        self.client.force_login(self.owner)
        start = self.client.get(reverse("integrations:start_smartcar"))
        state = parse_qs(urlparse(start["Location"]).query)["state"][0]

        with patch("integrations.views.sync_connection_task.delay") as delay:
            response = self.client.get(reverse("integrations:smartcar_callback"), {"user_id": "smartcar-user-1", "state": state})

        self.assertRedirects(response, reverse("integrations:index"))
        connection = IntegrationConnection.objects.get(household=self.household, provider="smartcar")
        self.assertEqual(connection.settings["smartcar_user_id"], "smartcar-user-1")
        self.assertEqual(connection.status, "needs_sync")
        delay.assert_called_once_with(connection.id, self.household.id)

    def test_spotify_callback_persists_tokens_and_queues_a_sync(self):
        save_app_config(self.household, "spotify", "spotify-client", "spotify-secret", {})
        self.client.force_login(self.owner)
        start = self.client.get(reverse("integrations:start_spotify"))
        state = parse_qs(urlparse(start["Location"]).query)["state"][0]

        with patch("integrations.services.requests.post", return_value=FakeResponse({"access_token": "access-token", "refresh_token": "refresh-token", "expires_in": 3600})), patch("integrations.services.requests.get", return_value=FakeResponse({"display_name": "Gezinsaccount"})), patch("integrations.views.sync_connection_task.delay") as delay:
            response = self.client.get(reverse("integrations:spotify_callback"), {"code": "code-1", "state": state})

        self.assertRedirects(response, reverse("integrations:index"))
        connection = IntegrationConnection.objects.get(household=self.household, provider="spotify")
        self.assertEqual(connection.external_account, "Gezinsaccount")
        self.assertEqual(connection.status, "needs_sync")
        self.assertTrue(connection.secret_encrypted)
        delay.assert_called_once_with(connection.id, self.household.id)

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

    def test_parent_can_save_google_home_configuration_with_live_events(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("integrations:save_google_home_config"),
            {
                "client_id": "google-client-id",
                "client_secret": "google-client-secret",
                "project_id": "device-access-project",
                "events_enabled": "on",
                "pubsub_subscription": "projects/family-app/subscriptions/nest-events",
                "pubsub_service_account_json": '{"type": "service_account", "project_id": "family-app"}',
            },
        )

        self.assertRedirects(response, reverse("integrations:index"))
        config = IntegrationAppConfig.objects.get(household=self.household, provider="google_home")
        self.assertEqual(config.client_id, "google-client-id")
        self.assertEqual(config.settings["project_id"], "device-access-project")
        self.assertTrue(config.settings["events_enabled"])
        self.assertEqual(config.settings["pubsub_subscription"], "projects/family-app/subscriptions/nest-events")

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

    def test_export_contains_the_task_note_timeline(self):
        task = Task.objects.get(household=self.household, title="Eigen taak")
        TaskNote.objects.create(household=self.household, task=task, author=self.owner, text="Gebeld met de gemeente.")
        TaskNote.objects.create(household=self.other_household, task=Task.objects.get(household=self.other_household, title="Andere taak"), text="Van de buren.")
        self.client.force_login(self.owner)

        payload = json.loads(self.client.get(reverse("integrations:export_household_data")).content)

        notes = payload["household_data"]["task_notes"]
        self.assertEqual([note["text"] for note in notes], ["Gebeld met de gemeente."])
        self.assertEqual(notes[0]["task__title"], "Eigen taak")

    def test_child_cannot_export_household_data(self):
        self.client.force_login(self.child)

        self.assertEqual(self.client.get(reverse("integrations:export_household_data")).status_code, 403)


class OpenClawTaskTimelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Eerste gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)
        self.other_household = Household.objects.create(name="Tweede gezin")
        self.task = Task.objects.create(household=self.household, title="Rijbewijs verlengen")
        self.other_task = Task.objects.create(household=self.other_household, title="Taak van de buren")
        _, self.token = create_token(self.household, self.user, scopes=["vandaag:read", "taken:write"])

    def _get(self, name, token=None, **params):
        return self.client.get(reverse(f"integrations:{name}"), params, HTTP_AUTHORIZATION=f"Bearer {token or self.token}")

    def test_all_tasks_exposes_the_note_timeline_and_completion_reason(self):
        TaskNote.objects.create(household=self.household, task=self.task, author=self.user, text="Gebeld met de gemeente.")
        TaskNote.objects.create(household=self.household, task=self.task, text="E-mail verwerkt, geen actie nodig.", created_by_agent=True)

        response = self._get("api_openclaw_all_tasks")

        self.assertEqual(response.status_code, 200)
        task = response.json()["tasks"][0]
        self.assertIsNone(task["completed_at"])
        self.assertIsNone(task["completion_reason"])
        self.assertEqual([note["text"] for note in task["notes_timeline"]], ["Gebeld met de gemeente.", "E-mail verwerkt, geen actie nodig."])
        self.assertEqual(task["notes_timeline"][0]["author"], str(self.user))
        self.assertFalse(task["notes_timeline"][0]["created_by_agent"])
        self.assertIsNone(task["notes_timeline"][1]["author"])
        self.assertTrue(task["notes_timeline"][1]["created_by_agent"])

    def test_include_completed_adds_recently_finished_tasks_with_their_reason(self):
        recent = Task.objects.create(household=self.household, title="Cadeau kopen", completed_at=timezone.now() - timedelta(days=3), completion_reason="Al geregeld door oma")
        Task.objects.create(household=self.household, title="Oude klus", completed_at=timezone.now() - timedelta(days=45), completion_reason="Lang geleden gedaan")

        default_titles = [task["title"] for task in self._get("api_openclaw_all_tasks").json()["tasks"]]
        payload = self._get("api_openclaw_all_tasks", include_completed="true").json()

        self.assertEqual(default_titles, ["Rijbewijs verlengen"])
        self.assertEqual(sorted(task["title"] for task in payload["tasks"]), ["Cadeau kopen", "Rijbewijs verlengen"])
        completed = next(task for task in payload["tasks"] if task["id"] == recent.id)
        self.assertEqual(completed["completion_reason"], "Al geregeld door oma")
        self.assertIsNotNone(completed["completed_at"])

    def test_agent_note_is_appended_to_the_timeline(self):
        response = self.client.post(
            reverse("integrations:api_openclaw_add_task_note", args=[self.task.id]),
            data=json.dumps({"text": "E-mail van de gemeente verwerkt, geen actie nodig."}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 201)
        note = TaskNote.objects.get(task=self.task)
        self.assertEqual(note.text, "E-mail van de gemeente verwerkt, geen actie nodig.")
        self.assertTrue(note.created_by_agent)
        self.assertEqual(note.author, self.user)
        self.assertEqual(note.household, self.household)
        self.assertEqual(response.json()["id"], note.id)

    def test_empty_note_is_refused(self):
        response = self.client.post(
            reverse("integrations:api_openclaw_add_task_note", args=[self.task.id]),
            data=json.dumps({"text": "   "}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(TaskNote.objects.filter(task=self.task).exists())

    def test_note_needs_the_taken_write_scope(self):
        _, read_only_token = create_token(self.household, self.user, scopes=["vandaag:read"])

        response = self.client.post(
            reverse("integrations:api_openclaw_add_task_note", args=[self.task.id]),
            data=json.dumps({"text": "Mag niet."}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {read_only_token}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TaskNote.objects.filter(task=self.task).exists())

    def test_note_on_a_task_from_another_household_is_not_found(self):
        response = self.client.post(
            reverse("integrations:api_openclaw_add_task_note", args=[self.other_task.id]),
            data=json.dumps({"text": "Niet van dit gezin."}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(TaskNote.objects.filter(task=self.other_task).exists())

    def test_reopened_task_no_longer_reports_a_completion_reason(self):
        Task.objects.filter(pk=self.task.pk).update(completion_reason="Al geregeld door oma")

        response = self._get("api_openclaw_all_tasks")

        task = response.json()["tasks"][0]
        self.assertIsNone(task["completed_at"])
        self.assertIsNone(task["completion_reason"])

    def test_timeline_only_carries_the_most_recent_notes_with_the_full_count(self):
        for number in range(1, 8):
            TaskNote.objects.create(household=self.household, task=self.task, author=self.user, text=f"Notitie {number}")

        response = self._get("api_openclaw_all_tasks")

        task = response.json()["tasks"][0]
        self.assertEqual([note["text"] for note in task["notes_timeline"]], ["Notitie 3", "Notitie 4", "Notitie 5", "Notitie 6", "Notitie 7"])
        self.assertEqual(task["notes_total"], 7)

    def test_overly_long_agent_note_is_truncated(self):
        response = self.client.post(
            reverse("integrations:api_openclaw_add_task_note", args=[self.task.id]),
            data=json.dumps({"text": "Heel lang verhaal. " * 300}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(TaskNote.objects.get(task=self.task).text), TASK_NOTE_MAX_LENGTH)


class OutlookTodoSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="todo-ouder@example.com", email="todo-ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Takengezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)
        self.connection = IntegrationConnection.objects.create(household=self.household, user=self.user, provider="outlook", display_name="Outlook")
        self.task_list = TaskList.objects.create(household=self.household, name="Klussen")
        self.link = TaskListSync.objects.create(household=self.household, task_list=self.task_list, connection=self.connection, provider=TaskListSync.Provider.OUTLOOK_TODO, external_list_id="lijst-1")

    def test_reopening_a_task_in_microsoft_to_do_clears_the_completion_reason(self):
        task = Task.objects.create(
            household=self.household,
            list=self.task_list,
            title="Rijbewijs verlengen",
            external_provider=TaskListSync.Provider.OUTLOOK_TODO,
            external_id="remote-1",
            completed_at=timezone.now() - timedelta(days=2),
            completion_reason="Al geregeld door oma",
        )
        Task.objects.filter(pk=task.pk).update(remote_updated_at=timezone.now() - timedelta(days=2))
        remote = {"id": "remote-1", "list_id": "lijst-1", "title": "Rijbewijs verlengen", "status": "notStarted", "due_at": None, "notes": "", "last_modified": timezone.now().isoformat(), "completed_at": None}

        with patch("integrations.providers.outlook_todo_tasks", return_value=[remote]), patch("integrations.providers.outlook_todo_task_update") as update:
            sync_task_list_link(self.link)

        task.refresh_from_db()
        self.assertIsNone(task.completed_at)
        self.assertEqual(task.completion_reason, "")
        self.assertFalse(update.called)


class OpenClawMailFolderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mail-ouder@example.com", email="mail-ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Maileerste gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)
        self.outlook = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.OUTLOOK,
            display_name="Outlook",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        self.imap = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider=IntegrationConnection.Provider.IMAP,
            display_name="Privémail",
            external_account="ouder@voorbeeld.nl",
            secret_encrypted=encrypt("app-wachtwoord"),
            settings={"host": "imap.voorbeeld.nl", "port": 993, "use_ssl": True},
        )
        # A second token for the same user would revoke the first, so the read-only token
        # belongs to the other parent in this household.
        self.reader = User.objects.create_user(username="mail-partner@example.com", email="mail-partner@example.com", password="safe-password-123", display_name="Partner")
        Membership.objects.create(household=self.household, user=self.reader, role=Membership.Role.PARENT)
        _, self.token = create_token(self.household, self.user, scopes=["outlook_mail:read", "outlook_mail:write", "imap_mail:read", "imap_mail:write"])
        _, self.read_token = create_token(self.household, self.reader, scopes=["outlook_mail:read", "imap_mail:read"])

    def _get(self, name, token=None, args=None, **params):
        return self.client.get(reverse(f"integrations:{name}", args=args or []), params, HTTP_AUTHORIZATION=f"Bearer {token or self.token}")

    def _post(self, name, payload, token=None, args=None):
        return self.client.post(
            reverse(f"integrations:{name}", args=args or []),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}",
        )

    def _imap_client(self, capabilities=("IMAP4REV1", "MOVE", "UIDPLUS"), list_data=None, found_uid=b"77", message_id="<nieuwsbrief@voorbeeld.nl>"):
        """A stand-in for imaplib. `capabilities` is what the server reports *after* logging in;
        client.capabilities keeps the poorer greeting list on purpose, because that is the trap
        real servers set — imaplib never refreshes it.
        """
        client = MagicMock()
        client.capabilities = ("IMAP4REV1",)
        client.capability.return_value = ("OK", [" ".join(capabilities).encode()])
        client.list.return_value = ("OK", list_data if list_data is not None else [b'(\\HasNoChildren) "/" "INBOX"'])
        client.create.return_value = ("OK", [b"Create completed."])
        client.subscribe.return_value = ("OK", [b"Subscribe completed."])
        client.select.return_value = ("OK", [b"3"])
        client.imap_calls = []

        def uid(command, *args):
            client.imap_calls.append((command.upper(), *args))
            if command.upper() == "FETCH":
                return ("OK", [(b"1 (UID 12 BODY[HEADER.FIELDS (MESSAGE-ID)] {40}", f"Message-ID: {message_id}\r\n\r\n".encode()), b")"])
            if command.upper() == "SEARCH":
                return ("OK", [found_uid])
            return ("OK", [None])

        client.uid.side_effect = uid
        return client

    def test_outlook_folders_are_listed_across_pages(self):
        responses = [
            FakeResponse({"value": [{"id": "map-1", "displayName": "Postvak IN", "parentFolderId": "hoofdmap", "unreadItemCount": 3, "totalItemCount": 12}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/mailFolders?$skip=100"}),
            FakeResponse({"value": [{"id": "map-2", "displayName": "Nieuwsbrieven", "parentFolderId": "hoofdmap", "unreadItemCount": 0, "totalItemCount": 4}]}),
        ]

        with patch("integrations.providers.requests.request", side_effect=responses) as request:
            response = self._get("api_openclaw_mail_folders", account="outlook")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["account"], "outlook")
        self.assertEqual([folder["name"] for folder in payload["folders"]], ["Postvak IN", "Nieuwsbrieven"])
        self.assertEqual(payload["folders"][0], {"id": "map-1", "name": "Postvak IN", "parent_id": "hoofdmap", "unread": 3, "total": 12})
        self.assertEqual(request.call_args_list[1].args[1], "https://graph.microsoft.com/v1.0/me/mailFolders?$skip=100")

    def test_outlook_folders_include_the_ones_nested_under_another_folder(self):
        responses = [
            FakeResponse({"value": [{"id": "map-1", "displayName": "Archief", "parentFolderId": "hoofdmap", "childFolderCount": 1, "unreadItemCount": 0, "totalItemCount": 2}]}),
            FakeResponse({"value": [{"id": "map-2", "displayName": "Nieuwsbrieven", "parentFolderId": "map-1", "childFolderCount": 0, "unreadItemCount": 1, "totalItemCount": 5}]}),
        ]

        with patch("integrations.providers.requests.request", side_effect=responses) as request:
            response = self._get("api_openclaw_mail_folders", account="outlook")

        self.assertEqual(response.status_code, 200)
        folders = response.json()["folders"]
        self.assertEqual([folder["name"] for folder in folders], ["Archief", "Nieuwsbrieven"])
        self.assertEqual(folders[1]["parent_id"], "map-1")
        self.assertEqual(request.call_args_list[1].args[1], "https://graph.microsoft.com/v1.0/me/mailFolders/map-1/childFolders")

    def test_imap_folders_are_listed_with_decoded_names_and_hierarchy(self):
        client = self._imap_client(list_data=[
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasChildren) "/" "Archief"',
            b'(\\HasNoChildren) "/" "Archief/Caf&AOk-"',
        ])

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._get("api_openclaw_mail_folders", account="ouder@voorbeeld.nl")

        self.assertEqual(response.status_code, 200)
        folders = response.json()["folders"]
        self.assertEqual([folder["id"] for folder in folders], ["INBOX", "Archief", "Archief/Café"])
        self.assertEqual(folders[2]["name"], "Café")
        self.assertEqual(folders[2]["parent_id"], "Archief")
        self.assertIsNone(folders[0]["parent_id"])
        client.logout.assert_called_once_with()

    def test_outlook_folder_is_created_under_its_parent(self):
        with patch("integrations.providers.requests.request", return_value=FakeResponse({"id": "map-9", "displayName": "Nieuwsbrieven", "parentFolderId": "map-1", "unreadItemCount": 0, "totalItemCount": 0})) as request:
            response = self._post("api_openclaw_mail_create_folder", {"account": "outlook", "name": "Nieuwsbrieven", "parent": "map-1"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["folder"]["id"], "map-9")
        self.assertEqual(request.call_args.args, ("POST", "https://graph.microsoft.com/v1.0/me/mailFolders/map-1/childFolders"))
        self.assertEqual(request.call_args.kwargs["json"], {"displayName": "Nieuwsbrieven"})

    def test_imap_folder_is_created_under_its_parent(self):
        client = self._imap_client(list_data=[b'(\\HasChildren) "." "Archief"'])

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._post("api_openclaw_mail_create_folder", {"account": "ouder@voorbeeld.nl", "name": "Nieuwsbrieven", "parent": "Archief"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["folder"], {"id": "Archief.Nieuwsbrieven", "name": "Nieuwsbrieven", "parent_id": "Archief", "unread": None, "total": None})
        client.create.assert_called_once_with('"Archief.Nieuwsbrieven"')
        client.subscribe.assert_called_once_with('"Archief.Nieuwsbrieven"')

    def test_folder_name_is_required(self):
        with patch("integrations.providers.requests.request") as request:
            response = self._post("api_openclaw_mail_create_folder", {"account": "outlook", "name": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Veld 'name' is verplicht.")
        self.assertFalse(request.called)

    def test_creating_a_folder_on_an_unknown_account_is_refused(self):
        response = self._post("api_openclaw_mail_create_folder", {"account": "buurman@voorbeeld.nl", "name": "Nieuwsbrieven"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Onbekend account", response.json()["error"])

    def test_creating_a_folder_needs_a_write_scope(self):
        response = self._post("api_openclaw_mail_create_folder", {"account": "outlook", "name": "Nieuwsbrieven"}, token=self.read_token)

        self.assertEqual(response.status_code, 403)

    def test_outlook_message_is_moved_and_reports_its_new_id(self):
        with patch("integrations.providers.requests.request", return_value=FakeResponse({"id": "bericht-nieuw", "parentFolderId": "map-2"})) as request:
            response = self._post("api_openclaw_mail_move", {"account": "outlook", "destination": "map-2"}, args=["bericht-oud"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"account": "outlook", "moved": True, "id": "bericht-nieuw", "folder": "map-2"})
        self.assertEqual(request.call_args.args, ("POST", "https://graph.microsoft.com/v1.0/me/messages/bericht-oud/move"))
        self.assertEqual(request.call_args.kwargs["json"], {"destinationId": "map-2"})

    def test_imap_move_uses_the_capabilities_the_server_reports_after_logging_in(self):
        client = self._imap_client()

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._post("api_openclaw_mail_move", {"account": "ouder@voorbeeld.nl", "destination": "Archief"}, args=["INBOX:12"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"account": "ouder@voorbeeld.nl", "moved": True, "id": "Archief:77", "folder": "Archief"})
        self.assertNotIn("MOVE", client.capabilities)
        self.assertEqual(client.select.call_args_list, [call('"INBOX"'), call('"Archief"', readonly=True)])
        self.assertEqual(client.imap_calls, [
            ("FETCH", "12", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])"),
            ("MOVE", "12", '"Archief"'),
            ("SEARCH", None, "HEADER", "Message-ID", '"<nieuwsbrief@voorbeeld.nl>"'),
        ])
        self.assertFalse(client.expunge.called)

    def test_imap_move_falls_back_to_copy_and_a_targeted_uid_expunge(self):
        client = self._imap_client(capabilities=("IMAP4REV1", "UIDPLUS"))

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._post("api_openclaw_mail_move", {"account": "ouder@voorbeeld.nl", "destination": "Archief"}, args=["INBOX:12"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "Archief:77")
        self.assertEqual(client.imap_calls, [
            ("FETCH", "12", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])"),
            ("COPY", "12", '"Archief"'),
            ("STORE", "12", "+FLAGS", "(\\Deleted)"),
            ("EXPUNGE", "12"),
            ("SEARCH", None, "HEADER", "Message-ID", '"<nieuwsbrief@voorbeeld.nl>"'),
        ])
        self.assertFalse(client.expunge.called)

    def test_imap_move_never_expunges_the_whole_folder_without_uidplus(self):
        client = self._imap_client(capabilities=("IMAP4REV1",))

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._post("api_openclaw_mail_move", {"account": "ouder@voorbeeld.nl", "destination": "Archief"}, args=["INBOX:12"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "Archief:77")
        self.assertFalse(client.expunge.called)
        self.assertNotIn("EXPUNGE", [call_args[0] for call_args in client.imap_calls])

    def test_imap_move_reports_no_new_id_when_the_message_cannot_be_found_back(self):
        client = self._imap_client(found_uid=b"")

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._post("api_openclaw_mail_move", {"account": "ouder@voorbeeld.nl", "destination": "Archief"}, args=["INBOX:12"])

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["id"])
        self.assertEqual(response.json()["folder"], "Archief")

    def test_a_message_in_a_nested_imap_folder_can_be_moved_and_read(self):
        client = self._imap_client()
        move_url = reverse("integrations:api_openclaw_mail_move", args=["Archief/Nieuwsbrieven:77"])

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._post("api_openclaw_mail_move", {"account": "ouder@voorbeeld.nl", "destination": "INBOX"}, args=["Archief/Nieuwsbrieven:77"])

        self.assertIn("mail/Archief/Nieuwsbrieven:77/verplaatsen/", move_url)
        self.assertEqual(response.status_code, 200)
        client.select.assert_any_call('"Archief/Nieuwsbrieven"')

    def test_imap_overview_selects_a_folder_by_its_encoded_name(self):
        client = self._imap_client()

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._get("api_openclaw_mail_overview", account="ouder@voorbeeld.nl", folder="Privé")

        self.assertEqual(response.status_code, 200)
        client.select.assert_called_once_with('"Priv&AOk-"', readonly=True)
        self.assertEqual(client.imap_calls[0], ("SEARCH", None, "UNDELETED"))
        self.assertEqual(response.json()["messages"][0]["id"], "Privé:77")

    def test_imap_read_selects_a_folder_by_its_encoded_name(self):
        client = self._imap_client()

        with patch("integrations.providers._imap_client", return_value=client):
            response = self._get("api_openclaw_mail_read", account="ouder@voorbeeld.nl", args=["Privé:77"])

        self.assertEqual(response.status_code, 200)
        client.select.assert_called_once_with('"Priv&AOk-"', readonly=True)

    def test_moving_a_message_without_a_destination_is_refused(self):
        with patch("integrations.providers.requests.request") as request:
            response = self._post("api_openclaw_mail_move", {"account": "outlook", "destination": " "}, args=["bericht-oud"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Veld 'destination' is verplicht.")
        self.assertFalse(request.called)

    def test_moving_a_message_on_an_unknown_account_is_refused(self):
        response = self._post("api_openclaw_mail_move", {"account": "buurman@voorbeeld.nl", "destination": "Archief"}, args=["INBOX:12"])

        self.assertEqual(response.status_code, 400)
        self.assertIn("Onbekend account", response.json()["error"])

    def test_moving_a_message_needs_a_write_scope(self):
        response = self._post("api_openclaw_mail_move", {"account": "outlook", "destination": "map-2"}, token=self.read_token, args=["bericht-oud"])

        self.assertEqual(response.status_code, 403)

    def test_a_token_from_another_household_reaches_no_mail_account(self):
        other_household = Household.objects.create(name="Tweede gezin")
        other_user = User.objects.create_user(username="buurman@example.com", email="buurman@example.com", password="safe-password-123")
        Membership.objects.create(household=other_household, user=other_user, role=Membership.Role.PARENT)
        _, other_token = create_token(other_household, other_user, scopes=["outlook_mail:read", "outlook_mail:write", "imap_mail:read", "imap_mail:write"])

        folders = self._get("api_openclaw_mail_folders", token=other_token, account="ouder@voorbeeld.nl")
        move = self._post("api_openclaw_mail_move", {"account": "ouder@voorbeeld.nl", "destination": "Archief"}, token=other_token, args=["INBOX:12"])
        create = self._post("api_openclaw_mail_create_folder", {"account": "ouder@voorbeeld.nl", "name": "Nieuwsbrieven"}, token=other_token)

        for response in (folders, move, create):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"], "Je hebt geen e-mailaccount gekoppeld in Instellingen.")

    def test_a_provider_failure_is_reported_as_a_readable_error(self):
        with patch("integrations.providers.requests.request", return_value=FakeResponse({"error": {"code": "ErrorAccessDenied", "message": "Toegang geweigerd."}}, ok=False)):
            response = self._post("api_openclaw_mail_move", {"account": "outlook", "destination": "map-2"}, args=["bericht-oud"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Toegang geweigerd.")


class OpenClawCalendarSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="agenda-ouder@example.com", email="agenda-ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Eerste gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)
        self.other_household = Household.objects.create(name="Tweede gezin")
        self.connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.user,
            provider="outlook",
            display_name="Outlook agenda",
            secret_encrypted=encrypt("refresh-token"),
            settings={"access_token": encrypt("access-token"), "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        )
        self.local_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda")
        self.work_source = CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.OUTLOOK, name="Werkagenda", external_id="calendar-1", connection=self.connection, is_read_only=False, sync_local_events=True)
        CalendarSource.objects.create(household=self.household, provider=CalendarSource.Provider.ICS, name="Feestdagen", is_read_only=True, sync_local_events=False)
        CalendarSource.objects.create(household=self.other_household, provider=CalendarSource.Provider.OUTLOOK, name="Agenda van de buren")
        _, self.token = create_token(self.household, self.user, scopes=["agenda:read"])

    def _sources(self):
        response = self.client.get(reverse("integrations:api_openclaw_calendar_sources"), HTTP_AUTHORIZATION=f"Bearer {self.token}")
        return {source["name"]: source for source in response.json()["sources"]}

    def test_sources_report_where_a_local_event_ends_up(self):
        response = self.client.get(reverse("integrations:api_openclaw_calendar_sources"), HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.assertEqual(response.status_code, 200)
        sources = {source["name"]: source for source in response.json()["sources"]}
        self.assertEqual(sorted(sources), ["Feestdagen", "Gezinsagenda", "Werkagenda"])
        self.assertTrue(sources["Werkagenda"]["sends_local_events"])
        self.assertTrue(sources["Werkagenda"]["supports_write_back"])
        self.assertFalse(sources["Feestdagen"]["sends_local_events"])
        self.assertFalse(sources["Feestdagen"]["supports_write_back"])
        self.assertFalse(sources["Gezinsagenda"]["supports_write_back"])
        # The family calendar has nowhere to push to, so it must never claim it does.
        self.assertFalse(sources["Gezinsagenda"]["sends_local_events"])

    def test_a_hidden_calendar_does_not_claim_to_receive_events(self):
        self.work_source.is_enabled = False
        self.work_source.save(update_fields=["is_enabled", "updated_at"])

        self.assertFalse(self._sources()["Werkagenda"]["sends_local_events"])

    def test_a_calendar_without_its_outlook_connection_does_not_claim_to_receive_events(self):
        self.connection.delete()

        self.work_source.refresh_from_db()
        self.assertTrue(self.work_source.sync_local_events)
        self.assertFalse(self._sources()["Werkagenda"]["sends_local_events"])

    def test_another_households_calendars_are_never_returned(self):
        response = self.client.get(reverse("integrations:api_openclaw_calendar_sources"), HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.assertNotIn("Agenda van de buren", [source["name"] for source in response.json()["sources"]])

    def test_sources_need_the_agenda_read_scope(self):
        _, other_token = create_token(self.household, self.user, scopes=["vandaag:read"])

        response = self.client.get(reverse("integrations:api_openclaw_calendar_sources"), HTTP_AUTHORIZATION=f"Bearer {other_token}")

        self.assertEqual(response.status_code, 403)

    def test_updating_an_event_queues_it_for_the_next_push(self):
        _, write_token = create_token(self.household, self.user, scopes=["agenda:write"])
        start = timezone.now().replace(second=0, microsecond=0)
        event = CalendarEvent.objects.create(household=self.household, title="Tandarts", starts_at=start, ends_at=start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.SYNCED, last_sync_error="oude fout")

        response = self.client.post(
            reverse("integrations:api_openclaw_update_event", args=[event.id]),
            data=json.dumps({"location": "Praktijk"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {write_token}",
        )

        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.location, "Praktijk")
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.PENDING)
        self.assertEqual(event.last_sync_error, "")

    def test_an_event_added_by_openclaw_is_pushed_to_the_linked_outlook_calendar(self):
        _, write_token = create_token(self.household, self.user, scopes=["agenda:write"])
        start = timezone.now().replace(second=0, microsecond=0)
        calls = []

        def graph_request(method, url, **_kwargs):
            calls.append((method, url))
            return FakeResponse({"id": "graph-event-3"}, status_code=201)

        response = self.client.post(
            reverse("integrations:api_openclaw_add_event"),
            data=json.dumps({"title": "Tandarts", "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=1)).isoformat()}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {write_token}",
        )

        self.assertEqual(response.status_code, 201)

        with patch("integrations.providers.requests.request", side_effect=graph_request):
            sync_pending_events_to_remote()

        self.assertEqual(calls, [("POST", "https://graph.microsoft.com/v1.0/me/calendars/calendar-1/events")])
        event = CalendarEvent.objects.get(household=self.household, title="Tandarts")
        self.assertEqual(event.external_id, "graph-event-3")
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.SYNCED)

    def test_an_event_from_an_outlook_calendar_cannot_be_rewritten(self):
        _, write_token = create_token(self.household, self.user, scopes=["agenda:write"])
        start = timezone.now().replace(second=0, microsecond=0)
        event = CalendarEvent.objects.create(household=self.household, source=self.work_source, external_id="graph-event-9", title="Teamoverleg", starts_at=start, ends_at=start + timedelta(hours=1), sync_status=CalendarEvent.SyncStatus.SYNCED)

        response = self.client.post(
            reverse("integrations:api_openclaw_update_event", args=[event.id]),
            data=json.dumps({"title": "Gekaapt via OpenClaw"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {write_token}",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Externe agenda-afspraken zijn alleen-lezen.")
        event.refresh_from_db()
        self.assertEqual(event.title, "Teamoverleg")
        self.assertEqual(event.sync_status, CalendarEvent.SyncStatus.SYNCED)

    def test_updating_an_event_from_another_household_is_not_found(self):
        _, write_token = create_token(self.household, self.user, scopes=["agenda:write"])
        start = timezone.now().replace(second=0, microsecond=0)
        other_event = CalendarEvent.objects.create(household=self.other_household, title="Afspraak van de buren", starts_at=start, ends_at=start + timedelta(hours=1))

        response = self.client.post(
            reverse("integrations:api_openclaw_update_event", args=[other_event.id]),
            data=json.dumps({"location": "Niet van dit gezin"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {write_token}",
        )

        self.assertEqual(response.status_code, 404)
        other_event.refresh_from_db()
        self.assertEqual(other_event.location, "")


class OpenClawTravelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reis-ouder@example.com", email="reis-ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.household = Household.objects.create(name="Eerste gezin")
        Membership.objects.create(household=self.household, user=self.user, role=Membership.Role.PARENT)
        self.other_household = Household.objects.create(name="Tweede gezin")
        self.trip = Trip.objects.create(household=self.household, destination="Barcelona", start_date=date(2026, 8, 1))
        TripStop.objects.create(household=self.household, trip=self.trip, name="Girona", arrives_on=date(2026, 8, 3))
        TripDocument.objects.create(household=self.household, trip=self.trip, title="Vluchtbevestiging", url="https://example.com/ticket")
        TripIdea.objects.create(household=self.household, trip=self.trip, text="Sagrada Familia bezoeken", author=self.user)
        self.other_trip = Trip.objects.create(household=self.other_household, destination="Reis van de buren")
        _, self.token = create_token(self.household, self.user, scopes=["reizen:read", "reizen:write"])

    def _post(self, name, args, payload, token=None):
        return self.client.post(
            reverse(f"integrations:{name}", args=args),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}",
        )

    def test_trips_carry_their_stops_documents_ideas_and_task_list(self):
        task_list = ensure_trip_task_list(self.trip)
        Task.objects.create(household=self.household, list=task_list, title="Koffers pakken")

        response = self.client.get(reverse("integrations:api_openclaw_trips"), HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.assertEqual(response.status_code, 200)
        trip = response.json()["trips"][0]
        self.assertEqual(trip["destination"], "Barcelona")
        self.assertEqual(trip["start_date"], "2026-08-01")
        self.assertEqual([stop["name"] for stop in trip["stops"]], ["Girona"])
        self.assertEqual([document["title"] for document in trip["documents"]], ["Vluchtbevestiging"])
        self.assertEqual([idea["text"] for idea in trip["ideas"]], ["Sagrada Familia bezoeken"])
        self.assertEqual(trip["task_list"]["name"], "Reis: Barcelona")
        self.assertEqual(trip["task_list"]["open_tasks"], 1)
        self.assertEqual([task["title"] for task in trip["task_list"]["tasks"]], ["Koffers pakken"])

    def test_trips_never_include_a_trip_of_another_household(self):
        response = self.client.get(reverse("integrations:api_openclaw_trips"), HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.assertEqual([trip["destination"] for trip in response.json()["trips"]], ["Barcelona"])

    def test_new_trip_gets_a_linked_task_list_and_its_stops(self):
        response = self._post("api_openclaw_add_trip", [], {
            "destination": "Ardennen",
            "start_date": "2026-10-01",
            "end_date": "2026-10-05",
            "stops": [{"name": "Namen", "arrives_on": "2026-10-02"}, "Dinant"],
        })

        self.assertEqual(response.status_code, 201)
        trip = Trip.objects.get(household=self.household, destination="Ardennen")
        self.assertEqual(trip.task_list.name, "Reis: Ardennen")
        self.assertTrue(response.json()["task_list_created"])
        self.assertEqual([stop.name for stop in trip.stops.all()], ["Namen", "Dinant"])
        self.assertEqual(response.json()["task_list"]["name"], "Reis: Ardennen")

    def test_trip_without_a_destination_is_refused(self):
        response = self._post("api_openclaw_add_trip", [], {"start_date": "2026-10-01"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Veld 'destination' is verplicht.")

    def test_update_only_touches_the_keys_it_was_given(self):
        response = self._post("api_openclaw_update_trip", [self.trip.id], {"end_date": "2026-08-12", "notes": "Vlucht bevestigd, KL1234"})

        self.assertEqual(response.status_code, 200)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.destination, "Barcelona")
        self.assertEqual(self.trip.start_date, date(2026, 8, 1))
        self.assertEqual(self.trip.end_date, date(2026, 8, 12))
        self.assertEqual(self.trip.notes, "Vlucht bevestigd, KL1234")

    def test_update_without_any_field_is_refused(self):
        response = self._post("api_openclaw_update_trip", [self.trip.id], {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Geef minstens één veld op om te wijzigen.")

    def test_update_with_a_return_before_departure_is_refused(self):
        response = self._post("api_openclaw_update_trip", [self.trip.id], {"end_date": "2026-07-01"})

        self.assertEqual(response.status_code, 400)
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.end_date)

    def test_document_is_attached_by_dropbox_path(self):
        response = self._post("api_openclaw_add_trip_document", [self.trip.id], {"title": "Hotelboeking", "dropbox_path": "/Reizen/Barcelona/hotel.pdf"})

        self.assertEqual(response.status_code, 201)
        document = TripDocument.objects.get(household=self.household, title="Hotelboeking")
        self.assertEqual(document.dropbox_path, "/Reizen/Barcelona/hotel.pdf")
        self.assertEqual(document.url, "")
        self.assertEqual(document.uploaded_by, self.user)

    def test_document_needs_exactly_one_source(self):
        both = self._post("api_openclaw_add_trip_document", [self.trip.id], {"title": "Twee bronnen", "url": "https://example.com/a", "dropbox_path": "/Reizen/a.pdf"})
        neither = self._post("api_openclaw_add_trip_document", [self.trip.id], {"title": "Geen bron"})

        self.assertEqual(both.status_code, 400)
        self.assertEqual(neither.status_code, 400)
        self.assertEqual(both.json()["error"], "Geef precies één bron op: 'url' of 'dropbox_path'.")
        self.assertEqual(TripDocument.objects.filter(household=self.household).count(), 1)

    def test_agent_idea_is_marked_as_created_by_the_agent(self):
        response = self._post("api_openclaw_add_trip_idea", [self.trip.id], {"text": "Museum met kinderkorting"})

        self.assertEqual(response.status_code, 201)
        idea = TripIdea.objects.get(household=self.household, text="Museum met kinderkorting")
        self.assertTrue(idea.created_by_agent)
        self.assertEqual(idea.author, self.user)

    def test_writing_needs_the_reizen_write_scope(self):
        _, read_only_token = create_token(self.household, self.user, scopes=["reizen:read"])

        response = self._post("api_openclaw_add_trip", [], {"destination": "Mag niet"}, token=read_only_token)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Trip.objects.filter(destination="Mag niet").exists())

    def test_reading_needs_the_reizen_read_scope(self):
        _, write_only_token = create_token(self.household, self.user, scopes=["reizen:write"])

        response = self.client.get(reverse("integrations:api_openclaw_trips"), HTTP_AUTHORIZATION=f"Bearer {write_only_token}")

        self.assertEqual(response.status_code, 403)

    def test_every_mutating_endpoint_refuses_a_trip_of_another_household(self):
        endpoints = [
            ("api_openclaw_update_trip", {"destination": "Overgenomen"}),
            ("api_openclaw_add_trip_document", {"title": "Ongewenst", "url": "https://example.com/x"}),
            ("api_openclaw_add_trip_idea", {"text": "Ongewenst idee"}),
        ]

        for name, payload in endpoints:
            with self.subTest(endpoint=name):
                response = self._post(name, [self.other_trip.id], payload)
                self.assertEqual(response.status_code, 404)

        self.other_trip.refresh_from_db()
        self.assertEqual(self.other_trip.destination, "Reis van de buren")
        self.assertFalse(TripDocument.objects.filter(trip=self.other_trip).exists())
        self.assertFalse(TripIdea.objects.filter(trip=self.other_trip).exists())
