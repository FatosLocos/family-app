import unittest
from unittest.mock import Mock, patch

from family_app_probe.philips_tv import PhilipsTVAdapter


class PhilipsTVAdapterTests(unittest.TestCase):
    def _response(self, payload, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.ok = status_code < 400
        response.json.return_value = payload
        return response

    def test_inventory_exposes_a_discovered_jointspace_tv(self):
        adapter = PhilipsTVAdapter()
        device = {
            "key": "uuid:philips-tv",
            "name": "Woonkamer TV",
            "kind": "Philips UHD Android TV",
            "address": "192.168.1.50",
            "details": {"manufacturer": "Philips", "model_description": "OLED"},
        }
        responses = [
            self._response({"name": "Philips TV", "model": "55OLED"}),
            self._response({"current": 10, "max": 20, "muted": False}),
            self._response({"component": {"packageName": "org.droidtv.tv"}}),
            self._response({"powerstate": "On"}),
        ]
        with patch("family_app_probe.philips_tv.discover_ssdp", return_value=[device]), patch("family_app_probe.philips_tv.requests.get", side_effect=responses):
            entity = adapter.inventory()[0]
        self.assertEqual(entity["source"], "philips_tv")
        self.assertEqual(entity["name"], "Philips TV")
        self.assertEqual(entity["attributes"]["philips_volume"], 50)
        self.assertTrue(entity["is_supported"])

    def test_control_posts_only_whitelisted_remote_keys(self):
        adapter = PhilipsTVAdapter()
        adapter._devices["192.168.1.50"] = {"base_url": "http://192.168.1.50:1925/6", "requires_pairing": False}
        response = self._response({})
        with patch("family_app_probe.philips_tv.requests.post", return_value=response) as post:
            adapter.control("192.168.1.50", "remote_key", "Home")
        post.assert_called_once_with("http://192.168.1.50:1925/6/input/key", json={"key": "Home"}, timeout=4, verify=False)
        with self.assertRaisesRegex(RuntimeError, "niet beschikbaar"):
            adapter.control("192.168.1.50", "remote_key", "not-a-key")

    def test_inventory_and_control_use_probe_local_digest_credentials(self):
        adapter = PhilipsTVAdapter({"devices": {"192.168.1.50": {"username": "probe-user", "password": "probe-secret", "api_version": 6}}})
        device = {
            "key": "uuid:philips-tv",
            "name": "Woonkamer TV",
            "kind": "Philips UHD Android TV",
            "address": "192.168.1.50",
            "details": {"manufacturer": "Philips", "model_description": "OLED"},
        }
        responses = [
            self._response({"name": "Philips TV", "model": "55OLED"}),
            self._response({"current": 10, "max": 20, "muted": False}),
            self._response({"component": {"packageName": "org.droidtv.tv"}}),
            self._response({"powerstate": "On"}),
        ]
        with patch("family_app_probe.philips_tv.discover_ssdp", return_value=[device]), patch("family_app_probe.philips_tv.requests.get", side_effect=responses) as get:
            adapter.inventory()
        self.assertEqual(get.call_args.kwargs["auth"].username, "probe-user")

        adapter._devices["192.168.1.50"] = {"host": "192.168.1.50", "base_url": "http://192.168.1.50:1925/6", "requires_pairing": False}
        with patch("family_app_probe.philips_tv.requests.post", return_value=self._response({})) as post:
            adapter.control("192.168.1.50", "remote_key", "Home")
        self.assertEqual(post.call_args.kwargs["auth"].username, "probe-user")
