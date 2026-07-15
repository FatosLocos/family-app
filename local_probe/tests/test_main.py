import argparse
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from family_app_probe.main import _safe_error, _sync, philips_tv_link, run


class PhilipsTVLinkTests(unittest.TestCase):
    def test_pairing_persists_credentials_only_in_probe_config(self):
        saved = {}

        class FakeSession:
            async def aclose(self):
                return None

        class FakeTV:
            def __init__(self, host, api_version):
                self.host = host
                self.api_version = api_version
                self.session = FakeSession()

            async def getSystem(self):
                return {"name": "Philips TV"}

            async def pairRequest(self, *args):
                return {"device": {"id": "probe-device"}}

            async def pairGrant(self, state, pin):
                self.assertEqual(state["device"]["id"], "probe-device")
                self.assertEqual(pin, "1234")
                return "probe-device", "probe-password"

            def assertEqual(self, actual, expected):
                if actual != expected:
                    raise AssertionError(f"{actual!r} != {expected!r}")

        def save_config(config):
            saved.update(config)

        with (
            patch.dict(sys.modules, {"haphilipsjs": SimpleNamespace(PhilipsTV=FakeTV)}),
            patch("family_app_probe.main.load_config", return_value={}),
            patch("family_app_probe.main.save_config", side_effect=save_config),
            patch("builtins.input", return_value="1234"),
        ):
            philips_tv_link(argparse.Namespace(host="192.168.1.50", api_version=6))

        self.assertEqual(
            saved["philips_tv"]["devices"]["192.168.1.50"],
            {"username": "probe-device", "password": "probe-password", "api_version": 6},
        )


class ProbeSyncTests(unittest.TestCase):
    def test_sync_keeps_healthy_adapter_when_another_adapter_fails(self):
        class FakeWebSocket:
            def __init__(self):
                self.payloads = []

            def send(self, payload):
                self.payloads.append(json.loads(payload))

        class HealthyAdapter:
            name = "hue"

            def inventory(self):
                return [{"name": "Keuken"}]

        class BrokenAdapter:
            name = "google_cast"

            def inventory(self):
                raise RuntimeError("token=super-secret bridge niet bereikbaar")

        ws = FakeWebSocket()
        status = _sync(ws, [HealthyAdapter(), BrokenAdapter()])

        self.assertEqual(status["hue"], {"status": "active", "entities": 1})
        self.assertEqual(status["google_cast"]["status"], "error")
        self.assertNotIn("super-secret", status["google_cast"]["error"])
        self.assertFalse(ws.payloads[0]["replace_adapters"])
        self.assertEqual(ws.payloads[1]["entities"], [{"name": "Keuken"}])

    def test_safe_error_redacts_common_credential_values(self):
        detail = _safe_error(RuntimeError("Authorization: Bearer api-secret cookie=session-value client_secret=oauth-secret password=hunter2"))

        self.assertNotIn("api-secret", detail)
        self.assertNotIn("session-value", detail)
        self.assertNotIn("oauth-secret", detail)
        self.assertNotIn("hunter2", detail)

    def test_one_off_run_skips_slow_network_discovery(self):
        websocket = SimpleNamespace(settimeout=lambda timeout: None)
        args = SimpleNamespace(once=True, inventory_interval=-1, discovery_interval=-1, sonos_refresh_interval=2)

        with (
            patch("family_app_probe.main.load_config", return_value={"probe_id": "probe", "token": "token", "websocket_url": "ws://example.test"}),
            patch("family_app_probe.main._adapters", return_value=[]),
            patch("family_app_probe.main.websocket.create_connection", return_value=websocket),
            patch("family_app_probe.main._sync") as sync,
            patch("family_app_probe.main.discover_network") as discover,
        ):
            run(args)

        sync.assert_called_once()
        discover.assert_not_called()

    def test_hue_link_command_persists_the_probe_configuration(self):
        class FakeWebSocket:
            def __init__(self):
                self.received = False
                self.payloads = []

            def settimeout(self, timeout):
                return None

            def recv(self):
                if self.received:
                    raise KeyboardInterrupt
                self.received = True
                return json.dumps({"type": "command", "command_id": "command-1", "action": "link_hue_bridge", "entity": {}, "value": {"bridge": "http://192.168.1.30"}})

            def send(self, payload):
                self.payloads.append(json.loads(payload))

        class Hue:
            name = "hue"

            def link_bridge(self, bridge):
                self.bridge = bridge

        websocket = FakeWebSocket()
        hue = Hue()
        config = {"probe_id": "probe", "token": "token", "websocket_url": "ws://example.test"}
        args = SimpleNamespace(once=False, inventory_interval=999, discovery_interval=999, sonos_refresh_interval=999)
        with (
            patch("family_app_probe.main.load_config", return_value=config),
            patch("family_app_probe.main._adapters", return_value=[hue]),
            patch("family_app_probe.main.websocket.create_connection", return_value=websocket),
            patch("family_app_probe.main.save_config") as save,
        ):
            with self.assertRaises(KeyboardInterrupt):
                run(args)

        self.assertEqual(hue.bridge, "http://192.168.1.30")
        save.assert_called_once_with(config)
        result = next(payload for payload in websocket.payloads if payload.get("type") == "command_result")
        self.assertTrue(result["succeeded"])
