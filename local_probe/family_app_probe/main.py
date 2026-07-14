from __future__ import annotations

import argparse
import json
import socket
import threading
import time

import requests
import websocket
import urllib3

from family_app_probe import __version__
from family_app_probe.config import load_config, save_config
from family_app_probe.discovery import discover_network
from family_app_probe.hue import HueAdapter
from family_app_probe.sonos import SonosAdapter


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def pair(args):
    response = requests.post(
        f"{args.server.rstrip('/')}/instellingen/api/lokale-probe/pair/",
        json={"code": args.code, "name": args.name or socket.gethostname(), "version": __version__},
        timeout=15,
    )
    response.raise_for_status()
    config = {"server": args.server.rstrip("/"), **response.json(), "hue": {}}
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


def _adapters(config):
    hue = HueAdapter(config.get("hue", {}))
    return [hue, SonosAdapter()]


def _send(ws, payload):
    ws.send(json.dumps(payload))


def _sync(ws, adapters, on_sonos_event=None):
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
            adapter_status[adapter.name] = {"status": "error", "error": str(error)[:180]}
    _send(ws, {"type": "heartbeat", "version": __version__, "adapters": adapter_status})
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
    last_inventory = last_discovery = 0.0
    while True:
        try:
            ws = websocket.create_connection(f"{config['websocket_url']}?token={config['token']}", timeout=20)
            ws.settimeout(1)
            print("Verbonden met Family App.")
            while True:
                now = time.monotonic()
                if now - last_inventory > args.inventory_interval or sonos_changed.is_set():
                    sonos_changed.clear()
                    _sync(ws, adapters, on_sonos_event=sonos_changed.set)
                    last_inventory = now
                if now - last_discovery > args.discovery_interval:
                    _send(ws, {"type": "discovery", "devices": discover_network()})
                    last_discovery = now
                if args.once:
                    time.sleep(0.2)
                    return
                try:
                    incoming = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if incoming.get("type") != "command":
                    continue
                entity = incoming.get("entity") or {}
                source = entity.get("source")
                adapter = adapter_map.get(source)
                if not adapter:
                    continue
                try:
                    adapter.control(entity.get("local_key", ""), incoming.get("action", ""), incoming.get("value"))
                    _send(ws, {"type": "command_result", "command_id": incoming.get("command_id", ""), "succeeded": True})
                    last_inventory = 0
                except Exception as error:
                    _send(ws, {"type": "command_result", "command_id": incoming.get("command_id", ""), "succeeded": False, "error": str(error)[:180]})
        except (OSError, requests.RequestException, websocket.WebSocketException) as error:
            print(f"Verbinding opnieuw proberen: {error}")
            time.sleep(8)


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
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--once", action="store_true", help="Voer een inventarisatie en discovery uit en stop daarna.")
    run_parser.add_argument("--inventory-interval", type=float, default=25.0)
    run_parser.add_argument("--discovery-interval", type=float, default=300.0)
    run_parser.set_defaults(handler=run)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
