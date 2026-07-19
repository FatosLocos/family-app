from __future__ import annotations

import base64
import email
import imaplib
import json
import os
import smtplib
import time
import uuid
from email.header import decode_header
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from datetime import timedelta
from decimal import Decimal

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.utils import timezone

from finance.models import BankAccount, BankConnection, Transaction
from home.models import HomeEntity
from integrations.crypto import decrypt, encrypt
from integrations.models import IntegrationConnection
from notifications.models import Notification
from planning.models import CalendarEvent, CalendarSource


class ProviderError(Exception):
    pass


class HueProviderError(ProviderError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    max_retries = 3
    base_delay = 1
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    retry_after = int(response.headers.get("Retry-After", base_delay * (2 ** attempt)))
                    time.sleep(retry_after)
                    continue
            return response
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    return response


def _go2rtc_stream_name(household_id: int, entity_id: int) -> str:
    """Generate per-household/entity stream name for isolation."""
    return f"family-app-{household_id}-{entity_id}"


def _go2rtc_mjpeg_stream_name(household_id: int, entity_id: int) -> str:
    """Generate per-household/entity MJPEG stream name for isolation."""
    return f"family-app-{household_id}-{entity_id}-mjpeg"

HOME_CONNECT_EVENT_LABELS = {
    "Dishcare.Dishwasher.Event.SaltLack": "Zout bijvullen",
    "Dishcare.Dishwasher.Event.RinseAidLack": "Glansspoelmiddel bijvullen",
    "Dishcare.Dishwasher.Event.ProgramBlockedSaltLack": "Programma geblokkeerd: zout bijvullen",
    "Dishcare.Dishwasher.Event.MachineCareReminder": "Machine Care uitvoeren",
    "ConsumerProducts.CoffeeMaker.Event.BeanContainerEmpty": "Bonenreservoir is leeg",
    "ConsumerProducts.CoffeeMaker.Event.WaterTankEmpty": "Waterreservoir is leeg",
    "ConsumerProducts.CoffeeMaker.Event.DeviceShouldBeDescaled": "Koffiemachine ontkalken",
    "ConsumerProducts.CoffeeMaker.Event.DeviceShouldBeCleaned": "Koffiemachine reinigen",
}

HOME_CONNECT_VALUE_LABELS = {
    "BSH.Common.EnumType.OperationState.Run": "Bezig",
    "BSH.Common.EnumType.OperationState.Pause": "Gepauzeerd",
    "BSH.Common.EnumType.OperationState.Finished": "Klaar",
    "BSH.Common.EnumType.OperationState.Inactive": "Inactief",
    "BSH.Common.EnumType.OperationState.Ready": "Gereed",
    "BSH.Common.EnumType.OperationState.DelayedStart": "Gepland",
    "Dishcare.Dishwasher.Program.Intensiv70": "Intensief 70 °C",
    "Dishcare.Dishwasher.Program.Auto2": "Auto",
    "Dishcare.Dishwasher.Program.Eco50": "Eco 50 °C",
    "Dishcare.Dishwasher.Program.Quick45": "Snel 45 °C",
    "Dishcare.Dishwasher.Program.Quick65": "Snel 65 °C",
    "Dishcare.Dishwasher.Program.Kurz60": "Kort 60 °C",
    "Dishcare.Dishwasher.Program.PreRinse": "Voorspoelen",
    "Dishcare.Dishwasher.Program.MachineCare": "Machine Care",
}

HOME_CONNECT_APPLIANCE_LABELS = {
    "dishwasher": "Vaatwasser",
    "coffee_maker": "Koffiemachine",
    "refrigerator": "Koelkast",
    "washer": "Wasmachine",
    "dryer": "Droger",
    "oven": "Oven",
    "hood": "Afzuigkap",
    "appliance": "Apparaat",
}


def _go2rtc_api_url() -> str:
    return os.environ.get("GO2RTC_API_URL", "http://127.0.0.1:1984").rstrip("/")


def _safe_response_json(response, provider: str) -> dict:
    """Return a provider response without leaking implementation details to the UI."""
    try:
        payload = response.json() if response.content else {}
    except ValueError as error:
        raise ProviderError(f"{provider} gaf geen geldige reactie.") from error
    if response.ok:
        return payload if isinstance(payload, dict) else {}

    if response.status_code == 429:
        raise ProviderError(f"{provider} heeft te veel aanvragen ontvangen. Probeer het later opnieuw.")

    if provider == "Outlook":
        message = payload.get("error", {}).get("message") if isinstance(payload.get("error"), dict) else payload.get("error_description")
    else:
        message = next(
            (
                item.get("error_description_translated") or item.get("error_description")
                for item in payload.get("Error", [])
                if isinstance(item, dict)
            ),
            None,
        )
    raise ProviderError(str(message or f"{provider} kon de aanvraag niet uitvoeren.")[:240])


def _parse_graph_datetime(value: dict) -> timezone.datetime:
    raw = value.get("dateTime", "")
    if not raw:
        raise ProviderError("Outlook leverde een afspraak zonder datum op.")
    try:
        parsed = timezone.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProviderError("Outlook leverde een ongeldige afspraakdatum op.") from error
    return timezone.make_aware(parsed, timezone.get_current_timezone()) if timezone.is_naive(parsed) else parsed


def _stored_outlook_token_is_current(settings: dict) -> bool:
    expires_at = settings.get("expires_at", "")
    if not settings.get("access_token") or not expires_at:
        return False
    try:
        expires = timezone.datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return False
    if timezone.is_naive(expires):
        expires = timezone.make_aware(expires, timezone.get_current_timezone())
    return expires > timezone.now() + timedelta(seconds=45)


def sync_connection(connection: IntegrationConnection) -> dict:
    if connection.provider == "outlook":
        return sync_outlook(connection)
    if connection.provider == "bunq":
        return sync_bunq(connection)
    if connection.provider == "hue":
        return sync_hue(connection)
    if connection.provider == "sonos":
        return sync_sonos(connection)
    if connection.provider == "spotify":
        return sync_spotify(connection)
    if connection.provider == "smartcar":
        return sync_smartcar(connection)
    if connection.provider == "google_home":
        return sync_google_home(connection)
    if connection.provider == "lg_thinq":
        return sync_lg_thinq(connection)
    if connection.provider == "home_connect":
        return sync_home_connect(connection)
    raise ProviderError("Onbekende koppeling.")


def _stored_token_is_current(data: dict) -> bool:
    expires_at = data.get("expires_at", "")
    if not data.get("access_token") or not expires_at:
        return False
    try:
        expires = timezone.datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return False
    if timezone.is_naive(expires):
        expires = timezone.make_aware(expires, timezone.get_current_timezone())
    return expires > timezone.now() + timedelta(seconds=45)


def _oauth_response(response, provider: str) -> dict:
    try:
        payload = response.json() if response.content else {}
    except ValueError as error:
        raise ProviderError(f"{provider} gaf geen geldige reactie.") from error
    if response.status_code == 429:
        raise ProviderError(f"{provider} heeft te veel aanvragen ontvangen. Probeer het later opnieuw.")
    if not response.ok or not isinstance(payload, dict):
        message = payload.get("error_description") or payload.get("error") if isinstance(payload, dict) else ""
        raise ProviderError(str(message or f"{provider} weigerde de aanvraag.")[:240])
    return payload


def _refresh_connection_token(connection: IntegrationConnection, provider: str, token_url: str) -> str:
    from django.db import transaction
    from cryptography.fernet import InvalidToken

    with transaction.atomic():
        connection = IntegrationConnection.objects.select_for_update().get(pk=connection.pk)
        data = dict(connection.settings) if isinstance(connection.settings, dict) else {}
        if _stored_token_is_current(data):
            try:
                return decrypt(data["access_token"])
            except InvalidToken:
                connection.status = "needs_reauth"
                connection.last_error = "Encryptie-sleutel is vernieuwd. Herauriseer de koppeling."
                connection.save(update_fields=["status", "last_error", "updated_at"])
                raise ProviderError(connection.last_error)
        try:
            refresh_token = decrypt(connection.secret_encrypted) if connection.secret_encrypted else ""
        except InvalidToken:
            connection.status = "needs_reauth"
            connection.last_error = "Encryptie-sleutel is vernieuwd. Herauriseer de koppeling."
            connection.save(update_fields=["status", "last_error", "updated_at"])
            raise ProviderError(connection.last_error)
        if not refresh_token:
            raise ProviderError(f"{provider} moet opnieuw worden geautoriseerd.")
        from integrations.services import get_app_config

        client_id, client_secret, _ = get_app_config(connection.household, connection.provider)
        if not client_id or not client_secret:
            raise ProviderError(f"{provider}-clientgegevens ontbreken.")
        response = requests.post(token_url, data={"grant_type": "refresh_token", "refresh_token": refresh_token}, auth=(client_id, client_secret), timeout=20)
        payload = _oauth_response(response, provider)
        if not payload.get("access_token"):
            raise ProviderError(f"{provider}-token vernieuwen mislukt.")
        if payload.get("refresh_token"):
            connection.secret_encrypted = encrypt(payload["refresh_token"])
        data["access_token"] = encrypt(payload["access_token"])
        data["expires_at"] = (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat()
        connection.settings = data
        connection.save(update_fields=["secret_encrypted", "settings", "updated_at"])
        return payload["access_token"]


def _sonos_request(connection: IntegrationConnection, method: str, path: str, payload: dict | None = None) -> dict:
    from integrations.services import SONOS_OAUTH_TOKEN_URL

    token = _refresh_connection_token(connection, "Sonos", SONOS_OAUTH_TOKEN_URL)
    try:
        response = requests.request(method, f"https://api.ws.sonos.com/control/api/v1{path}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=20)
    except requests.RequestException as error:
        raise ProviderError("Sonos is tijdelijk niet bereikbaar.") from error
    return _oauth_response(response, "Sonos")


def _spotify_request(connection: IntegrationConnection, method: str, path: str, *, params: dict | None = None, payload: dict | None = None, allow_empty: bool = False):
    from integrations.services import SPOTIFY_OAUTH_TOKEN_URL

    token = _refresh_connection_token(connection, "Spotify", SPOTIFY_OAUTH_TOKEN_URL)
    try:
        response = requests.request(method, f"https://api.spotify.com/v1{path}", headers={"Authorization": f"Bearer {token}"}, params=params, json=payload, timeout=20)
    except requests.RequestException as error:
        raise ProviderError("Spotify is tijdelijk niet bereikbaar.") from error
    if getattr(response, "status_code", None) == 204 and allow_empty:
        return {}
    return _oauth_response(response, "Spotify")


def _spotify_track_attributes(playback: dict) -> dict:
    item = playback.get("item") if isinstance(playback.get("item"), dict) else {}
    artists = item.get("artists") if isinstance(item.get("artists"), list) else []
    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    images = album.get("images") if isinstance(album.get("images"), list) else []
    return {
        "spotify_is_playing": bool(playback.get("is_playing")),
        "spotify_track_name": str(item.get("name") or ""),
        "spotify_track_artist": ", ".join(str(artist.get("name") or "") for artist in artists if isinstance(artist, dict) and artist.get("name")),
        "spotify_track_album": str(album.get("name") or ""),
        "spotify_track_artwork": str((images[0] if images and isinstance(images[0], dict) else {}).get("url") or ""),
        "spotify_progress_ms": playback.get("progress_ms"),
        "spotify_duration_ms": item.get("duration_ms"),
        "spotify_shuffle": bool(playback.get("shuffle_state")),
        "spotify_repeat": str(playback.get("repeat_state") or "off"),
        "spotify_context_uri": str((playback.get("context") or {}).get("uri") or "") if isinstance(playback.get("context"), dict) else "",
    }


def sync_spotify(connection: IntegrationConnection) -> dict:
    devices_response = _spotify_request(connection, "GET", "/me/player/devices")
    devices = devices_response.get("devices") if isinstance(devices_response.get("devices"), list) else []
    try:
        playback = _spotify_request(connection, "GET", "/me/player", allow_empty=True)
    except ProviderError:
        playback = {}
    active_device = playback.get("device") if isinstance(playback.get("device"), dict) else {}
    playlists_response = _spotify_request(connection, "GET", "/me/playlists", params={"limit": 20}, allow_empty=True)
    playlists = playlists_response.get("items") if isinstance(playlists_response.get("items"), list) else []
    playlist_items = [
        {"name": str(item.get("name") or "Playlist"), "uri": str(item.get("uri") or ""), "image": str(((item.get("images") or [{}])[0] or {}).get("url") or "")}
        for item in playlists if isinstance(item, dict) and item.get("uri")
    ]
    seen = set()
    for device in devices:
        if not isinstance(device, dict) or not device.get("id"):
            continue
        device_id = str(device["id"])
        is_active = bool(device.get("is_active")) or str(active_device.get("id") or "") == device_id
        attributes = {
            "spotify_device_id": device_id,
            "spotify_device_type": str(device.get("type") or "apparaat"),
            "spotify_device_name": str(device.get("name") or "Spotify Connect-apparaat"),
            "spotify_volume": (device.get("volume_percent") if isinstance(device.get("volume_percent"), int) else None),
            "spotify_is_active": is_active,
            "spotify_is_restricted": bool(device.get("is_restricted")),
            "spotify_supports_volume": device.get("volume_percent") is not None,
            "spotify_playlists": playlist_items if is_active else [],
        }
        if is_active:
            attributes.update(_spotify_track_attributes(playback))
        entity_id = f"spotify.{connection.id}.{device_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.SPOTIFY,
                "domain": "media_player",
                "name": str(device.get("name") or "Spotify Connect"),
                "state": "on" if is_active and bool(playback.get("is_playing")) else "off",
                "attributes": attributes,
                "is_available": True,
                "is_supported": not bool(device.get("is_restricted")),
            },
        )
        seen.add(entity_id)
    HomeEntity.objects.for_household(connection.household).filter(source=HomeEntity.Source.SPOTIFY, connection=connection).exclude(entity_id__in=seen).update(is_available=False)
    return {"devices": len(seen)}


def _home_connect_request(connection: IntegrationConnection, method: str, path: str, *, payload: dict | None = None, allow_empty: bool = False) -> dict:
    from integrations.services import HOME_CONNECT_OAUTH_TOKEN_URL

    token = _refresh_connection_token(connection, "Home Connect", HOME_CONNECT_OAUTH_TOKEN_URL)
    try:
        response = _request_with_retry(method, f"https://api.home-connect.com/api{path}", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.bsh.sdk.v1+json", "Content-Type": "application/vnd.bsh.sdk.v1+json"}, json=payload, timeout=20)
    except requests.RequestException as error:
        raise ProviderError("Home Connect is tijdelijk niet bereikbaar.") from error
    if allow_empty and getattr(response, "status_code", 200) in {204, 404, 409}:
        return {}
    return _oauth_response(response, "Home Connect")


def _home_connect_collection(payload: dict, key: str) -> list[dict]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return [item for item in data[key] if isinstance(item, dict)]
    return []


def _home_connect_values(payload: dict) -> dict:
    values = _home_connect_collection(payload, "status")
    return {str(item.get("key") or ""): item.get("value") for item in values if isinstance(item, dict) and item.get("key")}


def _home_connect_state(value: str) -> str:
    state = value.rsplit(".", 1)[-1].lower()
    return {"run": "running", "pause": "paused", "finished": "finished", "inactive": "idle", "ready": "ready"}.get(state, state or "unknown")


def _home_connect_label(value) -> str:
    raw = str(value or "")
    return HOME_CONNECT_VALUE_LABELS.get(raw, raw.rsplit(".", 1)[-1].replace("_", " "))


def _home_connect_event_label(key: str) -> str:
    return HOME_CONNECT_EVENT_LABELS.get(key, _home_connect_label(key))


def _home_connect_duration(seconds) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return ""
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}u {minutes:02d}m"
    return f"{minutes} min"


def _home_connect_appliance_meta(appliance_type: str) -> tuple[str, str]:
    normalized = appliance_type.lower()
    for needle, domain, icon in (
        ("dishwasher", "dishwasher", "dishwasher"),
        ("coffeemaker", "coffee_maker", "coffee"),
        ("coffee maker", "coffee_maker", "coffee"),
        ("fridge", "refrigerator", "refrigerator"),
        ("refrigerator", "refrigerator", "refrigerator"),
        ("freezer", "refrigerator", "refrigerator"),
        ("washerdryer", "washer", "washing-machine"),
        ("washer", "washer", "washing-machine"),
        ("dryer", "dryer", "shirt"),
        ("oven", "oven", "cooking-pot"),
        ("hood", "hood", "fan"),
    ):
        if needle in normalized:
            return domain, icon
    return "appliance", "plug"


def _home_connect_display_name(appliance: dict, appliance_domain: str) -> tuple[str, str]:
    """Use a recognisable device label while retaining Home Connect's custom name."""
    brand = str(appliance.get("brand") or "").strip()
    custom_name = str(appliance.get("name") or "").strip()
    type_label = HOME_CONNECT_APPLIANCE_LABELS.get(appliance_domain, "Apparaat")
    label = " ".join(part for part in (brand, type_label.lower()) if part).strip()
    return label or custom_name or type_label, custom_name


def _home_connect_programs(payload: dict) -> list[dict]:
    values = _home_connect_collection(payload, "programs")
    programs = []
    for item in values:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        options = []
        for option in item.get("options") or []:
            if not isinstance(option, dict) or not option.get("key") or "value" not in option:
                continue
            options.append({"key": str(option["key"]), "value": option["value"], "label": _home_connect_label(option["key"])})
        programs.append({"key": str(item["key"]), "label": _home_connect_label(item["key"]), "options": options})
    return programs


def _home_connect_commands(payload: dict) -> set[str]:
    values = _home_connect_collection(payload, "commands")
    return {str(item.get("key")) for item in values if isinstance(item, dict) and item.get("key")}


def _home_connect_appliances(payload: dict) -> list[dict]:
    """Handle Home Connect's documented data.homeappliances response shape."""
    return _home_connect_collection(payload, "homeappliances")


def _home_connect_active_program(payload: dict) -> dict:
    data = payload.get("data")
    if isinstance(data, dict):
        active = data.get("active")
        if isinstance(active, dict):
            return active
        if data.get("key"):
            return data
    return {}


def _home_connect_selected_program(payload: dict) -> dict:
    data = payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("selected"), dict):
            return data["selected"]
        if data.get("key"):
            return data
    return {}


