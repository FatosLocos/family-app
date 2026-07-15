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
        SONOS = "sonos", "Sonos"
        NEST_PROTECT = "nest_protect", "Nest Protect"
        LG_THINQ = "lg_thinq", "LG ThinQ"
        GOOGLE_HOME = "google_home", "Google Home"
        SPOTIFY = "spotify", "Spotify"
        SMARTCAR = "smartcar", "Smartcar"
        GOOGLE_CAST = "google_cast", "Google Cast"
        PHILIPS_TV = "philips_tv", "Philips TV"
        HOME_CONNECT = "home_connect", "Home Connect"

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


class EnergyReading(models.Model):
    """Track energy consumption readings over time."""

    class Unit(models.TextChoices):
        KWH = "kwh", "kWh"
        WH = "wh", "Wh"
        MJ = "mj", "MJ"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="energy_readings")
    source = models.CharField(max_length=80, default="grid")  # "grid", "solar", "battery", etc.
    consumption_kwh = models.DecimalField(max_digits=10, decimal_places=2)  # kWh consumed
    production_kwh = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # kWh produced (solar)
    timestamp = models.DateTimeField(db_index=True)
    cost_eur = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-timestamp",)
        indexes = [models.Index(fields=["household", "-timestamp"]), models.Index(fields=["source", "-timestamp"])]


class EVVehicle(models.Model):
    """Track electric vehicles in the household."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="ev_vehicles")
    name = models.CharField(max_length=120)
    make = models.CharField(max_length=80, blank=True)
    model = models.CharField(max_length=80, blank=True)
    battery_capacity_kwh = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    current_soc_percent = models.PositiveSmallIntegerField(default=0)  # State of charge
    current_range_km = models.PositiveIntegerField(default=0)  # Estimated range in km
    integration_provider = models.CharField(max_length=32, blank=True)  # e.g., "smartcar", "tesla_api"
    external_id = models.CharField(max_length=300, blank=True)
    is_charging = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.make} {self.model} ({self.current_soc_percent}%)"


class EVChargingSession(models.Model):
    """Track EV charging sessions."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="ev_charging_sessions")
    vehicle = models.ForeignKey(EVVehicle, on_delete=models.CASCADE, related_name="charging_sessions")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    start_soc_percent = models.PositiveSmallIntegerField()
    end_soc_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    energy_added_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    cost_eur = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-start_time",)
        indexes = [models.Index(fields=["vehicle", "-start_time"])]

    @property
    def duration_minutes(self) -> int | None:
        if self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return None
