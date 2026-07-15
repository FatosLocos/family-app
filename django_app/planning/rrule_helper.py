"""Helper for expanding recurring events using RRULE."""
from datetime import datetime, timedelta
from typing import Generator
import re


def expand_rrule_dates(rrule_string: str, start_date: datetime, num_occurrences: int = 52) -> Generator[datetime, None, None]:
    """
    Expand RRULE into individual occurrence dates.
    Supports basic RRULE patterns: DAILY, WEEKLY, MONTHLY, YEARLY
    """
    if not rrule_string or not rrule_string.startswith("RRULE:"):
        yield start_date
        return

    current = start_date
    rule_parts = {}

    # Parse RRULE string
    for part in rrule_string[6:].split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            rule_parts[key] = value

    freq = rule_parts.get("FREQ", "DAILY")
    interval = int(rule_parts.get("INTERVAL", 1))
    count = int(rule_parts.get("COUNT", num_occurrences))
    until_str = rule_parts.get("UNTIL")

    until_date = None
    if until_str:
        try:
            until_date = datetime.fromisoformat(until_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    occurrences = 0
    while occurrences < count:
        if until_date and current > until_date:
            break
        yield current

        # Advance to next occurrence
        if freq == "DAILY":
            current = current + timedelta(days=interval)
        elif freq == "WEEKLY":
            current = current + timedelta(weeks=interval)
        elif freq == "MONTHLY":
            # Simple month advancement; doesn't handle edge cases
            month = current.month + interval
            year = current.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            try:
                current = current.replace(year=year, month=month)
            except ValueError:
                # Handle day overflow (e.g., Jan 31 + 1 month)
                current = current.replace(year=year, month=month, day=1)
        elif freq == "YEARLY":
            current = current.replace(year=current.year + interval)
        else:
            break

        occurrences += 1


def has_rrule(event_data: dict) -> bool:
    """Check if event has a recurrence rule."""
    return bool(event_data.get("recurrence_rule") or event_data.get("rrule"))


def get_next_occurrences(event_data: dict, after_date: datetime = None, num: int = 10) -> list[datetime]:
    """Get next N occurrences of a recurring event."""
    if not has_rrule(event_data):
        return [event_data.get("start_date", after_date)]

    rrule_str = event_data.get("recurrence_rule") or event_data.get("rrule", "")
    start = event_data.get("start_date", after_date)

    if after_date and after_date > start:
        start = after_date

    return list(expand_rrule_dates(rrule_str, start, num))
