"""Protocol services for agents that run inside a household's local network."""
from __future__ import annotations

import secrets
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeEntity
from home.realtime import broadcast_home_entity
from integrations.models import IntegrationConnection, LocalDiscovery, LocalProbe


PAIRING_LIFETIME = timedelta(minutes=10)


class ProbeError(Exception):
    pass


def create_pairing(household) -> tuple[LocalProbe, str]:
    with household_db_scope(household.id):
        LocalProbe.objects.for_household(household).filter(status="pairing").delete()
        secret = secrets.token_urlsafe(6).upper()
        code = f"FAP-{household.id}-{secret}"
        probe = LocalProbe.objects.create(
            household=household,
            pairing_code_hash=make_password(code),
            pairing_expires_at=timezone.now() + PAIRING_LIFETIME,
        )
    return probe, code


def pair_probe(code: str, name: str, version: str) -> tuple[LocalProbe, str]:
    now = timezone.now()
    parts = code.split("-", 2)
    if len(parts) != 3 or parts[0] != "FAP" or not parts[1].isdigit():
        raise ProbeError("De pairing-code is ongeldig of verlopen.")
    household_id = int(parts[1])
    with household_db_scope(household_id):
        for probe in LocalProbe.objects.filter(household_id=household_id, status="pairing", pairing_expires_at__gte=now):
            if check_password(code, probe.pairing_code_hash):
                raw_token = secrets.token_urlsafe(48)
                token = f"{household_id}.{raw_token}"
                probe.name = (name or "Lokale probe").strip()[:120]
                probe.version = (version or "onbekend")[:80]
                probe.token_hash = make_password(raw_token)
                probe.pairing_code_hash = ""
                probe.pairing_expires_at = None
                probe.status = "online"
                probe.last_seen_at = now
                probe.last_error = ""
                probe.save()
                return probe, token
    raise ProbeError("De pairing-code is ongeldig of verlopen.")


def authenticate_probe(probe_id: str, token: str) -> LocalProbe:
    household_part, separator, raw_token = token.partition(".")
    if not separator or not household_part.isdigit():
        raise ProbeError("Probe is niet geautoriseerd.")
    with household_db_scope(int(household_part)):
        probe = LocalProbe.objects.filter(pk=probe_id, household_id=int(household_part), revoked_at__isnull=True, token_hash__gt="").select_related("household").first()
        if not probe or not check_password(raw_token, probe.token_hash):
            raise ProbeError("Probe is niet geautoriseerd.")
        return probe


def mark_probe_seen(probe: LocalProbe, version: str = "", adapters: dict | None = None) -> None:
    with household_db_scope(probe.household_id):
        probe.status = "online"
        probe.last_seen_at = timezone.now()
        probe.last_error = ""
        if version:
            probe.version = version[:80]
        if isinstance(adapters, dict):
            probe.adapters = adapters
        probe.save(update_fields=["status", "last_seen_at", "last_error", "version", "adapters", "updated_at"])


def mark_probe_offline(probe: LocalProbe) -> None:
    """Do not report a controllable probe after its outbound tunnel closes."""
    with household_db_scope(probe.household_id):
        if probe.revoked_at:
            return
        probe.status = "offline"
        probe.save(update_fields=["status", "updated_at"])


def record_probe_command_result(probe: LocalProbe, succeeded: bool, error: str = "") -> None:
    with household_db_scope(probe.household_id):
        probe.last_seen_at = timezone.now()
        probe.status = "online"
        probe.last_error = "" if succeeded else str(error or "Lokale apparaatopdracht mislukt.")[:500]
        probe.save(update_fields=["status", "last_seen_at", "last_error", "updated_at"])


def _source(value: str) -> str:
    if value not in {HomeEntity.Source.HUE, HomeEntity.Source.SONOS}:
        raise ProbeError("Deze lokale bron wordt nog niet ondersteund.")
    return value


def _existing_entity(probe: LocalProbe, source: str, local_key: str, external_id: str) -> HomeEntity | None:
    entities = HomeEntity.objects.for_household(probe.household).filter(source=source)
    by_probe = entities.filter(attributes__probe_id=str(probe.id), attributes__probe_local_key=local_key).first()
    if by_probe:
        return by_probe
    if external_id:
        return entities.filter(entity_id__endswith=f".{external_id}").first()
    return None


