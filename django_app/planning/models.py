from django.conf import settings
from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class PlanningRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        abstract = True


class CalendarSource(PlanningRecord):
    class Provider(models.TextChoices):
        LOCAL = "local", "Lokaal"
        OUTLOOK = "outlook", "Outlook"
        ICS = "ics", "ICS"
        GOOGLE_CALENDAR = "google_calendar", "Google Calendar"
        CALDAV = "caldav", "CalDAV"

    provider = models.CharField(max_length=16, choices=Provider.choices)
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    external_id = models.CharField(max_length=300, blank=True)
    is_enabled = models.BooleanField(default=True)
    is_read_only = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    # Write support fields
    write_access_token = models.TextField(blank=True)  # Encrypted OAuth token or CalDAV password
    caldav_url = models.URLField(blank=True)  # CalDAV server URL (if provider is CALDAV)
    caldav_username = models.CharField(max_length=120, blank=True)  # CalDAV username
    sync_local_events = models.BooleanField(default=True)  # Whether to sync local events back to remote


class CalendarEvent(PlanningRecord):
    class SyncStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        CONFLICT = "conflict", "Conflict"
        ERROR = "error", "Error"

    source = models.ForeignKey(CalendarSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    external_id = models.CharField(max_length=300, blank=True)
    title = models.CharField(max_length=240)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_all_day = models.BooleanField(default=False)
    location = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="calendar_events")

    # Write sync tracking
    sync_status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_sync_error = models.CharField(max_length=500, blank=True)
    remote_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("starts_at",)
        indexes = [models.Index(fields=("household", "starts_at")), models.Index(fields=("source", "external_id"))]


class IcsSubscription(PlanningRecord):
    name = models.CharField(max_length=160)
    url = models.URLField()
    source = models.OneToOneField(CalendarSource, on_delete=models.CASCADE, related_name="ics_subscription")
    last_error = models.TextField(blank=True)
