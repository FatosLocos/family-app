from urllib.parse import urlparse

import requests
from django.utils import timezone

from home.ha_gateway import HomeAssistantRegistries, _upsert_state
from home.models import HomeActionAudit, HomeAssistantConfig, HomeEntity
from home.realtime import broadcast_home_entity
from integrations.crypto import decrypt, encrypt

SUPPORTED_DOMAINS = {"light", "switch", "scene", "script", "cover", "climate", "media_player"}


class HomeAssistantError(Exception):
    pass


def _base_url(value):
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise HomeAssistantError("Gebruik een volledig http(s)-adres zonder inloggegevens.")
    return value.rstrip("/")


def save_config(household, base_url, token):
    config = HomeAssistantConfig.objects.for_household(household).first()
    if not token and not config:
        raise HomeAssistantError("Voeg een long-lived access token toe.")
    config, _ = HomeAssistantConfig.objects.get_or_create(household=household, defaults={"base_url": _base_url(base_url), "token_encrypted": encrypt(token)})
    config.base_url = _base_url(base_url)
    if token:
        config.token_encrypted = encrypt(token)
    config.last_error = ""
    config.save()
    return config


def _request(config, method, path, payload=None):
    try:
        response = requests.request(method, f"{config.base_url}{path}", headers={"Authorization": f"Bearer {decrypt(config.token_encrypted)}"}, json=payload, timeout=15)
    except requests.RequestException as error:
        raise HomeAssistantError("Home Assistant is niet bereikbaar.") from error
    if not response.ok:
        raise HomeAssistantError("Home Assistant weigerde de actie. Controleer adres en token.")
    try:
        return response.json() if response.content else {}
    except ValueError as error:
        raise HomeAssistantError("Home Assistant gaf geen geldige reactie.") from error


def sync_entities(household):
    config = HomeAssistantConfig.objects.for_household(household).first()
    if not config:
        raise HomeAssistantError("Home Assistant is nog niet gekoppeld.")
    try:
        states = _request(config, "GET", "/api/states")
        if not isinstance(states, list):
            raise HomeAssistantError("Home Assistant leverde geen entiteitenlijst.")
        seen = set()
        for item in states:
            entity_id = str(item.get("entity_id", ""))
            if "." not in entity_id:
                continue
            entity = _upsert_state(household, item, HomeAssistantRegistries({}, {}, {}), should_broadcast=False)
            if entity:
                seen.add(entity.entity_id)
        HomeEntity.objects.for_household(household).filter(source=HomeEntity.Source.HOME_ASSISTANT).exclude(entity_id__in=seen).update(is_available=False)
        config.last_sync_at, config.last_error = timezone.now(), ""
        config.save(update_fields=["last_sync_at", "last_error", "updated_at"])
        return len(seen)
    except HomeAssistantError as error:
        config.last_error = str(error)
        config.save(update_fields=["last_error", "updated_at"])
        raise


