import logging

import requests
from celery import shared_task
from django.utils import timezone

from common.db_scope import household_db_scope
from households.models import Household
from planning.calendar_sync import sync_event_to_google_calendar, sync_event_to_caldav, sync_event_to_outlook
from planning.ics import parse_ics
from planning.models import CalendarEvent, CalendarSource, IcsSubscription

logger = logging.getLogger(__name__)


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


@shared_task
def sync_pending_events_to_remote():
    """Sync pending local events back to the calendar each of them was addressed to.

    CalendarSource.receiving keeps a calendar that cannot accept events (switched off, read-only
    or without credentials) out of the loop, so an appointment aimed at such a calendar simply
    stays pending instead of being pushed somewhere it does not belong. CalendarEvent.pushable_to
    hands every event to exactly one calendar, so nothing is ever sent twice.
    """
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for source in CalendarSource.receiving(household):
                logger.info("Pushing pending events of household %s to calendar source %s (%s).", household.pk, source.pk, source.provider)
                _push_pending_events(source)


def _push_pending_events(source):
    for event in CalendarEvent.objects.pushable_to(source).filter(sync_status=CalendarEvent.SyncStatus.PENDING).order_by("pk"):
        try:
            if source.provider == CalendarSource.Provider.GOOGLE_CALENDAR:
                result = sync_event_to_google_calendar(event, source.write_access_token)
            elif source.provider == CalendarSource.Provider.CALDAV:
                # Decrypt password from field encryption
                password = source.write_access_token
                result = sync_event_to_caldav(event, source.caldav_url, source.caldav_username, password)
            elif source.provider == CalendarSource.Provider.OUTLOOK:
                result = sync_event_to_outlook(event, source.connection, source.external_id)
            else:
                continue

            if result and result["status"] == "synced":
                event.external_id = result.get("external_id") or event.external_id
                event.sync_status = CalendarEvent.SyncStatus.SYNCED
                event.last_sync_error = ""
                event.remote_updated_at = timezone.now()
            else:
                event.sync_status = CalendarEvent.SyncStatus.ERROR
                event.last_sync_error = result.get("error", "Unknown error") if result else "No result"

            event.save(
                update_fields=[
                    "sync_status",
                    "last_sync_error",
                    "remote_updated_at",
                    "external_id",
                    # planning.views._latest_push_error sorts on updated_at to show the
                    # newest failure, and auto_now only fires for fields listed here.
                    "updated_at",
                ]
            )
        except Exception as e:
            logger.error(f"Failed to sync event {event.id} to {source.provider}: {e}")
            event.sync_status = CalendarEvent.SyncStatus.ERROR
            event.last_sync_error = str(e)[:500]
            event.save(update_fields=["sync_status", "last_sync_error", "updated_at"])
