from __future__ import annotations

import time

import requests
from requests.auth import HTTPDigestAuth

from family_app_probe.discovery import discover_ssdp


class PhilipsTVAdapter:
    """Control Philips Android TVs through their locally advertised JointSpace API."""

    name = "philips_tv"
    _CACHE_SECONDS = 60
    _KEYS = {
        "Standby",
        "Home",
        "Back",
        "CursorUp",
        "CursorDown",
        "CursorLeft",
        "CursorRight",
        "Confirm",
        "VolumeUp",
        "VolumeDown",
        "Mute",
        "PlayPause",
        "Pause",
        "Stop",
        "Rewind",
        "FastForward",
        "WatchTV",
        "Options",
        "Info",
        "AmbilightOnOff",
    }

    def __init__(self, config: dict | None = None):
        self._config = config if isinstance(config, dict) else {}
        self._devices = {}
        self._checked_at = 0.0

    def _auth(self, host: str):
        devices = self._config.get("devices") if isinstance(self._config.get("devices"), dict) else {}
        credentials = devices.get(host) if isinstance(devices.get(host), dict) else {}
        username = str(credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "").strip()
        return HTTPDigestAuth(username, password) if username and password else None

    def _request_kwargs(self, host: str, *, timeout: int):
        kwargs = {"timeout": timeout, "verify": False}
        if auth := self._auth(host):
            kwargs["auth"] = auth
        return kwargs

    @staticmethod
    def _is_philips_tv(device: dict) -> bool:
        details = device.get("details") if isinstance(device.get("details"), dict) else {}
        identity = " ".join(
            str(value or "")
            for value in (
                device.get("name"),
                device.get("kind"),
                details.get("manufacturer"),
                details.get("model_description"),
                details.get("device_type"),
            )
        ).lower()
        return "philips" in identity and any(marker in identity for marker in ("tv", "android", "oled", "uhd"))

    @staticmethod
    def _base_urls(host: str, version: int):
        return (f"http://{host}:1925/{version}", f"https://{host}:1926/{version}")

    def _read(self, host: str, path: str, device: dict, *, required: bool = False):
        options = []
        if device.get("base_url"):
            options.append((device.get("version", 6), device["base_url"]))
        for version in (device.get("version", 6), 6, 5, 4):
            for base_url in self._base_urls(host, version):
                if base_url not in {candidate[1] for candidate in options}:
                    options.append((version, base_url))
        last_error = None
        for version, base_url in options:
            try:
                response = requests.get(f"{base_url}/{path.lstrip('/')}", **self._request_kwargs(host, timeout=3))
                if response.status_code == 401:
                    device["requires_pairing"] = True
                    return None
                if response.ok:
                    device["base_url"] = base_url
                    device["version"] = version
                    return response.json()
                last_error = RuntimeError(f"Philips TV gaf HTTP {response.status_code} terug.")
            except (requests.RequestException, ValueError) as error:
                last_error = error
        if required:
            raise RuntimeError("Philips TV is lokaal niet bereikbaar.") from last_error
        return None

    def _discover(self):
        if self._devices and time.monotonic() - self._checked_at < self._CACHE_SECONDS:
            return self._devices
        devices = {}
        for candidate in discover_ssdp():
            if not self._is_philips_tv(candidate):
                continue
            host = str(candidate.get("address") or "").strip()
            if not host:
                continue
            device = {"host": host, "name": str(candidate.get("name") or "Philips TV"), "details": candidate.get("details") or {}, "version": 6}
            configured_devices = self._config.get("devices") if isinstance(self._config.get("devices"), dict) else {}
            configured_device = configured_devices.get(host) if isinstance(configured_devices.get(host), dict) else {}
            if configured_device.get("api_version"):
                device["version"] = int(configured_device["api_version"])
            system = self._read(host, "system", device)
            if not system and not device.get("requires_pairing"):
                continue
            device["system"] = system or {}
            devices[host] = device
        self._devices = devices
        self._checked_at = time.monotonic()
        return devices

    @staticmethod
    def _volume(attributes: dict):
        value = attributes.get("current")
        maximum = attributes.get("max")
        try:
            return round(float(value) / float(maximum) * 100) if float(maximum) else None
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def inventory(self):
        entities = []
        for host, device in self._discover().items():
            system = device.get("system") or {}
            volume = self._read(host, "audio/volume", device) or {}
            activity = self._read(host, "activities/current", device) or {}
            power = self._read(host, "powerstate", device) or {}
            power_state = str(power.get("powerstate") or "On")
            model = str(system.get("model") or system.get("name") or device["details"].get("model_description") or "Philips Android TV")
            entities.append(
                {
                    "source": self.name,
                    "local_key": host,
                    "external_id": host,
                    "domain": "media_player",
                    "name": str(system.get("name") or device["name"]),
                    "state": "off" if power_state.lower() in {"off", "standby"} else "on",
                    "is_available": True,
                    "is_supported": not device.get("requires_pairing", False),
                    "attributes": {
                        "philips_model": model,
                        "philips_api_version": device.get("version", 6),
                        "philips_volume": self._volume(volume),
                        "philips_muted": bool(volume.get("muted", False)),
                        "philips_activity": str((activity.get("component") or {}).get("packageName") or ""),
                        "philips_requires_pairing": bool(device.get("requires_pairing", False)),
                    },
                }
            )
        return entities

    def control(self, local_key: str, action: str, value=None):
        device = self._devices.get(local_key)
        if not device:
            self._discover()
            device = self._devices.get(local_key)
        if not device:
            raise RuntimeError("Philips TV is lokaal niet bereikbaar. Zet de tv aan en vernieuw de lokale probe.")
        if device.get("requires_pairing"):
            raise RuntimeError("Deze Philips TV vereist eerst lokale pairing in JointSpace.")
        if action != "remote_key" or str(value or "") not in self._KEYS:
            raise RuntimeError("Deze Philips TV-bediening is niet beschikbaar.")
        response = requests.post(
            f"{device['base_url']}/input/key",
            json={"key": str(value)},
            **self._request_kwargs(str(device.get("host") or local_key), timeout=4),
        )
        if response.status_code == 401:
            device["requires_pairing"] = True
            raise RuntimeError("Deze Philips TV vereist eerst lokale pairing in JointSpace.")
        response.raise_for_status()
