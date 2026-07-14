from __future__ import annotations

import json
import uuid
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
from planning.models import CalendarEvent, CalendarSource


class ProviderError(Exception):
    pass


def _safe_response_json(response, provider: str) -> dict:
    """Return a provider response without leaking implementation details to the UI."""
    try:
        payload = response.json() if response.content else {}
    except ValueError as error:
        raise ProviderError(f"{provider} gaf geen geldige reactie.") from error
    if response.ok:
        return payload if isinstance(payload, dict) else {}

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
    raise ProviderError("Onbekende koppeling.")


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
        raise ProviderError("Philips Hue weigerde de aanvraag. Koppel de bridge opnieuw als dit blijft gebeuren.")
    if isinstance(payload, dict) and payload.get("errors"):
        first_error = next((item for item in payload["errors"] if isinstance(item, dict)), {})
        raise ProviderError(str(first_error.get("description") or "Philips Hue kon de aanvraag niet uitvoeren.")[:240])
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
    lights = lights_payload.get("data") if isinstance(lights_payload, dict) else None
    devices = devices_payload.get("data") if isinstance(devices_payload, dict) else None
    if not isinstance(lights, list):
        raise ProviderError("Philips Hue leverde geen lampenlijst.")
    device_names = {
        str(service.get("rid")): str(device.get("metadata", {}).get("name") or "Hue lamp")
        for device in (devices if isinstance(devices, list) else [])
        if isinstance(device, dict)
        for service in device.get("services", [])
        if isinstance(service, dict) and service.get("rtype") == "light" and service.get("rid")
    }
    seen, count = set(), 0
    for light in lights:
        if not isinstance(light, dict):
            continue
        light_id = str(light.get("id") or "")
        if not light_id:
            continue
        on = light.get("on") if isinstance(light.get("on"), dict) else {}
        dimming = light.get("dimming") if isinstance(light.get("dimming"), dict) else {}
        attributes = {
            "hue_light_id": light_id,
            "brightness": dimming.get("brightness"),
            "type": light.get("type", "light"),
        }
        entity_id = f"hue.{connection.id}.{light_id}"
        HomeEntity.objects.update_or_create(
            household=connection.household,
            entity_id=entity_id,
            defaults={
                "connection": connection,
                "source": HomeEntity.Source.HUE,
                "domain": "light",
                "name": device_names.get(light_id, str(light.get("metadata", {}).get("name") or f"Hue lamp {light_id}")),
                "state": "on" if on.get("on") else "off",
                "attributes": attributes,
                "is_available": True,
                "is_supported": True,
            },
        )
        seen.add(entity_id)
        count += 1
    HomeEntity.objects.for_household(connection.household).filter(
        source=HomeEntity.Source.HUE,
        connection=connection,
    ).exclude(entity_id__in=seen).update(is_available=False)
    return {"lights": count}


def control_hue_light(entity: HomeEntity, action: str, brightness=None) -> str:
    connection = entity.connection
    if entity.source != HomeEntity.Source.HUE or not connection:
        raise ProviderError("Deze Hue-lamp is niet beschikbaar.")
    light_id = str(entity.attributes.get("hue_light_id") or "")
    if not light_id:
        raise ProviderError("Deze Hue-lamp heeft geen geldige apparaatidentificatie.")
    if action == "on":
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
    else:
        raise ProviderError("Deze Philips Hue-bediening is niet beschikbaar.")
    if not connection.settings.get("bridge_username"):
        raise ProviderError("Bevestig eerst de Philips Hue Bridge.")
    _hue_request(connection, "PUT", f"/route/clip/v2/resource/light/{light_id}", payload)
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
    calendars_response = requests.get("https://graph.microsoft.com/v1.0/me/calendars?$select=id,name", headers=headers, timeout=20)
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
        response = requests.get(url, headers=headers, params={"startDateTime": start.isoformat(), "endDateTime": end.isoformat(), "$select": "id,subject,start,end,isAllDay,location"}, timeout=30)
        payload = _safe_response_json(response, "Outlook")
        for event in payload.get("value", []):
            if not event.get("id"):
                continue
            starts_at = _parse_graph_datetime(event.get("start", {}))
            ends_at = _parse_graph_datetime(event.get("end", {}))
            CalendarEvent.objects.update_or_create(household=connection.household, source=source, external_id=event["id"], defaults={"title": event.get("subject") or "Outlook afspraak", "starts_at": starts_at, "ends_at": ends_at, "is_all_day": bool(event.get("isAllDay")), "location": event.get("location", {}).get("displayName", "")})
            total += 1
        source.last_sync_at = timezone.now()
        source.save(update_fields=["last_sync_at", "updated_at"])
        synced_calendars += 1
    return {"calendars": synced_calendars, "events": total}


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
