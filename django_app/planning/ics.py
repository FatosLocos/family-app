from datetime import date, datetime, time

from django.utils import timezone
from icalendar import Calendar


def as_datetime(value, is_end=False):
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, time.max if is_end else time.min))
    return None


def parse_ics(data: bytes) -> list[dict]:
    calendar = Calendar.from_ical(data)
    events = []
    for component in calendar.walk("VEVENT"):
        raw_start = component.decoded("DTSTART", None)
        start = as_datetime(raw_start)
        end = as_datetime(component.decoded("DTEND", None), is_end=True) or start
        if not start:
            continue
        events.append({
            "external_id": str(component.get("UID", "")),
            "title": str(component.get("SUMMARY", "Afspraak")),
            "starts_at": start,
            "ends_at": end,
            "is_all_day": isinstance(raw_start, date) and not isinstance(raw_start, datetime),
            "location": str(component.get("LOCATION", "")),
            "notes": str(component.get("DESCRIPTION", "")),
        })
    return events
