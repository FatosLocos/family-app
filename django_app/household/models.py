from django.conf import settings
from django.db import models
from django.utils import timezone

from common.scoping import HouseholdManager
from households.models import Household


class HouseholdRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        abstract = True


class TaskList(HouseholdRecord):
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [models.UniqueConstraint(fields=("household", "name"), name="unique_task_list_name")]

    def __str__(self):
        return self.name


class Task(HouseholdRecord):
    class Priority(models.IntegerChoices):
        LOW = 1, "Laag"
        NORMAL = 2, "Normaal"
        HIGH = 3, "Hoog"

    title = models.CharField(max_length=240)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tasks")
    due_at = models.DateTimeField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(choices=Priority.choices, default=Priority.NORMAL)
    completed_at = models.DateTimeField(null=True, blank=True)
    list = models.ForeignKey(TaskList, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "created_at")


class ShoppingList(HouseholdRecord):
    name = models.CharField(max_length=120, default="Boodschappen")
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "name"), name="unique_shopping_list_name")]


class ShoppingItem(HouseholdRecord):
    list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    quantity = models.CharField(max_length=60, blank=True)
    category = models.CharField(max_length=80, blank=True)
    recurring = models.BooleanField(default=False)
    recurrence_days = models.PositiveSmallIntegerField(default=7)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("completed_at", "created_at")


class MealPlan(HouseholdRecord):
    title = models.CharField(max_length=200)
    planned_for = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("planned_for",)


class MealIngredient(HouseholdRecord):
    meal = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name="ingredients")
    name = models.CharField(max_length=200)
    quantity = models.CharField(max_length=60, blank=True)
    category = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ("created_at", "id")


class PantryItem(HouseholdRecord):
    name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    unit = models.CharField(max_length=32, default="stuks")
    minimum_quantity = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    category = models.CharField(max_length=80, blank=True)
    expires_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "name"), name="unique_household_pantry_item")]
        ordering = ("category", "name")


class Routine(HouseholdRecord):
    title = models.CharField(max_length=200)
    cadence = models.CharField(max_length=80, default="wekelijks")
    interval_days = models.PositiveSmallIntegerField(default=7)
    next_due_on = models.DateField(default=timezone.localdate)
    last_completed_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)


class ShoppingPrice(HouseholdRecord):
    class Source(models.TextChoices):
        MANUAL = "manual", "Handmatig"
        CHECKJEBON = "checkjebon", "Checkjebon"
        PRIJSPROFEET = "prijsprofeet", "PrijsProfeet"

    class Retailer(models.TextChoices):
        ALBERT_HEIJN = "ah", "Albert Heijn"
        JUMBO = "jumbo", "Jumbo"
        LIDL = "lidl", "Lidl"
        KAUFLAND = "kaufland", "Kaufland"

    item = models.ForeignKey(ShoppingItem, on_delete=models.CASCADE, related_name="prices")
    retailer = models.CharField(max_length=20, choices=Retailer.choices)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    unit_label = models.CharField(max_length=60, blank=True)
    is_offer = models.BooleanField(default=False)
    offer_label = models.CharField(max_length=160, blank=True)
    regular_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    offer_valid_until = models.DateField(null=True, blank=True)
    product_url = models.URLField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    matched_product_name = models.CharField(max_length=240, blank=True)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("item", "retailer"), name="unique_price_per_item_retailer")]
        ordering = ("price",)


class ShoppingOffer(HouseholdRecord):
    """A retailer promotion kept separate from the comparable base price."""

    item = models.ForeignKey(ShoppingItem, on_delete=models.CASCADE, related_name="offers")
    retailer = models.CharField(max_length=20, choices=ShoppingPrice.Retailer.choices)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    matched_product_name = models.CharField(max_length=240, blank=True)
    offer_label = models.CharField(max_length=160, blank=True)
    regular_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    offer_valid_until = models.DateField(null=True, blank=True)
    product_url = models.URLField(blank=True)
    source = models.CharField(max_length=20, choices=ShoppingPrice.Source.choices, default=ShoppingPrice.Source.PRIJSPROFEET)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("item", "retailer", "source"), name="unique_offer_per_item_retailer_source")]
        ordering = ("price",)


