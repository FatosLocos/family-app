from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class HomeAssistantConfig(models.Model):
    household = models.OneToOneField(Household, on_delete=models.CASCADE, related_name="home_assistant")
    base_url = models.URLField(max_length=500)
    token_encrypted = models.TextField()
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()


class HomeEntity(models.Model):
    class Source(models.TextChoices):
        HOME_ASSISTANT = "home_assistant", "Home Assistant"
        HUE = "hue", "Philips Hue"

    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    connection = models.ForeignKey("integrations.IntegrationConnection", null=True, blank=True, on_delete=models.CASCADE, related_name="home_entities")
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.HOME_ASSISTANT)
    entity_id = models.CharField(max_length=255)
    domain = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=255, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    is_available = models.BooleanField(default=True)
    is_supported = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "entity_id"), name="unique_home_entity_per_household")]
        ordering = ("domain", "name")


class HomeActionAudit(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    entity = models.ForeignKey(HomeEntity, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions")
    action = models.CharField(max_length=64)
    succeeded = models.BooleanField(default=False)
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-created_at",)


class MaintenanceItem(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=80, blank=True)
    due_date = models.DateField(null=True, blank=True)
    cadence_days = models.PositiveIntegerField(default=365)
    last_completed_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("due_date", "title")


class EmergencyContact(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    label = models.CharField(max_length=120)
    value = models.CharField(max_length=300)
    kind = models.CharField(max_length=40, default="contact")
    notes = models.CharField(max_length=300, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    objects = HouseholdManager()

    class Meta:
        ordering = ("sort_order", "label")


class Room(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    icon = models.CharField(max_length=40, default="armchair")
    sort_order = models.PositiveIntegerField(default=0)
    objects = HouseholdManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "name"), name="unique_room_per_household")]
        ordering = ("sort_order", "name")


class FurnishingItem(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=80, blank=True)
    location_detail = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("room__sort_order", "name")


def household_document_path(instance, filename):
    return f"documents/{instance.household_id}/{uuid4().hex}{Path(filename).suffix.lower()}"


class HouseholdDocument(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, blank=True)
    file = models.FileField(upload_to=household_document_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-created_at",)
