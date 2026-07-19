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


# Every scope the MCP tools currently understand. New tokens get all of
# these until the scope-picker UI ships; after that, a token only gets what
# was explicitly checked when it was created.
ALL_SCOPES = ["vandaag:read", "taken:write", "boodschappen:read", "boodschappen:write", "huis:read", "huis:write", "agenda:read", "agenda:write", "geld:read", "meldingen:read", "meldingen:write"]
SCOPE_LABELS = {
    "vandaag:read": "Dagoverzicht lezen",
    "taken:write": "Taken aanmaken en afronden",
    "boodschappen:read": "Boodschappenlijst lezen",
    "boodschappen:write": "Boodschappen toevoegen",
    "huis:read": "Apparaten in huis lezen",
    "huis:write": "Apparaten in huis bedienen",
    "agenda:read": "Agenda lezen",
    "agenda:write": "Afspraken toevoegen",
    "geld:read": "Financieel overzicht lezen (saldi, transacties, budgetten)",
    "meldingen:read": "Openstaande meldingen lezen",
    "meldingen:write": "Meldingen als afgeleverd markeren",
}

# Categories a user can opt into for proactive push. Each key is the
# dedupe_key prefix used by notifications/tasks.py and integrations/providers.py.
NOTIFICATION_CATEGORIES = {
    "task-overdue": "Achterstallige taken",
    "task-due-soon": "Taken die binnenkort moeten",
    "event-upcoming": "Afspraken binnen 24 uur",
    "recurring-due": "Aankomende afschrijvingen en inkomsten",
    "home-connect-finished": "Apparaat klaar (Home Connect)",
    "home-connect-event": "Apparaat heeft aandacht nodig (Home Connect)",
}


def log_openclaw_action(household, action: str, summary: str, status: str = "success", detail: str = "", user=None) -> None:
    """Record what OpenClaw did through FamilyApp, so it's visible in Instellingen."""
    with household_db_scope(household.id):
        OpenClawActionLog.objects.create(household=household, user=user, action=action, summary=summary[:240], status=status, detail=detail)


def create_token(household, user, label: str | None = None, scopes: list[str] | None = None) -> tuple[OpenClawToken, str]:
    """Mint a new token for this user, revoking any previously active token of theirs."""
    with household_db_scope(household.id):
        OpenClawToken.objects.for_household(household).filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        raw_token = secrets.token_urlsafe(32)
        token = OpenClawToken.objects.create(
            household=household,
            user=user,
            label=(label or str(user)).strip()[:120],
            token_hash=make_password(raw_token),
            scopes=list(scopes) if scopes is not None else list(ALL_SCOPES),
        )
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
        candidates = (
            OpenClawToken.objects.filter(household_id=int(household_part), revoked_at__isnull=True)
            .exclude(token_hash="")
            .select_related("household", "user")
        )
        for token in candidates:
            if check_password(raw_token, token.token_hash):
                return token
        raise TokenError("Token is niet geautoriseerd.")


def require_openclaw_token(scope: str):
    """Authenticate via `Authorization: Bearer <token>` and require it to carry `scope`.

    Enters household_db_scope for the duration of the view, since the usual
    ActiveHouseholdMiddleware never runs for these requests (no session). A
    token missing the required scope is refused with a 403, and the refusal
    is logged too — so a locked-down token is just as visible as a working one.
    """

    def decorator(view_func):
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
                request.openclaw_user = token.user
                OpenClawToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
                if scope not in (token.scopes or []):
                    log_openclaw_action(
                        token.household,
                        "toegang_geweigerd",
                        f"Actie geweigerd: token '{token.label}' mist scope '{scope}'",
                        status="error",
                        user=token.user,
                    )
                    return JsonResponse({"error": f"Dit token heeft geen toestemming voor '{scope}'."}, status=403)
                return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
