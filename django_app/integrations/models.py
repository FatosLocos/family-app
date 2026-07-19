from django.conf import settings
from django.db import models
from uuid import uuid4

from common.scoping import HouseholdManager
from households.models import Household


class IntegrationAppConfig(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    provider = models.CharField(max_length=32)
    client_id = models.CharField(max_length=240, blank=True)
    client_secret_encrypted = models.TextField(blank=True)
    settings = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "provider"), name="unique_household_integration_config")]


class IntegrationConnection(models.Model):
    class Provider(models.TextChoices):
        OUTLOOK = "outlook", "Outlook"
        BUNQ = "bunq", "bunq"
        HUE = "hue", "Philips Hue"
        SONOS = "sonos", "Sonos"
        LG_THINQ = "lg_thinq", "LG ThinQ"
        GOOGLE_HOME = "google_home", "Google Home"
        SPOTIFY = "spotify", "Spotify"
        SMARTCAR = "smartcar", "Smartcar"
        HOME_CONNECT = "home_connect", "Home Connect"
        DROPBOX = "dropbox", "Dropbox"
        IMAP = "imap", "IMAP e-mail"

    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=32, choices=Provider.choices)
    display_name = models.CharField(max_length=160)
    status = models.CharField(max_length=24, default="needs_auth")
    external_account = models.CharField(max_length=240, blank=True)
    secret_encrypted = models.TextField(blank=True)
    settings = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("household", "user", "provider"),
                condition=~models.Q(provider="imap"),
                name="unique_household_user_provider_connection",
            ),
            models.UniqueConstraint(
                fields=("household", "user", "provider", "external_account"),
                condition=models.Q(provider="imap"),
                name="unique_household_user_imap_account",
            ),
        ]


class SyncRun(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    connection = models.ForeignKey(IntegrationConnection, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=20, default="queued")
    detail = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class IntegrationAudit(models.Model):
    class Action(models.TextChoices):
        CONNECTED = "connected", "Gekoppeld"
        SYNC_SUCCEEDED = "sync_succeeded", "Synchronisatie geslaagd"
        SYNC_FAILED = "sync_failed", "Synchronisatie mislukt"
        DISCONNECTED = "disconnected", "Ontkoppeld"

    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    connection = models.ForeignKey(IntegrationConnection, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=32)
    action = models.CharField(max_length=32, choices=Action.choices)
    detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-created_at",)


class LocalProbe(models.Model):
    """A household-owned agent that can safely reach devices on the home LAN."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="local_probes")
    name = models.CharField(max_length=120, default="Lokale probe")
    token_hash = models.CharField(max_length=255, blank=True)
    pairing_code_hash = models.CharField(max_length=255, blank=True)
    pairing_expires_at = models.DateTimeField(null=True, blank=True)
    version = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=24, default="pairing")
    adapters = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-last_seen_at", "name")


class OpenClawToken(models.Model):
    """A household-scoped bearer credential for the OpenClaw chat agent to call our API."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="openclaw_tokens")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="openclaw_tokens")
    label = models.CharField(max_length=120, default="OpenClaw")
    token_hash = models.CharField(max_length=255)
    scopes = models.JSONField(default=list, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-created_at",)


class OpenClawActionLog(models.Model):
    """Audit trail of what OpenClaw did through FamilyApp, for user-visible transparency."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="openclaw_action_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="openclaw_action_logs")
    source = models.CharField(max_length=40, default="family-app")
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=240)
    status = models.CharField(max_length=10, choices=(("success", "Gelukt"), ("error", "Mislukt")), default="success")
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-created_at",)


class OpenClawNotificationPreference(models.Model):
    """Which notification categories a user wants proactively pushed to their own OpenClaw/WhatsApp."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="openclaw_notification_preferences")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="openclaw_notification_preferences")
    categories = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "user"), name="unique_household_user_notification_preference")]


class LocalDiscovery(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="local_discoveries")
    probe = models.ForeignKey(LocalProbe, on_delete=models.CASCADE, related_name="discoveries")
    key = models.CharField(max_length=300)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=80)
    address = models.GenericIPAddressField(null=True, blank=True)
    method = models.CharField(max_length=40)
    details = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("probe", "key"), name="unique_probe_discovery_key")]
        ordering = ("kind", "name")
