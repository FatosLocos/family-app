"""Google Device Access Pub/Sub pull subscription support."""

from __future__ import annotations

import base64
import json
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeEntity
from home.realtime import broadcast_home_entity
from integrations.crypto import decrypt
from integrations.models import IntegrationAppConfig, IntegrationConnection
from integrations.providers import apply_google_home_traits


class GoogleHomeEventError(Exception):
    pass


GOOGLE_EVENT_LABELS = {
    "sdm.devices.events.CameraMotion.Motion": "Beweging gedetecteerd",
    "sdm.devices.events.CameraPerson.Person": "Persoon gedetecteerd",
    "sdm.devices.events.CameraSound.Sound": "Geluid gedetecteerd",
    "sdm.devices.events.DoorbellChime.Chime": "Er is aangebeld",
}


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _service_account_token(raw_json: str) -> str:
    try:
        account = json.loads(raw_json)
        private_key = serialization.load_pem_private_key(str(account["private_key"]).encode(), password=None)
        now = int(time.time())
        header = _base64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        claims = _base64url(json.dumps({"iss": account["client_email"], "scope": "https://www.googleapis.com/auth/pubsub", "aud": account.get("token_uri", "https://oauth2.googleapis.com/token"), "iat": now, "exp": now + 3600}, separators=(",", ":")).encode())
        signature = private_key.sign(f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except (KeyError, TypeError, ValueError) as error:
        raise GoogleHomeEventError("Het Google serviceaccount JSON is ongeldig.") from error
    response = requests.post(
        str(account.get("token_uri") or "https://oauth2.googleapis.com/token"),
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": f"{header}.{claims}.{_base64url(signature)}"},
        timeout=15,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise GoogleHomeEventError("Google gaf geen geldig serviceaccount-token terug.") from error
    if not response.ok or not payload.get("access_token"):
        raise GoogleHomeEventError("Google accepteerde het serviceaccount niet voor Pub/Sub.")
    return str(payload["access_token"])


def _pull(subscription: str, token: str) -> list[dict]:
    if not subscription.startswith("projects/") or "/subscriptions/" not in subscription:
        raise GoogleHomeEventError("De Pub/Sub subscription moet de volledige projects/.../subscriptions/...-naam bevatten.")
    response = requests.post(
        f"https://pubsub.googleapis.com/v1/{subscription}:pull",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"maxMessages": 50},
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise GoogleHomeEventError("Pub/Sub gaf geen geldige events terug.") from error
    if not response.ok:
        raise GoogleHomeEventError("Pub/Sub kon de Nest-events niet ophalen. Controleer de subscription en Subscriber-rol.")
    return [item for item in payload.get("receivedMessages", []) if isinstance(item, dict)]


def _acknowledge(subscription: str, token: str, acknowledgements: list[str]) -> None:
    if not acknowledgements:
        return
    response = requests.post(
        f"https://pubsub.googleapis.com/v1/{subscription}:acknowledge",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"ackIds": acknowledgements},
        timeout=20,
    )
    if not response.ok:
        raise GoogleHomeEventError("Pub/Sub bevestigde de ontvangen Nest-events niet.")


def _event_payload(message: dict) -> dict | None:
    encoded = str((message.get("message") or {}).get("data") or "")
    if not encoded:
        return None
    try:
        return json.loads(base64.b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise GoogleHomeEventError("Een Pub/Sub-bericht bevat ongeldige Nest-eventdata.") from error


def poll_google_home_events(connection: IntegrationConnection) -> dict:
    """Apply every queued SDM resource update once; Pub/Sub remains the source of truth."""
    with household_db_scope(connection.household_id):
        config = IntegrationAppConfig.objects.filter(household=connection.household, provider="google_home").first()
        settings = config.settings if config and isinstance(config.settings, dict) else {}
        if not settings.get("events_enabled"):
            return {"status": "disabled", "events": 0}
        encrypted_key = str(settings.get("pubsub_service_account_json") or "")
        subscription = str(settings.get("pubsub_subscription") or "")
        if not encrypted_key or not subscription:
            raise GoogleHomeEventError("Live Nest-events zijn niet volledig geconfigureerd.")
        token = _service_account_token(decrypt(encrypted_key))
        received = _pull(subscription, token)
        connection_settings = dict(connection.settings) if isinstance(connection.settings, dict) else {}
        seen_ids = list(connection_settings.get("google_event_ids") or [])[-100:]
        acknowledgements, applied = [], 0
        for received_message in received:
            acknowledgement = str(received_message.get("ackId") or "")
            payload = _event_payload(received_message)
            event_id = str((payload or {}).get("eventId") or "")
            if payload and event_id not in seen_ids:
                resource_update = payload.get("resourceUpdate") if isinstance(payload.get("resourceUpdate"), dict) else {}
                resource_name = str(resource_update.get("name") or "")
                traits = resource_update.get("traits") if isinstance(resource_update.get("traits"), dict) else {}
                events = resource_update.get("events") if isinstance(resource_update.get("events"), dict) else {}
                if resource_name and (traits or events):
                    entity = HomeEntity.objects.for_household(connection.household).filter(connection=connection, attributes__google_resource_name=resource_name).first()
                    if entity:
                        previous_traits = entity.attributes.get("google_traits") if isinstance(entity.attributes, dict) and isinstance(entity.attributes.get("google_traits"), dict) else {}
                        merged_traits = {**previous_traits, **traits}
                        apply_google_home_traits(entity, merged_traits, {"name": resource_name, "type": entity.attributes.get("google_device_type", ""), "parentRelations": [{"displayName": name} for name in entity.attributes.get("google_locations", [])]})
                        if events:
                            event_type = next(iter(events), "")
                            entity.attributes["google_last_event"] = GOOGLE_EVENT_LABELS.get(event_type, event_type.rsplit(".", 1)[-1] or "Nieuwe Nest-melding")
                            entity.attributes["google_last_event_at"] = str((payload or {}).get("timestamp") or timezone.now().isoformat())
                            entity.state = "active"
                        entity.save(update_fields=["state", "attributes", "is_available", "is_supported", "last_seen_at"])
                        broadcast_home_entity(entity)
                        applied += 1
                if event_id:
                    seen_ids.append(event_id)
            if acknowledgement:
                acknowledgements.append(acknowledgement)
        _acknowledge(subscription, token, acknowledgements)
        connection_settings["google_event_ids"] = seen_ids[-100:]
        connection_settings["google_events_status"] = "active"
        connection_settings["google_events_last_at"] = timezone.now().isoformat() if received else connection_settings.get("google_events_last_at", "")
        connection.settings = connection_settings
        connection.save(update_fields=["settings", "updated_at"])
        return {"status": "active", "events": applied}
