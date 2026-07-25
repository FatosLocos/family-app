from datetime import datetime, time, timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import household_required, parent_required
from planning.forms import CalendarEventForm, IcsFileForm, IcsSubscriptionForm
from planning.ics import parse_ics
from planning.models import CalendarEvent, CalendarSource, IcsSubscription


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
    events = CalendarEvent.objects.for_household(request.household).filter(starts_at__lt=end, ends_at__gte=start).filter(Q(source__isnull=True) | Q(source__is_enabled=True)).select_related("source")
    if selected_sources:
        events = events.filter(source_id__in=selected_sources)
    sources = list(CalendarSource.objects.for_household(request.household).order_by("provider", "name"))
    for source in sources:
        source.last_sync_error = _latest_push_error(source)
    form = CalendarEventForm()
    form.fields["participants"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    event_list = list(events)
    previous_anchor, next_anchor = adjacent_anchors(anchor, view)
    return render(request, "planning/index.html", {
        "view": view, "anchor": anchor, "range_start": start_date, "range_end": end_date - timedelta(days=1), "events": event_list,
        "planner_days": planner_days(start_date, end_date, event_list), "previous_anchor": previous_anchor, "next_anchor": next_anchor,
        "sources": sources, "selected_sources": selected_sources, "event_form": form, "ics_form": IcsSubscriptionForm(), "ics_file_form": IcsFileForm(),
        "members": request.user.__class__.objects.filter(memberships__household=request.household).distinct(),
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
