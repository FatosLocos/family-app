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

    # Providers that can accept locally created events. LOCAL has no remote to write to and
    # ICS is a one-way subscription format, so neither can ever receive a write-back.
    WRITE_BACK_PROVIDERS = frozenset({Provider.OUTLOOK, Provider.GOOGLE_CALENDAR, Provider.CALDAV})

    provider = models.CharField(max_length=16, choices=Provider.choices)
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    connection = models.ForeignKey("integrations.IntegrationConnection", null=True, blank=True, on_delete=models.SET_NULL, related_name="calendar_sources")
    external_id = models.CharField(max_length=300, blank=True)
    is_enabled = models.BooleanField(default=True)
    is_read_only = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    # Write support fields
    write_access_token = models.TextField(blank=True)  # Encrypted OAuth token or CalDAV password
    caldav_url = models.URLField(blank=True)  # CalDAV server URL (if provider is CALDAV)
    caldav_username = models.CharField(max_length=120, blank=True)  # CalDAV username
    sync_local_events = models.BooleanField(default=True)  # Whether to sync local events back to remote

    @property
    def supports_write_back(self) -> bool:
        """Whether this source's provider is able to receive locally created events at all."""
        return self.provider in self.WRITE_BACK_PROVIDERS


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

    def mark_pending(self) -> None:
        """Queue this event for the next push to its external calendar.

        Every local write path calls this before saving: without it a SYNCED event would keep
        its status after being edited here and planning.tasks.sync_pending_events_to_remote
        would never send the change out. Callers using save(update_fields=...) must include
        "sync_status" and "last_sync_error".
        """
        self.sync_status = self.SyncStatus.PENDING
        self.last_sync_error = ""


class IcsSubscription(PlanningRecord):
    name = models.CharField(max_length=160)
    url = models.URLField()
    source = models.OneToOneField(CalendarSource, on_delete=models.CASCADE, related_name="ics_subscription")
    last_error = models.TextField(blank=True)
