from __future__ import annotations

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
    "_home-assistant._tcp.local.",
    "_sonos._tcp.local.",
)


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
        self.devices[key] = {
            "key": key,
            "name": name.removesuffix(service_type).rstrip("."),
            "kind": service_type.removeprefix("_").removesuffix("._tcp.local."),
            "address": address or None,
            "method": "mdns",
            "details": {"service_type": service_type, "port": info.port, "server": info.server or ""},
        }

    def update_service(self, zeroconf, service_type, name):
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type, name):
        self.devices.pop(f"{service_type}:{name}", None)


def discover_ssdp(timeout: float = 2.0) -> list[dict]:
    message = "\r\n".join(["M-SEARCH * HTTP/1.1", "HOST: 239.255.255.250:1900", 'MAN: "ssdp:discover"', "MX: 1", "ST: ssdp:all", "", ""]).encode()
    socket_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    socket_client.settimeout(timeout)
    socket_client.sendto(message, SSDP_TARGET)
    locations = set()
    try:
        while True:
            response, _ = socket_client.recvfrom(4096)
            headers = response.decode(errors="ignore").splitlines()
            location = next((line.split(":", 1)[1].strip() for line in headers if line.lower().startswith("location:")), "")
            if location:
                locations.add(location)
    except TimeoutError:
        pass
    finally:
        socket_client.close()
    devices = []
    for location in locations:
        try:
            xml = requests.get(location, timeout=4).content
            root = ElementTree.fromstring(xml)
            namespace = {"d": "urn:schemas-upnp-org:device-1-0"}
            device = root.find("d:device", namespace)
            if device is None:
                continue
            values = {tag: (device.findtext(f"d:{tag}", namespaces=namespace) or "") for tag in ("friendlyName", "modelName", "UDN", "serialNumber")}
            host = urlparse(location).hostname or ""
            devices.append({"key": values["UDN"] or location, "name": values["friendlyName"] or host, "kind": values["modelName"] or "UPnP-apparaat", "address": host, "method": "ssdp", "details": {"location": location, "serial": values["serialNumber"]}})
        except (requests.RequestException, ElementTree.ParseError):
            continue
    return devices


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


def discover_network(timeout: float = 2.0) -> list[dict]:
    devices = discover_ssdp(timeout)
    seen = {(item.get("address"), item.get("name")) for item in devices}
    for device in discover_mdns(timeout):
        identity = (device.get("address"), device.get("name"))
        if identity not in seen:
            devices.append(device)
            seen.add(identity)
    return devices
