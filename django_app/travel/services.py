"""Glue between a trip and the rest of the app — first of all the normal Taken tab."""
from household.models import TaskList
from travel.models import Trip

TASK_LIST_NAME_MAX_LENGTH = 120
TASK_LIST_NAME_ATTEMPTS = 50


def trip_task_list_name(destination: str) -> str:
    return f"Reis: {destination}".strip()[:TASK_LIST_NAME_MAX_LENGTH]


def ensure_trip_task_list(trip: Trip) -> TaskList | None:
    """Give a trip its own list in the normal Taken tab, and link it.

    TaskList is unique per (household, name), so a second trip to the same destination
    would collide on "Reis: <bestemming>". Those get a numbered suffix; an existing list
    with that name is reused only when no other trip claims it. Returns None when even a
    numbered name is taken, so the caller can say so instead of failing the whole trip.
    """
    if trip.task_list_id:
        return trip.task_list
    base_name = trip_task_list_name(trip.destination)
    task_list = None
    for attempt in range(1, TASK_LIST_NAME_ATTEMPTS + 1):
        suffix = "" if attempt == 1 else f" ({attempt})"
        name = f"{base_name[:TASK_LIST_NAME_MAX_LENGTH - len(suffix)]}{suffix}"
        existing = TaskList.objects.for_household(trip.household).filter(name=name).first()
        if existing is None:
            task_list = TaskList.objects.create(household=trip.household, name=name)
            break
        if not Trip.objects.for_household(trip.household).filter(task_list=existing).exists():
            task_list = existing
            break
    if task_list is None:
        return None
    trip.task_list = task_list
    trip.save(update_fields=["task_list", "updated_at"])
    return task_list


def trip_payload(trip: Trip) -> dict:
    """Serialise one trip with everything hanging off it, for the OpenClaw read endpoint."""
    task_list = trip.task_list
    tasks = list(task_list.tasks.all()) if task_list else []
    return {
        "id": trip.id,
        "destination": trip.destination,
        "start_date": trip.start_date.isoformat() if trip.start_date else None,
        "end_date": trip.end_date.isoformat() if trip.end_date else None,
        "notes": trip.notes,
        "stops": [
            {
                "id": stop.id,
                "name": stop.name,
                "arrives_on": stop.arrives_on.isoformat() if stop.arrives_on else None,
                "departs_on": stop.departs_on.isoformat() if stop.departs_on else None,
            }
            for stop in trip.stops.all()
        ],
        "documents": [
            {
                "id": document.id,
                "title": document.title,
                "kind": "bestand" if document.file else ("dropbox" if document.dropbox_path else "link"),
                "dropbox_path": document.dropbox_path or None,
                "url": document.url or None,
            }
            for document in trip.documents.all()
        ],
        "ideas": [
            {
                "id": idea.id,
                "text": idea.text,
                "author": str(idea.author) if idea.author else None,
                "created_by_agent": idea.created_by_agent,
                "created_at": idea.created_at.isoformat(),
            }
            for idea in trip.ideas.all()
        ],
        "task_list": {
            "id": task_list.id,
            "name": task_list.name,
            "open_tasks": sum(1 for task in tasks if task.completed_at is None),
            "tasks": [
                {"id": task.id, "title": task.title, "completed_at": task.completed_at.isoformat() if task.completed_at else None}
                for task in tasks
            ],
        } if task_list else None,
    }


def trips_for_reading(household):
    """Every trip of this household with its children prefetched, oldest departure first."""
    return (
        Trip.objects.for_household(household)
        .select_related("task_list")
        .prefetch_related("stops", "documents", "ideas__author", "task_list__tasks")
    )
