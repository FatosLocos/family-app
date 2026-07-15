import unittest
from unittest.mock import AsyncMock, patch

from family_app_probe.discovery import MDNS_SERVICE_TYPES, _suggested_integration, discover_bluetooth


class DiscoveryTests(unittest.TestCase):
    def test_safe_service_types_cover_local_media_and_smart_home_protocols(self):
        self.assertIn("_googlecast._tcp.local.", MDNS_SERVICE_TYPES)
        self.assertIn("_airplay._tcp.local.", MDNS_SERVICE_TYPES)
        self.assertIn("_spotify-connect._tcp.local.", MDNS_SERVICE_TYPES)
        self.assertIn("_matter._tcp.local.", MDNS_SERVICE_TYPES)
        self.assertIn("_androidtvremote2._tcp.local.", MDNS_SERVICE_TYPES)

    def test_discovery_suggestions_are_protocol_specific(self):
        self.assertEqual(_suggested_integration("_googlecast._tcp.local."), "Google Cast")
        self.assertEqual(_suggested_integration("_airplay._tcp.local."), "AirPlay")
        self.assertEqual(_suggested_integration("_spotify-connect._tcp.local."), "Spotify Connect")
        self.assertEqual(_suggested_integration("_hap._tcp.local."), "Apple HomeKit")
        self.assertEqual(_suggested_integration("_matter._tcp.local."), "Matter")
        self.assertEqual(_suggested_integration("Signify Philips hue bridge 2015"), "Philips Hue")
        self.assertEqual(_suggested_integration("2021/22 Philips UHD Android TV"), "Google Cast / Android TV")

    def test_bluetooth_discovery_keeps_advertised_metadata_without_pairing(self):
        advertised = [{"key": "ble:device-1", "name": "Temperatuursensor", "kind": "Bluetooth LE", "address": None, "method": "bluetooth_le", "details": {"bluetooth_address": "device-1", "rssi": -52, "service_uuids": ["1234"], "manufacturer_ids": ["76"], "suggested_integration": "Bluetooth LE"}}]
        with patch("family_app_probe.discovery._discover_bluetooth_async", new=AsyncMock(return_value=advertised)):
            devices = discover_bluetooth()

        self.assertEqual(devices[0]["method"], "bluetooth_le")
        self.assertEqual(devices[0]["details"]["suggested_integration"], "Bluetooth LE")

    def test_bluetooth_adapter_error_is_optional(self):
        error_type = type("BleakError", (Exception,), {"__module__": "bleak.exc"})
        with patch("family_app_probe.discovery._discover_bluetooth_async", new=AsyncMock(side_effect=error_type("Bluetooth uit"))):
            self.assertEqual(discover_bluetooth(), [])
