from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from common.db_scope import household_db_scope
from household.models import ShoppingItem
from household.price_providers import refresh_household_prices
from households.models import Household


@shared_task
def replenish_recurring_shopping_items():
    """Create the next open list entry only after the configured interval."""
    threshold = timezone.now()
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            completed_items = ShoppingItem.objects.for_household(household).filter(recurring=True, completed_at__isnull=False).select_related("list")
            for item in completed_items:
                if item.completed_at > threshold - timedelta(days=item.recurrence_days):
                    continue
                if ShoppingItem.objects.for_household(household).filter(list=item.list, name__iexact=item.name, completed_at__isnull=True).exists():
                    continue
                ShoppingItem.objects.create(household=household, list=item.list, name=item.name, quantity=item.quantity, category=item.category, recurring=True, recurrence_days=item.recurrence_days)


@shared_task
def process_receipt_ocr(receipt_id, household_id):
    from household.ocr import process_receipt
    with household_db_scope(household_id):
        process_receipt(receipt_id)


@shared_task
def refresh_household_shopping_prices(household_id):
    household = Household.objects.filter(pk=household_id).first()
    if not household:
        return {"updated": 0, "offers": 0, "errors": 0}
    with household_db_scope(household_id):
        return refresh_household_prices(household)


@shared_task
def refresh_shopping_prices():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            refresh_household_prices(household)


@shared_task
def refresh_household_weather():
    from household.models import WeatherPreference, WeatherData
    from household.weather_service import fetch_weather
    from django.conf import settings

    for pref in WeatherPreference.objects.select_related("household").filter(latitude__isnull=False, longitude__isnull=False):
        if not settings.WEATHER_API_KEY:
            continue

        weather_data = fetch_weather(pref.latitude, pref.longitude, settings.WEATHER_API_PROVIDER)
        if weather_data:
            with household_db_scope(pref.household.pk):
                WeatherData.objects.create(household=pref.household, **weather_data)
