import logging
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def fetch_weather_from_openweathermap(lat: Decimal, lon: Decimal, units: str = "metric") -> dict | None:
    """Fetch current weather from OpenWeatherMap API."""
    if not settings.WEATHER_API_KEY:
        return None

    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units={units}&appid={settings.WEATHER_API_KEY}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        return {
            "temperature": Decimal(str(data["main"]["temp"])),
            "feels_like": Decimal(str(data["main"].get("feels_like", data["main"]["temp"]))),
            "humidity": data["main"].get("humidity"),
            "wind_speed": Decimal(str(data.get("wind", {}).get("speed", 0))),
            "description": data["weather"][0].get("description", ""),
            "icon": data["weather"][0].get("icon", ""),
            "pressure": data["main"].get("pressure"),
            "clouds": data.get("clouds", {}).get("all"),
            "uvi": None,
        }
    except (requests.RequestException, KeyError, ValueError) as e:
        logger.error(f"Failed to fetch weather from OpenWeatherMap: {e}")
        return None


def fetch_weather(lat: Decimal, lon: Decimal, provider: str = "openweathermap") -> dict | None:
    """Fetch weather from configured provider."""
    if provider == "openweathermap":
        return fetch_weather_from_openweathermap(lat, lon)
    logger.warning(f"Unknown weather provider: {provider}")
    return None
