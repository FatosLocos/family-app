from datetime import timedelta

from celery import shared_task
from django.urls import reverse
from django.utils import timezone

from common.db_scope import household_db_scope
from finance.models import RecurringRule
from finance.tasks import next_recurring_due_date
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
            due_soon_tasks = Task.objects.for_household(household).filter(
                completed_at__isnull=True,
                due_at__gte=now,
                due_at__lte=tomorrow,
            )
            for task in due_soon_tasks:
                Notification.objects.get_or_create(
                    household=household,
                    dedupe_key=f"task-due-soon:{task.id}:{task.due_at.date().isoformat()}",
                    defaults={
                        "title": "Taak binnenkort",
                        "body": task.title,
                        "kind": "info",
                        "action_url": f"{reverse('household:index')}?tab=taken&filter=open",
                    },
                )
            upcoming_events = CalendarEvent.objects.for_household(household).filter(starts_at__gte=now, starts_at__lte=tomorrow)
            for event in upcoming_events:
                Notification.objects.get_or_create(
                    household=household,
                    dedupe_key=f"event-upcoming:{event.id}:{event.starts_at.date().isoformat()}",
                    defaults={"title": "Afspraak binnen 24 uur", "body": event.title, "kind": "info", "action_url": reverse("planning:index")},
                )
            for rule in RecurringRule.objects.for_household(household).filter(is_excluded=False):
                due_on = next_recurring_due_date(rule, timezone.localdate())
                if not due_on or due_on > timezone.localdate() + timedelta(days=3):
                    continue
                is_expense = rule.direction == RecurringRule.Direction.EXPENSE
                Notification.objects.get_or_create(
                    household=household,
                    dedupe_key=f"recurring-due:{rule.id}:{due_on.isoformat()}",
                    defaults={
                        "title": "Afschrijving binnenkort" if is_expense else "Inkomst verwacht",
                        "body": f"{rule.merchant} · € {rule.expected_amount} · {due_on:%d %b}",
                        "kind": "warning" if is_expense else "info",
                        "action_url": f"{reverse('finance:index')}?tab=planning",
                    },
                )
