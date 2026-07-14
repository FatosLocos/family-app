import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from common.db_scope import household_db_scope
from finance.models import RecurringRule, Transaction
from households.models import Household


def fingerprint(transaction: Transaction) -> str:
    value = transaction.counterparty or transaction.description
    value = re.sub(r"\d+", "", value.upper())
    return re.sub(r"\s+", " ", value).strip()[:180]


def refresh_household_recurring_rules(household):
    """Derive recurring rules while preserving an explicit user exclusion."""
    grouped = defaultdict(list)
    for transaction in Transaction.objects.for_household(household).order_by("booked_at"):
        if transaction.recurring_override is False:
            continue
        grouped[(fingerprint(transaction), transaction.amount >= 0)].append(transaction)
    for (key, income), transactions in grouped.items():
        dates = [item.booked_at for item in transactions]
        user_confirmed = any(item.recurring_override for item in transactions)
        automatic = len(dates) >= 2 and (dates[-1] - dates[0]).days >= 25
        if not automatic and not user_confirmed:
            continue
        existing = RecurringRule.objects.for_household(household).filter(fingerprint=key).first()
        if existing and existing.is_excluded and not user_confirmed:
            continue
        amounts = sorted(abs(item.amount) for item in transactions)
        # Income uses the lowest reliably observed amount unless the last three are higher.
        expected = amounts[0] if income else amounts[len(amounts) // 2]
        recent_amounts = [abs(item.amount) for item in transactions[-3:]]
        if income and len(recent_amounts) == 3 and len(set(recent_amounts)) == 1:
            expected = recent_amounts[-1]
        intervals = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
        cadence = max(1, round(sum(intervals) / len(intervals))) if intervals else 30
        RecurringRule.objects.update_or_create(household=household, fingerprint=key, defaults={
            "merchant": transactions[-1].counterparty or transactions[-1].description[:240],
            "direction": RecurringRule.Direction.INCOME if income else RecurringRule.Direction.EXPENSE,
            "expected_amount": expected, "cadence_days": cadence, "occurrence_count": len(transactions), "last_seen_at": dates[-1],
            "user_confirmed": user_confirmed, "is_excluded": False if user_confirmed else (existing.is_excluded if existing else False),
        })


@shared_task
def refresh_recurring_rules():
    for household in Household.objects.all():
        with household_db_scope(household.pk):
            refresh_household_recurring_rules(household)
