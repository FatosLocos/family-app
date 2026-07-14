import logging

from celery import shared_task
from django.utils import timezone

from common.db_scope import household_db_scope
from households.models import Household
from integrations.audit import log_integration_event
from integrations.models import IntegrationAudit, IntegrationConnection, SyncRun
from integrations.providers import ProviderError, sync_connection

logger = logging.getLogger(__name__)


@shared_task
def sync_connection_task(connection_id: int, household_id: int):
    with household_db_scope(household_id):
        connection = IntegrationConnection.objects.get(pk=connection_id, household_id=household_id)
        run = SyncRun.objects.create(household=connection.household, connection=connection, status="running")
        try:
            result = sync_connection(connection)
            connection.status = "configured"
            connection.last_sync_at = timezone.now()
            connection.last_error = ""
            connection.save(update_fields=["status", "last_sync_at", "last_error", "updated_at"])
            run.status, run.detail = "succeeded", str(result)
            log_integration_event(connection=connection, action=IntegrationAudit.Action.SYNC_SUCCEEDED, detail="Synchronisatie voltooid.")
        except ProviderError as error:
            connection.status, connection.last_error = "sync_error", str(error)[:500]
            connection.save(update_fields=["status", "last_error", "updated_at"])
            run.status, run.detail = "failed", str(error)[:500]
            log_integration_event(connection=connection, action=IntegrationAudit.Action.SYNC_FAILED, detail=run.detail)
        except Exception:
            logger.exception("Onverwachte fout tijdens synchronisatie van %s", connection.provider)
            connection.status = "sync_error"
            connection.last_error = "Synchronisatie mislukt. Controleer de koppeling en probeer het opnieuw."
            connection.save(update_fields=["status", "last_error", "updated_at"])
            run.status, run.detail = "failed", connection.last_error
            log_integration_event(connection=connection, action=IntegrationAudit.Action.SYNC_FAILED, detail=run.detail)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "detail", "finished_at"])


@shared_task
def sync_active_connections():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for connection in IntegrationConnection.objects.for_household(household).filter(status__in=["configured", "needs_sync"]):
                sync_connection_task.delay(connection.id, household.id)