def _home_connect_program_forecasts(program: dict) -> dict[str, int]:
    forecasts = {}
    labels = {
        "BSH.Common.Option.EnergyForecast": "energy",
        "BSH.Common.Option.WaterForecast": "water",
    }
    for option in program.get("options") or []:
        if not isinstance(option, dict):
            continue
        label = labels.get(str(option.get("key") or ""))
        value = option.get("value")
        if label and isinstance(value, (int, float)):
            forecasts[label] = max(0, min(100, round(value)))
    return forecasts


def _home_connect_door_label(value) -> str:
    normalized = str(value or "").lower()
    if normalized.endswith(".open") or normalized == "open":
        return "Deur open"
    if normalized.endswith(".closed") or normalized == "closed":
        return "Deur gesloten"
    return ""


def _home_connect_progress(value) -> int | None:
    if not isinstance(value, (int, float)):
        return None
    return max(0, min(100, round(float(value))))


def _home_connect_start_status(appliance: dict, values: dict) -> tuple[bool, str]:
    """Evaluate the documented preconditions for starting a Home Connect program."""
    if not bool(appliance.get("connected", False)):
        return False, "Het apparaat is niet verbonden."
    if values.get("BSH.Common.Status.RemoteControlActive") is not True:
        return False, "Bediening op afstand staat uit op het apparaat."
    remote_start_allowed = (
        values.get("BSH.Common.Status.RemoteControlStartAllowed") is True
        or values.get("BSH.Common.Status.RemoteStartAllowed") is True
    )
    if not remote_start_allowed:
        return False, "Remote Start staat uit op het apparaat."
    if values.get("BSH.Common.Status.LocalControlActive") is True:
        return False, "Het apparaat wordt lokaal bediend."
    operation = str(values.get("BSH.Common.Status.OperationState") or "")
    if _home_connect_state(operation) != "ready":
        return False, "Het apparaat is nog niet klaar om te starten."
    return True, "Klaar om een programma te starten."


def sync_home_connect(connection: IntegrationConnection) -> dict:
    payload = _home_connect_request(connection, "GET", "/homeappliances")
    appliances = _home_connect_appliances(payload)
    seen = set()
    for appliance in appliances:
        if not isinstance(appliance, dict) or not appliance.get("haId"):
            continue
        appliance_id = str(appliance["haId"])
        values = _home_connect_values(_home_connect_request(connection, "GET", f"/homeappliances/{appliance_id}/status", allow_empty=True))
        active = _home_connect_active_program(_home_connect_request(connection, "GET", f"/homeappliances/{appliance_id}/programs/active", allow_empty=True))
        available_programs = _home_connect_request(connection, "GET", f"/homeappliances/{appliance_id}/programs/available", allow_empty=True)
        programs = _home_connect_programs(available_programs)
        # The selected program is a separate Home Connect resource. It carries
        # the current option values (including energy and water forecasts).
        selected = _home_connect_selected_program(
            _home_connect_request(connection, "GET", f"/homeappliances/{appliance_id}/programs/selected", allow_empty=True)
        )
        commands = _home_connect_commands(_home_connect_request(connection, "GET", f"/homeappliances/{appliance_id}/commands", allow_empty=True))
        appliance_type = str(appliance.get("type") or "Home Connect-apparaat")
        appliance_domain, appliance_icon = _home_connect_appliance_meta(appliance_type)
        display_name, custom_name = _home_connect_display_name(appliance, appliance_domain)
        operation = str(values.get("BSH.Common.Status.OperationState") or "")
        can_start, start_status = _home_connect_start_status(appliance, values)
        remaining = values.get("BSH.Common.Option.RemainingProgramTime")
        progress = _home_connect_progress(values.get("BSH.Common.Option.ProgramProgress"))
        event_values = {
            key: _home_connect_event_label(key)
            for key, value in values.items()
            if ".Event." in key and value not in {False, "BSH.Common.EnumType.EventStatus.Inactive"}
        }
        entity_id = f"home_connect.{connection.id}.{appliance_id}"
        previous = HomeEntity.objects.for_household(connection.household).filter(entity_id=entity_id).first()
        previous_state = previous.state if previous else ""
        previous_events = previous.attributes.get("home_connect_events", {}) if previous and isinstance(previous.attributes, dict) else {}
        entity, _ = HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.HOME_CONNECT,
                "domain": appliance_domain,
                "name": display_name,
                "state": _home_connect_state(operation),
                "attributes": {
                    "home_connect_id": appliance_id,
                    "home_connect_type": appliance_type,
                    "home_connect_type_label": HOME_CONNECT_APPLIANCE_LABELS.get(appliance_domain, "Apparaat"),
                    "home_connect_icon": appliance_icon,
                    "home_connect_brand": str(appliance.get("brand") or ""),
                    "home_connect_model": str(appliance.get("enumber") or appliance.get("vib") or ""),
                    "home_connect_custom_name": custom_name,
                    "home_connect_connected": bool(appliance.get("connected", False)),
                    "home_connect_operation": _home_connect_label(operation),
                    "home_connect_program": _home_connect_label(active.get("key")) if isinstance(active, dict) else "",
                    "home_connect_selected_program_key": str(selected.get("key") or ""),
                    "home_connect_selected_program": _home_connect_label(selected.get("key")) if selected else "",
                    "home_connect_program_forecasts": _home_connect_program_forecasts(selected),
                    "home_connect_remaining_seconds": remaining if isinstance(remaining, (int, float)) else None,
                    "home_connect_remaining_label": _home_connect_duration(remaining),
                    "home_connect_program_progress": progress,
                    "home_connect_door_label": _home_connect_door_label(values.get("BSH.Common.Status.DoorState")),
                    "home_connect_remote_control": values.get("BSH.Common.Status.RemoteControlActive") is True,
                    # Home Connect v1 exposes RemoteControlStartAllowed. Keep the
                    # older key as a compatibility fallback for older appliance APIs.
                    "home_connect_remote_start": (
                        values.get("BSH.Common.Status.RemoteControlStartAllowed") is True
                        or values.get("BSH.Common.Status.RemoteStartAllowed") is True
                    ),
                    "home_connect_local_control": values.get("BSH.Common.Status.LocalControlActive") is True,
                    "home_connect_can_start": can_start,
                    "home_connect_start_status": start_status,
                    "home_connect_events": event_values,
                    "home_connect_programs": programs,
                    "home_connect_can_pause": "BSH.Common.Command.PauseProgram" in commands,
                    "home_connect_can_resume": "BSH.Common.Command.ResumeProgram" in commands,
                    "home_connect_can_stop": _home_connect_state(operation) in {"running", "paused"},
                    "home_connect_can_select_program": bool(appliance.get("connected", False)) and _home_connect_state(operation) in {"idle", "ready"} and bool(programs),
                },
                "is_available": bool(appliance.get("connected", False)),
                "is_supported": bool(appliance.get("connected", False)) and (bool(programs) or bool(commands)),
            },
        )
        if not previous or previous_state != entity.state or previous.attributes != entity.attributes or previous.is_available != entity.is_available:
            from home.realtime import broadcast_home_entity

            broadcast_home_entity(entity)
        if previous and previous_state != "finished" and entity.state == "finished":
            program_name = str(entity.attributes.get("home_connect_program") or "Programma")
            Notification.objects.get_or_create(
                household=connection.household,
                dedupe_key=f"home-connect-finished:{entity.id}:{program_name}:{timezone.localdate().isoformat()}",
                defaults={
                    "title": f"{entity.name} is klaar",
                    "body": program_name,
                    "kind": "info",
                    "action_url": "/huis/?source=home_connect",
                },
            )
        for event_key, event_label in event_values.items():
            if previous_events.get(event_key) == event_label:
                continue
            Notification.objects.get_or_create(
                household=connection.household,
                dedupe_key=f"home-connect-event:{entity.id}:{event_key}:{event_label}",
                defaults={
                    "title": f"{entity.name}: aandacht nodig",
                    "body": event_label,
                    "kind": "warning",
                    "action_url": "/huis/?source=home_connect",
                },
            )
        seen.add(entity_id)
    HomeEntity.objects.for_household(connection.household).filter(source=HomeEntity.Source.HOME_CONNECT, connection=connection).exclude(entity_id__in=seen).update(is_available=False)
    return {"devices": len(seen)}


def _smartcar_access_token(connection: IntegrationConnection) -> str:
    from integrations.services import get_app_config

    client_id, client_secret, _ = get_app_config(connection.household, "smartcar")
    if not client_id or not client_secret:
        raise ProviderError("Smartcar-clientgegevens ontbreken.")
    data = dict(connection.settings) if isinstance(connection.settings, dict) else {}
    if _stored_token_is_current(data):
        return decrypt(data["access_token"])
    try:
        response = requests.post(
            "https://iam.smartcar.com/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=20,
        )
    except requests.RequestException as error:
        raise ProviderError("Smartcar is tijdelijk niet bereikbaar.") from error
    payload = _oauth_response(response, "Smartcar")
    token = str(payload.get("access_token") or "")
    if not token:
        raise ProviderError("Smartcar gaf geen toegangstoken terug.")
    data["access_token"] = encrypt(token)
    data["expires_at"] = (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat()
    connection.settings = data
    connection.save(update_fields=["settings", "updated_at"])
    return token


def _smartcar_request(connection: IntegrationConnection, method: str, path: str, payload: dict | None = None) -> dict:
    data = connection.settings if isinstance(connection.settings, dict) else {}
    user_id = str(data.get("smartcar_user_id") or "")
    if not user_id:
        raise ProviderError("Smartcar moet opnieuw worden geautoriseerd.")
    try:
        response = requests.request(
            method,
            f"https://vehicle.api.smartcar.com/v3{path}",
            headers={"Authorization": f"Bearer {_smartcar_access_token(connection)}", "sc-user-id": user_id},
            json=payload,
            timeout=25,
        )
    except requests.RequestException as error:
        raise ProviderError("Smartcar is tijdelijk niet bereikbaar.") from error
    return _oauth_response(response, "Smartcar")


def _smartcar_signal_values(payload: dict) -> tuple[dict, set[str]]:
    values, codes = {}, set()
    for item in payload.get("data", []) if isinstance(payload.get("data"), list) else []:
        if not isinstance(item, dict):
            continue
        attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        code = str(attributes.get("code") or "")
        body = attributes.get("body") if isinstance(attributes.get("body"), dict) else {}
        if code:
            codes.add(code)
            values[code] = body
    return values, codes


def _smartcar_readings(payload: dict) -> list[dict]:
    readings = []
    for item in payload.get("data", []) if isinstance(payload.get("data"), list) else []:
        if not isinstance(item, dict):
            continue
        attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        body = attributes.get("body") if isinstance(attributes.get("body"), dict) else {}
        value = body.get("value")
        if value is None:
            continue
        label = str(attributes.get("name") or attributes.get("code") or "Signaal")
        unit = str(body.get("unit") or "")
        readings.append({"label": label, "value": str(value), "unit": unit})
    return readings[:12]


def sync_smartcar(connection: IntegrationConnection) -> dict:
    from integrations.services import get_app_config

    _, _, app_config = get_app_config(connection.household, "smartcar")
    controls_enabled = bool(app_config.get("allow_remote_controls"))
    connections = _smartcar_request(connection, "GET", "/connections")
    rows = connections.get("connections") if isinstance(connections.get("connections"), list) else connections.get("data") if isinstance(connections.get("data"), list) else []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        relationships = row.get("relationships") if isinstance(row.get("relationships"), dict) else {}
        vehicle_relationship = relationships.get("vehicle") if isinstance(relationships.get("vehicle"), dict) else {}
        vehicle_reference = vehicle_relationship.get("data") if isinstance(vehicle_relationship.get("data"), dict) else {}
        # V3 returns a connection id as row.id; the actual vehicle id lives in
        # relationships.vehicle.data.id. Older responses expose vehicleId directly.
        vehicle_id = str(row.get("vehicleId") or row.get("vehicle_id") or vehicle_reference.get("id") or "")
        if not vehicle_id:
            continue
        try:
            vehicle = _smartcar_request(connection, "GET", f"/vehicles/{vehicle_id}")
            signals_payload = _smartcar_request(connection, "GET", f"/vehicles/{vehicle_id}/signals?pageSize=100")
        except ProviderError:
            vehicle, signals_payload = {}, {}
        vehicle_data = vehicle.get("data") if isinstance(vehicle.get("data"), dict) else vehicle
        vehicle_attributes = vehicle_data.get("attributes") if isinstance(vehicle_data, dict) and isinstance(vehicle_data.get("attributes"), dict) else vehicle_data if isinstance(vehicle_data, dict) else {}
        signal_values, signal_codes = _smartcar_signal_values(signals_payload)
        signal_readings = _smartcar_readings(signals_payload)
        info = signals_payload.get("included", {}).get("vehicle", {}).get("attributes", {}) if isinstance(signals_payload.get("included"), dict) else {}
        info = info if isinstance(info, dict) else vehicle_attributes
        label = " ".join(str(info.get(key) or "") for key in ("make", "model", "year")).strip() or "Smartcar-voertuig"
        entity_id = f"smartcar.{connection.id}.{vehicle_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection, "source": HomeEntity.Source.SMARTCAR, "domain": "vehicle", "name": label,
                "state": "available", "is_available": True, "is_supported": True,
                "attributes": {"smartcar_vehicle_id": vehicle_id, "smartcar_signals": signal_values, "smartcar_readings": signal_readings, "smartcar_signal_codes": sorted(signal_codes), "smartcar_can_lock": controls_enabled and "lock-status" in signal_codes, "smartcar_can_unlock": controls_enabled and "lock-status" in signal_codes, "smartcar_make": info.get("make"), "smartcar_model": info.get("model"), "smartcar_year": info.get("year")},
            },
        )
        seen.add(entity_id)
    HomeEntity.objects.for_household(connection.household).filter(source=HomeEntity.Source.SMARTCAR, connection=connection).exclude(entity_id__in=seen).update(is_available=False)
    return {"vehicles": len(seen)}


def _sonos_optional_request(connection: IntegrationConnection, method: str, path: str, payload: dict | None = None) -> dict:
    try:
        return _sonos_request(connection, method, path, payload)
    except ProviderError:
        return {}


