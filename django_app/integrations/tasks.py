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
def sync_connection_task(connection_id: int, household_id: int, sync_run_id: int | None = None):
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
                if sync_run_id:
                    SyncRun.objects.filter(
                        pk=sync_run_id,
                        household_id=household_id,
                        connection=connection,
                        status="queued",
                    ).update(
                        status="failed",
                        detail="Er liep al een synchronisatie. Probeer opnieuw zodra die is voltooid.",
                        finished_at=timezone.now(),
                    )
                return {"status": "already_running"}
            if sync_run_id:
                run = SyncRun.objects.select_for_update().filter(
                    pk=sync_run_id,
                    household_id=household_id,
                    connection=connection,
                ).first()
                if run and run.status in {"succeeded", "failed"}:
                    return {"status": "already_finished"}
            else:
                run = SyncRun.objects.select_for_update().filter(
                    household_id=household_id,
                    connection=connection,
                    status="queued",
                ).order_by("-started_at").first()
            if not run:
                run = SyncRun.objects.create(household=connection.household, connection=connection, status="queued")
            run.status = "running"
            run.detail = ""
            run.save(update_fields=["status", "detail"])
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
            for connection in IntegrationConnection.objects.for_household(household).filter(status__in=["configured", "needs_sync"]).exclude(provider=IntegrationConnection.Provider.HOME_CONNECT):
                sync_connection_task.delay(connection.id, household.id)


@shared_task
def sync_home_connect_connections():
    """Keep appliance progress and maintenance signals useful without speeding up all integrations."""
    debounce_window = timedelta(seconds=30)
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for connection in IntegrationConnection.objects.for_household(household).filter(
                provider=IntegrationConnection.Provider.HOME_CONNECT,
                status__in=["configured", "needs_sync"],
            ):
                if connection.last_sync_at and timezone.now() - connection.last_sync_at < debounce_window:
                    continue
                sync_connection_task.delay(connection.id, household.id)


@shared_task
def renew_sonos_event_subscriptions():
    """Re-register Sonos cloud event targets without repeatedly syncing other providers."""
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for connection in IntegrationConnection.objects.for_household(household).filter(
                provider=IntegrationConnection.Provider.SONOS,
                status__in=["configured", "needs_sync"],
            ):
                sync_connection_task.delay(connection.id, household.id)


@shared_task
def poll_google_home_event_subscriptions():
    """Poll configured Google Pub/Sub subscriptions; acknowledgements make retries safe."""
    from integrations.google_home_events import GoogleHomeEventError, poll_google_home_events

    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for connection in IntegrationConnection.objects.for_household(household).filter(
                provider=IntegrationConnection.Provider.GOOGLE_HOME,
                status="configured",
            ):
                try:
                    poll_google_home_events(connection)
                except GoogleHomeEventError as error:
                    settings = dict(connection.settings) if isinstance(connection.settings, dict) else {}
                    settings["google_events_status"] = "error"
                    settings["google_events_error"] = str(error)[:240]
                    connection.settings = settings
                    connection.save(update_fields=["settings", "updated_at"])
                    logger.warning("Google Home eventpoll mislukt voor connection %s: %s", connection.id, error)


@shared_task
def cleanup_stale_data():
    """Clean up old sync runs, audit logs, and expired data."""
    retention_days = 90
    cutoff_date = timezone.now() - timedelta(days=retention_days)

    deleted_sync_runs, _ = SyncRun.objects.filter(finished_at__lt=cutoff_date).delete()
    deleted_audits, _ = IntegrationAudit.objects.filter(created_at__lt=cutoff_date).delete()

    logger.info("Cleaned up %d sync runs and %d audit records", deleted_sync_runs, deleted_audits)
