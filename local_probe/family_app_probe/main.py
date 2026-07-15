from __future__ import annotations

import asyncio
import argparse
import getpass
import json
import re
import socket
import threading
import time

import requests
import websocket
import urllib3

from family_app_probe import __version__
from family_app_probe.config import load_config, save_config
from family_app_probe.discovery import discover_network
from family_app_probe.google_cast import GoogleCastAdapter
from family_app_probe.hue import HueAdapter
from family_app_probe.nest_protect import NestProtectAdapter
from family_app_probe.philips_tv import PhilipsTVAdapter
from family_app_probe.sonos import SonosAdapter


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _safe_error(error: Exception) -> str:
    """Return a short diagnostic without leaking credentials into the app."""
    message = " ".join(str(error).split())
    message = re.sub(
        r"(?i)\b(access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization|cookies?|password|token)\b\s*[:=]\s*(?:bearer\s+)?[^\s,&]+",
        r"\1=[verborgen]",
        message,
    )
    return (message or "Onbekende fout.")[:180]


def pair(args):
    response = requests.post(
        f"{args.server.rstrip('/')}/instellingen/api/lokale-probe/pair/",
        json={"code": args.code, "name": args.name or socket.gethostname(), "version": __version__},
        timeout=15,
    )
    response.raise_for_status()
    config = {"server": args.server.rstrip("/"), **response.json(), "hue": {}, "nest_protect": {}}
    save_config(config)
    print(f"Probe gekoppeld als {config['probe_id']}.")


def hue_link(args):
    config = load_config()
    hue_config = config.setdefault("hue", {})
    hue_config["bridge"] = args.bridge.rstrip("/")
    adapter = HueAdapter(hue_config)
    adapter.link()
    save_config(config)
    print("Hue Bridge lokaal gekoppeld.")


def nest_protect_link(args):
    config = load_config()
    issue_token = str(args.issue_token or "").strip()
    cookies = getpass.getpass("Plak de Google-cookies voor Nest Protect (worden niet getoond): ").strip()
    if not issue_token or not cookies:
        raise SystemExit("Een issue token en Google-cookies zijn allebei nodig.")
    nest_config = {"issue_token": issue_token, "cookies": cookies}
    adapter = NestProtectAdapter(nest_config)
    count = len(adapter.inventory())
    config["nest_protect"] = nest_config
    save_config(config)
    print(f"Nest Protect lokaal gekoppeld ({count} melder(s) gevonden).")


def philips_tv_link(args):
    """Pair one Philips JointSpace TV locally and retain only probe-local credentials."""
    try:
        from haphilipsjs import PhilipsTV
    except ImportError as error:
        raise SystemExit("Installeer eerst de probe-afhankelijkheden opnieuw: .venv/bin/pip install -r requirements.txt") from error

    async def pair_tv():
        tv = PhilipsTV(args.host, api_version=args.api_version)
        try:
            await tv.getSystem()
            state = await tv.pairRequest("family_app", "Family App", socket.gethostname(), "Python", "native")
            pin = input("Voer de pincode in die nu op de Philips TV staat: ").strip()
            if not pin:
                raise RuntimeError("Er is geen pincode ingevuld.")
            username, password = await tv.pairGrant(state, pin)
            return username, password, tv.api_version
        finally:
            await tv.session.aclose()

    try:
        username, password, api_version = asyncio.run(pair_tv())
    except Exception as error:
        raise SystemExit(f"Philips TV-pairing is niet gelukt: {str(error)[:180]}") from error

    config = load_config()
    tv_config = config.setdefault("philips_tv", {})
    devices = tv_config.setdefault("devices", {})
    devices[args.host] = {"username": username, "password": password, "api_version": api_version}
    save_config(config)
    print("Philips TV lokaal gekoppeld. Start de probe opnieuw of voer run --once uit om bediening te activeren.")


def _adapters(config):
    hue = HueAdapter(config.get("hue", {}))
    return [hue, SonosAdapter(), NestProtectAdapter(config.get("nest_protect", {})), GoogleCastAdapter(), PhilipsTVAdapter(config.get("philips_tv", {}))]


def _send(ws, payload):
    ws.send(json.dumps(payload))


def _sync(ws, adapters, on_sonos_event=None, replace_adapter_status=False):
    entities = []
    adapter_status = {}
    for adapter in adapters:
        try:
            values = adapter.inventory()
            entities.extend(values)
            if adapter.name == "sonos" and on_sonos_event:
                adapter.ensure_events(on_sonos_event)
            adapter_status[adapter.name] = {"status": "active", "entities": len(values), **(adapter.event_status() if hasattr(adapter, "event_status") else {})}
        except Exception as error:
            adapter_status[adapter.name] = {"status": "error", "error": _safe_error(error)}
    _send(
        ws,
        {
            "type": "heartbeat",
            "version": __version__,
            "adapters": adapter_status,
            "replace_adapters": replace_adapter_status,
        },
    )
    _send(ws, {"type": "inventory", "entities": entities})
    return adapter_status


