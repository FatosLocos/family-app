from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from home.ha_contract import FAMILY_APP_HA_DOMAIN, family_app_home_assistant_contract
from home.ha_gateway import HomeAssistantRegistries, _upsert_state, apply_state_changed, websocket_url
from home.models import HomeActionAudit, HomeAssistantConfig, HomeEntity
from home.consumers import HomeLiveConsumer
from home.realtime import home_entity_payload
from home.services import HomeAssistantError, control_entity, sync_entities
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt
from integrations.models import IntegrationConnection, SyncRun


class FakeResponse:
    ok = True
    content = b"[]"

    def __init__(self, payload=None):
        self.payload = payload or []

    def json(self):
        return self.payload


class HomeAssistantTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent@example.com", email="parent@example.com", password="safe-password-123")
        self.child = User.objects.create_user(username="child@example.com", email="child@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.parent, role=Membership.Role.PARENT)
        Membership.objects.create(household=self.household, user=self.child, role=Membership.Role.CHILD)
        HomeAssistantConfig.objects.create(household=self.household, base_url="http://homeassistant.local:8123", token_encrypted=encrypt("secret"))

    @patch("home.services.requests.request")
    def test_sync_stores_supported_entities_and_keeps_unknown_read_only(self, request):
        request.return_value = FakeResponse([
            {"entity_id": "light.keuken", "state": "on", "attributes": {"friendly_name": "Keuken"}},
            {"entity_id": "sensor.temp", "state": "19", "attributes": {"friendly_name": "Temperatuur"}},
        ])
        self.assertEqual(sync_entities(self.household), 2)
        self.assertTrue(HomeEntity.objects.get(entity_id="light.keuken").is_supported)
        self.assertFalse(HomeEntity.objects.get(entity_id="sensor.temp").is_supported)

    @patch("home.services.requests.request")
    def test_control_uses_server_side_service_call_and_audits(self, request):
        request.side_effect = [FakeResponse({}), FakeResponse([])]
        entity = HomeEntity.objects.create(household=self.household, entity_id="switch.koffie", domain="switch", name="Koffie", is_supported=True)
        control_entity(self.household, entity, "on")
        self.assertIn("/api/services/switch/turn_on", request.call_args_list[0].args[1])
        self.assertTrue(HomeActionAudit.objects.get(entity=entity).succeeded)

    @patch("home.services.requests.request")
    def test_control_uses_domain_specific_cover_and_climate_services(self, request):
        request.side_effect = [FakeResponse({}), FakeResponse([]), FakeResponse({}), FakeResponse([])]
        cover = HomeEntity.objects.create(household=self.household, entity_id="cover.gordijnen", domain="cover", name="Gordijnen", is_supported=True)
        climate = HomeEntity.objects.create(household=self.household, entity_id="climate.woonkamer", domain="climate", name="Woonkamer", is_supported=True, attributes={"min_temp": 10, "max_temp": 28})

        control_entity(self.household, cover, "stop")
        control_entity(self.household, climate, "set_temperature", "21,5")

        self.assertIn("/api/services/cover/stop_cover", request.call_args_list[0].args[1])
        self.assertEqual(request.call_args_list[2].kwargs["json"], {"entity_id": "climate.woonkamer", "temperature": 21.5})
        self.assertIn("/api/services/climate/set_temperature", request.call_args_list[2].args[1])
        self.assertEqual(HomeActionAudit.objects.get(entity=climate).detail, "Via Home Assistant: Temperatuur ingesteld op 21.5 °C.")

    def test_invalid_home_action_is_rejected_and_audited(self):
        entity = HomeEntity.objects.create(household=self.household, entity_id="scene.avondsfeer", domain="scene", name="Avondsfeer", is_supported=True)
        with self.assertRaises(HomeAssistantError):
            control_entity(self.household, entity, "off")
        audit = HomeActionAudit.objects.get(entity=entity)
        self.assertFalse(audit.succeeded)
        self.assertEqual(audit.action, "off")

    @patch("integrations.providers.control_hue_light", return_value="Ingeschakeld.")
    @patch("home.services._request", side_effect=HomeAssistantError("Home Assistant is niet bereikbaar."))
    def test_home_assistant_control_can_fallback_to_matching_direct_entity(self, request, control_hue_light):
        ha_entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HOME_ASSISTANT,
            entity_id="light.koffie",
            domain="light",
            name="Koffie",
            is_supported=True,
            attributes={"ha_device_identifiers": ["hue:lamp-1"]},
        )
        direct_entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.lamp-1",
            domain="light",
            name="Koffie",
            is_supported=True,
            attributes={"hue_light_id": "lamp-1"},
        )

        control_entity(self.household, ha_entity, "on")

        control_hue_light.assert_called_once_with(direct_entity, "on", None)
        self.assertTrue(HomeActionAudit.objects.filter(entity=ha_entity, succeeded=True, detail__startswith="Via fallback").exists())

    def test_child_can_view_but_cannot_save_or_control(self):
        entity = HomeEntity.objects.create(household=self.household, entity_id="light.kamer", domain="light", name="Kamer", is_supported=True)
        self.client.force_login(self.child)
        self.assertEqual(self.client.get(reverse("home:index")).status_code, 200)
        self.assertEqual(self.client.post(reverse("home:save_home_assistant"), {"base_url": "http://ha.local", "token": "new"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("home:control", args=[entity.id, "on"])).status_code, 403)

    @patch("home.views.control_entity", return_value={"queued": True, "command_id": "probe-command-1"})
    def test_local_probe_control_waits_for_confirmation_in_the_browser(self, control):
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="probe.test.hue.light-1",
            domain="light",
            name="Keuken",
            state="off",
            is_supported=True,
            attributes={"probe_id": "probe-1", "probe_local_key": "light:light-1"},
        )
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("home:control", args=[entity.id, "on"]),
            HTTP_HX_REQUEST="true",
        )

        payload = json.loads(response["HX-Trigger"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["family:home-control"]["command_id"], "probe-command-1")
        self.assertTrue(payload["family:home-control"]["queued"])
        self.assertIn("opdracht verzonden", payload["family:toast"]["message"])
        control.assert_called_once_with(self.household, entity, "on", None)

    def test_parent_can_manage_household_home_records(self):
        self.client.force_login(self.parent)
        self.client.post(reverse("home:add_maintenance"), {"title": "Cv-ketel", "category": "Installatie", "cadence_days": 365})
        self.client.post(reverse("home:add_emergency_contact"), {"label": "Huisarts", "value": "010-1234567", "kind": "contact"})
        self.client.post(reverse("home:add_room"), {"name": "Zolder", "icon": "lamp"})
        response = self.client.get(reverse("home:index"), {"tab": "inrichting"})
        self.assertContains(response, "Zolder")
        self.assertContains(self.client.get(reverse("home:index"), {"tab": "onderhoud"}), "Cv-ketel")

    def test_home_connect_toolbar_reports_discovered_devices_and_links_to_them(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            status="configured",
        )
        HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id="home_connect.1.dishwasher",
            domain="dishwasher",
            name="Vaatwasser",
            is_available=True,
            is_supported=True,
            attributes={
                "home_connect_icon": "dishwasher",
                "home_connect_brand": "Siemens",
                "home_connect_type": "Dishwasher",
                "home_connect_type_label": "Vaatwasser",
            },
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "1 apparaat gevonden")
        self.assertContains(response, "source=home_connect")

    def test_home_connect_card_uses_compact_status_and_labelled_actions(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Home Connect",
            status="configured",
        )
        HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HOME_CONNECT,
            entity_id="home_connect.1.dishwasher",
            domain="dishwasher",
            name="Siemens vaatwasser",
            state="ready",
            is_available=True,
            is_supported=True,
            attributes={
                "home_connect_icon": "dishwasher",
                "home_connect_brand": "Siemens",
                "home_connect_type": "Dishwasher",
                "home_connect_type_label": "Vaatwasser",
                "home_connect_operation": "Gereed",
                "home_connect_selected_program": "Eco 50 °C",
                "home_connect_selected_program_key": "Dishcare.Dishwasher.Program.Eco50",
                "home_connect_door_label": "Deur gesloten",
                "home_connect_program_forecasts": {"energy": 47, "water": 43},
                "home_connect_can_start": True,
                "home_connect_can_select_program": True,
                "home_connect_programs": [{"key": "Dishcare.Dishwasher.Program.Eco50", "label": "Eco 50 °C", "options": []}],
            },
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "home_connect", "domain": "apparaten"})

        self.assertContains(response, "Gereed")
        self.assertContains(response, "Eco 50 °C")
        self.assertContains(response, "47%")
        self.assertContains(response, "43%")
        self.assertContains(response, "Kiezen")
        self.assertContains(response, "Start")
        self.assertNotContains(response, "Gereed ·")

    def test_active_google_cast_card_exposes_stop_control(self):
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.GOOGLE_CAST,
            entity_id="probe.cast.woonkamer",
            domain="media_player",
            name="Woonkamer TV",
            state="on",
            is_available=True,
            is_supported=True,
            attributes={
                "cast_player_state": "PLAYING",
                "cast_volume": 24,
                "cast_muted": False,
                "cast_title": "Testnummer",
                "cast_artist": "Testartiest",
                "cast_position": 12,
                "cast_duration": 180,
            },
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "google_cast", "domain": "apparaten"})

        self.assertContains(response, reverse("home:control", args=[entity.id, "stop"]))
        self.assertContains(response, "Afspelen stoppen")
        self.assertContains(response, "data-cast-now-playing")
        self.assertContains(response, "data-cast-progress-wrap")
        self.assertContains(response, "data-sonos-play-toggle")

    def test_idle_google_cast_card_uses_a_human_status(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.GOOGLE_CAST,
            entity_id="probe.cast.slaapkamer",
            domain="media_player",
            name="Slaapkamer",
            state="off",
            is_available=True,
            is_supported=True,
            attributes={"cast_player_state": "IDLE", "cast_volume": 18, "cast_muted": True},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "google_cast", "domain": "apparaten"})

        self.assertContains(response, "Gereed")
        self.assertContains(response, "Gedempt")
        self.assertNotContains(response, "Idle")

    def test_google_cast_card_does_not_expose_the_internal_entity_id(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.GOOGLE_CAST,
            entity_id="probe.local.google_cast.6d219e1b-a8a2",
            domain="media_player",
            name="Milan kamer",
            state="off",
            is_available=True,
            is_supported=True,
            attributes={"cast_model": "Google Nest Mini", "cast_player_state": "IDLE"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "google_cast", "domain": "apparaten"})

        self.assertContains(response, "Google Cast · Google Nest Mini")
        self.assertNotContains(response, "probe.local.google_cast.6d219e1b-a8a2")

    def test_active_home_connect_connection_uses_its_provider_name(self):
        IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HOME_CONNECT,
            display_name="Siemens",
            status="configured",
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "Home Connect")
        self.assertNotContains(response, "<strong>Koppeling <span", html=False)

    def test_unpaired_philips_tv_shows_a_contextual_local_pairing_command(self):
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.PHILIPS_TV,
            entity_id="probe.tv.woonkamer",
            domain="media_player",
            name="Philips TV woonkamer",
            state="on",
            is_available=True,
            is_supported=False,
            attributes={"philips_model": "55OLED706/12", "philips_requires_pairing": True, "probe_local_key": "192.168.1.234"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "philips_tv", "domain": "apparaten"})

        self.assertContains(response, "TV koppelen")
        self.assertContains(response, f'philips-tv-pairing-dialog-{entity.id}')
        self.assertContains(response, "philips-tv-link --host 192.168.1.234")

    def test_paired_philips_tv_exposes_the_compact_remote_dialog(self):
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.PHILIPS_TV,
            entity_id="probe.tv.philips-tv.woonkamer",
            domain="media_player",
            name="Philips TV woonkamer",
            is_available=True,
            is_supported=True,
            attributes={"philips_model": "55OLED706/12", "probe_local_key": "192.168.1.234"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "philips_tv", "domain": "apparaten"})

        self.assertContains(response, f'philips-tv-controls-dialog-{entity.id}')
        self.assertContains(response, 'value="CursorUp"')
        self.assertContains(response, 'value="AmbilightOnOff"')
        self.assertContains(response, 'value="Standby"')

    def test_home_assistant_interface_names_the_rest_api_integration(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("home:index"))
        self.assertContains(response, "Home Assistant")
        self.assertContains(response, "REST + realtime")

    def test_home_assistant_state_stores_registry_metadata(self):
        registries = HomeAssistantRegistries(
            entities={"light.keuken": {"entity_id": "light.keuken", "device_id": "device-1", "area_id": "area-1", "platform": "hue", "device_class": "light"}},
            devices={"device-1": {"id": "device-1", "name": "Hue bridge lamp", "identifiers": [["hue", "lamp-1"]]}},
            areas={"area-1": {"area_id": "area-1", "name": "Keuken"}},
        )

        entity = _upsert_state(
            self.household,
            {"entity_id": "light.keuken", "state": "on", "last_changed": "2026-07-14T10:00:00Z", "attributes": {"friendly_name": "Keukenlamp"}},
            registries,
            should_broadcast=False,
        )

        self.assertEqual(entity.source, HomeEntity.Source.HOME_ASSISTANT)
        self.assertEqual(entity.attributes["ha_area"], "Keuken")
        self.assertEqual(entity.attributes["ha_device_identifiers"], ["hue:lamp-1"])
        self.assertEqual(entity.attributes["ha_platform"], "hue")
        self.assertEqual(entity.attributes["ha_last_changed"], "2026-07-14T10:00:00Z")

    def test_home_assistant_state_changed_event_updates_entity(self):
        event = {"data": {"new_state": {"entity_id": "switch.koffie", "state": "on", "attributes": {"friendly_name": "Koffie"}}}}

        entity = apply_state_changed(HomeAssistantConfig.objects.get(household=self.household), event)

        self.assertEqual(entity.state, "on")
        self.assertEqual(entity.name, "Koffie")

    def test_home_assistant_websocket_url_uses_matching_scheme(self):
        self.assertEqual(websocket_url("http://ha.local:8123"), "ws://ha.local:8123/api/websocket")
        self.assertEqual(websocket_url("https://ha.example.nl"), "wss://ha.example.nl/api/websocket")

    def test_family_app_home_assistant_contract_reserves_expected_namespace(self):
        contract = family_app_home_assistant_contract()

        self.assertEqual(contract["domain"], FAMILY_APP_HA_DOMAIN)
        self.assertEqual(contract["version"], 1)
        self.assertIn("family_open_tasks", {entity["object_id"] for entity in contract["entities"]})
        self.assertIn("family", {entity["object_id"] for entity in contract["entities"]})
        self.assertIn("family_shopping", {entity["object_id"] for entity in contract["entities"]})
        self.assertIn("family_maintenance_due", {entity["object_id"] for entity in contract["entities"]})
        self.assertIn("family_app.task_completed", {event["event_type"] for event in contract["events"]})

    @patch("home.management.commands.listen_home_assistant.sync_once", return_value=3)
    def test_listen_home_assistant_once_syncs_configured_households(self, sync_once):
        output = StringIO()

        call_command("listen_home_assistant", "--once", stdout=output)

        self.assertEqual(sync_once.call_count, 1)
        self.assertIn("3 Home Assistant-entiteiten bijgewerkt.", output.getvalue())

    @patch("home.management.commands.listen_home_assistant.sync_once", side_effect=RuntimeError("geen verbinding"))
    def test_listen_home_assistant_once_records_errors(self, sync_once):
        output = StringIO()

        call_command("listen_home_assistant", "--once", stdout=output)

        config = HomeAssistantConfig.objects.get(household=self.household)
        self.assertEqual(sync_once.call_count, 1)
        self.assertEqual(config.last_error, "geen verbinding")

    def test_hue_light_control_is_server_side_and_audited(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            settings={"bridge_username": "bridge-user"},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id=f"hue.{connection.id}.1",
            domain="light",
            name="Keuken",
            is_supported=True,
            attributes={"hue_light_id": "1", "brightness": 120},
        )

        with patch("integrations.providers.control_hue_light", return_value="Helderheid ingesteld op 50%.") as control:
            control_entity(self.household, entity, "brightness", "127")

        control.assert_called_once_with(entity, "brightness", "127")
        entity.refresh_from_db()
        self.assertEqual(entity.state, "on")
        self.assertEqual(entity.attributes["brightness"], 127.0)
        audit = HomeActionAudit.objects.get(entity=entity)
        self.assertTrue(audit.succeeded)
        self.assertEqual(audit.detail, "Helderheid ingesteld op 50%.")

    def test_async_control_returns_a_toast_and_state_event(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            settings={"bridge_username": "bridge-user"},
        )
        entity = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id=f"hue.{connection.id}.1",
            domain="light",
            name="Keuken",
            is_supported=True,
            attributes={"hue_light_id": "1"},
        )
        self.client.force_login(self.parent)

        with patch("integrations.providers.control_hue_light", return_value="Ingeschakeld."):
            response = self.client.post(
                reverse("home:control", args=[entity.id, "on"]),
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        trigger = response.headers["HX-Trigger"]
        self.assertIn('"family:toast"', trigger)
        self.assertIn('"family:home-control"', trigger)
        self.assertIn(f'"entity_id": {entity.id}', trigger)

    def test_hue_scene_activation_marks_other_scenes_in_the_same_room_idle(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            settings={"bridge_username": "bridge-user"},
        )
        active_scene = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id="hue.scene.active",
            domain="scene",
            name="Lezen",
            state="active",
            is_supported=True,
            attributes={"hue_scene_id": "scene-active", "hue_resource_type": "scene", "hue_group_name": "Woonkamer"},
        )
        new_scene = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id="hue.scene.new",
            domain="scene",
            name="Film",
            state="idle",
            is_supported=True,
            attributes={"hue_scene_id": "scene-new", "hue_resource_type": "scene", "hue_group_name": "Woonkamer"},
        )

        with patch("integrations.providers.control_hue_light", return_value="Scène gestart."):
            control_entity(self.household, new_scene, "activate")

        active_scene.refresh_from_db()
        new_scene.refresh_from_db()
        self.assertEqual(active_scene.state, "idle")
        self.assertEqual(new_scene.state, "active")

    def test_hue_group_command_updates_visible_member_lights(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            settings={"bridge_username": "bridge-user"},
        )
        group = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.HUE,
            entity_id="hue.group.keuken",
            domain="group",
            name="Keuken",
            is_supported=True,
            attributes={"hue_grouped_light_id": "group-1", "hue_resource_type": "grouped_light", "member_light_ids": ["light-1", "light-2"]},
        )
        members = [
            HomeEntity.objects.create(household=self.household, connection=connection, source=HomeEntity.Source.HUE, entity_id=f"hue.{light_id}", domain="light", name=light_id, attributes={"hue_light_id": light_id})
            for light_id in ("light-1", "light-2")
        ]

        with patch("integrations.providers.control_hue_light", return_value="Ingeschakeld."):
            control_entity(self.household, group, "on")

        for member in members:
            member.refresh_from_db()
            self.assertEqual(member.state, "on")

    def test_hue_toolbar_shows_latest_sync_result(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            status="configured",
        )
        SyncRun.objects.create(household=self.household, connection=connection, status="succeeded", detail="{'lights': 3, 'groups': 1, 'scenes': 2}")

        self.client.force_login(self.parent)
        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "Laatste synchronisatie voltooid")
        self.assertContains(response, "3 lampen")
        self.assertContains(response, "1 kamer of zone")
        self.assertContains(response, "Automatisch elke 15 minuten bijgewerkt")

    def test_hue_toolbar_warns_when_the_last_sync_is_stale(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            status="configured",
        )
        from django.utils import timezone
        connection.last_sync_at = timezone.now() - timedelta(minutes=21)
        connection.save(update_fields=["last_sync_at"])
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "Status is ouder dan 20 minuten")

    def test_hue_toolbar_allows_retry_after_a_sync_error(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.HUE,
            display_name="Philips Hue",
            status="sync_error",
            settings={"bridge_username": "bridge-user"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "De laatste synchronisatie is niet gelukt")
        self.assertContains(response, reverse("integrations:sync_connection", args=[connection.id]))

    def test_home_can_filter_entities_by_source(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.living-room",
            domain="light",
            name="Hue woonkamer",
        )
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HOME_ASSISTANT,
            entity_id="switch.coffee",
            domain="switch",
            name="Home Assistant koffie",
        )

        self.client.force_login(self.parent)
        response = self.client.get(reverse("home:index"), {"source": "hue"})

        self.assertContains(response, "Hue woonkamer")
        self.assertNotContains(response, "Home Assistant koffie")
        self.assertNotContains(response, '>switch<', html=False)

    def test_home_assistant_area_is_available_as_room_filter(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HOME_ASSISTANT,
            entity_id="light.keuken",
            domain="light",
            name="Keukenlamp",
            attributes={"ha_area": "Keuken"},
        )
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HOME_ASSISTANT,
            entity_id="light.slaapkamer",
            domain="light",
            name="Slaapkamerlamp",
            attributes={"ha_area": "Slaapkamer"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"location": "Keuken"})

        self.assertContains(response, "Keukenlamp")
        self.assertNotContains(response, "Slaapkamerlamp")
        self.assertContains(response, "Keuken")

    def test_home_assistant_entity_hides_matching_direct_entity(self):
        ha_entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HOME_ASSISTANT,
            entity_id="light.woonkamer",
            domain="light",
            name="Woonkamerlamp",
            attributes={"ha_device_identifiers": ["hue:lamp-1"]},
        )
        direct_entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.lamp-1",
            domain="light",
            name="Woonkamerlamp",
            attributes={"hue_light_id": "lamp-1"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"domain": "alles"})

        displayed_ids = {entity.id for entity in response.context["display_entities"]}
        self.assertIn(ha_entity.id, displayed_ids)
        self.assertNotIn(direct_entity.id, displayed_ids)

    def test_local_sonos_group_replaces_matching_cloud_group_and_player(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
        )
        cloud_group = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SONOS,
            entity_id=f"sonos.{connection.id}.group.cloud-woonkamer",
            domain="media_player",
            name="Woonkamer cloud",
            attributes={"sonos_entity_type": "group", "sonos_coordinator_id": "player-woonkamer", "sonos_player_ids": ["player-woonkamer"]},
        )
        cloud_player = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SONOS,
            entity_id=f"sonos.{connection.id}.player.player-woonkamer",
            domain="speaker",
            name="Woonkamer speaker",
            attributes={"sonos_entity_type": "player", "sonos_player_id": "player-woonkamer"},
        )
        local_group = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.SONOS,
            entity_id="probe.local.sonos.group.player-woonkamer",
            domain="speaker",
            name="Woonkamer lokaal",
            attributes={"probe_id": "probe-1", "sonos_entity_type": "group", "sonos_player_ids": ["player-woonkamer", "player-surround"]},
        )
        other_group = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SONOS,
            entity_id=f"sonos.{connection.id}.group.slaapkamer",
            domain="media_player",
            name="Slaapkamer",
            attributes={"sonos_entity_type": "group", "sonos_coordinator_id": "player-slaapkamer", "sonos_player_ids": ["player-slaapkamer"]},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "sonos", "domain": "alles"})

        displayed_ids = {entity.id for entity in response.context["display_entities"]}
        self.assertIn(local_group.id, displayed_ids)
        self.assertIn(other_group.id, displayed_ids)
        self.assertNotIn(cloud_group.id, displayed_ids)
        self.assertNotIn(cloud_player.id, displayed_ids)

    def test_offline_local_sonos_group_falls_back_to_matching_cloud_group(self):
        connection = IntegrationConnection.objects.create(
            household=self.household,
            user=self.parent,
            provider=IntegrationConnection.Provider.SONOS,
            display_name="Sonos",
        )
        cloud_group = HomeEntity.objects.create(
            household=self.household,
            connection=connection,
            source=HomeEntity.Source.SONOS,
            entity_id=f"sonos.{connection.id}.group.cloud-woonkamer",
            domain="media_player",
            name="Woonkamer cloud",
            attributes={"sonos_entity_type": "group", "sonos_coordinator_id": "player-woonkamer", "sonos_player_ids": ["player-woonkamer"]},
        )
        local_group = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.SONOS,
            entity_id="probe.local.sonos.group.player-woonkamer",
            domain="speaker",
            name="Woonkamer lokaal",
            is_available=False,
            attributes={"probe_id": "probe-1", "sonos_entity_type": "group", "sonos_player_ids": ["player-woonkamer"]},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "sonos", "domain": "alles"})

        displayed_ids = {entity.id for entity in response.context["display_entities"]}
        self.assertIn(cloud_group.id, displayed_ids)
        self.assertNotIn(local_group.id, displayed_ids)


    def test_home_can_filter_hue_entities_by_room(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.kitchen",
            domain="light",
            name="Keukenlamp",
            attributes={"hue_locations": ["Keuken"]},
        )
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.bedroom",
            domain="light",
            name="Slaapkamerlamp",
            attributes={"hue_locations": ["Slaapkamer"]},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "hue", "location": "Keuken"})

        self.assertContains(response, "Keukenlamp")
        self.assertNotContains(response, "Slaapkamerlamp")
        self.assertContains(response, 'aria-label="Hue kamers"')

    def test_hue_scenes_are_grouped_and_filterable_by_their_room(self):
        for name, room in (("Lezen", "Woonkamer"), ("Ontspannen", "Woonkamer"), ("Slapen", "Slaapkamer")):
            HomeEntity.objects.create(
                household=self.household,
                source=HomeEntity.Source.HUE,
                entity_id=f"hue.scene.{name.lower()}",
                domain="scene",
                name=name,
                attributes={"hue_group_name": room},
            )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "hue", "domain": "scene", "location": "Woonkamer"})

        self.assertContains(response, "Woonkamer")
        self.assertContains(response, "Lezen")
        self.assertContains(response, "Ontspannen")
        self.assertNotContains(response, "Slapen")

    def test_unavailable_hue_entity_is_read_only(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.bedroom",
            domain="light",
            name="Hue slaapkamer",
            is_supported=True,
            is_available=False,
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "hue"})

        self.assertContains(response, "Niet bereikbaar")
        self.assertNotContains(response, 'aria-label="Hue slaapkamer inschakelen"')

    def test_hue_connectivity_issue_has_a_clear_localized_warning(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.hal",
            domain="light",
            name="Lange lampnaam voor de hal",
            attributes={"hue_connectivity": "connectivity_issue"},
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "hue"})

        self.assertContains(response, "Niet verbonden")
        self.assertNotContains(response, "connectivity_issue")
        self.assertContains(response, "hue-device-health is-error")

    def test_hue_sensors_are_grouped_per_device(self):
        sensor_attributes = {"hue_device_id": "device-gang", "hue_device_name": "Gang", "hue_locations": ["Gang"]}
        for sensor_id, kind, state in (
            ("motion", "Beweging", "Beweging"),
            ("light", "Lichtniveau", "Lichtniveau 12000"),
            ("temperature", "Temperatuur", "21,5 °C"),
        ):
            HomeEntity.objects.create(
                household=self.household,
                source=HomeEntity.Source.HUE,
                entity_id=f"hue.gang.{sensor_id}",
                domain="sensor",
                name=f"Gang · {kind}",
                state=state,
                attributes={**sensor_attributes, "hue_sensor_kind": kind, "sensor_active": sensor_id == "motion"},
                is_supported=False,
            )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"domain": "sensor"})

        self.assertContains(response, "Gang")
        self.assertContains(response, "Beweging")
        self.assertContains(response, "Lichtniveau")
        self.assertContains(response, "Temperatuur")
        self.assertNotContains(response, "Gang · Beweging")

    def test_home_entity_search_filters_hue_entities_immediately(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.scene.movie",
            domain="scene",
            name="Filmavond",
        )
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.scene.dinner",
            domain="scene",
            name="Eten",
        )
        self.client.force_login(self.parent)

        response = self.client.get(reverse("home:index"), {"source": "hue", "domain": "scene", "q": "film"})

        self.assertContains(response, "Filmavond")
        self.assertNotContains(response, ">Eten<", html=False)
        self.assertContains(response, 'data-live-search')

    def test_home_default_excludes_scenes_but_the_all_filter_keeps_them_available(self):
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.scene.movie",
            domain="scene",
            name="Filmavond",
        )
        HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.HUE,
            entity_id="hue.light.living",
            domain="light",
            name="Woonkamerlamp",
        )
        self.client.force_login(self.parent)

        default_response = self.client.get(reverse("home:index"))
        all_response = self.client.get(reverse("home:index"), {"domain": "alles"})

        self.assertContains(default_response, "Woonkamerlamp")
        self.assertNotContains(default_response, "Filmavond")
        self.assertContains(all_response, "Filmavond")

    @patch("home.views.sync_entities", return_value=2)
    def test_sync_returns_to_current_safe_filtered_home_page(self, sync_entities):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("home:sync_home_assistant"),
            HTTP_REFERER="http://testserver/huis/?source=hue&domain=scene",
        )

        self.assertRedirects(response, "/huis/?source=hue&domain=scene", fetch_redirect_response=False)
        sync_entities.assert_called_once_with(self.household)

    def test_household_document_is_downloadable_only_inside_household(self):
        self.client.force_login(self.parent)
        uploaded = SimpleUploadedFile("polis.pdf", b"document", content_type="application/pdf")
        self.client.post(reverse("home:add_document"), {"title": "Polis", "category": "Verzekering", "file": uploaded})
        from home.models import HouseholdDocument
        document = HouseholdDocument.objects.get(household=self.household)
        self.assertEqual(self.client.get(reverse("home:download_document", args=[document.id])).status_code, 200)
        self.client.force_login(self.child)
        self.assertEqual(self.client.get(reverse("home:download_document", args=[document.id])).status_code, 200)