class ShoppingPriceProviderStatus(HouseholdRecord):
    """Last known result for each external shopping-price source."""

    class Provider(models.TextChoices):
        CHECKJEBON = "checkjebon", "Checkjebon"
        PRIJSPROFEET = "prijsprofeet", "PrijsProfeet"

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Beschikbaar"
        FAILED = "failed", "Niet bereikbaar"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCEEDED)
    detail = models.CharField(max_length=240, blank=True)
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "provider"), name="unique_household_price_provider_status")]
        ordering = ("provider",)


class ShoppingPriceSnapshot(HouseholdRecord):
    """An immutable observation for a meaningful retailer price change."""

    item = models.ForeignKey(ShoppingItem, on_delete=models.CASCADE, related_name="price_snapshots")
    retailer = models.CharField(max_length=20, choices=ShoppingPrice.Retailer.choices)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    unit_label = models.CharField(max_length=60, blank=True)
    is_offer = models.BooleanField(default=False)
    offer_label = models.CharField(max_length=160, blank=True)
    regular_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=20, choices=ShoppingPrice.Source.choices)
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-observed_at",)
        indexes = [models.Index(fields=("item", "retailer", "-observed_at"), name="shopping_price_history_idx")]


def receipt_upload_path(instance, filename):
    from pathlib import Path
    from uuid import uuid4
    return f"receipts/{instance.household_id}/{uuid4().hex}{Path(filename).suffix.lower()}"


class Receipt(HouseholdRecord):
    class OcrStatus(models.TextChoices):
        PENDING = "pending", "Wacht op OCR"
        COMPLETE = "complete", "Herkenning klaar"
        FAILED = "failed", "Herkenning mislukt"

    retailer = models.CharField(max_length=120, blank=True)
    purchased_on = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image = models.FileField(upload_to=receipt_upload_path)
    ocr_text = models.TextField(blank=True)
    ocr_status = models.CharField(max_length=20, choices=OcrStatus.choices, default=OcrStatus.PENDING)
    ocr_error = models.CharField(max_length=300, blank=True)
    transaction = models.ForeignKey("finance.Transaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="receipts")

    class Meta:
        ordering = ("-purchased_on", "-created_at")


class ReceiptLineItem(HouseholdRecord):
    """A conservative product row recognised from a receipt image or PDF."""

    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="line_items")
    shopping_item = models.ForeignKey(ShoppingItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="receipt_line_items")
    name = models.CharField(max_length=240)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    raw_line = models.CharField(max_length=500, blank=True)


class WeatherPreference(models.Model):
    household = models.OneToOneField(Household, on_delete=models.CASCADE, related_name="weather_preference")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_name = models.CharField(max_length=200, blank=True)
    temperature_unit = models.CharField(max_length=1, choices=[("C", "Celsius"), ("F", "Fahrenheit")], default="C")
    wind_unit = models.CharField(max_length=3, choices=[("ms", "m/s"), ("kmh", "km/h"), ("mph", "mph")], default="ms")
    show_forecast = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Weather preferences"

    def __str__(self) -> str:
        return f"Weather for {self.household.name}"


class WeatherData(HouseholdRecord):
    temperature = models.DecimalField(max_digits=5, decimal_places=1)
    feels_like = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    humidity = models.PositiveSmallIntegerField(null=True, blank=True)
    wind_speed = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    description = models.CharField(max_length=100, blank=True)
    icon = models.CharField(max_length=20, blank=True)
    pressure = models.PositiveIntegerField(null=True, blank=True)
    uvi = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    clouds = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
