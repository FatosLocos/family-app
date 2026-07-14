from __future__ import annotations

import base64
import hashlib
import hmac
import json

from django.db import transaction
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeEntity
from home.realtime import broadcast_home_entity
from integrations.crypto import decrypt
from integrations.models import IntegrationAppConfig, IntegrationConnection


class SonosEventError(Exception):
    pass


_SIGNATURE_HEADERS = (
    "X-Sonos-Event-Seq-Id",
    "X-Sonos-Namespace",
    "X-Sonos-Type",
    "X-Sonos-Target-Type",
    "X-Sonos-Target-Value",
)


def sonos_event_signature(headers, client_id: str, client_secret: str) -> str:
    values = [headers.get(name, "") for name in _SIGNATURE_HEADERS]
    if not all(values):
        raise SonosEventError("Sonos-event mist verplichte headers.")
    digest = hashlib.sha256("".join([*values, client_id, client_secret]).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def process_sonos_event(household_id: int, callback_token: str, headers, raw_body: bytes) -> dict:
    """Validate and apply a single signed Sonos push event within its household scope."""
    with household_db_scope(household_id):
        with transaction.atomic():
            config = IntegrationAppConfig.objects.filter(household_id=household_id, provider="sonos").first()
            if not config:
                raise SonosEventError("Sonos-configuratie niet gevonden.")
            settings = config.settings if isinstance(config.settings, dict) else {}
            expected_token = decrypt(str(settings.get("event_callback_token") or ""))
            if not expected_token or not hmac.compare_digest(expected_token, callback_token):
                raise SonosEventError("Ongeldige Sonos callback URL.")
            client_secret = decrypt(config.client_secret_encrypted)
            provided_signature = headers.get("X-Sonos-Event-Signature", "")
            expected_signature = sonos_event_signature(headers, config.client_id, client_secret)
            if not provided_signature or not hmac.compare_digest(expected_signature, provided_signature):
                raise SonosEventError("Ongeldige Sonos-eventsignatuur.")
            try:
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SonosEventError("Sonos stuurde ongeldige eventdata.") from error
            if not isinstance(payload, dict):
                raise SonosEventError("Sonos stuurde ongeldige eventdata.")

            household_key = headers["X-Sonos-Household-Id"]
            # A Sonos account can expose more than one household. JSON lookup only
            # covers the primary household, so also inspect the stored full list.
            connection = next(
                (
                    candidate
                    for candidate in IntegrationConnection.objects.select_for_update().filter(
                        household_id=household_id,
                        provider=IntegrationConnection.Provider.SONOS,
                    )
                    if household_key == str((candidate.settings or {}).get("sonos_household_id") or "")
                    or household_key in ((candidate.settings or {}).get("sonos_household_ids") or [])
                ),
                None,
            )
            if not connection:
                return {"accepted": True, "sync_needed": False}

            sequence_id = int(headers["X-Sonos-Event-Seq-Id"])
            connection_settings = dict(connection.settings) if isinstance(connection.settings, dict) else {}
            last_sequence_id = int(connection_settings.get("sonos_event_last_sequence", -1))
            if sequence_id <= last_sequence_id:
                return {"accepted": True, "sync_needed": False, "duplicate": True}

            namespace = headers["X-Sonos-Namespace"]
            target_type = headers["X-Sonos-Target-Type"]
            target_value = headers["X-Sonos-Target-Value"]
            sync_needed = namespace == "groups"
            if target_type.lower() == "groupid":
                entity = HomeEntity.objects.for_household(connection.household).filter(
                    connection=connection,
                    entity_id=f"sonos.{connection.id}.group.{target_value}",
                ).first()
            elif target_type.lower() == "playerid":
                entity = HomeEntity.objects.for_household(connection.household).filter(
                    connection=connection,
                    entity_id=f"sonos.{connection.id}.player.{target_value}",
                ).first()
            else:
                entity = None
            if entity:
                attributes = dict(entity.attributes) if isinstance(entity.attributes, dict) else {}
                attributes["sonos_last_event"] = {"namespace": namespace, "type": headers["X-Sonos-Type"], "received_at": timezone.now().isoformat()}
                if namespace in {"groupVolume", "playerVolume"}:
                    attributes["sonos_volume"] = payload.get("volume")
                    attributes["sonos_muted"] = payload.get("muted")
                if namespace == "playback":
                    playback_state = str(payload.get("playbackState") or payload.get("state") or "").upper()
                    if "PLAYING" in playback_state:
                        entity.state = "on"
                    elif playback_state:
                        entity.state = "off"
                    attributes["sonos_playback_state"] = playback_state or attributes.get("sonos_playback_state", "")
                    from integrations.providers import sonos_playback_status_attributes

                    attributes.update(sonos_playback_status_attributes(payload))
                if namespace == "playbackMetadata":
                    from integrations.providers import sonos_playback_metadata_attributes

                    attributes.update(sonos_playback_metadata_attributes(payload))
                entity.attributes = attributes
                entity.save(update_fields=["state", "attributes", "last_seen_at"])
                broadcast_home_entity(entity)

            connection_settings["sonos_event_last_sequence"] = sequence_id
            connection_settings["sonos_event_last_at"] = timezone.now().isoformat()
            connection.settings = connection_settings
            connection.save(update_fields=["settings", "updated_at"])
            return {"accepted": True, "sync_needed": sync_needed, "connection_id": connection.id}
