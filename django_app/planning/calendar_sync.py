import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def sync_event_to_google_calendar(event, access_token: str) -> dict | None:
    """Sync a calendar event to Google Calendar."""
    try:
        from googleapiclient.discovery import build

        credentials = _build_google_credentials(access_token)
        service = build("calendar", "v3", credentials=credentials)

        event_body = {
            "summary": event.title,
            "description": event.notes,
            "location": event.location,
            "start": _format_datetime(event.starts_at, event.is_all_day),
            "end": _format_datetime(event.ends_at, event.is_all_day),
        }

        if event.external_id:
            # Update existing event
            result = service.events().update(
                calendarId="primary",
                eventId=event.external_id,
                body=event_body,
            ).execute()
        else:
            # Create new event
            result = service.events().insert(
                calendarId="primary",
                body=event_body,
            ).execute()

        return {"external_id": result["id"], "status": "synced", "error": None}

    except Exception as e:
        logger.error(f"Failed to sync event to Google Calendar: {e}")
        return {"status": "error", "error": str(e), "external_id": event.external_id}


def sync_event_to_caldav(event, caldav_url: str, username: str, password: str) -> dict | None:
    """Sync a calendar event to CalDAV server."""
    try:
        from caldav import Calendar
        from caldav.davclient import DAVClient
        from icalendar import Calendar as ICalCalendar
        from icalendar import Event as ICalEvent

        client = DAVClient(url=caldav_url, username=username, password=password)
        calendar = Calendar(client=client, url=caldav_url)

        uid = event.external_id or f"event-{event.id}@familyapp"
        ical_event = ICalEvent()
        ical_event.add("summary", event.title)
        ical_event.add("description", event.notes)
        ical_event.add("location", event.location)
        ical_event.add("dtstart", event.starts_at)
        ical_event.add("dtend", event.ends_at)
        ical_event.add("uid", uid)

        ical_calendar = ICalCalendar()
        ical_calendar.add("prodid", "-//Family App//Agenda//NL")
        ical_calendar.add("version", "2.0")
        ical_calendar.add_component(ical_event)
        ical_text = ical_calendar.to_ical().decode("utf-8")

        if event.external_id:
            # Update existing
            existing = calendar.event_by_uid(event.external_id)
            existing.data = ical_text
            existing.save()
        else:
            # Create new
            calendar.save_event(ical=ical_text)

        return {"status": "synced", "error": None, "external_id": uid}

    except Exception as e:
        logger.error(f"Failed to sync event to CalDAV: {e}")
        return {"status": "error", "error": str(e), "external_id": event.external_id}


def _build_google_credentials(access_token: str):
    """Build Google credentials from an already-valid access token.

    No refresh_token/client secret is stored for calendar-write connections,
    so this must not attempt to refresh - the caller is responsible for
    supplying a current token."""
    from google.oauth2.credentials import Credentials

    return Credentials(token=access_token)


def _format_datetime(dt: datetime, is_all_day: bool) -> dict:
    """Format datetime for Google Calendar API."""
    if is_all_day:
        return {"date": dt.date().isoformat()}
    else:
        return {
            "dateTime": dt.isoformat(),
            "timeZone": "Europe/Amsterdam",
        }
