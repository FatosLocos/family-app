from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import websocket
from django.db import close_old_connections
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeAssistantConfig, HomeEntity
from home.realtime import broadcast_home_entity
from integrations.crypto import decrypt


class HomeAssistantGatewayError(Exception):
    pass


@dataclass
class HomeAssistantRegistries:
    entities: dict[str, dict]
    devices: dict[str, dict]
    areas: dict[str, dict]


def websocket_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/api/websocket", "", "", ""))


def _send_command(ws, command_id: int, command_type: str, **values) -> dict:
    ws.send(json.dumps({"id": command_id, "type": command_type, **values}))
    while True:
        payload = json.loads(ws.recv())
        if payload.get("id") == command_id and payload.get("type") == "result":
            if not payload.get("success"):
                error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                raise HomeAssistantGatewayError(str(error.get("message") or f"Home Assistant weigerde {command_type}.")[:240])
            result = payload.get("result")
            return result if isinstance(result, dict) else {"items": result}


def _registry_items(result: dict) -> list[dict]:
    items = result.get("items", result)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _command_items(ws, command_id: int, command_type: str) -> tuple[int, list[dict]]:
    try:
        return command_id + 1, _registry_items(_send_command(ws, command_id, command_type))
    except HomeAssistantGatewayError:
        return command_id + 1, []


def authenticate(ws, token: str) -> None:
    try:
        greeting = json.loads(ws.recv())
    except (ValueError, websocket.WebSocketException) as error:
        raise HomeAssistantGatewayError("Home Assistant gaf geen geldige WebSocket-start.") from error
    if greeting.get("type") != "auth_required":
        raise HomeAssistantGatewayError("Home Assistant vroeg niet om authenticatie.")
    ws.send(json.dumps({"type": "auth", "access_token": token}))
    try:
        response = json.loads(ws.recv())
    except (ValueError, websocket.WebSocketException) as error:
        raise HomeAssistantGatewayError("Home Assistant gaf geen geldige authenticatiereactie.") from error
    if response.get("type") != "auth_ok":
        raise HomeAssistantGatewayError("Home Assistant WebSocket-authenticatie mislukt.")


def _connect(config: HomeAssistantConfig):
    ws = websocket.create_connection(websocket_url(config.base_url), timeout=30)
    authenticate(ws, decrypt(config.token_encrypted))
    return ws


def _area_name(area_id: str, registries: HomeAssistantRegistries) -> str:
    area = registries.areas.get(area_id)
    return str(area.get("name") or "") if area else ""


def _device_identifiers(device: dict) -> list[str]:
    identifiers = device.get("identifiers")
    values = []
    if isinstance(identifiers, list):
        for item in identifiers:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                values.append(":".join(str(part) for part in item[:2] if part))
            elif isinstance(item, str):
                values.append(item)
    return values


def _metadata_for(entity_id: str, registries: HomeAssistantRegistries) -> dict:
    entity = registries.entities.get(entity_id, {})
    device = registries.devices.get(str(entity.get("device_id") or ""), {})
    area_id = str(entity.get("area_id") or device.get("area_id") or "")
    return {
        "ha_entity_registry": entity,
        "ha_device": device,
        "ha_area": _area_name(area_id, registries),
        "ha_area_id": area_id,
        "ha_device_identifiers": _device_identifiers(device),
        "ha_device_class": str(entity.get("device_class") or ""),
        "ha_icon": str(entity.get("icon") or ""),
        "ha_platform": str(entity.get("platform") or ""),
    }


