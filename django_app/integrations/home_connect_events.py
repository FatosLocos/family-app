"""Home Connect Server-Sent Events listener.

The normal periodic sync remains the recovery path. This module only turns a
confirmed event from Home Connect into an immediate, authoritative resync.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterable, Iterator

import requests
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeEntity
from home.realtime import broadcast_home_entity
from integrations.models import IntegrationConnection
from integrations.providers import ProviderError, _home_connect_event_label, _home_connect_label, _refresh_connection_token, sync_home_connect
from integrations.services import HOME_CONNECT_OAUTH_TOKEN_URL

logger = logging.getLogger(__name__)

HOME_CONNECT_EVENTS_URL = "https://api.home-connect.com/api/homeappliances/events"


class HomeConnectEventError(Exception):
    pass


def parse_sse_events(lines: Iterable[bytes | str]) -> Iterator[dict]:
    """Parse a small, standards-compatible subset of an SSE response."""
    fields: dict[str, list[str] | str] = {"data": []}
    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r")
        if not line:
            data = "\n".join(fields["data"])
            event_type = str(fields.get("event") or "message")
            if event_type != "KEEP-ALIVE" and data:
                try:
                    payload = json.loads(data)
                except ValueError:
                    payload = {"raw": data}
                yield {"event": event_type, "id": str(fields.get("id") or ""), "data": payload}
            fields = {"data": []}
            continue
        if line.startswith(":") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.lstrip(" ")
        if key == "data":
            fields["data"].append(value)
        elif key in {"event", "id"}:
            fields[key] = value

    data = "\n".join(fields["data"])
    event_type = str(fields.get("event") or "message")
    if event_type != "KEEP-ALIVE" and data:
        try:
            payload = json.loads(data)
        except ValueError:
            payload = {"raw": data}
        yield {"event": event_type, "id": str(fields.get("id") or ""), "data": payload}


def _set_event_status(connection: IntegrationConnection, status: str, detail: str = "", *, received: bool = False) -> None:
    settings = dict(connection.settings) if isinstance(connection.settings, dict) else {}
    settings["home_connect_events_status"] = status
    settings["home_connect_events_error"] = detail[:240]
    if received:
        settings["home_connect_events_last_at"] = timezone.now().isoformat()
    connection.settings = settings
    connection.save(update_fields=["settings", "updated_at"])


def _event_summary(event: dict) -> str:
    event_type = str(event.get("event") or "").upper()
    payload = event.get("data") if isinstance(event.get("data"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    key = str(data.get("key") or "")
    if event_type == "CONNECTED":
        return "Apparaat verbonden"
    if event_type == "DISCONNECTED":
        return "Apparaat niet verbonden"
    if event_type == "EVENT" and key:
        return _home_connect_event_label(key)
    if event_type in {"STATUS", "NOTIFY"} and key:
        value = data.get("value")
        return f"{_home_connect_label(key)}: {_home_connect_label(value)}"
    return "Home Connect-status bijgewerkt"


def _record_event(connection: IntegrationConnection, event: dict) -> None:
    appliance_id = str(event.get("id") or "")
    if not appliance_id:
        return
    entity = HomeEntity.objects.for_household(connection.household).filter(
        connection=connection,
        source=HomeEntity.Source.HOME_CONNECT,
        attributes__home_connect_id=appliance_id,
    ).first()
    if not entity:
        return
    attributes = dict(entity.attributes) if isinstance(entity.attributes, dict) else {}
    attributes["home_connect_last_event"] = _event_summary(event)
    attributes["home_connect_last_event_at"] = timezone.now().isoformat()
    attributes["home_connect_last_event_type"] = str(event.get("event") or "").upper()
    entity.attributes = attributes
    entity.save(update_fields=["attributes", "last_seen_at"])
    broadcast_home_entity(entity)


def listen_home_connect_events_once(connection: IntegrationConnection, stop_event: threading.Event | None = None) -> dict:
    """Consume one HTTP event stream until it closes and refresh on each event."""
    stop_event = stop_event or threading.Event()
    with household_db_scope(connection.household_id):
        try:
            token = _refresh_connection_token(connection, "Home Connect", HOME_CONNECT_OAUTH_TOKEN_URL)
            response = requests.get(
                HOME_CONNECT_EVENTS_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "text/event-stream",
                    "Accept-Language": "nl-NL",
                },
                stream=True,
                timeout=(15, 70),
            )
        except (requests.RequestException, ProviderError) as error:
            raise HomeConnectEventError("Home Connect-eventstream is tijdelijk niet bereikbaar.") from error

        if not getattr(response, "ok", False):
            raise HomeConnectEventError("Home Connect accepteerde de eventverbinding niet. Controleer de koppeling.")

        _set_event_status(connection, "active")
        events = 0
        try:
            for event in parse_sse_events(response.iter_lines(decode_unicode=True)):
                if stop_event.is_set():
                    break
                # A Home Connect event only describes a changed property. A
                # regular sync keeps program data and controls consistent too.
                sync_home_connect(connection)
                _record_event(connection, event)
                events += 1
                _set_event_status(connection, "active", received=True)
        except (requests.RequestException, ProviderError) as error:
            raise HomeConnectEventError("Home Connect-eventstream is onderbroken.") from error
        finally:
            response.close()
        return {"events": events}


def listen_home_connect_events_forever(connection: IntegrationConnection, stop_event: threading.Event, reconnect_delay: float = 5.0) -> None:
    """Keep a connection open with bounded retry delay; suitable for one service."""
    while not stop_event.is_set():
        try:
            listen_home_connect_events_once(connection, stop_event)
        except HomeConnectEventError as error:
            with household_db_scope(connection.household_id):
                _set_event_status(connection, "error", str(error))
            logger.warning("Home Connect-events mislukt voor koppeling %s: %s", connection.id, error)
        stop_event.wait(reconnect_delay)
