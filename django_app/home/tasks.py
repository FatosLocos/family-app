import logging

from celery import shared_task
from django.utils import timezone

from common.db_scope import household_db_scope
from home.models import HomeAssistantConfig, HomeEntity, EVVehicle
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
    """Project Smartcar vehicle entities (synced by integrations.providers.sync_smartcar)
    into the EVVehicle dashboard model. Does not talk to Smartcar directly -
    integrations.tasks.sync_active_connections already keeps HomeEntity up to date."""
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            for entity in HomeEntity.objects.for_household(household).filter(source=HomeEntity.Source.SMARTCAR):
                attrs = entity.attributes or {}
                signals = attrs.get("smartcar_signals") or {}
                battery = signals.get("battery") or {}
                charge = signals.get("charge") or {}
                capacity = signals.get("battery:capacity") or {}

                percent_remaining = battery.get("percentRemaining")
                soc_percent = round(percent_remaining * 100) if isinstance(percent_remaining, (int, float)) else 0
                range_km = battery.get("range")
                capacity_kwh = capacity.get("capacity")

                EVVehicle.objects.update_or_create(
                    household=household,
                    external_id=attrs.get("smartcar_vehicle_id") or entity.entity_id,
                    defaults={
                        "name": entity.name,
                        "make": attrs.get("smartcar_make") or "",
                        "model": attrs.get("smartcar_model") or "",
                        "battery_capacity_kwh": capacity_kwh if isinstance(capacity_kwh, (int, float)) else None,
                        "current_soc_percent": soc_percent,
                        "current_range_km": round(range_km) if isinstance(range_km, (int, float)) else 0,
                        "integration_provider": "smartcar",
                        "is_charging": str(charge.get("state", "")).upper() == "CHARGING",
                        "last_sync_at": timezone.now(),
                    },
                )


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