def sonos_playback_metadata_attributes(payload: dict) -> dict:
    """Reduce Sonos metadata to the fields the household UI needs to display."""
    container = payload.get("container") if isinstance(payload.get("container"), dict) else {}
    current_item = payload.get("currentItem") if isinstance(payload.get("currentItem"), dict) else {}
    track = current_item.get("track") if isinstance(current_item.get("track"), dict) else {}
    artist = track.get("artist") if isinstance(track.get("artist"), dict) else {}
    album = track.get("album") if isinstance(track.get("album"), dict) else {}
    service = track.get("service") if isinstance(track.get("service"), dict) else container.get("service") if isinstance(container.get("service"), dict) else {}
    next_item = payload.get("nextItem") if isinstance(payload.get("nextItem"), dict) else {}
    next_track = next_item.get("track") if isinstance(next_item.get("track"), dict) else {}
    return {
        "sonos_now_playing_title": str(track.get("name") or container.get("name") or payload.get("streamInfo") or ""),
        "sonos_now_playing_artist": str(artist.get("name") or ""),
        "sonos_now_playing_album": str(album.get("name") or ""),
        "sonos_now_playing_artwork": str(track.get("imageUrl") or container.get("imageUrl") or ""),
        "sonos_source_name": str(service.get("name") or container.get("type") or ""),
        "sonos_source_type": str(container.get("type") or ""),
        "sonos_track_duration_ms": track.get("durationMillis"),
        "sonos_next_title": str(next_track.get("name") or ""),
        "sonos_can_next": bool(next_track),
        "sonos_can_previous": bool(track),
    }


def sonos_playback_status_attributes(payload: dict) -> dict:
    """Keep the UI limited to controls explicitly allowed by Sonos for this source."""
    actions = payload.get("availablePlaybackActions") if isinstance(payload.get("availablePlaybackActions"), dict) else {}
    play_modes = payload.get("playModes") if isinstance(payload.get("playModes"), dict) else {}
    return {
        "sonos_playback_state": str(payload.get("playbackState") or ""),
        "sonos_can_next": bool(actions.get("canSkip")),
        "sonos_can_previous": bool(actions.get("canSkipBack")),
        "sonos_can_shuffle": bool(actions.get("canShuffle")),
        "sonos_can_repeat": bool(actions.get("canRepeat")),
        "sonos_shuffle": bool(play_modes.get("shuffle")),
        "sonos_repeat": bool(play_modes.get("repeat")),
        "sonos_repeat_one": bool(play_modes.get("repeatOne")),
        "sonos_crossfade": bool(play_modes.get("crossfade")),
        "sonos_can_crossfade": "crossfade" in play_modes,
        "sonos_position_ms": payload.get("positionMillis"),
    }


def _sonos_favorites(payload: dict) -> list[dict]:
    """Persist a small, safe picker cache instead of exposing raw API payloads."""
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    favorites = []
    for item in items[:70]:
        if not isinstance(item, dict):
            continue
        favorite_id = str(item.get("id") or item.get("favoriteId") or "")
        if not favorite_id:
            continue
        favorites.append(
            {
                "id": favorite_id,
                "name": str(item.get("name") or item.get("title") or item.get("description") or "Sonos-favoriet"),
            }
        )
    return favorites


def sync_sonos(connection: IntegrationConnection) -> dict:
    from integrations.services import get_app_config

    households = _sonos_request(connection, "GET", "/households").get("households", [])
    if not isinstance(households, list) or not households:
        raise ProviderError("Sonos leverde geen huishoudens op.")
    household_ids = [str(item.get("id") or "") for item in households if isinstance(item, dict) and item.get("id")]
    selected = str(connection.settings.get("sonos_household_id") or "")
    if selected not in household_ids:
        selected = household_ids[0]
    seen = set()
    all_groups, all_players = [], []
    favorites_by_household = {
        sonos_household_id: _sonos_favorites(_sonos_optional_request(connection, "GET", f"/households/{sonos_household_id}/favorites"))
        for sonos_household_id in household_ids
    }
    for sonos_household_id in household_ids:
        payload = _sonos_request(connection, "GET", f"/households/{sonos_household_id}/groups")
        groups = payload.get("groups", []) if isinstance(payload, dict) else []
        players = payload.get("players", []) if isinstance(payload, dict) else []
        groups = groups if isinstance(groups, list) else []
        players = players if isinstance(players, list) else []
        all_groups.extend(groups)
        all_players.extend(players)
        player_groups = {
            str(player_id): group
            for group in groups if isinstance(group, dict)
            for player_id in group.get("playerIds", [])
        }
        for group in groups:
            if not isinstance(group, dict) or not group.get("id"):
                continue
            group_id = str(group["id"])
            playback = str(group.get("playbackState") or "")
            group_volume = _sonos_optional_request(connection, "GET", f"/groups/{group_id}/groupVolume")
            playback_status = _sonos_optional_request(connection, "GET", f"/groups/{group_id}/playback")
            playback_metadata = _sonos_optional_request(connection, "GET", f"/groups/{group_id}/playbackMetadata")
            member_ids = {str(item) for item in group.get("playerIds", [])}
            member_names = [str(player.get("name") or "Sonos-speaker") for player in players if isinstance(player, dict) and str(player.get("id") or "") in member_ids]
            entity_id = f"sonos.{connection.id}.group.{group_id}"
            HomeEntity.objects.update_or_create(
                household=connection.household,
                entity_id=entity_id,
                defaults={
                    "connection": connection,
                    "source": HomeEntity.Source.SONOS,
                    "domain": "media_player",
                    "name": str(group.get("name") or "Sonos-groep"),
                    "state": "on" if str(playback_status.get("playbackState") or playback) == "PLAYBACK_STATE_PLAYING" else "off",
                    "attributes": {"sonos_entity_type": "group", "sonos_household_id": sonos_household_id, "sonos_group_id": group_id, "sonos_coordinator_id": group.get("coordinatorId"), "sonos_player_ids": group.get("playerIds", []), "sonos_member_names": member_names, "sonos_favorites": favorites_by_household.get(sonos_household_id, []), "sonos_volume": group_volume.get("volume"), "sonos_muted": group_volume.get("muted", False), **sonos_playback_status_attributes({"playbackState": playback, **playback_status}), **sonos_playback_metadata_attributes(playback_metadata)},
                    "is_available": True,
                    "is_supported": True,
                },
            )
            seen.add(entity_id)
        for player in players:
            if not isinstance(player, dict) or not player.get("id"):
                continue
            player_id = str(player["id"])
            group = player_groups.get(player_id, {})
            group_id = str(group.get("id") or "") if isinstance(group, dict) else ""
            player_volume = _sonos_optional_request(connection, "GET", f"/players/{player_id}/playerVolume")
            entity_id = f"sonos.{connection.id}.player.{player_id}"
            HomeEntity.objects.update_or_create(
                household=connection.household,
                entity_id=entity_id,
                defaults={
                    "connection": connection,
                    "source": HomeEntity.Source.SONOS,
                    "domain": "speaker",
                    "name": str(player.get("name") or "Sonos-speaker"),
                    "state": "on" if str(group.get("playbackState") or "") == "PLAYBACK_STATE_PLAYING" else "off",
                    "attributes": {"sonos_entity_type": "player", "sonos_household_id": sonos_household_id, "sonos_player_id": player_id, "sonos_group_id": group_id, "sonos_group_name": group.get("name") if isinstance(group, dict) else "", "sonos_icon": player.get("icon"), "sonos_capabilities": player.get("capabilities", []), "sonos_device_ids": player.get("deviceIds", []), "sonos_api_version": player.get("apiVersion"), "sonos_volume": player_volume.get("volume"), "sonos_muted": player_volume.get("muted", False), "sonos_volume_fixed": player_volume.get("fixed", False)},
                    "is_available": True,
                    "is_supported": not bool(player_volume.get("fixed", False)),
                },
            )
            seen.add(entity_id)
    HomeEntity.objects.for_household(connection.household).filter(source=HomeEntity.Source.SONOS, connection=connection).exclude(entity_id__in=seen).update(is_available=False)
    settings = dict(connection.settings)
    settings["sonos_household_id"] = selected
    settings["sonos_household_ids"] = household_ids
    _, _, sonos_config = get_app_config(connection.household, "sonos")
    if sonos_config.get("events_enabled"):
        try:
            for sonos_household_id in household_ids:
                _sonos_request(connection, "POST", f"/households/{sonos_household_id}/groups/subscription")
            for group in all_groups:
                if isinstance(group, dict) and group.get("id"):
                    _sonos_request(connection, "POST", f"/groups/{group['id']}/playback/subscription")
                    _sonos_request(connection, "POST", f"/groups/{group['id']}/groupVolume/subscription")
                    _sonos_request(connection, "POST", f"/groups/{group['id']}/playbackMetadata/subscription")
            for player in all_players:
                if isinstance(player, dict) and player.get("id"):
                    _sonos_request(connection, "POST", f"/players/{player['id']}/playerVolume/subscription")
            settings["sonos_events_status"] = "active"
            settings["sonos_event_subscriptions_renewed_at"] = timezone.now().isoformat()
            settings.pop("sonos_events_error", None)
        except ProviderError as error:
            # Events improve freshness but must not block normal speaker control.
            settings["sonos_events_status"] = "waiting"
            settings["sonos_events_error"] = str(error)[:240]
    else:
        settings["sonos_events_status"] = "disabled"
        settings.pop("sonos_events_error", None)
    connection.settings = settings
    connection.save(update_fields=["settings", "updated_at"])
    return {"households": len(household_ids), "groups": len(all_groups), "players": len(all_players)}


def _google_home_request(connection: IntegrationConnection, method: str, path: str, payload: dict | None = None) -> dict:
    from integrations.services import GOOGLE_OAUTH_TOKEN_URL

    token = _refresh_connection_token(connection, "Google Home", GOOGLE_OAUTH_TOKEN_URL)
    try:
        response = requests.request(method, f"https://smartdevicemanagement.googleapis.com/v1{path}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=20)
    except requests.RequestException as error:
        raise ProviderError("Google Home is tijdelijk niet bereikbaar.") from error
    return _oauth_response(response, "Google Home")


def start_google_home_live_stream(entity: HomeEntity) -> dict:
    """Create a short-lived Google RTSP session and hand it only to the internal relay."""
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    resource_name = str(attributes.get("google_resource_name") or "")
    protocols = {str(protocol).upper() for protocol in attributes.get("camera_stream_protocols", [])}
    if not resource_name or "RTSP" not in protocols:
        raise ProviderError("Deze camera biedt geen RTSP-livestream.")
    if not entity.connection:
        raise ProviderError("De Google Home-koppeling voor deze camera ontbreekt.")

    # Generate per-household/entity stream names for tenant isolation
    rtsp_stream_name = _go2rtc_stream_name(entity.household_id, entity.id)
    mjpeg_stream_name = _go2rtc_mjpeg_stream_name(entity.household_id, entity.id)

    payload = _google_home_request(
        entity.connection,
        "POST",
        f"/{resource_name}:executeCommand",
        {"command": "sdm.devices.commands.CameraLiveStream.GenerateRtspStream", "params": {}},
    )
    results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
    stream_urls = results.get("streamUrls") if isinstance(results.get("streamUrls"), dict) else {}
    rtsp_url = str(stream_urls.get("rtspUrl") or "")
    if not rtsp_url.startswith("rtsp"):
        raise ProviderError("Google Home leverde geen geldige livestream.")
    try:
        relay_response = requests.put(
            f"{_go2rtc_api_url()}/api/streams",
            params={"name": rtsp_stream_name, "src": rtsp_url},
            timeout=20,
        )
    except requests.RequestException as error:
        raise ProviderError("De lokale videorelay is niet bereikbaar.") from error
    if not relay_response.ok:
        raise ProviderError("De videorelay kon de Nest-livestream niet starten.")
    try:
        mjpeg_response = requests.put(
            f"{_go2rtc_api_url()}/api/streams",
            params={"name": mjpeg_stream_name, "src": f"ffmpeg:{rtsp_stream_name}#video=mjpeg"},
            timeout=20,
        )
    except requests.RequestException as error:
        requests.delete(f"{_go2rtc_api_url()}/api/streams", params={"src": rtsp_stream_name}, timeout=10)
        raise ProviderError("De lokale videorelay is niet bereikbaar.") from error
    if not mjpeg_response.ok:
        requests.delete(f"{_go2rtc_api_url()}/api/streams", params={"src": rtsp_stream_name}, timeout=10)
        raise ProviderError("De videorelay kon de browserstream niet starten.")
    return {"expires_at": str(results.get("expiresAt") or ""), "stream_name": mjpeg_stream_name, "rtsp_stream_name": rtsp_stream_name}


def stop_google_home_live_stream(mjpeg_stream_name: str, rtsp_stream_name: str) -> None:
    """Stop a per-household/entity livestream."""
    try:
        requests.delete(f"{_go2rtc_api_url()}/api/streams", params={"src": mjpeg_stream_name}, timeout=10)
        requests.delete(f"{_go2rtc_api_url()}/api/streams", params={"src": rtsp_stream_name}, timeout=10)
    except requests.RequestException:
        pass


def google_home_mjpeg_stream(stream_name: str):
    return _google_home_relay_stream("/api/stream.mjpeg", stream_name)


def google_home_mp4_stream(stream_name: str):
    return _google_home_relay_stream("/api/stream.mp4", stream_name)


def _google_home_relay_stream(path: str, stream_name: str):
    try:
        response = requests.get(
            f"{_go2rtc_api_url()}{path}",
            params={"src": stream_name},
            stream=True,
            timeout=(5, 60),
        )
    except requests.RequestException as error:
        raise ProviderError("De videorelay is niet bereikbaar.") from error
    if not response.ok:
        response.close()
        raise ProviderError("De livestream is niet beschikbaar.")
    return response


def _round_temperature(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def google_home_thermostat_attributes(traits: dict, device: dict | None = None) -> dict:
    """Flatten exposed Device Access traits for one consistent Home card model."""
    device = device if isinstance(device, dict) else {}
    traits = traits if isinstance(traits, dict) else {}
    info = traits.get("sdm.devices.traits.Info") if isinstance(traits.get("sdm.devices.traits.Info"), dict) else {}
    temperature = traits.get("sdm.devices.traits.Temperature") if isinstance(traits.get("sdm.devices.traits.Temperature"), dict) else {}
    humidity = traits.get("sdm.devices.traits.Humidity") if isinstance(traits.get("sdm.devices.traits.Humidity"), dict) else {}
    connectivity = traits.get("sdm.devices.traits.Connectivity") if isinstance(traits.get("sdm.devices.traits.Connectivity"), dict) else {}
    settings = traits.get("sdm.devices.traits.Settings") if isinstance(traits.get("sdm.devices.traits.Settings"), dict) else {}
    setpoint = traits.get("sdm.devices.traits.ThermostatTemperatureSetpoint") if isinstance(traits.get("sdm.devices.traits.ThermostatTemperatureSetpoint"), dict) else {}
    mode = traits.get("sdm.devices.traits.ThermostatMode") if isinstance(traits.get("sdm.devices.traits.ThermostatMode"), dict) else {}
    eco = traits.get("sdm.devices.traits.ThermostatEco") if isinstance(traits.get("sdm.devices.traits.ThermostatEco"), dict) else {}
    hvac = traits.get("sdm.devices.traits.ThermostatHvac") if isinstance(traits.get("sdm.devices.traits.ThermostatHvac"), dict) else {}
    fan = traits.get("sdm.devices.traits.Fan") if isinstance(traits.get("sdm.devices.traits.Fan"), dict) else {}
    on_off = traits.get("sdm.devices.traits.OnOff") if isinstance(traits.get("sdm.devices.traits.OnOff"), dict) else {}
    camera_image = traits.get("sdm.devices.traits.CameraImage") if isinstance(traits.get("sdm.devices.traits.CameraImage"), dict) else {}
    camera_stream = traits.get("sdm.devices.traits.CameraLiveStream") if isinstance(traits.get("sdm.devices.traits.CameraLiveStream"), dict) else {}
    locations = [str(item.get("displayName")) for item in device.get("parentRelations", []) if isinstance(item, dict) and item.get("displayName")]
    return {
        "google_resource_name": str(device.get("name") or ""),
        "google_device_type": str(device.get("type") or ""),
        "google_traits": traits,
        "google_locations": locations,
        "google_model": str(info.get("model") or ""),
        "current_temperature": _round_temperature(temperature.get("ambientTemperatureCelsius")),
        "humidity": humidity.get("ambientHumidityPercent"),
        "temperature": _round_temperature(setpoint.get("heatCelsius")) if setpoint.get("heatCelsius") is not None else _round_temperature(setpoint.get("coolCelsius")),
        "temperature_heat": _round_temperature(setpoint.get("heatCelsius")),
        "temperature_cool": _round_temperature(setpoint.get("coolCelsius")),
        "thermostat_mode": str(mode.get("mode") or ""),
        "thermostat_modes": [str(item) for item in mode.get("availableModes", []) if item],
        "eco_mode": str(eco.get("mode") or ""),
        "eco_modes": [str(item) for item in eco.get("availableModes", []) if item],
        "eco_heat": _round_temperature(eco.get("heatCelsius")),
        "eco_cool": _round_temperature(eco.get("coolCelsius")),
        "hvac_status": str(hvac.get("status") or ""),
        "google_connectivity": str(connectivity.get("status") or ""),
        "temperature_scale": str(settings.get("temperatureScale") or "CELSIUS"),
        "fan_timer_mode": str(fan.get("timerMode") or ""),
        "fan_timer_timeout": str(fan.get("timerTimeout") or ""),
        "min_temp": 9,
        "max_temp": 32,
        "target_temp_step": 0.5,
        "supports_on_off": bool(on_off),
        "supports_temperature": "sdm.devices.traits.ThermostatTemperatureSetpoint" in traits,
        "supports_temperature_range": "sdm.devices.traits.ThermostatTemperatureSetpoint" in traits and mode.get("mode") == "HEATCOOL",
        "supports_thermostat_mode": bool(mode),
        "supports_eco": bool(eco),
        "supports_fan_timer": bool(fan),
        "supports_camera_image": bool(camera_image),
        "supports_camera_stream": bool(camera_stream),
        "camera_stream_protocols": [str(item) for item in camera_stream.get("supportedProtocols", []) if item],
        "supports_camera_motion": "sdm.devices.traits.CameraMotion" in traits,
        "supports_camera_person": "sdm.devices.traits.CameraPerson" in traits,
        "supports_camera_sound": "sdm.devices.traits.CameraSound" in traits,
        "supports_doorbell_chime": "sdm.devices.traits.DoorbellChime" in traits,
    }


def google_home_entity_name(device: dict, traits: dict) -> str:
    info = traits.get("sdm.devices.traits.Info") if isinstance(traits.get("sdm.devices.traits.Info"), dict) else {}
    if info.get("customName") or info.get("name"):
        return str(info.get("customName") or info.get("name"))
    device_type = str(device.get("type") or "")
    if device_type.endswith("THERMOSTAT"):
        return "Nest Thermostaat"
    if device_type.endswith("DOORBELL"):
        return "Nest Deurbel"
    if device_type.endswith("CAMERA"):
        return "Nest Camera"
    return device_type.rsplit(".", 1)[-1].replace("_", " ").title() or "Google Nest-apparaat"


def apply_google_home_traits(entity: HomeEntity, traits: dict, device: dict | None = None) -> HomeEntity:
    attributes = google_home_thermostat_attributes(traits, device)
    existing = entity.attributes if isinstance(entity.attributes, dict) else {}
    # Google omits the actual setpoint while a Nest thermostat is off. Keep the
    # most recently received value so the card can still explain its setting.
    if attributes["supports_temperature"]:
        for key in ("temperature", "temperature_heat", "temperature_cool"):
            if attributes.get(key) is None and existing.get(key) is not None:
                attributes[key] = existing[key]
    entity.attributes = {**existing, **attributes}
    connectivity = attributes["google_connectivity"]
    hvac = attributes["hvac_status"]
    entity.is_available = connectivity != "OFFLINE"
    entity.is_supported = bool(attributes["supports_on_off"] or attributes["supports_temperature"] or attributes["supports_thermostat_mode"] or attributes["supports_eco"] or attributes["supports_fan_timer"])
    if attributes["supports_temperature"] or attributes["supports_thermostat_mode"]:
        entity.state = {"HEATING": "heating", "COOLING": "cooling", "OFF": "off"}.get(hvac, "on" if attributes["thermostat_mode"] not in {"", "OFF"} else "off")
    else:
        entity.state = "ready" if entity.is_available else "off"
    return entity


def sync_google_home(connection: IntegrationConnection) -> dict:
    project_id = str(connection.settings.get("project_id") or "")
    if not project_id:
        raise ProviderError("Google Home Device Access project ID ontbreekt.")
    payload = _google_home_request(connection, "GET", f"/enterprises/{project_id}/devices")
    devices = payload.get("devices", []) if isinstance(payload, dict) else []
    seen = set()
    for device in devices if isinstance(devices, list) else []:
        if not isinstance(device, dict) or not device.get("name"):
            continue
        resource_name = str(device["name"])
        device_id = resource_name.rsplit("/", 1)[-1]
        traits = device.get("traits") if isinstance(device.get("traits"), dict) else {}
        info = traits.get("sdm.devices.traits.Info", {}) if isinstance(traits.get("sdm.devices.traits.Info"), dict) else {}
        is_climate = any(key in traits for key in ("sdm.devices.traits.Temperature", "sdm.devices.traits.ThermostatTemperatureSetpoint", "sdm.devices.traits.ThermostatMode"))
        entity_id = f"google_home.{connection.id}.{device_id}"
        entity, _ = HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.GOOGLE_HOME,
                "domain": "climate" if is_climate else "device",
                "name": google_home_entity_name(device, traits),
                "state": "off",
                "attributes": {},
                "is_available": True,
                "is_supported": False,
            },
        )
        apply_google_home_traits(entity, traits, device)
        entity.save(update_fields=["state", "attributes", "is_available", "is_supported", "last_seen_at"])
        seen.add(entity_id)
    HomeEntity.objects.for_household(connection.household).filter(source=HomeEntity.Source.GOOGLE_HOME, connection=connection).exclude(entity_id__in=seen).update(is_available=False)
    return {"devices": len(seen)}


