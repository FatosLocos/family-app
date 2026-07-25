from django.conf import settings
from django.db import models
from django.utils import timezone

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

    def __str__(self):
        # The "Terugsturen naar" picker renders these straight from the queryset.
        return self.name

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
    def receiving(cls, household):
        """The calendars a CalendarEvent.target_source may point at right now.

        Every gate planning.tasks.sync_pending_events_to_remote applies is repeated here,
        credentials included, so the "Terugsturen naar" picker, OpenClaw and the push task can
        never disagree about which calendar really accepts an appointment. A source that wants to
        receive events but has lost its credentials is left out and shows up in the Agenda tab as
        "Terugsturen wacht op koppeling".
        """
        candidates = cls.objects.for_household(household).filter(
            is_enabled=True, is_read_only=False, sync_local_events=True, provider__in=list(cls.WRITE_BACK_PROVIDERS)
        ).select_related("connection").order_by("name", "pk")
        # A queryset rather than the list: forms.ModelChoiceField needs one, and accepts_local_events
        # is a Python property so the credential half of the filter cannot live in SQL.
        return cls.objects.for_household(household).filter(pk__in=[source.pk for source in candidates if source.accepts_local_events]).order_by("name", "pk")


class CalendarEventQuerySet(HouseholdQuerySet):
    def pushable_to(self, source):
        """Every event sync_pending_events_to_remote may send to `source`.

        Two routes lead to a calendar: an event that already lives on it, and a locally created
        one whose "Terugsturen naar" (target_source) points at it. The target always wins over the
        origin, so an event that was addressed to another calendar is pushed there and nowhere
        else — one event carries one external_id and may exist in one external calendar only.
        """
        return self.filter(household_id=source.household_id).filter(
            models.Q(target_source=source) | models.Q(source=source, target_source__isnull=True)
        )


CalendarEventManager = models.Manager.from_queryset(CalendarEventQuerySet)