class HomeRealtimeTests(TransactionTestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="realtime@example.com", email="realtime@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Realtime gezin")
        Membership.objects.create(household=self.household, user=self.parent, role=Membership.Role.PARENT)

    def test_household_member_receives_a_live_entity_update(self):
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.SONOS,
            entity_id="sonos.group-1",
            domain="media_player",
            name="Woonkamer",
            state="on",
            attributes={"sonos_volume": 18, "sonos_muted": False, "sonos_playback_state": "PLAYBACK_STATE_PLAYING"},
        )

        async def scenario():
            communicator = WebsocketCommunicator(HomeLiveConsumer.as_asgi(), "/ws/huis/")
            communicator.scope["user"] = self.parent
            communicator.scope["url_route"] = {"kwargs": {"household_id": self.household.id}}
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await get_channel_layer().group_send(
                f"household-home-{self.household.id}",
                {"type": "home.entity_update", "payload": home_entity_payload(entity)},
            )
            payload = await communicator.receive_json_from()
            self.assertEqual(payload["type"], "home.entity.updated")
            self.assertEqual(payload["entity"]["id"], entity.id)
            self.assertEqual(payload["entity"]["attributes"]["sonos_volume"], 18)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_cast_playback_details_are_included_in_live_updates(self):
        entity = HomeEntity.objects.create(
            household=self.household,
            source=HomeEntity.Source.GOOGLE_CAST,
            entity_id="probe.cast.keuken",
            domain="media_player",
            name="Keuken",
            state="on",
            attributes={
                "cast_player_state": "PLAYING",
                "cast_volume": 35,
                "cast_title": "Testnummer",
                "cast_artist": "Testartiest",
                "cast_position": 12,
                "cast_duration": 180,
            },
        )

        payload = home_entity_payload(entity)

        self.assertEqual(payload["entity"]["attributes"]["cast_player_state"], "PLAYING")
        self.assertEqual(payload["entity"]["attributes"]["cast_title"], "Testnummer")
        self.assertEqual(payload["entity"]["attributes"]["cast_position"], 12)
        self.assertEqual(payload["entity"]["attributes"]["cast_duration"], 180)