def sync_lg_thinq(connection: IntegrationConnection) -> dict:
    data = dict(connection.settings) if isinstance(connection.settings, dict) else {}
    api_base_url = str(data.get("api_base_url") or "").rstrip("/")
    devices_path = str(data.get("devices_path") or "/devices")
    if not api_base_url:
        raise ProviderError("LG ThinQ API base URL ontbreekt.")
    from integrations.services import get_app_config

    _, _, config = get_app_config(connection.household, "lg_thinq")
    token_url = str(config.get("token_url") or "")
    if not token_url:
        raise ProviderError("LG ThinQ token URL ontbreekt.")
    token = _refresh_connection_token(connection, "LG ThinQ", token_url)
    try:
        response = requests.get(f"{api_base_url}/{devices_path.lstrip('/')}", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    except requests.RequestException as error:
        raise ProviderError("LG ThinQ is tijdelijk niet bereikbaar.") from error
    payload = _oauth_response(response, "LG ThinQ")
    devices = payload.get("devices") or payload.get("data") or []
    if not isinstance(devices, list):
        raise ProviderError("LG ThinQ leverde geen apparatenlijst.")
    seen = set()
    for device in devices:
        if not isinstance(device, dict):
            continue
        device_id = str(device.get("deviceId") or device.get("id") or "")
        if not device_id:
            continue
        entity_id = f"lg_thinq.{connection.id}.{device_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={"connection": connection, "source": HomeEntity.Source.LG_THINQ, "domain": "device", "name": str(device.get("alias") or device.get("name") or device.get("deviceName") or "LG ThinQ-apparaat"), "state": str(device.get("state") or "unknown"), "attributes": {"lg_device_id": device_id, "lg_device_type": device.get("deviceType") or device.get("type"), "lg_raw_status": device.get("snapshot") or device.get("status") or {}}, "is_available": True, "is_supported": False},
        )
        seen.add(entity_id)
    HomeEntity.objects.for_household(connection.household).filter(source=HomeEntity.Source.LG_THINQ, connection=connection).exclude(entity_id__in=seen).update(is_available=False)
    return {"devices": len(seen)}


def control_connected_home_entity(entity: HomeEntity, action: str, value=None) -> str:
    connection = entity.connection
    if not connection:
        raise ProviderError("De koppeling voor dit apparaat ontbreekt.")
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    if entity.source == HomeEntity.Source.HOME_CONNECT:
        appliance_id = str(attributes.get("home_connect_id") or "")
        if not appliance_id:
            raise ProviderError("Dit Home Connect-apparaat heeft geen geldige identificatie.")
        if action == "start_program":
            if not bool(attributes.get("home_connect_remote_start")):
                raise ProviderError("Zet eerst Remote Start aan op het apparaat.")
            if attributes.get("home_connect_can_start") is False:
                raise ProviderError(str(attributes.get("home_connect_start_status") or "Dit apparaat kan nu geen programma starten."))
            program = str(value or "").strip()
            selected_program = next((item for item in attributes.get("home_connect_programs", []) if isinstance(item, dict) and str(item.get("key")) == program), None)
            if not selected_program:
                raise ProviderError("Kies een programma dat dit apparaat momenteel toestaat.")
            options = [
                {"key": option["key"], "value": option["value"]}
                for option in selected_program.get("options", [])
                if isinstance(option, dict) and option.get("key") and "value" in option
            ]
            _home_connect_request(connection, "PUT", f"/homeappliances/{appliance_id}/programs/active", payload={"data": {"key": program, "options": options}})
            return "Programma gestart."
        if action == "select_program":
            if not bool(attributes.get("home_connect_can_select_program")):
                raise ProviderError("Er kan nu geen programma worden geselecteerd.")
            program = str(value or "").strip()
            selected_program = next((item for item in attributes.get("home_connect_programs", []) if isinstance(item, dict) and str(item.get("key")) == program), None)
            if not selected_program:
                raise ProviderError("Kies een programma dat dit apparaat momenteel toestaat.")
            _home_connect_request(connection, "PUT", f"/homeappliances/{appliance_id}/programs/selected", payload={"data": {"key": program}})
            return "Programma geselecteerd; het apparaat start niet automatisch."
        if action == "stop_program":
            if not bool(attributes.get("home_connect_can_stop")):
                raise ProviderError("Dit programma kan nu niet worden gestopt.")
            _home_connect_request(connection, "DELETE", f"/homeappliances/{appliance_id}/programs/active", allow_empty=True)
            return "Programma gestopt."
        command_map = {
            "pause_program": "BSH.Common.Command.PauseProgram",
            "resume_program": "BSH.Common.Command.ResumeProgram",
        }
        command = command_map.get(action)
        if not command or not bool(attributes.get(f"home_connect_can_{action.removesuffix('_program')}")):
            raise ProviderError("Deze Home Connect-bediening is nu niet beschikbaar.")
        _home_connect_request(connection, "PUT", f"/homeappliances/{appliance_id}/commands/{command}", payload={"data": True})
        return {"pause_program": "Programma gepauzeerd.", "resume_program": "Programma hervat."}[action]
    if entity.source == HomeEntity.Source.SPOTIFY:
        device_id = str(attributes.get("spotify_device_id") or "")
        if not device_id:
            raise ProviderError("Dit Spotify-apparaat heeft geen geldige identificatie.")
        if attributes.get("spotify_is_restricted"):
            raise ProviderError("Spotify staat bediening van dit apparaat niet toe.")
        if action == "transfer":
            _spotify_request(connection, "PUT", "/me/player", payload={"device_ids": [device_id], "play": False}, allow_empty=True)
            return "Spotify-bediening verplaatst naar dit apparaat."
        if action == "play_pause":
            if entity.state == "on":
                _spotify_request(connection, "PUT", "/me/player/pause", params={"device_id": device_id}, allow_empty=True)
                return "Spotify gepauzeerd."
            _spotify_request(connection, "PUT", "/me/player/play", params={"device_id": device_id}, allow_empty=True)
            return "Spotify afgespeeld."
        if action in {"next", "previous"}:
            endpoint = "/me/player/next" if action == "next" else "/me/player/previous"
            _spotify_request(connection, "POST", endpoint, params={"device_id": device_id}, allow_empty=True)
            return "Volgend nummer gekozen." if action == "next" else "Vorig nummer gekozen."
        if action == "set_volume":
            try:
                volume = max(0, min(100, int(float(value))))
            except (TypeError, ValueError) as error:
                raise ProviderError("Kies een volume tussen 0 en 100.") from error
            _spotify_request(connection, "PUT", "/me/player/volume", params={"device_id": device_id, "volume_percent": volume}, allow_empty=True)
            return f"Spotify-volume ingesteld op {volume}%."
        if action == "toggle_shuffle":
            state = not bool(attributes.get("spotify_shuffle"))
            _spotify_request(connection, "PUT", "/me/player/shuffle", params={"device_id": device_id, "state": str(state).lower()}, allow_empty=True)
            return f"Shuffle {'ingeschakeld' if state else 'uitgeschakeld'}."
        if action == "set_repeat_mode":
            repeat = str(value or "off")
            if repeat not in {"off", "context", "track"}:
                raise ProviderError("Kies een geldige herhaalmodus.")
            _spotify_request(connection, "PUT", "/me/player/repeat", params={"device_id": device_id, "state": repeat}, allow_empty=True)
            return "Herhaalmodus bijgewerkt."
        if action == "play_context":
            uri = str(value or "").strip()
            allowed_types = {"album", "artist", "episode", "playlist", "show", "track"}
            uri_parts = uri.split(":", 2)
            if len(uri_parts) != 3 or uri_parts[0] != "spotify" or uri_parts[1] not in allowed_types:
                raise ProviderError("Kies een geldige Spotify-playlist, album of track.")
            payload = {"uris": [uri]} if uri_parts[1] in {"track", "episode"} else {"context_uri": uri}
            _spotify_request(connection, "PUT", "/me/player/play", params={"device_id": device_id}, payload=payload, allow_empty=True)
            return "Spotify-selectie wordt afgespeeld."
        if action == "queue_uri":
            uri = str(value or "").strip()
            uri_parts = uri.split(":", 2)
            if len(uri_parts) != 3 or uri_parts[0] != "spotify" or uri_parts[1] not in {"track", "episode"}:
                raise ProviderError("Kies een geldige Spotify-track of aflevering.")
            _spotify_request(connection, "POST", "/me/player/queue", params={"device_id": device_id, "uri": uri}, allow_empty=True)
            return "Aan de Spotify-wachtrij toegevoegd."
        raise ProviderError("Deze Spotify-bediening is niet beschikbaar.")
    if entity.source == HomeEntity.Source.SMARTCAR:
        vehicle_id = str(attributes.get("smartcar_vehicle_id") or "")
        if not vehicle_id:
            raise ProviderError("Dit voertuig heeft geen geldige identificatie.")
        if action not in {"lock", "unlock"}:
            raise ProviderError("Deze Smartcar-bediening is niet beschikbaar.")
        if not bool(attributes.get(f"smartcar_can_{action}")):
            raise ProviderError("Deze Smartcar-bediening is niet voor dit voertuig geautoriseerd.")
        endpoint = f"/vehicles/{vehicle_id}/commands/security/{action}"
        _smartcar_request(connection, "POST", endpoint)
        return "Voertuig vergrendeld." if action == "lock" else "Voertuig ontgrendeld."
    if entity.source == HomeEntity.Source.SONOS:
        group_id = str(attributes.get("sonos_group_id") or "")
        household_id = str(attributes.get("sonos_household_id") or "")
        player_id = str(attributes.get("sonos_player_id") or "")
        is_player = attributes.get("sonos_entity_type") == "player"
        if not household_id or (is_player and not player_id) or (not is_player and not group_id):
            raise ProviderError("Dit Sonos-apparaat heeft geen geldige identificatie.")
        if action in {"set_volume", "volume_up", "volume_down", "mute", "unmute"}:
            target = f"/players/{player_id}/playerVolume" if is_player else f"/groups/{group_id}/groupVolume"
            if action == "set_volume":
                try:
                    volume = max(0, min(100, int(float(value))))
                except (TypeError, ValueError) as error:
                    raise ProviderError("Kies een volume tussen 0 en 100.") from error
                _sonos_request(connection, "POST", target, {"volume": volume})
                return f"Volume ingesteld op {volume}%."
            if action in {"volume_up", "volume_down"}:
                delta = 5 if action == "volume_up" else -5
                _sonos_request(connection, "POST", f"{target}/relative", {"volumeDelta": delta})
                return "Volume verhoogd." if delta > 0 else "Volume verlaagd."
            _sonos_request(connection, "POST", f"{target}/mute", {"muted": action == "mute"})
            return "Sonos is gedempt." if action == "mute" else "Sonos is niet meer gedempt."
        if is_player:
            raise ProviderError("Afspelen en pauzeren worden door Sonos op groepsniveau bediend.")
        if action in {"next", "previous"}:
            command = "skipToNextTrack" if action == "next" else "skipToPreviousTrack"
            _sonos_request(connection, "POST", f"/groups/{group_id}/playback/{command}", {})
            return "Volgende nummer gekozen." if action == "next" else "Vorige nummer gekozen."
        if action == "load_favorite":
            favorite_id = str(value or "")
            favorites = attributes.get("sonos_favorites") if isinstance(attributes.get("sonos_favorites"), list) else []
            if favorite_id not in {str(item.get("id")) for item in favorites if isinstance(item, dict)}:
                raise ProviderError("Kies een geldige Sonos-favoriet.")
            _sonos_request(connection, "POST", f"/groups/{group_id}/favorites", {"favoriteId": favorite_id, "action": "PLAY_NOW", "playOnCompletion": True})
            return "Sonos-favoriet gestart."
        if action == "set_group":
            player_ids = [str(player_id) for player_id in value if str(player_id)] if isinstance(value, (list, tuple)) else []
            if not player_ids or len(player_ids) > 32:
                raise ProviderError("Kies een geldige set Sonos-speakers.")
            known_players = {
                str(item.attributes.get("sonos_player_id"))
                for item in HomeEntity.objects.filter(
                    household=entity.household,
                    connection=connection,
                    source=HomeEntity.Source.SONOS,
                    domain="speaker",
                )
                if isinstance(item.attributes, dict) and item.attributes.get("sonos_household_id") == household_id
            }
            if not set(player_ids).issubset(known_players):
                raise ProviderError("Een geselecteerde speaker hoort niet bij dit Sonos-huishouden.")
            _sonos_request(
                connection,
                "POST",
                f"/households/{household_id}/groups/createGroup",
                {"playerIds": player_ids, "musicContextGroupId": group_id},
            )
            return "Sonos-groep bijgewerkt."
        if action in {"toggle_shuffle", "toggle_repeat", "toggle_crossfade"}:
            mode_key = "shuffle" if action == "toggle_shuffle" else "repeat" if action == "toggle_repeat" else "crossfade"
            mode_value = not bool(attributes.get(f"sonos_{mode_key}"))
            _sonos_request(connection, "POST", f"/groups/{group_id}/playback/playMode", {"playModes": {mode_key: mode_value}})
            label = "Shuffle" if mode_key == "shuffle" else "Herhalen" if mode_key == "repeat" else "Crossfade"
            return f"{label} {'ingeschakeld' if mode_value else 'uitgeschakeld'}."
        if action == "set_repeat_mode":
            repeat_mode = str(value or "off")
            if repeat_mode not in {"off", "all", "one"}:
                raise ProviderError("Kies een geldige herhaalmodus.")
            _sonos_request(
                connection,
                "POST",
                f"/groups/{group_id}/playback/playMode",
                {"playModes": {"repeat": repeat_mode != "off", "repeatOne": repeat_mode == "one"}},
            )
            return {"off": "Herhalen uitgeschakeld.", "all": "Herhalen van de wachtrij ingeschakeld.", "one": "Huidig nummer wordt herhaald."}[repeat_mode]
        command = "play" if action in {"on", "play_pause"} and entity.state != "on" else "pause"
        if action == "off":
            command = "pause"
        if action not in {"on", "off", "play_pause"}:
            raise ProviderError("Deze Sonos-bediening is niet beschikbaar.")
        _sonos_request(connection, "POST", f"/groups/{group_id}/playback/{command}", {})
        return "Sonos speelt af." if command == "play" else "Sonos is gepauzeerd."
    if entity.source == HomeEntity.Source.GOOGLE_HOME:
        resource_name = str(attributes.get("google_resource_name") or "")
        traits = attributes.get("google_traits") if isinstance(attributes.get("google_traits"), dict) else {}
        if not resource_name:
            raise ProviderError("Dit Google Home-apparaat heeft geen geldige identificatie.")
        if action in {"on", "off"} and "sdm.devices.traits.OnOff" in traits:
            payload = {"command": "sdm.devices.commands.OnOff", "params": {"on": action == "on"}}
            _google_home_request(connection, "POST", f"/{resource_name}:executeCommand", payload)
            return "Ingeschakeld." if action == "on" else "Uitgeschakeld."
        if action == "set_temperature" and "sdm.devices.traits.ThermostatTemperatureSetpoint" in traits:
            try:
                temperature = float(value)
            except (TypeError, ValueError) as error:
                raise ProviderError("Kies een geldige temperatuur.") from error
            mode = str(attributes.get("thermostat_mode") or (traits.get("sdm.devices.traits.ThermostatMode") or {}).get("mode") or "").upper()
            if mode == "HEATCOOL":
                raise ProviderError("Gebruik het warmte- en koelingsbereik in de thermostaatkaart.")
            if mode == "HEAT":
                payload = {"command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat", "params": {"heatCelsius": temperature}}
            elif mode == "COOL":
                payload = {"command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetCool", "params": {"coolCelsius": temperature}}
            else:
                raise ProviderError("Google Home meldt geen instelbare thermostaatmodus.")
            _google_home_request(connection, "POST", f"/{resource_name}:executeCommand", payload)
            return f"Temperatuur ingesteld op {temperature:g} °C."
        if action == "set_temperature_range" and "sdm.devices.traits.ThermostatTemperatureSetpoint" in traits:
            try:
                values = value if isinstance(value, dict) else json.loads(str(value))
                heat, cool = float(values["heat"]), float(values["cool"])
            except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
                raise ProviderError("Vul een geldig warmte- en koelbereik in.") from error
            if cool <= heat:
                raise ProviderError("De koeltemperatuur moet hoger zijn dan de warmtetemperatuur.")
            _google_home_request(connection, "POST", f"/{resource_name}:executeCommand", {"command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetRange", "params": {"heatCelsius": heat, "coolCelsius": cool}})
            return f"Bereik ingesteld op {heat:g}–{cool:g} °C."
        if action == "set_thermostat_mode" and "sdm.devices.traits.ThermostatMode" in traits:
            mode = str(value or "").upper()
            available = (traits.get("sdm.devices.traits.ThermostatMode") or {}).get("availableModes") or []
            if mode not in available:
                raise ProviderError("Deze thermostaatmodus is niet beschikbaar.")
            _google_home_request(connection, "POST", f"/{resource_name}:executeCommand", {"command": "sdm.devices.commands.ThermostatMode.SetMode", "params": {"mode": mode}})
            return "Thermostaatmodus bijgewerkt."
        if action == "set_eco_mode" and "sdm.devices.traits.ThermostatEco" in traits:
            mode = str(value or "").upper()
            available = (traits.get("sdm.devices.traits.ThermostatEco") or {}).get("availableModes") or []
            if mode not in available:
                raise ProviderError("Deze Eco-modus is niet beschikbaar.")
            _google_home_request(connection, "POST", f"/{resource_name}:executeCommand", {"command": "sdm.devices.commands.ThermostatEco.SetMode", "params": {"mode": mode}})
            return "Eco-modus bijgewerkt."
        if action == "set_fan_timer" and "sdm.devices.traits.Fan" in traits:
            try:
                seconds = int(value)
            except (TypeError, ValueError) as error:
                raise ProviderError("Kies een geldige ventilatorduur.") from error
            if seconds not in {0, 900, 1800, 3600, 7200, 14400}:
                raise ProviderError("Deze ventilatorduur is niet beschikbaar.")
            params = {"timerMode": "OFF"} if seconds == 0 else {"timerMode": "ON", "duration": f"{seconds}s"}
            _google_home_request(connection, "POST", f"/{resource_name}:executeCommand", {"command": "sdm.devices.commands.Fan.SetTimer", "params": params})
            return "Ventilatortimer bijgewerkt."
        raise ProviderError("Deze Google Home-bediening is niet beschikbaar voor dit apparaat.")
    if entity.source == HomeEntity.Source.LG_THINQ:
        raise ProviderError("LG ThinQ-apparaten worden na synchronisatie veilig als status getoond. Bedieningscommando's verschillen per apparaat en worden toegevoegd zodra de Smart Solution API de device-capabilities levert.")
    raise ProviderError("Deze bediening is niet beschikbaar.")


