from urllib.parse import urlparse

import requests
from django.utils import timezone

from home.models import HomeActionAudit, HomeAssistantConfig, HomeEntity
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
            domain = entity_id.split(".", 1)[0]
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            HomeEntity.objects.update_or_create(household=household, entity_id=entity_id, defaults={"domain": domain, "name": attributes.get("friendly_name") or entity_id, "state": str(item.get("state", "")), "attributes": attributes, "is_available": item.get("state") not in {"unavailable", "unknown"}, "is_supported": domain in SUPPORTED_DOMAINS})
            seen.add(entity_id)
        HomeEntity.objects.for_household(household).exclude(entity_id__in=seen).update(is_available=False)
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
    if entity.source == HomeEntity.Source.HUE:
        from integrations.providers import ProviderError, control_hue_light, sync_hue

        try:
            detail = control_hue_light(entity, action, target_temperature)
            sync_hue(entity.connection)
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
        HomeActionAudit.objects.create(household=household, entity=entity, action=service, succeeded=True, detail=_action_detail(action, payload))
        sync_entities(household)
    except HomeAssistantError as error:
        HomeActionAudit.objects.create(household=household, entity=entity, action=action, succeeded=False, detail=str(error))
        raise