def _upsert_state(household, state: dict, registries: HomeAssistantRegistries | None = None, should_broadcast: bool = True) -> HomeEntity | None:
    entity_id = str(state.get("entity_id") or "")
    if "." not in entity_id:
        return None
    attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    registries = registries or HomeAssistantRegistries({}, {}, {})
    metadata = _metadata_for(entity_id, registries)
    merged_attributes = {
        **attributes,
        **metadata,
        "ha_last_changed": str(state.get("last_changed") or ""),
        "ha_last_updated": str(state.get("last_updated") or ""),
    }
    registry_entry = metadata["ha_entity_registry"] if isinstance(metadata["ha_entity_registry"], dict) else {}
    name = attributes.get("friendly_name") or registry_entry.get("name") or registry_entry.get("original_name") or entity_id
    entity, _ = HomeEntity.objects.update_or_create(
        household=household,
        entity_id=entity_id,
        defaults={
            "source": HomeEntity.Source.HOME_ASSISTANT,
            "domain": entity_id.split(".", 1)[0],
            "name": str(name),
            "state": str(state.get("state", "")),
            "attributes": merged_attributes,
            "is_available": state.get("state") not in {"unavailable", "unknown"},
            "is_supported": entity_id.split(".", 1)[0] in {"light", "switch", "scene", "script", "cover", "climate", "media_player"},
        },
    )
    if should_broadcast:
        broadcast_home_entity(entity)
    return entity


def load_initial_state(config: HomeAssistantConfig, ws) -> int:
    command_id = 1
    command_id, entity_registry = _command_items(ws, command_id, "config/entity_registry/list")
    command_id, device_registry = _command_items(ws, command_id, "config/device_registry/list")
    command_id, area_registry = _command_items(ws, command_id, "config/area_registry/list")
    states_result = _send_command(ws, command_id, "get_states")
    states = _registry_items(states_result)
    registries = HomeAssistantRegistries(
        entities={str(item.get("entity_id")): item for item in entity_registry if item.get("entity_id")},
        devices={str(item.get("id")): item for item in device_registry if item.get("id")},
        areas={str(item.get("area_id") or item.get("id")): item for item in area_registry if item.get("area_id") or item.get("id")},
    )
    with household_db_scope(config.household_id):
        seen = set()
        for state in states:
            entity = _upsert_state(config.household, state, registries, should_broadcast=False)
            if entity:
                seen.add(entity.entity_id)
        HomeEntity.objects.filter(household=config.household, source=HomeEntity.Source.HOME_ASSISTANT).exclude(entity_id__in=seen).update(is_available=False)
        config.last_sync_at, config.last_error = timezone.now(), ""
        config.save(update_fields=["last_sync_at", "last_error", "updated_at"])
    return len(seen)


def apply_state_changed(config: HomeAssistantConfig, event: dict) -> HomeEntity | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    new_state = data.get("new_state") if isinstance(data.get("new_state"), dict) else None
    if not new_state:
        return None
    with household_db_scope(config.household_id):
        entity = _upsert_state(config.household, new_state)
        config.last_sync_at, config.last_error = timezone.now(), ""
        config.save(update_fields=["last_sync_at", "last_error", "updated_at"])
        return entity


def sync_once(config: HomeAssistantConfig) -> int:
    ws = _connect(config)
    try:
        return load_initial_state(config, ws)
    finally:
        ws.close()


def listen_forever(config: HomeAssistantConfig, stop_event: threading.Event | None = None) -> None:
    stop_event = stop_event or threading.Event()
    backoff = 2
    while not stop_event.is_set():
        close_old_connections()
        try:
            with household_db_scope(config.household_id):
                config.refresh_from_db()
            ws = _connect(config)
            load_initial_state(config, ws)
            command_id = 10_000
            _send_command(ws, command_id, "subscribe_events", event_type="state_changed")
            ws.settimeout(5)
            backoff = 2
            while not stop_event.is_set():
                close_old_connections()
                try:
                    payload = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if payload.get("type") == "event" and isinstance(payload.get("event"), dict):
                    apply_state_changed(config, payload["event"])
        except Exception as error:
            with household_db_scope(config.household_id):
                config.last_error = str(error)[:300]
                config.save(update_fields=["last_error", "updated_at"])
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
