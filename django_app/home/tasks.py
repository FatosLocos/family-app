import logging

from celery import shared_task
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeAssistantConfig, EVVehicle
from home.services import HomeAssistantError, sync_entities
from households.models import Household

logger = logging.getLogger(__name__)


@shared_task
def sync_home_assistant_connections():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for config in HomeAssistantConfig.objects.filter(household=household):
                try:
                    sync_entities(household)
                except HomeAssistantError:
                    continue


@shared_task
def sync_ev_vehicle_data():
    """Sync EV vehicle data from Smartcar and other integrations."""
    from integrations.models import IntegrationConnection

    for household in Household.objects.all():
        with household_db_scope(household.pk):
            # Get Smartcar connections
            smartcar_connections = IntegrationConnection.objects.filter(
                household=household, provider="smartcar", is_enabled=True
            )

            for connection in smartcar_connections:
                try:
                    # Fetch vehicle data from Smartcar API
                    vehicles_data = connection.fetch_vehicles()
                    if not vehicles_data:
                        continue

                    for vehicle_data in vehicles_data:
                        vehicle, created = EVVehicle.objects.update_or_create(
                            household=household,
                            external_id=vehicle_data.get("id"),
                            defaults={
                                "name": vehicle_data.get("name", "Unknown"),
                                "make": vehicle_data.get("make", ""),
                                "model": vehicle_data.get("model", ""),
                                "battery_capacity_kwh": vehicle_data.get("battery_capacity_kwh"),
                                "current_soc_percent": vehicle_data.get("soc_percent", 0),
                                "current_range_km": vehicle_data.get("range_km", 0),
                                "is_charging": vehicle_data.get("is_charging", False),
                                "last_sync_at": timezone.now(),
                            },
                        )

                except Exception as e:
                    logger.error(f"Failed to sync EV data for connection {connection.id}: {e}")
                    continue


@shared_task
def sync_energy_readings_from_home_assistant():
    """Sync energy readings from Home Assistant if available."""
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            try:
                config = HomeAssistantConfig.objects.get(household=household)
            except HomeAssistantConfig.DoesNotExist:
                continue

            try:
                from home.ha_integration import get_ha_entities
                from home.energy_service import record_energy_reading

                entities = get_ha_entities(household.id)
                energy_entities = [e for e in entities if e.get("entity_id", "").startswith("sensor.") and "energy" in e.get("entity_id", "")]

                for entity in energy_entities:
                    try:
                        consumption_kwh = float(entity.get("state", 0))
                        record_energy_reading(
                            household.id,
                            consumption_kwh=consumption_kwh,
                            source="home_assistant",
                            timestamp=timezone.now(),
                        )
                    except (ValueError, TypeError):
                        continue

            except Exception as e:
                logger.error(f"Failed to sync energy readings from HA: {e}")
                continue
