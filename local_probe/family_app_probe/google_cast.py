from __future__ import annotations

import time


class GoogleCastAdapter:
    """Local, minimal controls for devices advertised through Google Cast."""

    name = "google_cast"

    def __init__(self):
        self._casts = {}

    def _discover(self):
        try:
            import pychromecast
        except ImportError as error:
            raise RuntimeError("PyChromecast ontbreekt; installeer de probe-afhankelijkheden opnieuw.") from error
        casts, browser = pychromecast.get_chromecasts(tries=1, timeout=6)
        try:
            for cast in casts:
                try:
                    cast.wait(timeout=8)
                    key = str(cast.cast_info.uuid or cast.cast_info.host)
                    self._casts[key] = cast
                except Exception:
                    continue
        finally:
            pychromecast.discovery.stop_discovery(browser)
        return self._casts

    def inventory(self):
        casts = self._discover()
        entities = []
        for key, cast in casts.items():
            info = cast.cast_info
            status = cast.status
            media = cast.media_controller.status
            volume = getattr(status, "volume_level", None)
            player_state = str(getattr(media, "player_state", "") or "")
            entities.append(
                {
                    "source": self.name,
                    "local_key": key,
                    "external_id": key,
                    "domain": "media_player",
                    "name": str(info.friendly_name or info.model_name or "Google Cast"),
                    "state": "on" if player_state == "PLAYING" else "off",
                    "is_available": True,
                    "is_supported": True,
                    "attributes": {
                        "cast_uuid": key,
                        "cast_model": str(info.model_name or "Google Cast"),
                        "cast_type": str(info.cast_type or ""),
                        "cast_host": str(info.host or ""),
                        "cast_volume": round(float(volume or 0) * 100),
                        "cast_muted": bool(getattr(status, "volume_muted", False)),
                        "cast_player_state": player_state,
                        "cast_title": str(getattr(media, "title", "") or ""),
                        "cast_artist": str(getattr(media, "artist", "") or ""),
                        "cast_duration": float(getattr(media, "duration", 0) or 0),
                        "cast_position": float(getattr(media, "current_time", 0) or 0),
                    },
                }
            )
        return entities

    def control(self, local_key: str, action: str, value=None):
        cast = self._casts.get(local_key)
        if not cast:
            self._discover()
            cast = self._casts.get(local_key)
        if not cast:
            raise RuntimeError("Google Cast-apparaat is niet meer bereikbaar.")
        media = cast.media_controller
        if action == "play_pause":
            if str(getattr(media.status, "player_state", "")) == "PLAYING":
                media.pause()
            else:
                media.play()
        elif action == "set_volume":
            cast.set_volume(max(0, min(100, int(float(value)))) / 100)
        elif action == "mute":
            cast.set_volume_muted(True)
        elif action == "unmute":
            cast.set_volume_muted(False)
        elif action == "stop":
            media.stop()
        else:
            raise RuntimeError("Deze Google Cast-bediening is niet beschikbaar.")
        time.sleep(0.25)
