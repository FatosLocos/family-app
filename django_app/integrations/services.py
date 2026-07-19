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
SONOS_OAUTH_AUTHORIZE_URL = "https://api.sonos.com/login/v3/oauth"
SONOS_OAUTH_TOKEN_URL = "https://api.sonos.com/login/v3/oauth/access"
SPOTIFY_OAUTH_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_OAUTH_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative"

DROPBOX_OAUTH_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_OAUTH_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_SCOPES = "files.metadata.read files.content.read account_info.read"
HOME_CONNECT_OAUTH_AUTHORIZE_URL = "https://api.home-connect.com/security/oauth/authorize"
HOME_CONNECT_OAUTH_TOKEN_URL = "https://api.home-connect.com/security/oauth/token"
HOME_CONNECT_SCOPES = "IdentifyAppliance Monitor Settings Control"
SMARTCAR_CONNECT_URL = "https://connect.smartcar.com/oauth/authorize"
GOOGLE_HOME_PCM_URL = "https://nestservices.google.com/partnerconnections"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_HOME_SCOPE = "https://www.googleapis.com/auth/sdm.service"


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
        return "", "", {"app_id": "", "device_name": "Family App"}
    if provider == "sonos":
        return "", "", {}
    if provider == "spotify":
        return "", "", {}
    if provider == "smartcar":
        return "", "", {"country": "NL"}
    if provider == "home_connect":
        return "", "", {}
    if provider == "google_home":
        return "", "", {"project_id": ""}
    if provider == "lg_thinq":
        return "", "", {"authorize_url": "", "token_url": "", "api_base_url": "", "devices_path": "/devices"}
    if provider == "dropbox":
        return "", "", {}
    return "", "", {}


def get_sonos_event_callback_token(household) -> str:
    _, _, config = get_app_config(household, "sonos")
    encrypted_token = str(config.get("event_callback_token") or "")
    return decrypt(encrypted_token) if encrypted_token else ""


def save_sonos_config(household, client_id: str, client_secret: str, events_enabled: bool) -> IntegrationAppConfig:
    _, _, existing = get_app_config(household, "sonos")
    token = get_sonos_event_callback_token(household) or secrets.token_urlsafe(32)
    return save_app_config(
        household,
        "sonos",
        client_id,
        client_secret,
        {"event_callback_token": encrypt(token), "events_enabled": events_enabled},
    )


def save_google_home_config(household, client_id: str, client_secret: str, project_id: str, events_enabled: bool, pubsub_subscription: str, pubsub_service_account_json: str) -> IntegrationAppConfig:
    """Keep the Pub/Sub key encrypted and preserve it when its field is blank."""
    _, _, existing = get_app_config(household, "google_home")
    service_account = str(pubsub_service_account_json or "").strip()
    encrypted_service_account = str(existing.get("pubsub_service_account_json") or "")
    if service_account:
        encrypted_service_account = encrypt(service_account)
    return save_app_config(
        household,
        "google_home",
        client_id,
        client_secret,
        {
            "project_id": project_id,
            "events_enabled": bool(events_enabled),
            "pubsub_subscription": str(pubsub_subscription or "").strip(),
            "pubsub_service_account_json": encrypted_service_account,
        },
    )


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
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    device_id = connection.settings.get("device_id") or secrets.token_hex(16)
    request.session["hue_oauth"] = {"state": state, "verifier": verifier, "connection_id": connection.id, "device_id": device_id}
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": f"{public_origin(request)}/instellingen/hue/callback/",
        "state": state,
        "deviceid": device_id,
        "devicename": config.get("device_name") or "Family App",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if config.get("app_id"):
        params["appid"] = config["app_id"]
    return f"{HUE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


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
            "code_verifier": session["verifier"],
            "redirect_uri": f"{public_origin(request)}/instellingen/hue/callback/",
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
        "device_id": session["device_id"],
    }
    connection.status = "needs_bridge_link"
    connection.last_error = ""
    connection.save()
    return connection


