from __future__ import annotations

import re
import socket
import threading
import time
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import requests

from family_app_probe.discovery import discover_ssdp


SOAP_NAMESPACES = {"s": "http://schemas.xmlsoap.org/soap/envelope/"}


class SonosAdapter:
    """Read and control Sonos at the group coordinator, not at satellites."""

    name = "sonos"

    def __init__(self):
        self.players = {}
        self.member_players = {}
        self._devices = []
        self._devices_checked_at = 0.0
        self._event_server = None
        self._event_thread = None
        self._event_callback = None
        self._subscriptions = {}
        self._extended_status_cache = {}
        self._member_status_cache = {}
        self.group_members = {}
        self.topology_members = {}
        self.room_detection_play_ids = {}
        self.last_event_at = None
        self.last_event_error = ""

    def _sonos_devices(self):
        # SSDP discovery is relatively slow and does not need to run for every
        # live playback tick. Speaker topology is still refreshed frequently.
        if time.monotonic() - self._devices_checked_at > 120 or not self._devices:
            self._devices = [device for device in discover_ssdp() if "sonos" in str(device.get("kind", "")).lower()]
            self._devices_checked_at = time.monotonic()
        return self._devices

    @staticmethod
    def _speaker_label(value):
        """Remove discovery-only host and UUID details from Sonos friendly names."""
        candidate = str(value or "").strip()
        match = re.fullmatch(
            r"(?:\d{1,3}\.){3}\d{1,3}\s*-\s*(.+?)\s*-\s*(?:RINCON|uuid:)[A-Za-z0-9_:-]+",
            candidate,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else candidate

    def _soap(self, host, service, action, values=None):
        values = values or {}
        body = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in values.items())
        envelope = f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:{action} xmlns:u="urn:schemas-upnp-org:service:{service}:1">{body}</u:{action}></s:Body></s:Envelope>'
        root_services = {"AlarmClock", "AudioIn", "DeviceProperties", "GroupManagement", "HTControl", "ZoneGroupTopology"}
        path = f"/{service}/Control" if service in root_services else f"/MediaRenderer/{service}/Control"
        response = requests.post(
            f"http://{host}:1400{path}",
            data=envelope.encode(),
            headers={"SOAPACTION": f'"urn:schemas-upnp-org:service:{service}:1#{action}"', "Content-Type": 'text/xml; charset="utf-8"'},
            timeout=5,
        )
        response.raise_for_status()
        return ElementTree.fromstring(response.content)

    @staticmethod
    def _event_path(service):
        return f"/{service}/Event" if service == "ZoneGroupTopology" else f"/MediaRenderer/{service}/Event"

    @staticmethod
    def _local_address_for(host):
        """Select the LAN address Sonos can reach for the event callback."""
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            client.connect((host, 1400))
            return client.getsockname()[0]
        finally:
            client.close()

    def _start_event_server(self):
        if self._event_server:
            return
        adapter = self

        class SonosEventHandler(BaseHTTPRequestHandler):
            def do_NOTIFY(self):  # noqa: N802 - UPnP method name is uppercase.
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(content_length) if content_length else b""
                adapter._handle_event(self.path, dict(self.headers), payload)
                self.send_response(200)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        self._event_server = ThreadingHTTPServer(("0.0.0.0", 0), SonosEventHandler)
        self._event_thread = threading.Thread(target=self._event_server.serve_forever, name="family-app-sonos-events", daemon=True)
        self._event_thread.start()

    def _handle_event(self, _path, _headers, _payload):
        # A full inventory read keeps one state model for polling and events.
        # Sonos event bodies can differ per product and software version.
        self.last_event_at = time.time()
        if self._event_callback:
            self._event_callback()

    def _subscribe(self, host, service):
        self._start_event_server()
        key = (host, service)
        existing = self._subscriptions.get(key)
        headers = {"TIMEOUT": "Second-1800"}
        if existing and existing["expires_at"] > time.time() + 90:
            return
        if existing:
            headers["SID"] = existing["sid"]
        else:
            local_address = self._local_address_for(host)
            callback = f"http://{local_address}:{self._event_server.server_port}/sonos-events"
            headers.update({"CALLBACK": f"<{callback}>", "NT": "upnp:event"})
        response = requests.request("SUBSCRIBE", f"http://{host}:1400{self._event_path(service)}", headers=headers, timeout=5)
        response.raise_for_status()
        sid = response.headers.get("SID") or (existing or {}).get("sid")
        if not sid:
            raise RuntimeError("Sonos gaf geen event-abonnement terug.")
        timeout_value = response.headers.get("TIMEOUT", "Second-1800").lower().removeprefix("second-")
        try:
            lifetime = max(120, int(timeout_value))
        except ValueError:
            lifetime = 1800
        self._subscriptions[key] = {"sid": sid, "expires_at": time.time() + lifetime}

    def ensure_events(self, on_change):
        """Create or refresh local UPnP subscriptions for all group coordinators."""
        self._event_callback = on_change
        errors = []
        for host in set(self.players.values()):
            for service in ("AVTransport", "RenderingControl", "GroupRenderingControl", "ZoneGroupTopology"):
                try:
                    self._subscribe(host, service)
                except (requests.RequestException, RuntimeError, OSError) as error:
                    errors.append(str(error))
        self.last_event_error = "; ".join(errors)[:180]

    def event_status(self):
        return {
            "event_subscriptions": len(self._subscriptions),
            "last_event_at": self.last_event_at,
            "event_error": self.last_event_error,
        }

    @staticmethod
    def _value(root, suffix, default=""):
        return next((node.text for node in root.iter() if node.tag.endswith(suffix) and node.text is not None), default)

    @staticmethod
    def _didl_metadata(value):
        if not value:
            return {}
        try:
            root = ElementTree.fromstring(value)
        except ElementTree.ParseError:
            return {}
        values = {}
        fields = {
            "title": "title",
            "creator": "artist",
            "album": "album",
            "albumArtURI": "artwork",
        }
        for node in root.iter():
            field = fields.get(node.tag.rsplit("}", 1)[-1])
            if field and node.text:
                values[field] = node.text.strip()
        return values

    @staticmethod
    def _seconds(value):
        try:
            parts = [int(part) for part in str(value).split(":")]
        except ValueError:
            return 0
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return 0

    def _zone_groups(self, host):
        root = self._soap(host, "ZoneGroupTopology", "GetZoneGroupState")
        state = self._value(root, "ZoneGroupState")
        if not state:
            return []
        topology = ElementTree.fromstring(state)
        groups = []
        for group in topology.findall(".//ZoneGroup"):
            coordinator = group.attrib.get("Coordinator", "")
            members = list(group.findall("./ZoneGroupMember"))
            members.extend(group.findall(".//Satellite"))
            members = [member for member in members if member is not None]
            if coordinator and members:
                groups.append({"coordinator": coordinator, "members": members})
        return groups

    def _player_status(self, host):
        # GroupRenderingControl preserves the relative levels of surround and
        # Sub members. It must be sent to the group coordinator.
        try:
            volume_xml = self._soap(host, "GroupRenderingControl", "GetGroupVolume", {"InstanceID": 0})
            mute_xml = self._soap(host, "GroupRenderingControl", "GetGroupMute", {"InstanceID": 0})
        except requests.RequestException:
            volume_xml = self._soap(host, "RenderingControl", "GetVolume", {"InstanceID": 0, "Channel": "Master"})
            mute_xml = self._soap(host, "RenderingControl", "GetMute", {"InstanceID": 0, "Channel": "Master"})
        try:
            transport_xml = self._soap(host, "AVTransport", "GetTransportInfo", {"InstanceID": 0})
            transport = self._value(transport_xml, "CurrentTransportState", "STOPPED")
        except requests.RequestException:
            transport = "STOPPED"
        try:
            position_xml = self._soap(host, "AVTransport", "GetPositionInfo", {"InstanceID": 0})
            media_xml = self._soap(host, "AVTransport", "GetMediaInfo", {"InstanceID": 0})
            actions_xml = self._soap(host, "AVTransport", "GetCurrentTransportActions", {"InstanceID": 0})
            transport_settings_xml = self._soap(host, "AVTransport", "GetTransportSettings", {"InstanceID": 0})
            metadata = self._didl_metadata(self._value(position_xml, "TrackMetaData"))
            source_metadata = self._didl_metadata(self._value(media_xml, "CurrentURIMetaData"))
            actions = {item.strip().lower() for item in self._value(actions_xml, "Actions").split(",") if item.strip()}
            duration = self._value(position_xml, "TrackDuration")
            position = self._value(position_xml, "RelTime")
            play_mode = self._value(transport_settings_xml, "PlayMode", "NORMAL").upper()
            current_uri = self._value(media_xml, "CurrentURI")
        except (requests.RequestException, ElementTree.ParseError):
            metadata, source_metadata, actions, duration, position, play_mode, current_uri = {}, {}, set(), "", "", "NORMAL", ""
        try:
            crossfade_xml = self._soap(host, "AVTransport", "GetCrossfadeMode", {"InstanceID": 0})
            crossfade = self._value(crossfade_xml, "CrossfadeMode", "0") == "1"
            can_crossfade = True
        except (requests.RequestException, ElementTree.ParseError):
            crossfade, can_crossfade = False, False
        extended_status = self._extended_player_status(host)
        return {
            "volume": int(self._value(volume_xml, "CurrentVolume", "0")),
            "muted": self._value(mute_xml, "CurrentMute", "0") == "1",
            "transport": transport,
            "now_playing": metadata,
            "source": source_metadata.get("title", ""),
            "is_tv_input": current_uri.startswith("x-sonos-htastream:"),
            "actions": actions,
            "duration": duration if duration != "NOT_IMPLEMENTED" else "",
            "position": position if position != "NOT_IMPLEMENTED" else "",
            "duration_seconds": self._seconds(duration),
            "position_seconds": self._seconds(position),
            "play_mode": play_mode,
            "shuffle": play_mode in {"SHUFFLE", "SHUFFLE_NOREPEAT"},
            "repeat": play_mode in {"SHUFFLE", "REPEAT_ALL", "REPEAT_ONE"},
            "repeat_one": play_mode == "REPEAT_ONE",
            "crossfade": crossfade,
            "can_crossfade": can_crossfade,
            **extended_status,
        }

    def _extended_player_status(self, host):
        """Read infrequently changed sound settings without polling them every 2 seconds."""
        cached = self._extended_status_cache.get(host)
        if cached and cached["expires_at"] > time.monotonic():
            return cached["values"]
        values = {
            "can_audio_tuning": False,
            "bass": 0,
            "treble": 0,
            "loudness": False,
            "can_sleep_timer": False,
            "sleep_timer_minutes": 0,
            "can_alarms": False,
            "alarms": [],
            "running_alarm_id": "",
            "can_queue": False,
            "queue": [],
            "can_favorites": False,
            "favorites": [],
            "can_saved_queues": False,
            "saved_queues": [],
            "can_device_settings": False,
            "led_on": True,
            "button_locked": False,
            "can_output_fixed": False,
            "output_fixed": False,
            "can_room_calibration_status": False,
            "room_calibration_enabled": False,
            "can_rename_room": False,
            "room_name": "",
            "room_configuration": "1",
            "can_tv_input": False,
            "can_tv_autoplay": False,
            "autoplay_linked_zones": False,
            "autoplay_room_id": "",
            "autoplay_volume": 0,
            "use_autoplay_volume": False,
            "can_home_theater_feedback": False,
            "ir_repeater_on": False,
            "led_feedback_on": False,
            "remote_configured": False,
            "home_theater_eq": {},
            "can_line_in": False,
            "line_in_name": "Line-in",
            "line_in_icon": "",
            "line_in_level": 0,
        }
        try:
            bass_xml = self._soap(host, "RenderingControl", "GetBass", {"InstanceID": 0})
            treble_xml = self._soap(host, "RenderingControl", "GetTreble", {"InstanceID": 0})
            loudness_xml = self._soap(host, "RenderingControl", "GetLoudness", {"InstanceID": 0, "Channel": "Master"})
            values.update(
                {
                    "can_audio_tuning": True,
                    "bass": int(self._value(bass_xml, "CurrentBass", "0")),
                    "treble": int(self._value(treble_xml, "CurrentTreble", "0")),
                    "loudness": self._value(loudness_xml, "CurrentLoudness", "0") == "1",
                }
            )
        except (requests.RequestException, ElementTree.ParseError, ValueError):
            pass
        try:
            sleep_xml = self._soap(host, "AVTransport", "GetRemainingSleepTimerDuration", {"InstanceID": 0})
            values["can_sleep_timer"] = True
            values["sleep_timer_minutes"] = self._seconds(self._value(sleep_xml, "RemainingSleepTimerDuration")) // 60
        except (requests.RequestException, ElementTree.ParseError):
            pass
        try:
            alarms_xml = self._soap(host, "AlarmClock", "ListAlarms")
            alarm_list = self._value(alarms_xml, "CurrentAlarmList")
            alarms_root = ElementTree.fromstring(alarm_list) if alarm_list else None
            values["alarms"] = [
                {
                    "id": alarm.attrib.get("ID", ""),
                    "time": alarm.attrib.get("StartTime", ""),
                    "room": alarm.attrib.get("RoomUUID", ""),
                    "enabled": alarm.attrib.get("Enabled", "0") == "1",
                    "recurrence": alarm.attrib.get("Recurrence", ""),
                    "duration": alarm.attrib.get("Duration", "00:30:00"),
                    "program_uri": alarm.attrib.get("ProgramURI", "x-rincon-buzzer:0"),
                    "program_metadata": alarm.attrib.get("ProgramMetaData", ""),
                    "play_mode": alarm.attrib.get("PlayMode", "NORMAL"),
                    "volume": alarm.attrib.get("Volume", "20"),
                    "include_linked_zones": alarm.attrib.get("IncludeLinkedZones", "1"),
                }
                for alarm in (alarms_root.findall(".//Alarm") if alarms_root is not None else [])[:20]
            ]
            values["can_alarms"] = True
        except (requests.RequestException, ElementTree.ParseError):
            values["alarms"], values["can_alarms"] = [], False
        if values["can_alarms"]:
            try:
                running_xml = self._soap(host, "AVTransport", "GetRunningAlarmProperties", {"InstanceID": 0})
                values["running_alarm_id"] = self._value(running_xml, "AlarmID")
            except (requests.RequestException, ElementTree.ParseError):
                pass
        try:
            queue_xml = self._content_directory(
                host,
                "Browse",
                {
                    "ObjectID": "Q:0",
                    "BrowseFlag": "BrowseDirectChildren",
                    "Filter": "*",
                    "StartingIndex": 0,
                    "RequestedCount": 50,
                    "SortCriteria": "",
                },
            )
            queue_didl = self._value(queue_xml, "Result")
            queue_root = ElementTree.fromstring(queue_didl) if queue_didl else None
            values["queue"] = [
                {
                    "id": item.attrib.get("id", ""),
                    "title": next((child.text or "" for child in item.iter() if child.tag.endswith("title")), "Onbekend nummer"),
                    "artist": next((child.text or "" for child in item.iter() if child.tag.endswith("creator")), ""),
                }
                for item in (queue_root.findall(".//{*}item") if queue_root is not None else [])[:50]
            ]
            values["can_queue"] = True
        except (requests.RequestException, ElementTree.ParseError):
            values["queue"], values["can_queue"] = [], False
        try:
            favorites_xml = self._content_directory(
                host,
                "Browse",
                {
                    "ObjectID": "FV:2",
                    "BrowseFlag": "BrowseDirectChildren",
                    "Filter": "*",
                    "StartingIndex": 0,
                    "RequestedCount": 50,
                    "SortCriteria": "",
                },
            )
            favorites_didl = self._value(favorites_xml, "Result")
            favorites_root = ElementTree.fromstring(favorites_didl) if favorites_didl else None
            values["favorites"] = [
                {
                    "id": item.attrib.get("id", ""),
                    "name": next((child.text or "" for child in item.iter() if child.tag.endswith("title")), "Onbekende favoriet"),
                    "uri": next((child.text or "" for child in item.iter() if child.tag.endswith("res")), ""),
                    "metadata": next((child.text or "" for child in item.iter() if child.tag.endswith("resMD")), ""),
                    "playable": bool(next((child.text or "" for child in item.iter() if child.tag.endswith("res")), "")),
                }
                for item in (favorites_root.findall(".//{*}item") if favorites_root is not None else [])[:50]
            ]
            values["can_favorites"] = True
        except (requests.RequestException, ElementTree.ParseError):
            values["favorites"], values["can_favorites"] = [], False
        try:
            saved_queues_xml = self._content_directory(
                host,
                "Browse",
                {
                    "ObjectID": "SQ:",
                    "BrowseFlag": "BrowseDirectChildren",
                    "Filter": "*",
                    "StartingIndex": 0,
                    "RequestedCount": 50,
                    "SortCriteria": "",
                },
            )
            saved_queues_didl = self._value(saved_queues_xml, "Result")
            saved_queues_root = ElementTree.fromstring(saved_queues_didl) if saved_queues_didl else None
            values["saved_queues"] = [
                {
                    "id": item.attrib.get("id", ""),
                    "name": next((child.text or "" for child in item.iter() if child.tag.endswith("title")), "Naamloze wachtrij"),
                    "uri": next((child.text or "" for child in item.iter() if child.tag.endswith("res")), ""),
                    "metadata": next((child.text or "" for child in item.iter() if child.tag.endswith("resMD")), ""),
                }
                for item in (saved_queues_root.findall(".//{*}container") if saved_queues_root is not None else [])[:50]
            ]
            values["can_saved_queues"] = True
        except (requests.RequestException, ElementTree.ParseError):
            values["saved_queues"], values["can_saved_queues"] = [], False
        try:
            led_xml = self._soap(host, "DeviceProperties", "GetLEDState")
            lock_xml = self._soap(host, "DeviceProperties", "GetButtonLockState")
            values.update(
                {
                    "can_device_settings": True,
                    "led_on": self._value(led_xml, "CurrentLEDState", "On") == "On",
                    "button_locked": self._value(lock_xml, "CurrentButtonLockState", "Off") == "On",
                }
            )
        except (requests.RequestException, ElementTree.ParseError):
            values.update({"can_device_settings": False, "led_on": True, "button_locked": False})
        try:
            supports_fixed_xml = self._soap(host, "RenderingControl", "GetSupportsOutputFixed", {"InstanceID": 0})
            output_fixed_xml = self._soap(host, "RenderingControl", "GetOutputFixed", {"InstanceID": 0})
            values.update(
                {
                    "can_output_fixed": self._value(supports_fixed_xml, "CurrentSupportsFixed", "0") == "1",
                    "output_fixed": self._value(output_fixed_xml, "CurrentFixed", "0") == "1",
                }
            )
        except (requests.RequestException, ElementTree.ParseError):
            pass
        try:
            calibration_xml = self._soap(host, "RenderingControl", "GetRoomCalibrationStatus", {"InstanceID": 0})
            values.update(
                {
                    "can_room_calibration_status": self._value(calibration_xml, "RoomCalibrationAvailable", "0") == "1",
                    "room_calibration_enabled": self._value(calibration_xml, "RoomCalibrationEnabled", "0") == "1",
                }
            )
        except (requests.RequestException, ElementTree.ParseError):
            pass
        try:
            zone_info_xml = self._soap(host, "DeviceProperties", "GetZoneInfo")
            values["can_tv_input"] = int(self._value(zone_info_xml, "HTAudioIn", "0")) > 0
        except (requests.RequestException, ElementTree.ParseError, ValueError):
            pass
        if values["can_tv_input"]:
            try:
                autoplay_linked_xml = self._soap(host, "DeviceProperties", "GetAutoplayLinkedZones", {"Source": "spdif"})
                autoplay_room_xml = self._soap(host, "DeviceProperties", "GetAutoplayRoomUUID", {"Source": "spdif"})
                autoplay_volume_xml = self._soap(host, "DeviceProperties", "GetAutoplayVolume", {"Source": "spdif"})
                autoplay_use_volume_xml = self._soap(host, "DeviceProperties", "GetUseAutoplayVolume", {"Source": "spdif"})
                values.update(
                    {
                        "can_tv_autoplay": True,
                        "autoplay_linked_zones": self._value(autoplay_linked_xml, "IncludeLinkedZones", "0") == "1",
                        "autoplay_room_id": self._value(autoplay_room_xml, "RoomUUID"),
                        "autoplay_volume": int(self._value(autoplay_volume_xml, "CurrentVolume", "0")),
                        "use_autoplay_volume": self._value(autoplay_use_volume_xml, "UseVolume", "0") == "1",
                    }
                )
            except (requests.RequestException, ElementTree.ParseError, ValueError):
                pass
            try:
                ir_repeater_xml = self._soap(host, "HTControl", "GetIRRepeaterState")
                led_feedback_xml = self._soap(host, "HTControl", "GetLEDFeedbackState")
                remote_xml = self._soap(host, "HTControl", "IsRemoteConfigured")
                values.update(
                    {
                        "can_home_theater_feedback": True,
                        "ir_repeater_on": self._value(ir_repeater_xml, "CurrentIRRepeaterState", "Off") == "On",
                        "led_feedback_on": self._value(led_feedback_xml, "LEDFeedbackState", "Off") == "On",
                        "remote_configured": self._value(remote_xml, "RemoteConfigured", "0") == "1",
                    }
                )
            except (requests.RequestException, ElementTree.ParseError):
                pass
            for eq_type in (
                "NightMode",
                "DialogLevel",
                "SpeechEnhanceEnabled",
                "SurroundLevel",
                "MusicSurroundLevel",
                "SurroundEnable",
                "SurroundMode",
                "HeightChannelLevel",
                "SubGain",
                "AudioDelay",
                "SubCrossover",
            ):
                try:
                    eq_xml = self._soap(host, "RenderingControl", "GetEQ", {"InstanceID": 0, "EQType": eq_type})
                    values["home_theater_eq"][eq_type] = int(self._value(eq_xml, "CurrentValue", "0"))
                except (requests.RequestException, ElementTree.ParseError, ValueError):
                    continue
        try:
            zone_attributes_xml = self._soap(host, "DeviceProperties", "GetZoneAttributes")
            values["room_name"] = self._value(zone_attributes_xml, "CurrentZoneName")
            values["room_configuration"] = self._value(zone_attributes_xml, "CurrentConfiguration", "1")
            values["can_rename_room"] = bool(values["room_name"])
        except (requests.RequestException, ElementTree.ParseError):
            pass
        try:
            audio_input_xml = self._soap(host, "AudioIn", "GetAudioInputAttributes")
            line_level_xml = self._soap(host, "AudioIn", "GetLineInLevel")
            left_level = int(self._value(line_level_xml, "CurrentLeftLineInLevel", "0"))
            right_level = int(self._value(line_level_xml, "CurrentRightLineInLevel", str(left_level)))
            values.update(
                {
                    "can_line_in": True,
                    "line_in_name": self._value(audio_input_xml, "CurrentName", "Line-in"),
                    "line_in_icon": self._value(audio_input_xml, "CurrentIcon"),
                    "line_in_level": round((left_level + right_level) / 2),
                }
            )
        except (requests.RequestException, ElementTree.ParseError, ValueError):
            pass
        self._extended_status_cache[host] = {"expires_at": time.monotonic() + 15, "values": values}
        return values

    @staticmethod
    def _control_payload(value):
        try:
            payload = json.loads(str(value or ""))
        except (TypeError, ValueError) as error:
            raise RuntimeError("De Sonos-opdracht bevat ongeldige gegevens.") from error
        if not isinstance(payload, dict):
            raise RuntimeError("De Sonos-opdracht bevat ongeldige gegevens.")
        return payload

    @staticmethod
    def _queue_index(value):
        match = re.search(r"/(\d+)$", str(value or ""))
        if not match:
            raise RuntimeError("Dit nummer heeft geen geldige wachtrijpositie.")
        return int(match.group(1))

    @staticmethod
    def _playable_uri(value):
        """Accept direct media URIs without turning the speaker into an open proxy."""
        uri = str(value or "").strip()
        if not uri or len(uri) > 2048 or any(character in uri for character in "\r\n\x00"):
            raise RuntimeError("Geef een geldige media-URL op.")
        if not re.match(r"^(?:https?|x-sonos(?:api)?(?:-[a-z0-9]+)?|x-rincon|x-file-cifs):", uri, flags=re.IGNORECASE):
            raise RuntimeError("Gebruik een http(s)-stream of een geldige Sonos-bron-URL.")
        return uri

    def _alarm_by_id(self, host, alarm_id):
        alarms = self._extended_player_status(host).get("alarms", [])
        return next((alarm for alarm in alarms if str(alarm.get("id")) == str(alarm_id)), None)

    def _alarm_values(self, alarm, *, enabled=None, time_value=None, recurrence=None, volume=None):
        return {
            "ID": alarm["id"],
            "StartLocalTime": time_value or alarm.get("time") or "07:00:00",
            "Duration": alarm.get("duration") or "00:30:00",
            "Recurrence": recurrence or alarm.get("recurrence") or "DAILY",
            "Enabled": int(alarm.get("enabled") if enabled is None else enabled),
            "RoomUUID": alarm.get("room") or "",
            "ProgramURI": alarm.get("program_uri") or "x-rincon-buzzer:0",
            "ProgramMetaData": alarm.get("program_metadata") or "",
            "PlayMode": alarm.get("play_mode") or "NORMAL",
            "Volume": volume if volume is not None else alarm.get("volume") or "20",
            "IncludeLinkedZones": alarm.get("include_linked_zones") or "1",
        }

    @staticmethod
    def _tv_metadata(player_id):
        return (
            '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
            'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            '<item id="spdif-input" parentID="0" restricted="false">'
            f"<dc:title>{escape(player_id)}</dc:title>"
            '<upnp:class>object.item.audioItem.linein.homeTheater</upnp:class>'
            f'<res protocolInfo="spdif">x-sonos-htastream:{escape(player_id)}:spdif</res>'
            "</item></DIDL-Lite>"
        )

    def _member_audio_status(self, player_id):
        cached = self._member_status_cache.get(player_id)
        if cached and cached["expires_at"] > time.monotonic():
            return cached["values"]
        host = self.member_players.get(player_id)
        values = {"volume": None, "muted": False, "fixed": True}
        if host:
            try:
                volume_xml = self._soap(host, "RenderingControl", "GetVolume", {"InstanceID": 0, "Channel": "Master"})
                mute_xml = self._soap(host, "RenderingControl", "GetMute", {"InstanceID": 0, "Channel": "Master"})
                fixed_xml = self._soap(host, "RenderingControl", "GetOutputFixed", {"InstanceID": 0})
                values = {
                    "volume": int(self._value(volume_xml, "CurrentVolume", "0")),
                    "muted": self._value(mute_xml, "CurrentMute", "0") == "1",
                    "fixed": self._value(fixed_xml, "CurrentOutputFixed", "0") == "1",
                }
            except (requests.RequestException, ElementTree.ParseError, ValueError):
                pass
        self._member_status_cache[player_id] = {"expires_at": time.monotonic() + 15, "values": values}
        return values

    @staticmethod
    def _content_directory(host, action, values=None):
        values = values or {}
        body = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in values.items())
        envelope = f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:{action} xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">{body}</u:{action}></s:Body></s:Envelope>'
        response = requests.post(
            f"http://{host}:1400/MediaServer/ContentDirectory/Control",
            data=envelope.encode(),
            headers={"SOAPACTION": f'"urn:schemas-upnp-org:service:ContentDirectory:1#{action}"', "Content-Type": 'text/xml; charset="utf-8"'},
            timeout=5,
        )
        response.raise_for_status()
        return ElementTree.fromstring(response.content)

    def inventory(self):
        devices = self._sonos_devices()
        by_id = {device["key"].replace("uuid:", ""): device for device in devices}
        self.players = {}
        self.group_members = {}
        self.topology_members = {}
        self.member_players = {player_id: device["address"] for player_id, device in by_id.items() if device.get("address")}
        output = []
        seen_coordinators = set()
        for device in devices:
            try:
                groups = self._zone_groups(device["address"])
            except (requests.RequestException, ElementTree.ParseError):
                continue
            for topology_group in groups:
                for topology_member in topology_group["members"]:
                    topology_id = topology_member.attrib.get("UUID", "")
                    topology_device = by_id.get(topology_id)
                    if topology_id:
                        self.topology_members[topology_id] = {
                            "id": topology_id,
                            "name": self._speaker_label((topology_device or {}).get("name") or topology_member.attrib.get("ZoneName") or topology_id),
                            "boot_seq": topology_member.attrib.get("BootSeq", ""),
                            "is_satellite": topology_member.tag.endswith("Satellite"),
                        }
            for group in groups:
                coordinator = group["coordinator"]
                if coordinator in seen_coordinators:
                    continue
                coordinator_device = by_id.get(coordinator)
                if not coordinator_device:
                    continue
                try:
                    status = self._player_status(coordinator_device["address"])
                except (requests.RequestException, ElementTree.ParseError, ValueError):
                    continue
                seen_coordinators.add(coordinator)
                self.players[coordinator] = coordinator_device["address"]
                member_names = []
                member_controls = []
                member_topology = []
                for member in group["members"]:
                    member_id = member.attrib.get("UUID", "")
                    member_device = by_id.get(member_id)
                    member_name = self._speaker_label((member_device or {}).get("name") or member.attrib.get("ZoneName") or member_id)
                    member_names.append(member_name)
                    member_status = self._member_audio_status(member_id)
                    member_controls.append({"id": member_id, "name": member_name, **member_status})
                    member_topology.append(
                        {
                            "id": member_id,
                            "name": member_name,
                            "is_coordinator": member_id == coordinator,
                            "is_satellite": member.tag.endswith("Satellite"),
                            "boot_seq": member.attrib.get("BootSeq", ""),
                            "channel_map": member.attrib.get("HTSatChanMapSet", ""),
                            "calibration_state": member.attrib.get("RoomCalibrationState", ""),
                        }
                    )
                self.group_members[coordinator] = member_topology
                current_member_ids = {member["id"] for member in member_topology}
                grouping_candidates = [
                    member
                    for member in self.topology_members.values()
                    if member["id"] not in current_member_ids and member.get("boot_seq") and not member.get("is_satellite")
                ]
                channel_map = next((member.get("channel_map") for member in member_topology if member.get("is_coordinator") and member.get("channel_map")), "")
                is_stereo_pair = bool(
                    len(member_topology) == 2
                    and ":LF,LF" in channel_map
                    and ":RF,RF" in channel_map
                )
                group_name = group["members"][0].attrib.get("ZoneName") or coordinator_device["name"]
                output.append(
                    {
                        "source": "sonos",
                        "local_key": f"group:{coordinator}",
                        "external_id": f"group:{coordinator}",
                        "domain": "speaker",
                        "name": group_name,
                        "state": "on" if status["transport"] == "PLAYING" else "off",
                        "is_available": True,
                        "is_supported": True,
                        "attributes": {
                            "sonos_entity_type": "group",
                            "sonos_group_id": coordinator,
                            "sonos_group_name": group_name,
                            "sonos_player_ids": [member.attrib.get("UUID", "") for member in group["members"]],
                            "sonos_member_names": member_names,
                            "sonos_member_controls": member_controls,
                            "sonos_group_members": member_topology,
                            "sonos_has_physical_members": any(not member["is_coordinator"] for member in member_topology),
                            "sonos_can_room_calibration": any(member.get("calibration_state") for member in member_topology),
                            "sonos_is_stereo_pair": is_stereo_pair,
                            "sonos_stereo_channel_map": channel_map if is_stereo_pair else "",
                            "sonos_grouping_candidates": grouping_candidates,
                            "sonos_volume": status["volume"],
                            "sonos_muted": status["muted"],
                            "sonos_playback_state": f"PLAYBACK_STATE_{status['transport']}",
                            "sonos_now_playing_title": status["now_playing"].get("title", ""),
                            "sonos_now_playing_artist": status["now_playing"].get("artist", ""),
                            "sonos_now_playing_album": status["now_playing"].get("album", ""),
                            "sonos_now_playing_artwork": status["now_playing"].get("artwork", ""),
                            "sonos_source_name": status["source"],
                            "sonos_is_tv_input": status["is_tv_input"],
                            "sonos_can_tv_input": status["can_tv_input"],
                            "sonos_can_tv_autoplay": status["can_tv_autoplay"],
                            "sonos_autoplay_linked_zones": status["autoplay_linked_zones"],
                            "sonos_autoplay_room_id": status["autoplay_room_id"],
                            "sonos_autoplay_rooms": [member for member in self.topology_members.values() if not member.get("is_satellite")],
                            "sonos_autoplay_volume": status["autoplay_volume"],
                            "sonos_use_autoplay_volume": status["use_autoplay_volume"],
                            "sonos_can_home_theater_feedback": status["can_home_theater_feedback"],
                            "sonos_ir_repeater_on": status["ir_repeater_on"],
                            "sonos_led_feedback_on": status["led_feedback_on"],
                            "sonos_remote_configured": status["remote_configured"],
                            "sonos_home_theater_eq": status["home_theater_eq"],
                            "sonos_position": status["position"],
                            "sonos_duration": status["duration"],
                            "sonos_position_seconds": status["position_seconds"],
                            "sonos_duration_seconds": status["duration_seconds"],
                            "sonos_progress_percent": round(status["position_seconds"] / status["duration_seconds"] * 100, 2) if status["duration_seconds"] else 0,
                            "sonos_can_next": "next" in status["actions"],
                            "sonos_can_previous": "previous" in status["actions"],
                            "sonos_can_shuffle": True,
                            "sonos_can_repeat": True,
                            "sonos_shuffle": status["shuffle"],
                            "sonos_repeat": status["repeat"],
                            "sonos_repeat_one": status["repeat_one"],
                            "sonos_crossfade": status["crossfade"],
                            "sonos_can_crossfade": status["can_crossfade"],
                            "sonos_can_audio_tuning": status["can_audio_tuning"],
                            "sonos_bass": status["bass"],
                            "sonos_treble": status["treble"],
                            "sonos_loudness": status["loudness"],
                            "sonos_can_sleep_timer": status["can_sleep_timer"],
                            "sonos_sleep_timer_minutes": status["sleep_timer_minutes"],
                            "sonos_can_alarms": status["can_alarms"],
                            "sonos_alarms": status["alarms"],
                            "sonos_running_alarm_id": status["running_alarm_id"],
                            "sonos_can_device_settings": status["can_device_settings"],
                            "sonos_led_on": status["led_on"],
                            "sonos_button_locked": status["button_locked"],
                            "sonos_can_output_fixed": status["can_output_fixed"],
                            "sonos_output_fixed": status["output_fixed"],
                            "sonos_can_room_calibration_status": status["can_room_calibration_status"],
                            "sonos_room_calibration_enabled": status["room_calibration_enabled"],
                            "sonos_can_rename_room": status["can_rename_room"],
                            "sonos_room_name": status["room_name"],
                            "sonos_can_queue": status["can_queue"],
                            "sonos_queue": status["queue"],
                            "sonos_can_favorites": status["can_favorites"],
                            "sonos_favorites": status["favorites"],
                            "sonos_can_saved_queues": status["can_saved_queues"],
                            "sonos_saved_queues": status["saved_queues"],
                            "sonos_can_line_in": status["can_line_in"],
                            "sonos_line_in_name": status["line_in_name"],
                            "sonos_line_in_icon": status["line_in_icon"],
                            "sonos_line_in_level": status["line_in_level"],
                        },
                    }
                )
        return output

    def control(self, local_key, action, value):
        _, player_id = local_key.split(":", 1)
        host = self.players.get(player_id)
        if not host:
            self.inventory()
            host = self.players.get(player_id)
        if not host:
            raise RuntimeError("Sonos-groep is lokaal niet gevonden.")
        if action == "set_volume":
            self._soap(host, "GroupRenderingControl", "SetGroupVolume", {"InstanceID": 0, "DesiredVolume": int(float(value))})
        elif action in {"mute", "unmute"}:
            self._soap(host, "GroupRenderingControl", "SetGroupMute", {"InstanceID": 0, "DesiredMute": 1 if action == "mute" else 0})
        elif action in {"on", "off", "play_pause"}:
            if action == "play_pause":
                status = self._player_status(host)["transport"]
                command = "Pause" if status == "PLAYING" else "Play"
            else:
                command = "Play" if action == "on" else "Pause"
            self._soap(host, "AVTransport", command, {"InstanceID": 0, "Speed": 1} if command == "Play" else {"InstanceID": 0})
        elif action in {"next", "previous"}:
            self._soap(host, "AVTransport", "Next" if action == "next" else "Previous", {"InstanceID": 0})
        elif action in {"toggle_shuffle", "toggle_repeat"}:
            status = self._player_status(host)
            shuffle = bool(status["shuffle"])
            repeat = bool(status["repeat"])
            if action == "toggle_shuffle":
                shuffle = not shuffle
            else:
                repeat = not repeat
            play_mode = "SHUFFLE" if shuffle and repeat else "SHUFFLE_NOREPEAT" if shuffle else "REPEAT_ALL" if repeat else "NORMAL"
            self._soap(host, "AVTransport", "SetPlayMode", {"InstanceID": 0, "NewPlayMode": play_mode})
        elif action == "set_repeat_mode":
            repeat_mode = str(value or "off")
            if repeat_mode not in {"off", "all", "one"}:
                raise RuntimeError("Kies een geldige herhaalmodus.")
            status = self._player_status(host)
            shuffle = bool(status["shuffle"])
            play_mode = "REPEAT_ONE" if repeat_mode == "one" else "SHUFFLE" if repeat_mode == "all" and shuffle else "REPEAT_ALL" if repeat_mode == "all" else "SHUFFLE_NOREPEAT" if shuffle else "NORMAL"
            self._soap(host, "AVTransport", "SetPlayMode", {"InstanceID": 0, "NewPlayMode": play_mode})
        elif action == "toggle_crossfade":
            crossfade = not bool(self._player_status(host)["crossfade"])
            self._soap(host, "AVTransport", "SetCrossfadeMode", {"InstanceID": 0, "CrossfadeMode": int(crossfade)})
        elif action in {"set_bass", "set_treble"}:
            try:
                level = max(-10, min(10, int(value)))
            except (TypeError, ValueError) as error:
                raise RuntimeError("Kies een waarde tussen -10 en 10.") from error
            setting = "Bass" if action == "set_bass" else "Treble"
            self._soap(host, "RenderingControl", f"Set{setting}", {"InstanceID": 0, f"Desired{setting}": level})
        elif action == "toggle_loudness":
            loudness = not bool(self._player_status(host)["loudness"])
            self._soap(host, "RenderingControl", "SetLoudness", {"InstanceID": 0, "Channel": "Master", "DesiredLoudness": int(loudness)})
        elif action == "reset_equalizer":
            self._soap(host, "RenderingControl", "ResetBasicEQ", {"InstanceID": 0})
        elif action == "set_sleep_timer":
            try:
                minutes = max(0, min(720, int(value)))
            except (TypeError, ValueError) as error:
                raise RuntimeError("Kies een slaaptimer tussen 0 en 720 minuten.") from error
            duration = "" if minutes == 0 else f"{minutes // 60:02}:{minutes % 60:02}:00"
            self._soap(host, "AVTransport", "ConfigureSleepTimer", {"InstanceID": 0, "NewSleepTimerDuration": duration})
        elif action == "switch_to_tv":
            if not self._extended_player_status(host).get("can_tv_input"):
                raise RuntimeError("Deze Sonos-groep heeft geen tv-ingang.")
            uri = f"x-sonos-htastream:{player_id}:spdif"
            self._soap(host, "AVTransport", "SetAVTransportURI", {"InstanceID": 0, "CurrentURI": uri, "CurrentURIMetaData": self._tv_metadata(player_id)})
            self._soap(host, "AVTransport", "Play", {"InstanceID": 0, "Speed": 1})
        elif action == "select_line_in":
            if not self._extended_player_status(host).get("can_line_in"):
                raise RuntimeError("Deze Sonos-speaker heeft geen lokale line-in.")
            self._soap(host, "AudioIn", "SelectAudio", {"ObjectID": f"x-rincon-stream:{player_id}"})
        elif action in {"set_line_in_level", "rename_line_in", "start_line_in_transmission", "stop_line_in_transmission"}:
            status = self._extended_player_status(host)
            if not status.get("can_line_in"):
                raise RuntimeError("Deze Sonos-speaker heeft geen lokale line-in.")
            if action == "set_line_in_level":
                try:
                    level = max(0, min(100, int(value)))
                except (TypeError, ValueError) as error:
                    raise RuntimeError("Kies een line-inniveau tussen 0 en 100.") from error
                self._soap(host, "AudioIn", "SetLineInLevel", {"DesiredLeftLineInLevel": level, "DesiredRightLineInLevel": level})
            elif action == "rename_line_in":
                name = str(value or "").strip()
                if not name or len(name) > 64:
                    raise RuntimeError("Geef de line-in een naam van maximaal 64 tekens.")
                self._soap(host, "AudioIn", "SetAudioInputAttributes", {"DesiredName": name, "DesiredIcon": status.get("line_in_icon", "")})
            else:
                self._soap(host, "AudioIn", "StartTransmissionToGroup" if action == "start_line_in_transmission" else "StopTransmissionToGroup", {"CoordinatorID": player_id})
        elif action in {"toggle_autoplay_linked_zones", "toggle_use_autoplay_volume", "set_autoplay_volume", "set_autoplay_room"}:
            status = self._extended_player_status(host)
            if not status.get("can_tv_autoplay"):
                raise RuntimeError("Tv-autoplay is niet beschikbaar voor deze Sonos-groep.")
            if action == "toggle_autoplay_linked_zones":
                self._soap(host, "DeviceProperties", "SetAutoplayLinkedZones", {"Source": "spdif", "IncludeLinkedZones": int(not status["autoplay_linked_zones"])})
            elif action == "set_autoplay_room":
                room_id = str(value or "")
                if room_id not in self.topology_members:
                    raise RuntimeError("Kies een bekende Sonos-ruimte voor tv-autoplay.")
                self._soap(host, "DeviceProperties", "SetAutoplayRoomUUID", {"Source": "spdif", "RoomUUID": room_id})
            elif action == "toggle_use_autoplay_volume":
                self._soap(host, "DeviceProperties", "SetUseAutoplayVolume", {"Source": "spdif", "UseVolume": int(not status["use_autoplay_volume"])})
            else:
                try:
                    volume = max(0, min(100, int(value)))
                except (TypeError, ValueError) as error:
                    raise RuntimeError("Kies een tv-autoplayvolume tussen 0 en 100.") from error
                self._soap(host, "DeviceProperties", "SetAutoplayVolume", {"Source": "spdif", "Volume": volume})
        elif action in {"toggle_ir_repeater", "toggle_led_feedback"}:
            status = self._extended_player_status(host)
            if not status.get("can_home_theater_feedback"):
                raise RuntimeError("Deze home-theaterinstelling is niet beschikbaar.")
            if action == "toggle_ir_repeater":
                self._soap(host, "HTControl", "SetIRRepeaterState", {"DesiredIRRepeaterState": "Off" if status["ir_repeater_on"] else "On"})
            else:
                self._soap(host, "HTControl", "SetLEDFeedbackState", {"LEDFeedbackState": "Off" if status["led_feedback_on"] else "On"})
        elif action in {"identify_ir_remote", "learn_ir_code", "commit_ir_remote"}:
            if not self._extended_player_status(host).get("can_home_theater_feedback"):
                raise RuntimeError("Deze Sonos-groep ondersteunt geen IR-afstandsbediening.")
            if action == "identify_ir_remote":
                try:
                    timeout = max(5, min(60, int(value or 30)))
                except (TypeError, ValueError) as error:
                    raise RuntimeError("Kies een herkenningstijd tussen 5 en 60 seconden.") from error
                self._soap(host, "HTControl", "IdentifyIRRemote", {"Timeout": timeout})
            elif action == "learn_ir_code":
                payload = self._control_payload(value)
                code = str(payload.get("code") or "").strip()
                try:
                    timeout = max(5, min(60, int(payload.get("timeout", 30))))
                except (TypeError, ValueError) as error:
                    raise RuntimeError("Kies een leertijd tussen 5 en 60 seconden.") from error
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", code):
                    raise RuntimeError("Kies een geldige knop voor de afstandsbediening.")
                self._soap(host, "HTControl", "LearnIRCode", {"IRCode": code, "Timeout": timeout})
            else:
                name = str(value or "").strip()
                if not name or len(name) > 64:
                    raise RuntimeError("Geef de afstandsbediening een naam van maximaal 64 tekens.")
                self._soap(host, "HTControl", "CommitLearnedIRCodes", {"Name": name})
        elif action == "set_home_theater_eq":
            payload = self._control_payload(value)
            eq_type = str(payload.get("eq_type") or "")
            try:
                desired_value = int(payload.get("value"))
            except (TypeError, ValueError) as error:
                raise RuntimeError("Kies een geldige home-theaterwaarde.") from error
            supported = self._extended_player_status(host).get("home_theater_eq", {})
            if eq_type not in supported:
                raise RuntimeError("Deze home-theaterinstelling is niet beschikbaar.")
            if eq_type in {"NightMode", "DialogLevel", "SpeechEnhanceEnabled", "SurroundEnable", "SurroundMode", "SubCrossover"}:
                desired_value = 1 if desired_value else 0
            elif eq_type == "HeightChannelLevel":
                desired_value = max(-10, min(10, desired_value))
            elif eq_type == "AudioDelay":
                desired_value = max(0, min(15, desired_value))
            else:
                desired_value = max(-15, min(15, desired_value))
            self._soap(host, "RenderingControl", "SetEQ", {"InstanceID": 0, "EQType": eq_type, "DesiredValue": desired_value})
        elif action == "seek":
            try:
                seconds = max(0, int(value))
            except (TypeError, ValueError) as error:
                raise RuntimeError("Kies een geldig tijdstip.") from error
            target = f"{seconds // 3600:02}:{seconds % 3600 // 60:02}:{seconds % 60:02}"
            self._soap(host, "AVTransport", "Seek", {"InstanceID": 0, "Unit": "REL_TIME", "Target": target})
        elif action in {"play_uri", "queue_uri", "set_next_uri"}:
            uri = self._playable_uri(value)
            if action == "play_uri":
                self._soap(host, "AVTransport", "SetAVTransportURI", {"InstanceID": 0, "CurrentURI": uri, "CurrentURIMetaData": ""})
                self._soap(host, "AVTransport", "Play", {"InstanceID": 0, "Speed": 1})
            elif action == "queue_uri":
                self._soap(host, "AVTransport", "AddURIToQueue", {"InstanceID": 0, "EnqueuedURI": uri, "EnqueuedURIMetaData": "", "DesiredFirstTrackNumberEnqueued": 0, "EnqueueAsNext": 0})
            else:
                self._soap(host, "AVTransport", "SetNextAVTransportURI", {"InstanceID": 0, "NextURI": uri, "NextURIMetaData": ""})
        elif action == "remove_queue_item":
            object_id = str(value or "")
            if not object_id:
                raise RuntimeError("Kies een nummer uit de wachtrij.")
            self._soap(host, "AVTransport", "RemoveTrackFromQueue", {"InstanceID": 0, "ObjectID": object_id})
        elif action in {"move_queue_item_up", "move_queue_item_down"}:
            index = self._queue_index(value)
            target_index = index - 1 if action == "move_queue_item_up" else index + 1
            if target_index < 1:
                raise RuntimeError("Dit nummer staat al bovenaan de wachtrij.")
            queue = self._extended_player_status(host).get("queue", [])
            if target_index > len(queue):
                raise RuntimeError("Dit nummer staat al onderaan de wachtrij.")
            self._soap(
                host,
                "AVTransport",
                "ReorderTracksInQueue",
                {"InstanceID": 0, "StartingIndex": index, "NumberOfTracks": 1, "InsertBefore": target_index},
            )
        elif action == "clear_queue":
            self._soap(host, "AVTransport", "RemoveAllTracksFromQueue", {"InstanceID": 0})
        elif action == "refresh_music_library":
            self._content_directory(host, "RefreshShareIndex", {"AlbumArtistDisplayOption": "NONE"})
        elif action == "load_favorite":
            favorite_id = str(value or "")
            favorite = next((item for item in self._extended_player_status(host).get("favorites", []) if str(item.get("id")) == favorite_id), None)
            if not favorite or not favorite.get("uri"):
                raise RuntimeError("Deze Sonos-favoriet kan lokaal niet worden gestart.")
            self._soap(
                host,
                "AVTransport",
                "SetAVTransportURI",
                {"InstanceID": 0, "CurrentURI": favorite["uri"], "CurrentURIMetaData": favorite.get("metadata", "")},
            )
            self._soap(host, "AVTransport", "Play", {"InstanceID": 0, "Speed": 1})
        elif action == "save_queue":
            title = str(value or "").strip()
            if not title or len(title) > 80:
                raise RuntimeError("Geef de wachtrij een naam van maximaal 80 tekens.")
            self._soap(host, "AVTransport", "SaveQueue", {"InstanceID": 0, "Title": title, "ObjectID": ""})
        elif action == "load_saved_queue":
            queue_id = str(value or "")
            queue = next((item for item in self._extended_player_status(host).get("saved_queues", []) if str(item.get("id")) == queue_id), None)
            if not queue or not queue.get("uri"):
                raise RuntimeError("Deze opgeslagen wachtrij kan lokaal niet worden gestart.")
            self._soap(
                host,
                "AVTransport",
                "SetAVTransportURI",
                {"InstanceID": 0, "CurrentURI": queue["uri"], "CurrentURIMetaData": queue.get("metadata", "")},
            )
            self._soap(host, "AVTransport", "Play", {"InstanceID": 0, "Speed": 1})
        elif action == "delete_saved_queue":
            queue_id = str(value or "")
            queue = next((item for item in self._extended_player_status(host).get("saved_queues", []) if str(item.get("id")) == queue_id), None)
            if not queue:
                raise RuntimeError("Deze opgeslagen wachtrij is niet meer beschikbaar.")
            self._content_directory(host, "DestroyObject", {"ObjectID": queue_id})
        elif action == "create_alarm":
            payload = self._control_payload(value)
            time_value = str(payload.get("time") or "").strip()
            recurrence = str(payload.get("recurrence") or "DAILY").upper()
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", time_value):
                raise RuntimeError("Kies een geldige tijd voor de wekker.")
            if recurrence not in {"DAILY", "ONCE", "WEEKDAYS", "WEEKENDS"}:
                raise RuntimeError("Kies een geldige herhaling voor de wekker.")
            self._soap(
                host,
                "AlarmClock",
                "CreateAlarm",
                {
                    "StartLocalTime": f"{time_value}:00" if len(time_value) == 5 else time_value,
                    "Duration": "00:30:00",
                    "Recurrence": recurrence,
                    "Enabled": 1,
                    "RoomUUID": player_id,
                    "ProgramURI": "x-rincon-buzzer:0",
                    "ProgramMetaData": "",
                    "PlayMode": "NORMAL",
                    "Volume": 20,
                    "IncludeLinkedZones": 1,
                },
            )
        elif action in {"toggle_alarm", "update_alarm", "delete_alarm", "snooze_alarm"}:
            payload = self._control_payload(value)
            alarm_id = str(payload.get("id") or "")
            alarm = self._alarm_by_id(host, alarm_id)
            if not alarm:
                raise RuntimeError("Deze Sonos-wekker is niet meer beschikbaar.")
            if action == "toggle_alarm":
                self._soap(host, "AlarmClock", "UpdateAlarm", self._alarm_values(alarm, enabled=not alarm.get("enabled")))
            elif action == "update_alarm":
                time_value = str(payload.get("time") or "").strip()
                recurrence = str(payload.get("recurrence") or "").upper()
                try:
                    volume = max(0, min(100, int(payload.get("volume"))))
                except (TypeError, ValueError) as error:
                    raise RuntimeError("Kies een volume tussen 0 en 100 voor de wekker.") from error
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", time_value):
                    raise RuntimeError("Kies een geldige tijd voor de wekker.")
                if recurrence not in {"DAILY", "ONCE", "WEEKDAYS", "WEEKENDS"}:
                    raise RuntimeError("Kies een geldige herhaling voor de wekker.")
                self._soap(
                    host,
                    "AlarmClock",
                    "UpdateAlarm",
                    self._alarm_values(
                        alarm,
                        time_value=f"{time_value}:00" if len(time_value) == 5 else time_value,
                        recurrence=recurrence,
                        volume=volume,
                    ),
                )
            elif action == "delete_alarm":
                self._soap(host, "AlarmClock", "DestroyAlarm", {"ID": alarm_id})
            else:
                running_alarm_id = self._extended_player_status(host).get("running_alarm_id")
                if str(running_alarm_id) != alarm_id:
                    raise RuntimeError("Alleen een wekker die nu afgaat kan worden uitgesteld.")
                self._soap(host, "AVTransport", "SnoozeAlarm", {"InstanceID": 0, "Duration": "00:10:00"})
        elif action == "toggle_led":
            led_on = not bool(self._player_status(host)["led_on"])
            self._soap(host, "DeviceProperties", "SetLEDState", {"DesiredLEDState": "On" if led_on else "Off"})
        elif action == "toggle_button_lock":
            locked = not bool(self._player_status(host)["button_locked"])
            self._soap(host, "DeviceProperties", "SetButtonLockState", {"DesiredButtonLockState": "On" if locked else "Off"})
        elif action in {"toggle_output_fixed", "toggle_room_calibration"}:
            status = self._extended_player_status(host)
            if action == "toggle_output_fixed":
                if not status.get("can_output_fixed"):
                    raise RuntimeError("Deze Sonos-speaker ondersteunt geen vaste uitvoer.")
                self._soap(host, "RenderingControl", "SetOutputFixed", {"InstanceID": 0, "DesiredFixed": int(not status.get("output_fixed"))})
            else:
                if not status.get("can_room_calibration_status"):
                    raise RuntimeError("Deze Sonos-speaker ondersteunt geen instelbare kamerkalibratie.")
                self._soap(host, "RenderingControl", "SetRoomCalibrationStatus", {"InstanceID": 0, "RoomCalibrationEnabled": int(not status.get("room_calibration_enabled"))})
        elif action == "rename_room":
            room_name = str(value or "").strip()
            if not room_name or len(room_name) > 32:
                raise RuntimeError("Geef de Sonos-ruimte een naam van maximaal 32 tekens.")
            status = self._extended_player_status(host)
            if not status.get("can_rename_room"):
                raise RuntimeError("Deze Sonos-ruimte kan lokaal niet worden hernoemd.")
            self._soap(
                host,
                "DeviceProperties",
                "SetZoneAttributes",
                {"DesiredZoneName": room_name, "DesiredIcon": "", "DesiredConfiguration": status.get("room_configuration") or "1"},
            )
        elif action == "remove_group_member":
            payload = self._control_payload(value)
            member_id = str(payload.get("member_id") or "")
            if payload.get("confirmed") is not True:
                raise RuntimeError("Bevestig eerst dat deze speaker uit de fysieke Sonos-groep mag worden gehaald.")
            members = self.group_members.get(player_id)
            if not members:
                self.inventory()
                members = self.group_members.get(player_id, [])
            member = next((item for item in members if item["id"] == member_id), None)
            if not member or member.get("is_coordinator"):
                raise RuntimeError("Kies een niet-coördinerende speaker uit deze Sonos-groep.")
            if member.get("is_satellite"):
                self._soap(host, "DeviceProperties", "RemoveHTSatellite", {"SatRoomUUID": member_id})
            else:
                self._soap(host, "GroupManagement", "RemoveMember", {"MemberID": member_id})
        elif action == "add_group_member":
            payload = self._control_payload(value)
            member_id = str(payload.get("member_id") or "")
            if payload.get("confirmed") is not True:
                raise RuntimeError("Bevestig eerst dat deze speaker aan de fysieke Sonos-groep mag worden toegevoegd.")
            candidate = self.topology_members.get(member_id)
            if not candidate:
                self.inventory()
                candidate = self.topology_members.get(member_id)
            if not candidate or candidate.get("is_satellite") or not candidate.get("boot_seq"):
                raise RuntimeError("Kies een zelfstandige Sonos-speaker die aan deze groep mag worden toegevoegd.")
            self._soap(host, "GroupManagement", "AddMember", {"MemberID": member_id, "BootSeq": candidate["boot_seq"]})
        elif action == "add_ht_satellite":
            payload = self._control_payload(value)
            member_id = str(payload.get("member_id") or "")
            role = str(payload.get("role") or "").lower()
            if payload.get("confirmed") is not True:
                raise RuntimeError("Bevestig eerst dat deze speaker als home-theater-satelliet mag worden gekoppeld.")
            channel = {"sub": "SW", "links": "LR", "rechts": "RR"}.get(role)
            candidate = self.topology_members.get(member_id)
            members = self.group_members.get(player_id) or []
            current_map = next((member.get("channel_map") for member in members if member.get("is_coordinator") and member.get("channel_map")), f"{player_id}:LF,RF")
            if not channel or not candidate or candidate.get("is_satellite") or not candidate.get("boot_seq"):
                raise RuntimeError("Kies een zelfstandige speaker en een geldige home-theaterrol.")
            if re.search(rf":{channel}(?:;|$)", current_map):
                raise RuntimeError("Deze home-theaterrol is al bezet.")
            self._soap(host, "DeviceProperties", "AddHTSatellite", {"HTSatChanMapSet": f"{current_map};{member_id}:{channel}"})
        elif action == "create_stereo_pair":
            payload = self._control_payload(value)
            member_id = str(payload.get("member_id") or "")
            if payload.get("confirmed") is not True:
                raise RuntimeError("Bevestig eerst dat deze twee speakers een stereopaar mogen vormen.")
            members = self.group_members.get(player_id)
            if not members:
                self.inventory()
                members = self.group_members.get(player_id, [])
            candidate = self.topology_members.get(member_id)
            if len(members) != 1 or not candidate or candidate.get("is_satellite") or not candidate.get("boot_seq"):
                raise RuntimeError("Een stereopaar kan alleen met twee zelfstandige Sonos-speakers worden gemaakt.")
            channel_map = f"{player_id}:LF,LF;{member_id}:RF,RF"
            self._soap(host, "DeviceProperties", "CreateStereoPair", {"ChannelMapSet": channel_map})
        elif action == "separate_stereo_pair":
            payload = self._control_payload(value)
            if payload.get("confirmed") is not True:
                raise RuntimeError("Bevestig eerst dat het stereopaar mag worden gescheiden.")
            channel_map = payload.get("channel_map") or ""
            if not channel_map:
                raise RuntimeError("De kanaalmap van dit stereopaar ontbreekt.")
            self._soap(host, "DeviceProperties", "SeparateStereoPair", {"ChannelMapSet": channel_map})
        elif action in {"start_room_calibration", "stop_room_calibration"}:
            payload = self._control_payload(value)
            if payload.get("confirmed") is not True:
                raise RuntimeError("Bevestig eerst dat de room-calibration mag worden gestart of gestopt.")
            members = self.group_members.get(player_id)
            if not members:
                self.inventory()
                members = self.group_members.get(player_id, [])
            if not any(member.get("calibration_state") for member in members):
                raise RuntimeError("Room-calibration is niet beschikbaar voor deze Sonos-groep.")
            if action == "start_room_calibration":
                response = self._soap(
                    host,
                    "DeviceProperties",
                    "RoomDetectionStartChirping",
                    {"Channel": 0, "DurationMilliseconds": 3000, "ChirpIfPlayingSwappableAudio": 0},
                )
                play_id = self._value(response, "PlayId")
                if not play_id:
                    raise RuntimeError("Sonos gaf geen identificatie voor de testtoon terug.")
                self.room_detection_play_ids[player_id] = play_id
            else:
                play_id = self.room_detection_play_ids.get(player_id)
                if not play_id:
                    raise RuntimeError("Er is geen lopende Sonos-testtoon om te stoppen.")
                self._soap(host, "DeviceProperties", "RoomDetectionStopChirping", {"PlayId": play_id})
                self.room_detection_play_ids.pop(player_id, None)
        elif action in {"member_volume_up", "member_volume_down", "toggle_member_mute"}:
            member_id = str(value or "")
            member_host = self.member_players.get(member_id)
            if not member_host:
                raise RuntimeError("Deze Sonos-speaker is lokaal niet gevonden.")
            member_status = self._member_audio_status(member_id)
            if member_status["fixed"]:
                raise RuntimeError("Het volume van deze speaker is vast ingesteld.")
            if action == "toggle_member_mute":
                self._soap(member_host, "RenderingControl", "SetMute", {"InstanceID": 0, "Channel": "Master", "DesiredMute": int(not member_status["muted"])})
            else:
                delta = 5 if action == "member_volume_up" else -5
                volume = max(0, min(100, int(member_status["volume"] or 0) + delta))
                self._soap(member_host, "RenderingControl", "SetVolume", {"InstanceID": 0, "Channel": "Master", "DesiredVolume": volume})
            self._member_status_cache.pop(member_id, None)
        else:
            raise RuntimeError("Deze Sonos-actie wordt lokaal nog niet ondersteund.")
        self._extended_status_cache.pop(host, None)