def run(args):
    config = load_config()
    required = {"probe_id", "token", "websocket_url"}
    if not required.issubset(config):
        raise SystemExit("Koppel eerst deze probe met het pair-commando.")
    adapters = _adapters(config)
    adapter_map = {adapter.name: adapter for adapter in adapters}
    sonos_changed = threading.Event()
    last_inventory = last_discovery = last_sonos_sync = 0.0
    reconnect_delay = 2.0
    while True:
        try:
            ws = websocket.create_connection(f"{config['websocket_url']}?token={config['token']}", timeout=20)
            ws.settimeout(1)
            print("Verbonden met Family App.")
            reconnect_delay = 2.0
            while True:
                now = time.monotonic()
                if now - last_inventory > args.inventory_interval:
                    sonos_changed.clear()
                    _sync(ws, adapters, on_sonos_event=sonos_changed.set, replace_adapter_status=True)
                    last_inventory = now
                    last_sonos_sync = now
                    sonos_changed.clear()
                # A one-off check is intentionally limited to the inventory.
                # Network discovery can take a minute on a larger LAN and is
                # not necessary to confirm pairing or device control.
                if args.once:
                    return
                # Sonos emits events for state changes, but not for every
                # elapsed playback second. Keep just this local adapter fresh
                # while the page is open; Hue and other adapters are untouched.
                elif "sonos" in adapter_map and (sonos_changed.is_set() or now - last_sonos_sync > args.sonos_refresh_interval):
                    sonos_changed.clear()
                    _sync(ws, [adapter_map["sonos"]], on_sonos_event=sonos_changed.set)
                    last_sonos_sync = now
                if now - last_discovery > args.discovery_interval:
                    try:
                        _send(ws, {"type": "discovery", "devices": discover_network()})
                    except Exception as error:
                        # Discovery is an optional enrichment. A temporary
                        # multicast/BLE failure must not drop device control.
                        print(f"Discovery overgeslagen: {_safe_error(error)}")
                    last_discovery = now
                try:
                    incoming = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                except json.JSONDecodeError:
                    print("Ongeldig bericht van Family App genegeerd.")
                    continue
                if not isinstance(incoming, dict):
                    print("Onverwacht bericht van Family App genegeerd.")
                    continue
                if incoming.get("type") != "command":
                    continue
                entity = incoming.get("entity") or {}
                source = entity.get("source")
                action = incoming.get("action", "")
                if action == "link_hue_bridge":
                    try:
                        hue = adapter_map.get("hue")
                        if not hue:
                            raise RuntimeError("Hue is niet beschikbaar in deze lokale probe.")
                        value = incoming.get("value") if isinstance(incoming.get("value"), dict) else {}
                        hue.link_bridge(str(value.get("bridge") or ""))
                        save_config(config)
                        _send(ws, {"type": "command_result", "command_id": incoming.get("command_id", ""), "entity_id": "", "action": action, "succeeded": True})
                        last_inventory = 0
                    except Exception as error:
                        _send(ws, {"type": "command_result", "command_id": incoming.get("command_id", ""), "entity_id": "", "action": action, "succeeded": False, "error": _safe_error(error)})
                    continue
                adapter = adapter_map.get(source)
                if not adapter:
                    _send(
                        ws,
                        {
                            "type": "command_result",
                            "command_id": incoming.get("command_id", ""),
                            "entity_id": entity.get("id", ""),
                            "action": incoming.get("action", ""),
                            "succeeded": False,
                            "error": "Deze lokale apparaatbron wordt niet ondersteund door de probe.",
                        },
                    )
                    continue
                try:
                    adapter.control(entity.get("local_key", ""), incoming.get("action", ""), incoming.get("value"))
                    _send(ws, {"type": "command_result", "command_id": incoming.get("command_id", ""), "entity_id": entity.get("id", ""), "action": incoming.get("action", ""), "succeeded": True})
                    last_inventory = 0
                except Exception as error:
                    _send(ws, {"type": "command_result", "command_id": incoming.get("command_id", ""), "entity_id": entity.get("id", ""), "action": incoming.get("action", ""), "succeeded": False, "error": _safe_error(error)})
        except (OSError, requests.RequestException, websocket.WebSocketException) as error:
            print(f"Verbinding opnieuw proberen over {reconnect_delay:.0f}s: {_safe_error(error)}")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30.0)


def main():
    parser = argparse.ArgumentParser(description="Family App Local Probe")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pair_parser = subparsers.add_parser("pair")
    pair_parser.add_argument("--server", required=True)
    pair_parser.add_argument("--code", required=True)
    pair_parser.add_argument("--name")
    pair_parser.set_defaults(handler=pair)
    hue_parser = subparsers.add_parser("hue-link")
    hue_parser.add_argument("--bridge", required=True)
    hue_parser.set_defaults(handler=hue_link)
    nest_parser = subparsers.add_parser("nest-protect-link", help="Koppel Nest Protect met lokale Google-sessiegegevens.")
    nest_parser.add_argument("--issue-token", required=True, help="Volledige Google iframerpc Request URL uit de Nest Protect-handleiding.")
    nest_parser.set_defaults(handler=nest_protect_link)
    philips_parser = subparsers.add_parser("philips-tv-link", help="Koppel een Philips TV via lokale JointSpace-pairing.")
    philips_parser.add_argument("--host", required=True, help="Lokaal IP-adres van de Philips TV.")
    philips_parser.add_argument("--api-version", type=int, default=6, choices=(4, 5, 6))
    philips_parser.set_defaults(handler=philips_tv_link)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--once", action="store_true", help="Stuur een inventarisatie naar Family App en stop daarna.")
    run_parser.add_argument("--inventory-interval", type=float, default=25.0)
    run_parser.add_argument("--discovery-interval", type=float, default=300.0)
    run_parser.add_argument("--sonos-refresh-interval", type=float, default=2.0, help="Interval voor lokale Sonos-voortgang tijdens afspelen.")
    run_parser.set_defaults(handler=run)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
