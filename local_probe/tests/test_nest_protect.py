import unittest

from family_app_probe.nest_protect import NestProtectAdapter, _battery_percent


class NestProtectAdapterTests(unittest.TestCase):
    def test_protect_bucket_becomes_read_only_safety_entity(self):
        entities = NestProtectAdapter.entities_from_buckets([
            {
                "object_key": "where.structure-1",
                "value": {"wheres": [{"where_id": "where-1", "name": "Hal"}]},
            },
            {
                "object_key": "topaz.device-1",
                "value": {
                    "serial_number": "06A123",
                    "where_id": "where-1",
                    "model_name": "Nest Protect",
                    "smoke_status": 0,
                    "co_status": 1,
                    "heat_status": 0,
                    "battery_level": 5000,
                    "line_power_present": True,
                    "wired_or_battery": "wired",
                    "removed_from_base": False,
                },
            },
        ])

        self.assertEqual(len(entities), 1)
        entity = entities[0]
        self.assertEqual(entity["source"], "nest_protect")
        self.assertEqual(entity["domain"], "safety")
        self.assertEqual(entity["state"], "co")
        self.assertFalse(entity["is_supported"])
        self.assertEqual(entity["attributes"]["nest_location"], "Hal")
        self.assertTrue(entity["attributes"]["nest_line_power"])

    def test_unconfigured_adapter_does_not_make_network_calls(self):
        adapter = NestProtectAdapter({})

        self.assertEqual(adapter.inventory(), [])
        self.assertEqual(adapter.event_status()["mode"], "disabled")

    def test_battery_percentage_is_bounded(self):
        self.assertIsNone(_battery_percent(2800))
        self.assertGreaterEqual(_battery_percent(4950), 0)
        self.assertLessEqual(_battery_percent(4950), 100)