def _service_call_for(entity, action, target_temperature=None):
    services = {
        "light": {"on": "turn_on", "off": "turn_off"},
        "switch": {"on": "turn_on", "off": "turn_off"},
        "scene": {"activate": "turn_on"},
        "script": {"run": "turn_on"},
        "cover": {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"},
        "climate": {"on": "turn_on", "off": "turn_off", "set_temperature": "set_temperature"},
        "media_player": {
            "on": "turn_on",
            "off": "turn_off",
            "play_pause": "media_play_pause",
            "volume_down": "volume_down",
            "volume_up": "volume_up",
        },
    }
    service = services.get(entity.domain, {}).get(action)
    if not service or not entity.is_supported:
        raise HomeAssistantError("Deze bediening is niet beschikbaar voor dit apparaat.")

    payload = {"entity_id": entity.entity_id}
    if action == "set_temperature":
        try:
            temperature = float(str(target_temperature).replace(",", "."))
        except (TypeError, ValueError) as error:
            raise HomeAssistantError("Vul een geldige temperatuur in.") from error
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        minimum = float(attributes.get("min_temp", 5))
        maximum = float(attributes.get("max_temp", 35))
        if not minimum <= temperature <= maximum:
            raise HomeAssistantError(f"Kies een temperatuur tussen {minimum:g} en {maximum:g} °C.")
        payload["temperature"] = temperature
    return service, payload


def _action_detail(action, payload):
    labels = {
        "activate": "Scène gestart.",
        "run": "Script gestart.",
        "open": "Openen uitgevoerd.",
        "close": "Sluiten uitgevoerd.",
        "stop": "Actie gestopt.",
        "on": "Ingeschakeld.",
        "off": "Uitgeschakeld.",
        "play_pause": "Afspelen gepauzeerd of hervat.",
        "volume_down": "Volume verlaagd.",
        "volume_up": "Volume verhoogd.",
    }
    if action == "set_temperature":
        return f"Temperatuur ingesteld op {payload['temperature']:g} °C."
    return labels[action]


def control_entity(household, entity, action, target_temperature=None):
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    probe_id = attributes.get("probe_id")
    if probe_id:
        from integrations.local_probe import ProbeError, send_probe_command
        from integrations.models import LocalProbe

        try:
            probe = LocalProbe.objects.for_household(household).get(pk=probe_id, revoked_at__isnull=True)
            send_probe_command(probe, entity, action, target_temperature)
            HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=True, detail="Lokale opdracht naar probe verzonden.")
            return
        except (LocalProbe.DoesNotExist, ProbeError) as error:
            HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=False, detail=str(error))
            raise HomeAssistantError(str(error)) from error
    if entity.source == HomeEntity.Source.HUE:
        from integrations.providers import ProviderError, control_hue_light

        try:
            detail = control_hue_light(entity, action, target_temperature)
            _apply_hue_control_state(entity, action, target_temperature)
            HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=True, detail=detail)
            return
        except ProviderError as error:
            HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=False, detail=str(error))
            raise HomeAssistantError(str(error)) from error
    if entity.source in {HomeEntity.Source.SONOS, HomeEntity.Source.GOOGLE_HOME, HomeEntity.Source.LG_THINQ}:
        from integrations.providers import ProviderError, control_connected_home_entity

        try:
            detail = control_connected_home_entity(entity, action, target_temperature)
            if entity.source == HomeEntity.Source.SONOS:
                _apply_sonos_control_state(entity, action, target_temperature)
                if action == "set_group" and entity.connection:
                    from integrations.providers import sync_sonos

                    sync_sonos(entity.connection)
            elif action == "on":
                entity.state = "on"
            elif action == "play_pause":
                entity.state = "on" if entity.state != "on" else "off"
            elif action == "off":
                entity.state = "off"
            elif action == "set_temperature":
                attributes = dict(entity.attributes) if isinstance(entity.attributes, dict) else {}
                attributes["temperature"] = float(target_temperature)
                entity.attributes = attributes
            entity.save(update_fields=["state", "attributes", "last_seen_at"])
            broadcast_home_entity(entity)
            HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=True, detail=detail)
            return
        except ProviderError as error:
            HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=False, detail=str(error))
            raise HomeAssistantError(str(error)) from error
    config = HomeAssistantConfig.objects.for_household(household).first()
    if not config:
        raise HomeAssistantError("Home Assistant is nog niet gekoppeld.")
    try:
        service, payload = _service_call_for(entity, action, target_temperature)
        _request(config, "POST", f"/api/services/{entity.domain}/{service}", payload)
        HomeActionAudit.objects.create(household=household, entity=entity, action=service, succeeded=True, detail=f"Via Home Assistant: {_action_detail(action, payload)}")
        sync_entities(household)
    except HomeAssistantError as error:
        fallback = _home_assistant_fallback_entity(household, entity) if entity.source == HomeEntity.Source.HOME_ASSISTANT else None
        if fallback:
            try:
                control_entity(household, fallback, action, target_temperature)
                HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=True, detail=f"Via fallback uitgevoerd: {fallback.name}.")
                return
            except HomeAssistantError:
                pass
        HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=False, detail=str(error))
        raise


def _norm(value):
    return "".join(str(value or "").casefold().split())


def _direct_identifier_values(entity):
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    values = set()
    for key in (
        "hue_light_id",
        "hue_grouped_light_id",
        "hue_scene_id",
        "sonos_player_id",
        "sonos_group_id",
        "google_resource_name",
        "lg_device_id",
        "probe_local_key",
    ):
        value = attributes.get(key)
        if value:
            values.add(str(value))
    for key in ("sonos_player_ids", "member_light_ids"):
        items = attributes.get(key)
        if isinstance(items, list):
            values.update(str(item) for item in items if item)
    return values


def _home_assistant_fallback_entity(household, entity):
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    ha_identifiers = {str(item) for item in attributes.get("ha_device_identifiers", []) if item}
    candidates = HomeEntity.objects.for_household(household).exclude(source=HomeEntity.Source.HOME_ASSISTANT).filter(is_supported=True, is_available=True)
    name_key = _norm(entity.name)
    for candidate in candidates:
        direct_values = _direct_identifier_values(candidate)
        if direct_values and any(value and any(value in ha_identifier for ha_identifier in ha_identifiers) for value in direct_values):
            return candidate
    if name_key:
        return next((candidate for candidate in candidates if candidate.domain == entity.domain and _norm(candidate.name) == name_key), None)
    return None


