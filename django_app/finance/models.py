from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class FinanceRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        abstract = True


class BankConnection(FinanceRecord):
    class Provider(models.TextChoices):
        BUNQ = "bunq", "bunq"
        ABN_MANUAL = "abn_amro_manual", "ABN AMRO import"

    provider = models.CharField(max_length=32, choices=Provider.choices)
    display_name = models.CharField(max_length=160)
    status = models.CharField(max_length=24, default="configured")
    external_reference = models.CharField(max_length=180, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "provider", "external_reference"), name="unique_household_finance_connection")]


class BankAccount(FinanceRecord):
    connection = models.ForeignKey(BankConnection, on_delete=models.CASCADE, related_name="accounts")
    provider_account_id = models.CharField(max_length=180)
    name = models.CharField(max_length=160)
    iban = models.CharField(max_length=48, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("connection", "provider_account_id"), name="unique_provider_bank_account")]


class Transaction(FinanceRecord):
    account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="transactions")
    provider_transaction_id = models.CharField(max_length=180)
    booked_at = models.DateField()
    description = models.TextField()
    counterparty = models.CharField(max_length=240, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    payment_type = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    recurring_override = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ("-booked_at", "-id")
        constraints = [models.UniqueConstraint(fields=("account", "provider_transaction_id"), name="unique_provider_transaction")]
        indexes = [models.Index(fields=("household", "booked_at")), models.Index(fields=("household", "counterparty"))]


class RecurringRule(FinanceRecord):
    class Direction(models.TextChoices):
        INCOME = "income", "Inkomsten"
        EXPENSE = "expense", "Kosten"

    class Group(models.TextChoices):
        FIXED = "fixed", "Vaste lasten"
        INSURANCE = "insurance", "Verzekeringen"
        CREDIT = "credit", "Leningen & credits"
        SUBSCRIPTION = "subscription", "Abonnementen"
        TAX = "tax", "Belastingen"
        OTHER = "other", "Overig"

    fingerprint = models.CharField(max_length=180)
    merchant = models.CharField(max_length=240)
    direction = models.CharField(max_length=12, choices=Direction.choices)
    group = models.CharField(max_length=16, choices=Group.choices, default=Group.OTHER)
    expected_amount = models.DecimalField(max_digits=14, decimal_places=2)
    cadence_days = models.PositiveIntegerField(default=30)
    occurrence_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateField(null=True, blank=True)
    user_confirmed = models.BooleanField(default=False)
    is_excluded = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("household", "fingerprint"), name="unique_household_recurring_fingerprint")]


class Budget(FinanceRecord):
    name = models.CharField(max_length=160)
    monthly_limit = models.DecimalField(max_digits=14, decimal_places=2)
    category = models.CharField(max_length=100, blank=True)
