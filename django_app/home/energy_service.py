"""Energy and EV tracking service."""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Sum
from django.utils import timezone

from home.models import EnergyReading, EVChargingSession, EVVehicle

logger = logging.getLogger(__name__)


def record_energy_reading(
    household_id: int,
    consumption_kwh: Decimal,
    production_kwh: Decimal = Decimal("0"),
    source: str = "grid",
    cost_eur: Decimal | None = None,
    timestamp: datetime | None = None,
) -> EnergyReading | None:
    """Record an energy reading for the household."""
    try:
        from common.db_scope import household_db_scope

        with household_db_scope(household_id):
            reading = EnergyReading.objects.create(
                household_id=household_id,
                consumption_kwh=consumption_kwh,
                production_kwh=production_kwh,
                source=source,
                cost_eur=cost_eur,
                timestamp=timestamp or timezone.now(),
            )
            return reading
    except Exception as e:
        logger.error(f"Failed to record energy reading: {e}")
        return None


def get_energy_summary(household_id: int, days: int = 30) -> dict:
    """Get energy consumption summary for the household."""
    from common.db_scope import household_db_scope

    try:
        with household_db_scope(household_id):
            cutoff_date = timezone.now() - timedelta(days=days)
            readings = EnergyReading.objects.filter(household_id=household_id, timestamp__gte=cutoff_date)

            consumption = readings.aggregate(total=Sum("consumption_kwh"))["total"] or Decimal("0")
            production = readings.aggregate(total=Sum("production_kwh"))["total"] or Decimal("0")
            cost = readings.aggregate(total=Sum("cost_eur"))["total"] or Decimal("0")

            return {
                "period_days": days,
                "total_consumption_kwh": float(consumption),
                "total_production_kwh": float(production),
                "total_cost_eur": float(cost),
                "net_consumption_kwh": float(consumption - production),
                "avg_daily_kwh": float(consumption / days) if days > 0 else 0,
            }
    except Exception as e:
        logger.error(f"Failed to get energy summary: {e}")
        return {}


def get_hourly_trend(household_id: int, hours: int = 24) -> list[dict]:
    """Get hourly energy consumption trend."""
    from common.db_scope import household_db_scope

    try:
        with household_db_scope(household_id):
            cutoff_time = timezone.now() - timedelta(hours=hours)
            readings = EnergyReading.objects.filter(
                household_id=household_id, timestamp__gte=cutoff_time
            ).order_by("timestamp")

            # Group by hour
            hourly_data = {}
            for reading in readings:
                hour_key = reading.timestamp.strftime("%Y-%m-%d %H:00")
                if hour_key not in hourly_data:
                    hourly_data[hour_key] = {
                        "consumption_kwh": Decimal("0"),
                        "production_kwh": Decimal("0"),
                        "count": 0,
                    }
                hourly_data[hour_key]["consumption_kwh"] += reading.consumption_kwh
                hourly_data[hour_key]["production_kwh"] += reading.production_kwh
                hourly_data[hour_key]["count"] += 1

            return [
                {
                    "hour": hour,
                    "consumption_kwh": float(data["consumption_kwh"]),
                    "production_kwh": float(data["production_kwh"]),
                }
                for hour, data in sorted(hourly_data.items())
            ]
    except Exception as e:
        logger.error(f"Failed to get hourly trend: {e}")
        return []


def get_ev_dashboard(household_id: int) -> dict:
    """Get EV dashboard summary for all vehicles."""
    from common.db_scope import household_db_scope

    try:
        with household_db_scope(household_id):
            vehicles = EVVehicle.objects.filter(household_id=household_id)

            vehicle_summaries = []
            for vehicle in vehicles:
                sessions = vehicle.charging_sessions.filter(end_time__isnull=False).order_by("-start_time")[:30]
                total_energy = sessions.aggregate(total=Sum("energy_added_kwh"))["total"] or Decimal("0")
                total_cost = sessions.aggregate(total=Sum("cost_eur"))["total"] or Decimal("0")
                avg_duration = sessions.aggregate(avg=Avg("start_soc_percent"))["avg"] or 0

                vehicle_summaries.append(
                    {
                        "id": vehicle.id,
                        "name": vehicle.name,
                        "make": str(vehicle.make),
                        "model": str(vehicle.model),
                        "current_soc_percent": vehicle.current_soc_percent,
                        "current_range_km": vehicle.current_range_km,
                        "is_charging": vehicle.is_charging,
                        "battery_capacity_kwh": float(vehicle.battery_capacity_kwh or 0),
                        "last_30_days": {
                            "sessions": sessions.count(),
                            "energy_added_kwh": float(total_energy),
                            "total_cost_eur": float(total_cost),
                        },
                    }
                )

            return {
                "vehicles": vehicle_summaries,
                "total_vehicles": len(vehicle_summaries),
                "vehicles_charging": sum(1 for v in vehicle_summaries if v["is_charging"]),
            }
    except Exception as e:
        logger.error(f"Failed to get EV dashboard: {e}")
        return {"vehicles": [], "total_vehicles": 0, "vehicles_charging": 0}


def start_charging_session(vehicle_id: int, start_soc_percent: int, location: str = "") -> EVChargingSession | None:
    """Start tracking a charging session."""
    try:
        session = EVChargingSession.objects.create(
            vehicle_id=vehicle_id,
            start_time=timezone.now(),
            start_soc_percent=start_soc_percent,
            location=location,
        )
        vehicle = EVVehicle.objects.get(id=vehicle_id)
        vehicle.is_charging = True
        vehicle.save(update_fields=["is_charging"])
        return session
    except Exception as e:
        logger.error(f"Failed to start charging session: {e}")
        return None


def end_charging_session(session_id: int, end_soc_percent: int, cost_eur: Decimal | None = None) -> bool:
    """End and finalize a charging session."""
    try:
        session = EVChargingSession.objects.get(id=session_id)
        session.end_time = timezone.now()
        session.end_soc_percent = end_soc_percent
        session.energy_added_kwh = Decimal(
            (end_soc_percent - session.start_soc_percent) * session.vehicle.battery_capacity_kwh / 100
        )
        session.cost_eur = cost_eur
        session.save()

        vehicle = session.vehicle
        vehicle.is_charging = False
        vehicle.current_soc_percent = end_soc_percent
        vehicle.save(update_fields=["is_charging", "current_soc_percent"])

        return True
    except Exception as e:
        logger.error(f"Failed to end charging session: {e}")
        return False
