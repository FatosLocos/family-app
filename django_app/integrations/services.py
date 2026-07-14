from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from integrations.crypto import decrypt, encrypt
from integrations.models import IntegrationAppConfig, IntegrationConnection

OUTLOOK_SCOPES = "offline_access User.Read Calendars.Read"
HUE_OAUTH_AUTHORIZE_URL = "https://api.meethue.com/v2/oauth2/authorize"
HUE_OAUTH_TOKEN_URL = "https://api.meethue.com/v2/oauth2/token"


def public_origin(request) -> str:
    return request.build_absolute_uri("/").rstrip("/")


def get_app_config(household, provider: str) -> tuple[str, str, dict]:
    configured = IntegrationAppConfig.objects.filter(household=household, provider=provider).first()
    if configured:
        return configured.client_id, decrypt(configured.client_secret_encrypted), configured.settings
    if provider == "outlook":
        return settings.OUTLOOK_CALENDAR_CLIENT_ID, settings.OUTLOOK_CALENDAR_CLIENT_SECRET, {"tenant_id": "consumers"}
    if provider == "bunq":
        return settings.BUNQ_OAUTH_CLIENT_ID, settings.BUNQ_OAUTH_CLIENT_SECRET, {"environment": "production"}
    if provider == "hue":
        return "", "", {"app_id": "family-app", "device_name": "Family App"}
    return "", "", {}


def save_app_config(household, provider: str, client_id: str, client_secret: str, config: dict) -> IntegrationAppConfig:
    stored, _ = IntegrationAppConfig.objects.get_or_create(household=household, provider=provider)
    stored.client_id = client_id
    if client_secret:
        stored.client_secret_encrypted = encrypt(client_secret)
    stored.settings = config
    stored.save()
    return stored


def start_outlook_connection(request) -> str:
    client_id, _, config = get_app_config(request.household, "outlook")
    if not client_id:
        raise ValueError("Vul eerst de Outlook clientgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(household=request.household, user=request.user, provider="outlook", defaults={"display_name": "Outlook agenda"})
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    request.session["outlook_oauth"] = {"state": state, "verifier": verifier, "connection_id": connection.id}
    tenant = config.get("tenant_id", "consumers")
    params = urlencode({"client_id": client_id, "response_type": "code", "response_mode": "query", "redirect_uri": f"{public_origin(request)}/instellingen/outlook/callback/", "scope": OUTLOOK_SCOPES, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{params}"


def finish_outlook_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("outlook_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Outlook-aanmelding.")
    client_id, client_secret, config = get_app_config(request.household, "outlook")
    if not client_id or not client_secret:
        raise ValueError("Outlook clientgegevens ontbreken.")
    response = requests.post(f"https://login.microsoftonline.com/{config.get('tenant_id', 'consumers')}/oauth2/v2.0/token", data={"client_id": client_id, "client_secret": client_secret, "code": code, "code_verifier": session["verifier"], "redirect_uri": f"{public_origin(request)}/instellingen/outlook/callback/", "grant_type": "authorization_code"}, timeout=20)
    payload = response.json()
    if not response.ok or not payload.get("access_token"):
        raise ValueError(payload.get("error_description", "Outlook gaf geen toegangstoken terug."))
    profile = requests.get("https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName", headers={"Authorization": f"Bearer {payload['access_token']}"}, timeout=20).json()
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.external_account = profile.get("mail") or profile.get("userPrincipalName") or ""
    connection.settings = {"access_token": encrypt(payload["access_token"]), "expires_at": (timezone.now() + timedelta(seconds=int(payload.get("expires_in", 3600)) - 60)).isoformat(), "tenant_id": config.get("tenant_id", "consumers")}
    connection.status = "configured"
    connection.last_error = ""
    connection.save()
    return connection


def start_bunq_connection(request) -> str:
    client_id, _, config = get_app_config(request.household, "bunq")
    if not client_id:
        raise ValueError("Vul eerst de bunq OAuth-clientgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(household=request.household, user=request.user, provider="bunq", defaults={"display_name": "bunq"})
    state = secrets.token_urlsafe(24)
    request.session["bunq_oauth"] = {"state": state, "connection_id": connection.id}
    host = "https://oauth.sandbox.bunq.com/auth" if config.get("environment") == "sandbox" else "https://oauth.bunq.com/auth"
    return f"{host}?{urlencode({'response_type': 'code', 'client_id': client_id, 'redirect_uri': f'{public_origin(request)}/instellingen/bunq/callback/', 'state': state})}"


def finish_bunq_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("bunq_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen bunq-aanmelding.")
    client_id, client_secret, config = get_app_config(request.household, "bunq")
    environment = config.get("environment", "production")
    endpoint = "https://api-oauth.sandbox.bunq.com/v1/token" if environment == "sandbox" else "https://api.oauth.bunq.com/v1/token"
    response = requests.post(endpoint, params={"grant_type": "authorization_code", "code": code, "redirect_uri": f"{public_origin(request)}/instellingen/bunq/callback/", "client_id": client_id, "client_secret": client_secret}, timeout=20)
    payload = response.json()
    if not response.ok or not payload.get("access_token"):
        raise ValueError(payload.get("error_description", payload.get("error", "bunq gaf geen toegangstoken terug.")))
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload["access_token"])
    connection.settings = {"environment": environment, "token_type": payload.get("token_type", "bearer")}
    connection.status = "needs_sync"
    connection.last_error = ""
    connection.save()
    return connection


def start_hue_connection(request) -> str:
    client_id, _, config = get_app_config(request.household, "hue")
    if not client_id:
        raise ValueError("Vul eerst de Philips Hue-clientgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.HUE,
        defaults={"display_name": "Philips Hue"},
    )
    state = secrets.token_urlsafe(24)
    device_id = connection.settings.get("device_id") or secrets.token_hex(16)
    request.session["hue_oauth"] = {"state": state, "connection_id": connection.id, "device_id": device_id}
    app_id = config.get("app_id") or "family-app"
    params = urlencode({
        "client_id": client_id,
        "clientid": client_id,
        "response_type": "code",
        "redirect_uri": f"{public_origin(request)}/instellingen/hue/callback/",
        "state": state,
        "appid": app_id,
        "deviceid": device_id,
        "devicename": config.get("device_name") or "Family App",
    })
    return f"{HUE_OAUTH_AUTHORIZE_URL}?{params}"


def finish_hue_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("hue_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Philips Hue-aanmelding.")
    client_id, client_secret, config = get_app_config(request.household, "hue")
    if not client_id or not client_secret:
        raise ValueError("Philips Hue-clientgegevens ontbreken.")
    response = requests.post(
        HUE_OAUTH_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{public_origin(request)}/instellingen/hue/callback/",
            "client_id": client_id,
        },
        auth=(client_id, client_secret),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Philips Hue gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError("Philips Hue gaf geen toegangstoken terug. Controleer de redirect-URL en clientgegevens.")
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat(),
        "app_id": config.get("app_id") or "family-app",
        "device_id": session["device_id"],
    }
    connection.status = "needs_bridge_link"
    connection.last_error = ""
    connection.save()
    return connection