def _stored_hue_token_is_current(data: dict) -> bool:
    expires_at = data.get("expires_at", "")
    if not data.get("access_token") or not expires_at:
        return False
    try:
        expires = timezone.datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return False
    if timezone.is_naive(expires):
        expires = timezone.make_aware(expires, timezone.get_current_timezone())
    return expires > timezone.now() + timedelta(seconds=45)


def _hue_response(response):
    try:
        payload = response.json() if response.content else {}
    except ValueError as error:
        raise ProviderError("Philips Hue gaf geen geldige reactie.") from error
    if not response.ok:
        raise HueProviderError(
            "Philips Hue weigerde de aanvraag. Koppel de bridge opnieuw als dit blijft gebeuren.",
            getattr(response, "status_code", None),
        )
    if isinstance(payload, dict) and payload.get("errors"):
        first_error = next((item for item in payload["errors"] if isinstance(item, dict)), {})
        raise HueProviderError(str(first_error.get("description") or "Philips Hue kon de aanvraag niet uitvoeren.")[:240])
    return payload


def _hue_token(connection: IntegrationConnection) -> str:
    data = connection.settings
    if _stored_hue_token_is_current(data):
        return decrypt(data["access_token"])
    refresh_token = decrypt(connection.secret_encrypted) if connection.secret_encrypted else ""
    if not refresh_token:
        raise ProviderError("Philips Hue moet opnieuw worden geautoriseerd.")
    from integrations.services import HUE_OAUTH_TOKEN_URL, get_app_config

    client_id, client_secret, _ = get_app_config(connection.household, "hue")
    if not client_id or not client_secret:
        raise ProviderError("Philips Hue-clientgegevens ontbreken.")
    response = requests.post(
        HUE_OAUTH_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(client_id, client_secret),
        timeout=20,
    )
    payload = _hue_response(response)
    if not payload.get("access_token"):
        raise ProviderError("Philips Hue-token vernieuwen mislukt.")
    connection.secret_encrypted = encrypt(payload.get("refresh_token") or refresh_token)
    connection.settings = {
        **data,
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat(),
    }
    connection.save(update_fields=["secret_encrypted", "settings", "updated_at"])
    return payload["access_token"]


def _hue_request(connection: IntegrationConnection, method: str, path: str, payload: dict | None = None):
    token = _hue_token(connection)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # The V1 bridge-registration calls only use the bearer token. Every V2
    # resource request also needs the application key returned by that step.
    application_key = str(connection.settings.get("bridge_username") or "")
    if application_key:
        headers["hue-application-key"] = application_key
    try:
        response = requests.request(
            method,
            f"https://api.meethue.com{path}",
            headers=headers,
            json=payload,
            timeout=20,
        )
    except requests.RequestException as error:
        raise ProviderError("Philips Hue is tijdelijk niet bereikbaar.") from error
    return _hue_response(response)


def _hue_optional_resource(connection: IntegrationConnection, resource_type: str) -> list[dict]:
    """Return an optional V2 resource list without making older bridges fail sync."""
    try:
        payload = _hue_request(connection, "GET", f"/route/clip/v2/resource/{resource_type}")
    except HueProviderError as error:
        if error.status_code == 404:
            return []
        raise
    resources = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in resources if isinstance(item, dict)] if isinstance(resources, list) else []


def _hue_sensor_state(resource_type: str, resource: dict) -> tuple[str, bool]:
    if resource_type == "motion":
        motion = resource.get("motion") if isinstance(resource.get("motion"), dict) else {}
        active = bool(motion.get("motion"))
        return ("Beweging" if active else "Geen beweging"), active
    if resource_type == "temperature":
        temperature = resource.get("temperature") if isinstance(resource.get("temperature"), dict) else {}
        value = temperature.get("temperature")
        try:
            celsius = float(value)
            # Hue V2 reports modern bridges directly in degrees Celsius. Some
            # older payloads use hundredths, so retain compatibility there.
            if abs(celsius) > 100:
                celsius /= 100
            return f"{celsius:.1f} °C".replace(".", ","), False
        except (TypeError, ValueError):
            return "Temperatuur onbekend", False
    if resource_type == "light_level":
        light = resource.get("light") if isinstance(resource.get("light"), dict) else {}
        value = light.get("light_level")
        return (f"Lichtniveau {value}" if value is not None else "Lichtniveau onbekend"), False
    if resource_type == "contact":
        report = resource.get("contact_report") if isinstance(resource.get("contact_report"), dict) else {}
        changed = report.get("changed")
        if changed is True:
            return "Contact geopend", True
        if changed is False:
            return "Contact gesloten", False
        return "Contactstatus onbekend", False
    if resource_type == "button":
        report = resource.get("button_report") if isinstance(resource.get("button_report"), dict) else {}
        event = report.get("event")
        return (f"Laatste knopactie: {event}" if event else "Nog geen knopactie"), False
    return "Status onbekend", False


def _gamut_point(value) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        return float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError):
        return None


def _point_is_in_gamut(point: tuple[float, float], gamut: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]) -> bool:
    def cross(origin, first, second):
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])

    red, green, blue = gamut
    first, second, third = cross(point, red, green), cross(point, green, blue), cross(point, blue, red)
    return (first >= 0 and second >= 0 and third >= 0) or (first <= 0 and second <= 0 and third <= 0)


def _nearest_point_on_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    delta_x, delta_y = end[0] - start[0], end[1] - start[1]
    length_squared = delta_x * delta_x + delta_y * delta_y
    if not length_squared:
        return start
    factor = max(0, min(1, ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / length_squared))
    return start[0] + factor * delta_x, start[1] + factor * delta_y


