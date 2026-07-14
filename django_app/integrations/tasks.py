import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
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
        with transaction.atomic():
            connection = IntegrationConnection.objects.select_for_update().get(pk=connection_id, household_id=household_id)
            stale_before = timezone.now() - timedelta(minutes=30)
            SyncRun.objects.filter(connection=connection, status="running", started_at__lt=stale_before).update(
                status="failed",
                detail="Synchronisatie duurde te lang en is opnieuw ingepland.",
                finished_at=timezone.now(),
            )
            if SyncRun.objects.filter(connection=connection, status="running").exists():
                return {"status": "already_running"}
            run = SyncRun.objects.create(household=connection.household, connection=connection, status="running")
        try:
            result = sync_connection(connection)
            connection.status = "configured"
            connection.last_sync_at = timezone.now()
            connection.last_error = ""
            connection.save(update_fields=["status", "last_sync_at", "last_error", "updated_at"])
            run.status, run.detail = "succeeded", str(result)
            log_integration_event(connection=connection, action=IntegrationAudit.Action.SYNC_SUCCEEDED, detail="Synchronisatie voltooid.")
            outcome = {"status": "succeeded", **result}
        except ProviderError as error:
            connection.status, connection.last_error = "sync_error", str(error)[:500]
            connection.save(update_fields=["status", "last_error", "updated_at"])
            run.status, run.detail = "failed", str(error)[:500]
            log_integration_event(connection=connection, action=IntegrationAudit.Action.SYNC_FAILED, detail=run.detail)
            outcome = {"status": "failed"}
        except Exception:
            logger.exception("Onverwachte fout tijdens synchronisatie van %s", connection.provider)
            connection.status = "sync_error"
            connection.last_error = "Synchronisatie mislukt. Controleer de koppeling en probeer het opnieuw."
            connection.save(update_fields=["status", "last_error", "updated_at"])
            run.status, run.detail = "failed", connection.last_error
            log_integration_event(connection=connection, action=IntegrationAudit.Action.SYNC_FAILED, detail=run.detail)
            outcome = {"status": "failed"}
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "detail", "finished_at"])
        return outcome


@shared_task
def sync_active_connections():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for connection in IntegrationConnection.objects.for_household(household).filter(status__in=["configured", "needs_sync"]):
                sync_connection_task.delay(connection.id, household.id)
