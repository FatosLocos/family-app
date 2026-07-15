from __future__ import annotations

import asyncio
import socket
import time
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


SSDP_TARGET = ("239.255.255.250", 1900)
MDNS_SERVICE_TYPES = (
    "_hap._tcp.local.",
    "_googlecast._tcp.local.",
    "_airplay._tcp.local.",
    "_raop._tcp.local.",
    "_spotify-connect._tcp.local.",
    "_matter._tcp.local.",
    "_matterc._udp.local.",
    "_androidtvremote2._tcp.local.",
    "_home-assistant._tcp.local.",
    "_sonos._tcp.local.",
)
WSD_TARGET = ("239.255.255.250", 3702)
WSD_PROBE = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<s:Envelope xmlns:s=\"http://www.w3.org/2003/05/soap-envelope\" xmlns:a=\"http://schemas.xmlsoap.org/ws/2004/08/addressing\" xmlns:d=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\">
  <s:Header><a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action><a:MessageID>uuid:{message_id}</a:MessageID><a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></s:Header>
  <s:Body><d:Probe/></s:Body>
</s:Envelope>"""


class _MdnsListener(ServiceListener):
    def __init__(self, zeroconf):
        self.zeroconf = zeroconf
        self.devices = {}

    def add_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name, timeout=1200)
        if not info:
            return
        addresses = info.parsed_addresses()
        address = addresses[0] if addresses else ""
        key = f"{service_type}:{name}"
        properties = {
            str(key.decode(errors="ignore") if isinstance(key, bytes) else key): str(value.decode(errors="ignore") if isinstance(value, bytes) else value)
            for key, value in (info.properties or {}).items()
        }
        self.devices[key] = {
            "key": key,
            "name": name.removesuffix(service_type).rstrip("."),
            "kind": service_type.removeprefix("_").removesuffix("._tcp.local."),
            "address": address or None,
            "method": "mdns",
            "details": {"service_type": service_type, "port": info.port, "server": info.server or "", "properties": properties, "suggested_integration": _suggested_integration(service_type, name)},
        }

    def update_service(self, zeroconf, service_type, name):
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type, name):
        self.devices.pop(f"{service_type}:{name}", None)


def _suggested_integration(service_type: str, name: str = "") -> str:
    value = f"{service_type} {name}".lower()
    if ("signify" in value or "philips hue" in value) and ("bridge" in value or "hue" in value):
        return "Philips Hue"
    if "philips" in value and ("android tv" in value or "uhd" in value):
        return "Google Cast / Android TV"
    if "googlecast" in value or "eureka" in value:
        return "Google Cast"
    if "androidtv" in value:
        return "Android TV"
    if "airplay" in value or "raop" in value:
        return "AirPlay"
    if "spotify-connect" in value:
        return "Spotify Connect"
    if "_hap" in value:
        return "Apple HomeKit"
    if "matter" in value:
        return "Matter"
    if "sonos" in value:
        return "Sonos"
    if "home-assistant" in value:
        return "Home Assistant"
    return "Handmatige beoordeling"


def _ssdp_headers(response: bytes) -> dict[str, str]:
    values = {}
    for line in response.decode(errors="ignore").splitlines()[1:]:
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip().lower()] = value.strip()
    return values


def discover_ssdp(timeout: float = 2.0) -> list[dict]:
    message = "\r\n".join(["M-SEARCH * HTTP/1.1", "HOST: 239.255.255.250:1900", 'MAN: "ssdp:discover"', "MX: 1", "ST: ssdp:all", "", ""]).encode()
    socket_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    socket_client.settimeout(timeout)
    socket_client.sendto(message, SSDP_TARGET)
    locations = {}
    try:
        while True:
            response, _ = socket_client.recvfrom(4096)
            headers = _ssdp_headers(response)
            location = headers.get("location", "")
            if location:
                locations[location] = headers
    except TimeoutError:
        pass
    finally:
        socket_client.close()
    devices = []
    for location, headers in locations.items():
        try:
            xml = requests.get(location, timeout=4).content
            root = ElementTree.fromstring(xml)
            namespace = {"d": "urn:schemas-upnp-org:device-1-0"}
            device = root.find("d:device", namespace)
            if device is None:
                continue
            values = {tag: (device.findtext(f"d:{tag}", namespaces=namespace) or "") for tag in ("friendlyName", "modelName", "modelDescription", "manufacturer", "deviceType", "UDN", "serialNumber", "presentationURL")}
            host = urlparse(location).hostname or ""
            devices.append({"key": values["UDN"] or location, "name": values["friendlyName"] or host, "kind": values["modelName"] or "UPnP-apparaat", "address": host, "method": "ssdp", "details": {"location": location, "serial": values["serialNumber"], "manufacturer": values["manufacturer"], "model_description": values["modelDescription"], "device_type": values["deviceType"], "presentation_url": values["presentationURL"], "server": headers.get("server", ""), "search_target": headers.get("st", ""), "suggested_integration": _suggested_integration(f"{values['manufacturer']} {values['modelName']} {values['deviceType']}", values['friendlyName'])}})
        except (requests.RequestException, ElementTree.ParseError):
            continue
    return devices


def discover_ws_discovery(timeout: float = 2.0) -> list[dict]:
    """Discover ONVIF/WS-Discovery endpoints by multicast, never address-scanning."""
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    client.settimeout(timeout)
    client.sendto(WSD_PROBE.format(message_id=f"{int(time.time() * 1000000):x}").encode(), WSD_TARGET)
    devices = {}
    try:
        while True:
            payload, sender = client.recvfrom(8192)
            try:
                root = ElementTree.fromstring(payload)
            except ElementTree.ParseError:
                continue
            namespaces = {"d": "http://schemas.xmlsoap.org/ws/2005/04/discovery", "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing"}
            for match in root.findall(".//d:ProbeMatch", namespaces):
                endpoint = match.findtext("a:EndpointReference/a:Address", namespaces=namespaces) or ""
                types = match.findtext("d:Types", namespaces=namespaces) or ""
                xaddrs = match.findtext("d:XAddrs", namespaces=namespaces) or ""
                first_address = xaddrs.split()[0] if xaddrs else ""
                host = urlparse(first_address).hostname or sender[0]
                key = endpoint or first_address or f"wsd:{host}"
                devices[key] = {"key": key, "name": host, "kind": "ONVIF/WS-Discovery-apparaat", "address": host, "method": "ws_discovery", "details": {"endpoint": endpoint, "types": types, "xaddrs": xaddrs, "suggested_integration": "ONVIF-camera" if "NetworkVideo" in types or "onvif" in types.lower() else "Handmatige beoordeling"}}
    except TimeoutError:
        pass
    finally:
        client.close()
    return list(devices.values())


def discover_mdns(timeout: float = 2.0) -> list[dict]:
    """Discover local services without probing arbitrary IP addresses."""
    zeroconf = Zeroconf()
    listener = _MdnsListener(zeroconf)
    browsers = []
    try:
        browsers = [ServiceBrowser(zeroconf, service_type, listener) for service_type in MDNS_SERVICE_TYPES]
        time.sleep(timeout)
        return list(listener.devices.values())
    finally:
        for browser in browsers:
            browser.cancel()
        zeroconf.close()


async def _discover_bluetooth_async(timeout: float) -> list[dict]:
    """Inventory advertised Bluetooth LE devices without pairing or connecting."""
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices = []
    for address, item in found.items():
        device, advertisement = item if isinstance(item, tuple) else (item, None)
        name = str(getattr(device, "name", "") or getattr(advertisement, "local_name", "") or "Bluetooth LE-apparaat")
        service_uuids = [str(value) for value in (getattr(advertisement, "service_uuids", None) or [])]
        manufacturer_data = getattr(advertisement, "manufacturer_data", None) or {}
        devices.append(
            {
                "key": f"ble:{address}",
                "name": name,
                "kind": "Bluetooth LE",
                "address": None,
                "method": "bluetooth_le",
                "details": {
                    "bluetooth_address": str(address),
                    "rssi": getattr(advertisement, "rssi", None),
                    "service_uuids": service_uuids,
                    "manufacturer_ids": [str(value) for value in manufacturer_data.keys()],
                    "suggested_integration": "Bluetooth LE",
                },
            }
        )
    return devices


def discover_bluetooth(timeout: float = 2.0) -> list[dict]:
    """BLE is optional: no adapter, permission or package is non-fatal."""
    try:
        return asyncio.run(_discover_bluetooth_async(timeout))
    except (ImportError, OSError, RuntimeError):
        return []
    except Exception as error:
        # Bleak raises its own exception class for macOS permissions and a
        # disabled adapter. Do not let an optional radio stop LAN discovery.
        if error.__class__.__module__.startswith("bleak."):
            return []
        raise


def discover_network(timeout: float = 2.0) -> list[dict]:
    devices = discover_ssdp(timeout) + discover_ws_discovery(timeout) + discover_bluetooth(timeout)
    seen = {(item.get("address"), item.get("name")) for item in devices}
    for device in discover_mdns(timeout):
        identity = (device.get("address"), device.get("name"))
        if identity not in seen:
            devices.append(device)
            seen.add(identity)
    return devices
