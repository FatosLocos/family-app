"""Protocol services for agents that run inside a household's local network."""
from __future__ import annotations

import secrets
from uuid import uuid4
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeEntity
from home.realtime import broadcast_home_entity
from integrations.models import IntegrationConnection, LocalDiscovery, LocalProbe


PAIRING_LIFETIME = timedelta(minutes=10)
# The agent normally emits a heartbeat and inventory at least every 25 seconds.
# A short grace period prevents a restarted server from treating yesterday's
# websocket as a live, controllable local connection.
PROBE_STALE_AFTER = timedelta(minutes=2)


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


def mark_probe_seen(
    probe: LocalProbe,
    version: str = "",
    adapters: dict | None = None,
    *,
    replace_adapters: bool = False,
) -> None:
    with household_db_scope(probe.household_id):
        probe.status = "online"
        probe.last_seen_at = timezone.now()
        probe.last_error = ""
        if version:
            probe.version = version[:80]
        if isinstance(adapters, dict):
            known_adapters = probe.adapters if isinstance(probe.adapters, dict) else {}
            probe.adapters = adapters if replace_adapters else {**known_adapters, **adapters}
        probe.save(update_fields=["status", "last_seen_at", "last_error", "version", "adapters", "updated_at"])


def mark_probe_offline(probe: LocalProbe) -> None:
    """Do not report a controllable probe after its outbound tunnel closes."""
    with household_db_scope(probe.household_id):
        if probe.revoked_at:
            return
        probe.status = "offline"
        probe.save(update_fields=["status", "updated_at"])


def probe_is_current(probe: LocalProbe, *, now=None) -> bool:
    """Return whether the probe has recently confirmed its websocket tunnel."""
    now = now or timezone.now()
    return bool(
        not probe.revoked_at
        and probe.status == "online"
        and probe.last_seen_at
        and probe.last_seen_at >= now - PROBE_STALE_AFTER
    )


def expire_stale_probes(household, *, now=None) -> list[LocalProbe]:
    """Mark abandoned probes offline and remove their local-control overlay.

    Cloud entities can be enriched by a probe. Those entities remain visible
    and controllable through their cloud provider when the probe disappears.
    Synthetic local records remain in the audit-friendly inventory, but are
    explicitly unavailable until the probe reconnects.
    """
    now = now or timezone.now()
    cutoff = now - PROBE_STALE_AFTER
    with household_db_scope(household.id):
        stale_probes = list(
            LocalProbe.objects.for_household(household)
            .filter(status="online", revoked_at__isnull=True)
            .filter(Q(last_seen_at__lt=cutoff) | Q(last_seen_at__isnull=True))
        )
        for probe in stale_probes:
            probe.status = "offline"
            probe.save(update_fields=["status", "updated_at"])

            entities = HomeEntity.objects.for_household(household).filter(
                attributes__probe_id=str(probe.id)
            )
            for entity in entities:
                attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
                if entity.entity_id.startswith(f"probe.{probe.id}."):
                    entity.is_available = False
                    entity.save(update_fields=["is_available", "last_seen_at"])
                    broadcast_home_entity(entity)
                    continue

                # This is a cloud entity that was temporarily enriched with a
                # local source of truth. Preserve cloud state but never route
                # a later action through a disconnected probe.
                clean_attributes = {
                    key: value
                    for key, value in attributes.items()
                    if key not in {"probe_id", "probe_name", "probe_local_key", "probe_updated_at"}
                }
                entity.attributes = clean_attributes
                entity.save(update_fields=["attributes", "last_seen_at"])
                broadcast_home_entity(entity)
    return stale_probes


