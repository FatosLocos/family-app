from django.conf import settings
from django.db import models

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
        constraints = [models.UniqueConstraint(fields=("household", "user", "provider"), name="unique_household_user_provider_connection")]


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
