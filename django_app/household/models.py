from django.conf import settings
from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class HouseholdRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        abstract = True


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

    class Meta:
        ordering = ("completed_at", "due_at", "-priority", "created_at")


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


class Routine(HouseholdRecord):
    title = models.CharField(max_length=200)
    cadence = models.CharField(max_length=80, default="wekelijks")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)


class ShoppingPrice(HouseholdRecord):
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
    product_url = models.URLField(blank=True)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("item", "retailer"), name="unique_price_per_item_retailer")]
        ordering = ("price",)


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