def record_probe_command_result(
    probe: LocalProbe,
    succeeded: bool,
    error: str = "",
    *,
    command_id: str = "",
    entity_id: str = "",
    action: str = "",
) -> None:
    with household_db_scope(probe.household_id):
        probe.last_seen_at = timezone.now()
        probe.status = "online"
        probe.last_error = "" if succeeded else str(error or "Lokale apparaatopdracht mislukt.")[:500]
        probe.save(update_fields=["status", "last_seen_at", "last_error", "updated_at"])
        try:
            entity_pk = int(entity_id)
        except (TypeError, ValueError):
            return
        entity = HomeEntity.objects.for_household(probe.household).filter(
            pk=entity_pk,
            attributes__probe_id=str(probe.id),
        ).first()
        if not entity:
            return
        from home.models import HomeActionAudit
        from home.realtime import broadcast_home_control_result

        detail = "Lokale opdracht bevestigd." if succeeded else str(error or "Lokale apparaatopdracht mislukt.")[:300]
        HomeActionAudit.objects.create(
            household=probe.household,
            entity=entity,
            action=str(action or "local_command")[:64],
            succeeded=succeeded,
            detail=detail,
        )
        broadcast_home_control_result(entity, command_id=str(command_id or ""), succeeded=succeeded, error=detail if not succeeded else "")


def _source(value: str) -> str:
    if value not in {HomeEntity.Source.HUE, HomeEntity.Source.SONOS, HomeEntity.Source.NEST_PROTECT, HomeEntity.Source.GOOGLE_CAST, HomeEntity.Source.PHILIPS_TV}:
        raise ProbeError("Deze lokale bron wordt nog niet ondersteund.")
    return value


def _existing_entity(probe: LocalProbe, source: str, local_key: str, external_id: str) -> HomeEntity | None:
    entities = HomeEntity.objects.for_household(probe.household).filter(source=source)
    by_probe = entities.filter(attributes__probe_id=str(probe.id), attributes__probe_local_key=local_key).first()
    if by_probe:
        return by_probe
    if external_id:
        exact_entity = entities.filter(entity_id__endswith=f".{external_id}").first()
        if exact_entity:
            return exact_entity
        if source == HomeEntity.Source.SONOS and external_id.startswith("group:"):
            group_id = external_id.partition(":")[2]
            for entity in entities.filter(attributes__sonos_entity_type="group"):
                attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
                known_ids = {
                    str(attributes.get("sonos_group_id") or ""),
                    str(attributes.get("sonos_coordinator_id") or ""),
                    *{str(player_id) for player_id in attributes.get("sonos_player_ids", []) if player_id},
                }
                if group_id in known_ids:
                    return entity
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


def _discovery_identity(*, key: str, name: str, address: str, details: dict, method: str = "") -> str:
    """Use stable network identifiers so one device is not listed per protocol."""
    properties = details.get("properties") if isinstance(details.get("properties"), dict) else {}
    if str(method).casefold() == "bluetooth_le":
        # BLE privacy addresses change regularly. A rotating address must not
        # create a new discovery on every scan. Named advertisements are
        # stable enough for a useful suggestion; anonymous advertisements are
        # deliberately grouped by the limited metadata they disclose.
        normalized_name = " ".join(str(name or "").casefold().split())
        manufacturer_ids = details.get("manufacturer_ids") if isinstance(details.get("manufacturer_ids"), list) else []
        service_uuids = details.get("service_uuids") if isinstance(details.get("service_uuids"), list) else []
        manufacturer_key = ",".join(sorted(str(item).casefold() for item in manufacturer_ids if item))
        service_key = ",".join(sorted(str(item).casefold() for item in service_uuids if item))
        if normalized_name not in {"", "bluetooth le-apparaat", "onbekend apparaat"}:
            return f"ble:name:{normalized_name}:{manufacturer_key}"
        return f"ble:anonymous:{manufacturer_key}:{service_key}"
    normalized_address = str(address or "").strip().casefold()
    if normalized_address:
        return f"network:{normalized_address}"
    for value in (
        details.get("serial"),
        details.get("endpoint"),
        details.get("bluetooth_address"),
        properties.get("deviceid"),
        properties.get("pi"),
        details.get("location"),
        details.get("server"),
    ):
        normalized = str(value or "").strip().casefold()
        if normalized:
            return f"id:{normalized}"
    normalized_key = str(key or "").strip().casefold()
    if normalized_key.startswith("uuid:"):
        return f"id:{normalized_key}"
    normalized_name = " ".join(str(name or "").casefold().split())
    return f"name:{normalized_name}"