def _apply_sonos_control_state(entity, action, value=None):
    """Reflect a confirmed Sonos command without waiting for a full inventory sync."""
    attributes = dict(entity.attributes) if isinstance(entity.attributes, dict) else {}
    if action in {"on", "off", "play_pause"}:
        entity.state = "on" if action == "on" or (action == "play_pause" and entity.state != "on") else "off"
        attributes["sonos_playback_state"] = "PLAYBACK_STATE_PLAYING" if entity.state == "on" else "PLAYBACK_STATE_PAUSED"
        if attributes.get("sonos_entity_type") == "group":
            HomeEntity.objects.filter(
                household=entity.household,
                connection=entity.connection,
                source=HomeEntity.Source.SONOS,
                attributes__sonos_group_id=attributes.get("sonos_group_id"),
            ).exclude(pk=entity.pk).update(state=entity.state)
    elif action == "set_volume":
        try:
            attributes["sonos_volume"] = max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            pass
    elif action == "toggle_shuffle":
        attributes["sonos_shuffle"] = not bool(attributes.get("sonos_shuffle"))
    elif action == "toggle_repeat":
        attributes["sonos_repeat"] = not bool(attributes.get("sonos_repeat"))
    elif action in {"volume_up", "volume_down"}:
        current = attributes.get("sonos_volume")
        if isinstance(current, (int, float)):
            attributes["sonos_volume"] = max(0, min(100, int(current) + (5 if action == "volume_up" else -5)))
    elif action in {"mute", "unmute"}:
        attributes["sonos_muted"] = action == "mute"
    entity.attributes = attributes


def _apply_hue_control_state(entity, action, value=None):
    """Keep the visible Hue card responsive after a confirmed remote command.

    A full Hue inventory sync is intentionally left to the explicit refresh
    action. Fetching every resource after a single dimmer change is slow and
    unnecessary for the local, confirmed state shown to the user.
    """
    attributes = dict(entity.attributes) if isinstance(entity.attributes, dict) else {}
    update_fields = ["attributes"]
    if action == "on":
        entity.state = "on"
        update_fields.append("state")
    elif action == "off":
        entity.state = "off"
        update_fields.append("state")
    elif action == "activate":
        entity.state = "active"
        update_fields.append("state")
        group_name = attributes.get("hue_group_name")
        if group_name:
            HomeEntity.objects.filter(
                household=entity.household,
                source=HomeEntity.Source.HUE,
                domain="scene",
                attributes__hue_group_name=group_name,
            ).exclude(pk=entity.pk).update(state="idle")
    elif action == "brightness":
        try:
            attributes["brightness"] = float(value)
        except (TypeError, ValueError):
            pass
        entity.state = "on"
        update_fields.append("state")
    elif action == "color_temperature":
        try:
            attributes["color_temperature"] = int(float(value))
        except (TypeError, ValueError):
            pass
        entity.state = "on"
        update_fields.append("state")
    elif action == "color":
        attributes["color_hex"] = str(value or "")
        entity.state = "on"
        update_fields.append("state")
    elif action == "effect":
        attributes["effect_current"] = str(value or "")
    entity.attributes = attributes
    entity.save(update_fields=update_fields + ["last_seen_at"])
    if entity.domain == "group":
        _apply_hue_group_member_state(entity, action, value)


def _apply_hue_group_member_state(group, action, value=None):
    """Mirror a confirmed Hue group command into the visible member cards.

    Hue applies the command to the bridge group in one request. Updating the
    local member state avoids a misleading UI until the next full sync.
    """
    if action not in {"on", "off", "brightness", "color_temperature", "color", "effect"}:
        return
    attributes = group.attributes if isinstance(group.attributes, dict) else {}
    member_light_ids = {str(light_id) for light_id in attributes.get("member_light_ids", []) if light_id}
    member_names = {str(name) for name in attributes.get("member_names", []) if name}
    if not member_light_ids and not member_names:
        return
    candidates = HomeEntity.objects.filter(
        household=group.household,
        connection=group.connection,
        source=HomeEntity.Source.HUE,
        domain="light",
    )
    for member in candidates:
        member_attributes = dict(member.attributes) if isinstance(member.attributes, dict) else {}
        if str(member_attributes.get("hue_light_id") or "") not in member_light_ids and member.name not in member_names:
            continue
        fields = ["attributes", "last_seen_at"]
        if action == "on":
            member.state = "on"
            fields.append("state")
        elif action == "off":
            member.state = "off"
            fields.append("state")
        elif action == "brightness":
            try:
                member_attributes["brightness"] = float(value)
            except (TypeError, ValueError):
                continue
            member.state = "on"
            fields.append("state")
        elif action == "color_temperature":
            try:
                member_attributes["color_temperature"] = int(float(value))
            except (TypeError, ValueError):
                continue
            member.state = "on"
            fields.append("state")
        elif action == "color":
            member_attributes["color_hex"] = str(value or "")
            member.state = "on"
            fields.append("state")
        elif action == "effect":
            member_attributes["effect_current"] = str(value or "")
        member.attributes = member_attributes
        member.save(update_fields=fields)
