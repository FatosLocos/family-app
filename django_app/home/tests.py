from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from home.models import HomeActionAudit, HomeAssistantConfig, HomeEntity
from home.services import HomeAssistantError, control_entity, sync_entities
from households.models import Household, Membership
from identity.models import User
from integrations.crypto import encrypt


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
        self.assertEqual(HomeActionAudit.objects.get(entity=climate).detail, "Temperatuur ingesteld op 21.5 °C.")

    def test_invalid_home_action_is_rejected_and_audited(self):
        entity = HomeEntity.objects.create(household=self.household, entity_id="scene.avondsfeer", domain="scene", name="Avondsfeer", is_supported=True)
        with self.assertRaises(HomeAssistantError):
            control_entity(self.household, entity, "off")
        audit = HomeActionAudit.objects.get(entity=entity)
        self.assertFalse(audit.succeeded)
        self.assertEqual(audit.action, "off")

    def test_child_can_view_but_cannot_save_or_control(self):
        entity = HomeEntity.objects.create(household=self.household, entity_id="light.kamer", domain="light", name="Kamer", is_supported=True)
        self.client.force_login(self.child)
        self.assertEqual(self.client.get(reverse("home:index")).status_code, 200)
        self.assertEqual(self.client.post(reverse("home:save_home_assistant"), {"base_url": "http://ha.local", "token": "new"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("home:control", args=[entity.id, "on"])).status_code, 403)

    def test_parent_can_manage_household_home_records(self):
        self.client.force_login(self.parent)
        self.client.post(reverse("home:add_maintenance"), {"title": "Cv-ketel", "category": "Installatie", "cadence_days": 365})
        self.client.post(reverse("home:add_emergency_contact"), {"label": "Huisarts", "value": "010-1234567", "kind": "contact"})
        self.client.post(reverse("home:add_room"), {"name": "Zolder", "icon": "lamp"})
        response = self.client.get(reverse("home:index"), {"tab": "inrichting"})
        self.assertContains(response, "Zolder")
        self.assertContains(self.client.get(reverse("home:index"), {"tab": "onderhoud"}), "Cv-ketel")

    def test_home_assistant_interface_names_the_rest_api_integration(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("home:index"))
        self.assertContains(response, "Home Assistant REST API")

    def test_household_document_is_downloadable_only_inside_household(self):
        self.client.force_login(self.parent)
        uploaded = SimpleUploadedFile("polis.pdf", b"document", content_type="application/pdf")
        self.client.post(reverse("home:add_document"), {"title": "Polis", "category": "Verzekering", "file": uploaded})
        from home.models import HouseholdDocument
        document = HouseholdDocument.objects.get(household=self.household)
        self.assertEqual(self.client.get(reverse("home:download_document", args=[document.id])).status_code, 200)
        self.client.force_login(self.child)
        self.assertEqual(self.client.get(reverse("home:download_document", args=[document.id])).status_code, 200)