def start_sonos_connection(request) -> str:
    client_id, _, _ = get_app_config(request.household, "sonos")
    if not client_id:
        raise ValueError("Vul eerst de Sonos-clientgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.SONOS,
        defaults={"display_name": "Sonos"},
    )
    state = secrets.token_urlsafe(24)
    request.session["sonos_oauth"] = {"state": state, "connection_id": connection.id}
    return f"{SONOS_OAUTH_AUTHORIZE_URL}?{urlencode({'client_id': client_id, 'response_type': 'code', 'state': state, 'scope': 'playback-control-all', 'redirect_uri': f'{public_origin(request)}/instellingen/sonos/callback/'})}"


def finish_sonos_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("sonos_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Sonos-aanmelding.")
    client_id, client_secret, _ = get_app_config(request.household, "sonos")
    if not client_id or not client_secret:
        raise ValueError("Sonos-clientgegevens ontbreken.")
    response = requests.post(
        SONOS_OAUTH_TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": f"{public_origin(request)}/instellingen/sonos/callback/"},
        auth=(client_id, client_secret),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Sonos gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError(str(payload.get("error_description") or "Sonos gaf geen toegangstoken terug."))
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 86400)) - 60, 60))).isoformat(),
    }
    connection.status, connection.last_error = "needs_sync", ""
    connection.save()
    return connection


def start_spotify_connection(request) -> str:
    client_id, _, _ = get_app_config(request.household, "spotify")
    if not client_id:
        raise ValueError("Vul eerst de Spotify-clientgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.SPOTIFY,
        defaults={"display_name": "Spotify Connect"},
    )
    state = secrets.token_urlsafe(24)
    request.session["spotify_oauth"] = {"state": state, "connection_id": connection.id}
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": f"{public_origin(request)}/instellingen/spotify/callback/",
        "scope": SPOTIFY_SCOPES,
        "state": state,
    }
    return f"{SPOTIFY_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def finish_spotify_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("spotify_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Spotify-aanmelding.")
    client_id, client_secret, _ = get_app_config(request.household, "spotify")
    if not client_id or not client_secret:
        raise ValueError("Spotify-clientgegevens ontbreken.")
    response = requests.post(
        SPOTIFY_OAUTH_TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": f"{public_origin(request)}/instellingen/spotify/callback/"},
        auth=(client_id, client_secret),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Spotify gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError(str(payload.get("error_description") or "Spotify gaf geen toegangstoken terug."))
    profile = requests.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {payload['access_token']}"}, timeout=20)
    try:
        account = profile.json() if profile.ok else {}
    except ValueError:
        account = {}
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.external_account = str(account.get("display_name") or account.get("email") or account.get("id") or "")
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat(),
    }
    connection.status, connection.last_error = "needs_sync", ""
    connection.save()
    return connection


def start_dropbox_connection(request) -> str:
    client_id, _, _ = get_app_config(request.household, "dropbox")
    if not client_id:
        raise ValueError("Vul eerst de Dropbox-appgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.DROPBOX,
        defaults={"display_name": "Dropbox"},
    )
    state = secrets.token_urlsafe(24)
    request.session["dropbox_oauth"] = {"state": state, "connection_id": connection.id}
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": f"{public_origin(request)}/instellingen/dropbox/callback/",
        "scope": DROPBOX_SCOPES,
        "state": state,
        "token_access_type": "offline",
    }
    return f"{DROPBOX_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def finish_dropbox_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("dropbox_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Dropbox-aanmelding.")
    client_id, client_secret, _ = get_app_config(request.household, "dropbox")
    if not client_id or not client_secret:
        raise ValueError("Dropbox-appgegevens ontbreken.")
    response = requests.post(
        DROPBOX_OAUTH_TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": f"{public_origin(request)}/instellingen/dropbox/callback/"},
        auth=(client_id, client_secret),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Dropbox gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError(str(payload.get("error_description") or "Dropbox gaf geen toegangstoken terug."))
    profile = requests.post("https://api.dropboxapi.com/2/users/get_current_account", headers={"Authorization": f"Bearer {payload['access_token']}"}, timeout=20)
    try:
        account = profile.json() if profile.ok else {}
    except ValueError:
        account = {}
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.external_account = str(account.get("email") or (account.get("name") or {}).get("display_name") or "")
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 14400)) - 60, 60))).isoformat(),
    }
    connection.status, connection.last_error = "connected", ""
    connection.save()
    return connection


