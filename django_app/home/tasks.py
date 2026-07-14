from celery import shared_task

from home.models import HomeAssistantConfig
from home.services import HomeAssistantError, sync_entities


@shared_task
def sync_home_assistant_connections():
    for config in HomeAssistantConfig.objects.select_related("household"):
        try:
            sync_entities(config.household)
        except HomeAssistantError:
            continue
