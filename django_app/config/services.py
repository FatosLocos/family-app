from datetime import datetime, time

from django.utils import timezone

from family.birthdays import upcoming_birthdays
from family.models import ContactPerson
from household.models import MealPlan, Routine, ShoppingItem, Task
from notifications.models import Notification
from planning.models import CalendarEvent
from planning.views import calendar_range


def build_today_summary(household):
    """Aggregate the "vandaag" dashboard data — shared by the HTML view and the OpenClaw API.

    events_today uses the same start/end-of-day overlap window as the Agenda
    tab's "Dag"-view (planning.views.calendar_range), so a household always
    gets one consistent answer to "what's on today" everywhere it's asked.
    """
    now = timezone.now()
    today = timezone.localdate()
    start_date, end_date = calendar_range(today, "day")
    day_start = timezone.make_aware(datetime.combine(start_date, time.min))
    day_end = timezone.make_aware(datetime.combine(end_date, time.min))

    open_tasks = Task.objects.for_household(household).filter(completed_at__isnull=True).order_by("due_at", "-priority")
    open_shopping = ShoppingItem.objects.for_household(household).filter(completed_at__isnull=True).select_related("list")
    events_today = list(
        CalendarEvent.objects.for_household(household).filter(starts_at__lt=day_end, ends_at__gte=day_start).order_by("starts_at")
    )
    upcoming_events = CalendarEvent.objects.for_household(household).filter(ends_at__gte=now).order_by("starts_at")[:5]
    notifications = Notification.objects.for_household(household).filter(read_at__isnull=True).order_by("-created_at")[:4]
    routines = Routine.objects.for_household(household).filter(is_active=True, next_due_on__lte=today).select_related("assigned_to").order_by("next_due_on", "title")[:5]
    meals = MealPlan.objects.for_household(household).filter(planned_for__gte=today).order_by("planned_for")[:2]
    birthdays = upcoming_birthdays(
        ContactPerson.objects.for_household(household).filter(birth_date__isnull=False).select_related("contact"),
        today,
    )[:3]

    tasks_due_today = Task.objects.for_household(household).filter(due_at__date=today)
    tasks_due_today_total = tasks_due_today.count()
    tasks_due_today_done = tasks_due_today.filter(completed_at__isnull=False).count()

    return {
        "today": today,
        "tasks": list(open_tasks[:5]),
        "shopping_items": list(open_shopping[:5]),
        "events": list(upcoming_events),
        "events_today": events_today,
        "notifications": list(notifications),
        "routines": list(routines),
        "meals": list(meals),
        "birthdays": birthdays,
        "tasks_due_today_total": tasks_due_today_total,
        "tasks_due_today_done": tasks_due_today_done,
        "tasks_due_today_pct": round(tasks_due_today_done / tasks_due_today_total * 100) if tasks_due_today_total else 0,
        "shopping_open_count": open_shopping.count(),
        "events_today_count": len(events_today),
    }
