from datetime import timedelta

from celery import shared_task
from django.urls import reverse
from django.utils import timezone

from common.db_scope import household_db_scope
from household.models import Task
from households.models import Household
from notifications.models import Notification
from planning.models import CalendarEvent


@shared_task
def refresh_household_notifications():
    now = timezone.now()
    tomorrow = now + timedelta(hours=24)
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            overdue_tasks = Task.objects.for_household(household).filter(completed_at__isnull=True, due_at__lt=now)
            for task in overdue_tasks:
                Notification.objects.get_or_create(
                    household=household,
                    dedupe_key=f"task-overdue:{task.id}",
                    defaults={"title": "Taak is achterstallig", "body": task.title, "kind": "warning", "action_url": f"{reverse('household:index')}?tab=taken&filter=open"},
                )
            upcoming_events = CalendarEvent.objects.for_household(household).filter(starts_at__gte=now, starts_at__lte=tomorrow)
            for event in upcoming_events:
                Notification.objects.get_or_create(
                    household=household,
                    dedupe_key=f"event-upcoming:{event.id}:{event.starts_at.date().isoformat()}",
                    defaults={"title": "Afspraak binnen 24 uur", "body": event.title, "kind": "info", "action_url": reverse("planning:index")},
                )
