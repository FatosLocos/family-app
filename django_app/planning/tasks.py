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


def _still_addressed_to(event, addressed_to):
    """The event as the database has it now, or None when it moved on while this push was running.

    A push spends the length of an HTTP call outside the database. Saving the object we started
    with would write its external_id and sync_status back over a retarget that was stored in the
    meantime, which leaves the appointment pointing at the copy in the calendar it just left while
    the new calendar never receives anything.
    """
    fresh = CalendarEvent.objects.filter(pk=event.pk).first()
    if fresh is None or (fresh.target_source_id, fresh.external_id) != addressed_to:
        return None
    return fresh


def _remember_left_behind_copy(event, result):
    """Record the copy this push created in a calendar the event no longer points at.

    CalendarEvent.retarget could not list this id yet: the push was still on its way when the user
    picked another calendar. It is remembered for the same reason retarget does it — otherwise the
    next pull of that calendar imports the copy as a second appointment.
    """
    remote_id = (result or {}).get("external_id")
    fresh = CalendarEvent.objects.filter(pk=event.pk).first() if remote_id else None
    if fresh is None:
        return
    fresh.abandon_external_id(remote_id)
    fresh.save(update_fields=["abandoned_external_ids", "updated_at"])


def _push_pending_events(source):
    for event in CalendarEvent.objects.pushable_to(source).filter(sync_status=CalendarEvent.SyncStatus.PENDING).order_by("pk"):
        # The calendar and the remote item this push is about to write to, so its result can be
        # thrown away when the appointment was addressed to another calendar in the meantime.
        addressed_to = (event.target_source_id, event.external_id)
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
        except Exception as e:
            logger.error(f"Failed to sync event {event.id} to {source.provider}: {e}")
            failed = _still_addressed_to(event, addressed_to)
            if failed is not None:
                failed.sync_status = CalendarEvent.SyncStatus.ERROR
                failed.last_sync_error = str(e)[:500]
                failed.save(update_fields=["sync_status", "last_sync_error", "updated_at"])
            continue

        pushed = _still_addressed_to(event, addressed_to)
        if pushed is None:
            logger.info("Event %s was retargeted while it was being pushed to %s; its result is not stored.", event.pk, source.pk)
            _remember_left_behind_copy(event, result)
            continue

        if result and result["status"] == "synced":
            pushed.external_id = result.get("external_id") or pushed.external_id
            pushed.sync_status = CalendarEvent.SyncStatus.SYNCED
            pushed.last_sync_error = ""
            pushed.remote_updated_at = timezone.now()
        else:
            pushed.sync_status = CalendarEvent.SyncStatus.ERROR
            pushed.last_sync_error = result.get("error", "Unknown error") if result else "No result"

        pushed.save(
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
