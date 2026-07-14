from __future__ import annotations

from datetime import date


def birthday_in_year(birth_date: date, year: int) -> date:
    """Return the observable birthday date for a year, including leap years."""
    try:
        return birth_date.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def upcoming_birthdays(people, today: date) -> list[dict]:
    birthdays = []
    for person in people:
        upcoming = birthday_in_year(person.birth_date, today.year)
        if upcoming < today:
            upcoming = birthday_in_year(person.birth_date, today.year + 1)
        birthdays.append({
            "person": person,
            "next_date": upcoming,
            "turning_age": upcoming.year - person.birth_date.year,
            "is_today": upcoming == today,
        })
    return sorted(birthdays, key=lambda birthday: (birthday["next_date"], birthday["person"].name.casefold()))