def start_home_connect_connection(request) -> str:
    client_id, _, _ = get_app_config(request.household, "home_connect")
    if not client_id:
        raise ValueError("Vul eerst de Home Connect-clientgegevens in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.HOME_CONNECT,
        defaults={"display_name": "Home Connect"},
    )
    state = secrets.token_urlsafe(24)
    request.session["home_connect_oauth"] = {"state": state, "connection_id": connection.id}
    return f"{HOME_CONNECT_OAUTH_AUTHORIZE_URL}?{urlencode({'client_id': client_id, 'response_type': 'code', 'redirect_uri': f'{public_origin(request)}/instellingen/home-connect/callback/', 'scope': HOME_CONNECT_SCOPES, 'state': state})}"


def finish_home_connect_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("home_connect_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Home Connect-aanmelding.")
    client_id, client_secret, _ = get_app_config(request.household, "home_connect")
    if not client_id or not client_secret:
        raise ValueError("Home Connect-clientgegevens ontbreken.")
    response = requests.post(
        HOME_CONNECT_OAUTH_TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": f"{public_origin(request)}/instellingen/home-connect/callback/"},
        auth=(client_id, client_secret),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Home Connect gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError(str(payload.get("error_description") or payload.get("error") or "Home Connect gaf geen toegangstoken terug."))
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat(),
    }
    connection.status, connection.last_error = "needs_sync", ""
    connection.save()
    return connection


def start_smartcar_connection(request) -> str:
    _, _, config = get_app_config(request.household, "smartcar")
    connect_client_id = str(config.get("connect_client_id") or "").strip()
    if not connect_client_id:
        raise ValueError("Vul eerst het Smartcar Connect client ID uit de appconfiguratie in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.SMARTCAR,
        defaults={"display_name": "Smartcar"},
    )
    state = secrets.token_urlsafe(24)
    request.session["smartcar_oauth"] = {"state": state, "connection_id": connection.id}
    params = {
        "response_type": "code",
        "client_id": connect_client_id,
        "redirect_uri": f"{public_origin(request)}/instellingen/smartcar/callback/",
        "state": state,
        "mode": "live",
    }
    country = str(config.get("country") or "").strip().upper()
    if country:
        params["country"] = country
    return f"{SMARTCAR_CONNECT_URL}?{urlencode(params)}"


def finish_smartcar_connection(request, user_id: str, state: str) -> IntegrationConnection:
    session = request.session.pop("smartcar_oauth", {})
    if not session or not secrets.compare_digest(str(session.get("state") or ""), state):
        raise ValueError("Ongeldige of verlopen Smartcar-aanmelding.")
    if not user_id:
        raise ValueError("Smartcar gaf geen voertuigverbinding terug.")
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    data = dict(connection.settings) if isinstance(connection.settings, dict) else {}
    data["smartcar_user_id"] = user_id
    connection.settings = data
    connection.external_account = "Smartcar-voertuigen"
    connection.status = "needs_sync"
    connection.last_error = ""
    connection.save(update_fields=["settings", "external_account", "status", "last_error", "updated_at"])
    return connection


