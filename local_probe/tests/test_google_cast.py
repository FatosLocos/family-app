import unittest
from unittest.mock import Mock, patch

from family_app_probe.google_cast import GoogleCastAdapter


class GoogleCastAdapterTests(unittest.TestCase):
    def _cast(self):
        cast = Mock()
        cast.cast_info.uuid = "device-1"
        cast.cast_info.host = "192.168.1.20"
        cast.cast_info.friendly_name = "Keuken"
        cast.cast_info.model_name = "Nest Audio"
        cast.cast_info.cast_type = "audio"
        cast.status.volume_level = 0.35
        cast.status.volume_muted = False
        cast.media_controller.status.player_state = "PLAYING"
        cast.media_controller.status.title = "Testnummer"
        cast.media_controller.status.artist = "Testartiest"
        cast.media_controller.status.duration = 180
        cast.media_controller.status.current_time = 12
        return cast

    def test_inventory_exposes_playback_and_volume(self):
        adapter = GoogleCastAdapter()
        with patch.object(adapter, "_discover", return_value={"device-1": self._cast()}):
            entity = adapter.inventory()[0]
        self.assertEqual(entity["source"], "google_cast")
        self.assertEqual(entity["name"], "Keuken")
        self.assertEqual(entity["attributes"]["cast_volume"], 35)
        self.assertEqual(entity["attributes"]["cast_player_state"], "PLAYING")
        self.assertEqual(entity["attributes"]["cast_position"], 12)
        self.assertEqual(entity["attributes"]["cast_duration"], 180)

    def test_control_uses_only_supported_media_and_volume_actions(self):
        adapter = GoogleCastAdapter()
        cast = self._cast()
        adapter._casts["device-1"] = cast
        adapter.control("device-1", "set_volume", "42")
        cast.set_volume.assert_called_once_with(0.42)
        adapter.control("device-1", "play_pause")
        cast.media_controller.pause.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "niet beschikbaar"):
            adapter.control("device-1", "play_uri", "https://example.test")
