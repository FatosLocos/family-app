import requests
from celery import shared_task
from django.utils import timezone

from common.db_scope import household_db_scope
from households.models import Household
from planning.ics import parse_ics
from planning.models import CalendarEvent, IcsSubscription


@shared_task
def sync_ics_subscriptions():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for subscription in IcsSubscription.objects.for_household(household).select_related("source"):
                try:
                    response = requests.get(subscription.url, timeout=30)
                    response.raise_for_status()
                    for event in parse_ics(response.content):
                        if event["external_id"]:
                            CalendarEvent.objects.update_or_create(household=household, source=subscription.source, external_id=event["external_id"], defaults=event)
                    subscription.source.last_sync_at = timezone.now()
                    subscription.source.save(update_fields=["last_sync_at", "updated_at"])
                    subscription.last_error = ""
                    subscription.save(update_fields=["last_error", "updated_at"])
                except Exception as error:
                    subscription.last_error = str(error)[:500]
                    subscription.save(update_fields=["last_error", "updated_at"])
