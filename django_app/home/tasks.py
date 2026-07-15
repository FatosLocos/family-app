from celery import shared_task

from common.db_scope import household_db_scope
from home.models import HomeAssistantConfig
from home.services import HomeAssistantError, sync_entities
from households.models import Household


@shared_task
def sync_home_assistant_connections():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for config in HomeAssistantConfig.objects.filter(household=household):
                try:
                    sync_entities(household)
                except HomeAssistantError:
                    continue
