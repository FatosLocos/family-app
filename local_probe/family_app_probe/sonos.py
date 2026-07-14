from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.etree import ElementTree

import requests

from family_app_probe.discovery import discover_ssdp


SOAP_NAMESPACES = {"s": "http://schemas.xmlsoap.org/soap/envelope/"}


class SonosAdapter:
    """Read and control Sonos at the group coordinator, not at satellites."""

    name = "sonos"

    def __init__(self):
        self.players = {}
        self._event_server = None
        self._event_thread = None
        self._event_callback = None
        self._subscriptions = {}
        self.last_event_at = None
        self.last_event_error = ""

    def _sonos_devices(self):
        return [device for device in discover_ssdp() if "sonos" in str(device.get("kind", "")).lower()]

    def _soap(self, host, service, action, values=None):
        values = values or {}
        body = "".join(f"<{key}>{value}</{key}>" for key, value in values.items())
        envelope = f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:{action} xmlns:u="urn:schemas-upnp-org:service:{service}:1">{body}</u:{action}></s:Body></s:Envelope>'
        path = f"/{service}/Control" if service == "ZoneGroupTopology" else f"/MediaRenderer/{service}/Control"
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

    def _zone_groups(self, host):
        root = self._soap(host, "ZoneGroupTopology", "GetZoneGroupState")
        state = self._value(root, "ZoneGroupState")
        if not state:
            return []
        topology = ElementTree.fromstring(state)
        groups = []
        for group in topology.findall(".//ZoneGroup"):
            coordinator = group.attrib.get("Coordinator", "")
            members = [group.find("ZoneGroupMember")]
            members.extend(group.findall(".//Satellite"))
            members = [member for member in members if member is not None]
            if coordinator and members:
                groups.append({"coordinator": coordinator, "members": members})
        return groups

    def _player_status(self, host):
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
            metadata = self._didl_metadata(self._value(position_xml, "TrackMetaData"))
            source_metadata = self._didl_metadata(self._value(media_xml, "CurrentURIMetaData"))
            actions = {item.strip().lower() for item in self._value(actions_xml, "Actions").split(",") if item.strip()}
            duration = self._value(position_xml, "TrackDuration")
            position = self._value(position_xml, "RelTime")
        except (requests.RequestException, ElementTree.ParseError):
            metadata, source_metadata, actions, duration, position = {}, {}, set(), "", ""
        return {
            "volume": int(self._value(volume_xml, "CurrentVolume", "0")),
            "muted": self._value(mute_xml, "CurrentMute", "0") == "1",
            "transport": transport,
            "now_playing": metadata,
            "source": source_metadata.get("title", ""),
            "actions": actions,
            "duration": duration if duration != "NOT_IMPLEMENTED" else "",
            "position": position if position != "NOT_IMPLEMENTED" else "",
        }

    def inventory(self):
        devices = self._sonos_devices()
        by_id = {device["key"].replace("uuid:", ""): device for device in devices}
        self.players = {}
        output = []
        seen_coordinators = set()
        for device in devices:
            try:
                groups = self._zone_groups(device["address"])
            except (requests.RequestException, ElementTree.ParseError):
                continue
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
                for member in group["members"]:
                    member_id = member.attrib.get("UUID", "")
                    member_device = by_id.get(member_id)
                    member_names.append((member_device or {}).get("name") or member.attrib.get("ZoneName") or member_id)
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
                            "sonos_volume": status["volume"],
                            "sonos_muted": status["muted"],
                            "sonos_playback_state": f"PLAYBACK_STATE_{status['transport']}",
                            "sonos_now_playing_title": status["now_playing"].get("title", ""),
                            "sonos_now_playing_artist": status["now_playing"].get("artist", ""),
                            "sonos_now_playing_album": status["now_playing"].get("album", ""),
                            "sonos_now_playing_artwork": status["now_playing"].get("artwork", ""),
                            "sonos_source_name": status["source"],
                            "sonos_position": status["position"],
                            "sonos_duration": status["duration"],
                            "sonos_can_next": "next" in status["actions"],
                            "sonos_can_previous": "previous" in status["actions"],
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
            self._soap(host, "RenderingControl", "SetVolume", {"InstanceID": 0, "Channel": "Master", "DesiredVolume": int(float(value))})
        elif action in {"mute", "unmute"}:
            self._soap(host, "RenderingControl", "SetMute", {"InstanceID": 0, "Channel": "Master", "DesiredMute": 1 if action == "mute" else 0})
        elif action in {"on", "off", "play_pause"}:
            if action == "play_pause":
                status = self._player_status(host)["transport"]
                command = "Pause" if status == "PLAYING" else "Play"
            else:
                command = "Play" if action == "on" else "Pause"
            self._soap(host, "AVTransport", command, {"InstanceID": 0, "Speed": 1} if command == "Play" else {"InstanceID": 0})
        elif action in {"next", "previous"}:
            self._soap(host, "AVTransport", "Next" if action == "next" else "Previous", {"InstanceID": 0})
        else:
            raise RuntimeError("Deze Sonos-actie wordt lokaal nog niet ondersteund.")
