from __future__ import annotations

from collections.abc import Iterable

import requests


NEST_JWT_URL = "https://nestauthproxyservice-pa.googleapis.com/v1/issue_jwt"
NEST_SESSION_URL = "https://home.nest.com/session"


class NestProtectError(RuntimeError):
    """The unofficial Nest Protect session could not be read."""


class NestProtectAuthError(NestProtectError):
    """Google cookies or the issue token need to be renewed locally."""


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _battery_percent(millivolts):
    """Estimate the percentage using the Protect battery curve published by HA."""
    raw = _as_int(millivolts, 0)
    if raw <= 3000 or raw > 6000:
        return None
    if raw > 4950:
        slope, intercept = 0.001816609, -8.548096886
    elif raw > 4800:
        slope, intercept = 0.000291667, -0.991176471
    elif raw > 4500:
        slope, intercept = 0.001077342, -4.730392157
    else:
        slope, intercept = 0.000434641, -1.825490196
    return max(0, min(100, round((slope * raw + intercept) * 100)))


class NestProtectAdapter:
    """Read Nest Protect data using Nest's undocumented Google-account API.

    This adapter is deliberately read-only. A Nest Protect remains a physical
    safety device; the Family App only mirrors its status for awareness.
    """

    name = "nest_protect"

    def __init__(self, config, session=None):
        self.config = config if isinstance(config, dict) else {}
        self.issue_token = str(self.config.get("issue_token") or "").strip()
        self.cookies = str(self.config.get("cookies") or "").strip()
        self.session = session or requests.Session()
        self.last_error = ""
        self.last_sync_mode = "disabled"

    @property
    def enabled(self):
        return bool(self.issue_token and self.cookies)

    def event_status(self):
        return {
            "mode": self.last_sync_mode,
            "reauth_required": bool(self.last_error),
            "error": self.last_error[:180],
        }

    def _google_access_token(self):
        response = self.session.get(
            self.issue_token,
            headers={
                "Sec-Fetch-Mode": "cors",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://accounts.google.com/o/oauth2/iframe",
                "Cookie": self.cookies,
            },
            timeout=15,
        )
        if response.status_code in {401, 403}:
            raise NestProtectAuthError("Google-aanmelding verlopen. Koppel Nest Protect opnieuw op de lokale probe.")
        response.raise_for_status()
        token = (response.json() or {}).get("access_token")
        if not token:
            raise NestProtectAuthError("Google gaf geen toegangstoken terug. Koppel Nest Protect opnieuw op de lokale probe.")
        return str(token)

    def _nest_session(self):
        google_token = self._google_access_token()
        response = self.session.post(
            NEST_JWT_URL,
            data={
                "embed_google_oauth_access_token": "true",
                "expire_after": "3600s",
                "google_oauth_access_token": google_token,
                "policy_id": "authproxy-oauth-policy",
            },
            headers={"Authorization": f"Bearer {google_token}"},
            timeout=15,
        )
        if response.status_code in {401, 403}:
            raise NestProtectAuthError("Google-autorisatie geweigerd. Koppel Nest Protect opnieuw op de lokale probe.")
        response.raise_for_status()
        jwt = (response.json() or {}).get("jwt")
        if not jwt:
            raise NestProtectAuthError("Nest kon geen sessietoken maken. Koppel Nest Protect opnieuw op de lokale probe.")
        response = self.session.get(
            NEST_SESSION_URL,
            headers={
                "Authorization": f"Basic {jwt}",
                "Cookie": f"G_ENABLED_IDPS=google; eu_cookie_accepted=1; viewer-volume=0.5; cztoken={jwt}",
            },
            timeout=15,
        )
        if response.status_code in {401, 403}:
            raise NestProtectAuthError("Nest-sessie verlopen. Koppel Nest Protect opnieuw op de lokale probe.")
        response.raise_for_status()
        payload = response.json() or {}
        if not payload.get("access_token") or not payload.get("userid"):
            raise NestProtectAuthError("Nest-sessie bevat geen geldige gebruiker. Koppel Nest Protect opnieuw op de lokale probe.")
        return payload

    def _buckets(self):
        session = self._nest_session()
        headers = {
            "Authorization": f"Basic {session['access_token']}",
            "X-nl-user-id": str(session["userid"]),
            "X-nl-protocol-version": "1",
        }
        response = self.session.post(
            f"https://home.nest.com/api/0.1/user/{session['userid']}/app_launch",
            headers=headers,
            json={"known_bucket_types": ["kryptonite", "structure", "topaz", "where", "user"], "known_bucket_versions": []},
            timeout=20,
        )
        if response.status_code in {401, 403}:
            raise NestProtectAuthError("Nest-toegang geweigerd. Koppel Nest Protect opnieuw op de lokale probe.")
        response.raise_for_status()
        payload = response.json() or {}
        return payload.get("updated_buckets") or []

    @staticmethod
    def _location_names(buckets: Iterable[dict]):
        locations = {}
        for bucket in buckets:
            if not isinstance(bucket, dict) or not str(bucket.get("object_key") or "").startswith("where."):
                continue
            values = bucket.get("value") if isinstance(bucket.get("value"), dict) else {}
            for item in values.get("wheres") or []:
                if isinstance(item, dict) and item.get("where_id"):
                    locations[str(item["where_id"])] = str(item.get("name") or "Onbekende ruimte")
        return locations

    @classmethod
    def entities_from_buckets(cls, buckets):
        buckets = [bucket for bucket in buckets if isinstance(bucket, dict)]
        locations = cls._location_names(buckets)
        entities = []
        for bucket in buckets:
            object_key = str(bucket.get("object_key") or "")
            if not object_key.startswith("topaz."):
                continue
            values = bucket.get("value") if isinstance(bucket.get("value"), dict) else {}
            where_name = locations.get(str(values.get("where_id") or ""), "")
            smoke = _as_int(values.get("smoke_status"))
            co = _as_int(values.get("co_status"))
            heat = _as_int(values.get("heat_status"))
            issue_fields = ("battery_health_state", "wifi_status", "component_smoke_test_passed", "component_co_test_passed", "component_heat_test_passed")
            issues = [field.removeprefix("component_").removesuffix("_passed").replace("_", " ") for field in issue_fields if values.get(field) not in {None, 0, "0", True, "ok"}]
            if co:
                state = "co"
            elif smoke:
                state = "smoke"
            elif heat:
                state = "heat"
            elif issues:
                state = "warning"
            else:
                state = "normal"
            removed = bool(values.get("removed_from_base"))
            serial = str(values.get("serial_number") or values.get("device_id") or object_key)
            label = str(values.get("name") or where_name or "Nest Protect")
            attributes = {
                "nest_protect_id": object_key,
                "nest_location": where_name,
                "nest_model": str(values.get("model_name") or values.get("model_version") or "Nest Protect"),
                "nest_smoke_status": smoke,
                "nest_co_status": co,
                "nest_heat_status": heat,
                "nest_battery_mv": _as_int(values.get("battery_level")) or None,
                "nest_battery_percent": _battery_percent(values.get("battery_level")),
                "nest_line_power": bool(values.get("line_power_present")),
                "nest_wired": str(values.get("wired_or_battery") or "").lower() == "wired",
                "nest_occupancy": "thuis" if values.get("auto_away") is False and values.get("line_power_present") else "",
                "nest_removed_from_base": removed,
                "nest_component_issues": issues,
            }
            entities.append({
                "source": cls.name,
                "local_key": object_key,
                "external_id": serial,
                "domain": "safety",
                "name": label,
                "state": state,
                "is_available": not removed,
                "is_supported": False,
                "attributes": attributes,
            })
        return entities

    def inventory(self):
        if not self.enabled:
            self.last_sync_mode = "disabled"
            self.last_error = ""
            return []
        try:
            entities = self.entities_from_buckets(self._buckets())
        except (NestProtectError, requests.RequestException, ValueError) as error:
            self.last_sync_mode = "needs_reauth" if isinstance(error, NestProtectAuthError) else "error"
            self.last_error = str(error)
            if isinstance(error, NestProtectError):
                raise
            raise NestProtectError("Nest Protect kon niet worden bijgewerkt. Controleer de lokale netwerkverbinding.") from error
        self.last_sync_mode = "polling"
        self.last_error = ""
        return entities
