from __future__ import annotations


FAMILY_APP_HA_DOMAIN = "family_app"
FAMILY_APP_HA_CONTRACT_VERSION = 1

FAMILY_APP_HA_ENTITIES = (
    {
        "platform": "sensor",
        "object_id": "family_open_tasks",
        "name": "Family open tasks",
        "state_source": "open_task_count",
        "unit": "tasks",
    },
    {
        "platform": "calendar",
        "object_id": "family",
        "name": "Family calendar",
        "state_source": "planning_events",
        "unit": "",
    },
    {
        "platform": "todo",
        "object_id": "family_shopping",
        "name": "Family shopping",
        "state_source": "shopping_items",
        "unit": "items",
    },
    {
        "platform": "binary_sensor",
        "object_id": "family_maintenance_due",
        "name": "Family maintenance due",
        "state_source": "overdue_maintenance",
        "unit": "",
    },
)

FAMILY_APP_HA_EVENTS = (
    {
        "event_type": "family_app.task_created",
        "required_fields": ("task_id", "title", "household_id"),
    },
    {
        "event_type": "family_app.task_completed",
        "required_fields": ("task_id", "title", "household_id", "completed_by"),
    },
    {
        "event_type": "family_app.maintenance_due",
        "required_fields": ("maintenance_id", "title", "household_id", "due_date"),
    },
)


def family_app_home_assistant_contract() -> dict:
    return {
        "domain": FAMILY_APP_HA_DOMAIN,
        "version": FAMILY_APP_HA_CONTRACT_VERSION,
        "entities": list(FAMILY_APP_HA_ENTITIES),
        "events": list(FAMILY_APP_HA_EVENTS),
    }
