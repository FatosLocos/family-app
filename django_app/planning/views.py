import secrets
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from family.models import WishItem, WishList
from households.decorators import household_required, parent_required
from planning.forms import CalendarEventForm, EventInviteForm, EventProgramItemForm, EventQuestionForm, EventVenueForm, IcsFileForm, IcsSubscriptionForm
from planning.ics import parse_ics
from planning.models import CalendarEvent, CalendarSource, EventGuest, EventInvite, EventProgramItem, EventQuestion, EventVenue


def calendar_range(anchor, view):
    if view == "day":
        return anchor, anchor + timedelta(days=1)
    if view == "month":
        first_day = anchor.replace(day=1)
        start = first_day - timedelta(days=first_day.weekday())
        next_month = (first_day + timedelta(days=32)).replace(day=1)
        end = next_month + timedelta(days=(6 - next_month.weekday()) % 7 + 1)
        return start, end
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=7)


def planner_days(start_date, end_date, events):
    """Expand events across visible days for consistent day, week and month views."""
    event_map = {start_date + timedelta(days=offset): [] for offset in range((end_date - start_date).days)}
    for event in events:
        event_start = timezone.localtime(event.starts_at).date()
        event_end = timezone.localtime(event.ends_at).date()
        if not event.is_all_day and event.ends_at.time() == time.min and event_end > event_start:
            event_end -= timedelta(days=1)
        current = max(event_start, start_date)
        visible_end = min(event_end, end_date - timedelta(days=1))
        while current <= visible_end:
            event_map[current].append(event)
            current += timedelta(days=1)
    return [{"date": date, "events": event_map[date], "is_today": date == timezone.localdate()} for date in event_map]


def adjacent_anchors(anchor, view):
    if view == "month":
        current_month = anchor.replace(day=1)
        return current_month - timedelta(days=1), (current_month + timedelta(days=32)).replace(day=1)
    span = 1 if view == "day" else 7
    return anchor - timedelta(days=span), anchor + timedelta(days=span)


def _latest_push_error(source):
    """CalendarSource has no error field of its own — a failed write-back is recorded on the
    event that failed, so surface the most recent one instead of leaving a broken toggle silent.
    The event set is the same one the push task walks (locally created events included), because
    those are exactly the ones that can fail on their way to this calendar.
    """
    if not source.accepts_local_events:
        return ""
    return CalendarEvent.objects.pushable_to(source).filter(sync_status=CalendarEvent.SyncStatus.ERROR).exclude(last_sync_error="").order_by("-updated_at").values_list("last_sync_error", flat=True).first() or ""


def _public_invite_url(request, invite):
    """The absolute public URL of a shared invitation, or "" while it has no token yet."""
    if not invite.share_token:
        return ""
    return request.build_absolute_uri(reverse("planning:public_event_invite", args=[invite.share_token]))


def _invite_of(event):
    """The event's invitation, or None. Reverse OneToOne access raises when there is none."""
    try:
        return event.invite
    except EventInvite.DoesNotExist:
        return None