class CalendarEvent(PlanningRecord):
    class SyncStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        CONFLICT = "conflict", "Conflict"
        ERROR = "error", "Error"

    source = models.ForeignKey(CalendarSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    # Where a locally created event is written back to; source stays the calendar it came from.
    # Empty means the appointment never leaves FamilyApp.
    target_source = models.ForeignKey(CalendarSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="targeted_events")
    external_id = models.CharField(max_length=300, blank=True)
    # The ids of the copies earlier targets kept: there is no delete-sync, so those copies stay in
    # their external calendar and integrations.providers.sync_outlook has to recognise them, or it
    # imports every one of them as a second appointment.
    abandoned_external_ids = models.JSONField(default=list, blank=True)
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

    def retarget(self, source) -> bool:
        """Send this event to another calendar from now on. Returns True when a copy is left behind.

        external_id belongs to the calendar the event was created in, so it is dropped together
        with the target: that is what makes the next push create the appointment in the new
        calendar instead of patching the one in the old. There is no delete-sync, so the copy in
        the old calendar keeps existing and every caller has to say so out loud. Its id moves to
        abandoned_external_ids, because otherwise the next pull of that calendar would file the
        copy as a second appointment inside FamilyApp on top of that.

        Callers using save(update_fields=...) must include "target_source", "external_id",
        "abandoned_external_ids", "remote_updated_at", "sync_status" and "last_sync_error".
        """
        if (source.pk if source else None) == self.target_source_id:
            return False
        self.target_source = source
        left_behind = bool(self.external_id)
        if left_behind:
            self.abandon_external_id(self.external_id)
        self.external_id = ""
        self.remote_updated_at = None
        self.mark_pending()
        return left_behind

    def abandon_external_id(self, external_id: str) -> None:
        """Remember a remote copy this event no longer maintains, so no pull imports it again."""
        remembered = list(self.abandoned_external_ids or [])
        if external_id and external_id not in remembered:
            remembered.append(external_id)
        self.abandoned_external_ids = remembered


class IcsSubscription(PlanningRecord):
    name = models.CharField(max_length=160)
    url = models.URLField()
    source = models.OneToOneField(CalendarSource, on_delete=models.CASCADE, related_name="ics_subscription")
    last_error = models.TextField(blank=True)


class EventVenue(PlanningRecord):
    """A reusable address the household holds events at ("standaardlocatie").

    home.Room is about rooms inside the house and carries no address, and family.Contact
    describes a person or organisation rather than a place, so an invitation gets its own
    light model instead of bending either of those.
    """

    name = models.CharField(max_length=160)
    address = models.CharField(max_length=240, blank=True)
    postal_code = models.CharField(max_length=24, blank=True)
    city = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [models.UniqueConstraint(fields=("household", "name"), name="unique_event_venue_name_per_household")]

    def __str__(self):
        return self.name

    @property
    def full_address(self) -> str:
        return " ".join(part for part in (self.address, self.postal_code, self.city) if part)


class EventInvite(PlanningRecord):
    """The public, shareable invitation that hangs off one calendar event.

    Mirrors family.WishList: is_shared plus an unguessable share_token is the whole public
    contract. The token is the authorisation (in Python), the Postgres policy only proves
    containment — two independent layers, exactly like the public wishlist.
    """

    event = models.OneToOneField(CalendarEvent, on_delete=models.CASCADE, related_name="invite")
    is_shared = models.BooleanField(default=False)
    share_token = models.CharField(max_length=48, null=True, blank=True, unique=True)
    intro = models.TextField(blank=True)
    # SET_NULL on both: removing a wishlist or a venue must never take the invitation with it.
    wishlist = models.ForeignKey("family.WishList", null=True, blank=True, on_delete=models.SET_NULL, related_name="event_invites")
    venue = models.ForeignKey(EventVenue, null=True, blank=True, on_delete=models.SET_NULL, related_name="invites")
    rsvp_deadline = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Uitnodiging voor {self.event_id}"

    @property
    def rsvp_closed(self) -> bool:
        return bool(self.rsvp_deadline and timezone.now() > self.rsvp_deadline)

    @property
    def attending_count(self) -> int:
        """Total number of people coming, guests plus the extras they brought along."""
        return self.guests.filter(rsvp=EventGuest.Rsvp.YES).aggregate(total=models.Sum("party_size"))["total"] or 0


class EventProgramItem(PlanningRecord):
    invite = models.ForeignKey(EventInvite, on_delete=models.CASCADE, related_name="program_items")
    # Free text rather than a TimeField: an organiser writes "14:00", "rond 15u" or
    # "na het eten", and none of those has to be a real clock time.
    starts_at = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=240)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.description


class EventQuestion(PlanningRecord):
    class Kind(models.TextChoices):
        TEXT = "text", "Tekst"
        YESNO = "yesno", "Ja of nee"
        NUMBER = "number", "Aantal"

    invite = models.ForeignKey(EventInvite, on_delete=models.CASCADE, related_name="questions")
    label = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TEXT)
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.label


class EventGuest(PlanningRecord):
    """One anonymous RSVP. Written by a visitor without an account, so household is set
    explicitly from the invitation and never from a request the visitor controls."""

    class Rsvp(models.TextChoices):
        YES = "yes", "Komt"
        NO = "no", "Komt niet"
        MAYBE = "maybe", "Misschien"

    invite = models.ForeignKey(EventInvite, on_delete=models.CASCADE, related_name="guests")
    name = models.CharField(max_length=160)
    rsvp = models.CharField(max_length=8, choices=Rsvp.choices, default=Rsvp.YES)
    party_size = models.PositiveSmallIntegerField(default=1)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self):
        return self.name


class EventAnswer(PlanningRecord):
    guest = models.ForeignKey(EventGuest, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(EventQuestion, on_delete=models.CASCADE, related_name="answers")
    value = models.TextField(blank=True)

    class Meta:
        ordering = ("question__sort_order", "id")
