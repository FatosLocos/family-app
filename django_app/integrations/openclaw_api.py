"""Bearer-token API access for the OpenClaw chat agent.

Mirrors the LocalProbe pairing pattern in integrations/local_probe.py: a
household-prefixed composite token (f"{household_id}.{raw_token}") lets an
inbound request resolve its RLS scope before touching the database, since
there is no session middleware for non-browser callers.
"""
from __future__ import annotations

import functools
import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from common.db_scope import household_db_scope
from integrations.models import OpenClawActionLog, OpenClawToken


class TokenError(Exception):
    pass


def log_openclaw_action(household, action: str, summary: str, status: str = "success", detail: str = "") -> None:
    """Record what OpenClaw did through FamilyApp, so it's visible in Instellingen."""
    with household_db_scope(household.id):
        OpenClawActionLog.objects.create(household=household, action=action, summary=summary[:240], status=status, detail=detail)


def create_token(household, label: str = "OpenClaw") -> tuple[OpenClawToken, str]:
    """Mint a new token, revoking any previously active one for this household."""
    with household_db_scope(household.id):
        OpenClawToken.objects.for_household(household).filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        raw_token = secrets.token_urlsafe(32)
        token = OpenClawToken.objects.create(household=household, label=(label or "OpenClaw").strip()[:120], token_hash=make_password(raw_token))
    return token, f"{household.id}.{raw_token}"


def revoke_token(token: OpenClawToken) -> None:
    with household_db_scope(token.household_id):
        token.revoked_at = timezone.now()
        token.token_hash = ""
        token.save(update_fields=["revoked_at", "token_hash", "updated_at"])


def authenticate_token(bearer_value: str) -> OpenClawToken:
    household_part, separator, raw_token = (bearer_value or "").partition(".")
    if not separator or not household_part.isdigit() or not raw_token:
        raise TokenError("Ongeldig token.")
    with household_db_scope(int(household_part)):
        token = (
            OpenClawToken.objects.filter(household_id=int(household_part), revoked_at__isnull=True)
            .exclude(token_hash="")
            .select_related("household")
            .first()
        )
        if not token or not check_password(raw_token, token.token_hash):
            raise TokenError("Token is niet geautoriseerd.")
        return token


def require_openclaw_token(view_func):
    """Authenticate via `Authorization: Bearer <token>` instead of a session cookie.

    Enters household_db_scope for the duration of the view, since the usual
    ActiveHouseholdMiddleware never runs for these requests (no session).
    """

    @csrf_exempt
    @functools.wraps(view_func)
    def wrapped(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return JsonResponse({"error": "Ontbrekende of ongeldige Authorization-header."}, status=401)
        try:
            token = authenticate_token(header.removeprefix("Bearer ").strip())
        except TokenError as error:
            return JsonResponse({"error": str(error)}, status=401)
        with household_db_scope(token.household_id):
            request.household = token.household
            OpenClawToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
            return view_func(request, *args, **kwargs)

    return wrapped