def apply_discovery(probe: LocalProbe, devices: list[dict]) -> int:
    if not isinstance(devices, list):
        raise ProbeError("Discovery-resultaat heeft een ongeldige vorm.")
    with household_db_scope(probe.household_id):
        existing_by_identity = {}
        duplicate_ids = []
        for discovery in LocalDiscovery.objects.for_household(probe.household).filter(probe=probe).order_by("-last_seen_at", "-id"):
            identity = _discovery_identity(
                key=discovery.key,
                name=discovery.name,
                address=discovery.address or "",
                details=discovery.details if isinstance(discovery.details, dict) else {},
                method=discovery.method,
            )
            if identity in existing_by_identity:
                duplicate_ids.append(discovery.id)
            else:
                existing_by_identity[identity] = discovery
        if duplicate_ids:
            LocalDiscovery.objects.for_household(probe.household).filter(pk__in=duplicate_ids).delete()

        incoming_by_identity = {}
        for device in devices[:300]:
            if not isinstance(device, dict) or not device.get("key"):
                continue
            details = device.get("details") if isinstance(device.get("details"), dict) else {}
            identity = _discovery_identity(
                key=str(device["key"]),
                name=str(device.get("name") or ""),
                address=str(device.get("address") or ""),
                details=details,
                method=str(device.get("method") or ""),
            )
            incoming_by_identity.setdefault(identity, device)

        count = 0
        for identity, device in incoming_by_identity.items():
            address = str(device.get("address") or "")
            values = {
                "household": probe.household,
                "name": str(device.get("name") or "Onbekend apparaat")[:200],
                "kind": str(device.get("kind") or "onbekend")[:80],
                "address": address if address.count(".") == 3 or ":" in address else None,
                "method": str(device.get("method") or "lan")[:40],
                "details": device.get("details") if isinstance(device.get("details"), dict) else {},
            }
            existing = existing_by_identity.get(identity)
            if existing:
                for field, value in values.items():
                    setattr(existing, field, value)
                existing.save(update_fields=[*values.keys(), "last_seen_at"])
            else:
                LocalDiscovery.objects.create(probe=probe, key=str(device["key"])[:300], **values)
            count += 1
    return count


def _send_probe_payload(probe: LocalProbe, payload: dict) -> str:
    if not probe_is_current(probe):
        if not probe.revoked_at:
            expire_stale_probes(probe.household)
        raise ProbeError("De lokale probe is niet verbonden.")
    layer = get_channel_layer()
    if not layer:
        raise ProbeError("Live verbinding met de lokale probe is niet beschikbaar.")
    command_id = uuid4().hex
    async_to_sync(layer.group_send)(
        f"local-probe-{probe.id}",
        {
            "type": "probe.command",
            "payload": {"type": "command", "command_id": command_id, **payload},
        },
    )
    return command_id


def send_probe_command(probe: LocalProbe, entity: HomeEntity, action: str, value=None) -> str:
    return _send_probe_payload(
        probe,
        {
            "action": action,
            "entity": {
                "id": entity.id,
                "local_key": entity.attributes.get("probe_local_key"),
                "source": entity.source,
                "domain": entity.domain,
            },
            "value": value,
        },
    )


def send_probe_system_command(probe: LocalProbe, action: str, value=None) -> str:
    """Send a household-approved probe action that is not tied to an entity."""
    return _send_probe_payload(probe, {"action": action, "entity": {}, "value": value})


def revoke_probe(probe: LocalProbe) -> None:
    with household_db_scope(probe.household_id):
        probe.revoked_at = timezone.now()
        probe.status = "revoked"
        probe.token_hash = ""
        probe.save(update_fields=["revoked_at", "status", "token_hash", "updated_at"])