def _clamp_to_hue_gamut(point: tuple[float, float], raw_gamut) -> tuple[float, float]:
    if not isinstance(raw_gamut, dict):
        return point
    gamut = tuple(_gamut_point(raw_gamut.get(color)) for color in ("red", "green", "blue"))
    if any(item is None for item in gamut):
        return point
    typed_gamut = gamut  # All entries are validated points after the check above.
    if _point_is_in_gamut(point, typed_gamut):
        return point
    candidates = [_nearest_point_on_segment(point, typed_gamut[index], typed_gamut[(index + 1) % 3]) for index in range(3)]
    return min(candidates, key=lambda candidate: (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2)


def _hue_xy_from_hex(value, gamut=None) -> dict[str, float]:
    """Convert browser sRGB to CIE XY and constrain it to the lamp's Hue gamut."""
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6 or any(character not in "0123456789abcdefABCDEF" for character in raw):
        raise ProviderError("Kies een geldige kleur.")
    channels = [int(raw[index:index + 2], 16) / 255 for index in range(0, 6, 2)]
    red, green, blue = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    x_value = red * 0.4124 + green * 0.3576 + blue * 0.1805
    y_value = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z_value = red * 0.0193 + green * 0.1192 + blue * 0.9505
    total = x_value + y_value + z_value
    if total <= 0:
        raise ProviderError("Zwart kan niet als Hue-kleur worden ingesteld. Schakel de lamp uit om zwart te gebruiken.")
    x, y = _clamp_to_hue_gamut((x_value / total, y_value / total), gamut)
    return {"x": round(x, 4), "y": round(y, 4)}


def _hue_hex_from_xy(raw_xy, brightness=None) -> str:
    """Convert a Hue XY color back to a browser color picker value."""
    point = _gamut_point(raw_xy)
    if not point or point[1] <= 0:
        return ""
    x, y = point
    try:
        luminance = max(0.01, min(1.0, float(brightness) / 100))
    except (TypeError, ValueError):
        luminance = 1.0
    z = 1.0 - x - y
    x_value, z_value = luminance * x / y, luminance * z / y
    # Inverse of the sRGB D65 matrix used in _hue_xy_from_hex.
    red = x_value * 3.2406 - luminance * 1.5372 - z_value * 0.4986
    green = -x_value * 0.9689 + luminance * 1.8758 + z_value * 0.0415
    blue = x_value * 0.0557 - luminance * 0.204 + z_value * 1.057
    largest = max(red, green, blue)
    if largest > 1:
        red, green, blue = red / largest, green / largest, blue / largest
    channels = [channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055 for channel in (red, green, blue)]
    return "#" + "".join(f"{round(max(0, min(1, channel)) * 255):02x}" for channel in channels)


def _hue_effect_attributes(light: dict) -> dict:
    """Expose only the effect values that a Hue light explicitly advertises."""
    for resource_name, action_key in (("effects_v2", "action"), ("effects", "effect")):
        effects = light.get(resource_name)
        if not isinstance(effects, dict):
            continue
        values = [str(value) for value in effects.get("effect_values", []) if isinstance(value, str)]
        if values:
            return {
                "supports_effects": True,
                "effect_values": values,
                "effect_current": str(effects.get("status") or "no_effect"),
                "effects_resource": resource_name,
                "effects_action_key": action_key,
            }
    return {"supports_effects": False, "effect_values": [], "effect_current": "", "effects_resource": "", "effects_action_key": ""}


def _hue_supports_color(resource: dict) -> bool:
    """Hue advertises color support by including the color capability object.

    Some bridge firmware versions return an empty object until a color is set,
    so its presence is more reliable than its current contents.
    """
    return isinstance(resource.get("color"), dict)


def arm_hue_bridge_link(connection: IntegrationConnection) -> None:
    if connection.provider != IntegrationConnection.Provider.HUE:
        raise ProviderError("Dit is geen Philips Hue-koppeling.")
    _hue_request(connection, "PUT", "/route/api/0/config", {"linkbutton": True})
    connection.status = "awaiting_bridge_link"
    connection.last_error = ""
    connection.save(update_fields=["status", "last_error", "updated_at"])


def finish_hue_bridge_link(connection: IntegrationConnection) -> None:
    if connection.provider != IntegrationConnection.Provider.HUE:
        raise ProviderError("Dit is geen Philips Hue-koppeling.")
    payload = _hue_request(connection, "POST", "/route/api", {"devicetype": "family-app#server"})
    entries = payload if isinstance(payload, list) else []
    username = next(
        (entry.get("success", {}).get("username") for entry in entries if isinstance(entry, dict) and entry.get("success", {}).get("username")),
        "",
    )
    if not username:
        raise ProviderError("De Hue Bridge is nog niet bevestigd. Druk op de fysieke knop en probeer opnieuw.")
    connection.settings = {**connection.settings, "bridge_username": username}
    connection.status = "needs_sync"
    connection.last_error = ""
    connection.save(update_fields=["settings", "status", "last_error", "updated_at"])


def sync_hue(connection: IntegrationConnection) -> dict:
    username = str(connection.settings.get("bridge_username") or "")
    if not username:
        raise ProviderError("Bevestig eerst de Philips Hue Bridge.")
    lights_payload = _hue_request(connection, "GET", "/route/clip/v2/resource/light")
    devices_payload = _hue_request(connection, "GET", "/route/clip/v2/resource/device")
    rooms_payload = _hue_request(connection, "GET", "/route/clip/v2/resource/room")
    zones_payload = _hue_request(connection, "GET", "/route/clip/v2/resource/zone")
    grouped_lights_payload = _hue_request(connection, "GET", "/route/clip/v2/resource/grouped_light")
    scenes_payload = _hue_request(connection, "GET", "/route/clip/v2/resource/scene")
    sensor_resources = {
        resource_type: _hue_optional_resource(connection, resource_type)
        for resource_type in ("motion", "temperature", "light_level", "contact", "button")
    }
    device_power_resources = _hue_optional_resource(connection, "device_power")
    connectivity_resources = _hue_optional_resource(connection, "zigbee_connectivity")
    lights = lights_payload.get("data") if isinstance(lights_payload, dict) else None
    devices = devices_payload.get("data") if isinstance(devices_payload, dict) else None
    if not isinstance(lights, list):
        raise ProviderError("Philips Hue leverde geen lampenlijst.")
    power_by_device, connectivity_by_device = {}, {}
    for power in device_power_resources:
        owner = power.get("owner") if isinstance(power.get("owner"), dict) else {}
        device_id = str(owner.get("rid") or "") if owner.get("rtype") == "device" else ""
        power_state = power.get("power_state") if isinstance(power.get("power_state"), dict) else {}
        if device_id:
            power_by_device[device_id] = {
                "hue_battery_level": power_state.get("battery_level"),
                "hue_battery_state": str(power_state.get("battery_state") or ""),
            }
    for connectivity in connectivity_resources:
        owner = connectivity.get("owner") if isinstance(connectivity.get("owner"), dict) else {}
        device_id = str(owner.get("rid") or "") if owner.get("rtype") == "device" else ""
        if device_id:
            connectivity_by_device[device_id] = {"hue_connectivity": str(connectivity.get("status") or "")}

    device_details, device_resource_details = {}, {}
    for device in devices if isinstance(devices, list) else []:
        if not isinstance(device, dict):
            continue
        metadata = device.get("metadata") if isinstance(device.get("metadata"), dict) else {}
        product_data = device.get("product_data") if isinstance(device.get("product_data"), dict) else {}
        details = {
            "hue_device_id": str(device.get("id") or ""),
            "hue_device_name": str(metadata.get("name") or "Hue lamp"),
            "hue_product_name": str(product_data.get("product_name") or product_data.get("model_id") or ""),
            "hue_model_id": str(product_data.get("model_id") or ""),
            "hue_manufacturer": str(product_data.get("manufacturer_name") or ""),
            **power_by_device.get(str(device.get("id") or ""), {}),
            **connectivity_by_device.get(str(device.get("id") or ""), {}),
        }
        for service in device.get("services", []):
            if not isinstance(service, dict) or not service.get("rtype") or not service.get("rid"):
                continue
            resource_type, resource_id = str(service["rtype"]), str(service["rid"])
            device_resource_details[(resource_type, resource_id)] = details
            if resource_type == "light":
                device_details[resource_id] = details
    device_lights = {
        str(device.get("id")): [str(service.get("rid")) for service in device.get("services", []) if isinstance(service, dict) and service.get("rtype") == "light" and service.get("rid")]
        for device in (devices if isinstance(devices, list) else [])
        if isinstance(device, dict) and device.get("id")
    }
    group_names, group_members, device_locations = {}, {}, {}
    for resource_type, payload in (("room", rooms_payload), ("zone", zones_payload)):
        for group in payload.get("data", []) if isinstance(payload, dict) else []:
            if not isinstance(group, dict) or not group.get("id"):
                continue
            group_id = str(group["id"])
            group_names[(resource_type, group_id)] = str(group.get("metadata", {}).get("name") or ("Hue kamer" if resource_type == "room" else "Hue zone"))
            members = []
            for child in group.get("children", []):
                if not isinstance(child, dict):
                    continue
                if child.get("rtype") == "device":
                    device_id = str(child.get("rid") or "")
                    members.extend(device_lights.get(device_id, []))
                    device_locations.setdefault(device_id, set()).add(group_names[(resource_type, group_id)])
                elif resource_type == "zone" and child.get("rtype") == "room":
                    room_member_ids = group_members.get(("room", str(child.get("rid") or "")), [])
                    members.extend(room_member_ids)
                    for device_id, light_ids in device_lights.items():
                        if set(light_ids).intersection(room_member_ids):
                            device_locations.setdefault(device_id, set()).add(group_names[(resource_type, group_id)])
            group_members[(resource_type, group_id)] = members

    light_profiles = {}
    for light in lights:
        if not isinstance(light, dict) or not light.get("id"):
            continue
        light_id = str(light["id"])
        device_details_for_light = device_details.get(light_id, {})
        light_profiles[light_id] = {
            "name": device_details_for_light.get("hue_device_name") or str(light.get("metadata", {}).get("name") or f"Hue lamp {light_id}"),
            "supports_color": _hue_supports_color(light),
            "color_hex": _hue_hex_from_xy(
                light.get("color", {}).get("xy") if isinstance(light.get("color"), dict) else None,
                light.get("dimming", {}).get("brightness") if isinstance(light.get("dimming"), dict) else None,
            ),
        }

    seen, lights_count, groups_count, scenes_count, sensors_count = set(), 0, 0, 0, 0
    for light in lights:
        if not isinstance(light, dict):
            continue
        light_id = str(light.get("id") or "")
        if not light_id:
            continue
        on = light.get("on") if isinstance(light.get("on"), dict) else {}
        dimming = light.get("dimming") if isinstance(light.get("dimming"), dict) else {}
        color_temperature = light.get("color_temperature") if isinstance(light.get("color_temperature"), dict) else {}
        mirek_schema = color_temperature.get("mirek_schema") if isinstance(color_temperature.get("mirek_schema"), dict) else {}
        gradient = light.get("gradient") if isinstance(light.get("gradient"), dict) else {}
        attributes = {
            "hue_light_id": light_id,
            "brightness": dimming.get("brightness"),
            "supports_dimming": bool(dimming),
            "color_temperature": color_temperature.get("mirek"),
            "supports_color_temperature": bool(mirek_schema),
            "color_temperature_min": mirek_schema.get("mirek_minimum"),
            "color_temperature_max": mirek_schema.get("mirek_maximum"),
            "supports_color": _hue_supports_color(light),
            "color_gamut": light.get("color", {}).get("gamut") if isinstance(light.get("color"), dict) else None,
            "color_xy": light.get("color", {}).get("xy") if isinstance(light.get("color"), dict) else None,
            "color_hex": _hue_hex_from_xy(light.get("color", {}).get("xy"), dimming.get("brightness")) if isinstance(light.get("color"), dict) else "",
            "gradient_points": len(gradient.get("points", [])) if isinstance(gradient.get("points"), list) else 0,
            "hue_resource_type": "light",
            "type": light.get("type", "light"),
            **device_details.get(light_id, {}),
            **_hue_effect_attributes(light),
        }
        if attributes.get("hue_device_id"):
            attributes["hue_locations"] = sorted(device_locations.get(attributes["hue_device_id"], []))
        entity_id = f"hue.{connection.id}.{light_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.HUE,
                "domain": "light",
                "name": device_details.get(light_id, {}).get("hue_device_name") or str(light.get("metadata", {}).get("name") or f"Hue lamp {light_id}"),
                "state": "on" if on.get("on") else "off",
                "attributes": attributes,
                "is_available": attributes.get("hue_connectivity") != "disconnected",
                "is_supported": True,
            },
        )
        seen.add(entity_id)
        lights_count += 1

    grouped_lights = grouped_lights_payload.get("data") if isinstance(grouped_lights_payload, dict) else []
    for grouped_light in grouped_lights if isinstance(grouped_lights, list) else []:
        if not isinstance(grouped_light, dict) or not grouped_light.get("id"):
            continue
        owner = grouped_light.get("owner") if isinstance(grouped_light.get("owner"), dict) else {}
        owner_type, owner_id = str(owner.get("rtype") or ""), str(owner.get("rid") or "")
        if owner_type not in {"room", "zone"} or not owner_id:
            continue
        group_id = str(grouped_light["id"])
        on = grouped_light.get("on") if isinstance(grouped_light.get("on"), dict) else {}
        dimming = grouped_light.get("dimming") if isinstance(grouped_light.get("dimming"), dict) else {}
        color_temperature = grouped_light.get("color_temperature") if isinstance(grouped_light.get("color_temperature"), dict) else {}
        mirek_schema = color_temperature.get("mirek_schema") if isinstance(color_temperature.get("mirek_schema"), dict) else {}
        color = grouped_light.get("color") if isinstance(grouped_light.get("color"), dict) else {}
        name = group_names.get((owner_type, owner_id), "Hue kamer" if owner_type == "room" else "Hue zone")
        member_profiles = [light_profiles[light_id] for light_id in group_members.get((owner_type, owner_id), []) if light_id in light_profiles]
        member_names = [profile["name"] for profile in member_profiles]
        supports_member_color = any(profile["supports_color"] for profile in member_profiles)
        member_color_hexes = sorted({profile["color_hex"] for profile in member_profiles if profile["color_hex"]})
        group_color_hex = _hue_hex_from_xy(color.get("xy"), dimming.get("brightness")) or (member_color_hexes[0] if len(member_color_hexes) == 1 else "")
        entity_id = f"hue.{connection.id}.grouped_light.{group_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.HUE,
                "domain": "group",
                "name": name,
                "state": "on" if on.get("on") else "off",
                "attributes": {
                    "hue_grouped_light_id": group_id,
                    "hue_resource_type": "grouped_light",
                    "hue_group_type": owner_type,
                    "brightness": dimming.get("brightness"),
                    "supports_dimming": bool(dimming),
                    "color_temperature": color_temperature.get("mirek"),
                    "supports_color_temperature": bool(mirek_schema),
                    "color_temperature_min": mirek_schema.get("mirek_minimum"),
                    "color_temperature_max": mirek_schema.get("mirek_maximum"),
                    # Some bridges omit color on a grouped_light while the
                    # individual member lights do advertise it. Group control
                    # still supports a color command in that situation.
                    "supports_color": _hue_supports_color(grouped_light) or supports_member_color,
                    "color_gamut": color.get("gamut"),
                    "color_xy": color.get("xy"),
                    "color_hex": group_color_hex,
                    "color_mixed": len(member_color_hexes) > 1,
                    "member_color_hexes": member_color_hexes,
                    "member_count": len(group_members.get((owner_type, owner_id), [])),
                    "member_light_ids": group_members.get((owner_type, owner_id), []),
                    "member_names": member_names,
                    **_hue_effect_attributes(grouped_light),
                },
                "is_available": True,
                "is_supported": True,
            },
        )
        seen.add(entity_id)
        groups_count += 1

    sensor_labels = {
        "motion": "Beweging",
        "temperature": "Temperatuur",
        "light_level": "Lichtniveau",
        "contact": "Contact",
        "button": "Knop",
    }
    for resource_type, resources in sensor_resources.items():
        for resource in resources:
            resource_id = str(resource.get("id") or "")
            if not resource_id:
                continue
            details = device_resource_details.get((resource_type, resource_id), {})
            sensor_name = details.get("hue_device_name") or str(resource.get("metadata", {}).get("name") or "Hue sensor")
            state, active = _hue_sensor_state(resource_type, resource)
            attributes = {
                "hue_sensor_id": resource_id,
                "hue_resource_type": resource_type,
                "hue_sensor_kind": sensor_labels[resource_type],
                "sensor_active": active,
                **details,
            }
            if attributes.get("hue_device_id"):
                attributes["hue_locations"] = sorted(device_locations.get(attributes["hue_device_id"], []))
            entity_id = f"hue.{connection.id}.sensor.{resource_type}.{resource_id}"
            HomeEntity.objects.update_or_create(
                household=connection.household,
                entity_id=entity_id,
                defaults={
                    "connection": connection,
                    "source": HomeEntity.Source.HUE,
                    "domain": "sensor",
                    "name": f"{sensor_name} · {sensor_labels[resource_type]}",
                    "state": state,
                    "attributes": attributes,
                    "is_available": attributes.get("hue_connectivity") != "disconnected",
                    "is_supported": False,
                },
            )
            seen.add(entity_id)
            sensors_count += 1

    scenes = scenes_payload.get("data") if isinstance(scenes_payload, dict) else []
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict) or not scene.get("id"):
            continue
        scene_id = str(scene["id"])
        group = scene.get("group") if isinstance(scene.get("group"), dict) else {}
        group_name = group_names.get((str(group.get("rtype") or ""), str(group.get("rid") or "")), "Hue")
        status = scene.get("status") if isinstance(scene.get("status"), dict) else {}
        entity_id = f"hue.{connection.id}.scene.{scene_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.HUE,
                "domain": "scene",
                "name": str(scene.get("metadata", {}).get("name") or "Hue scène"),
                "state": "active" if status.get("active") else "idle",
                "attributes": {"hue_scene_id": scene_id, "hue_resource_type": "scene", "hue_group_name": group_name},
                "is_available": True,
                "is_supported": True,
            },
        )
        seen.add(entity_id)
        scenes_count += 1
    HomeEntity.objects.for_household(connection.household).filter(
        source=HomeEntity.Source.HUE,
        connection=connection,
    ).exclude(entity_id__in=seen).update(is_available=False)
    return {"lights": lights_count, "groups": groups_count, "sensors": sensors_count, "scenes": scenes_count}


