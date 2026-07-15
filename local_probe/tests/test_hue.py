import unittest
from unittest.mock import Mock, patch

from family_app_probe.hue import HueAdapter


class HueAdapterTests(unittest.TestCase):
    def test_inventory_exposes_light_effects_colors_and_group_members(self):
        resources = [
            {
                "id": "room-1",
                "type": "room",
                "metadata": {"name": "Woonkamer"},
                "children": [{"rtype": "device", "rid": "device-1"}, {"rtype": "device", "rid": "device-2"}],
                "services": [{"rtype": "grouped_light", "rid": "group-1"}],
            },
            {
                "id": "device-1",
                "type": "device",
                "metadata": {"name": "Muur lampen"},
                "services": [{"rtype": "light", "rid": "light-1"}],
            },
            {
                "id": "light-1",
                "type": "light",
                "metadata": {"name": "Muur lamp 1"},
                "on": {"on": True},
                "dimming": {"brightness": 42},
                "color": {"xy": {"x": 0.54, "y": 0.32}},
                "color_temperature": {"mirek": 320, "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500}},
                "effects_v2": {"status": "prism", "effect_values": ["no_effect", "prism"]},
            },
            {
                "id": "device-2",
                "type": "device",
                "metadata": {"name": "Muur lamp 2"},
                "services": [{"rtype": "light", "rid": "light-2"}],
            },
            {
                "id": "light-2",
                "type": "light",
                "metadata": {"name": "Muur lamp 2"},
                "on": {"on": True},
                "dimming": {"brightness": 42},
                "color": {"xy": {"x": 0.15, "y": 0.06}},
            },
            {
                "id": "group-1",
                "type": "grouped_light",
                "owner": {"rid": "room-1", "rtype": "room"},
                "on": {"on": True},
                "dimming": {"brightness": 42},
                "color": {"xy": {"x": 0.54, "y": 0.32}},
                "color_temperature": {"mirek": 320, "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500}},
                "effects_v2": {"status": "prism", "effect_values": ["no_effect", "prism"]},
            },
        ]
        response = Mock()
        response.json.return_value = {"data": resources}
        adapter = HueAdapter({"bridge": "https://bridge.local", "app_key": "key"})

        with patch("family_app_probe.hue.requests.get", return_value=response):
            entities = adapter.inventory()

        light = next(entity for entity in entities if entity["domain"] == "light")
        group = next(entity for entity in entities if entity["domain"] == "group")
        self.assertTrue(light["attributes"]["supports_color"])
        self.assertTrue(light["attributes"]["supports_effects"])
        self.assertEqual(light["attributes"]["effect_current"], "prism")
        self.assertTrue(light["attributes"]["color_hex"].startswith("#"))
        self.assertEqual(group["attributes"]["member_light_ids"], ["light-1", "light-2"])
        self.assertEqual(group["attributes"]["member_names"], ["Muur lampen", "Muur lamp 2"])
        self.assertTrue(group["attributes"]["color_mixed"])
        self.assertEqual(len(group["attributes"]["member_color_hexes"]), 2)

    def test_effect_control_uses_the_v2_effect_endpoint(self):
        response = Mock()
        adapter = HueAdapter({"bridge": "https://bridge.local", "app_key": "key"})

        with patch("family_app_probe.hue.requests.put", return_value=response) as request:
            adapter.control("light:light-1", "effect", "prism")

        self.assertEqual(request.call_args.kwargs["json"], {"effects_v2": {"action": "prism"}})