def apply_inventory(probe: LocalProbe, entities: list[dict]) -> int:
    """Upsert local source-of-truth state and fan it out to open household views."""
    if not isinstance(entities, list):
        raise ProbeError("Inventaris heeft een ongeldige vorm.")
    updated = 0
    seen_entity_ids = set()
    sources = set()
    with household_db_scope(probe.household_id):
        for payload in entities[:500]:
            if not isinstance(payload, dict):
                continue
            source = _source(str(payload.get("source") or ""))
            local_key = str(payload.get("local_key") or "")[:240]
            external_id = str(payload.get("external_id") or "")[:240]
            name = str(payload.get("name") or "")[:255]
            domain = str(payload.get("domain") or "")[:64]
            if not local_key or not name or not domain:
                continue
            sources.add(source)
            attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
            entity = _existing_entity(probe, source, local_key, external_id)
            connection = IntegrationConnection.objects.for_household(probe.household).filter(provider=source).first()
            merged_attributes = {
                **(entity.attributes if entity and isinstance(entity.attributes, dict) else {}),
                **attributes,
                "probe_id": str(probe.id),
                "probe_name": probe.name,
                "probe_local_key": local_key,
                "probe_updated_at": timezone.now().isoformat(),
            }
            defaults = {
                "connection": connection,
                "domain": domain,
                "name": name,
                "state": str(payload.get("state") or ""),
                "attributes": merged_attributes,
                "is_available": bool(payload.get("is_available", True)),
                "is_supported": bool(payload.get("is_supported", False)),
            }
            if entity:
                for key, value in defaults.items():
                    setattr(entity, key, value)
                entity.save()
            else:
                entity = HomeEntity.objects.create(
                    household=probe.household,
                    entity_id=f"probe.{probe.id}.{source}.{local_key}"[:255],
                    source=source,
                    **defaults,
                )
            broadcast_home_entity(entity)
            seen_entity_ids.add(entity.pk)
            updated += 1
        # An inventory is authoritative for entities that were created by this
        # probe. Remove only these synthetic records; cloud-synced records
        # enriched by the probe deliberately remain intact.
        stale = HomeEntity.objects.for_household(probe.household).filter(
            source__in=sources,
            entity_id__startswith=f"probe.{probe.id}.",
        ).exclude(pk__in=seen_entity_ids)
        stale.delete()
    return updated


def apply_discovery(probe: LocalProbe, devices: list[dict]) -> int:
    if not isinstance(devices, list):
        raise ProbeError("Discovery-resultaat heeft een ongeldige vorm.")
    count = 0
    with household_db_scope(probe.household_id):
        for device in devices[:300]:
            if not isinstance(device, dict) or not device.get("key"):
                continue
            address = str(device.get("address") or "")
            values = {
                "household": probe.household,
                "name": str(device.get("name") or "Onbekend apparaat")[:200],
                "kind": str(device.get("kind") or "onbekend")[:80],
                "address": address if address.count(".") == 3 or ":" in address else None,
                "method": str(device.get("method") or "lan")[:40],
                "details": device.get("details") if isinstance(device.get("details"), dict) else {},
            }
            LocalDiscovery.objects.update_or_create(probe=probe, key=str(device["key"])[:300], defaults=values)
            count += 1
    return count


def send_probe_command(probe: LocalProbe, entity: HomeEntity, action: str, value=None) -> None:
    if probe.revoked_at or probe.status != "online":
        raise ProbeError("De lokale probe is niet verbonden.")
    layer = get_channel_layer()
    if not layer:
        raise ProbeError("Live verbinding met de lokale probe is niet beschikbaar.")
    async_to_sync(layer.group_send)(
        f"local-probe-{probe.id}",
        {
            "type": "probe.command",
            "payload": {
                "type": "command",
                "entity": {
                    "local_key": entity.attributes.get("probe_local_key"),
                    "source": entity.source,
                    "domain": entity.domain,
                },
                "action": action,
                "value": value,
            },
        },
    )


def revoke_probe(probe: LocalProbe) -> None:
    with household_db_scope(probe.household_id):
        probe.revoked_at = timezone.now()
        probe.status = "revoked"
        probe.token_hash = ""
        probe.save(update_fields=["revoked_at", "status", "token_hash", "updated_at"])