def control_hue_light(entity: HomeEntity, action: str, brightness=None) -> str:
    connection = entity.connection
    if entity.source != HomeEntity.Source.HUE or not connection:
        raise ProviderError("Deze Hue-lamp is niet beschikbaar.")
    resource_type = str(entity.attributes.get("hue_resource_type") or "light")
    resource_id = str(entity.attributes.get("hue_light_id") or entity.attributes.get("hue_grouped_light_id") or entity.attributes.get("hue_scene_id") or "")
    if not resource_id:
        raise ProviderError("Deze Hue-lamp heeft geen geldige apparaatidentificatie.")
    if resource_type == "scene":
        if action != "activate":
            raise ProviderError("Deze Philips Hue-bediening is niet beschikbaar.")
        path, payload, detail = f"/route/clip/v2/resource/scene/{resource_id}", {"recall": {"action": "active"}}, "Scène gestart."
    elif action == "on":
        payload, detail = {"on": {"on": True}}, "Ingeschakeld."
    elif action == "off":
        payload, detail = {"on": {"on": False}}, "Uitgeschakeld."
    elif action == "brightness":
        try:
            value = float(brightness)
        except (TypeError, ValueError) as error:
            raise ProviderError("Kies een geldige helderheid.") from error
        if not 0 <= value <= 100:
            raise ProviderError("Helderheid moet tussen 0 en 100 liggen.")
        payload, detail = {"on": {"on": True}, "dimming": {"brightness": value}}, f"Helderheid ingesteld op {round(value)}%."
    elif action == "color_temperature":
        try:
            value = int(float(brightness))
        except (TypeError, ValueError) as error:
            raise ProviderError("Kies een geldige kleurtemperatuur.") from error
        minimum = int(entity.attributes.get("color_temperature_min") or 153)
        maximum = int(entity.attributes.get("color_temperature_max") or 500)
        if not minimum <= value <= maximum:
            raise ProviderError("Kies een kleurtemperatuur binnen het bereik van deze lamp.")
        payload, detail = {"on": {"on": True}, "color_temperature": {"mirek": value}}, "Kleurtemperatuur ingesteld."
    elif action == "color":
        if not entity.attributes.get("supports_color"):
            raise ProviderError("Deze lamp ondersteunt geen kleurbediening.")
        payload, detail = {"on": {"on": True}, "color": {"xy": _hue_xy_from_hex(brightness, entity.attributes.get("color_gamut"))}}, "Kleur ingesteld."
    elif action == "effect":
        effect = str(brightness or "")
        values = entity.attributes.get("effect_values") if isinstance(entity.attributes.get("effect_values"), list) else []
        if effect not in values:
            raise ProviderError("Dit lichteffect is niet beschikbaar voor deze lamp.")
        resource_name = str(entity.attributes.get("effects_resource") or "")
        action_key = str(entity.attributes.get("effects_action_key") or "")
        if resource_name not in {"effects_v2", "effects"} or action_key not in {"action", "effect"}:
            raise ProviderError("Deze lamp ondersteunt geen lichteffecten.")
        payload = {resource_name: {action_key: effect}}
        detail = "Lichteffect uitgeschakeld." if effect == "no_effect" else f"Lichteffect {effect.replace('_', ' ')} ingesteld."
    else:
        raise ProviderError("Deze Philips Hue-bediening is niet beschikbaar.")
    if not connection.settings.get("bridge_username"):
        raise ProviderError("Bevestig eerst de Philips Hue Bridge.")
    if resource_type != "scene":
        resource_type = "grouped_light" if resource_type == "grouped_light" else "light"
        path = f"/route/clip/v2/resource/{resource_type}/{resource_id}"
    _hue_request(connection, "PUT", path, payload)
    return detail


def _outlook_token(connection: IntegrationConnection) -> str:
    data = connection.settings
    if _stored_outlook_token_is_current(data):
        return decrypt(data["access_token"])
    from integrations.services import get_app_config
    client_id, client_secret, config = get_app_config(connection.household, "outlook")
    response = requests.post(f"https://login.microsoftonline.com/{config.get('tenant_id', 'consumers')}/oauth2/v2.0/token", data={"client_id": client_id, "client_secret": client_secret, "refresh_token": decrypt(connection.secret_encrypted), "grant_type": "refresh_token"}, timeout=20)
    payload = _safe_response_json(response, "Outlook")
    if not payload.get("access_token"):
        raise ProviderError("Outlook-token vernieuwen mislukt.")
    connection.secret_encrypted = encrypt(payload.get("refresh_token") or decrypt(connection.secret_encrypted))
    connection.settings = {**data, "access_token": encrypt(payload["access_token"]), "expires_at": (timezone.now() + timedelta(seconds=int(payload.get("expires_in", 3600)) - 60)).isoformat()}
    connection.save(update_fields=["secret_encrypted", "settings", "updated_at"])
    return payload["access_token"]


def sync_outlook(connection: IntegrationConnection) -> dict:
    token = _outlook_token(connection)
    headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="Europe/Amsterdam"'}
    calendars_response = _request_with_retry("GET", "https://graph.microsoft.com/v1.0/me/calendars?$select=id,name", headers=headers, timeout=20)
    calendars = _safe_response_json(calendars_response, "Outlook").get("value", [])
    start, end = timezone.now() - timedelta(days=14), timezone.now() + timedelta(days=120)
    total, synced_calendars = 0, 0
    for calendar in calendars:
        calendar_id = calendar.get("id")
        if not calendar_id:
            continue
        source, created = CalendarSource.objects.get_or_create(
            household=connection.household,
            provider=CalendarSource.Provider.OUTLOOK,
            external_id=calendar_id,
            defaults={"name": calendar.get("name", "Outlook agenda"), "owner": connection.user, "is_read_only": True},
        )
        if not created and source.name != calendar.get("name", source.name):
            source.name = calendar.get("name", source.name)
            source.save(update_fields=["name", "updated_at"])
        if not source.is_enabled:
            continue
        url = f"https://graph.microsoft.com/v1.0/me/calendars/{calendar['id']}/calendarView"
        params = {"startDateTime": start.isoformat(), "endDateTime": end.isoformat(), "$select": "id,subject,start,end,isAllDay,location"}
        while url:
            response = _request_with_retry("GET", url, headers=headers, params=params if url == f"https://graph.microsoft.com/v1.0/me/calendars/{calendar['id']}/calendarView" else None, timeout=30)
            payload = _safe_response_json(response, "Outlook")
            for event in payload.get("value", []):
                if not event.get("id"):
                    continue
                starts_at = _parse_graph_datetime(event.get("start", {}))
                ends_at = _parse_graph_datetime(event.get("end", {}))
                CalendarEvent.objects.update_or_create(household=connection.household, source=source, external_id=event["id"], defaults={"title": event.get("subject") or "Outlook afspraak", "starts_at": starts_at, "ends_at": ends_at, "is_all_day": bool(event.get("isAllDay")), "location": event.get("location", {}).get("displayName", "")})
                total += 1
            url = payload.get("@odata.nextLink")
            params = None
        source.last_sync_at = timezone.now()
        source.save(update_fields=["last_sync_at", "updated_at"])
        synced_calendars += 1
    return {"calendars": synced_calendars, "events": total}


def _outlook_headers(connection: IntegrationConnection) -> dict:
    return {
        "Authorization": f"Bearer {_outlook_token(connection)}",
        "Prefer": 'outlook.body-content-type="text"',
        "Content-Type": "application/json",
    }


def _outlook_mail_summary(message: dict) -> dict:
    sender = (message.get("from") or {}).get("emailAddress", {})
    return {
        "id": message.get("id"),
        "subject": message.get("subject") or "",
        "from": sender.get("address", ""),
        "from_name": sender.get("name", ""),
        "received_at": message.get("receivedDateTime"),
        "is_read": bool(message.get("isRead")),
        "preview": message.get("bodyPreview", ""),
    }


def outlook_mail_overview(connection: IntegrationConnection, folder: str = "inbox", unread_only: bool = False, top: int = 20) -> list[dict]:
    """List recent messages in a mail folder (default inbox), newest first."""
    headers = _outlook_headers(connection)
    params = {"$select": "id,subject,from,receivedDateTime,isRead,bodyPreview", "$top": min(top, 50), "$orderby": "receivedDateTime desc"}
    if unread_only:
        params["$filter"] = "isRead eq false"
    response = _request_with_retry("GET", f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages", headers=headers, params=params, timeout=20)
    payload = _safe_response_json(response, "Outlook")
    return [_outlook_mail_summary(message) for message in payload.get("value", [])]


def outlook_mail_read(connection: IntegrationConnection, message_id: str) -> dict:
    """Read the full text content of one message, given its id (from outlook_mail_overview)."""
    headers = _outlook_headers(connection)
    params = {"$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,body"}
    response = _request_with_retry("GET", f"https://graph.microsoft.com/v1.0/me/messages/{message_id}", headers=headers, params=params, timeout=20)
    message = _safe_response_json(response, "Outlook")
    summary = _outlook_mail_summary(message)
    summary["to"] = [recipient.get("emailAddress", {}).get("address", "") for recipient in message.get("toRecipients", [])]
    summary["cc"] = [recipient.get("emailAddress", {}).get("address", "") for recipient in message.get("ccRecipients", [])]
    summary["body"] = (message.get("body") or {}).get("content", "")
    return summary


def outlook_mail_send(connection: IntegrationConnection, to: list[str], subject: str, body: str, cc: list[str] | None = None) -> None:
    """Send a new email."""
    headers = _outlook_headers(connection)
    message = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": address}} for address in to],
    }
    if cc:
        message["cc"] = [{"emailAddress": {"address": address}} for address in cc]
    response = _request_with_retry("POST", "https://graph.microsoft.com/v1.0/me/sendMail", headers=headers, json={"message": message}, timeout=20)
    _safe_response_json(response, "Outlook")


def outlook_mail_reply(connection: IntegrationConnection, message_id: str, comment: str, reply_all: bool = False) -> None:
    """Reply to an existing message, given its id (from outlook_mail_overview/outlook_mail_read)."""
    headers = _outlook_headers(connection)
    action = "replyAll" if reply_all else "reply"
    response = _request_with_retry("POST", f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/{action}", headers=headers, json={"comment": comment}, timeout=20)
    _safe_response_json(response, "Outlook")


def _outlook_todo_task_summary(task: dict, list_id: str) -> dict:
    due = (task.get("dueDateTime") or {}).get("dateTime")
    return {
        "id": task.get("id"),
        "list_id": list_id,
        "title": task.get("title") or "",
        "status": task.get("status", "notStarted"),
        "due_at": due,
        "notes": (task.get("body") or {}).get("content", ""),
    }


def outlook_todo_lists(connection: IntegrationConnection) -> list[dict]:
    """List the household member's Microsoft To Do lists."""
    headers = _outlook_headers(connection)
    response = _request_with_retry("GET", "https://graph.microsoft.com/v1.0/me/todo/lists", headers=headers, params={"$select": "id,displayName"}, timeout=20)
    payload = _safe_response_json(response, "Outlook")
    return [{"id": entry.get("id"), "name": entry.get("displayName", "")} for entry in payload.get("value", [])]


def outlook_todo_tasks(connection: IntegrationConnection, list_id: str, include_completed: bool = False) -> list[dict]:
    """List tasks in a Microsoft To Do list, given its id (from outlook_todo_lists)."""
    headers = _outlook_headers(connection)
    params = {"$select": "id,title,status,dueDateTime,body"}
    if not include_completed:
        params["$filter"] = "status ne 'completed'"
    response = _request_with_retry("GET", f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks", headers=headers, params=params, timeout=20)
    payload = _safe_response_json(response, "Outlook")
    return [_outlook_todo_task_summary(task, list_id) for task in payload.get("value", [])]


def outlook_todo_task_create(connection: IntegrationConnection, list_id: str, title: str, due_date: str | None = None, notes: str | None = None) -> dict:
    """Create a new task in a Microsoft To Do list, given its id (from outlook_todo_lists)."""
    headers = _outlook_headers(connection)
    body = {"title": title}
    if due_date:
        body["dueDateTime"] = {"dateTime": due_date, "timeZone": "Europe/Amsterdam"}
    if notes:
        body["body"] = {"content": notes, "contentType": "text"}
    response = _request_with_retry("POST", f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks", headers=headers, json=body, timeout=20)
    task = _safe_response_json(response, "Outlook")
    return _outlook_todo_task_summary(task, list_id)


def outlook_todo_task_update(connection: IntegrationConnection, list_id: str, task_id: str, title: str | None = None, due_date: str | None = None, notes: str | None = None, status: str | None = None) -> dict:
    """Partial update of an existing To Do task, given the list and task id."""
    headers = _outlook_headers(connection)
    body: dict = {}
    if title is not None:
        body["title"] = title
    if due_date is not None:
        body["dueDateTime"] = {"dateTime": due_date, "timeZone": "Europe/Amsterdam"} if due_date else None
    if notes is not None:
        body["body"] = {"content": notes, "contentType": "text"}
    if status is not None:
        body["status"] = status
    if not body:
        raise ProviderError("Geef minstens één veld op om te wijzigen.")
    response = _request_with_retry("PATCH", f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}", headers=headers, json=body, timeout=20)
    task = _safe_response_json(response, "Outlook")
    return _outlook_todo_task_summary(task, list_id)


def _bunq_request(url: str, method: str, token: str, private_key, body: dict | None = None):
    raw = json.dumps(body) if body else ""
    signature = private_key.sign(raw.encode(), padding.PKCS1v15(), hashes.SHA256())
    headers = {"Cache-Control": "no-cache", "User-Agent": "Family App", "X-Bunq-Language": "nl_NL", "X-Bunq-Region": "nl_NL", "X-Bunq-Geolocation": "0 0 0 0 NL", "X-Bunq-Client-Request-Id": str(uuid.uuid4()), "X-Bunq-Client-Signature": __import__("base64").b64encode(signature).decode()}
    if token:
        headers["X-Bunq-Client-Authentication"] = token
    if body:
        headers["Content-Type"] = "application/json"
    response = requests.request(method, url, headers=headers, data=raw if body else None, timeout=30)
    return _safe_response_json(response, "bunq")


def _bunq_items(payload):
    return payload.get("Response", []) if isinstance(payload, dict) else []


def _bunq_user_ids(payload: dict) -> list[int]:
    return list({entry[key].get("id") for entry in _bunq_items(payload) for key in ("UserPerson", "UserCompany", "UserApiKey") if isinstance(entry.get(key), dict) and entry[key].get("id")})


def _bunq_account_data(item: dict) -> dict | None:
    return next((value for key, value in item.items() if key.startswith("MonetaryAccount") and isinstance(value, dict)), None)


def sync_bunq(connection: IntegrationConnection) -> dict:
    token = decrypt(connection.secret_encrypted)
    environment = connection.settings.get("environment", "production")
    base = "https://public-api.sandbox.bunq.com/v1" if environment == "sandbox" else "https://api.bunq.com/v1"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    installation = _bunq_request(f"{base}/installation", "POST", "", private_key, {"client_public_key": public_pem})
    installation_token = next((entry.get("Token", {}).get("token") for entry in _bunq_items(installation) if entry.get("Token")), "")
    _bunq_request(f"{base}/device-server", "POST", installation_token, private_key, {"description": "Family App", "secret": token, "permitted_ips": ["*"]})
    session = _bunq_request(f"{base}/session-server", "POST", installation_token, private_key, {"secret": token})
    session_token = next((entry.get("Token", {}).get("token") for entry in _bunq_items(session) if entry.get("Token")), "")
    if not session_token:
        raise ProviderError("bunq sessie kon niet worden gemaakt.")
    users = _bunq_user_ids(session)
    if not users:
        users = _bunq_user_ids(_bunq_request(f"{base}/user", "GET", session_token, private_key))
    if not users:
        raise ProviderError("bunq gaf geen toegankelijk gebruikersprofiel terug.")
    bank_connection, _ = BankConnection.objects.get_or_create(household=connection.household, provider="bunq", external_reference=str(connection.id), defaults={"display_name": "bunq"})
    account_count, transaction_count = 0, 0
    seen_accounts: set[str] = set()
    account_endpoints = (
        "monetary-account",
        "monetary-account-bank",
        "monetary-account-savings",
        "monetary-account-savings-external",
        "monetary-account-joint",
        "monetary-account-external",
        "monetary-account-card",
    )
    for user_id in users:
        for endpoint in account_endpoints:
            try:
                account_payload = _bunq_request(f"{base}/user/{user_id}/{endpoint}?count=200", "GET", session_token, private_key)
            except ProviderError:
                if endpoint == "monetary-account":
                    raise
                continue
            for item in _bunq_items(account_payload):
                account_data = _bunq_account_data(item)
                if not account_data or not account_data.get("id"):
                    continue
                provider_id = str(account_data["id"])
                if provider_id in seen_accounts:
                    continue
                seen_accounts.add(provider_id)
                aliases = account_data.get("alias", [])
                iban = next((alias.get("value", "") for alias in aliases if alias.get("type") == "IBAN"), "")
                balance = account_data.get("balance", {})
                account, _ = BankAccount.objects.update_or_create(household=connection.household, connection=bank_connection, provider_account_id=provider_id, defaults={"name": account_data.get("description", "bunq rekening"), "iban": iban, "currency": balance.get("currency", "EUR"), "balance": Decimal(str(balance.get("value", "0")))})
                account_count += 1
                try:
                    payments = _bunq_request(f"{base}/user/{user_id}/monetary-account/{provider_id}/payment?count=200", "GET", session_token, private_key)
                except ProviderError:
                    continue
                for response_item in _bunq_items(payments):
                    payment = response_item.get("Payment")
                    if not payment or not payment.get("id"):
                        continue
                    amount = payment.get("amount", {})
                    alias = payment.get("counterparty_alias", {})
                    _, created = Transaction.objects.update_or_create(household=connection.household, account=account, provider_transaction_id=f"{provider_id}:{payment['id']}", defaults={"booked_at": payment.get("created", "")[:10], "description": payment.get("description", "bunq transactie"), "counterparty": alias.get("display_name") or alias.get("value", ""), "amount": Decimal(str(amount.get("value", "0"))), "currency": amount.get("currency", "EUR"), "metadata": {"source": "bunq", "raw": payment}})
                    transaction_count += int(created)
    return {"accounts": account_count, "new_transactions": transaction_count}


def _dropbox_access_token(connection: IntegrationConnection) -> str:
    """Return a valid Dropbox access token, refreshing it first if it has expired."""
    from django.utils.dateparse import parse_datetime

    from integrations.services import DROPBOX_OAUTH_TOKEN_URL, get_app_config

    stored = connection.settings if isinstance(connection.settings, dict) else {}
    expires_at = parse_datetime(stored.get("expires_at") or "") if stored.get("expires_at") else None
    if expires_at and timezone.now() < expires_at and stored.get("access_token"):
        return decrypt(stored["access_token"])

    refresh_token = decrypt(connection.secret_encrypted) if connection.secret_encrypted else ""
    if not refresh_token:
        raise ProviderError("Dropbox-koppeling mist een refresh token. Koppel Dropbox opnieuw.")
    client_id, client_secret, _ = get_app_config(connection.household, "dropbox")
    if not client_id or not client_secret:
        raise ProviderError("Dropbox-appgegevens ontbreken.")
    response = requests.post(
        DROPBOX_OAUTH_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(client_id, client_secret),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderError("Dropbox gaf geen geldige reactie bij het vernieuwen van de toegang.") from error
    if not response.ok or not payload.get("access_token"):
        raise ProviderError("Dropbox-toegang vernieuwen is mislukt. Koppel Dropbox opnieuw.")
    new_expires_at = timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 14400)) - 60, 60))
    connection.settings = {**stored, "access_token": encrypt(payload["access_token"]), "expires_at": new_expires_at.isoformat()}
    connection.save(update_fields=["settings", "updated_at"])
    return payload["access_token"]