def start_google_home_connection(request) -> str:
    client_id, _, config = get_app_config(request.household, "google_home")
    project_id = str(config.get("project_id") or "")
    if not client_id or not project_id:
        raise ValueError("Vul eerst de Google Home-clientgegevens en het Device Access project ID in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.GOOGLE_HOME,
        defaults={"display_name": "Google Home"},
    )
    state = secrets.token_urlsafe(24)
    request.session["google_home_oauth"] = {"state": state, "connection_id": connection.id}
    params = {"redirect_uri": f"{public_origin(request)}/instellingen/google-home/callback/", "access_type": "offline", "prompt": "consent", "client_id": client_id, "response_type": "code", "scope": GOOGLE_HOME_SCOPE, "state": state}
    return f"{GOOGLE_HOME_PCM_URL}/{project_id}/auth?{urlencode(params)}"


def finish_google_home_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("google_home_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen Google Home-aanmelding.")
    client_id, client_secret, config = get_app_config(request.household, "google_home")
    if not client_id or not client_secret or not config.get("project_id"):
        raise ValueError("Google Home-clientgegevens of Device Access project ID ontbreken.")
    response = requests.post(
        GOOGLE_OAUTH_TOKEN_URL,
        data={"client_id": client_id, "client_secret": client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": f"{public_origin(request)}/instellingen/google-home/callback/"},
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Google gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError(str(payload.get("error_description") or "Google gaf geen toegangstoken terug."))
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat(),
        "project_id": config["project_id"],
    }
    connection.status, connection.last_error = "needs_sync", ""
    connection.save()
    return connection


def start_lg_thinq_connection(request) -> str:
    client_id, _, config = get_app_config(request.household, "lg_thinq")
    if not client_id or not config.get("authorize_url"):
        raise ValueError("Vul eerst de LG ThinQ-clientgegevens en OAuth-endpoints uit de Smart Solution API in.")
    connection, _ = IntegrationConnection.objects.get_or_create(
        household=request.household,
        user=request.user,
        provider=IntegrationConnection.Provider.LG_THINQ,
        defaults={"display_name": "LG ThinQ"},
    )
    state = secrets.token_urlsafe(24)
    request.session["lg_thinq_oauth"] = {"state": state, "connection_id": connection.id}
    return f"{config['authorize_url']}?{urlencode({'client_id': client_id, 'response_type': 'code', 'redirect_uri': f'{public_origin(request)}/instellingen/lg-thinq/callback/', 'state': state})}"


def finish_lg_thinq_connection(request, code: str, state: str) -> IntegrationConnection:
    session = request.session.pop("lg_thinq_oauth", {})
    if not session or not secrets.compare_digest(session.get("state", ""), state):
        raise ValueError("Ongeldige of verlopen LG ThinQ-aanmelding.")
    client_id, client_secret, config = get_app_config(request.household, "lg_thinq")
    if not client_id or not client_secret or not config.get("token_url") or not config.get("api_base_url"):
        raise ValueError("LG ThinQ-clientgegevens of API-endpoints ontbreken.")
    response = requests.post(
        config["token_url"],
        data={"client_id": client_id, "client_secret": client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": f"{public_origin(request)}/instellingen/lg-thinq/callback/"},
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("LG ThinQ gaf geen geldige OAuth-reactie.") from error
    if not response.ok or not payload.get("access_token"):
        raise ValueError(str(payload.get("error_description") or "LG ThinQ gaf geen toegangstoken terug."))
    connection = IntegrationConnection.objects.get(pk=session["connection_id"], household=request.household)
    connection.secret_encrypted = encrypt(payload.get("refresh_token", ""))
    connection.settings = {
        "access_token": encrypt(payload["access_token"]),
        "expires_at": (timezone.now() + timedelta(seconds=max(int(payload.get("expires_in", 3600)) - 60, 60))).isoformat(),
        "api_base_url": config["api_base_url"].rstrip("/"),
        "devices_path": str(config.get("devices_path") or "/devices"),
    }
    connection.status, connection.last_error = "needs_sync", ""
    connection.save()
    return connection
