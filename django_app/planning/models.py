from django.conf import settings
from django.db import models

from common.scoping import HouseholdManager, HouseholdQuerySet
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

    @property
    def accepts_local_events(self) -> bool:
        """Whether planning.tasks.sync_pending_events_to_remote really pushes to this calendar.

        This repeats every gate that task applies, credentials included, so the Agenda tab and
        OpenClaw's agenda_bronnen can never promise a write-back that silently never happens.
        """
        if not (self.supports_write_back and self.is_enabled and self.sync_local_events and not self.is_read_only):
            return False
        if self.provider == self.Provider.OUTLOOK:
            # external_id is the Graph calendar id the push writes to, connection is the mailbox
            # whose token it writes with; without either there is nothing to push to.
            return self.connection_id is not None and bool(self.external_id)
        if self.provider == self.Provider.CALDAV:
            return bool(self.caldav_url and self.write_access_token)
        return bool(self.write_access_token)

    @classmethod
    def write_back_target(cls, household):
        """The one calendar that currently receives this household's locally created events.

        A CalendarEvent carries a single external_id, so it can live in exactly one external
        calendar; planning.views.toggle_source_write_back keeps at most one source switched on and
        this returns the oldest one if a leftover ever slips through. A source that wants to
        receive events but has lost its credentials is skipped here and shows up in the Agenda tab
        as "Terugsturen wacht op koppeling".
        """
        candidates = cls.objects.for_household(household).filter(
            is_enabled=True, is_read_only=False, sync_local_events=True, provider__in=list(cls.WRITE_BACK_PROVIDERS)
        ).select_related("connection").order_by("pk")
        for source in candidates:
            if source.accepts_local_events:
                return source
        return None


class CalendarEventQuerySet(HouseholdQuerySet):
    def pushable_to(self, source):
        """Every event sync_pending_events_to_remote may send to `source`.

        Besides the events that already live on that calendar this covers the locally created
        ones: planning.views.add_event files those under the household's own "Gezinsagenda"
        (a LOCAL source, or no source at all for older rows), so without them the write-back
        toggle would have nothing to send at all.
        """
        return self.filter(household_id=source.household_id).filter(
            models.Q(source=source) | models.Q(source__isnull=True) | models.Q(source__provider=CalendarSource.Provider.LOCAL)
        )


CalendarEventManager = models.Manager.from_queryset(CalendarEventQuerySet)


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

    objects = CalendarEventManager()

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