def _dropbox_list_folder(access_token: str, path: str, *, recursive: bool, page_limit: int) -> list[dict]:
    response = requests.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"path": path, "recursive": recursive, "include_deleted": False, "limit": page_limit},
        timeout=20,
    )
    if not response.ok:
        raise ProviderError("Dropbox kon de bestandenlijst niet ophalen.")
    return response.json().get("entries", [])


def _dropbox_entry_summary(entry: dict) -> dict:
    return {
        "name": entry.get("name"),
        "path": entry.get("path_display"),
        "type": entry.get(".tag"),
        "modified": entry.get("server_modified"),
        "size": entry.get("size"),
    }


def dropbox_overview(connection: IntegrationConnection) -> list[dict]:
    """List the top-level folders and files in the household's Dropbox — a fast, single-call
    table of contents. Deliberately shallow: whole-account recency scans proved unreliable for
    accounts with deep or shared folder structures (a sports club's shared drive can bury its
    files many levels down, silently starving a bounded recursive walk). Use dropbox_list or
    dropbox_search to go deeper once you know where to look.
    """
    access_token = _dropbox_access_token(connection)
    entries = _dropbox_list_folder(access_token, "", recursive=False, page_limit=200)
    return [_dropbox_entry_summary(entry) for entry in entries]


def dropbox_list_folder_contents(connection: IntegrationConnection, path: str) -> list[dict]:
    """List the direct contents (folders and files, one level deep) of a specific Dropbox path."""
    access_token = _dropbox_access_token(connection)
    entries = _dropbox_list_folder(access_token, path, recursive=False, page_limit=200)
    return [_dropbox_entry_summary(entry) for entry in entries]


def dropbox_search(connection: IntegrationConnection, query: str, path: str = "", limit: int = 20) -> list[dict]:
    """Search the household's Dropbox by filename (and, where Dropbox supports it, content) —
    server-side search, so it isn't limited by folder depth the way listing is."""
    access_token = _dropbox_access_token(connection)
    body = {"query": query, "options": {"max_results": min(limit, 100), "file_status": "active"}}
    if path:
        body["options"]["path"] = path
    response = requests.post(
        "https://api.dropboxapi.com/2/files/search_v2",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=body,
        timeout=20,
    )
    if not response.ok:
        raise ProviderError("Dropbox kon niet doorzocht worden.")
    matches = response.json().get("matches", [])
    entries = [match["metadata"]["metadata"] for match in matches if match.get("metadata", {}).get(".tag") == "metadata"]
    return [_dropbox_entry_summary(entry) for entry in entries[:limit]]


DROPBOX_TEXT_EXTENSIONS = {"txt", "md", "csv", "json"}
DROPBOX_DOCUMENT_EXTENSIONS = {"pdf", "docx"}
DROPBOX_MAX_READ_BYTES = 20 * 1024 * 1024
DROPBOX_MAX_READ_CHARS = 20000


def _extract_pdf_text(content: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx_text(content: bytes) -> str:
    import io

    import docx

    document = docx.Document(io.BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def dropbox_read_file_text(connection: IntegrationConnection, path: str) -> dict:
    """Download a specific Dropbox file and extract its text content, for AI context.

    Only plain-text (txt/md/csv/json) and document (pdf/docx) formats are supported — there is
    no support for reading photos, video, audio, or spreadsheets, and file content is never
    proxied for those. Files above DROPBOX_MAX_READ_BYTES are refused outright to bound memory
    and latency; extracted text beyond DROPBOX_MAX_READ_CHARS is truncated.
    """
    access_token = _dropbox_access_token(connection)
    meta_response = requests.post(
        "https://api.dropboxapi.com/2/files/get_metadata",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"path": path},
        timeout=20,
    )
    if not meta_response.ok:
        raise ProviderError("Dropbox kon de bestandsinfo niet ophalen.")
    metadata = meta_response.json()
    if metadata.get(".tag") != "file":
        raise ProviderError("Dit pad is geen bestand.")
    name = str(metadata.get("name") or "")
    size = int(metadata.get("size") or 0)
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if extension not in DROPBOX_TEXT_EXTENSIONS and extension not in DROPBOX_DOCUMENT_EXTENSIONS:
        supported = ", ".join(sorted(DROPBOX_TEXT_EXTENSIONS | DROPBOX_DOCUMENT_EXTENSIONS))
        raise ProviderError(f"Bestandstype '.{extension}' wordt niet ondersteund voor tekst lezen (alleen {supported}).")
    if size > DROPBOX_MAX_READ_BYTES:
        raise ProviderError(f"Bestand is te groot om te lezen ({size // (1024 * 1024)} MB, maximum {DROPBOX_MAX_READ_BYTES // (1024 * 1024)} MB).")

    download_response = requests.post(
        "https://content.dropboxapi.com/2/files/download",
        headers={"Authorization": f"Bearer {access_token}", "Dropbox-API-Arg": json.dumps({"path": path})},
        timeout=30,
    )
    if not download_response.ok:
        raise ProviderError("Dropbox kon het bestand niet downloaden.")
    content = download_response.content

    if extension in DROPBOX_TEXT_EXTENSIONS:
        text = content.decode("utf-8", errors="replace")
    elif extension == "pdf":
        text = _extract_pdf_text(content)
    else:
        text = _extract_docx_text(content)

    truncated = len(text) > DROPBOX_MAX_READ_CHARS
    return {
        "name": name,
        "path": metadata.get("path_display"),
        "text": text[:DROPBOX_MAX_READ_CHARS],
        "truncated": truncated,
    }


DROPBOX_MAX_RAW_BYTES = 5 * 1024 * 1024


def dropbox_download_file_raw(connection: IntegrationConnection, path: str) -> dict:
    """Download any Dropbox file's raw bytes (base64-encoded), regardless of format.

    Unlike dropbox_read_file_text, this does no text extraction — it hands back the file
    exactly as it is, so the caller can parse formats FamilyApp doesn't understand itself
    (spreadsheets, presentations, images). Bounded much tighter than the text-read path
    (DROPBOX_MAX_RAW_BYTES vs DROPBOX_MAX_READ_BYTES) because base64 inflates size by ~33%
    and the result ultimately has to fit in an LLM's context.
    """
    access_token = _dropbox_access_token(connection)
    meta_response = requests.post(
        "https://api.dropboxapi.com/2/files/get_metadata",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"path": path},
        timeout=20,
    )
    if not meta_response.ok:
        raise ProviderError("Dropbox kon de bestandsinfo niet ophalen.")
    metadata = meta_response.json()
    if metadata.get(".tag") != "file":
        raise ProviderError("Dit pad is geen bestand.")
    name = str(metadata.get("name") or "")
    size = int(metadata.get("size") or 0)
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if size > DROPBOX_MAX_RAW_BYTES:
        raise ProviderError(f"Bestand is te groot om ruw te lezen ({size // (1024 * 1024)} MB, maximum {DROPBOX_MAX_RAW_BYTES // (1024 * 1024)} MB).")

    download_response = requests.post(
        "https://content.dropboxapi.com/2/files/download",
        headers={"Authorization": f"Bearer {access_token}", "Dropbox-API-Arg": json.dumps({"path": path})},
        timeout=30,
    )
    if not download_response.ok:
        raise ProviderError("Dropbox kon het bestand niet downloaden.")

    return {
        "name": name,
        "path": metadata.get("path_display"),
        "extension": extension,
        "size": size,
        "content_base64": base64.b64encode(download_response.content).decode("ascii"),
    }


def _decode_mime_header(value: str) -> str:
    if not value:
        return ""
    decoded = ""
    for text, charset in decode_header(value):
        decoded += text.decode(charset or "utf-8", errors="replace") if isinstance(text, bytes) else text
    return decoded


def _imap_client(connection: IntegrationConnection) -> imaplib.IMAP4:
    settings = connection.settings
    host = settings.get("host", "")
    port = int(settings.get("port", 993))
    password = decrypt(connection.secret_encrypted)
    try:
        client = imaplib.IMAP4_SSL(host, port) if settings.get("use_ssl", True) else imaplib.IMAP4(host, port)
        client.login(connection.external_account, password)
    except (imaplib.IMAP4.error, OSError) as error:
        raise ProviderError(f"IMAP-verbinding mislukt: {error}") from error
    return client


def test_imap_login(host: str, port: int, use_ssl: bool, username: str, password: str) -> None:
    """Verify IMAP credentials work without persisting anything. Raises ProviderError on failure."""
    try:
        client = imaplib.IMAP4_SSL(host, port, timeout=15) if use_ssl else imaplib.IMAP4(host, port, timeout=15)
        client.login(username, password)
        client.logout()
    except (imaplib.IMAP4.error, OSError) as error:
        raise ProviderError(f"Inloggen bij de IMAP-server is mislukt: {error}") from error


def _extract_plain_text(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except (LookupError, ValueError):
                    continue
        return ""
    if message.get_content_type() == "text/plain":
        try:
            return message.get_payload(decode=True).decode(message.get_content_charset() or "utf-8", errors="replace")
        except (LookupError, ValueError):
            return ""
    return ""


def imap_mail_overview(connection: IntegrationConnection, folder: str = "INBOX", unread_only: bool = False, top: int = 20) -> list[dict]:
    """List recent messages in an IMAP folder, newest first (headers only — no body preview;
    use imap_mail_read for full content). Uses IMAP UIDs (stable across sessions), not
    sequence numbers, so returned ids stay valid for later imap_mail_read/imap_mail_reply calls.
    """
    client = _imap_client(connection)
    try:
        status, _ = client.select(folder, readonly=True)
        if status != "OK":
            raise ProviderError(f"Map '{folder}' bestaat niet of is niet bereikbaar.")
        status, data = client.uid("search", None, "UNSEEN" if unread_only else "ALL")
        if status != "OK":
            raise ProviderError("IMAP-zoekopdracht mislukt.")
        uids = data[0].split()
        uids = uids[-top:] if top else uids
        uids.reverse()
        messages = []
        for uid in uids:
            status, msg_data = client.uid("fetch", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            flags_raw = imaplib.ParseFlags(msg_data[0][0]) if isinstance(msg_data[0][0], bytes) else ()
            headers = email.message_from_bytes(msg_data[0][1])
            sender_name, sender_email = parseaddr(_decode_mime_header(headers.get("From", "")))
            messages.append({
                "id": f"{folder}:{uid.decode()}",
                "subject": _decode_mime_header(headers.get("Subject", "")),
                "from": sender_email,
                "from_name": sender_name,
                "received_at": headers.get("Date", ""),
                "is_read": b"\\Seen" in flags_raw,
            })
        return messages
    finally:
        client.logout()


def imap_mail_read(connection: IntegrationConnection, message_id: str) -> dict:
    """Read the full text content of one IMAP message, given its id (from imap_mail_overview)."""
    try:
        folder, uid = message_id.split(":", 1)
    except ValueError as error:
        raise ProviderError("Ongeldig bericht-id.") from error
    client = _imap_client(connection)
    try:
        status, _ = client.select(folder, readonly=True)
        if status != "OK":
            raise ProviderError(f"Map '{folder}' bestaat niet of is niet bereikbaar.")
        status, msg_data = client.uid("fetch", uid.encode(), "(BODY.PEEK[])")
        if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            raise ProviderError("Bericht niet gevonden.")
        message = email.message_from_bytes(msg_data[0][1])
        sender_name, sender_email = parseaddr(_decode_mime_header(message.get("From", "")))
        return {
            "id": message_id,
            "subject": _decode_mime_header(message.get("Subject", "")),
            "from": sender_email,
            "from_name": sender_name,
            "to": [addr for _, addr in getaddresses(message.get_all("To", []) or [])],
            "cc": [addr for _, addr in getaddresses(message.get_all("Cc", []) or [])],
            "received_at": message.get("Date", ""),
            "body": _extract_plain_text(message),
            "message_id_header": message.get("Message-ID", ""),
        }
    finally:
        client.logout()


def _imap_smtp_send(connection: IntegrationConnection, message: EmailMessage) -> None:
    settings = connection.settings
    host = settings.get("smtp_host") or settings.get("host", "")
    port = int(settings.get("smtp_port", 587))
    password = decrypt(connection.secret_encrypted)
    try:
        server = smtplib.SMTP_SSL(host, port, timeout=20) if port == 465 else smtplib.SMTP(host, port, timeout=20)
        try:
            if port != 465 and settings.get("smtp_use_tls", True):
                server.starttls()
            server.login(connection.external_account, password)
            server.send_message(message)
        finally:
            server.quit()
    except (smtplib.SMTPException, OSError) as error:
        raise ProviderError(f"E-mail versturen via SMTP is mislukt: {error}") from error


def imap_mail_send(connection: IntegrationConnection, to: list[str], subject: str, body: str, cc: list[str] | None = None) -> None:
    """Send a new email from this IMAP/SMTP account."""
    message = EmailMessage()
    message["From"] = connection.external_account
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message.set_content(body)
    _imap_smtp_send(connection, message)


def imap_mail_reply(connection: IntegrationConnection, message_id: str, comment: str, reply_all: bool = False) -> None:
    """Reply to an existing IMAP message, given its id (from imap_mail_overview/imap_mail_read)."""
    original = imap_mail_read(connection, message_id)
    to = [original["from"]] if original["from"] else []
    cc = []
    if reply_all:
        cc = [addr for addr in (original.get("to", []) + original.get("cc", [])) if addr and addr.lower() != (connection.external_account or "").lower()]
    if not to:
        raise ProviderError("Kon geen afzender vinden om op te antwoorden.")
    message = EmailMessage()
    message["From"] = connection.external_account
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    subject = original.get("subject", "")
    message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if original.get("message_id_header"):
        message["In-Reply-To"] = original["message_id_header"]
        message["References"] = original["message_id_header"]
    message.set_content(comment)
    _imap_smtp_send(connection, message)