@household_required
def index(request):
    view = request.GET.get("view", "week")
    try:
        anchor = datetime.fromisoformat(request.GET.get("date", "")).date()
    except ValueError:
        anchor = timezone.localdate()
    start_date, end_date = calendar_range(anchor, view)
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date, time.min))
    selected_sources = request.GET.getlist("source")
    events = CalendarEvent.objects.for_household(request.household).filter(starts_at__lt=end, ends_at__gte=start).filter(Q(source__isnull=True) | Q(source__is_enabled=True)).select_related("source", "invite__venue", "invite__wishlist").prefetch_related("invite__program_items", "invite__questions", "invite__guests__answers__question")
    if selected_sources:
        events = events.filter(source_id__in=selected_sources)
    sources = list(CalendarSource.objects.for_household(request.household).order_by("provider", "name"))
    for source in sources:
        source.last_sync_error = _latest_push_error(source)
    form = CalendarEventForm()
    form.fields["participants"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    event_list = list(events)
    venues = list(EventVenue.objects.for_household(request.household))
    wishlists = list(WishList.objects.for_household(request.household))
    for event in event_list:
        # A reverse OneToOne raises DoesNotExist when it is missing, so hand the template a
        # plain attribute instead of making it rely on silent template failures.
        event.event_invite = _invite_of(event)
        if event.event_invite and event.event_invite.is_shared and event.event_invite.share_token:
            event.event_invite.public_url = _public_invite_url(request, event.event_invite)
    # Every live public link, whatever the calendar is showing: an invitation for a party in
    # August must stay revocable when the agenda is open on September.
    shared_invites = list(EventInvite.objects.for_household(request.household).filter(is_shared=True).select_related("event").order_by("event__starts_at"))
    for invite in shared_invites:
        invite.public_url = _public_invite_url(request, invite)
    previous_anchor, next_anchor = adjacent_anchors(anchor, view)
    return render(request, "planning/index.html", {
        "view": view, "anchor": anchor, "range_start": start_date, "range_end": end_date - timedelta(days=1), "events": event_list,
        "planner_days": planner_days(start_date, end_date, event_list), "previous_anchor": previous_anchor, "next_anchor": next_anchor,
        "sources": sources, "selected_sources": selected_sources, "event_form": form, "ics_form": IcsSubscriptionForm(), "ics_file_form": IcsFileForm(),
        "members": request.user.__class__.objects.filter(memberships__household=request.household).distinct(),
        "venues": venues, "wishlists": wishlists, "venue_form": EventVenueForm(), "question_kinds": EventQuestion.Kind.choices,
        "shared_invites": shared_invites,
    })


@household_required
@require_POST
def add_event(request):
    form = CalendarEventForm(request.POST)
    form.fields["participants"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        event = form.save(commit=False)
        event.household = request.household
        event.source, _ = CalendarSource.objects.get_or_create(household=request.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda", defaults={"is_read_only": False})
        event.mark_pending()
        event.save()
        form.save_m2m()
        messages.success(request, "Afspraak toegevoegd.")
    return redirect("planning:index")


def _local_event_or_404(request, event_id):
    event = get_object_or_404(CalendarEvent.objects.for_household(request.household).select_related("source"), pk=event_id)
    if event.source_id and event.source.provider != CalendarSource.Provider.LOCAL:
        raise Http404("Externe agenda-afspraken zijn alleen-lezen.")
    return event


@household_required
@require_POST
def update_event(request, event_id):
    event = _local_event_or_404(request, event_id)
    form = CalendarEventForm(request.POST, instance=event)
    form.fields["participants"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        event = form.save(commit=False)
        event.mark_pending()
        event.save()
        form.save_m2m()
        messages.success(request, "Afspraak aangepast.")
    else:
        messages.error(request, "Controleer de afspraakvelden.")
    return redirect("planning:index")


@household_required
@require_POST
def delete_event(request, event_id):
    event = _local_event_or_404(request, event_id)
    # There is no delete-sync: an event that was already pushed keeps existing in the external
    # calendar and the next pull would import it again, so say so instead of pretending it is gone.
    pushed_to = CalendarSource.write_back_target(request.household) if event.external_id else None
    event.delete()
    messages.success(request, "Afspraak verwijderd.")
    if pushed_to:
        messages.success(request, f"Let op: deze afspraak staat ook in {pushed_to.name}. Verwijder hem daar zelf, anders komt hij bij de volgende synchronisatie terug.")
    return redirect("planning:index")


@parent_required
@require_POST
def add_ics_subscription(request):
    form = IcsSubscriptionForm(request.POST)
    if form.is_valid():
        subscription = form.save(commit=False)
        subscription.household = request.household
        source = CalendarSource.objects.create(household=request.household, provider=CalendarSource.Provider.ICS, name=subscription.name, is_read_only=True)
        subscription.source = source
        subscription.save()
        messages.success(request, "ICS-abonnement toegevoegd. De eerste synchronisatie volgt automatisch.")
    return redirect("planning:index")


@parent_required
@require_POST
def import_ics_file(request):
    form = IcsFileForm(request.POST, request.FILES)
    if form.is_valid():
        file = form.cleaned_data["calendar_file"]
        if not file.name.lower().endswith(".ics") and file.content_type not in {"text/calendar", "application/ics"}:
            messages.error(request, "Kies een geldig ICS-bestand.")
            return redirect("planning:index")
        try:
            source = CalendarSource.objects.create(household=request.household, provider=CalendarSource.Provider.ICS, name=form.cleaned_data["name"], is_read_only=True)
            for event in parse_ics(file.read()):
                if event["external_id"]:
                    CalendarEvent.objects.create(household=request.household, source=source, **event)
            messages.success(request, "ICS-bestand geïmporteerd.")
        except Exception as error:
            messages.error(request, f"ICS-import mislukt: {error}")
    return redirect("planning:index")


@parent_required
@require_POST
def remove_source(request, source_id):
    source = CalendarSource.objects.for_household(request.household).get(pk=source_id)
    if source.provider == CalendarSource.Provider.LOCAL:
        messages.error(request, "De gezinsagenda kan niet worden verwijderd.")
    else:
        source.delete()
        messages.success(request, "Agendakoppeling verwijderd.")
    return redirect("planning:index")


@parent_required
@require_POST
def toggle_source(request, source_id):
    source = CalendarSource.objects.for_household(request.household).get(pk=source_id)
    if source.provider == CalendarSource.Provider.LOCAL:
        messages.error(request, "De gezinsagenda blijft altijd actief.")
    else:
        source.is_enabled = not source.is_enabled
        source.save(update_fields=["is_enabled", "updated_at"])
        messages.success(request, f"{source.name} is {'ingeschakeld' if source.is_enabled else 'uitgeschakeld'}.")
    return redirect("planning:index")


@parent_required
@require_POST
def toggle_source_write_back(request, source_id):
    """Turn "lokale afspraken hierheen terugsturen" on or off for one linked calendar."""
    source = get_object_or_404(CalendarSource.objects.for_household(request.household), pk=source_id)
    if not source.supports_write_back:
        messages.error(request, f"{source.name} kan geen afspraken ontvangen.")
        return redirect("planning:index")
    if source.provider == CalendarSource.Provider.OUTLOOK and source.connection_id is None and not source.sync_local_events:
        messages.error(request, f"{source.name} heeft geen gekoppeld Outlook-account meer. Synchroniseer Outlook opnieuw in Instellingen.")
        return redirect("planning:index")
    source.sync_local_events = not source.sync_local_events
    # is_read_only is the other half of the same decision; keeping them opposed stops the push
    # task from ever seeing a source that is both "stuur hierheen" and "alleen-lezen".
    source.is_read_only = not source.sync_local_events
    source.save(update_fields=["sync_local_events", "is_read_only", "updated_at"])
    if not source.sync_local_events:
        messages.success(request, f"Lokale afspraken worden niet meer naar {source.name} teruggestuurd.")
        return redirect("planning:index")
    messages.success(request, f"Lokale afspraken worden voortaan naar {source.name} teruggestuurd.")
    # An event carries one external_id, so it can live in exactly one external calendar: turning
    # write-back on here has to turn it off everywhere else, or every appointment would be
    # duplicated across calendars.
    superseded = CalendarSource.objects.for_household(request.household).filter(sync_local_events=True, provider__in=list(CalendarSource.WRITE_BACK_PROVIDERS)).exclude(pk=source.pk)
    names = list(superseded.values_list("name", flat=True))
    if names:
        superseded.update(sync_local_events=False, is_read_only=True, updated_at=timezone.now())
        messages.success(request, f"Terugsturen naar {', '.join(names)} is uitgezet: er kan er maar één tegelijk aanstaan.")
    return redirect("planning:index")


# --- Event invitations ------------------------------------------------------------------
# The public half of this module follows family.views.public_wishlist exactly: an unguessable
# token authorises in Python, the Postgres household_isolation policy proves containment, and
# every child object is scoped through its parent instead of through a household the anonymous
# visitor could influence.


def _event_invite_or_404(request, event_id):
    """Get (or lazily create) the invitation for one of this household's local events.

    Goes through _local_event_or_404 like every other mutating event endpoint: an appointment
    that was synced in from Outlook, Google or an ICS feed is read-only here, and publishing
    its title, time and location on an unauthenticated URL is exactly the kind of write the
    rest of this module already refuses.
    """
    event = _local_event_or_404(request, event_id)
    invite, _ = EventInvite.objects.get_or_create(event=event, defaults={"household": request.household})
    return invite


# Everything below is @parent_required, not @household_required: the content of an invitation
# ends up on an unauthenticated URL the moment the link is on, so putting a family appointment
# out there is a parent's call — like every other publish/link action in this module
# (add_ics_subscription, toggle_source, remove_source) and like family.views.
# toggle_wishlist_share, which only lets the owner or a parent share.
@parent_required
@require_POST
def update_event_invite(request, event_id):
    """Create or update the invitation details of an event. Never touches the public link."""
    invite = _event_invite_or_404(request, event_id)
    form = EventInviteForm(request.POST, instance=invite, household=request.household)
    if form.is_valid():
        form.save()
        messages.success(request, "Uitnodiging opgeslagen.")
    else:
        messages.error(request, "Controleer de velden van de uitnodiging.")
    return redirect("planning:index")


@parent_required
@require_POST
def toggle_event_share(request, event_id):
    invite = _event_invite_or_404(request, event_id)
    invite.is_shared = not invite.is_shared
    # Generated once and never rotated, like family.views.toggle_wishlist_share: someone who
    # already has the link keeps it working when the organiser switches sharing back on.
    if invite.is_shared and not invite.share_token:
        invite.share_token = secrets.token_urlsafe(24)
    invite.save(update_fields=["is_shared", "share_token", "updated_at"])
    messages.success(request, "Publieke uitnodigingslink geactiveerd." if invite.is_shared else "Publieke uitnodigingslink uitgeschakeld.")
    return redirect("planning:index")


@parent_required
@require_POST
def add_event_program_item(request, event_id):
    invite = _event_invite_or_404(request, event_id)
    form = EventProgramItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.household = request.household
        item.invite = invite
        item.save()
        messages.success(request, "Programma-onderdeel toegevoegd.")
    else:
        messages.error(request, "Vul een omschrijving in voor het programma-onderdeel.")
    return redirect("planning:index")


@parent_required
@require_POST
def delete_event_program_item(request, item_id):
    item = get_object_or_404(EventProgramItem.objects.for_household(request.household), pk=item_id)
    item.delete()
    messages.success(request, "Programma-onderdeel verwijderd.")
    return redirect("planning:index")


@parent_required
@require_POST
def add_event_question(request, event_id):
    invite = _event_invite_or_404(request, event_id)
    form = EventQuestionForm(request.POST)
    if form.is_valid():
        question = form.save(commit=False)
        question.household = request.household
        question.invite = invite
        question.save()
        messages.success(request, "Vraag toegevoegd.")
    else:
        messages.error(request, "Controleer de vraag.")
    return redirect("planning:index")


@parent_required
@require_POST
def delete_event_question(request, question_id):
    question = get_object_or_404(EventQuestion.objects.for_household(request.household), pk=question_id)
    question.delete()
    messages.success(request, "Vraag verwijderd.")
    return redirect("planning:index")


@parent_required
@require_POST
def add_event_venue(request):
    form = EventVenueForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data["name"]
        if EventVenue.objects.for_household(request.household).filter(name=name).exists():
            messages.error(request, f"Er bestaat al een locatie met de naam '{name}'.")
            return redirect("planning:index")
        venue = form.save(commit=False)
        venue.household = request.household
        venue.save()
        messages.success(request, "Locatie toegevoegd.")
    else:
        messages.error(request, "Controleer de locatiegegevens.")
    return redirect("planning:index")


@parent_required
@require_POST
def update_event_venue(request, venue_id):
    """Correct a standard venue. Without this a typo in the name is permanent: the unique
    constraint on (household, name) blocks recreating it under the right name."""
    venue = get_object_or_404(EventVenue.objects.for_household(request.household), pk=venue_id)
    form = EventVenueForm(request.POST, instance=venue)
    if form.is_valid():
        name = form.cleaned_data["name"]
        if EventVenue.objects.for_household(request.household).filter(name=name).exclude(pk=venue.pk).exists():
            messages.error(request, f"Er bestaat al een locatie met de naam '{name}'.")
            return redirect("planning:index")
        form.save()
        messages.success(request, "Locatie aangepast.")
    else:
        messages.error(request, "Controleer de locatiegegevens.")
    return redirect("planning:index")


@parent_required
@require_POST
def delete_event_venue(request, venue_id):
    """Remove a standard venue. EventInvite.venue is SET_NULL, so an invitation that used it
    keeps existing and simply falls back to the event's own location."""
    venue = get_object_or_404(EventVenue.objects.for_household(request.household), pk=venue_id)
    venue.delete()
    messages.success(request, "Locatie verwijderd.")
    return redirect("planning:index")


def _shared_invite_or_404(token):
    """The one lookup every public view uses: shared only, and never .for_household()."""
    return get_object_or_404(EventInvite.objects.filter(is_shared=True).select_related("event", "venue"), share_token=token)


def _public_wishlist_of(invite):
    """The linked wishlist, but only when that wishlist is itself shared.

    An invitation may not widen family.WishList's own public exception: the RLS policy on
    family_wishlist keeps requiring is_shared, so a wishlist that the owner did not share
    stays invisible here instead of leaking through the invitation.
    """
    if not invite.wishlist_id:
        return None
    return WishList.objects.filter(pk=invite.wishlist_id, is_shared=True).first()


def public_event_invite(request, token):
    invite = _shared_invite_or_404(token)
    wishlist = _public_wishlist_of(invite)
    return render(request, "planning/public_event_invite.html", {
        "invite": invite,
        "event": invite.event,
        "program_items": EventProgramItem.objects.filter(invite=invite),
        "questions": EventQuestion.objects.filter(invite=invite),
        "wishlist": wishlist,
        "wish_items": WishItem.objects.filter(wishlist=wishlist) if wishlist else [],
        "attending_count": invite.attending_count,
        "rsvp_closed": invite.rsvp_closed,
    })


def _clean_answer(question, raw):
    """Validate one answer against its question. Returns the stored value or raises ValueError."""
    value = raw.strip()
    if not value:
        if question.is_required:
            raise ValueError(f"'{question.label}' is verplicht.")
        return ""
    if question.kind == EventQuestion.Kind.YESNO:
        if value not in {"ja", "nee"}:
            raise ValueError(f"Beantwoord '{question.label}' met ja of nee.")
        return value
    if question.kind == EventQuestion.Kind.NUMBER:
        if not value.isdigit():
            raise ValueError(f"'{question.label}' verwacht een aantal.")
        return str(int(value))
    return value[:2000]


@require_POST
def rsvp_event(request, token):
    invite = _shared_invite_or_404(token)
    if invite.rsvp_closed:
        messages.error(request, "De aanmeldtermijn voor deze uitnodiging is verstreken.")
        return redirect("planning:public_event_invite", token=token)

    name = request.POST.get("name", "").strip()[:160]
    rsvp = request.POST.get("rsvp", "").strip()
    if not name:
        messages.error(request, "Vul je naam in om je aan te melden.")
        return redirect("planning:public_event_invite", token=token)
    if rsvp not in EventGuest.Rsvp.values:
        messages.error(request, "Geef aan of je komt, niet komt of misschien komt.")
        return redirect("planning:public_event_invite", token=token)
    try:
        party_size = int(request.POST.get("party_size") or 1)
    except (TypeError, ValueError):
        party_size = 0
    if not 1 <= party_size <= 50:
        messages.error(request, "Vul een aantal personen tussen 1 en 50 in.")
        return redirect("planning:public_event_invite", token=token)

    # Scoped through the invitation, never through a household the visitor can influence.
    questions = list(EventQuestion.objects.filter(invite=invite))
    answers = []
    for question in questions:
        try:
            answers.append((question, _clean_answer(question, request.POST.get(f"vraag-{question.id}", ""))))
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("planning:public_event_invite", token=token)

    with transaction.atomic():
        guest = EventGuest.objects.create(household=invite.household, invite=invite, name=name, rsvp=rsvp, party_size=party_size, note=request.POST.get("note", "").strip()[:2000])
        for question, value in answers:
            if value:
                guest.answers.create(household=invite.household, question=question, value=value)
    messages.success(request, "Bedankt, je aanmelding is doorgegeven.")
    return redirect("planning:public_event_invite", token=token)
